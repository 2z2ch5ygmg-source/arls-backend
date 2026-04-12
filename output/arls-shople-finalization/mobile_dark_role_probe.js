const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

const OUT_DIR = path.resolve(process.env.OUT_DIR || 'output/arls-shople-finalization/mobile-dark-role');
const FRONTEND_URL = process.env.FRONTEND_URL || 'https://rgarlsfront50018.z12.web.core.windows.net/?api=https://rg-arls-backend.azurewebsites.net';
const API_BASE = process.env.API_BASE || 'https://rg-arls-backend.azurewebsites.net/api/v1';
const MOBILE_VIEWPORT = { width: Number(process.env.MOBILE_WIDTH || 390), height: Number(process.env.MOBILE_HEIGHT || 844) };
const DARK_THEME_KEY = 'rg-arls-ui-theme';

const roles = [
  {
    name: 'hq_admin_srs',
    tenant_code: 'srs_korea',
    username: '09903300003',
    password: '09903300003',
    tenantContext: null,
  },
  {
    name: 'developer_master_scoped_srs',
    tenant_code: 'MASTER',
    username: 'platform_admin',
    password: 'Admin1234!!',
    tenantContext: {
      tenantId: '7d3997c3-346a-407e-a416-687fe0827992',
      tenantCode: 'SRS_KOREA',
      tenantName: 'SRS Korea',
    },
  },
];

const routes = [
  { name: 'calendar-month', hash: '#/calendar/month', view: 'calendar', waitSelector: '#view-calendar:not(.hidden)' },
  { name: 'profile-settings', hash: '#/profile', view: 'profile', waitSelector: '#view-profile:not(.hidden)' },
  { name: 'profile-theme', hash: '#/profile?segment=theme', view: 'profile', waitSelector: '#view-profile:not(.hidden)' },
  { name: 'leave-history', hash: '#/leave?tab=history', view: 'leave', waitSelector: '#view-leave:not(.hidden)' },
  { name: 'leave-settings', hash: '#/leave?tab=settings', view: 'leave', waitSelector: '#view-leave:not(.hidden)' },
  { name: 'notices', hash: '#/feature/notices', view: 'notices', waitSelector: '#view-notices:not(.hidden)' },
  { name: 'employees', hash: '#/branch/employees', view: 'employees', waitSelector: '#view-employees:not(.hidden)' },
  { name: 'sites', hash: '#/branch/sites', view: 'org', waitSelector: '#view-org:not(.hidden)' },
  { name: 'reports-finance-submit', hash: '#/reports?tab=finance', view: 'reports', waitSelector: '#view-reports:not(.hidden)' },
  { name: 'reports-finance-download', hash: '#/reports/finance-download', view: 'reports', waitSelector: '#view-reports:not(.hidden)' },
];

function safeFileName(value) {
  return String(value).replace(/[^a-z0-9_.-]+/gi, '-').replace(/^-+|-+$/g, '').toLowerCase();
}

async function login(role) {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      tenant_code: role.tenant_code,
      username: role.username,
      password: role.password,
    }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(`login failed ${res.status} ${JSON.stringify(data)}`);
  return {
    accessToken: data.access_token || data?.data?.access_token,
    refreshToken: data.refresh_token || data?.data?.refresh_token,
    user: data.user || data?.data?.user,
  };
}

async function collectRoute(page, roleName, route) {
  const url = `${FRONTEND_URL}${route.hash}`;
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 });
  await page.waitForSelector(route.waitSelector, { timeout: 30000 }).catch(() => null);
  await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => null);
  await page.waitForTimeout(3200);

  // For Finance submit, make sure we do not click any submission action. We only let existing read-only workspaces hydrate.
  const screenshot = path.join(OUT_DIR, `${safeFileName(roleName)}-${route.name}-${MOBILE_VIEWPORT.width}x${MOBILE_VIEWPORT.height}-dark.png`);
  await page.screenshot({ path: screenshot, fullPage: true });

  const metrics = await page.evaluate(({ routeName, expectedView }) => {
    const doc = document.documentElement;
    const body = document.body;
    const scrollWidth = Math.max(doc?.scrollWidth || 0, body?.scrollWidth || 0);
    const clientWidth = Math.max(doc?.clientWidth || 0, body?.clientWidth || 0);
    const overflowNodes = Array.from(document.querySelectorAll('body *'))
      .filter((node) => {
        if (!(node instanceof HTMLElement)) return false;
        const rect = node.getBoundingClientRect();
        if (!rect.width || !rect.height) return false;
        return rect.right > window.innerWidth + 1 || rect.left < -1;
      })
      .slice(0, 12)
      .map((node) => ({
        tag: node.tagName.toLowerCase(),
        id: node.id || '',
        className: String(node.className || '').slice(0, 140),
        text: String(node.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 120),
        rect: (() => {
          const r = node.getBoundingClientRect();
          return { left: Math.round(r.left), right: Math.round(r.right), width: Math.round(r.width) };
        })(),
      }));
    const visibleView = Array.from(document.querySelectorAll('.view'))
      .find((node) => node instanceof HTMLElement && !node.classList.contains('hidden'));
    const title = document.querySelector('.view:not(.hidden) h1, .view:not(.hidden) h2, .view:not(.hidden) h3')?.textContent?.trim() || '';
    const activeProfileSegment = document.querySelector('[data-action="profile-workspace-segment"].active')?.textContent?.trim() || '';
    const activeLeaveTab = document.querySelector('[data-action="leave-workspace-tab"].active, [data-action="leave-tab"].active, .leave-workspace-tab.active')?.textContent?.trim() || '';
    const activeReportsTab = document.querySelector('[data-action="reports-view-tab"].active')?.textContent?.trim() || '';
    const noticeRows = document.querySelectorAll('[data-notice-id], #noticesListBody tr, .notices-list-item').length;
    const employeeRows = document.querySelectorAll('#employeeDesktopTableBody tr, .employee-directory-row').length;
    const siteRows = document.querySelectorAll('#siteDesktopTableBody tr, .site-directory-row').length;
    const calendarRail = document.querySelectorAll('.calendar-selected-day-rail, [data-calendar-selected-day-rail]').length;
    const financeRows = document.querySelectorAll('#scheduleFinanceOverviewTableBody tr, #financeDownloadTableBody tr').length;
    const loadingCount = Array.from(document.querySelectorAll('.loading, .spinner, [aria-busy="true"]'))
      .filter((node) => node instanceof HTMLElement && !node.classList.contains('hidden')).length;
    return {
      routeName,
      expectedView,
      hash: location.hash,
      currentView: visibleView ? String(visibleView.id || '').replace(/^view-/, '') : '',
      title,
      theme: document.documentElement.dataset.uiTheme || document.body.dataset.uiTheme || document.documentElement.getAttribute('data-ui-theme') || '',
      bodyClass: document.body.className,
      scrollWidth,
      clientWidth,
      pageOverflowX: scrollWidth > clientWidth + 1,
      internalWideNodeCount: overflowNodes.length,
      overflowX: scrollWidth > clientWidth + 1,
      overflowNodes,
      loadingCount,
      activeProfileSegment,
      activeLeaveTab,
      activeReportsTab,
      counts: { noticeRows, employeeRows, siteRows, calendarRail, financeRows },
      topText: String(document.querySelector('.view:not(.hidden)')?.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 500),
    };
  }, { routeName: route.name, expectedView: route.view });

  return { ...metrics, screenshot };
}

async function runRole(browser, role) {
  const result = {
    role: role.name,
    login: null,
    routes: [],
    consoleErrors: [],
    pageErrors: [],
    failedRequests: [],
    httpApiErrors: [],
  };

  let session;
  try {
    session = await login(role);
    result.login = {
      ok: true,
      role: session.user?.role || '',
      tenant_code: session.user?.tenant_code || '',
      username: session.user?.username || role.username,
    };
  } catch (error) {
    result.login = { ok: false, error: String(error) };
    return result;
  }

  const context = await browser.newContext({ viewport: MOBILE_VIEWPORT, isMobile: true, hasTouch: true });
  await context.addInitScript(({ session, role, DARK_THEME_KEY }) => {
    localStorage.setItem('accessToken', session.accessToken);
    localStorage.setItem('refreshToken', session.refreshToken);
    localStorage.setItem('rg-arls-session', JSON.stringify({ token: session.accessToken, refreshToken: session.refreshToken, user: session.user }));
    localStorage.setItem(DARK_THEME_KEY, 'dark');
    if (role.tenantContext) {
      const ctx = role.tenantContext;
      const username = String(session.user?.username || role.username || '').trim().toLowerCase();
      const id = String(session.user?.id || '').trim();
      const contextPayload = { tenantCode: ctx.tenantCode, tenantName: ctx.tenantName };
      const activePayload = { activeTenantId: ctx.tenantId, activeTenantCode: ctx.tenantCode, activeTenantName: ctx.tenantName };
      for (const keyPart of [username, id].filter(Boolean)) {
        localStorage.setItem(`rg-arls-dev-tenant-context:${keyPart}`, JSON.stringify(contextPayload));
        localStorage.setItem(`dev_active_tenant_id:${keyPart}`, ctx.tenantId);
      }
      localStorage.setItem('rg-arls-ui-active-tenant', JSON.stringify(activePayload));
    }
  }, { session, role, DARK_THEME_KEY });

  const page = await context.newPage();
  page.on('console', (msg) => {
    if (msg.type() === 'error') result.consoleErrors.push(msg.text());
  });
  page.on('pageerror', (error) => result.pageErrors.push(String(error)));
  page.on('requestfailed', (req) => result.failedRequests.push(`${req.failure()?.errorText || 'failed'} ${req.url()}`));
  page.on('response', (res) => {
    const status = res.status();
    const url = res.url();
    if (status >= 400 && /\/api\//.test(url)) result.httpApiErrors.push(`${status} ${url}`);
  });

  try {
    for (const route of routes) {
      try {
        result.routes.push(await collectRoute(page, role.name, route));
      } catch (error) {
        result.routes.push({ routeName: route.name, hash: route.hash, error: String(error) });
      }
    }
  } finally {
    await context.close();
  }
  return result;
}

(async () => {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const all = [];
  try {
    for (const role of roles) {
      all.push(await runRole(browser, role));
    }
  } finally {
    await browser.close();
  }

  const summary = {
    generatedAt: new Date().toISOString(),
    frontend: FRONTEND_URL,
    apiBase: API_BASE,
    viewport: MOBILE_VIEWPORT,
    theme: 'dark',
    readOnly: true,
    roles: all,
  };
  fs.writeFileSync(path.join(OUT_DIR, 'capture.json'), JSON.stringify(summary, null, 2));
  console.log(JSON.stringify({ resultPath: path.join(OUT_DIR, 'capture.json'), roles: all.map((r) => ({ role: r.role, login: r.login, routeCount: r.routes.length, consoleErrors: r.consoleErrors.length, pageErrors: r.pageErrors.length, failedRequests: r.failedRequests.length, httpApiErrors: r.httpApiErrors.length, routeErrors: r.routes.filter((x) => x.error).length, pageOverflowRoutes: r.routes.filter((x) => x.pageOverflowX).map((x) => x.routeName), internalWideRoutes: r.routes.filter((x) => x.internalWideNodeCount > 0).map((x) => x.routeName) })) }, null, 2));
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
