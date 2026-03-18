# ARLS + Sentrix QA Kit

This folder runs browser smoke checks for both systems with Playwright.

## Quick start

```bash
cd qa
npm install
npm run install:browsers
npm run smoke
```

## One-command runs

- `npm run arls`: run only ARLS smoke tests
- `npm run sentrix`: run only Sentrix smoke tests
- `npm run all`: run all ARLS + Sentrix tests
- `npm run smoke`: run only tests tagged `@smoke`
- `npm run arls:auth`: run ARLS auth/API smoke checks
- `npm run sentrix:auth`: run Sentrix auth/API smoke checks

## Environment

- `QA_ARLS_BASE_URL`: ARLS frontend URL
- `QA_ARLS_API_BASE`: ARLS API base URL for health check
- `QA_SENTRIX_BASE_URL`: Sentrix frontend and health base URL
- `QA_SENTRIX_WORKSPACE_PATH`: optional hash route for a login-less entry view
- `QA_ARLS_TENANT_CODE`, `QA_ARLS_USERNAME`, `QA_ARLS_PASSWORD`: credentials for optional authenticated ARLS checks
- `QA_ARLS_SITE_CODE`, `QA_ARLS_MONTH`: optional filters for ARLS workspace query checks
- `QA_SENTRIX_API_BASE`: Sentrix API base URL (optional if API checks are enabled)
- `QA_SENTRIX_AUTH_TOKEN`, `QA_SENTRIX_TOKEN`: optional bearer token for Sentrix API checks
- `QA_SENTRIX_SITE_CODE`, `QA_SENTRIX_TENANT_CODE`, `QA_SENTRIX_MONTH`: optional filters for Sentrix workspace API checks

No credentials are required for baseline smoke checks.
