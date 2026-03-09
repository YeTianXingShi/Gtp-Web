#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="${PROJECT_DIR}/data/app.pid"

is_process_running() {
  local pid="$1"
  [[ -n "${pid}" ]] && kill -0 "${pid}" >/dev/null 2>&1
}

if [[ ! -f "${PID_FILE}" ]]; then
  echo "No PID file found (${PID_FILE}). App may already be stopped."
  exit 0
fi

APP_PID="$(cat "${PID_FILE}" 2>/dev/null || true)"
if [[ -z "${APP_PID}" ]]; then
  echo "PID file is empty. Removing stale PID file."
  rm -f "${PID_FILE}"
  exit 0
fi

if ! is_process_running "${APP_PID}"; then
  echo "Process ${APP_PID} is not running. Removing stale PID file."
  rm -f "${PID_FILE}"
  exit 0
fi

echo "Stopping app (PID: ${APP_PID})..."
kill "${APP_PID}" || true

for _ in $(seq 1 20); do
  if ! is_process_running "${APP_PID}"; then
    rm -f "${PID_FILE}"
    echo "Stopped gracefully."
    exit 0
  fi
  sleep 0.3
done

echo "Graceful stop timed out. Force killing ${APP_PID}..."
kill -9 "${APP_PID}" || true
rm -f "${PID_FILE}"
echo "Stopped (force)."
