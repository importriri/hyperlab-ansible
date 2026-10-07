#!/usr/bin/env bash
# Group 11: the host USB policy (ADR 0038). Turning the block on is a
# destructive step: it stops at a confirmation. The internal keyboard (i8042)
# and touchpad (I2C) are not USB and must keep working.
export ACCEPTANCE_GROUP=11-usbguard
# shellcheck source=tools/acceptance/lib.sh disable=SC1091
source "$(dirname "$0")/lib.sh"
acceptance_start
become_once

USB_SYSFS=${HYPERLAB_USB_SYSFS:-/sys/bus/usb/devices}

usb_list() {
    local d
    for d in "$USB_SYSFS"/*; do
        [[ -e $d/idVendor ]] || continue
        printf '%s %s:%s authorized=%s\n' "${d##*/}" "$(<"$d/idVendor")" "$(<"$d/idProduct")" "$(<"$d/authorized")"
    done
}

# attached_all_allowed: as many "allow" rows as USB devices the kernel
# reports, and no blocked one, before anything new is plugged in.
attached_all_allowed() {
    local listing allowed blocked attached
    listing=$(as_root "list USB devices" usbguard list-devices) || return 1
    allowed=$(grep -cE '^[0-9]+: allow' <<<"$listing")
    blocked=$(grep -cE '^[0-9]+: (block|reject)' <<<"$listing")
    attached=$(usb_list | wc -l)
    printf '%s\n' "$listing"
    printf 'allowed=%s blocked=%s attached=%s\n' "$allowed" "$blocked" "$attached"
    (( attached > 0 && allowed == attached && blocked == 0 ))
}

backup "USB devices before" usb_list
rollback "sudo systemctl disable --now usbguard   (stops the block)"
rollback "echo 1 | sudo tee /sys/bus/usb/devices/<port>/authorized   (one blocked device, now)"
# Fail closed: the block is offered only after a clean dry run.
if check "usbguard check mode" playbook "usbguard check" -i inventory.ini playbooks/host-usbguard.yml --check --diff; then
    report "Plug any USB mouse or keyboard you use BEFORE the next step, so it enters the policy."
    if confirm block "turn on USBGuard: every USB device not attached now stays blocked"; then
        check "usbguard applied" playbook "usbguard apply" -i inventory.ini playbooks/host-usbguard.yml
        check "every attached device allowed, none blocked" attached_all_allowed
        ask "internal keyboard" "Type a few letters on the internal keyboard: do they appear?"
        ask "internal touchpad" "Move the pointer with the touchpad: does it move?"
        ask "a new stick is blocked" "Plug a USB stick: is it NOT mounted? (the shell's USB devices view lists it blocked)"
        screenshot "usb devices view"
        backup "USB devices after" usb_list
    fi
else
    report "BLOCK NOT OFFERED: the check mode failed (the failed task is above); nothing was changed."
fi
acceptance_end
