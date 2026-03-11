# RG ARLS

ARLS는 FastAPI 백엔드와 정적 PWA 프런트를 함께 두는 작업본입니다.

## Current Layout

- `app/`: FastAPI application
- `migrations/`: bootstrap and migration SQL
- `frontend/`: static PWA frontend
- `Dockerfile`, `requirements.txt`: backend container/runtime
- `scripts/auto-deploy-hr.sh`: one-click deploy entry
- `scripts/deploy-azure.sh`: Azure backend/frontend deploy script

## Deployment Policy

표준 배포 경로는 GitHub Actions가 아니라 로컬 shell script입니다.

- 전체 배포: `bash ./scripts/auto-deploy-hr.sh`
- 프런트만 배포: `bash ./scripts/auto-deploy-hr.sh --frontend-only --backend-url https://rg-arls-backend.azurewebsites.net`
- 백엔드만 배포: `bash ./scripts/deploy-azure.sh --backend-only --backend-deploy container`

배포 전에 필요한 것:

- `az login`
- `docker login` 또는 `az acr login`
- `.env` 또는 환경변수에 Azure/DB 값 설정

## Notes

- 현재 저장소는 `origin`이 아닌 `backend-origin`만 있어도 배포 스크립트가 동작하도록 맞춰져 있습니다.
- 현재 루트 구조는 `app/`와 `Dockerfile`이 저장소 루트에 있으므로, 배포 스크립트도 이 구조를 자동 감지합니다.
- 프런트는 Azure Storage static website로 배포되며 기본 URL은 `https://rgarlsfront50018.z12.web.core.windows.net`입니다.

## Health Check

- Backend: `https://rg-arls-backend.azurewebsites.net/health`
- Frontend: `https://rgarlsfront50018.z12.web.core.windows.net/?api=https://rg-arls-backend.azurewebsites.net`
