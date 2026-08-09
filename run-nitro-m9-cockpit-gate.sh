#!/usr/bin/env bash
# Hardware boundary for the frozen M9 + cockpit candidate on the Nitro host.
set -Eeuo pipefail

STORE=/var/lib/libvirt/images/hyperlab
SPEC=vm-specs/debian-dev.yml
NETWORKS=(clean dirty dev lab services)
STAMP="$(date +%Y%m%d-%H%M%S)"
EVIDENCE_ROOT="${XDG_STATE_HOME:-${HOME}/.local/state}/hyperlab-gates"
LOG_DIR="${EVIDENCE_ROOT}/m9-cockpit-nitro-${STAMP}"

fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
step() { printf '\n== %s\n' "$*"; }

[[ -d .git && -x ./verify.sh ]] \
  || fail "run from the hyperlab-ansible repository root"
[[ -z "$(git status --porcelain)" ]] \
  || fail "the candidate working tree is not clean"
[[ -x tools/guest_store_guard.py ]] \
  || fail "guest store hardening is missing"
[[ -x tools/hyperlabctl/bin/hyperlabctl ]] \
  || fail "the cockpit CLI is missing"

candidate_head="$(git rev-parse HEAD)"
mkdir -p "${LOG_DIR}"
printf '%s\n' "${candidate_head}" >"${LOG_DIR}/candidate-head.txt"
git status --short --branch >"${LOG_DIR}/git-status.txt"

step "Host-independent integrated contracts"
PYTHONDONTWRITEBYTECODE=1 python tests/guest_store_guard_contract.py \
  | tee "${LOG_DIR}/guest-store-guard.log"
PYTHONDONTWRITEBYTECODE=1 python tests/guest_order_contract.py \
  | tee "${LOG_DIR}/guest-order.log"
PYTHONDONTWRITEBYTECODE=1 python tests/guest_contract.py \
  | tee "${LOG_DIR}/guest-contract.log"
PYTHONDONTWRITEBYTECODE=1 python tests/hyperlabctl_contract.py \
  | tee "${LOG_DIR}/cockpit-contract.log"
PYTHONDONTWRITEBYTECODE=1 python tests/m3_cockpit_contract.py \
  | tee "${LOG_DIR}/managed-cockpit-contract.log"
PYTHONDONTWRITEBYTECODE=1 python tests/rofi_theme_contract.py \
  | tee "${LOG_DIR}/rofi-theme-contract.log"

step "Rofi parser checks on the installed Nitro version"
rofi -config roles/host_desktop_sway/files/rofi-config.rasi -dump-config \
  >"${LOG_DIR}/rofi-config.dump"
rofi -no-config -theme roles/host_desktop_sway/files/rofi-launcher.rasi -dump-theme \
  >"${LOG_DIR}/rofi-launcher.dump"
rofi -no-config -theme roles/host_desktop_sway/files/rofi-hyperlab.rasi -dump-theme \
  >"${LOG_DIR}/rofi-hyperlab.dump"
git diff --check | tee "${LOG_DIR}/diff-check.log"

step "Read the become password once for all automated host gates"
runtime_dir="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
[[ -d "${runtime_dir}" && -O "${runtime_dir}" ]] \
  || fail "a private user runtime directory is required: ${runtime_dir}"
BECOME_PASSWORD_FILE="$(mktemp "${runtime_dir}/privatestack-become.XXXXXX")"
chmod 0600 "${BECOME_PASSWORD_FILE}"
cleanup_become_password() {
  rm -f -- "${BECOME_PASSWORD_FILE}"
}
trap cleanup_become_password EXIT

printf 'BECOME password: ' >&2
IFS= read -r -s become_password
printf '\n' >&2
[[ -n "${become_password}" ]] || fail "the become password cannot be empty"
printf '%s\n' "${become_password}" >"${BECOME_PASSWORD_FILE}"
unset become_password

feed_become_password() {
  awk 'NR == 1 { print; exit }' "${BECOME_PASSWORD_FILE}"
}

feed_become_password | sudo -S -k -p '' -v \
  || fail "sudo rejected the supplied become password"
sudo -k

run_ansible() {
  ansible-playbook --become-password-file "${BECOME_PASSWORD_FILE}" "$@"
}

run_sudo() {
  feed_become_password | sudo -S -k -p '' "$@"
}

step "Complete repository verification battery"
PRIVATESTACK_BECOME_PASSWORD_FILE="${BECOME_PASSWORD_FILE}" \
  ./verify.sh | tee "${LOG_DIR}/verify.log"

step "Hardware preflight"
run_ansible -i inventory.ini playbooks/preflight.yml --check --diff \
  | tee "${LOG_DIR}/preflight-check.log"
run_ansible -i inventory.ini playbooks/preflight.yml --diff \
  | tee "${LOG_DIR}/preflight-apply.log"

step "Network domains dry run"
run_ansible -i inventory.ini playbooks/network-domains.yml --check --diff \
  | tee "${LOG_DIR}/network-check.log"

step "Network domains real convergence"
run_ansible -i inventory.ini playbooks/network-domains.yml --diff \
  | tee "${LOG_DIR}/network-apply.log"

step "Network domains changed=0 proof"
run_ansible -i inventory.ini playbooks/network-domains.yml --diff \
  | tee "${LOG_DIR}/network-idempotent.log"
grep -Eq 'changed=0[[:space:]].*failed=0' "${LOG_DIR}/network-idempotent.log" \
  || fail "second network_domains apply was not changed=0/failed=0"

step "Verify all five persistent active autostart networks"
for network in "${NETWORKS[@]}"; do
  run_sudo virsh net-info "${network}" | tee "${LOG_DIR}/net-info-${network}.log"
  grep -Eq '^Active:[[:space:]]+yes$' "${LOG_DIR}/net-info-${network}.log" \
    || fail "${network} is not active"
  grep -Eq '^Persistent:[[:space:]]+yes$' "${LOG_DIR}/net-info-${network}.log" \
    || fail "${network} is not persistent"
  grep -Eq '^Autostart:[[:space:]]+yes$' "${LOG_DIR}/net-info-${network}.log" \
    || fail "${network} does not autostart"
done
[[ "$(run_sudo cat /etc/privatestack/bricks/network_domains)" == network_domains ]] \
  || fail "network_domains brick stamp is missing or invalid"

step "Desktop cockpit dry run"
run_ansible -i inventory.ini playbooks/host-desktop-sway.yml --check --diff \
  -e "host_desktop_sway_hyperlab_checkout=${PWD}" \
  | tee "${LOG_DIR}/desktop-check.log"

step "Desktop cockpit real convergence"
run_ansible -i inventory.ini playbooks/host-desktop-sway.yml --diff \
  -e "host_desktop_sway_hyperlab_checkout=${PWD}" \
  | tee "${LOG_DIR}/desktop-apply.log"

step "Desktop cockpit changed=0 proof"
run_ansible -i inventory.ini playbooks/host-desktop-sway.yml --diff \
  -e "host_desktop_sway_hyperlab_checkout=${PWD}" \
  | tee "${LOG_DIR}/desktop-idempotent.log"
grep -Eq 'changed=0[[:space:]].*failed=0' "${LOG_DIR}/desktop-idempotent.log" \
  || fail "second desktop apply was not changed=0/failed=0"

[[ "$(cat /etc/hyperlabctl/checkout)" == "${PWD}" ]] \
  || fail "/etc/hyperlabctl/checkout does not point at this checkout"
[[ -s /usr/share/bash-completion/completions/hyperlabctl ]] \
  || fail "hyperlabctl completion was not installed"

step "Cockpit CLI and managed action registry"
set +e
hyperlabctl status --json >"${LOG_DIR}/status.json" \
  2>"${LOG_DIR}/status.stderr"
status_rc=$?
set -e
[[ ${status_rc} -eq 0 || ${status_rc} -eq 2 ]] \
  || fail "hyperlabctl status returned unexpected exit ${status_rc}"
python -m json.tool "${LOG_DIR}/status.json" >/dev/null
hyperlabctl actions --json >"${LOG_DIR}/actions.json"
python - "${LOG_DIR}/actions.json" <<'PY'
import json
import sys

expected = {
    "vm.create",
    "vm.destroy",
    "vm.validate",
    "vm.managed-start",
    "vm.managed-shutdown",
    "vm.force-stop",
    "vm.reset",
}
actions = {
    item["id"]: item
    for item in json.load(open(sys.argv[1], encoding="utf-8"))
}
missing = sorted(expected - set(actions))
if missing:
    raise SystemExit("missing managed actions: " + ", ".join(missing))
for action_id in expected:
    action = actions[action_id]
    if not action["available"] or not action["privileged"]:
        raise SystemExit(f"unsafe managed action metadata: {action_id}")
print("managed action registry: OK")
PY

step "Event stream heartbeat and user journal access"
timeout 10 hyperlabctl watch --heartbeat 1 --max-cycles 2 \
  >"${LOG_DIR}/watch.jsonl"
python - "${LOG_DIR}/watch.jsonl" <<'PY'
import json
import sys

lines = [
    line
    for line in open(sys.argv[1], encoding="utf-8")
    if line.strip()
]
if len(lines) != 2:
    raise SystemExit(f"expected two watch payloads, got {len(lines)}")
for line in lines:
    json.loads(line)
print("watch stream: OK")
PY
journalctl -u virtqemud -n 1 --no-pager >"${LOG_DIR}/journal-user.log" \
  || fail "virtqemud journal is not readable by the admin user"

snapshot_store() {
  run_sudo find "${STORE}" -xdev \
    -printf '%P\0%y\0%m\0%u\0%g\0%s\0%T@\0' \
    | sort -z | sha256sum | awk '{print $1}'
}

snapshot_domains() {
  run_sudo virsh list --all --uuid \
    | sed '/^$/d' | sort | sha256sum | awk '{print $1}'
}

step "Snapshot before the intentional unsealed-image refusal"
store_before="$(snapshot_store)"
domains_before="$(snapshot_domains)"
printf '%s\n' "${store_before}" >"${LOG_DIR}/store-before.sha256"
printf '%s\n' "${domains_before}" >"${LOG_DIR}/domains-before.sha256"

step "Resolve the expected managed-create refusal"
if run_sudo test -f /etc/privatestack/bricks/image_factory; then
  refusal_reason=unsealed-image
  refusal_pattern='image debian is not sealed'
else
  refusal_reason=missing-image-factory-prerequisite
  refusal_pattern='guest needs image_factory on this host first'
fi
printf '%s\n' "${refusal_reason}" >"${LOG_DIR}/vm-create-expected-refusal.txt"

step "Managed create check must refuse before host writes"
set +e
run_ansible -i inventory.ini playbooks/vm-create.yml --check --diff \
  -e "guest_spec=${SPEC}" >"${LOG_DIR}/vm-create-refusal.log" 2>&1
create_rc=$?
set -e
cat "${LOG_DIR}/vm-create-refusal.log"
[[ ${create_rc} -ne 0 ]] \
  || fail "vm-create unexpectedly succeeded with a public not-built image"
grep -Fq "${refusal_pattern}" "${LOG_DIR}/vm-create-refusal.log" \
  || fail "vm-create failed for an unexpected reason: expected ${refusal_reason}"

step "Prove the refusal left store and domain registry unchanged"
store_after="$(snapshot_store)"
domains_after="$(snapshot_domains)"
printf '%s\n' "${store_after}" >"${LOG_DIR}/store-after.sha256"
printf '%s\n' "${domains_after}" >"${LOG_DIR}/domains-after.sha256"
[[ "${store_before}" == "${store_after}" ]] \
  || fail "store changed during refusal"
[[ "${domains_before}" == "${domains_after}" ]] \
  || fail "libvirt domain registry changed during refusal"

printf '\nAUTOMATED NITRO M9 + COCKPIT GATE: GREEN\n'
printf 'Candidate: %s\nEvidence: %s\n' "${candidate_head}" "${LOG_DIR}"
printf '%s\n' 'Manual desktop boundary remains:'
printf '%s\n' '  1. reload Sway; verify Mod+F1 palette, Mod+F2 panel and Mod+F3 doctor'
printf '%s\n' '  2. hover the Waybar HyperLab group and verify the drawer opens'
printf '%s\n' '  3. start/stop an unmanaged disposable test domain and verify immediate refresh'
printf '%s\n' '  4. select a managed action and verify it only prepares the privileged playbook'
printf '%s\n' '  5. verify Catppuccin colours and panel geometry in Foot'
printf '%s\n' 'After this focused gate, continue the ordered M9 campaign in docs/release-evidence.md.'
