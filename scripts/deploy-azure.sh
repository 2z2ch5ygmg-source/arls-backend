#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"
TMP_DIR="$(mktemp -d)"

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

resolve_backend_dir() {
  if [[ -f "$ROOT_DIR/Dockerfile" && -d "$ROOT_DIR/app" ]]; then
    echo "$ROOT_DIR"
    return 0
  fi
  if [[ -f "$ROOT_DIR/backend/Dockerfile" && -d "$ROOT_DIR/backend/app" ]]; then
    echo "$ROOT_DIR/backend"
    return 0
  fi
  if [[ -d "$ROOT_DIR/backend/app" ]]; then
    echo "$ROOT_DIR/backend"
    return 0
  fi
  echo "$ROOT_DIR"
}

BACKEND_DIR="$(resolve_backend_dir)"

trap 'rm -rf "$TMP_DIR"' EXIT

usage() {
  cat <<'EOF'
사용법:
  ./scripts/deploy-azure.sh [--backend-only] [--frontend-only] [--backend-url <url>] [--backend-deploy <container|zip>]

권장(한 번에 배포):
  ./scripts/deploy-azure.sh --backend-deploy container
EOF
}

AZ_PYTHON_DEFAULT="$(ls -1 /opt/homebrew/Cellar/azure-cli/*/libexec/bin/python 2>/dev/null | tail -n 1 || true)"
AZ_PYTHON_CLI="${AZ_PYTHON_CLI:-$AZ_PYTHON_DEFAULT}"
AZ_CLI_MODE="az"
AZ_BIN="$(resolve_bin az \
  "$HOME/.homebrew/bin/az" \
  "/opt/homebrew/bin/az" \
  "/usr/local/bin/az" || true)"
DOCKER_BIN="$(resolve_bin docker \
  "/usr/local/bin/docker" \
  "/opt/homebrew/bin/docker" \
  "/Applications/Docker.app/Contents/Resources/bin/docker" || true)"

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
      echo "Azure CLI 호출을 python 모드로 전환합니다: $AZ_PYTHON_CLI"
      return 0
    fi
  fi

  echo "Azure CLI(az) 실행에 실패했습니다."
  exit 1
}

configure_az_cli

load_dotenv() {
  local file="$1"
  local raw_key raw_value key value

  while IFS='=' read -r raw_key raw_value || [[ -n "$raw_key" ]]; do
    if [[ -z "${raw_key//[[:space:]]/}" ]]; then
      continue
    fi
    [[ "$raw_key" =~ ^[[:space:]]*# ]] && continue

    key="${raw_key%%=*}"
    key="$(echo "$key" | awk '{$1=$1; print}')"  # trim
    value="${raw_value:-}"
    value="${value%$'\r'}"
    value="$(echo "$value" | awk '{$1=$1; print}')" # trim
    value="${value%\"}"; value="${value#\"}"
    value="${value%\'}"; value="${value#\'}"

  case "$key" in
      DATABASE_URL|JWT_SECRET|INIT_SUPER_ADMIN_PASSWORD|INIT_SUPER_ADMIN_USERNAME|INIT_SUPER_ADMIN_TENANT_CODE|CORS_ORIGINS|CORS_ORIGIN_REGEX|AZ_CORS_ORIGINS|AZ_CORS_ORIGIN_REGEX|RATE_LIMIT_PER_MINUTE|API_IDEMPOTENCY_TTL_MINUTES|JWT_EXPIRES_MINUTES|AZ_SUBSCRIPTION_ID|AZ_SUBSCRIPTION_NAME|AZ_FRONT_STORAGE_PREFIX|AZ_FRONT_STORAGE_ACCOUNT|ALLOW_BRANCH_MANAGER_USER_MANAGE|AZ_ALLOW_BRANCH_MANAGER_USER_MANAGE|SOC_INTEGRATION_ENABLED|SOC_INGEST_REQUIRE_HMAC|SOC_INGEST_HMAC_SECRET|SOC_INGEST_REQUIRE_TOKEN|SOC_INGEST_TOKEN|SOC_LEAVE_OVERRIDE_ENABLED|SOC_OVERTIME_ENABLED|SOC_CLOSING_OT_ENABLED|SHEETS_SYNC_ENABLED|APPLE_REPORT_OVERNIGHT_ENABLED|APPLE_REPORT_DAYTIME_ENABLED|APPLE_REPORT_OT_ENABLED|APPLE_REPORT_TOTAL_LATE_ENABLED|PAYROLL_SHEET_ENABLED|GOOGLE_SHEETS_DEFAULT_WEBHOOK|GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON|GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON_B64|GOOGLE_PLACES_API_KEY|GOOGLE_MAPS_API_KEY|PUSH_NOTIFICATIONS_ENABLED|PUSH_ATTENDANCE_AUTO_CHECKOUT_ENABLED|PUSH_FCM_SERVER_KEY|PUSH_ATTENDANCE_TITLE|PUSH_REQUEST_TIMEOUT_SECONDS|AZ_GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON|AZ_GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON_B64|AZ_GOOGLE_PLACES_API_KEY|AZ_GOOGLE_MAPS_API_KEY|AZ_PUSH_NOTIFICATIONS_ENABLED|AZ_PUSH_ATTENDANCE_AUTO_CHECKOUT_ENABLED|AZ_PUSH_FCM_SERVER_KEY|AZ_PUSH_ATTENDANCE_TITLE|AZ_PUSH_REQUEST_TIMEOUT_SECONDS|AZ_SOC_INTEGRATION_ENABLED|AZ_SOC_INGEST_REQUIRE_HMAC|AZ_SOC_INGEST_HMAC_SECRET|AZ_SOC_INGEST_REQUIRE_TOKEN|AZ_SOC_INGEST_TOKEN|AZ_SOC_LEAVE_OVERRIDE_ENABLED|AZ_SOC_OVERTIME_ENABLED|AZ_SOC_CLOSING_OT_ENABLED|AZ_SHEETS_SYNC_ENABLED|AZ_APPLE_REPORT_OVERNIGHT_ENABLED|AZ_APPLE_REPORT_DAYTIME_ENABLED|AZ_APPLE_REPORT_OT_ENABLED|AZ_APPLE_REPORT_TOTAL_LATE_ENABLED|AZ_PAYROLL_SHEET_ENABLED|AZ_GOOGLE_SHEETS_DEFAULT_WEBHOOK|AZ_BACKEND_DEPLOY_MODE|AZ_BACKEND_ACR_NAME|AZ_BACKEND_IMAGE_REPO|AZ_BACKEND_IMAGE_TAG|AZ_BACKEND_IMAGE_PLATFORM)
        if [[ -z "${!key+x}" ]]; then
          export "$key=$value"
        fi
        ;;
    esac
  done < "$file"
}

contains_csv_value() {
  local csv="$1"
  local value="$2"
  local item
  IFS=',' read -r -a items <<< "$csv"
  for item in "${items[@]}"; do
    item="$(echo "$item" | awk '{$1=$1; print}')"
    if [[ "$item" == "$value" ]]; then
      return 0
    fi
  done
  return 1
}

if [[ -f "$ROOT_DIR/.env" ]]; then
  load_dotenv "$ROOT_DIR/.env"
fi

MODE="all"
CLI_BACKEND_URL=""
CLI_BACKEND_DEPLOY_MODE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --backend-only)
      MODE="backend"
      shift
      ;;
    --frontend-only)
      MODE="frontend"
      shift
      ;;
    --backend-url)
      shift
      if [[ -z "${1:-}" ]]; then
        echo "--backend-url 값이 필요합니다."
        usage
        exit 1
      fi
      CLI_BACKEND_URL="$1"
      shift
      ;;
    --backend-deploy)
      shift
      if [[ -z "${1:-}" ]]; then
        echo "--backend-deploy 값이 필요합니다. (container|zip)"
        usage
        exit 1
      fi
      CLI_BACKEND_DEPLOY_MODE="$1"
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "지원하지 않는 옵션: $1"
      usage
      exit 1
      ;;
  esac
done

AZ_RG="${AZ_RG:-rg-shifty-dev}"
AZ_LOCATION="${AZ_LOCATION:-koreacentral}"
AZ_BACKEND_APP="${AZ_BACKEND_APP:-rg-arls-backend}"
AZ_BACKEND_PLAN="${AZ_BACKEND_PLAN:-rg-arls-backend-plan}"
AZ_BACKEND_SKU="${AZ_BACKEND_SKU:-B1}"
AZ_BACKEND_RUNTIME="${AZ_BACKEND_RUNTIME:-PYTHON|3.12}"
AZ_BACKEND_PORT="${AZ_BACKEND_PORT:-8080}"
AZ_BACKEND_DEPLOY_MODE="${AZ_BACKEND_DEPLOY_MODE:-container}"
AZ_BACKEND_ACR_NAME="${AZ_BACKEND_ACR_NAME:-}"
AZ_BACKEND_IMAGE_REPO="${AZ_BACKEND_IMAGE_REPO:-rg-arls-backend}"
AZ_BACKEND_IMAGE_TAG="${AZ_BACKEND_IMAGE_TAG:-v$(date -u +%y%m%d-%H%M%S)}"
AZ_BACKEND_IMAGE_PLATFORM="${AZ_BACKEND_IMAGE_PLATFORM:-linux/amd64}"

if [[ -n "$CLI_BACKEND_DEPLOY_MODE" ]]; then
  AZ_BACKEND_DEPLOY_MODE="$CLI_BACKEND_DEPLOY_MODE"
fi
AZ_BACKEND_DEPLOY_MODE="$(echo "$AZ_BACKEND_DEPLOY_MODE" | tr '[:upper:]' '[:lower:]')"
if [[ "$AZ_BACKEND_DEPLOY_MODE" != "container" && "$AZ_BACKEND_DEPLOY_MODE" != "zip" ]]; then
  echo "지원하지 않는 백엔드 배포 모드: $AZ_BACKEND_DEPLOY_MODE (container|zip)"
  exit 1
fi

AZ_DATABASE_URL="${AZ_DATABASE_URL:-${DATABASE_URL:-}}"
AZ_JWT_SECRET="${AZ_JWT_SECRET:-${JWT_SECRET:-$(python3 - <<'PY'
import secrets

print(secrets.token_urlsafe(32))
PY
)}}"
AZ_JWT_EXPIRES_MINUTES="${AZ_JWT_EXPIRES_MINUTES:-${JWT_EXPIRES_MINUTES:-480}}"
AZ_JWT_ALGORITHM="${AZ_JWT_ALGORITHM:-${JWT_ALGORITHM:-HS256}}"
AZ_RATE_LIMIT_PER_MINUTE="${AZ_RATE_LIMIT_PER_MINUTE:-240}"
AZ_IDEMPOTENCY_TTL="${AZ_IDEMPOTENCY_TTL:-${API_IDEMPOTENCY_TTL_MINUTES:-120}}"
AZ_ALLOW_BRANCH_MANAGER_USER_MANAGE="${AZ_ALLOW_BRANCH_MANAGER_USER_MANAGE:-${ALLOW_BRANCH_MANAGER_USER_MANAGE:-false}}"
AZ_INIT_SUPER_ADMIN_USERNAME="${AZ_INIT_SUPER_ADMIN_USERNAME:-${INIT_SUPER_ADMIN_USERNAME:-platform_admin}}"
AZ_INIT_SUPER_ADMIN_PASSWORD="${AZ_INIT_SUPER_ADMIN_PASSWORD:-${INIT_SUPER_ADMIN_PASSWORD:-Admin1234!!}}"
AZ_INIT_SUPER_ADMIN_TENANT_CODE="${AZ_INIT_SUPER_ADMIN_TENANT_CODE:-${INIT_SUPER_ADMIN_TENANT_CODE:-MASTER}}"
AZ_CORS_ORIGINS="${AZ_CORS_ORIGINS:-}"
AZ_CORS_ORIGIN_REGEX="${AZ_CORS_ORIGIN_REGEX:-${CORS_ORIGIN_REGEX:-}}"
AZ_SOC_INTEGRATION_ENABLED="${AZ_SOC_INTEGRATION_ENABLED:-${SOC_INTEGRATION_ENABLED:-true}}"
AZ_SOC_INGEST_REQUIRE_HMAC="${AZ_SOC_INGEST_REQUIRE_HMAC:-${SOC_INGEST_REQUIRE_HMAC:-true}}"
AZ_SOC_INGEST_HMAC_SECRET="${AZ_SOC_INGEST_HMAC_SECRET:-${SOC_INGEST_HMAC_SECRET:-${HR_WEBHOOK_SECRET:-$AZ_JWT_SECRET}}}"
AZ_SOC_INGEST_REQUIRE_TOKEN="${AZ_SOC_INGEST_REQUIRE_TOKEN:-${SOC_INGEST_REQUIRE_TOKEN:-false}}"
AZ_SOC_INGEST_TOKEN="${AZ_SOC_INGEST_TOKEN:-${SOC_INGEST_TOKEN:-}}"
AZ_SOC_LEAVE_OVERRIDE_ENABLED="${AZ_SOC_LEAVE_OVERRIDE_ENABLED:-${SOC_LEAVE_OVERRIDE_ENABLED:-true}}"
AZ_SOC_OVERTIME_ENABLED="${AZ_SOC_OVERTIME_ENABLED:-${SOC_OVERTIME_ENABLED:-true}}"
AZ_SOC_CLOSING_OT_ENABLED="${AZ_SOC_CLOSING_OT_ENABLED:-${SOC_CLOSING_OT_ENABLED:-true}}"
AZ_SHEETS_SYNC_ENABLED="${AZ_SHEETS_SYNC_ENABLED:-${SHEETS_SYNC_ENABLED:-false}}"
AZ_APPLE_REPORT_OVERNIGHT_ENABLED="${AZ_APPLE_REPORT_OVERNIGHT_ENABLED:-${APPLE_REPORT_OVERNIGHT_ENABLED:-true}}"
AZ_APPLE_REPORT_DAYTIME_ENABLED="${AZ_APPLE_REPORT_DAYTIME_ENABLED:-${APPLE_REPORT_DAYTIME_ENABLED:-false}}"
AZ_APPLE_REPORT_OT_ENABLED="${AZ_APPLE_REPORT_OT_ENABLED:-${APPLE_REPORT_OT_ENABLED:-false}}"
AZ_APPLE_REPORT_TOTAL_LATE_ENABLED="${AZ_APPLE_REPORT_TOTAL_LATE_ENABLED:-${APPLE_REPORT_TOTAL_LATE_ENABLED:-false}}"
AZ_PAYROLL_SHEET_ENABLED="${AZ_PAYROLL_SHEET_ENABLED:-${PAYROLL_SHEET_ENABLED:-true}}"
AZ_GOOGLE_SHEETS_DEFAULT_WEBHOOK="${AZ_GOOGLE_SHEETS_DEFAULT_WEBHOOK:-${GOOGLE_SHEETS_DEFAULT_WEBHOOK:-}}"
AZ_GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON="${AZ_GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON:-${GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON:-}}"
AZ_GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON_B64="${AZ_GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON_B64:-${GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON_B64:-}}"
AZ_GOOGLE_PLACES_API_KEY="${AZ_GOOGLE_PLACES_API_KEY:-${GOOGLE_PLACES_API_KEY:-}}"
AZ_GOOGLE_MAPS_API_KEY="${AZ_GOOGLE_MAPS_API_KEY:-${GOOGLE_MAPS_API_KEY:-${AZ_GOOGLE_PLACES_API_KEY:-}}}"
AZ_PUSH_NOTIFICATIONS_ENABLED="${AZ_PUSH_NOTIFICATIONS_ENABLED:-${PUSH_NOTIFICATIONS_ENABLED:-true}}"
AZ_PUSH_ATTENDANCE_AUTO_CHECKOUT_ENABLED="${AZ_PUSH_ATTENDANCE_AUTO_CHECKOUT_ENABLED:-${PUSH_ATTENDANCE_AUTO_CHECKOUT_ENABLED:-true}}"
AZ_PUSH_FCM_SERVER_KEY="${AZ_PUSH_FCM_SERVER_KEY:-${PUSH_FCM_SERVER_KEY:-}}"
AZ_PUSH_ATTENDANCE_TITLE="${AZ_PUSH_ATTENDANCE_TITLE:-${PUSH_ATTENDANCE_TITLE:-출퇴근 알림}}"
AZ_PUSH_REQUEST_TIMEOUT_SECONDS="${AZ_PUSH_REQUEST_TIMEOUT_SECONDS:-${PUSH_REQUEST_TIMEOUT_SECONDS:-5}}"
if [[ -z "$AZ_CORS_ORIGIN_REGEX" ]]; then
  AZ_CORS_ORIGIN_REGEX="^https://[a-z0-9-]+\\.z12\\.web\\.core\\.windows\\.net$|^https://rg-arls-backend\\.azurewebsites\\.net$|^https?://localhost(:[0-9]+)?$|^https?://127\\.0\\.0\\.1(:[0-9]+)?$|^(capacitor|ionic|app)://localhost$"
fi

AZ_FRONT_STORAGE_PREFIX="${AZ_FRONT_STORAGE_PREFIX:-rgarlsfront}"
AZ_FRONT_STORAGE_ACCOUNT="${AZ_FRONT_STORAGE_ACCOUNT:-rgarlsfront50018}"
AZ_SUBSCRIPTION_ID="${AZ_SUBSCRIPTION_ID:-}"
AZ_SUBSCRIPTION_NAME="${AZ_SUBSCRIPTION_NAME:-}"
AZ_DEFAULT_SUBSCRIPTION_NAME="${AZ_DEFAULT_SUBSCRIPTION_NAME:-Azure 구독 1}"

az_cli account show >/dev/null 2>&1 || az_cli login

clean_ws() {
  tr -d '[:space:]'
}

az_exec() {
  if [[ -n "${AZ_SUBSCRIPTION_MATCHED:-}" ]]; then
    az_cli "$@" --subscription "$AZ_SUBSCRIPTION_MATCHED"
  else
    az_cli "$@"
  fi
}

AZ_SUBSCRIPTION_ID="$(echo "$AZ_SUBSCRIPTION_ID" | clean_ws)"
AZ_SUBSCRIPTION_NAME="$(echo "$AZ_SUBSCRIPTION_NAME" | sed 's/^ *//;s/ *$//')"
AZ_DEFAULT_SUBSCRIPTION_NAME="$(echo "$AZ_DEFAULT_SUBSCRIPTION_NAME" | sed 's/^ *//;s/ *$//')"

if [[ -z "$AZ_SUBSCRIPTION_NAME" ]]; then
  AZ_SUBSCRIPTION_NAME="$AZ_DEFAULT_SUBSCRIPTION_NAME"
fi

AZ_SUBSCRIPTION_MATCHED=""
if [[ -n "$AZ_SUBSCRIPTION_NAME" ]]; then
  AZ_SUBSCRIPTION_MATCHED="$(az_cli account list --query "[?name=='$AZ_SUBSCRIPTION_NAME' || id=='$AZ_SUBSCRIPTION_NAME'].id | [0]" -o tsv 2>/dev/null | clean_ws || true)"
fi

if [[ -z "$AZ_SUBSCRIPTION_MATCHED" && -n "$AZ_SUBSCRIPTION_ID" ]]; then
  AZ_SUBSCRIPTION_MATCHED="$(az_cli account list --query "[?id=='$AZ_SUBSCRIPTION_ID'].id | [0]" -o tsv 2>/dev/null | clean_ws || true)"
fi

if [[ -z "$AZ_SUBSCRIPTION_MATCHED" ]]; then
  echo "구독 선택 실패: $AZ_SUBSCRIPTION_NAME / $AZ_SUBSCRIPTION_ID"
  echo "현재 로그인 세션에서 구독 ID를 확인할 수 없습니다."
  az_cli account list --query "[].{name:name,id:id,tenantId:tenantId,state:state}" -o table
  exit 1
fi

if ! az_cli account set --subscription "$AZ_SUBSCRIPTION_MATCHED" >/dev/null 2>&1; then
  echo "경고: az account set 실패. 명시적 --subscription 모드로 계속 진행합니다: $AZ_SUBSCRIPTION_MATCHED"
fi

AZ_SUBSCRIPTION_ID="$(az_cli account show --query id -o tsv 2>/dev/null | clean_ws || true)"
if [[ -z "$AZ_SUBSCRIPTION_ID" ]]; then
  AZ_SUBSCRIPTION_ID="$AZ_SUBSCRIPTION_MATCHED"
fi

echo "Azure 구독: $AZ_SUBSCRIPTION_ID"

if [[ -z "$AZ_DATABASE_URL" ]]; then
  echo "DB 연결 문자열이 없습니다. AZ_DATABASE_URL 또는 DATABASE_URL을 먼저 설정하세요."
  exit 1
fi

ensure_backend_url_format() {
  local url="$1"
  url="${url%/}"
  if [[ "$url" != https://* && "$url" != http://* ]]; then
    url="https://$url"
  fi
  echo "$url"
}

wait_for_backend_health() {
  local url="$1"
  local max_retry="${2:-24}"
  local sleep_sec="${3:-5}"
  local i

  for ((i=1; i<=max_retry; i++)); do
    if curl -fsS "${url}/health" >/dev/null 2>&1; then
      echo "백엔드 헬스체크 통과: ${url}/health"
      return 0
    fi
    sleep "$sleep_sec"
  done

  echo "백엔드 헬스체크 실패: ${url}/health"
  return 1
}

deploy_backend() {
  echo "1) 리소스 그룹 확인/생성: $AZ_RG"
  az_exec group create --name "$AZ_RG" --location "$AZ_LOCATION" --output none

  echo "2) App Service 플랜 확인/생성: $AZ_BACKEND_PLAN"
  if ! az_exec appservice plan show --name "$AZ_BACKEND_PLAN" --resource-group "$AZ_RG" >/dev/null 2>&1; then
    az_exec appservice plan create \
      --name "$AZ_BACKEND_PLAN" \
      --resource-group "$AZ_RG" \
      --location "$AZ_LOCATION" \
      --sku "$AZ_BACKEND_SKU" \
      --is-linux \
      --output none
  fi

  echo "3) 웹앱 생성/갱신: $AZ_BACKEND_APP"
  if ! az_exec webapp show --name "$AZ_BACKEND_APP" --resource-group "$AZ_RG" >/dev/null 2>&1; then
    az_exec webapp create \
      --resource-group "$AZ_RG" \
      --plan "$AZ_BACKEND_PLAN" \
      --name "$AZ_BACKEND_APP" \
      --runtime "$AZ_BACKEND_RUNTIME" \
      --https-only true \
      --output none
  fi

  if [[ "$AZ_BACKEND_DEPLOY_MODE" == "zip" ]]; then
    # 컨테이너 모드에서 zip 모드로 전환할 때 반드시 Python 런타임으로 되돌린다.
    az_exec webapp config set \
      --name "$AZ_BACKEND_APP" \
      --resource-group "$AZ_RG" \
      --linux-fx-version "$AZ_BACKEND_RUNTIME" \
      --output none
    local startup_cmd="python -m uvicorn app.main:app --host 0.0.0.0 --port $AZ_BACKEND_PORT"
    az_exec webapp config set \
      --name "$AZ_BACKEND_APP" \
      --resource-group "$AZ_RG" \
      --startup-file "$startup_cmd" \
      --output none
  fi

  local cors="$AZ_CORS_ORIGINS"
  if [[ -z "$cors" ]]; then
    local existing_cors
    existing_cors="$(az_exec webapp config appsettings list --name "$AZ_BACKEND_APP" --resource-group "$AZ_RG" --query "[?name=='CORS_ORIGINS'].value | [0]" -o tsv 2>/dev/null | clean_ws || true)"
    if [[ -n "$existing_cors" && "$existing_cors" != "None" ]]; then
      cors="$existing_cors"
    else
      cors="https://${AZ_BACKEND_APP}.azurewebsites.net,http://localhost:5173,http://127.0.0.1:5173,http://localhost:$AZ_BACKEND_PORT,http://127.0.0.1:$AZ_BACKEND_PORT"
    fi
  fi

  local scm_build="0"
  if [[ "$AZ_BACKEND_DEPLOY_MODE" == "zip" ]]; then
    scm_build="1"
  fi

  echo "4) 앱 설정 반영"
  az_exec webapp config appsettings set --name "$AZ_BACKEND_APP" --resource-group "$AZ_RG" --output none --settings \
    APP_NAME="RG ARLS Dev" \
    ENVIRONMENT="production" \
    PORT="$AZ_BACKEND_PORT" \
    WEBSITES_PORT="$AZ_BACKEND_PORT" \
    DATABASE_URL="$AZ_DATABASE_URL" \
    JWT_SECRET="$AZ_JWT_SECRET" \
    JWT_EXPIRES_MINUTES="$AZ_JWT_EXPIRES_MINUTES" \
    JWT_ALGORITHM="$AZ_JWT_ALGORITHM" \
    API_IDEMPOTENCY_TTL_MINUTES="$AZ_IDEMPOTENCY_TTL" \
    RATE_LIMIT_PER_MINUTE="$AZ_RATE_LIMIT_PER_MINUTE" \
    ALLOW_BRANCH_MANAGER_USER_MANAGE="$AZ_ALLOW_BRANCH_MANAGER_USER_MANAGE" \
    INIT_SUPER_ADMIN_USERNAME="$AZ_INIT_SUPER_ADMIN_USERNAME" \
    INIT_SUPER_ADMIN_PASSWORD="$AZ_INIT_SUPER_ADMIN_PASSWORD" \
    INIT_SUPER_ADMIN_TENANT_CODE="$AZ_INIT_SUPER_ADMIN_TENANT_CODE" \
    SOC_INTEGRATION_ENABLED="$AZ_SOC_INTEGRATION_ENABLED" \
    SOC_INGEST_REQUIRE_HMAC="$AZ_SOC_INGEST_REQUIRE_HMAC" \
    SOC_INGEST_HMAC_SECRET="$AZ_SOC_INGEST_HMAC_SECRET" \
    SOC_INGEST_REQUIRE_TOKEN="$AZ_SOC_INGEST_REQUIRE_TOKEN" \
    SOC_INGEST_TOKEN="$AZ_SOC_INGEST_TOKEN" \
    SOC_LEAVE_OVERRIDE_ENABLED="$AZ_SOC_LEAVE_OVERRIDE_ENABLED" \
    SOC_OVERTIME_ENABLED="$AZ_SOC_OVERTIME_ENABLED" \
    SOC_CLOSING_OT_ENABLED="$AZ_SOC_CLOSING_OT_ENABLED" \
    SHEETS_SYNC_ENABLED="$AZ_SHEETS_SYNC_ENABLED" \
    APPLE_REPORT_OVERNIGHT_ENABLED="$AZ_APPLE_REPORT_OVERNIGHT_ENABLED" \
    APPLE_REPORT_DAYTIME_ENABLED="$AZ_APPLE_REPORT_DAYTIME_ENABLED" \
    APPLE_REPORT_OT_ENABLED="$AZ_APPLE_REPORT_OT_ENABLED" \
    APPLE_REPORT_TOTAL_LATE_ENABLED="$AZ_APPLE_REPORT_TOTAL_LATE_ENABLED" \
    PAYROLL_SHEET_ENABLED="$AZ_PAYROLL_SHEET_ENABLED" \
    GOOGLE_SHEETS_DEFAULT_WEBHOOK="$AZ_GOOGLE_SHEETS_DEFAULT_WEBHOOK" \
    GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON="$AZ_GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON" \
    GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON_B64="$AZ_GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON_B64" \
    GOOGLE_PLACES_API_KEY="$AZ_GOOGLE_PLACES_API_KEY" \
    PUSH_NOTIFICATIONS_ENABLED="$AZ_PUSH_NOTIFICATIONS_ENABLED" \
    PUSH_ATTENDANCE_AUTO_CHECKOUT_ENABLED="$AZ_PUSH_ATTENDANCE_AUTO_CHECKOUT_ENABLED" \
    PUSH_FCM_SERVER_KEY="$AZ_PUSH_FCM_SERVER_KEY" \
    PUSH_ATTENDANCE_TITLE="$AZ_PUSH_ATTENDANCE_TITLE" \
    PUSH_REQUEST_TIMEOUT_SECONDS="$AZ_PUSH_REQUEST_TIMEOUT_SECONDS" \
    CORS_ORIGINS="$cors" \
    CORS_ORIGIN_REGEX="$AZ_CORS_ORIGIN_REGEX" \
    SCM_DO_BUILD_DURING_DEPLOYMENT="$scm_build"

  echo "4-1) 상태 검사 경로 설정: /health"
  az_exec webapp config set \
    --name "$AZ_BACKEND_APP" \
    --resource-group "$AZ_RG" \
    --generic-configurations '{"healthCheckPath":"/health"}' \
    --output none

  if [[ "$AZ_BACKEND_DEPLOY_MODE" == "container" ]]; then
    if [[ -z "$DOCKER_BIN" ]]; then
      echo "docker가 필요합니다. Docker Desktop을 설치 후 다시 실행하세요."
      exit 1
    fi
    if [[ -z "$AZ_BACKEND_ACR_NAME" ]]; then
      echo "컨테이너 배포 모드에서는 AZ_BACKEND_ACR_NAME 설정이 필요합니다."
      echo "예: export AZ_BACKEND_ACR_NAME='acrsecurityopsprod001-eneccucxdcfedqhm'"
      exit 1
    fi

    local acr_login_server
    acr_login_server="$(az_exec acr show --name "$AZ_BACKEND_ACR_NAME" --query loginServer -o tsv 2>/dev/null || true)"
    if [[ -z "$acr_login_server" ]]; then
      echo "ACR 조회 실패: $AZ_BACKEND_ACR_NAME"
      exit 1
    fi

    BACKEND_IMAGE="${acr_login_server}/${AZ_BACKEND_IMAGE_REPO}:${AZ_BACKEND_IMAGE_TAG}"
    echo "5) 백엔드 컨테이너 빌드/푸시"
    echo "이미지: $BACKEND_IMAGE"
    az_exec acr login --name "$AZ_BACKEND_ACR_NAME"
    "$DOCKER_BIN" build --platform "$AZ_BACKEND_IMAGE_PLATFORM" -t "$BACKEND_IMAGE" "$BACKEND_DIR"
    "$DOCKER_BIN" push "$BACKEND_IMAGE"

    local acr_username acr_password
    acr_username="$(az_exec acr credential show --name "$AZ_BACKEND_ACR_NAME" --query username -o tsv 2>/dev/null || true)"
    acr_password="$(az_exec acr credential show --name "$AZ_BACKEND_ACR_NAME" --query passwords[0].value -o tsv 2>/dev/null || true)"
    if [[ -z "$acr_username" || -z "$acr_password" ]]; then
      echo "ACR 관리자 자격증명을 읽지 못했습니다."
      echo "다음 명령으로 ACR admin user를 활성화하세요:"
      echo "az acr update -n $AZ_BACKEND_ACR_NAME --admin-enabled true"
      exit 1
    fi

    az_exec webapp config container set \
      --name "$AZ_BACKEND_APP" \
      --resource-group "$AZ_RG" \
      --container-image-name "$BACKEND_IMAGE" \
      --container-registry-url "https://${acr_login_server}" \
      --container-registry-user "$acr_username" \
      --container-registry-password "$acr_password" \
      --output none
  else
    if ! command -v zip >/dev/null 2>&1; then
      echo "zip이 필요합니다. brew install zip 등으로 설치하세요."
      exit 1
    fi

    echo "5) 백엔드 코드 패키지 배포(zip)"
    local pkg="$TMP_DIR/backend-deploy.zip"
    (
      cd "$BACKEND_DIR"
      zip -q -r "$pkg" . \
        -x ".venv/*" ".git/*" "__pycache__/*" "*.pyc" "*.DS_Store"
    )
    if ! az_exec webapp deploy \
      --resource-group "$AZ_RG" \
      --name "$AZ_BACKEND_APP" \
      --src-path "$pkg" \
      --type zip \
      --output none; then
      echo "webapp deploy 실패 -> config-zip으로 재시도"
      az_exec webapp deployment source config-zip \
        --resource-group "$AZ_RG" \
        --name "$AZ_BACKEND_APP" \
        --src "$pkg" \
        --output none
    fi
  fi

  az_exec webapp restart --name "$AZ_BACKEND_APP" --resource-group "$AZ_RG" --output none

  BACKEND_URL="$(ensure_backend_url_format "$(az_exec webapp show --resource-group "$AZ_RG" --name "$AZ_BACKEND_APP" --query defaultHostName -o tsv)")"
  wait_for_backend_health "$BACKEND_URL" 30 5
}

make_storage_name() {
  local prefix="$1"
  local suffix
  suffix="$(date +%s | tail -c 6)"
  local name="${prefix}${suffix}"
  if [[ ${#name} -gt 24 ]]; then
    name="${name:0:24}"
  fi
  echo "$name"
}

create_storage_account_if_missing() {
  local name="$1"
  if az_exec storage account show --name "$name" --resource-group "$AZ_RG" >/dev/null 2>&1; then
    return 0
  fi

  if az_exec storage account create \
      --name "$name" \
      --resource-group "$AZ_RG" \
      --location "$AZ_LOCATION" \
      --sku Standard_LRS \
      --kind StorageV2 \
      --https-only true \
      --output none; then
    return 0
  fi

  return 1
}

ensure_storage_provider_registered() {
  local reg_state
  reg_state="$(az_exec provider show --namespace Microsoft.Storage --query registrationState -o tsv 2>/dev/null || echo Unknown)"
  if [[ "$reg_state" != "Registered" && "$reg_state" != "Registering" ]]; then
    az_exec provider register --namespace Microsoft.Storage --output none
  fi
  return 0
}

deploy_frontend() {
  if [[ -z "${1:-}" ]]; then
    echo "프론트 배포에 사용할 백엔드 URL이 필요합니다."
    exit 1
  fi
  local backend_url
  backend_url="$(ensure_backend_url_format "$1")"

  local storage_account="$AZ_FRONT_STORAGE_ACCOUNT"
  if [[ -n "$storage_account" ]]; then
    if ! create_storage_account_if_missing "$storage_account"; then
      echo "지정한 스토리지 계정 생성/확인 실패: $storage_account"
      exit 1
    fi
  else
    ensure_storage_provider_registered
    for _ in {1..12}; do
      storage_account="$(make_storage_name "$AZ_FRONT_STORAGE_PREFIX")"
      if create_storage_account_if_missing "$storage_account"; then
        break
      fi
      storage_account=""
    done
  fi

  if [[ -z "$storage_account" ]]; then
    echo "스테틱 웹 스토리지 계정을 확보하지 못했습니다."
    exit 1
  fi

  echo "6) 스토리지 계정 확인/생성: $storage_account"
  az_exec storage account show --name "$storage_account" --resource-group "$AZ_RG" >/dev/null 2>&1 \
    || true

  az_exec storage blob service-properties update \
    --account-name "$storage_account" \
    --static-website \
    --index-document index.html \
    --404-document index.html \
    --output none

  local account_key
  account_key="$(az_exec storage account keys list --resource-group "$AZ_RG" --account-name "$storage_account" --query "[0].value" -o tsv)"
  local frontend_source="$TMP_DIR/frontend"
  rm -rf "$frontend_source"
  mkdir -p "$frontend_source"
  cp -R "$FRONTEND_DIR/." "$frontend_source"

  # 배포한 백엔드 주소를 자동으로 연결
  if command -v python3 >/dev/null 2>&1; then
    python3 - "$frontend_source/config.js" "$backend_url" "$(date -u +%s)" "$AZ_GOOGLE_MAPS_API_KEY" <<'PY'
import pathlib
import sys

path, backend_url, build_id, google_maps_api_key = sys.argv[1:]
p = pathlib.Path(path)
lines = p.read_text().splitlines()
result = []
updated_api = False
updated_build = False
updated_google_maps_key = False

for line in lines:
    if line.startswith("window.ENV_API_BASE"):
        result.append(f"window.ENV_API_BASE = '{backend_url}';")
        updated_api = True
        continue
    if line.startswith("window.ENV_BUILD_ID"):
        result.append(f"window.ENV_BUILD_ID = '{build_id}';")
        updated_build = True
        continue
    if line.startswith("window.ENV_GOOGLE_MAPS_API_KEY"):
        result.append(f"window.ENV_GOOGLE_MAPS_API_KEY = '{google_maps_api_key}';")
        updated_google_maps_key = True
        continue
    result.append(line)

if not updated_api:
    result.insert(0, f"window.ENV_API_BASE = '{backend_url}';")
if not updated_build:
    result.insert(1, f"window.ENV_BUILD_ID = '{build_id}';")
if not updated_google_maps_key:
    result.insert(2, f"window.ENV_GOOGLE_MAPS_API_KEY = '{google_maps_api_key}';")

p.write_text("\n".join(result) + "\n")
PY
  else
    cat <<EOF > "$frontend_source/config.js"
window.ENV_API_BASE = '${backend_url}';
window.ENV_BUILD_ID = '$(date -u +%s)';
window.ENV_GOOGLE_MAPS_API_KEY = '${AZ_GOOGLE_MAPS_API_KEY}';
EOF
  fi

  az_exec storage blob upload-batch \
    --account-name "$storage_account" \
    --account-key "$account_key" \
    --destination '$web' \
    --source "$frontend_source" \
    --overwrite \
    --output none

  FRONTEND_URL="$(az_exec storage account show --name "$storage_account" --resource-group "$AZ_RG" --query primaryEndpoints.web -o tsv | sed 's#/$##')"

  echo "7) 백엔드 CORS에 프론트 엔드포인트 등록"
  local existing_cors
  existing_cors="$(az_exec webapp config appsettings list --name "$AZ_BACKEND_APP" --resource-group "$AZ_RG" --query "[?name=='CORS_ORIGINS'].value | [0]" -o tsv 2>/dev/null | clean_ws || true)"

  local merged_cors="$AZ_CORS_ORIGINS"
  if [[ -z "$merged_cors" ]]; then
    if [[ -n "$existing_cors" && "$existing_cors" != "None" ]]; then
      merged_cors="$existing_cors"
    else
      merged_cors="http://localhost:5173,http://127.0.0.1:5173,http://localhost:${AZ_BACKEND_PORT},http://127.0.0.1:${AZ_BACKEND_PORT},https://${AZ_BACKEND_APP}.azurewebsites.net"
    fi
  fi

  if ! contains_csv_value "$merged_cors" "$FRONTEND_URL"; then
    merged_cors="${merged_cors},$FRONTEND_URL"
  fi

  if [[ "$merged_cors" != *"${AZ_BACKEND_APP}.azurewebsites.net"* ]]; then
    if [[ -n "$merged_cors" ]]; then
      merged_cors="${merged_cors},https://rg-arls-backend.azurewebsites.net"
    else
      merged_cors="https://rg-arls-backend.azurewebsites.net"
    fi
  fi
  
  if [[ "$merged_cors" == "$existing_cors" ]]; then
    echo "CORS_ORIGINS 변경 없음 (백엔드 재시작 생략)"
  else
    az_exec webapp config appsettings set --name "$AZ_BACKEND_APP" --resource-group "$AZ_RG" --output none --settings \
      CORS_ORIGINS="$merged_cors"
  fi
}

BACKEND_URL=""
FRONTEND_URL=""
BACKEND_IMAGE=""

if [[ "$MODE" == "backend" ]]; then
  deploy_backend
  echo
  echo "백엔드 배포 완료"
  echo "BACKEND_DEPLOY_MODE=$AZ_BACKEND_DEPLOY_MODE"
  if [[ -n "$BACKEND_IMAGE" ]]; then
    echo "BACKEND_IMAGE=$BACKEND_IMAGE"
  fi
  echo "BACKEND_URL=$BACKEND_URL"
  echo
  echo "다음으로 프론트 배포: ./scripts/deploy-azure.sh --frontend-only --backend-url \"$BACKEND_URL\""
  exit 0
fi

if [[ "$MODE" == "frontend" ]]; then
  if [[ -n "$CLI_BACKEND_URL" ]]; then
    DEP_BACKEND_URL="$CLI_BACKEND_URL"
  else
    DEP_BACKEND_URL="${AZ_BACKEND_URL:-}"
  fi

  if [[ -z "$DEP_BACKEND_URL" ]]; then
    echo "프론트 배포에는 --backend-url 또는 AZ_BACKEND_URL가 필요합니다."
    exit 1
  fi

  deploy_frontend "$DEP_BACKEND_URL"
  echo
  echo "프론트 배포 완료"
  echo "FRONTEND_URL=$FRONTEND_URL"
  echo "접속 URL: ${FRONTEND_URL}/?api=${DEP_BACKEND_URL%/}"
  exit 0
fi

deploy_backend
deploy_frontend "$BACKEND_URL"

echo
echo "배포 완료"
echo "백엔드 배포 모드: $AZ_BACKEND_DEPLOY_MODE"
if [[ -n "$BACKEND_IMAGE" ]]; then
  echo "백엔드 이미지: $BACKEND_IMAGE"
fi
echo "백엔드: $BACKEND_URL"
echo "프론트: $FRONTEND_URL"
echo "접속 URL: ${FRONTEND_URL}/?api=${BACKEND_URL}"
echo
echo "헬스 체크:"
curl -fsS "${BACKEND_URL}/health" || true
echo
echo "로그인 테스트:"
echo "curl -s -X POST ${BACKEND_URL}/api/v1/auth/login ... (본문은 README 참고)"
