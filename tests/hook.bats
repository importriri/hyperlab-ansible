#!/usr/bin/env bats
# Protocol tests for the gpu_handoff qemu hook. The hook is invoked
# DIRECTLY (not via bash): the executable bit is part of the contract.

setup() {
    TESTDIR="$(mktemp -d)"
    export GPU_HANDOFF_ROTATION="${TESTDIR}/rotation"
    export GPU_HANDOFF_DOMAINS="${TESTDIR}/domains"
    export GPU_HANDOFF_MANAGED_DIR="${TESTDIR}/domains.d"
    export GPU_HANDOFF_STATE_DIR="${TESTDIR}/state"
    mkdir -m 0755 "${GPU_HANDOFF_MANAGED_DIR}"
    HOOK="${BATS_TEST_DIRNAME}/../roles/gpu_handoff/files/qemu"
    cat > "${GPU_HANDOFF_ROTATION}" <<EOF
# network trust
clean 3
dev 2
dirty 1
lab 0
EOF
    cat > "${GPU_HANDOFF_DOMAINS}" <<EOF
# exact-libvirt-domain network-profile
win11clean-valley clean
arch-dev-vfio dev
win11dirty-disposable dirty
win11lab-test lab
EOF
    # libvirt passes the domain XML on stdin. An unlisted domain is judged
    # by it: no PCI passthrough passes, PCI passthrough is refused.
    PLAIN_XML="${TESTDIR}/plain.xml"
    cat > "${PLAIN_XML}" <<EOF
<domain type='kvm'><name>svc-jellyfin</name><devices>
<disk type='file' device='disk'/><interface type='network'/>
</devices></domain>
EOF
    PCI_XML="${TESTDIR}/pci.xml"
    cat > "${PCI_XML}" <<EOF
<domain type='kvm'><name>rogue-vfio</name><devices>
<hostdev mode='subsystem' type='pci' managed='yes'>
<source><address domain='0x0000' bus='0x01' slot='0x00' function='0x0'/></source>
</hostdev></devices></domain>
EOF
    NIC_XML="${TESTDIR}/nic.xml"
    cat > "${NIC_XML}" <<EOF
<domain type='kvm'><name>rogue-nic</name><devices>
<interface type="hostdev" managed="yes"><source/></interface>
</devices></domain>
EOF
    # Failure injection replaces one utility on PATH. chmod alone is no
    # injection: the battery also runs as root.
    FAKE_BIN="${TESTDIR}/bin"
    mkdir "${FAKE_BIN}"
    REAL_FLOCK="$(command -v flock)"
    REAL_MKTEMP="$(command -v mktemp)"
    export REAL_FLOCK REAL_MKTEMP
    BACKGROUND_PIDS=()
    EVENT_LOG=()
    declare -gA REPORT_FD=()
}

teardown() {
    local pid
    for pid in "${BACKGROUND_PIDS[@]}"; do
        kill "${pid}" 2>/dev/null || :
    done
    rm -rf "${TESTDIR}"
}

state() {
    cat "${GPU_HANDOFF_STATE_DIR}/trust"
}

# Record a complete committed rung and a byte copy to compare against.
seed_state() {
    mkdir -p "${GPU_HANDOFF_STATE_DIR}"
    printf '%s\n' "$1" > "${GPU_HANDOFF_STATE_DIR}/trust"
    cp "${GPU_HANDOFF_STATE_DIR}/trust" "${TESTDIR}/trust.before"
}

# Replace one utility for the hook: fake <name> <bash body>.
fake() {
    printf '#!/usr/bin/env bash\n%s\n' "$2" > "${FAKE_BIN}/$1"
    chmod 0755 "${FAKE_BIN}/$1"
}

run_hook_with_fakes() {
    run env PATH="${FAKE_BIN}:${PATH}" "${HOOK}" "$@"
}

temp_files() {
    find "${GPU_HANDOFF_STATE_DIR}" -mindepth 1 -name 'trust.*' | wc -l
}

# Barrier utilities for the concurrency tests. They observe and pause the
# hook; the lock itself is the real flock(2) on the hook's own lock file.
# flock reports whether the lock was free or held by the other request,
# then runs the real flock with the hook's arguments. mktemp is the first
# step of the commit, after the previous rung was read: a request started
# with BARRIER_HOLD=1 waits there until the test opens the gate.
make_barriers() {
    EVENTS="${TESTDIR}/events"
    GATE="${TESTDIR}/gate"
    mkfifo "${EVENTS}" "${GATE}"
    export BARRIER_EVENTS="${EVENTS}" BARRIER_GATE="${GATE}"
    # Read-write opens never block on a FIFO and keep both ends alive.
    exec {events_fd}<>"${EVENTS}"
    exec {gate_fd}<>"${GATE}"
    # shellcheck disable=SC2016 # expanded by the fake, not here
    fake flock '
fd="${*: -1}"
if "${REAL_FLOCK}" -n -x "${fd}"; then seen=free; else seen=contended; fi
printf "lock %s %s\n" "${seen}" "${BARRIER_ROLE}" > "${BARRIER_EVENTS}"
exec "${REAL_FLOCK}" "$@"'
    # shellcheck disable=SC2016 # expanded by the fake, not here
    fake mktemp '
printf "commit %s\n" "${BARRIER_ROLE}" > "${BARRIER_EVENTS}"
if [[ "${BARRIER_HOLD:-}" == 1 ]]; then
    read -r -t 20 _ < "${BARRIER_GATE}" || exit 1
fi
exec "${REAL_MKTEMP}" "$@"'
}

# The GPU profile each race role requests.
declare -gA ROLE_DOMAIN=(
    [clean]=win11clean-valley
    [dev]=arch-dev-vfio
    [dirty]=win11dirty-disposable
)

# Start one prepare in the background. When the hook exits it reports
# "exit <role>" at once, then waits for its own report gate before
# reporting "done <role> <status>", so the test decides the order in which
# completions arrive.
start_prepare() {
    local role="$1" hold="$2" report_fd
    mkfifo "${TESTDIR}/report-${role}"
    exec {report_fd}<>"${TESTDIR}/report-${role}"
    REPORT_FD[${role}]="${report_fd}"
    {
        local rc=0
        env PATH="${FAKE_BIN}:${PATH}" BARRIER_ROLE="${role}" \
            BARRIER_HOLD="${hold}" timeout 30 "${HOOK}" "${ROLE_DOMAIN[${role}]}" prepare \
            > "${TESTDIR}/${role}.out" 2>&1 || rc=$?
        printf 'exit %s\n' "${role}" > "${EVENTS}"
        read -r -t 20 _ < "${TESTDIR}/report-${role}" || rc="${rc}-unreleased"
        printf 'done %s %s\n' "${role}" "${rc}" > "${EVENTS}"
    } 3>&- &
    BACKGROUND_PIDS+=("$!")
}

# take_event [--keep] <regex>: the first event not yet taken that matches,
# in arrival order, reading more within a bound when none has arrived yet.
# Events that do not match stay for a later take. --keep leaves the match
# in place: it only waits for the arrival.
take_event() {
    local keep=0 pattern line i=0
    if [[ "$1" == --keep ]]; then
        keep=1
        shift
    fi
    pattern="$1"
    while :; do
        for (( ; i < ${#EVENT_LOG[@]}; i++ )); do
            if [[ "${EVENT_LOG[i]}" =~ ${pattern} ]]; then
                AWAITED="${EVENT_LOG[i]}"
                if (( keep == 0 )); then
                    EVENT_LOG=("${EVENT_LOG[@]:0:i}" "${EVENT_LOG[@]:i+1}")
                fi
                return 0
            fi
        done
        if ! read -r -t 20 -u "${events_fd}" line; then
            echo "no event matching '${pattern}' within the bound; untaken: ${EVENT_LOG[*]}" >&2
            return 1
        fi
        EVENT_LOG+=("${line}")
    done
}

# Release the completion reports one at a time, each only after the
# previous one has arrived: they arrive exactly in the order given.
report_in_order() {
    local role
    for role in "$@"; do
        printf 'go\n' >&"${REPORT_FD[${role}]}"
        take_event --keep "^done ${role} "
    done
}

# race <held> <waiting> <held status> <waiting status> <report order...>
# <held> reads the rung and stops before its commit. <waiting> is started
# only then; the test goes on once it is seen waiting on the lock, or
# finished (which only happens if nothing serializes them). Then <held>
# commits, both complete, and their reports arrive in the order given.
race() {
    local held="$1" waiting="$2" held_status="$3" waiting_status="$4"
    shift 4
    make_barriers
    start_prepare "${held}" 1
    take_event "^commit ${held}$"

    start_prepare "${waiting}" 0
    take_event "^(lock contended ${waiting}|exit ${waiting})$"
    WAITING_SEEN="${AWAITED}"

    printf 'go\n' >&"${gate_fd}"
    report_in_order "$@"
    take_event "^done ${held} "
    [ "${AWAITED}" = "done ${held} ${held_status}" ]
    take_event "^done ${waiting} "
    [ "${AWAITED}" = "done ${waiting} ${waiting_status}" ]
}

@test "the hook file itself carries the executable bit (the 100644 trap)" {
    [ -x "${HOOK}" ]
}

@test "first reviewed GPU domain is allowed and records network trust" {
    run "${HOOK}" win11clean-valley prepare
    [ "$status" -eq 0 ]
    [ "$(state)" = "3" ]
}

@test "the reviewed Linux VFIO candidate records dev trust" {
    run "${HOOK}" arch-dev-vfio prepare
    [ "$status" -eq 0 ]
    [ "$(state)" = "2" ]
}

@test "downgrade is allowed across exact domains (clean -> dirty)" {
    "${HOOK}" win11clean-valley prepare
    run "${HOOK}" win11dirty-disposable prepare
    [ "$status" -eq 0 ]
    [ "$(state)" = "1" ]
}

@test "lateral restart at the same trust is allowed" {
    "${HOOK}" win11dirty-disposable prepare
    run "${HOOK}" win11dirty-disposable prepare
    [ "$status" -eq 0 ]
    [ "$(state)" = "1" ]
}

@test "upgrade is refused and leaves state untouched (dirty -> clean)" {
    "${HOOK}" win11dirty-disposable prepare
    run "${HOOK}" win11clean-valley prepare
    [ "$status" -eq 1 ]
    [[ "$output" == *REFUSING* ]]
    [ "$(state)" = "1" ]
}

@test "lab can start first when explicitly reviewed" {
    run "${HOOK}" win11lab-test prepare
    [ "$status" -eq 0 ]
    [ "$(state)" = "0" ]
}

@test "after lab every cleaner reviewed GPU domain is refused until reboot" {
    "${HOOK}" win11lab-test prepare
    run "${HOOK}" win11dirty-disposable prepare
    [ "$status" -eq 1 ]
}

@test "a reboot (state dir gone) reopens the ladder" {
    "${HOOK}" win11lab-test prepare
    rm -rf "${GPU_HANDOFF_STATE_DIR}"
    run "${HOOK}" win11clean-valley prepare
    [ "$status" -eq 0 ]
    [ "$(state)" = "3" ]
}

@test "corrupt state refuses reviewed GPU domains" {
    mkdir -p "${GPU_HANDOFF_STATE_DIR}"
    echo garbage > "${GPU_HANDOFF_STATE_DIR}/trust"
    run "${HOOK}" win11clean-valley prepare
    [ "$status" -eq 1 ]
}

@test "corrupt rotation refuses a reviewed GPU domain" {
    echo "clean banana" > "${GPU_HANDOFF_ROTATION}"
    run "${HOOK}" win11clean-valley prepare
    [ "$status" -eq 1 ]
}

@test "missing rotation refuses before membership decisions" {
    rm -f "${GPU_HANDOFF_ROTATION}"
    run "${HOOK}" win11clean-valley prepare
    [ "$status" -eq 1 ]
}

@test "empty rotation is a broken config" {
    : > "${GPU_HANDOFF_ROTATION}"
    run "${HOOK}" win11clean-valley prepare
    [ "$status" -eq 1 ]
}

@test "missing domain allowlist fails closed even for a service VM" {
    rm -f "${GPU_HANDOFF_DOMAINS}"
    run "${HOOK}" svc-jellyfin prepare
    [ "$status" -eq 1 ]
}

@test "an unknown profile in the exact allowlist is refused" {
    echo "win11clean-valley unknown" > "${GPU_HANDOFF_DOMAINS}"
    run "${HOOK}" win11clean-valley prepare
    [ "$status" -eq 1 ]
    [[ "$output" == *"unknown profile"* ]]
}

@test "an unlisted service domain passes while GPU trust is held" {
    "${HOOK}" win11clean-valley prepare
    run "${HOOK}" svc-jellyfin prepare < "${PLAIN_XML}"
    [ "$status" -eq 0 ]
    [ "$(state)" = "3" ]
}

@test "an unlisted service domain passes with no state and creates none" {
    run "${HOOK}" svc-jellyfin prepare < "${PLAIN_XML}"
    [ "$status" -eq 0 ]
    [ ! -e "${GPU_HANDOFF_STATE_DIR}/trust" ]
}

@test "network profile names alone are not GPU domain names" {
    run "${HOOK}" clean prepare < "${PLAIN_XML}"
    [ "$status" -eq 0 ]
    [ ! -e "${GPU_HANDOFF_STATE_DIR}/trust" ]
}

@test "an unlisted domain with PCI passthrough is refused and records nothing" {
    run "${HOOK}" rogue-vfio prepare < "${PCI_XML}"
    [ "$status" -eq 1 ]
    [[ "$output" == *"PCI passthrough without a reviewed GPU handoff policy"* ]]
    [ ! -e "${GPU_HANDOFF_STATE_DIR}/trust" ]
}

@test "an unlisted domain cannot take PCI passthrough while trust is held" {
    "${HOOK}" win11dirty-disposable prepare
    run "${HOOK}" rogue-vfio prepare < "${PCI_XML}"
    [ "$status" -eq 1 ]
    [ "$(state)" = "1" ]
}

@test "an unlisted domain with a hostdev network interface is refused" {
    run "${HOOK}" rogue-nic prepare < "${NIC_XML}"
    [ "$status" -eq 1 ]
}

@test "an unlisted domain without domain XML fails closed" {
    run "${HOOK}" svc-jellyfin prepare < /dev/null
    [ "$status" -eq 1 ]
    [ ! -e "${GPU_HANDOFF_STATE_DIR}/trust" ]
}

@test "non-prepare phases pass instantly even for an upgrade" {
    "${HOOK}" win11dirty-disposable prepare
    run "${HOOK}" win11clean-valley started
    [ "$status" -eq 0 ]
    [ "$(state)" = "1" ]
}

@test "a C10 managed SERVICES Machine may use reviewed dev GPU handoff" {
    printf 'services-workload-01 dev\n' \
        > "${GPU_HANDOFF_MANAGED_DIR}/services-workload-01.conf"
    chmod 0644 "${GPU_HANDOFF_MANAGED_DIR}/services-workload-01.conf"

    run "${HOOK}" services-workload-01 prepare
    [ "$status" -eq 0 ]
    [ "$(state)" = "2" ]
}

@test "a SERVICES Machine's GPU use is a rung: a cleaner domain after it is refused" {
    printf 'services-workload-01 dev\n' \
        > "${GPU_HANDOFF_MANAGED_DIR}/services-workload-01.conf"
    chmod 0644 "${GPU_HANDOFF_MANAGED_DIR}/services-workload-01.conf"

    "${HOOK}" services-workload-01 prepare
    run "${HOOK}" win11clean-valley prepare
    [ "$status" -eq 1 ]
    [[ "$output" == *REFUSING* ]]
    [ "$(state)" = "2" ]
}

@test "a SERVICES Machine cannot raise the ladder after a dirtier use" {
    printf 'services-workload-01 dev\n' \
        > "${GPU_HANDOFF_MANAGED_DIR}/services-workload-01.conf"
    chmod 0644 "${GPU_HANDOFF_MANAGED_DIR}/services-workload-01.conf"

    "${HOOK}" win11dirty-disposable prepare
    run "${HOOK}" services-workload-01 prepare
    [ "$status" -eq 1 ]
    [[ "$output" == *REFUSING* ]]
    [ "$(state)" = "1" ]
}

@test "duplicate static and managed domain policy fails closed" {
    printf 'arch-dev-vfio dev\n' \
        > "${GPU_HANDOFF_MANAGED_DIR}/arch-dev-vfio.conf"
    chmod 0644 "${GPU_HANDOFF_MANAGED_DIR}/arch-dev-vfio.conf"

    run "${HOOK}" arch-dev-vfio prepare
    [ "$status" -eq 1 ]
    [[ "$output" == *"duplicate domain"* ]]
}

@test "a redirected managed Machine policy fails closed" {
    printf 'services-workload-01 dev\n' > "${TESTDIR}/redirected"
    ln -s "${TESTDIR}/redirected" \
        "${GPU_HANDOFF_MANAGED_DIR}/services-workload-01.conf"

    run "${HOOK}" services-workload-01 prepare
    [ "$status" -eq 1 ]
    [[ "$output" == *"unsafe managed policy"* ]]
}

@test "a managed policy filename must match its exact domain" {
    printf 'other-machine dev\n' \
        > "${GPU_HANDOFF_MANAGED_DIR}/services-workload-01.conf"
    chmod 0644 "${GPU_HANDOFF_MANAGED_DIR}/services-workload-01.conf"

    run "${HOOK}" services-workload-01 prepare
    [ "$status" -eq 1 ]
    [[ "$output" == *"expected services-workload-01"* ]]
}

@test "missing managed policy directory fails closed" {
    rm -rf "${GPU_HANDOFF_MANAGED_DIR}"

    run "${HOOK}" svc-jellyfin prepare
    [ "$status" -eq 1 ]
    [[ "$output" == *"missing or redirected"* ]]
}

# --- the state transaction: lock, read, compare, atomic commit ---------------

@test "the lock is created private and the published rung stays world-readable" {
    run "${HOOK}" win11dirty-disposable prepare
    [ "$status" -eq 0 ]
    [ "$(stat -c %a "${GPU_HANDOFF_STATE_DIR}/lock")" = "600" ]
    [ "$(stat -c %a "${GPU_HANDOFF_STATE_DIR}/trust")" = "644" ]
    [ "$(temp_files)" -eq 0 ]
}

@test "a failed lock acquisition refuses and leaves the rung byte-identical" {
    seed_state 3
    fake flock 'exit 1'
    run_hook_with_fakes win11dirty-disposable prepare
    [ "$status" -eq 1 ]
    [[ "$output" == *"cannot lock"* ]]
    cmp "${TESTDIR}/trust.before" "${GPU_HANDOFF_STATE_DIR}/trust"
}

@test "a failed lock acquisition on a fresh boot records nothing" {
    fake flock 'exit 1'
    run_hook_with_fakes win11clean-valley prepare
    [ "$status" -eq 1 ]
    [ ! -e "${GPU_HANDOFF_STATE_DIR}/trust" ]
}

@test "a redirected lock is refused and its target is not created" {
    mkdir -p "${GPU_HANDOFF_STATE_DIR}"
    ln -s "${TESTDIR}/victim" "${GPU_HANDOFF_STATE_DIR}/lock"
    run "${HOOK}" win11clean-valley prepare
    [ "$status" -eq 1 ]
    [[ "$output" == *"lock"*"redirected"* ]]
    [ ! -e "${TESTDIR}/victim" ]
    [ ! -e "${GPU_HANDOFF_STATE_DIR}/trust" ]
}

@test "a lock that is not a regular file is refused" {
    mkdir -p "${GPU_HANDOFF_STATE_DIR}/lock"
    run "${HOOK}" win11clean-valley prepare
    [ "$status" -eq 1 ]
    [ ! -e "${GPU_HANDOFF_STATE_DIR}/trust" ]
}

@test "a redirected state directory is refused and nothing is written there" {
    mkdir "${TESTDIR}/elsewhere"
    ln -s "${TESTDIR}/elsewhere" "${GPU_HANDOFF_STATE_DIR}"
    run "${HOOK}" win11clean-valley prepare
    [ "$status" -eq 1 ]
    [[ "$output" == *"redirected"* ]]
    [ -z "$(ls -A "${TESTDIR}/elsewhere")" ]
}

@test "a redirected trust file is refused and neither it nor its target changes" {
    mkdir -p "${GPU_HANDOFF_STATE_DIR}"
    printf '3\n' > "${TESTDIR}/elsewhere"
    ln -s "${TESTDIR}/elsewhere" "${GPU_HANDOFF_STATE_DIR}/trust"
    run "${HOOK}" win11dirty-disposable prepare
    [ "$status" -eq 1 ]
    [[ "$output" == *"redirected"* ]]
    [ -L "${GPU_HANDOFF_STATE_DIR}/trust" ]
    [ "$(cat "${TESTDIR}/elsewhere")" = "3" ]
    [ "$(temp_files)" -eq 0 ]
}

@test "a trust path that is not a regular file is refused" {
    mkdir -p "${GPU_HANDOFF_STATE_DIR}/trust"
    run "${HOOK}" win11dirty-disposable prepare
    [ "$status" -eq 1 ]
    [ -d "${GPU_HANDOFF_STATE_DIR}/trust" ]
    [ -z "$(ls -A "${GPU_HANDOFF_STATE_DIR}/trust")" ]
}

@test "a failed temporary file creation refuses and leaves the rung byte-identical" {
    seed_state 3
    fake mktemp 'exit 1'
    run_hook_with_fakes win11dirty-disposable prepare
    [ "$status" -eq 1 ]
    [[ "$output" == *"cannot create a temporary state file"* ]]
    cmp "${TESTDIR}/trust.before" "${GPU_HANDOFF_STATE_DIR}/trust"
}

@test "a temporary file outside the state directory is refused and kept" {
    seed_state 3
    : > "${TESTDIR}/foreign"
    fake mktemp "echo '${TESTDIR}/foreign'"
    run_hook_with_fakes win11dirty-disposable prepare
    [ "$status" -eq 1 ]
    cmp "${TESTDIR}/trust.before" "${GPU_HANDOFF_STATE_DIR}/trust"
    [ -e "${TESTDIR}/foreign" ]
    [ ! -s "${TESTDIR}/foreign" ]
}

# A real short write: the file-size limit binds root too, and an ignored
# SIGXFSZ turns it into an EFBIG write error inside the hook.
@test "a failed rung write refuses, keeps the old rung and leaves no temporary file" {
    seed_state 3
    # shellcheck disable=SC2016 # expanded by the inner shell
    run bash -c 'trap "" XFSZ; ulimit -f 0; exec "$@"' _ \
        "${HOOK}" win11dirty-disposable prepare
    [ "$status" -eq 1 ]
    [[ "$output" == *"cannot write"* ]]
    cmp "${TESTDIR}/trust.before" "${GPU_HANDOFF_STATE_DIR}/trust"
    [ "$(temp_files)" -eq 0 ]
}

@test "a failed first rung write records no state that could authorize a start" {
    # shellcheck disable=SC2016 # expanded by the inner shell
    run bash -c 'trap "" XFSZ; ulimit -f 0; exec "$@"' _ \
        "${HOOK}" win11dirty-disposable prepare
    [ "$status" -eq 1 ]
    [ ! -e "${GPU_HANDOFF_STATE_DIR}/trust" ]
    [ "$(temp_files)" -eq 0 ]
}

@test "a failed rename refuses, keeps the old rung and leaves no temporary file" {
    seed_state 3
    fake mv 'exit 1'
    run_hook_with_fakes win11dirty-disposable prepare
    [ "$status" -eq 1 ]
    [[ "$output" == *"cannot publish"* ]]
    cmp "${TESTDIR}/trust.before" "${GPU_HANDOFF_STATE_DIR}/trust"
    [ "$(temp_files)" -eq 0 ]
}

@test "an interrupted commit refuses, removes its temporary file and releases the lock" {
    seed_state 3
    # shellcheck disable=SC2016 # expanded by the fake
    fake mv 'kill -TERM "${PPID}"; exit 1'
    run_hook_with_fakes win11dirty-disposable prepare
    [ "$status" -eq 1 ]
    cmp "${TESTDIR}/trust.before" "${GPU_HANDOFF_STATE_DIR}/trust"
    [ "$(temp_files)" -eq 0 ]

    rm "${FAKE_BIN}/mv"
    run timeout 30 "${HOOK}" win11dirty-disposable prepare
    [ "$status" -eq 0 ]
    [ "$(state)" = "1" ]
}

@test "an interruption while taking the lock refuses and records nothing" {
    seed_state 3
    # shellcheck disable=SC2016 # expanded by the fake
    fake flock 'kill -TERM "${PPID}"; exec "${REAL_FLOCK}" "$@"'
    run_hook_with_fakes win11dirty-disposable prepare
    [ "$status" -eq 1 ]
    cmp "${TESTDIR}/trust.before" "${GPU_HANDOFF_STATE_DIR}/trust"
    [ "$(temp_files)" -eq 0 ]

    rm "${FAKE_BIN}/flock"
    run timeout 30 "${HOOK}" win11dirty-disposable prepare
    [ "$status" -eq 0 ]
    [ "$(state)" = "1" ]
}

# The step itself succeeds: only the signal can stop the commit here.
@test "an interruption during a successful commit step still refuses" {
    seed_state 3
    REAL_CHMOD="$(command -v chmod)"
    export REAL_CHMOD
    # shellcheck disable=SC2016 # expanded by the fake
    fake chmod 'kill -TERM "${PPID}"; exec "${REAL_CHMOD}" "$@"'
    run_hook_with_fakes win11dirty-disposable prepare
    [ "$status" -eq 1 ]
    cmp "${TESTDIR}/trust.before" "${GPU_HANDOFF_STATE_DIR}/trust"
    [ "$(temp_files)" -eq 0 ]
}

# The signal lands after the real temporary file exists and before the
# command that created it has returned its name to the hook. The fake sends
# it to the outermost process running the hook, never to a subshell.
@test "a signal while the temporary file is created removes it and refuses" {
    seed_state 3
    fake mktemp "$(cat <<'FAKE'
path="$("${REAL_MKTEMP}" "$@")" || exit 1
hook_pid="${PPID}"
parent_of() {
    local _pid _comm _state ppid _rest
    read -r _pid _comm _state ppid _rest < "/proc/$1/stat"
    printf '%s\n' "${ppid}"
}
runs_hook() {
    tr '\0' '\n' < "/proc/$1/cmdline" | grep -q 'gpu_handoff/files/qemu$'
}
runs_hook "${hook_pid}" || exit 1
while runs_hook "$(parent_of "${hook_pid}")"; do
    hook_pid="$(parent_of "${hook_pid}")"
done
kill -TERM "${hook_pid}"
printf '%s\n' "${path}"
FAKE
)"
    run_hook_with_fakes win11dirty-disposable prepare
    [ "$status" -eq 1 ]
    [[ "$output" == *"interrupted while creating"* ]]
    cmp "${TESTDIR}/trust.before" "${GPU_HANDOFF_STATE_DIR}/trust"
    [ "$(temp_files)" -eq 0 ]

    rm "${FAKE_BIN}/mktemp"
    run timeout 30 "${HOOK}" win11dirty-disposable prepare
    [ "$status" -eq 0 ]
    [ "$(state)" = "1" ]
}

@test "a killed hook releases the lock and keeps the old rung" {
    seed_state 3
    # shellcheck disable=SC2016 # expanded by the fake
    fake mv 'kill -KILL "${PPID}"; exit 1'
    run_hook_with_fakes win11dirty-disposable prepare
    [ "$status" -ne 0 ]
    cmp "${TESTDIR}/trust.before" "${GPU_HANDOFF_STATE_DIR}/trust"

    rm "${FAKE_BIN}/mv"
    run timeout 30 "${HOOK}" win11dirty-disposable prepare
    [ "$status" -eq 0 ]
    [ "$(state)" = "1" ]
}

# The old race: the cleaner request reads the fresh-boot state, the dirtier
# one commits, and the cleaner one then overwrites it with a higher rung.
# Each race runs twice, with the completion reports arriving in both orders.
@test "concurrent prepares on a fresh boot: a stale clean commit cannot overwrite dirty (clean reports first)" {
    race clean dirty 0 0 clean dirty
    [ "$(state)" = "1" ]
    [ "${WAITING_SEEN}" = "lock contended dirty" ]
    [ "$(temp_files)" -eq 0 ]
    run "${HOOK}" win11clean-valley prepare
    [ "$status" -eq 1 ]
    [[ "$output" == *REFUSING* ]]
    [ "$(state)" = "1" ]
}

@test "concurrent prepares on a fresh boot: a stale clean commit cannot overwrite dirty (dirty reports first)" {
    race clean dirty 0 0 dirty clean
    [ "$(state)" = "1" ]
    [ "${WAITING_SEEN}" = "lock contended dirty" ]
    [ "$(temp_files)" -eq 0 ]
}

@test "concurrent prepares on a fresh boot: clean waiting on a dirty commit is refused (dirty reports first)" {
    race dirty clean 0 1 dirty clean
    grep -q REFUSING "${TESTDIR}/clean.out"
    [ "$(state)" = "1" ]
    [ "${WAITING_SEEN}" = "lock contended clean" ]
    [ "$(temp_files)" -eq 0 ]
}

@test "concurrent prepares on a fresh boot: clean waiting on a dirty commit is refused (clean reports first)" {
    race dirty clean 0 1 clean dirty
    [ "$(state)" = "1" ]
    [ "${WAITING_SEEN}" = "lock contended clean" ]
}

# The same races over a committed rung: the lock must also hold when the
# previous rung exists, not only when the first one is being created.
@test "concurrent prepares over rung 3: a stale dev commit cannot overwrite dirty" {
    seed_state 3
    race dev dirty 0 0 dirty dev
    [ "$(state)" = "1" ]
    [ "${WAITING_SEEN}" = "lock contended dirty" ]
    [ "$(temp_files)" -eq 0 ]
    run "${HOOK}" arch-dev-vfio prepare
    [ "$status" -eq 1 ]
    [[ "$output" == *REFUSING* ]]
    [ "$(state)" = "1" ]
}

@test "concurrent prepares over rung 3: dev waiting on a dirty commit is refused" {
    seed_state 3
    race dirty dev 0 1 dev dirty
    grep -q REFUSING "${TESTDIR}/dev.out"
    [ "$(state)" = "1" ]
    [ "${WAITING_SEEN}" = "lock contended dev" ]
    [ "$(temp_files)" -eq 0 ]
    run "${HOOK}" arch-dev-vfio prepare
    [ "$status" -eq 1 ]
    [ "$(state)" = "1" ]
}
