#!/usr/bin/env bash
# Group 10: boot once with AppArmor in the kernel (ADR 0037). Two runs:
#   10-apparmor-boot.sh prepare   checks, then a one-time boot into the
#                                 AppArmor entry (stops for confirmation)
#   10-apparmor-boot.sh verify    after that reboot
# The default entry never changes here: the next boot after the one-shot is
# the usual one, which is the rollback.
export ACCEPTANCE_GROUP=10-apparmor-boot-${1:-}
# shellcheck source=tools/acceptance/lib.sh disable=SC1091
source "$(dirname "$0")/lib.sh"
acceptance_start
become_once

entry=arch-linux-hardened-vfio-apparmor.conf
case ${1:-} in
prepare)
    backup "boot entries" bootctl list --no-pager
    backup "lsm before" cat /sys/kernel/security/lsm
    expect "the AppArmor entry exists" "$entry" bootctl list --no-pager
    expect "the default is still the Vfio entry" 'arch-linux-hardened-vfio\.conf' \
        as_root "read the default entry" bootctl status --no-pager
    rollback "reboot again: the one-shot applies once and the default entry boots next"
    if confirm reboot "boot once into the AppArmor entry and reboot the host now"; then
        as_root "one-time boot into the AppArmor entry" bootctl set-oneshot "$entry"
        as_root "reboot" systemctl reboot
    fi
    ;;
verify)
    expect "AppArmor is in the running LSM list" 'apparmor' cat /sys/kernel/security/lsm
    expect "the kernel line names AppArmor" 'lsm=[^ ]*apparmor' cat /proc/cmdline
    expect "AppArmor reports itself enabled" '^Y' cat /sys/module/apparmor/parameters/enabled
    check "srv-tz-01 starts" playbook "start srv-tz-01" -i inventory.ini playbooks/vm-start.yml \
        -e guest_spec=vm-specs/.generated/srv-tz-01.yml
    check "srv-tz-01 answers over SSH" ansible srv-tz-01 -i inventory.ini \
        -i "${XDG_RUNTIME_DIR}/srv-tz-01.ini" -m ping
    report "Start dev-01 and open Looking Glass (hyperlabctl open looking-glass dev-01), then answer."
    ask "Looking Glass shows dev-01" "Does Looking Glass show dev-01's desktop and take input?"
    screenshot "looking glass under AppArmor"
    if [[ -r /sys/kernel/security/apparmor/profiles ]]; then
        backup_root "loaded AppArmor profiles" cat /sys/kernel/security/apparmor/profiles
    fi
    ;;
*)
    report "usage: 10-apparmor-boot.sh prepare|verify"
    exit 2
    ;;
esac
acceptance_end
