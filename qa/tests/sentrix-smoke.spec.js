const { expect, test } = require('@playwright/test');

const sentrixBaseUrl =
  process.env.QA_SENTRIX_BASE_URL ||
  'https://security-ops-center-prod-002-260227135557.azurewebsites.net';
const sentrixWorkspacePath =
  process.env.QA_SENTRIX_WORKSPACE_PATH || '/#/ops/support-workers';

test.describe('Sentrix QA @sentrix @smoke', () => {
  test('Sentrix frontend route loads', async ({ page }) => {
    await page.goto(`${sentrixBaseUrl}${sentrixWorkspacePath}`);
    await page.waitForLoadState('domcontentloaded');
    const pageText = (await page.locator('body').innerText()).trim();
    expect(pageText.length).toBeGreaterThan(0);
  });

  test('Sentrix health endpoint returns ok', async ({ request }) => {
    const health = await request.get(`${sentrixBaseUrl}/health`);
    expect(health.ok()).toBeTruthy();
    const payload = await health.json();
    expect(payload).toHaveProperty('status');
  });
});
