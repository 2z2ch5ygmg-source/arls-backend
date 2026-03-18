const { expect, test } = require('@playwright/test');

const arlsBaseUrl =
  process.env.QA_ARLS_BASE_URL ||
  'https://rgarlsfront50018.z12.web.core.windows.net/?api=https://rg-arls-backend.azurewebsites.net';
const arlsApiBase =
  process.env.QA_ARLS_API_BASE || 'https://rg-arls-backend.azurewebsites.net';

test.describe('ARLS QA @arls @smoke', () => {
  test('ARLS frontend loads and renders', async ({ page }) => {
    await page.goto(arlsBaseUrl);
    await page.waitForLoadState('domcontentloaded');
    const pageText = (await page.locator('body').innerText()).trim();
    expect(pageText.length).toBeGreaterThan(0);
  });

  test('ARLS health endpoint returns ok', async ({ request }) => {
    const health = await request.get(`${arlsApiBase}/health`);
    expect(health.ok()).toBeTruthy();
    const payload = await health.json();
    expect(payload).toHaveProperty('status');
  });
});
