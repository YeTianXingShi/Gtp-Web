#!/usr/bin/env bash
set -euo pipefail

# Minimal Linux bootstrap:
# - Installs Python3 + venv + pip (if missing)
# - Creates virtualenv
# - Installs Python dependencies
# - Starts app in background
#
# NOTE:
# - If config/env/ or config/users.json are missing, they will be auto-created
#   from config/env.example/ and config/users.example.json respectively.

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_DIR="${ENV_DIR:-${PROJECT_DIR}/config/env}"
USERS_FILE="${PROJECT_DIR}/config/users.json"
VENV_DIR="${PROJECT_DIR}/.venv"
PID_FILE="${PROJECT_DIR}/data/app.pid"
LOG_DIR="${PROJECT_DIR}/logs"
RUNTIME_LOG_FILE="${LOG_DIR}/runtime.log"
LOG_TO_STDOUT="${LOG_TO_STDOUT:-0}"

has_cmd() {
  command -v "$1" >/dev/null 2>&1
}

is_process_running() {
  local pid="$1"
  [[ -n "${pid}" ]] && kill -0 "${pid}" >/dev/null 2>&1
}

run_privileged() {
  if [[ "${EUID}" -eq 0 ]]; then
    "$@"
  elif has_cmd sudo; then
    sudo "$@"
  else
    echo "Error: need root or sudo to install system packages." >&2
    exit 1
  fi
}

install_python_deps() {
  if has_cmd apt-get; then
    run_privileged apt-get update
    run_privileged apt-get install -y python3 python3-venv python3-pip
    return
  fi
  if has_cmd dnf; then
    run_privileged dnf install -y python3 python3-pip
    return
  fi
  if has_cmd yum; then
    run_privileged yum install -y python3 python3-pip
    return
  fi
  if has_cmd pacman; then
    run_privileged pacman -Sy --noconfirm python python-pip
    return
  fi
  if has_cmd zypper; then
    run_privileged zypper --non-interactive install python3 python3-pip python3-virtualenv
    return
  fi
  if has_cmd apk; then
    run_privileged apk add --no-cache python3 py3-pip py3-virtualenv
    return
  fi
  echo "Error: unsupported package manager. Please install python3, python3-venv, pip manually." >&2
  exit 1
}

has_grouped_env() {
  [[ -d "${ENV_DIR}" ]] && find "${ENV_DIR}" -maxdepth 1 -type f -name '*.env' | grep -q .
}

read_env_value() {
  local key="$1"
  local line=""
  local current_line=""
  local env_path=""

  if has_grouped_env; then
    while IFS= read -r env_path; do
      current_line="$(grep -E "^${key}=" "${env_path}" | tail -n 1 || true)"
      if [[ -n "${current_line}" ]]; then
        line="${current_line}"
      fi
    done < <(find "${ENV_DIR}" -maxdepth 1 -type f -name '*.env' | sort)
  fi

  if [[ -z "${line}" ]]; then
    return 1
  fi

  line="${line#*=}"
  line="${line%\"}"
  line="${line#\"}"
  line="${line%\'}"
  line="${line#\'}"
  if [[ -z "${line}" ]]; then
    return 1
  fi

  printf '%s\n' "${line}"
}

read_env_port() {
  read_env_value PORT || echo "8000"
}

echo "[1/5] Checking Python..."
if ! has_cmd python3; then
  echo "python3 not found. Installing..."
  install_python_deps
fi

if ! python3 -m venv --help >/dev/null 2>&1; then
  echo "python3 venv module is unavailable. Installing python venv dependencies..."
  install_python_deps
fi

echo "[2/5] Checking required config files..."
EXAMPLE_ENV_DIR="${PROJECT_DIR}/config/env.example"
EXAMPLE_USERS_FILE="${PROJECT_DIR}/config/users.example.json"

if ! has_grouped_env; then
  if [[ -d "${EXAMPLE_ENV_DIR}" ]]; then
    echo "Config not found. Initializing from env.example..."
    cp -R "${EXAMPLE_ENV_DIR}" "${ENV_DIR}"
    echo "Created ${ENV_DIR}/ — please edit the .env files to set your API keys."
  else
    echo "Error: missing ${ENV_DIR}/*.env and no ${EXAMPLE_ENV_DIR}/ template found." >&2
    exit 1
  fi
fi
if [[ ! -f "${USERS_FILE}" ]]; then
  if [[ -f "${EXAMPLE_USERS_FILE}" ]]; then
    echo "Users config not found. Initializing from users.example.json..."
    cp "${EXAMPLE_USERS_FILE}" "${USERS_FILE}"
    echo "Created ${USERS_FILE} — please edit it to configure your users."
  else
    echo "Error: missing ${USERS_FILE} and no ${EXAMPLE_USERS_FILE} template found." >&2
    exit 1
  fi
fi

echo "[3/5] Creating virtual environment..."
if [[ ! -f "${VENV_DIR}/bin/activate" ]]; then
  if [[ -d "${VENV_DIR}" ]]; then
    echo "Detected incomplete virtualenv at ${VENV_DIR}, recreating..."
    rm -rf "${VENV_DIR}"
  fi
  python3 -m venv "${VENV_DIR}"
fi

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

echo "[4/5] Installing Python dependencies..."
python -m pip install --upgrade pip >/dev/null
pip install -r "${PROJECT_DIR}/requirements.txt"

echo "[5/5] Starting app in background..."
mkdir -p "${PROJECT_DIR}/data" "${LOG_DIR}"

if [[ -f "${PID_FILE}" ]]; then
  OLD_PID="$(cat "${PID_FILE}" 2>/dev/null || true)"
  if is_process_running "${OLD_PID}"; then
    echo "App is already running (PID: ${OLD_PID})."
    echo "URL: http://127.0.0.1:$(read_env_port)"
    echo "Logs dir: ${LOG_DIR}"
    echo "Category logs: app.log request.log auth.log conversation.log chat.log error.log"
    echo "Runtime output: ${RUNTIME_LOG_FILE}"
    echo "Stop: bash stop_linux.sh"
    exit 0
  fi
  echo "Removing stale PID file."
  rm -f "${PID_FILE}"
fi

cd "${PROJECT_DIR}"
nohup env \
  LOG_TO_STDOUT="${LOG_TO_STDOUT}" \
  "${VENV_DIR}/bin/python" app.py >"${RUNTIME_LOG_FILE}" 2>&1 < /dev/null &

APP_PID=$!
echo "${APP_PID}" > "${PID_FILE}"

sleep 1
if is_process_running "${APP_PID}"; then
  echo "Started."
  echo "PID: ${APP_PID}"
  echo "URL: http://127.0.0.1:$(read_env_port)"
  echo "Logs dir: ${LOG_DIR}"
  echo "Category logs: app.log request.log auth.log conversation.log chat.log error.log"
  echo "Runtime output: ${RUNTIME_LOG_FILE}"
  echo "Stop: bash stop_linux.sh"
else
  echo "Failed to start app. Showing recent logs:"
  tail -n 80 "${RUNTIME_LOG_FILE}" || true
  rm -f "${PID_FILE}"
  exit 1
fi
