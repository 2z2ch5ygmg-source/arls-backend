# arls-backend

## Deployment policy
- Azure Web App `rg-arls-backend` is deployed by GitHub Actions only.
- Trigger branch is fixed to `main`.
- Local zip deploy/manual Azure CLI deploy is not the standard path.

## Workflow
- File: `.github/workflows/azure-webapp.yml`
- Trigger: `push` to `main`
- Actions: `azure/login@v2` (OIDC) + `azure/webapps-deploy@v3`

## Required GitHub secrets (OIDC)
- `AZUREAPPSERVICE_CLIENTID_2D0BAD1277E54D68AB1AEE8365610001`
- `AZUREAPPSERVICE_TENANTID_6AFAB1BB33A243268F5F062CEB3B4BDB`
- `AZUREAPPSERVICE_SUBSCRIPTIONID_5430C5FDF1CF4649BA67C8ACAD76CE82`

## Optional secret
- `AZURE_WEBAPP_PUBLISH_PROFILE` (kept for troubleshooting only, not required by current workflow)

## Azure setup checklist
1. Azure Portal > `rg-arls-backend` > Deployment Center: set source to GitHub repository `arls-backend`, branch `main`.
2. Azure Portal > `rg-arls-backend` > Deployment Center: enable GitHub Actions (OIDC).
3. GitHub > repository `arls-backend` > Settings > Secrets and variables > Actions:
   confirm the 3 OIDC secrets above are present.

## QA
1. Commit and push to `main`.
2. Confirm workflow `Build and deploy arls-backend` succeeds.
3. Confirm `https://rg-arls-backend.azurewebsites.net/health` returns 200.
