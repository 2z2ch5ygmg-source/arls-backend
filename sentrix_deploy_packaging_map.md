# Sentrix Deploy Packaging Map

## Executive Summary

- Backend and frontend are deployed separately.
- The backend app does not serve the frontend bundle.
- The frontend bundle is rewritten during deploy with a backend URL and build ID, then uploaded to Azure static website storage.
- A service worker caches the shell assets, so frontend/backend skew is a real regression risk.
- The auto-deploy helper can commit and ship unrelated repo changes because it stages everything.

## 1. Backend Runtime Package

### Container build
- `Dockerfile`

What it does:
- installs Python dependencies
- installs LibreOffice and Noto CJK fonts
- `COPY . .`
- runs `uvicorn app.main:app`

Why it is sensitive:
- The whole repo is copied into the backend image, even though the backend does not serve the static frontend.
- A backend build artifact can therefore capture unrelated frontend changes from the same worktree.

### FastAPI runtime
- `app/main.py`

Relevant behavior:
- includes backend routers under `/api/v1`
- `/health` returns `{"status":"ok"}`
- `/` returns `{"message":"RG ARLS API"}`
- no static-file mounting for `frontend/`

Why it matters:
- Frontend and backend versioning are operationally separate even though they live in one repo.

## 2. Frontend Static Packaging

### Deploy script
- `scripts/deploy-azure.sh`

Key behavior:
- `deploy_backend` and `deploy_frontend` are separate flows
- frontend files are copied to a temp directory
- `frontend/config.js` is rewritten with:
  - backend URL
  - build ID
  - Google Maps key
- temp frontend is uploaded to Azure Blob static website storage
- backend `CORS_ORIGINS` is then updated to include the frontend URL

### Runtime frontend config
- `frontend/config.js`
  - `window.ENV_API_BASE`
  - `window.ENV_BUILD_ID`

### Service worker cache
- `frontend/sw.js`
  - caches:
    - `index.html`
    - `config.js`
    - `manifest.json`
    - `css/styles.css`
    - `js/app.js`

### PWA manifest
- `frontend/manifest.json`
  - `start_url` contains a backend URL query parameter

## 3. Build Version Injection

### Backend image version
- `scripts/deploy-azure.sh`
  - `AZ_BACKEND_IMAGE_TAG` defaults to `v$(date -u +%y%m%d-%H%M%S)`

### Frontend build version
- `scripts/deploy-azure.sh`
  - rewrites `window.ENV_BUILD_ID` with `date -u +%s`
- `frontend/sw.js`
  - hardcodes `SW_VERSION = 'rg-arls-sw-v1773534899'` in the checked-in file

### Why this is sensitive
- Backend image tags and frontend build IDs are not one shared release unit.
- A backend deploy does not automatically update static frontend assets.
- A frontend deploy can update `config.js` and cached shell state independently from backend code.

## 4. Routes and CORS Coupling

### Backend CORS setup
- `app/main.py`
  - defaults include the Azure static frontend origin and the backend app origin
- `scripts/deploy-azure.sh`
  - merges the actual static website URL into backend `CORS_ORIGINS`

### Why this is sensitive
- The working frontend URL is not fixed until deployment completes.
- Deploy order matters.
- Manual or partial deploys can leave the backend without the current frontend origin or vice versa.

## 5. Regression-Prone Coupling Points

### “Backend fix rolls UI back” risks

1. `scripts/auto-deploy-hr.sh`
   - runs `git add .`
   - commits every current repo change
   - then deploys
   - result: unrelated UI edits can ship with a backend deploy

2. `Dockerfile`
   - backend image includes the full repo
   - source-level coupling remains even though runtime serving is separate

3. `frontend/sw.js`
   - caches `index.html`, `config.js`, and `js/app.js`
   - stale service-worker state can keep old UI even when backend changed

4. `frontend/config.js`
   - backend URL and build ID are deploy-time mutations, not source-of-truth code-only values

5. `scripts/publish-backend-origin.sh`
   - publishes backend paths only
   - omits frontend files entirely
   - a backend-only mirror or review branch can diverge from the live SPA

## 6. Deployment Modes

### Container mode
- builds and pushes Docker image to ACR
- configures App Service container image

### Zip mode
- zips the repo root contents except ignored paths
- deploys via `az webapp deploy` or `config-zip`

### Why both are sensitive
- Container and zip deployments package slightly different runtime assumptions.
- Both use the integrated repo root.
- Neither gives a single immutable backend+frontend release artifact.

## 7. Exact Sensitive Files

### Highest sensitivity
- `Dockerfile`
- `app/main.py`
- `app/config.py`
- `scripts/deploy-azure.sh`
- `scripts/auto-deploy-hr.sh`
- `scripts/publish-backend-origin.sh`
- `frontend/config.js`
- `frontend/sw.js`
- `frontend/manifest.json`

## 8. Bottom Line

- The deploy model is not a single release unit.
- Backend, frontend, cache versioning, runtime config injection, and repo-wide auto-commit behavior all create real regression surface.
- This is the main place where “small backend fix, surprising UI regression” can happen.
