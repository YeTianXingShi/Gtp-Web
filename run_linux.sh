#!/usr/bin/env bash
set -euo pipefail

# One-click bootstrap for Linux:
# - Installs Python3 + venv + pip (via common package managers)
# - Creates virtualenv
# - Installs Python dependencies
# - Initializes .env and users config (if missing)
# - Starts Flask app

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${PROJECT_DIR}/.env"
ENV_EXAMPLE_FILE="${PROJECT_DIR}/.env.example"
USERS_FILE="${PROJECT_DIR}/config/users.json"
USERS_EXAMPLE_FILE="${PROJECT_DIR}/config/users.example.json"
VENV_DIR="${PROJECT_DIR}/.venv"
PID_FILE="${PROJECT_DIR}/data/app.pid"
LOG_DIR="${PROJECT_DIR}/logs"
LOG_FILE="${LOG_DIR}/app.log"
RUNTIME_LOG_FILE="${LOG_DIR}/runtime.log"

APP_SECRET_KEY="${APP_SECRET_KEY:-}"
AI_BASE_URL="${AI_BASE_URL:-}"
AI_API_KEY="${AI_API_KEY:-}"
AI_MODELS="${AI_MODELS:-}"
PORT="${PORT:-}"
LOG_TO_STDOUT="${LOG_TO_STDOUT:-0}"
DEFAULT_AI_MODELS="gpt-4o-mini,gpt-4.1-mini"
DEFAULT_PORT="8000"

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

read_env_value() {
  local key="$1"
  local line=""
  if [[ -f "${ENV_FILE}" ]]; then
    line="$(grep -E "^${key}=" "${ENV_FILE}" | tail -n 1 || true)"
  fi
  if [[ -z "${line}" ]]; then
    return 0
  fi
  line="${line#*=}"
  line="${line%\"}"
  line="${line#\"}"
  line="${line%\'}"
  line="${line#\'}"
  echo "${line}"
}

upsert_env_value() {
  local key="$1"
  local value="$2"
  local escaped
  escaped="$(printf '%s' "${value}" | sed -e 's/[&|]/\\&/g')"

  if grep -q -E "^${key}=" "${ENV_FILE}"; then
    sed -i "s|^${key}=.*|${key}=${escaped}|g" "${ENV_FILE}"
  else
    echo "${key}=${value}" >> "${ENV_FILE}"
  fi
}

prompt_value() {
  local label="$1"
  local default_value="${2:-}"
  local result=""
  read -r -p "${label}${default_value:+ [${default_value}]}: " result
  if [[ -z "${result}" ]]; then
    result="${default_value}"
  fi
  echo "${result}"
}

prompt_required_value() {
  local label="$1"
  local default_value="${2:-}"
  local result=""
  while true; do
    result="$(prompt_value "${label}" "${default_value}")"
    if [[ -n "${result}" ]]; then
      echo "${result}"
      return 0
    fi
    echo "This field is required."
  done
}

prompt_required_secret() {
  local label="$1"
  local default_mask="${2:-}"
  local result=""
  while true; do
    if [[ -n "${default_mask}" ]]; then
      read -r -s -p "${label} [Press Enter to keep current]: " result
    else
      read -r -s -p "${label}: " result
    fi
    echo

    if [[ -n "${result}" ]]; then
      echo "${result}"
      return 0
    fi

    if [[ -n "${default_mask}" ]]; then
      echo "${default_mask}"
      return 0
    fi
    echo "This field is required."
  done
}

if [[ $# -gt 0 ]]; then
  if [[ "${1}" == "-h" || "${1}" == "--help" ]]; then
    cat <<'EOF'
Usage:
  ./run_linux.sh

The script runs in interactive mode and will ask for:
  - AI_BASE_URL
  - AI_API_KEY
  - AI_MODELS
  - PORT
  - APP_SECRET_KEY (optional)
EOF
    exit 0
  fi
  echo "Error: this script uses interactive input. Run without arguments: ./run_linux.sh" >&2
  exit 1
fi

echo "[1/7] Checking Python..."
if ! has_cmd python3; then
  echo "python3 not found. Installing..."
  install_python_deps
fi

if ! python3 -m venv --help >/dev/null 2>&1; then
  echo "python3 venv module is unavailable. Installing python venv dependencies..."
  install_python_deps
fi

echo "[2/7] Creating virtual environment..."
if [[ ! -f "${VENV_DIR}/bin/activate" ]]; then
  if [[ -d "${VENV_DIR}" ]]; then
    echo "Detected incomplete virtualenv at ${VENV_DIR}, recreating..."
  fi
  python3 -m venv "${VENV_DIR}"
fi

# shellcheck disable=SC1091
if [[ ! -f "${VENV_DIR}/bin/activate" ]]; then
  echo "Error: failed to create virtualenv at ${VENV_DIR}." >&2
  echo "Please check python3-venv installation and directory permissions." >&2
  exit 1
fi

source "${VENV_DIR}/bin/activate"

echo "[3/7] Installing Python dependencies..."
python -m pip install --upgrade pip >/dev/null
pip install -r "${PROJECT_DIR}/requirements.txt"

echo "[4/7] Preparing config files..."
ENV_PREEXISTED="false"
if [[ -f "${ENV_FILE}" ]]; then
  ENV_PREEXISTED="true"
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  cp "${ENV_EXAMPLE_FILE}" "${ENV_FILE}"
fi
if [[ ! -f "${USERS_FILE}" ]]; then
  cp "${USERS_EXAMPLE_FILE}" "${USERS_FILE}"
fi
mkdir -p "${PROJECT_DIR}/data" "${LOG_DIR}"

if [[ -z "${AI_BASE_URL}" ]]; then
  AI_BASE_URL="$(read_env_value "AI_BASE_URL")"
fi
if [[ -z "${AI_API_KEY}" ]]; then
  AI_API_KEY="$(read_env_value "AI_API_KEY")"
fi
if [[ -z "${AI_MODELS}" ]]; then
  AI_MODELS="$(read_env_value "AI_MODELS")"
fi
if [[ -z "${PORT}" ]]; then
  PORT="$(read_env_value "PORT")"
fi
if [[ -z "${APP_SECRET_KEY}" ]]; then
  APP_SECRET_KEY="$(read_env_value "APP_SECRET_KEY")"
fi

if [[ -z "${AI_MODELS}" ]]; then
  AI_MODELS="${DEFAULT_AI_MODELS}"
fi
if [[ -z "${PORT}" ]]; then
  PORT="${DEFAULT_PORT}"
fi

if [[ "${ENV_PREEXISTED}" == "true" ]]; then
  echo "[5/7] Existing .env detected, skipping interactive input."
  if [[ -z "${AI_BASE_URL}" || -z "${AI_API_KEY}" ]]; then
    echo "Error: existing .env is missing AI_BASE_URL or AI_API_KEY." >&2
    echo "Please update ${ENV_FILE} and rerun." >&2
    exit 1
  fi
  if [[ -z "${APP_SECRET_KEY}" ]]; then
    APP_SECRET_KEY="dev-secret-$(date +%s)"
  fi
  echo "[6/7] Using existing .env values."
else
  echo "[5/7] Interactive setup..."
  AI_BASE_URL="$(prompt_required_value "AI API Base URL (e.g. https://api.openai.com/v1)" "${AI_BASE_URL}")"
  AI_API_KEY="$(prompt_required_secret "AI API Key" "${AI_API_KEY}")"
  AI_MODELS="$(prompt_required_value "AI Models (comma-separated)" "${AI_MODELS}")"
  PORT="$(prompt_required_value "Server Port" "${PORT}")"

  generated_secret="dev-secret-$(date +%s)"
  APP_SECRET_KEY="$(prompt_value "App Secret Key (optional, auto-generate if empty)" "${APP_SECRET_KEY}")"
  if [[ -z "${APP_SECRET_KEY}" ]]; then
    APP_SECRET_KEY="${generated_secret}"
  fi

  echo "[6/7] Saving and exporting runtime environment..."
  save_answer="$(prompt_value "Save these values to .env for next runs? (Y/n)" "Y")"
  if [[ "${save_answer}" =~ ^[Yy]$ || -z "${save_answer}" ]]; then
    upsert_env_value "APP_SECRET_KEY" "${APP_SECRET_KEY}"
    upsert_env_value "AI_BASE_URL" "${AI_BASE_URL}"
    upsert_env_value "AI_API_KEY" "${AI_API_KEY}"
    upsert_env_value "AI_MODELS" "${AI_MODELS}"
    upsert_env_value "USERS_FILE" "${USERS_FILE}"
    upsert_env_value "PORT" "${PORT}"
    echo ".env updated."
  else
    echo "Skipping .env update."
  fi
fi

export APP_SECRET_KEY
export AI_BASE_URL
export AI_API_KEY
export AI_MODELS
export USERS_FILE="${USERS_FILE}"
export PORT="${PORT}"
export LOG_TO_STDOUT="${LOG_TO_STDOUT}"

echo "[7/7] Starting app in background..."
if [[ -f "${PID_FILE}" ]]; then
  OLD_PID="$(cat "${PID_FILE}" 2>/dev/null || true)"
  if is_process_running "${OLD_PID}"; then
    echo "App is already running (PID: ${OLD_PID})."
    echo "URL: http://127.0.0.1:${PORT}"
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
  APP_SECRET_KEY="${APP_SECRET_KEY}" \
  AI_BASE_URL="${AI_BASE_URL}" \
  AI_API_KEY="${AI_API_KEY}" \
  AI_MODELS="${AI_MODELS}" \
  USERS_FILE="${USERS_FILE}" \
  PORT="${PORT}" \
  LOG_TO_STDOUT="${LOG_TO_STDOUT}" \
  "${VENV_DIR}/bin/python" app.py >"${RUNTIME_LOG_FILE}" 2>&1 < /dev/null &

APP_PID=$!
echo "${APP_PID}" > "${PID_FILE}"

sleep 1
if is_process_running "${APP_PID}"; then
  echo "Started."
  echo "PID: ${APP_PID}"
  echo "URL: http://127.0.0.1:${PORT}"
  echo "Logs dir: ${LOG_DIR}"
  echo "Category logs: app.log request.log auth.log conversation.log chat.log error.log"
  echo "Runtime output: ${RUNTIME_LOG_FILE}"
  echo "Stop: bash stop_linux.sh"
else
  echo "Failed to start app. Showing recent logs:"
  tail -n 60 "${RUNTIME_LOG_FILE}" || true
  rm -f "${PID_FILE}"
  exit 1
fi
