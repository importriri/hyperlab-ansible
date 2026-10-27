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

# Start one prepare in the background; it reports "done <role> <status>".
start_prepare() {
    local role="$1" hold="$2" domain="$3"
    {
        local rc=0
        env PATH="${FAKE_BIN}:${PATH}" BARRIER_ROLE="${role}" \
            BARRIER_HOLD="${hold}" timeout 30 "${HOOK}" "${domain}" prepare \
            > "${TESTDIR}/${role}.out" 2>&1 || rc=$?
        printf 'done %s %s\n' "${role}" "${rc}" > "${EVENTS}"
    } 3>&- &
    BACKGROUND_PIDS+=("$!")
}

# Read events until one matches an extended regex; fail after a bound.
await_event() {
    local pattern="$1" line=""
    while read -r -t 20 -u "${events_fd}" line; do
        if [[ "${line}" =~ ${pattern} ]]; then
            AWAITED="${line}"
            return 0
        fi
    done
    echo "no event matching '${pattern}' within the bound" >&2
    return 1
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
@test "concurrent prepares: a stale cleaner commit cannot overwrite a dirtier rung" {
    make_barriers
    start_prepare clean 1 win11clean-valley
    await_event '^commit clean$'

    # Without the lock the dirtier request commits here, before the gate.
    start_prepare dirty 0 win11dirty-disposable
    await_event '^(lock contended dirty|done dirty .*)$'
    dirty_first="${AWAITED}"

    printf 'go\n' >&"${gate_fd}"
    await_event '^done clean '
    [ "${AWAITED}" = "done clean 0" ]
    if [ "${dirty_first}" = "lock contended dirty" ]; then
        await_event '^done dirty '
        [ "${AWAITED}" = "done dirty 0" ]
    fi
    [ "$(state)" = "1" ]
    [ "${dirty_first}" = "lock contended dirty" ]
    [ "$(temp_files)" -eq 0 ]

    run "${HOOK}" win11clean-valley prepare
    [ "$status" -eq 1 ]
    [[ "$output" == *REFUSING* ]]
    [ "$(state)" = "1" ]
}

@test "concurrent prepares: a cleaner request waiting on a dirtier commit is refused" {
    make_barriers
    start_prepare dirty 1 win11dirty-disposable
    await_event '^commit dirty$'

    start_prepare clean 0 win11clean-valley
    await_event '^(lock contended clean|done clean .*)$'
    [ "${AWAITED}" = "lock contended clean" ]

    printf 'go\n' >&"${gate_fd}"
    await_event '^done dirty '
    [ "${AWAITED}" = "done dirty 0" ]
    await_event '^done clean '
    [ "${AWAITED}" = "done clean 1" ]
    grep -q REFUSING "${TESTDIR}/clean.out"
    [ "$(state)" = "1" ]
    [ "$(temp_files)" -eq 0 ]
}
