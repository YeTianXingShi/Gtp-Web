#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_CONFIG_FILE="${PROJECT_DIR}/config/deploy.env"
CONFIG_FILE="${1:-${DEPLOY_CONFIG:-${DEFAULT_CONFIG_FILE}}}"

has_cmd() {
  command -v "$1" >/dev/null 2>&1
}

is_truthy() {
  case "${1:-}" in
    1|true|TRUE|yes|YES|on|ON) return 0 ;;
    *) return 1 ;;
  esac
}

shell_quote() {
  printf '%q' "$1"
}

resolve_local_path() {
  local path="$1"

  if [[ "${path}" = /* ]]; then
    printf '%s\n' "${path}"
    return
  fi

  printf '%s\n' "${PROJECT_DIR}/${path}"
}

resolve_remote_path() {
  local path="$1"

  if [[ "${path}" = /* ]]; then
    printf '%s\n' "${path}"
    return
  fi

  printf '%s\n' "${REMOTE_DIR}/${path}"
}

ensure_config_file() {
  if [[ ! -f "${CONFIG_FILE}" ]]; then
    echo "未找到部署配置文件：${CONFIG_FILE}"
    echo "请先参考 config/deploy.example.env 创建 config/deploy.env。"
    exit 1
  fi
}

load_config() {
  set -a
  source "${CONFIG_FILE}"
  set +a

  DEPLOY_PORT="${DEPLOY_PORT:-22}"
  LOCAL_GIT_PUSH="${LOCAL_GIT_PUSH:-1}"
  LOCAL_GIT_REMOTE="${LOCAL_GIT_REMOTE:-origin}"
  REMOTE_GIT_REMOTE="${REMOTE_GIT_REMOTE:-origin}"
  SSH_STRICT_HOST_KEY_CHECKING="${SSH_STRICT_HOST_KEY_CHECKING:-accept-new}"
  SYNC_LOCAL_CONFIG="${SYNC_LOCAL_CONFIG:-1}"
  LOCAL_ENV_DIR="${LOCAL_ENV_DIR:-config/env}"
  LOCAL_USERS_FILE="${LOCAL_USERS_FILE:-config/users.json}"
  REMOTE_ENV_DIR="${REMOTE_ENV_DIR:-config/env}"
  REMOTE_USERS_FILE="${REMOTE_USERS_FILE:-config/users.json}"
}

require_value() {
  local name="$1"
  local value="${!name:-}"

  if [[ -z "${value}" ]]; then
    echo "配置项 ${name} 不能为空。"
    exit 1
  fi
}

ensure_dependencies() {
  if ! has_cmd git; then
    echo "未检测到 git，请先安装 git。"
    exit 1
  fi

  if ! has_cmd ssh; then
    echo "未检测到 ssh，请先安装 OpenSSH 客户端。"
    exit 1
  fi

  if ! has_cmd scp; then
    echo "未检测到 scp，请先安装 OpenSSH 客户端。"
    exit 1
  fi

  if [[ -n "${DEPLOY_PASSWORD:-}" ]] && ! has_cmd sshpass; then
    echo "检测到配置了 DEPLOY_PASSWORD，但本机未安装 sshpass。"
    echo "请先安装 sshpass，或清空 DEPLOY_PASSWORD 后改用 SSH Key/交互式登录。"
    exit 1
  fi
}

ensure_git_repo() {
  if ! git -C "${PROJECT_DIR}" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "当前目录不是 Git 仓库：${PROJECT_DIR}"
    exit 1
  fi
}

resolve_local_branch() {
  local branch="${LOCAL_GIT_BRANCH:-}"

  if [[ -z "${branch}" ]]; then
    branch="$(git -C "${PROJECT_DIR}" rev-parse --abbrev-ref HEAD)"
  fi

  if [[ -z "${branch}" || "${branch}" == "HEAD" ]]; then
    echo "无法识别当前分支，请在配置中显式设置 LOCAL_GIT_BRANCH。"
    exit 1
  fi

  printf '%s\n' "${branch}"
}

push_local_changes() {
  local branch="$1"

  if ! is_truthy "${LOCAL_GIT_PUSH}"; then
    echo "已跳过本地 git push。"
    return
  fi

  if ! git -C "${PROJECT_DIR}" diff --quiet --ignore-submodules HEAD --; then
    echo "提示：检测到本地仍有未提交改动，git push 只会推送已提交内容。"
  fi

  echo "开始执行本地 git push：${LOCAL_GIT_REMOTE} ${branch}"
  git -C "${PROJECT_DIR}" push "${LOCAL_GIT_REMOTE}" "${branch}"
}

run_ssh_script() {
  local remote_script="$1"
  local encoded_script
  local ssh_target="${DEPLOY_USER}@${DEPLOY_HOST}"
  local ssh_opts=(
    -p "${DEPLOY_PORT}"
    -o "StrictHostKeyChecking=${SSH_STRICT_HOST_KEY_CHECKING}"
  )

  if [[ -n "${SSH_CONNECT_TIMEOUT:-}" ]]; then
    ssh_opts+=( -o "ConnectTimeout=${SSH_CONNECT_TIMEOUT}" )
  fi

  printf -v encoded_script '%q' "${remote_script}"

  if [[ -n "${DEPLOY_PASSWORD:-}" ]]; then
    sshpass -p "${DEPLOY_PASSWORD}" ssh "${ssh_opts[@]}" "${ssh_target}" "bash -lc ${encoded_script}"
    return
  fi

  ssh "${ssh_opts[@]}" "${ssh_target}" "bash -lc ${encoded_script}"
}

run_scp_upload() {
  local source_path="$1"
  local target_path="$2"
  local ssh_target="${DEPLOY_USER}@${DEPLOY_HOST}"
  local scp_opts=(
    -P "${DEPLOY_PORT}"
    -p
    -o "StrictHostKeyChecking=${SSH_STRICT_HOST_KEY_CHECKING}"
  )

  if [[ -n "${SSH_CONNECT_TIMEOUT:-}" ]]; then
    scp_opts+=( -o "ConnectTimeout=${SSH_CONNECT_TIMEOUT}" )
  fi

  if [[ -n "${DEPLOY_PASSWORD:-}" ]]; then
    sshpass -p "${DEPLOY_PASSWORD}" scp "${scp_opts[@]}" "$source_path" "${ssh_target}:${target_path}"
    return
  fi

  scp "${scp_opts[@]}" "$source_path" "${ssh_target}:${target_path}"
}

run_scp_upload_dir() {
  local source_path="$1"
  local target_dir="$2"
  local ssh_target="${DEPLOY_USER}@${DEPLOY_HOST}"
  local scp_opts=(
    -r
    -p
    -P "${DEPLOY_PORT}"
    -o "StrictHostKeyChecking=${SSH_STRICT_HOST_KEY_CHECKING}"
  )

  if [[ -n "${SSH_CONNECT_TIMEOUT:-}" ]]; then
    scp_opts+=( -o "ConnectTimeout=${SSH_CONNECT_TIMEOUT}" )
  fi

  if [[ -n "${DEPLOY_PASSWORD:-}" ]]; then
    sshpass -p "${DEPLOY_PASSWORD}" scp "${scp_opts[@]}" "$source_path" "${ssh_target}:${target_dir}"
    return
  fi

  scp "${scp_opts[@]}" "$source_path" "${ssh_target}:${target_dir}"
}

build_remote_prepare_script() {
  local remote_branch="$1"
  local sync_config="$2"
  local remote_env_dir="$3"
  local remote_env_parent="$4"
  local remote_users_parent="$5"
  local remote_pull_cmd="git pull"

  if [[ -n "${REMOTE_GIT_REMOTE:-}" ]]; then
    remote_pull_cmd+=" $(shell_quote "${REMOTE_GIT_REMOTE}")"
  fi

  if [[ -n "${remote_branch}" ]]; then
    remote_pull_cmd+=" $(shell_quote "${remote_branch}")"
  fi

  cat <<EOF_INNER
set -euo pipefail
cd $(shell_quote "${REMOTE_DIR}")
${remote_pull_cmd}
${REMOTE_STOP_CMD}
EOF_INNER

  if is_truthy "${sync_config}"; then
    cat <<EOF_INNER
mkdir -p $(shell_quote "${remote_env_parent}")
mkdir -p $(shell_quote "${remote_users_parent}")
rm -rf $(shell_quote "${remote_env_dir}")
EOF_INNER
  fi
}


build_remote_start_script() {
  cat <<EOF_INNER
set -euo pipefail
cd $(shell_quote "${REMOTE_DIR}")
${REMOTE_START_CMD}
EOF_INNER
}

sync_local_config_files() {
  local local_env_dir
  local local_users_file
  local remote_env_dir
  local remote_users_file
  local remote_env_parent

  if ! is_truthy "${SYNC_LOCAL_CONFIG}"; then
    echo "已跳过同步本地配置文件。"
    return
  fi

  local_env_dir="$(resolve_local_path "${LOCAL_ENV_DIR}")"
  local_users_file="$(resolve_local_path "${LOCAL_USERS_FILE}")"
  remote_env_dir="$(resolve_remote_path "${REMOTE_ENV_DIR}")"
  remote_users_file="$(resolve_remote_path "${REMOTE_USERS_FILE}")"
  remote_env_parent="$(dirname "${remote_env_dir}")"

  if [[ ! -d "${local_env_dir}" ]]; then
    echo "本地配置目录不存在：${local_env_dir}"
    exit 1
  fi

  if [[ ! -f "${local_users_file}" ]]; then
    echo "本地用户配置不存在：${local_users_file}"
    exit 1
  fi

  echo "开始同步本地配置目录：${local_env_dir} -> ${remote_env_dir}"
  run_scp_upload_dir "${local_env_dir}" "${remote_env_parent}/"

  echo "开始同步本地用户配置：${local_users_file} -> ${remote_users_file}"
  run_scp_upload "${local_users_file}" "${remote_users_file}"
}

run_remote_deploy() {
  local remote_branch="$1"
  local remote_env_dir="$(resolve_remote_path "${REMOTE_ENV_DIR}")"
  local remote_users_file="$(resolve_remote_path "${REMOTE_USERS_FILE}")"
  local remote_env_parent="$(dirname "${remote_env_dir}")"
  local remote_users_parent="$(dirname "${remote_users_file}")"
  local ssh_target="${DEPLOY_USER}@${DEPLOY_HOST}"

  echo "开始连接远程服务器：${ssh_target}:${DEPLOY_PORT}"
  echo "远程项目目录：${REMOTE_DIR}"

  run_ssh_script "$(build_remote_prepare_script "${remote_branch}" "${SYNC_LOCAL_CONFIG}" "${remote_env_dir}" "${remote_env_parent}" "${remote_users_parent}")"
  sync_local_config_files
  run_ssh_script "$(build_remote_start_script)"
}

main() {
  local local_branch
  local remote_branch

  ensure_config_file
  load_config
  ensure_dependencies
  ensure_git_repo

  require_value DEPLOY_HOST
  require_value DEPLOY_PORT
  require_value DEPLOY_USER
  require_value REMOTE_DIR
  require_value REMOTE_STOP_CMD
  require_value REMOTE_START_CMD

  if is_truthy "${SYNC_LOCAL_CONFIG}"; then
    require_value LOCAL_ENV_DIR
    require_value LOCAL_USERS_FILE
    require_value REMOTE_ENV_DIR
    require_value REMOTE_USERS_FILE
  fi

  local_branch="$(resolve_local_branch)"
  remote_branch="${REMOTE_GIT_BRANCH:-${local_branch}}"

  echo "使用配置文件：${CONFIG_FILE}"
  echo "本地分支：${local_branch}"
  echo "远程分支：${remote_branch}"
  echo "同步配置文件：${SYNC_LOCAL_CONFIG}"

  push_local_changes "${local_branch}"
  run_remote_deploy "${remote_branch}"

  echo "部署完成。"
}

main "$@"
