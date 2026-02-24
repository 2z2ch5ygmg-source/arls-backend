# arls-backend

## Deployment policy
- Azure Web App `rg-arls-backend` is deployed by GitHub Actions only.
- Trigger branch is fixed to `main`.
- Local zip deploy/manual Azure CLI deploy is not the standard path.

## Workflow
- File: `.github/workflows/azure-webapp.yml`
- Trigger: `push` to `main`
- Action: `azure/webapps-deploy@v3`

## Required GitHub secret
- Name: `AZURE_WEBAPP_PUBLISH_PROFILE`
- Value: full XML content from Azure Web App publish profile

## Azure setup checklist
1. Azure Portal > `rg-arls-backend` > Deployment Center: set source to GitHub repository `arls-backend`, branch `main`.
2. Azure Portal > `rg-arls-backend` > Get publish profile: download XML.
3. GitHub > repository `arls-backend` > Settings > Secrets and variables > Actions:
   add `AZURE_WEBAPP_PUBLISH_PROFILE`.

## QA
1. Commit and push to `main`.
2. Confirm workflow `Build and deploy arls-backend` succeeds.
3. Confirm `https://rg-arls-backend.azurewebsites.net/health` returns 200.
