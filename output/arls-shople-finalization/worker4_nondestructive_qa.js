const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

const OUT_DIR = path.resolve('output/arls-shople-finalization/worker4-live-nondestructive');
const FRONT = process.env.ARLS_FRONTEND_URL || 'https://rgarlsfront50018.z12.web.core.windows.net/?api=https://rg-arls-backend.azurewebsites.net';
const API = process.env.ARLS_API_URL || 'https://rg-arls-backend.azurewebsites.net/api/v1';
const LOGIN_TENANT = process.env.INIT_SUPER_ADMIN_TENANT_CODE || process.env.LOGIN_TENANT || 'MASTER';
const LOGIN_USER = process.env.INIT_SUPER_ADMIN_USERNAME || process.env.LOGIN_USER || 'platform_admin';
const LOGIN_PASSWORD = process.env.INIT_SUPER_ADMIN_PASSWORD || process.env.LOGIN_PASSWORD;
if (!LOGIN_PASSWORD) throw new Error('Set INIT_SUPER_ADMIN_PASSWORD or LOGIN_PASSWORD');

fs.mkdirSync(OUT_DIR, { recursive: true });

function sanitizeUrl(rawUrl) {
  try {
    const url = new URL(rawUrl);
    if (url.searchParams.has('api')) url.searchParams.set('api', '<api>');
    return url.toString();
  } catch {
    return String(rawUrl || '');
  }
}

async function login() {
  const response = await fetch(`${API}/auth/login`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      tenant_code: LOGIN_TENANT,
      username: LOGIN_USER,
      password: LOGIN_PASSWORD,
    }),
  });
  const payload = await response.json().catch(() => ({}));
  const data = payload?.data && typeof payload.data === 'object' ? payload.data : payload;
  if (!response.ok || !data?.access_token || !data?.user) {
    throw new Error(`login failed ${response.status}: ${JSON.stringify(payload).slice(0, 500)}`);
  }
  return data;
}

function screenshotPath(name) {
  return path.join(OUT_DIR, `${name}.png`);
}

async function waitForRoute(page, hash, selector) {
  await page.evaluate((nextHash) => { location.hash = nextHash; }, hash);
  await page.locator(selector || '#shell').first().waitFor({ state: 'visible', timeout: 45000 });
  await page.waitForTimeout(2500);
}

async function countVisible(page, selector) {
  return page.locator(selector).evaluateAll((nodes) => nodes.filter((node) => {
    if (!(node instanceof HTMLElement)) return false;
    const rect = node.getBoundingClientRect();
    const style = getComputedStyle(node);
    return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
  }).length).catch(() => 0);
}

async function pageSnapshot(page) {
  return page.evaluate(() => {
    const visibleView = document.querySelector('.view:not(.hidden)');
    const appSheet = document.querySelector('#appSheet');
    return {
      hash: location.hash,
      view: window.state?.currentView || '',
      title: visibleView?.querySelector('h1,h2,h3')?.textContent?.trim() || '',
      overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
      sheetOpen: Boolean(appSheet && !appSheet.classList.contains('hidden')),
      sheetTitle: appSheet?.querySelector('.sheet-title, h2, h3')?.textContent?.trim() || '',
      textSample: visibleView?.textContent?.replace(/\s+/g, ' ').trim().slice(0, 800) || '',
    };
  });
}

async function clickFirstVisible(page, selector) {
  return page.locator(selector).evaluateAll((nodes) => {
    const node = nodes.find((candidate) => {
      if (!(candidate instanceof HTMLElement)) return false;
      const rect = candidate.getBoundingClientRect();
      const style = getComputedStyle(candidate);
      return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
    });
    if (!node) return false;
    node.scrollIntoView({ block: 'center', inline: 'center' });
    node.click();
    return true;
  });
}

(async () => {
  const session = await login();
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  await context.addInitScript((seed) => {
    localStorage.setItem('accessToken', seed.token);
    localStorage.setItem('refreshToken', seed.refreshToken);
    localStorage.setItem('rg-arls-session', JSON.stringify({ token: seed.token, refreshToken: seed.refreshToken, user: seed.user }));
    localStorage.setItem('rg-arls-ui-active-tenant', 'MASTER');
    localStorage.setItem('rg-arls-working-tenant-code', 'SRS_KOREA');
    localStorage.setItem('rg-arls-runtime-bypass-password-gate', '1');
  }, { token: session.access_token, refreshToken: session.refresh_token || '', user: session.user });

  const page = await context.newPage();
  const consoleErrors = [];
  const failedRequests = [];
  const httpApiErrors = [];
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push({ text: message.text(), location: message.location() });
  });
  page.on('requestfailed', (request) => failedRequests.push({ method: request.method(), url: sanitizeUrl(request.url()), failure: request.failure()?.errorText || '' }));
  page.on('response', (response) => {
    const url = response.url();
    if (url.includes('/api/v1/') && response.status() >= 400) {
      httpApiErrors.push({ status: response.status(), url: sanitizeUrl(url) });
    }
  });

  await page.goto(`${FRONT}&worker4=${Date.now()}#/home`, { waitUntil: 'domcontentloaded', timeout: 45000 });
  await page.waitForFunction(() => {
    const shell = document.querySelector('#shell');
    return shell && !shell.classList.contains('hidden');
  }, { timeout: 45000 });
  await page.waitForTimeout(1200);
  consoleErrors.length = 0;
  failedRequests.length = 0;
  httpApiErrors.length = 0;

  const checks = [];

  // Employee row detail: read-only row open. Does not use edit/delete actions.
  await waitForRoute(page, '#/branch/employees', '#view-employees:not(.hidden)');
  const employeeRows = await countVisible(page, '#employeeDesktopTableBody .employee-directory-row, .employee-directory-card[data-action="employee-open-detail"]');
  let employeeClicked = false;
  if (employeeRows > 0) {
    employeeClicked = await clickFirstVisible(page, '#employeeDesktopTableBody .employee-directory-row, .employee-directory-card[data-action="employee-open-detail"]');
    await page.waitForFunction(() => {
      const body = document.querySelector('#employeeDirectoryDetailBody');
      const text = body?.textContent || '';
      return text && !text.includes('불러오는 중');
    }, { timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(700);
  }
  const employeeShot = screenshotPath('employee-row-detail');
  await page.screenshot({ path: employeeShot, fullPage: true });
  checks.push({
    name: 'employee-row-detail',
    route: '#/branch/employees',
    count: employeeRows,
    clicked: employeeClicked,
    screenshot: employeeShot,
    after: await page.evaluate(() => ({
      ...(() => {
        const panel = document.querySelector('#employeeDirectoryDetailPanel');
        const body = document.querySelector('#employeeDirectoryDetailBody');
        return {
          detailEmployeeId: window.state?.employeeAdmin?.detailEmployeeId || '',
          drawerOpen: Boolean(window.state?.employeeAdmin?.detailDrawerOpen),
          panelVisible: Boolean(panel && !panel.classList.contains('hidden')),
          detailText: body?.textContent?.replace(/\s+/g, ' ').trim().slice(0, 500) || '',
        };
      })(),
      overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth,
    })),
  });

  // Site row detail: read-only row open. Does not use edit/create actions.
  await waitForRoute(page, '#/branch/sites', '#view-org:not(.hidden)');
  const siteRows = await countVisible(page, '#siteDesktopTableBody .site-directory-row, .site-directory-card[data-action="site-open-detail"]');
  let siteClicked = false;
  if (siteRows > 0) {
    siteClicked = await clickFirstVisible(page, '#siteDesktopTableBody .site-directory-row, .site-directory-card[data-action="site-open-detail"]');
    await page.waitForTimeout(1500);
  }
  const siteShot = screenshotPath('site-row-detail');
  await page.screenshot({ path: siteShot, fullPage: true });
  checks.push({
    name: 'site-row-detail',
    route: '#/branch/sites',
    count: siteRows,
    clicked: siteClicked,
    screenshot: siteShot,
    after: await page.evaluate(() => {
      const panel = document.querySelector('#siteDirectoryDetailPanel');
      return {
        detailId: window.state?.siteDirectoryDetailId || '',
        panelVisible: Boolean(panel && !panel.classList.contains('hidden')),
        detailText: panel?.textContent?.replace(/\s+/g, ' ').trim().slice(0, 500) || '',
        overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth,
      };
    }),
  });

  // Notices detail, only if rows exist; no edit/delete/publish.
  await waitForRoute(page, '#/feature/notices', '#view-notices:not(.hidden)');
  const noticeDetailRows = await countVisible(page, '[data-action="notices-open-detail"]');
  let noticeDetailClicked = false;
  if (noticeDetailRows > 0) {
    noticeDetailClicked = await clickFirstVisible(page, '[data-action="notices-open-detail"]');
    await page.waitForTimeout(2200);
  }
  const noticeDetailShot = screenshotPath('notice-detail-row');
  await page.screenshot({ path: noticeDetailShot, fullPage: true });
  checks.push({
    name: 'notice-detail-row',
    route: '#/feature/notices',
    count: noticeDetailRows,
    clicked: noticeDetailClicked,
    screenshot: noticeDetailShot,
    after: await page.evaluate(() => {
      const panel = document.querySelector('#noticesDetailPanel');
      return {
        mode: window.state?.notices?.mode || '',
        selectedNoticeId: window.state?.notices?.selectedNoticeId || '',
        detailVisible: Boolean(panel && !panel.classList.contains('hidden')),
        detailText: panel?.textContent?.replace(/\s+/g, ' ').trim().slice(0, 500) || '',
        overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth,
      };
    }),
  });

  // Notices compose open only; no publish or draft mutation beyond opening the editor.
  await waitForRoute(page, '#/feature/notices', '#view-notices:not(.hidden)');
  const composeButtons = await countVisible(page, '[data-action="notices-open-compose"], [data-action="notices-create"]');
  let composeClicked = false;
  if (composeButtons > 0) {
    composeClicked = await clickFirstVisible(page, '[data-action="notices-open-compose"], [data-action="notices-create"]');
    await page.locator('#noticesComposePanel:not(.hidden)').first().waitFor({ state: 'visible', timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(1200);
  }
  const composeShot = screenshotPath('notice-compose-open');
  await page.screenshot({ path: composeShot, fullPage: true });
  checks.push({
    name: 'notice-compose-open',
    route: '#/feature/notices',
    count: composeButtons,
    clicked: composeClicked,
    screenshot: composeShot,
    after: await page.evaluate(() => {
      const panel = document.querySelector('#noticesComposePanel');
      return {
        hash: location.hash,
        mode: window.state?.notices?.mode || '',
        composeVisible: Boolean(panel && !panel.classList.contains('hidden')),
        toolLabels: Array.from(document.querySelectorAll('#noticesComposePanel button')).map((node) => node.textContent.trim()).filter(Boolean).slice(0, 12),
        overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth,
      };
    }),
  });

  // Calendar new-event modal open only; no save/delete.
  await waitForRoute(page, '#/calendar/month', '#view-calendar:not(.hidden)');
  const calendarButtons = await countVisible(page, '[data-action="calendar-new-event"]');
  let calendarClicked = false;
  if (calendarButtons > 0) {
    calendarClicked = await clickFirstVisible(page, '[data-action="calendar-new-event"]');
    await page.locator('#appSheet:not(.hidden) [data-calendar-editor-root="true"]').first().waitFor({ state: 'visible', timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(1200);
  }
  const calendarShot = screenshotPath('calendar-new-event-modal-open');
  await page.screenshot({ path: calendarShot, fullPage: true });
  checks.push({
    name: 'calendar-new-event-modal-open',
    route: '#/calendar/month',
    count: calendarButtons,
    clicked: calendarClicked,
    screenshot: calendarShot,
    after: await pageSnapshot(page),
  });
  await page.keyboard.press('Escape').catch(() => {});
  await page.waitForTimeout(500);

  // Finance tab switch only; no upload/download/submit.
  await waitForRoute(page, '#/reports', '#view-reports:not(.hidden)');
  const financeDownloadTabs = await countVisible(page, '[data-action="reports-view-tab"][data-tab="finance-download"]');
  let financeClicked = false;
  if (financeDownloadTabs > 0) {
    financeClicked = await clickFirstVisible(page, '[data-action="reports-view-tab"][data-tab="finance-download"]');
    await page.waitForTimeout(1800);
  }
  const financeShot = screenshotPath('finance-download-tab-switch');
  await page.screenshot({ path: financeShot, fullPage: true });
  checks.push({
    name: 'finance-download-tab-switch',
    route: '#/reports',
    count: financeDownloadTabs,
    clicked: financeClicked,
    screenshot: financeShot,
    after: await page.evaluate(() => ({
      hash: location.hash,
      view: window.state?.currentView || '',
      activeReportsTab: window.state?.reportsViewTab || '',
      title: document.querySelector('#view-reports h2, #view-reports h3')?.textContent?.trim() || '',
      tabLabels: Array.from(document.querySelectorAll('[data-action="reports-view-tab"]')).filter((node) => !node.classList.contains('hidden')).map((node) => node.textContent.trim()),
      overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth,
    })),
  });

  await browser.close();
  const result = {
    generatedAt: new Date().toISOString(),
    frontend: sanitizeUrl(FRONT),
    viewport: { width: 1366, height: 900 },
    checks,
    consoleErrors,
    failedRequests,
    httpApiErrors,
  };
  const resultPath = path.join(OUT_DIR, 'capture.json');
  fs.writeFileSync(resultPath, JSON.stringify(result, null, 2));
  console.log(JSON.stringify({ resultPath, checkCount: checks.length, consoleErrors: consoleErrors.length, failedRequests: failedRequests.length, httpApiErrors: httpApiErrors.length }, null, 2));
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
