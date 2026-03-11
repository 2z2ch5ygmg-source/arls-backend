# Repo Structure

ARLS의 현재 작업 루트는 백엔드와 프런트를 함께 포함합니다.

## Primary Paths

- `app/`: FastAPI backend
- `migrations/`: SQL bootstrap/migrations
- `frontend/`: static PWA frontend
- `scripts/auto-deploy-hr.sh`: 표준 원클릭 배포 엔트리
- `scripts/deploy-azure.sh`: Azure backend/frontend 배포 구현
- `Dockerfile`, `requirements.txt`: backend container/runtime build

## Deployment Model

- 기본 배포는 GitHub Actions가 아니라 로컬 shell script 기준입니다.
- `auto-deploy-hr.sh`가 commit/push 시도를 한 뒤 `deploy-azure.sh`를 호출합니다.
- `deploy-azure.sh`는 현재 저장소 구조를 감지해 루트 backend 또는 `backend/` 하위 구조 둘 다 처리합니다.

## Remotes

- `backend-origin`: backend-only GitHub repository
  - URL: `https://github.com/2z2ch5ygmg-source/arls-backend`

현재 작업본에는 `origin`이 없어도 스크립트가 `backend-origin`으로 fallback 하도록 맞춰져 있습니다.

## Current State

- Backend Azure App Service: `rg-arls-backend`
- Frontend Azure static website: `rgarlsfront50018`
- Standard deploy entry:

```bash
bash ./scripts/auto-deploy-hr.sh
```
