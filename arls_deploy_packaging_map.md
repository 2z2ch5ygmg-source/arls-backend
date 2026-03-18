# ARLS Deploy / Packaging Map

## Active Runtime Shape

- Backend runtime root: repository root
  - `Dockerfile`
  - `app/`
  - `migrations/`
  - `requirements.txt`
- Frontend runtime root: `frontend/`
  - static HTML/CSS/JS
  - no bundler build pipeline
- Mobile shell / packaging residue
  - `capacitor.config.json`
  - `ios/`

## F. Deployment / Packaging

## 1. Docker / Backend Packaging

### Active Dockerfile

- `Dockerfile`
  - base image: `python:3.12-slim`
  - installs `libreoffice-writer` and `fonts-noto-cjk`
  - installs `requirements.txt`
  - copies entire repo
  - runs `uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}`

### Backend runtime coupling

- Startup target is hard-coded to `app.main:app`
- Therefore repository-root `app/` is the authoritative backend package, not `backend/app`

## 2. Frontend Packaging

### Static frontend

- `frontend/index.html`
- `frontend/js/app.js`
- `frontend/css/styles.css`
- `frontend/config.js`
- `frontend/manifest.json`
- `frontend/sw.js`

### Deployment model

- `scripts/deploy-azure.sh` copies `frontend/` directly into a temp directory
- The script rewrites `frontend/config.js` with:
  - backend API base URL
  - `ENV_BUILD_ID`
  - Google Maps key
- Upload target is Azure Storage static website (`$web`)

### No build step

- `package.json` has no real frontend build script
- Frontend deploy regressions are therefore mostly raw-file copy/config rewrite regressions

## 3. Build Scripts

### Primary deploy implementation

- `scripts/deploy-azure.sh`
  - resolves backend dir by preferring repository root when `Dockerfile` + `app/` exist
  - still supports `backend/` fallback
  - supports backend deploy mode:
    - `container`
    - `zip`
  - also deploys frontend static site and updates backend CORS

### One-click wrapper

- `scripts/auto-deploy-hr.sh`
  - calls `attempt_git_push`
  - then invokes `deploy-azure.sh`

### Backend-origin sync path

- `scripts/publish-backend-origin.sh`
  - syncs backend subset into a separate `backend-origin` repository
  - still supports both root-layout and `backend/`-subdir layout

## 4. Image Tagging / Version Coupling

### Backend image versioning

- `scripts/deploy-azure.sh`
  - default image tag: `v$(date -u +%y%m%d-%H%M%S)`
- This is timestamp-based, not git-SHA-based

### Frontend versioning

- `frontend/config.js`
  - `window.ENV_BUILD_ID`
- Deployment script rewrites the build id at publish time

### Runtime cross-coupling

- Frontend is configured with backend URL during deploy, not during build
- Backend CORS origins are also rewritten by deploy script
- That makes deploy-time config mutation a major regression vector

## 5. Deployment Targets / Runtime Config

### Key files

- `app/config.py`
- `frontend/config.js`
- `capacitor.config.json`
- `README.md`
- `REPO_STRUCTURE.md`

### Capacitor/mobile coupling

- `capacitor.config.json`
  - `webDir = "frontend"`
  - server URL points to deployed Azure static website

## 6. Where Regressions Can Happen

### Backend packaging drift

- `scripts/deploy-azure.sh` still supports:
  - root layout
  - `backend/` subdir layout
- This creates ambiguity over what is authoritative during manual/hotfix deploys

### Frontend config rewrite drift

- `frontend/config.js` is mutated during deploy
- A stale/mismatched API base or build id can be published without any compile step catching it

### Auto-commit deploy risk

- `scripts/auto-deploy-hr.sh`
  - runs `git add .`
  - commits all dirty changes
  - pushes before deploy
- This is a high-risk path for accidental unreviewed code and doc changes reaching production

### Root vs backend-origin sync divergence

- `scripts/publish-backend-origin.sh` exists because deployment/source distribution still assumes a backend-only publishing model in some cases

### Runtime schema repair masking migration issues

- `app/db.py`
  - silently applies repair SQL for missing columns/constraints
- Helpful operationally, but it can hide migration drift until later

## Exact Files / Scripts

- `Dockerfile`
- `requirements.txt`
- `scripts/deploy-azure.sh`
- `scripts/auto-deploy-hr.sh`
- `scripts/publish-backend-origin.sh`
- `frontend/config.js`
- `capacitor.config.json`
- `package.json`
- `app/main.py`
- `app/config.py`
- `app/db.py`
- `README.md`
- `REPO_STRUCTURE.md`

## Architecture Review Notes

- ARLS deployment is script-driven and mutable at publish time.
- The most important packaging fact is that the active app lives at repository root, but deployment tooling still carries compatibility logic for a `backend/` sub-layout.
- The most dangerous deploy-time regression point is `auto-deploy-hr.sh`, not the Dockerfile itself.
