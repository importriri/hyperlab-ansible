#!/usr/bin/env bats

setup() {
  REPO_ROOT="$(cd "${BATS_TEST_DIRNAME}/.." && pwd)"
  TEST_ROOT="$(mktemp -d)"
  mkdir -p "${TEST_ROOT}/bin" "${TEST_ROOT}/runtime" \
    "${TEST_ROOT}/config/waybar" "${TEST_ROOT}/state" "${TEST_ROOT}/home"

  printf '%s\n' \
    '#!/usr/bin/env bash' \
    'printf "swaymsg %s\n" "$*" >>"${WAYBAR_TEST_EVENTS:?}"' \
    >"${TEST_ROOT}/bin/swaymsg"

  printf '%s\n' \
    '#!/usr/bin/env bash' \
    'printf "waybar %s\n" "$$" >>"${WAYBAR_TEST_STARTS:?}"' \
    "trap 'exit 0' INT TERM HUP" \
    'while :; do sleep 1; done' \
    >"${TEST_ROOT}/bin/waybar"

  printf '%s\n' \
    '#!/usr/bin/env bash' \
    'exit 0' \
    >"${TEST_ROOT}/bin/pkill"

  printf '%s\n' \
    '#!/usr/bin/env bash' \
    ': >"${WAYBAR_LEGACY_READY:?}"' \
    "trap 'exit 0' INT TERM HUP" \
    'while :; do sleep 1; done' \
    >"${TEST_ROOT}/bin/privatestack-waybar-legacy"

  chmod +x "${TEST_ROOT}/bin/swaymsg" "${TEST_ROOT}/bin/waybar" \
    "${TEST_ROOT}/bin/pkill" "${TEST_ROOT}/bin/privatestack-waybar-legacy"

  export XDG_RUNTIME_DIR="${TEST_ROOT}/runtime"
  export XDG_CONFIG_HOME="${TEST_ROOT}/config"
  export XDG_STATE_HOME="${TEST_ROOT}/state"
  export HOME="${TEST_ROOT}/home"
  export PATH="${TEST_ROOT}/bin:${PATH}"
  export WAYBAR_TEST_EVENTS="${TEST_ROOT}/events"
  export WAYBAR_TEST_STARTS="${TEST_ROOT}/starts"
  export WAYBAR_LEGACY_READY="${TEST_ROOT}/legacy-ready"
  LAUNCHER="${REPO_ROOT}/roles/host_desktop_sway/files/privatestack-waybar.sh"
  supervisor_pids=()
}

teardown() {
  local pid
  for pid in "${supervisor_pids[@]}"; do
    kill -TERM "${pid}" 2>/dev/null || true
  done
  for pid in "${supervisor_pids[@]}"; do
    wait "${pid}" 2>/dev/null || true
  done
  rm -rf -- "${TEST_ROOT}"
}

@test "concurrent reload launchers keep one Waybar supervisor" {
  local owner starts

  for _ in 1 2 3 4; do
    "${LAUNCHER}" &
    supervisor_pids+=("$!")
  done

  for _ in {1..100}; do
    [[ -s "${WAYBAR_TEST_STARTS}" ]] && \
      [[ -s "${XDG_RUNTIME_DIR}/privatestack-waybar-supervisor.pid" ]] && break
    sleep 0.02
  done

  [[ -s "${WAYBAR_TEST_STARTS}" ]]
  [[ -s "${XDG_RUNTIME_DIR}/privatestack-waybar-supervisor.pid" ]]

  owner="$(<"${XDG_RUNTIME_DIR}/privatestack-waybar-supervisor.pid")"
  kill -0 "${owner}"

  sleep 0.2
  starts="$(wc -l <"${WAYBAR_TEST_STARTS}")"
  [[ ${starts} -eq 1 ]]

  for pid in "${supervisor_pids[@]}"; do
    if [[ ${pid} != "${owner}" ]]; then
      ! kill -0 "${pid}" 2>/dev/null
    fi
  done
}

@test "the flock release retires one legacy pid-file supervisor" {
  local current legacy owner starts

  "${TEST_ROOT}/bin/privatestack-waybar-legacy" &
  legacy=$!
  supervisor_pids+=("${legacy}")
  for _ in {1..100}; do
    [[ -e "${WAYBAR_LEGACY_READY}" ]] && break
    sleep 0.02
  done
  [[ -e "${WAYBAR_LEGACY_READY}" ]]
  printf '%s\n' "${legacy}" \
    >"${XDG_RUNTIME_DIR}/privatestack-waybar-supervisor.pid"

  "${LAUNCHER}" &
  current=$!
  supervisor_pids+=("${current}")

  for _ in {1..100}; do
    [[ -s "${WAYBAR_TEST_STARTS}" ]] && break
    sleep 0.02
  done

  wait "${legacy}"
  [[ -s "${WAYBAR_TEST_STARTS}" ]]
  owner="$(<"${XDG_RUNTIME_DIR}/privatestack-waybar-supervisor.pid")"
  [[ ${owner} == "${current}" ]]
  kill -0 "${current}"
  starts="$(wc -l <"${WAYBAR_TEST_STARTS}")"
  [[ ${starts} -eq 1 ]]
}
