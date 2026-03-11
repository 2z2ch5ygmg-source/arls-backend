# Repo Structure

This workspace is currently centered on the ARLS backend repository root.

Primary runtime files live at the root:

- `app/` for the FastAPI application
- `migrations/` for database bootstrap/migrations
- `Dockerfile` and `requirements.txt` for container/runtime build

Companion local files may also exist here:

- `ios/` for the iOS wrapper workspace
- local logs, caches, and helper scripts

## Remotes

- `backend-origin`: backend-only GitHub repository
  - URL: `https://github.com/2z2ch5ygmg-source/arls-backend`

There is currently no separate remote configured for a larger integrated workspace.

## Sync Rules

- Work from the repository root.
- Azure deployment is based on the repository root and the root `Dockerfile`.
- If you need to republish this workspace into the backend-only GitHub repository, run:

```bash
./scripts/publish-backend-origin.sh
```

That script:

- clones `backend-origin` `main` to a temp directory
- replaces its contents with the backend runtime files from the current workspace
- removes cache files
- commits and pushes only if there are real changes

## Current State

- Active backend remote: `backend-origin`
- Azure App Service image currently points to `acrsecurityopsprod001-eneccucxdcfedqhm.azurecr.io/rg-arls-backend`
