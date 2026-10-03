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
}

teardown() {
    rm -rf "${TESTDIR}"
}

state() {
    cat "${GPU_HANDOFF_STATE_DIR}/trust"
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
