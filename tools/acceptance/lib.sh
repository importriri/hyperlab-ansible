# shellcheck shell=bash
# Shared helpers for the Nitro acceptance scripts (tools/acceptance/*.sh).
#
# Each script is one group of the operator's test plan. It runs the group's
# checks, keeps the evidence under ~/hyperlab-evidence/<date>/<group>-<time>/
# and prints PASS or FAIL per check. tests/acceptance_scripts_contract.py
# holds every script to these rules:
#
#   * root only through as_root or playbook, each announced in the report
#     before it runs; never a bare sudo;
#   * the become password is read once per group, checked, and handed to
#     each command on a fresh 0600 FIFO: never argv, the environment, a file
#     or a log;
#   * every captured output passes redact before it is written;
#   * a risky step makes its backup first and writes the rollback command
#     into the report;
#   * a destructive step stops at confirm, one at a time, and is skipped
#     unless the operator types the step's own word.

set -uo pipefail

: "${ACCEPTANCE_GROUP:?set ACCEPTANCE_GROUP before sourcing lib.sh}"
ACCEPTANCE_REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
EVIDENCE_ROOT=${HYPERLAB_EVIDENCE_ROOT:-$HOME/hyperlab-evidence}
EVIDENCE="$EVIDENCE_ROOT/$(date +%F)/$ACCEPTANCE_GROUP-$(date +%H%M%S)"
REPORT="$EVIDENCE/report.txt"
PASSES=0
FAILS=0
SKIPS=0
_become=""
_nopasswd=0
_runtime=""

acceptance_start() {
    umask 077
    mkdir -p "$EVIDENCE"
    _runtime=$(mktemp -d "${XDG_RUNTIME_DIR:-/tmp}/hyperlab-acceptance.XXXXXX")
    trap acceptance_cleanup EXIT
    trap 'acceptance_cleanup; exit 130' INT TERM
    report "group $ACCEPTANCE_GROUP on $(hostname) at $(date --iso-8601=seconds)"
    report "repository $(git -C "$ACCEPTANCE_REPO" rev-parse --short HEAD 2>/dev/null || echo unknown)"
    report "evidence $EVIDENCE"
}

acceptance_cleanup() {
    _become=""
    if [[ -n $_runtime && -d $_runtime ]]; then
        rm -rf -- "$_runtime"
    fi
}

# The report goes to stderr as well as the file, so a command's own output
# (a backup, for one) is never mixed with it.
report() {
    printf '%s\n' "$*" | tee -a "$REPORT" >&2
}

redact() {
    # shellcheck disable=SC2016  # the $ in the hash pattern is literal
    sed -E \
        -e '/-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----/,/-----END [A-Z0-9 ]*PRIVATE KEY-----/c\[private key redacted]' \
        -e 's/((password|passwd|passphrase|secret|token|api[_-]?key)["]?[[:space:]]*[:=][[:space:]]*["]?)[^[:space:]"]+/\1[redacted]/gI' \
        -e 's/\$(1|2[abxy]|5|6|7|y|gy)\$[^[:space:]:"]+/[password hash redacted]/g' \
        -e 's/(BECOME|SUDO) password:.*/\1 password: [redacted]/I'
}

slug() {
    printf '%s' "$1" | tr -c 'A-Za-z0-9' '-' | tr -s '-' | cut -c1-60
}

# check NAME COMMAND...: run it, keep its redacted output, PASS on exit 0.
check() {
    local name=$1 log
    shift
    log="$EVIDENCE/$(slug "$name").log"
    if "$@" 2>&1 | redact >"$log"; then
        PASSES=$((PASSES + 1))
        report "PASS  $name"
    else
        FAILS=$((FAILS + 1))
        report "FAIL  $name  (evidence: $log)"
    fi
}

# expect NAME REGEX COMMAND...: PASS when the output matches REGEX.
expect() {
    local name=$1 pattern=$2 log
    shift 2
    log="$EVIDENCE/$(slug "$name").log"
    "$@" 2>&1 | redact >"$log"
    if grep -Eq -- "$pattern" "$log"; then
        PASSES=$((PASSES + 1))
        report "PASS  $name"
    else
        FAILS=$((FAILS + 1))
        report "FAIL  $name  (expected /$pattern/; evidence: $log)"
    fi
}

_become_mode() {
    # A sudo time window (the operator's own sudoers drop-in) needs no
    # password; anything else gets the password once.
    if sudo -n -k true 2>/dev/null; then
        _nopasswd=1
        return 0
    fi
    _nopasswd=0
    return 1
}

# Call once at the top of a script, before any check: checks run in
# subshells, which inherit the password but cannot set it for the next one.
become_once() {
    if _become_mode; then
        report "root: passwordless sudo is open; no password asked"
        return 0
    fi
    [[ -n $_become ]] && return 0
    local answer
    IFS= read -rsp "[$ACCEPTANCE_GROUP] sudo password for $(id -un) (asked once for this group): " answer </dev/tty
    printf '\n' >&2
    _become=$answer
    answer=""
    if ! printf '%s\n' "$_become" | sudo -S -k -p '' true 2>/dev/null; then
        _become=""
        report "FAIL  the sudo password was refused; nothing that needs root ran"
        exit 1
    fi
    report "root: password checked once for this group (kept in memory only)"
}

# as_root WHY COMMAND...: the one way a script runs a command as root.
as_root() {
    local why=$1
    shift
    become_once
    report "ROOT  $why: $*"
    if (( _nopasswd )); then
        sudo -n -- "$@" </dev/null
    else
        # -k: always read the password, so it is never left on the
        # command's stdin by a cached credential.
        printf '%s\n' "$_become" | sudo -S -k -p '' -- "$@"
    fi
}

# playbook WHY ARGS...: ansible-playbook with become, password on a FIFO.
playbook() {
    local why=$1 log fifo writer rc
    shift
    become_once
    log="$EVIDENCE/$(slug "$why").log"
    report "PLAY  $why: ansible-playbook $*"
    if (( _nopasswd )); then
        (cd "$ACCEPTANCE_REPO" && ansible-playbook "$@") 2>&1 | redact >"$log"
        rc=${PIPESTATUS[0]}
    else
        fifo="$_runtime/become.$RANDOM$RANDOM"
        mkfifo -m 600 "$fifo"
        (printf '%s\n' "$_become" >"$fifo") &
        writer=$!
        (cd "$ACCEPTANCE_REPO" && ansible-playbook --become-password-file "$fifo" "$@") 2>&1 | redact >"$log"
        rc=${PIPESTATUS[0]}
        kill "$writer" 2>/dev/null
        wait "$writer" 2>/dev/null
        rm -f -- "$fifo"
    fi
    tail -n 3 "$log" | tee -a "$REPORT" >&2
    return "$rc"
}

# backup NAME COMMAND...: the command's output, kept before a risky step.
backup() {
    local name=$1 file
    shift
    file="$EVIDENCE/backup-$(slug "$name")"
    if "$@" >"$file" 2>"$file.err"; then
        report "BACKUP $name -> $file"
    else
        report "FAIL  backup $name failed; the risky step after it does not run"
        exit 1
    fi
}

backup_root() {
    local name=$1 file
    shift
    file="$EVIDENCE/backup-$(slug "$name")"
    if as_root "backup $name" "$@" >"$file" 2>"$file.err"; then
        report "BACKUP $name -> $file"
    else
        report "FAIL  backup $name failed; the risky step after it does not run"
        exit 1
    fi
}

rollback() {
    report "ROLLBACK if needed: $*"
}

# confirm WORD WHAT: stop before a destructive step; 0 only on WORD.
confirm() {
    local word=$1 what=$2 answer
    report "STOP  $what"
    IFS= read -rp "Type '$word' to do it now, anything else skips it: " answer </dev/tty
    if [[ $answer == "$word" ]]; then
        report "      confirmed by the operator"
        return 0
    fi
    SKIPS=$((SKIPS + 1))
    report "      SKIPPED (not confirmed)"
    return 1
}

# screenshot NAME: the operator's screen now, for review after the run.
screenshot() {
    local file
    file="$EVIDENCE/shot-$(slug "$1").png"
    if grim "$file" 2>/dev/null; then
        report "SHOT  $1 -> $file"
    else
        report "SHOT  $1 failed (grim needs the Wayland session)"
    fi
}

# ask NAME QUESTION: the operator's own observation, recorded as PASS/FAIL.
ask() {
    local name=$1 question=$2 answer
    IFS= read -rp "$question [y/n] " answer </dev/tty
    if [[ $answer == y ]]; then
        PASSES=$((PASSES + 1))
        report "PASS  $name (operator)"
    else
        FAILS=$((FAILS + 1))
        report "FAIL  $name (operator)"
    fi
}

acceptance_end() {
    report "group $ACCEPTANCE_GROUP: $PASSES passed, $FAILS failed, $SKIPS skipped"
    (( FAILS == 0 ))
}
