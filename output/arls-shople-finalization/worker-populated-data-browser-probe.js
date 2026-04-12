const { chromium } = require('playwright');
const fs = require('fs/promises');
const path = require('path');
const API = 'https://rg-arls-backend.azurewebsites.net';
const FRONT = `https://rgarlsfront50018.z12.web.core.windows.net/?api=${encodeURIComponent(API)}&worker2Populated=${Date.now()}`;
const TENANT = { id: '7d3997c3-346a-407e-a416-687fe0827992', code: 'SRS_KOREA', name: 'SRS Korea' };
const OUT = 'output/arls-shople-finalization/populated-captures';
const routes = [
  {name:'attendance-period-list', hash:'#/attendance?section=period&mode=list'},
  {name:'schedule-list', hash:'#/schedules/list'},
  {name:'schedule-calendar', hash:'#/schedules/calendar'},
  {name:'leave-grants', hash:'#/leave?tab=grants'},
  {name:'notices', hash:'#/feature/notices'},
];
async function login() {
  if (!process.env.ARLS_QA_PASSWORD) throw new Error('Set ARLS_QA_PASSWORD before rerunning this probe.');
  const res = await fetch(`${API}/api/v1/auth/login`, {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({tenant_code:'MASTER', username:'platform_admin', password: process.env.ARLS_QA_PASSWORD || ''})});
  const json = await res.json();
  if (!res.ok) throw new Error(`login failed ${res.status}`);
  return json.data || json;
}
(async () => {
  await fs.mkdir(OUT, {recursive:true});
  const session = await login();
  const browser = await chromium.launch({headless:true});
  const context = await browser.newContext({viewport:{width:1366,height:900}, deviceScaleFactor:1});
  await context.addInitScript(({session, tenant}) => {
    localStorage.setItem('rg-arls-session', JSON.stringify({token: session.access_token, refreshToken: session.refresh_token || '', user: session.user || null}));
    localStorage.setItem('rg-arls-dev-tenant-context:platform_admin', JSON.stringify({tenantCode: tenant.code, tenantName: tenant.name}));
    localStorage.setItem('dev_active_tenant_id:platform_admin', tenant.id);
    localStorage.setItem('rg-arls-ui-active-tenant', JSON.stringify({activeTenantId: tenant.id, activeTenantCode: tenant.code, activeTenantName: tenant.name}));
    localStorage.setItem('rg-arls-runtime-bypass-password-gate', 'true');
  }, {session, tenant:TENANT});
  const page = await context.newPage();
  const consoleErrors=[]; const failedRequests=[]; const httpApiErrors=[];
  page.on('console', msg => { if (msg.type()==='error') consoleErrors.push(msg.text().slice(0,500)); });
  page.on('requestfailed', req => failedRequests.push(req.url()));
  page.on('response', res => { const u=res.url(); if (u.includes('/api/v1/') && res.status()>=400) httpApiErrors.push({status:res.status(), url:u}); });
  const results=[];
  for (const route of routes) {
    const url = `${FRONT}${route.hash}`;
    await page.goto(url, {waitUntil:'domcontentloaded', timeout:45000});
    await page.waitForLoadState('networkidle', {timeout:12000}).catch(()=>{});
    await page.waitForTimeout(2000);
    const title = await page.locator('h1, .page-title, [data-page-title]').first().textContent({timeout:3000}).catch(()=>null);
    const bodyText = await page.locator('body').innerText({timeout:5000}).catch(()=> '');
    const screenshot = path.join(OUT, `${route.name}.png`);
    await page.screenshot({path:screenshot, fullPage:true});
    const rowHints = await page.locator('tbody tr, .data-row, .schedule-row, .notice-card, .notice-list-item, .calendar-event, .leave-row').count().catch(()=>null);
    const overflowX = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 2).catch(()=>null);
    results.push({route:route.hash, url, title, screenshot, rowHints, overflowX, textSample: bodyText.replace(/\s+/g,' ').trim().slice(0,1200)});
  }
  await browser.close();
  console.log(JSON.stringify({at:new Date().toISOString(), frontend:FRONT, tenant:TENANT, consoleErrors, failedRequests, httpApiErrors, results}, null, 2));
})().catch(err => { console.error(err); process.exit(1); });
