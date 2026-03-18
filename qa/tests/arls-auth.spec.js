const { expect, test } = require('@playwright/test');

const {
  loginArls,
  buildArlsAuthenticatedHeaders,
  DEFAULT_ARLS_API_BASE,
} = require('./_helpers');

const arlsMonth = process.env.QA_ARLS_MONTH || new Date().toISOString().slice(0, 7);

function getMonthWindow() {
  return arlsMonth.includes('-') && /^\d{4}-\d{2}$/.test(arlsMonth) ? arlsMonth : new Date().toISOString().slice(0, 7);
}

function buildWorkspaceQuery() {
  const params = new URLSearchParams({ month: getMonthWindow() });

  const tenantCode = (process.env.QA_ARLS_TENANT_CODE || '').trim();
  const siteCode = (process.env.QA_ARLS_SITE_CODE || '').trim();

  if (tenantCode) {
    params.set('tenant_code', tenantCode);
  }
  if (siteCode) {
    params.set('site_code', siteCode);
  }

  return params.toString();
}

test.describe('ARLS Authenticated QA @arls', () => {
  test('ARLS login API returns valid token and /me', async ({ request }) => {
    const loginResult = await loginArls(request);

    if (!loginResult.ok || !loginResult.token) {
      test.skip(loginResult.reason || 'ARLS credentials not configured');
    }

    const headers = buildArlsAuthenticatedHeaders(loginResult.token);
    const me = await request.get(`${DEFAULT_ARLS_API_BASE}/api/v1/me`, { headers });

    expect(me.ok()).toBeTruthy();
    const mePayload = await me.json();

    expect(mePayload.success).toBe(true);
    expect(mePayload.data).toHaveProperty('user_id');
    expect(mePayload.data).toHaveProperty('tenant_id');
    expect(mePayload.data).toHaveProperty('role');
    expect(mePayload.data).toHaveProperty('group');
    expect(typeof mePayload.data.user_id).toBe('string');
  });

  test('ARLS support-status workspace can be queried with authenticated session', async ({ request }) => {
    const loginResult = await loginArls(request);

    if (!loginResult.ok || !loginResult.token) {
      test.skip(loginResult.reason || 'ARLS credentials not configured');
    }

    const headers = buildArlsAuthenticatedHeaders(loginResult.token);
    const workspaceQuery = buildWorkspaceQuery();
    const workspace = await request.get(
      `${DEFAULT_ARLS_API_BASE}/api/v1/schedules/support-status-workspace?${workspaceQuery}`,
      {
        headers,
      },
    );

    expect([200, 403]).toContain(workspace.status());
    if (workspace.status() === 403) {
      return;
    }

    const payload = await workspace.json();
    expect(payload.success).toBe(true);
    expect(payload.data).toHaveProperty('month');
  });
});
