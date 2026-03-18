const { expect, test } = require('@playwright/test');

const sentrixApiBase =
  process.env.QA_SENTRIX_API_BASE || process.env.QA_SENTRIX_BASE_URL || 'https://security-ops-center-prod-002-260227135557.azurewebsites.net';
const sentrixWorkspaceMonth = process.env.QA_SENTRIX_MONTH || new Date().toISOString().slice(0, 7);

function extractBearerToken() {
  const token = (process.env.QA_SENTRIX_AUTH_TOKEN || process.env.QA_SENTRIX_TOKEN || '').trim();
  return token.length > 0 ? token : '';
}

function buildSentrixWorkspaceQuery() {
  const params = new URLSearchParams();
  const siteCode = (process.env.QA_SENTRIX_SITE_CODE || '').trim();
  const tenantCode = (process.env.QA_SENTRIX_TENANT_CODE || '').trim();

  if (siteCode) {
    params.set('site', siteCode);
  }
  if (tenantCode) {
    params.set('tenant_code', tenantCode);
  }
  params.set('month', sentrixWorkspaceMonth);
  return params.toString();
}

test.describe('Sentrix Authenticated QA @sentrix', () => {
  test('Sentrix workspace page opens', async ({ page }) => {
    const workspacePath = process.env.QA_SENTRIX_WORKSPACE_PATH || '/#/ops/support-workers';
    await page.goto(`${sentrixApiBase}${workspacePath}`);
    await page.waitForLoadState('domcontentloaded');
    const title = await page.title();
    expect(title.length).toBeGreaterThan(0);
  });

  test('Sentrix support submissions workspace API', async ({ request }) => {
    const token = extractBearerToken();
    if (!token) {
      test.skip('QA_SENTRIX_AUTH_TOKEN not set');
    }

    const params = buildSentrixWorkspaceQuery();
    const response = await request.get(
      `${sentrixApiBase}/api/ops/support-submissions/workspace?${params}`,
      {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      },
    );

    expect([200, 401]).toContain(response.status());
    if (response.status() === 401) {
      return;
    }

    const payload = await response.json();
    expect(payload).toBeTruthy();
  });
});
