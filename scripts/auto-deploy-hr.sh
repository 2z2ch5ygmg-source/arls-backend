#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

resolve_bin() {
  local cmd="$1"
  shift || true

  if command -v "$cmd" >/dev/null 2>&1; then
    command -v "$cmd"
    return 0
  fi

  local candidate
  for candidate in "$@"; do
    if [[ -x "$candidate" ]]; then
      echo "$candidate"
      return 0
    fi
  done

  return 1
}

AUTO_DEPLOY_BRANCH="${AUTO_DEPLOY_BRANCH:-main}"
AUTO_DEPLOY_REMOTE="${AUTO_DEPLOY_REMOTE:-}"
AUTO_DEPLOY_COMMIT_MSG="${AUTO_DEPLOY_COMMIT_MSG:-ui: auto deploy $(date +%Y-%m-%dT%H:%M:%S)}"
AZ_RG="${AZ_RG:-rg-shifty-dev}"
AZ_BACKEND_APP="${AZ_BACKEND_APP:-rg-arls-backend}"
AZ_PYTHON_DEFAULT="$(ls -1 /opt/homebrew/Cellar/azure-cli/*/libexec/bin/python 2>/dev/null | tail -n 1 || true)"
AZ_PYTHON_CLI="${AZ_PYTHON_CLI:-$AZ_PYTHON_DEFAULT}"
AZ_CLI_MODE="az"
AZ_BIN="$(resolve_bin az \
  "$HOME/.homebrew/bin/az" \
  "/opt/homebrew/bin/az" \
  "/usr/local/bin/az" || true)"

log() {
  printf '[AUTO DEPLOY] %s\n' "$1"
}

az_cli() {
  if [[ "$AZ_CLI_MODE" == "python" ]]; then
    "$AZ_PYTHON_CLI" -Im azure.cli "$@"
  else
    "$AZ_BIN" "$@"
  fi
}

configure_az_cli() {
  if [[ -n "$AZ_BIN" ]] && "$AZ_BIN" version >/dev/null 2>&1; then
    AZ_CLI_MODE="az"
    return 0
  fi
  if [[ -n "$AZ_PYTHON_CLI" && -x "$AZ_PYTHON_CLI" ]]; then
    AZ_CLI_MODE="python"
    if az_cli version >/dev/null 2>&1; then
      log "Azure CLI 호출을 python 모드로 전환합니다."
      return 0
    fi
  fi
  return 1
}

attempt_git_push() {
  if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    log "Git repo가 아니어서 commit/push를 건너뜁니다."
    return 0
  fi

  local top
  top="$(git rev-parse --show-toplevel)"
  if [[ "$top" != "$ROOT_DIR" ]]; then
    log "현재 git top-level($top)이 프로젝트 루트($ROOT_DIR)와 달라 commit/push를 건너뜁니다."
    return 0
  fi

  if [[ -f .git/MERGE_HEAD || -d .git/rebase-apply || -d .git/rebase-merge ]]; then
    log "merge/rebase 진행 중이라 commit/push를 중단합니다."
    return 1
  fi

  local remote_name="${AUTO_DEPLOY_REMOTE:-}"
  if [[ -z "$remote_name" ]]; then
    if git remote get-url origin >/dev/null 2>&1; then
      remote_name="origin"
    elif git remote get-url backend-origin >/dev/null 2>&1; then
      remote_name="backend-origin"
    fi
  fi

  if [[ -z "$remote_name" ]]; then
    log "push 가능한 remote가 없어 commit/push를 건너뜁니다."
    return 0
  fi

  if [[ -z "$(git status --porcelain)" ]]; then
    log "변경 사항이 없어 commit/push를 건너뜁니다."
    return 0
  fi

  git add .
  if git diff --cached --quiet; then
    log "staged 변경이 없어 commit/push를 건너뜁니다."
    return 0
  fi

  git commit -m "$AUTO_DEPLOY_COMMIT_MSG"
  git push "$remote_name" "$AUTO_DEPLOY_BRANCH"
  log "git push 완료: $remote_name/$AUTO_DEPLOY_BRANCH"
}

resolve_acr_name() {
  if [[ -n "${AZ_BACKEND_ACR_NAME:-}" ]]; then
    return 0
  fi

  if ! configure_az_cli; then
    log "az CLI 실행 불가로 ACR 자동 감지를 건너뜁니다."
    return 0
  fi

  local acr_user
  acr_user="$(az_cli webapp config container show \
    -g "$AZ_RG" \
    -n "$AZ_BACKEND_APP" \
    --query "[?name=='DOCKER_REGISTRY_SERVER_USERNAME'].value | [0]" \
    -o tsv 2>/dev/null | tr -d '\r' | xargs || true)"
  if [[ -n "$acr_user" ]]; then
    export AZ_BACKEND_ACR_NAME="$acr_user"
    log "AZ_BACKEND_ACR_NAME 자동 설정: $AZ_BACKEND_ACR_NAME"
  fi
}

main() {
  attempt_git_push
  resolve_acr_name

  local has_backend_deploy="false"
  local arg
  for arg in "$@"; do
    if [[ "$arg" == "--backend-deploy" ]]; then
      has_backend_deploy="true"
      break
    fi
  done
  if [[ "$has_backend_deploy" != "true" ]]; then
    set -- "$@" --backend-deploy container
  fi

  bash "$SCRIPT_DIR/deploy-azure.sh" "$@"
}

main "$@"
