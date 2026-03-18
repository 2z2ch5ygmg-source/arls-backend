// @ts-check
const { devices } = require('@playwright/test');

/**
 * @type {import('@playwright/test').PlaywrightTestConfig}
 */
const arlsBaseUrl = process.env.QA_ARLS_BASE_URL || 'https://rgarlsfront50018.z12.web.core.windows.net/?api=https://rg-arls-backend.azurewebsites.net';
const sentrixBaseUrl = process.env.QA_SENTRIX_BASE_URL || 'https://security-ops-center-prod-002-260227135557.azurewebsites.net';

module.exports = {
  testDir: './tests',
  timeout: 90_000,
  retries: 1,
  reporter: [
    ['list'],
    ['html', { open: 'never', outputFolder: 'playwright-report' }]
  ],
  outputDir: 'test-results',
  use: {
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    headless: true,
    viewport: { width: 1440, height: 920 },
    ignoreHTTPSErrors: true,
    ...devices['Desktop Chrome'],
  },
  projects: [
    {
      name: 'arls',
      use: {
        baseURL: arlsBaseUrl,
      },
    },
    {
      name: 'sentrix',
      use: {
        baseURL: sentrixBaseUrl,
      },
    },
  ],
};
