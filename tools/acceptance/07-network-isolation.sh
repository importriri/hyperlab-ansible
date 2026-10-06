#!/usr/bin/env bash
# Group 7: guest isolation on the host (roadmap milestone 9; the fail-closed
# rule for undeclared bridges and the lab host's network, ADR 0046). Applies
# playbooks/foundation.yml, so it changes the host firewall: the ruleset and
# the dev leases are kept first, and the report names the rollback.
export ACCEPTANCE_GROUP=07-network-isolation
# shellcheck source=tools/acceptance/lib.sh disable=SC1091
source "$(dirname "$0")/lib.sh"
acceptance_start
# Asked here, once: every check below runs in a subshell and inherits it.
become_once

backup_root "nft ruleset before" nft list ruleset
backup_root "lab-isolation.nft before" cat /etc/nftables.d/lab-isolation.nft
backup "dev leases before" virsh --connect qemu:///system net-dhcp-leases dev
rollback "sudo nft flush chain inet lab_isolation input   (immediate, only the guest-to-host chain)"
rollback "sudo cp $EVIDENCE/backup-lab-isolation-nft-before /etc/nftables.d/lab-isolation.nft && sudo systemctl reload nftables"

# Fail closed: foundation is offered only after a clean dry run.
if check "foundation check mode" playbook "foundation check" -i inventory.ini playbooks/foundation.yml --check --diff; then
    report "Read the check-mode diff in the evidence before going on: only the isolation rules and the boot entries may change."
    if confirm apply "apply playbooks/foundation.yml (the new guest isolation takes effect at once)"; then
        check "foundation applied" playbook "foundation apply" -i inventory.ini playbooks/foundation.yml

        expect "input chain ends with the virbr* catch-all" 'iifname "virbr\*" counter packets [0-9]+ bytes [0-9]+ drop' \
            as_root "read the input chain" nft list chain inet lab_isolation input
        expect "the lab host's bridge is isolated" 'iifname "virbr-hl-lab" counter packets [0-9]+ bytes [0-9]+ drop' \
            as_root "read the input chain" nft list chain inet lab_isolation input
        expect "forward chain ends with the bridge-to-bridge catch-all" \
            'iifname "virbr\*" oifname "virbr\*" counter packets [0-9]+ bytes [0-9]+ drop' \
            as_root "read the forward chain" nft list chain inet lab_isolation forward

        check "SSH to srv-tz-01" ansible srv-tz-01 -i inventory.ini -i "${XDG_RUNTIME_DIR}/srv-tz-01.ini" -m ping
        check "DNS inside srv-tz-01" ansible srv-tz-01 -i inventory.ini -i "${XDG_RUNTIME_DIR}/srv-tz-01.ini" \
            -m command -a "getent hosts archlinux.org"
        check "srv-tz-01 cannot reach the dev resolver" ansible srv-tz-01 -i inventory.ini \
            -i "${XDG_RUNTIME_DIR}/srv-tz-01.ini" -m shell -a "! timeout 3 bash -c '</dev/tcp/10.10.3.1/53'"
        check "srv-tz-01 cannot reach the host's LLMNR" ansible srv-tz-01 -i inventory.ini \
            -i "${XDG_RUNTIME_DIR}/srv-tz-01.ini" -m shell -a "! timeout 3 bash -c '</dev/tcp/10.10.5.1/5355'"
        backup "dev leases after" virsh --connect qemu:///system net-dhcp-leases dev
    fi
else
    report "APPLY NOT OFFERED: the check mode failed (the failed task is above); nothing was changed."
fi
acceptance_end
