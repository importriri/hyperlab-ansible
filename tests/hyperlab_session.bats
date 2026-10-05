#!/usr/bin/env bats

setup() {
  REPO_ROOT="$(cd "${BATS_TEST_DIRNAME}/.." && pwd)"
  TEST_ROOT="$(mktemp -d)"
  mkdir -p "${TEST_ROOT}/bin" "${TEST_ROOT}/runtime"

  cat >"${TEST_ROOT}/bin/hyperlab-manager" <<'MANAGER'
#!/usr/bin/env bash
set -u

pid_file=${HYPERLAB_TEST_PID_FILE:?}
starts=${HYPERLAB_TEST_STARTS:?}

printf '%s %s\n' "$$" "$*" >>"${starts}"
printf '%s\n' "$$" >"${pid_file}"

cleanup() {
    if [[ -r ${pid_file} ]] && [[ $(<"${pid_file}") == "$$" ]]; then
        rm -f -- "${pid_file}"
    fi
}

trap 'cleanup; exit 0' INT TERM HUP
trap cleanup EXIT

while :; do
    sleep 1
done
MANAGER

  cat >"${TEST_ROOT}/bin/gapplication" <<'GAPPLICATION'
#!/usr/bin/env bash
set -u

printf '%s\n' "$*" >>"${HYPERLAB_TEST_ACTIONS:?}"
sleep "${HYPERLAB_TEST_QUIT_DELAY:-0}"

pid_file=${HYPERLAB_TEST_PID_FILE:?}
if [[ -r ${pid_file} ]]; then
    pid=$(<"${pid_file}")
    kill -TERM "${pid}" 2>/dev/null || true
fi
GAPPLICATION

  chmod +x "${TEST_ROOT}/bin/hyperlab-manager" \
    "${TEST_ROOT}/bin/gapplication"

  export XDG_RUNTIME_DIR="${TEST_ROOT}/runtime"
  export PATH="${TEST_ROOT}/bin:${PATH}"
  export PRIVATESTACK_HYPERLAB_MANAGER="${TEST_ROOT}/bin/hyperlab-manager"
  export PRIVATESTACK_HYPERLAB_APP_ID=io.github.importriri.HyperlabControlCenter.Test
  export HYPERLAB_TEST_PID_FILE="${TEST_ROOT}/manager.pid"
  export HYPERLAB_TEST_STARTS="${TEST_ROOT}/starts"
  export HYPERLAB_TEST_ACTIONS="${TEST_ROOT}/actions"
  export HYPERLAB_TEST_QUIT_DELAY=0

  LAUNCHER="${REPO_ROOT}/roles/host_desktop_sway/files/privatestack-hyperlab-session.sh"
  MANAGED_PIDS_FILE="${TEST_ROOT}/managed-pids"
  : >"${MANAGED_PIDS_FILE}"
}

teardown() {
  local pid

  if [[ -r ${HYPERLAB_TEST_PID_FILE} ]]; then
    pid=$(<"${HYPERLAB_TEST_PID_FILE}")
    kill -TERM "${pid}" 2>/dev/null || true
  fi

  while IFS= read -r pid; do
    kill -TERM "${pid}" 2>/dev/null || true
  done <"${MANAGED_PIDS_FILE}"
  while IFS= read -r pid; do
    wait "${pid}" 2>/dev/null || true
  done <"${MANAGED_PIDS_FILE}"

  rm -rf -- "${TEST_ROOT}"
}

# One read of the pid file. The old manager removes it on exit and the new
# one truncates it before writing, so a failed or empty read is "no pid", not
# a different pid (problems/session-test-pid-file-race.md).
read_manager_pid() {
  local pid

  { pid=$(<"${HYPERLAB_TEST_PID_FILE}"); } 2>/dev/null || return 1
  [[ -n ${pid} ]] || return 1
  printf '%s\n' "${pid}"
}

wait_for_pid_change() {
  local old_pid=$1 attempts=${2:-200} pid

  for ((i = 0; i < attempts; i++)); do
    if pid=$(read_manager_pid) && [[ ${pid} != "${old_pid}" ]]; then
      return 0
    fi
    sleep 0.02
  done

  return 1
}

start_old_manager() {
  "${PRIVATESTACK_HYPERLAB_MANAGER}" --warm &
  OLD_MANAGER_PID=$!
  printf '%s\n' "${OLD_MANAGER_PID}" >>"${MANAGED_PIDS_FILE}"

  for _ in {1..100}; do
    [[ -r ${HYPERLAB_TEST_PID_FILE} ]] && break
    sleep 0.02
  done

  [[ -r ${HYPERLAB_TEST_PID_FILE} ]]
  [[ $(<"${HYPERLAB_TEST_PID_FILE}") == "${OLD_MANAGER_PID}" ]]
}

@test "a missing, unreadable or empty pid file is not a new manager" {
  rm -f -- "${HYPERLAB_TEST_PID_FILE}"
  run wait_for_pid_change 12345 3
  [[ ${status} -eq 1 ]]

  # -r succeeds and the read fails, as when the old manager removes the
  # file between the two.
  mkdir -- "${HYPERLAB_TEST_PID_FILE}"
  run wait_for_pid_change 12345 3
  rmdir -- "${HYPERLAB_TEST_PID_FILE}"
  [[ ${status} -eq 1 ]]

  : >"${HYPERLAB_TEST_PID_FILE}"
  run wait_for_pid_change 12345 3
  rm -f -- "${HYPERLAB_TEST_PID_FILE}"
  [[ ${status} -eq 1 ]]

  printf '67890\n' >"${HYPERLAB_TEST_PID_FILE}"
  run wait_for_pid_change 12345 3
  rm -f -- "${HYPERLAB_TEST_PID_FILE}"
  [[ ${status} -eq 0 ]]
}

@test "a reload replaces the resident manager before warming the new source" {
  local current starts actions

  start_old_manager

  "${LAUNCHER}" &
  current=$!
  printf '%s\n' "${current}" >>"${MANAGED_PIDS_FILE}"

  wait_for_pid_change "${OLD_MANAGER_PID}"
  wait "${OLD_MANAGER_PID}"

  [[ $(<"${HYPERLAB_TEST_PID_FILE}") == "${current}" ]]
  kill -0 "${current}"

  starts=$(wc -l <"${HYPERLAB_TEST_STARTS}")
  actions=$(wc -l <"${HYPERLAB_TEST_ACTIONS}")
  [[ ${starts} -eq 2 ]]
  [[ ${actions} -eq 1 ]]
  grep -Fxq 'action io.github.importriri.HyperlabControlCenter.Test quit' \
    "${HYPERLAB_TEST_ACTIONS}"
}

@test "concurrent reload helpers perform one serialized replacement" {
  local current pid starts actions
  local -a reload_pids=()

  start_old_manager
  export HYPERLAB_TEST_QUIT_DELAY=0.2

  for _ in 1 2 3 4; do
    "${LAUNCHER}" &
    reload_pids+=("$!")
    printf '%s\n' "${reload_pids[-1]}" >>"${MANAGED_PIDS_FILE}"
  done

  wait_for_pid_change "${OLD_MANAGER_PID}"
  current=$(<"${HYPERLAB_TEST_PID_FILE}")
  kill -0 "${current}"

  for pid in "${reload_pids[@]}"; do
    if [[ ${pid} != "${current}" ]]; then
      wait "${pid}"
      run kill -0 "${pid}"
      [[ ${status} -ne 0 ]]
    fi
  done

  starts=$(wc -l <"${HYPERLAB_TEST_STARTS}")
  actions=$(wc -l <"${HYPERLAB_TEST_ACTIONS}")
  [[ ${starts} -eq 2 ]]
  [[ ${actions} -eq 1 ]]
}
