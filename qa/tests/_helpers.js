const DEFAULT_ARLS_API_BASE = process.env.QA_ARLS_API_BASE || 'https://rg-arls-backend.azurewebsites.net';

function ensureValue(value) {
  return typeof value === 'string' && value.trim().length > 0 ? value.trim() : '';
}

function extractAccessToken(payload) {
  if (!payload || typeof payload !== 'object') {
    return '';
  }

  return (
    ensureValue(payload.access_token) ||
    ensureValue(payload?.data?.access_token) ||
    ensureValue(payload?.token) ||
    ''
  );
}

async function loginArls(request) {
  const tenantCode = ensureValue(process.env.QA_ARLS_TENANT_CODE);
  const username = ensureValue(process.env.QA_ARLS_USERNAME);
  const password = ensureValue(process.env.QA_ARLS_PASSWORD);

  if (!tenantCode || !username || !password) {
    return { token: '', user: null, reason: 'QA_ARLS_TENANT_CODE / QA_ARLS_USERNAME / QA_ARLS_PASSWORD not set' };
  }

  const loginResponse = await request.post(`${DEFAULT_ARLS_API_BASE}/api/v1/auth/login`, {
    headers: { 'content-type': 'application/json' },
    data: {
      tenant_code: tenantCode,
      username,
      password,
    },
  });

  const payload = await loginResponse.json();
  const token = extractAccessToken(payload);
  return {
    token,
    user:
      payload?.user ||
      payload?.data?.user ||
      null,
    status: loginResponse.status(),
    ok: loginResponse.ok(),
    reason: loginResponse.ok() ? '' : `login failed: status=${loginResponse.status()}`,
  };
}

function buildArlsAuthenticatedHeaders(token) {
  if (!token) {
    return {};
  }

  return {
    Authorization: `Bearer ${token}`,
  };
}

module.exports = {
  DEFAULT_ARLS_API_BASE,
  loginArls,
  buildArlsAuthenticatedHeaders,
};
