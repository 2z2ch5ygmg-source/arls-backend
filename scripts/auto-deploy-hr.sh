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
AZ_RG="${AZ_RG:-}"
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

collect_changed_paths() {
  {
    git diff --name-only
    git diff --cached --name-only
    git ls-files --others --exclude-standard
  } | sed '/^$/d' | sort -u
}

collect_staged_paths() {
  git diff --cached --name-only | sed '/^$/d' | sort -u
}

build_allowed_git_patterns() {
  local frontend_only="false"
  local backend_only="false"
  local arg

  for arg in "$@"; do
    case "$arg" in
      --frontend-only)
        frontend_only="true"
        ;;
      --backend-only)
        backend_only="true"
        ;;
    esac
  done

  local -a patterns=()
  if [[ "$frontend_only" == "true" ]]; then
    patterns=(
      "frontend/*"
    )
  elif [[ "$backend_only" == "true" ]]; then
    patterns=(
      "app/*"
      "migrations/*"
      "tests/*"
      "requirements*.txt"
      "Dockerfile"
      "Dockerfile.*"
      "scripts/deploy-azure.sh"
      "scripts/auto-deploy-hr.sh"
    )
  else
    patterns=(
      "frontend/*"
      "app/*"
      "migrations/*"
      "tests/*"
      "requirements*.txt"
      "Dockerfile"
      "Dockerfile.*"
      "scripts/deploy-azure.sh"
      "scripts/auto-deploy-hr.sh"
    )
  fi

  printf '%s\n' "${patterns[@]}"
}

path_matches_allowed_patterns() {
  local path="$1"
  shift || true

  local pattern
  for pattern in "$@"; do
    if [[ "$path" == $pattern ]]; then
      return 0
    fi
  done

  return 1
}

attempt_git_push() {
  local args=("$@")

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

  local -a changed_paths=()
  while IFS= read -r path; do
    [[ -n "$path" ]] && changed_paths+=("$path")
  done < <(collect_changed_paths)
  if [[ "${#changed_paths[@]}" -eq 0 ]]; then
    log "변경 사항이 없어 commit/push를 건너뜁니다."
    return 0
  fi

  local -a allowed_patterns=()
  while IFS= read -r path; do
    [[ -n "$path" ]] && allowed_patterns+=("$path")
  done < <(build_allowed_git_patterns "${args[@]}")
  local -a stageable_paths=()
  local -a blocked_paths=()
  local -a staged_paths=()
  local -a staged_blocked_paths=()
  local path

  for path in "${changed_paths[@]}"; do
    if path_matches_allowed_patterns "$path" "${allowed_patterns[@]}"; then
      stageable_paths+=("$path")
    else
      blocked_paths+=("$path")
    fi
  done

  if [[ "${#stageable_paths[@]}" -eq 0 ]]; then
    log "배포 범위 내 변경이 없어 commit/push를 건너뜁니다."
    return 0
  fi

  while IFS= read -r path; do
    [[ -n "$path" ]] && staged_paths+=("$path")
  done < <(collect_staged_paths)

  if [[ "${#staged_paths[@]}" -gt 0 ]]; then
    for path in "${staged_paths[@]}"; do
      if ! path_matches_allowed_patterns "$path" "${allowed_patterns[@]}"; then
        staged_blocked_paths+=("$path")
      fi
    done
  fi

  if [[ "${#staged_blocked_paths[@]}" -gt 0 ]]; then
    log "배포 범위 밖 staged 변경이 있어 자동 commit/push를 건너뜁니다."
    for path in "${staged_blocked_paths[@]}"; do
      log "staged 범위 밖 변경: $path"
    done
    return 0
  fi

  if [[ "${#blocked_paths[@]}" -gt 0 ]]; then
    log "배포 범위 밖 변경은 제외하고 범위 내 변경만 자동 commit/push 합니다."
    for path in "${blocked_paths[@]}"; do
      log "제외되는 범위 밖 변경: $path"
    done
  fi

  git add -- "${stageable_paths[@]}"
  local -a final_staged_paths=()
  while IFS= read -r path; do
    [[ -n "$path" ]] && final_staged_paths+=("$path")
  done < <(collect_staged_paths)

  local -a final_staged_blocked_paths=()
  if [[ "${#final_staged_paths[@]}" -gt 0 ]]; then
    for path in "${final_staged_paths[@]}"; do
      if ! path_matches_allowed_patterns "$path" "${allowed_patterns[@]}"; then
        final_staged_blocked_paths+=("$path")
      fi
    done
  fi

  if [[ "${#final_staged_blocked_paths[@]}" -gt 0 ]]; then
    log "staged 영역에 범위 밖 변경이 남아 있어 자동 commit/push를 중단합니다."
    for path in "${final_staged_blocked_paths[@]}"; do
      log "최종 staged 범위 밖 변경: $path"
    done
    return 0
  fi

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
    return 0
  fi

  if [[ -n "${AZ_RG:-}" ]]; then
    local rg_acrs
    rg_acrs="$(az_cli acr list --resource-group "$AZ_RG" --query "[].name" -o tsv 2>/dev/null || true)"
    local rg_acr_count
    rg_acr_count="$(printf '%s\n' "$rg_acrs" | sed '/^$/d' | wc -l | tr -d ' ' )"
    if [[ "$rg_acr_count" -eq 1 ]]; then
      export AZ_BACKEND_ACR_NAME="$(printf '%s\n' "$rg_acrs" | sed '/^$/d')"
      log "AZ_BACKEND_ACR_NAME 자동 설정: $AZ_BACKEND_ACR_NAME (RG)"
      return 0
    fi
  fi

  local all_acrs
  all_acrs="$(az_cli acr list --query "[].name" -o tsv 2>/dev/null || true)"
  local acr_count
  acr_count="$(printf '%s\n' "$all_acrs" | sed '/^$/d' | wc -l | tr -d ' ')"
  if [[ "$acr_count" -eq 1 ]]; then
    export AZ_BACKEND_ACR_NAME="$(printf '%s\n' "$all_acrs" | sed '/^$/d')"
    log "AZ_BACKEND_ACR_NAME 자동 설정: $AZ_BACKEND_ACR_NAME (구독)"
    return 0
  fi

  if [[ "$acr_count" -gt 1 ]]; then
    log "구독에 여러 ACR이 있어 AZ_BACKEND_ACR_NAME을 자동 선택할 수 없습니다."
    log "확인된 ACR 목록:"
    az_cli acr list --query "[].{name:name, loginServer:loginServer, resourceGroup:resourceGroup}" --output table
  elif [[ -n "${AZ_RG:-}" ]]; then
    local rg_acrs_list
    rg_acrs_list="$(printf '%s\n' "$rg_acrs" | sed '/^$/d' | tr '\n' ' ')"
    if [[ -n "$rg_acrs_list" ]]; then
      log "RG($AZ_RG)에서 ACR 후보: $rg_acrs_list"
    fi
  else
    log "AZ_RG 미설정 상태입니다."
  fi

  if [[ -n "${AZ_RG:-}" ]]; then
    return 0
  fi

  return 0
}

resolve_rg_by_backend_app() {
  if [[ -z "$AZ_BACKEND_APP" ]]; then
    return 1
  fi

  local rows
  rows="$(az_cli webapp list --query "[?name=='$AZ_BACKEND_APP'].{name:name,resourceGroup:resourceGroup}" -o tsv 2>/dev/null || true)"
  if [[ -z "$rows" ]]; then
    return 1
  fi

  local rg_count
  rg_count="$(printf '%s\n' "$rows" | sed '/^$/d' | wc -l | tr -d ' ')"
  if [[ "$rg_count" -eq 1 ]]; then
    printf '%s\n' "$rows" | awk -F '\t' '{print $2}'
    return 0
  fi

  echo "동일한 웹앱명 '$AZ_BACKEND_APP'이(가) 여러 RG에 존재합니다."
  printf '%s\n' "$rows" | awk -F '\t' '{print " - " $2 " / " $1}'
  return 1
}

main() {
  attempt_git_push "$@"
  resolve_acr_name
  if [[ -z "$AZ_RG" ]]; then
    if ! AZ_RG="$(resolve_rg_by_backend_app)"; then
      echo "AZ_RG를 지정하지 않으면 컨테이너 자격증명 자동 감지가 정확하지 않을 수 있습니다."
    fi
  fi

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
