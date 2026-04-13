#!/usr/bin/env node
/**
 * ARLS targeted UI cleanup route sweep.
 *
 * Captures required ARLS routes at desktop, 375px, and 768px viewports and
 * writes the artifact contract consumed by the UI cleanup team:
 *   artifacts/ui-sweep/YYYYMMDD-HHMM-arls-ui-cleanup/{manifest.json,console.json,network.json,verdict.md,desktop,375,768}
 *
 * The sweep uses a local static server and mocked auth/API responses by default
 * so it can run from a checkout without a live backend. It fails if any required
 * route/viewport pair does not produce a visible route panel and screenshot.
 */

import fs from "node:fs/promises";
import path from "node:path";
import http from "node:http";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const REPO_ROOT = path.resolve(__dirname, "../..");

const REQUIRED_ROUTES = Object.freeze([
  "/home",
  "/attendance",
  "/attendance?section=period&mode=list",
  "/attendance?section=stats&scope=attendance",
  "/requests",
  "/requests?section=documents",
  "/leave?tab=status",
  "/leave?tab=history",
  "/leave?tab=settings",
  "/schedules/calendar",
  "/schedules/upload",
  "/schedules/hq-upload",
  "/reports",
  "/reports/finance-download",
  "/branch/employees",
  "/branch/sites",
  "/hr?segment=apply",
  "/hr?segment=manage",
  "/ops/support-workers",
  "/profile",
]);

const VIEWPORTS = Object.freeze({
  desktop: { width: 1366, height: 900 },
  "375": { width: 375, height: 812 },
  "768": { width: 768, height: 1024 },
});

const FAMILY_SELECTORS = Object.freeze({
  tabs: [
    ".workspace-tabs .workspace-tab",
    ".approval-tabs .approval-tab",
    ".azure-tabbar .approval-tab",
    "[role='tab']",
  ],
  filters: [
    ".ui-filterbar",
    ".command-bar",
    ".leave-requests-filter-controls",
    ".requests-filter-controls",
    ".attendance-ops-toolbar",
    ".schedule-filter-row",
    ".employee-toolbar",
    ".site-filter-grid",
  ],
  steppers: [
    ".schedule-wizard-progress .schedule-wizard-step",
    ".reports-panel-stepper-index",
    ".reports-wizard-step",
    ".wizard-step-strip .wizard-step-chip",
  ],
  kpi: [
    "[class*='kpi']",
    "[id*='Kpi']",
    "[class*='metric']",
    "[class*='summary-card']",
    "[class*='status-card']",
    "[class*='stat-card']",
  ],
  detailPanels: [
    "[class*='detail-panel']",
    "[class*='detail-rail']",
    "[class*='detail-card']",
    "[id*='Detail']",
    ".drawer:not(.hidden)",
  ],
  approvalFlow: [
    ".hr-approval-stage",
    ".hr-approval-saved-stage-stack",
    "#hrApprovalProcedureStages",
    "[id*='ApprovalProcedure']",
  ],
});

const EXPECTED_FAMILIES = Object.freeze({
  "/home": ["kpi"],
  "/attendance": ["tabs", "filters", "kpi"],
  "/requests": ["tabs", "filters", "kpi", "detailPanels"],
  "/leave": ["tabs", "filters", "kpi"],
  "/schedules/calendar": ["tabs", "filters"],
  "/schedules/upload": ["tabs", "filters", "steppers"],
  "/schedules/hq-upload": ["tabs", "filters", "steppers"],
  "/reports": ["tabs", "kpi", "steppers"],
  "/reports/finance-download": ["tabs", "filters", "detailPanels"],
  "/branch/employees": ["tabs", "filters", "detailPanels"],
  "/branch/sites": ["tabs", "filters", "detailPanels"],
  "/hr": ["tabs", "filters", "approvalFlow"],
  "/ops/support-workers": ["tabs", "filters", "kpi", "detailPanels"],
  "/profile": ["tabs"],
});

const VIEW_SELECTOR_BY_ROUTE = Object.freeze({
  "/home": "#view-home:not(.hidden)",
  "/attendance": "#view-attendance:not(.hidden)",
  "/requests": "#view-requests:not(.hidden)",
  "/leave": "#view-leave:not(.hidden)",
  "/schedules/calendar": "#view-schedule:not(.hidden)",
  "/schedules/upload": "#view-schedule:not(.hidden)",
  "/schedules/hq-upload": "#view-schedule:not(.hidden)",
  "/reports": "#view-reports:not(.hidden)",
  "/reports/finance-download": "#view-reports:not(.hidden)",
  "/branch/employees": "#view-employees:not(.hidden)",
  "/branch/sites": "#view-org:not(.hidden)",
  "/hr": "#view-hr:not(.hidden)",
  "/ops/support-workers": "#view-support-status:not(.hidden)",
  "/profile": "#view-profile:not(.hidden)",
});

const SAMPLE_USER = Object.freeze({
  id: "ui-sweep-user",
  username: "ui-sweep",
  full_name: "UI Sweep HQ Admin",
  role: "hq_admin",
  tenant_id: "tenant-srs-korea",
  tenant_code: "SRS_KOREA",
  tenant_name: "SRS Korea",
  employee_id: "emp-ui-sweep",
  employee_code: "HQ001",
  site_id: "site-seoul",
  site_code: "SEOUL01",
});

const SAMPLE_SITE = Object.freeze({
  id: "site-seoul",
  tenant_id: SAMPLE_USER.tenant_id,
  tenant_code: SAMPLE_USER.tenant_code,
  company_code: SAMPLE_USER.tenant_code,
  site_code: "SEOUL01",
  site_name: "서울 센터",
  address: "서울시 중구 세종대로 1",
  is_active: true,
  radius_meters: 120,
  latitude: 37.5665,
  longitude: 126.978,
});

const SAMPLE_EMPLOYEE = Object.freeze({
  id: "emp-ui-sweep",
  tenant_id: SAMPLE_USER.tenant_id,
  tenant_code: SAMPLE_USER.tenant_code,
  employee_code: "HQ001",
  full_name: "홍길동",
  site_id: SAMPLE_SITE.id,
  site_code: SAMPLE_SITE.site_code,
  site_name: SAMPLE_SITE.site_name,
  role: "hq_admin",
  user_role: "hq_admin",
  employment_status: "active",
  phone: "010-0000-0000",
});

function parseArgs(argv) {
  const args = {
    outputBase: process.env.ARLS_UI_SWEEP_OUTPUT_BASE || "artifacts/ui-sweep",
    baseUrl: process.env.ARLS_UI_SWEEP_BASE_URL || "",
    apiBase: process.env.ARLS_UI_SWEEP_API_BASE || "",
    headful: false,
    keepServer: false,
    routeDelayMs: Number(process.env.ARLS_UI_SWEEP_ROUTE_DELAY_MS || 250),
    visibleTimeoutMs: Number(process.env.ARLS_UI_SWEEP_VISIBLE_TIMEOUT_MS || 7000),
    only: "",
    softFail: false,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const key = argv[i];
    const next = argv[i + 1];
    if (key === "--output-base") {
      args.outputBase = next;
      i += 1;
    } else if (key === "--base-url") {
      args.baseUrl = next;
      i += 1;
    } else if (key === "--api-base") {
      args.apiBase = next;
      i += 1;
    } else if (key === "--only") {
      args.only = next;
      i += 1;
    } else if (key === "--route-delay-ms") {
      args.routeDelayMs = Number(next);
      i += 1;
    } else if (key === "--visible-timeout-ms") {
      args.visibleTimeoutMs = Number(next);
      i += 1;
    } else if (key === "--headful") {
      args.headful = true;
    } else if (key === "--keep-server") {
      args.keepServer = true;
    } else if (key === "--soft-fail") {
      args.softFail = true;
    } else if (key === "--help" || key === "-h") {
      printHelpAndExit();
    } else {
      throw new Error(`Unknown argument: ${key}`);
    }
  }
  if (!Number.isFinite(args.routeDelayMs) || args.routeDelayMs < 0) {
    throw new Error("--route-delay-ms must be a non-negative number");
  }
  if (!Number.isFinite(args.visibleTimeoutMs) || args.visibleTimeoutMs <= 0) {
    throw new Error("--visible-timeout-ms must be a positive number");
  }
  return args;
}

function printHelpAndExit() {
  console.log(`ARLS UI route sweep\n\nOptions:\n  --output-base <dir>        Base artifact directory (default artifacts/ui-sweep)\n  --base-url <url>           Existing frontend index URL; otherwise starts local static server\n  --api-base <url>           API base before /api/v1; defaults to local server base\n  --only <substring>         Run routes containing substring only\n  --route-delay-ms <n>       Extra settle delay before screenshot (default 250)\n  --visible-timeout-ms <n>   Route panel visibility timeout (default 7000)\n  --headful                  Show browser\n  --soft-fail                Write artifacts but exit 0 on missing route/viewport\n`);
  process.exit(0);
}

function normalizeRoutePath(route = "") {
  const raw = String(route || "").trim();
  const hashless = raw.startsWith("#") ? raw.slice(1) : raw;
  const pathOnly = hashless.split("?")[0] || "/";
  return pathOnly.endsWith("/") && pathOnly.length > 1 ? pathOnly.slice(0, -1) : pathOnly;
}

function routeId(route = "") {
  return String(route || "")
    .replace(/^\//, "")
    .replace(/[^a-z0-9]+/gi, "-")
    .replace(/^-+|-+$/g, "") || "root";
}

function kstTimestamp(date = new Date()) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(date);
  const get = (type) => parts.find((item) => item.type === type)?.value || "00";
  return `${get("year")}${get("month")}${get("day")}-${get("hour")}${get("minute")}`;
}

function makeJwt(user = SAMPLE_USER) {
  const header = { alg: "none", typ: "JWT" };
  const payload = {
    sub: user.id,
    username: user.username,
    name: user.full_name,
    full_name: user.full_name,
    role: user.role,
    tenant_id: user.tenant_id,
    tenant_code: user.tenant_code,
    employee_id: user.employee_id,
    employee_code: user.employee_code,
    exp: Math.floor(Date.now() / 1000) + 24 * 60 * 60,
  };
  const encode = (obj) => Buffer.from(JSON.stringify(obj)).toString("base64url");
  return `${encode(header)}.${encode(payload)}.ui-sweep`;
}

async function startStaticServer(rootDir) {
  const server = http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url || "/", "http://127.0.0.1");
      if (url.pathname.startsWith("/api/v1/")) {
        res.writeHead(404, { "content-type": "application/json; charset=utf-8" });
        res.end(JSON.stringify({ detail: "API route should be mocked by Playwright" }));
        return;
      }
      let pathname = decodeURIComponent(url.pathname);
      if (pathname === "/") pathname = "/frontend/index.html";
      const filePath = path.resolve(rootDir, `.${pathname}`);
      if (!filePath.startsWith(rootDir)) {
        res.writeHead(403);
        res.end("Forbidden");
        return;
      }
      const stat = await fs.stat(filePath).catch(() => null);
      const resolved = stat?.isDirectory() ? path.join(filePath, "index.html") : filePath;
      const body = await fs.readFile(resolved);
      res.writeHead(200, { "content-type": contentTypeForPath(resolved) });
      res.end(body);
    } catch (error) {
      res.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
      res.end(`Not found: ${String(error?.message || error)}`);
    }
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  const port = typeof address === "object" && address ? address.port : 0;
  return {
    server,
    origin: `http://127.0.0.1:${port}`,
    close: () => new Promise((resolve) => server.close(resolve)),
  };
}

function contentTypeForPath(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  if (ext === ".html") return "text/html; charset=utf-8";
  if (ext === ".js" || ext === ".mjs") return "text/javascript; charset=utf-8";
  if (ext === ".css") return "text/css; charset=utf-8";
  if (ext === ".json" || ext === ".webmanifest") return "application/json; charset=utf-8";
  if (ext === ".svg") return "image/svg+xml";
  if (ext === ".png") return "image/png";
  if (ext === ".jpg" || ext === ".jpeg") return "image/jpeg";
  if (ext === ".ico") return "image/x-icon";
  return "application/octet-stream";
}

async function installAuthInitScript(context, token) {
  await context.addInitScript(({ sessionToken, user }) => {
    const session = { token: sessionToken, refreshToken: sessionToken, user };
    try {
      localStorage.setItem("rg-arls-session", JSON.stringify(session));
      localStorage.setItem("accessToken", sessionToken);
      localStorage.setItem("refreshToken", sessionToken);
      localStorage.setItem("rg-arls-ui-theme", "light");
      localStorage.setItem(
        "rg-arls-ui-active-tenant",
        JSON.stringify({ tenantId: user.tenant_id, tenantCode: user.tenant_code, tenantName: user.tenant_name }),
      );
    } catch {
      // Storage may be unavailable in unusual browser contexts; route visibility will fail clearly.
    }
  }, { sessionToken: token, user: SAMPLE_USER });
}

async function installApiMock(page, token, networkRows) {
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = request.url();
    const startedAt = Date.now();
    const response = mockApiResponse(url, request.method(), token);
    const failed = Number(response.status || 200) >= 400;
    networkRows.push({
      url,
      method: request.method(),
      status: response.status || 200,
      failed,
      mocked: true,
      timestamp: new Date().toISOString(),
      durationMs: Date.now() - startedAt,
    });
    await route.fulfill({
      status: response.status || 200,
      contentType: response.contentType || "application/json; charset=utf-8",
      body: response.body ?? JSON.stringify(response.json ?? {}),
    });
  });
}

function mockApiResponse(rawUrl, method, token) {
  const url = new URL(rawUrl);
  const pathName = url.pathname.replace(/^.*\/api\/v1/, "") || "/";
  const cleanPath = pathName.replace(/\/+$/, "") || "/";
  const lower = cleanPath.toLowerCase();

  if (lower === "/auth/me") return json(SAMPLE_USER);
  if (lower === "/auth/refresh") {
    return json({ access_token: token, refresh_token: token, token, user: SAMPLE_USER });
  }
  if (lower.startsWith("/auth/tenant-check")) {
    return json({ ok: true, tenant_code: SAMPLE_USER.tenant_code, tenant_name: SAMPLE_USER.tenant_name });
  }
  if (lower === "/companies") {
    return json([{ id: SAMPLE_USER.tenant_id, tenant_code: SAMPLE_USER.tenant_code, tenant_name: SAMPLE_USER.tenant_name }]);
  }
  if (lower === "/sites" || lower.startsWith("/sites?") || lower.startsWith("/dev/sites")) {
    return json([SAMPLE_SITE]);
  }
  if (lower.startsWith("/sites/")) return json(SAMPLE_SITE);
  if (lower === "/employees" || lower.startsWith("/employees?") || lower.startsWith("/dev/employees")) {
    return json([SAMPLE_EMPLOYEE]);
  }
  if (lower.startsWith("/employees/") && lower.includes("drawer-summary")) {
    return json({ employee: SAMPLE_EMPLOYEE, site: SAMPLE_SITE, recent_attendance: [], leave_balance: { remaining_days: 12 } });
  }
  if (lower.startsWith("/employees/")) return json(SAMPLE_EMPLOYEE);

  if (lower.includes("schedule") || lower.includes("schedules")) {
    if (lower.includes("status")) return json({ ok: true, rows: [], metrics: {} });
    if (lower.includes("lite")) return json({ rows: sampleScheduleRows(), employees: [SAMPLE_EMPLOYEE], days: [], metrics: { total: 1 } });
    if (lower.includes("finance") || lower.includes("support")) {
      return json({ rows: [], items: [], artifacts: [], summary: {}, status: "ready", ok: true });
    }
    return json(sampleScheduleRows());
  }
  if (lower.includes("attendance")) {
    if (lower.includes("home-status") || lower.includes("today/status")) {
      return json({ status: "ready", site: SAMPLE_SITE, checked_in: false, work_date: todayDateKey() });
    }
    return json([]);
  }
  if (lower.includes("leave") || lower.includes("leaves")) {
    if (lower.includes("policies")) return json(sampleLeavePolicies());
    if (lower.includes("grants")) return json([]);
    return json([]);
  }
  if (lower.includes("approval") || lower.includes("certificates") || lower.includes("hr/documents")) {
    if (lower.includes("approval-policy")) return json({ stages: sampleApprovalStages(), rules: [] });
    if (lower.includes("types")) return json([{ code: "employment_certificate", label: "재직증명서" }]);
    return json({ rows: [], items: [], stages: sampleApprovalStages(), total: 0 });
  }
  if (lower.includes("home/briefing")) {
    return json({ notices: [], today: {}, metrics: { scheduled: 1, present: 0, vacancy: 0 }, queue: [] });
  }
  if (lower.includes("notices") || lower.includes("notifications") || lower.includes("reminders")) {
    return json({ rows: [], items: [], total: 0, unread_count: 0 });
  }
  if (lower.includes("integrations") || lower.includes("groupware") || lower.includes("mail")) {
    return json({ rows: [], items: [], status: "ready", ok: true });
  }
  if (method !== "GET") return json({ ok: true, id: "mocked" });
  return json({ rows: [], items: [], data: [], results: [], total: 0, ok: true });
}

function json(value, status = 200) {
  return { status, json: value };
}

function todayDateKey() {
  return new Date().toISOString().slice(0, 10);
}

function sampleScheduleRows() {
  return [
    {
      id: "schedule-ui-sweep-1",
      tenant_code: SAMPLE_USER.tenant_code,
      employee_code: SAMPLE_EMPLOYEE.employee_code,
      employee_name: SAMPLE_EMPLOYEE.full_name,
      site_code: SAMPLE_SITE.site_code,
      site_name: SAMPLE_SITE.site_name,
      schedule_date: todayDateKey(),
      shift_type: "day",
      source: "ui-sweep",
    },
  ];
}

function sampleLeavePolicies() {
  return [
    { id: "annual", policy_key: "annual", leave_type: "annual", name: "연차", active: true },
    { id: "sick", policy_key: "sick", leave_type: "sick", name: "병가", active: true },
  ];
}

function sampleApprovalStages() {
  return [
    { id: "stage-1", name: "1차 승인", order: 1, members: [{ user_id: SAMPLE_USER.id, full_name: SAMPLE_USER.full_name }] },
    { id: "stage-2", name: "최종 승인", order: 2, members: [] },
  ];
}

function buildUrl(baseUrl, apiBase, route) {
  const base = new URL(baseUrl);
  base.searchParams.set("api", apiBase);
  base.hash = route;
  return base.toString();
}

async function visiblePanelInfo(page, selector) {
  return page.evaluate(({ targetSelector }) => {
    const visible = (node) => {
      if (!(node instanceof HTMLElement)) return false;
      const style = window.getComputedStyle(node);
      return style.display !== "none" && style.visibility !== "hidden" && !node.classList.contains("hidden");
    };
    const target = Array.from(document.querySelectorAll(targetSelector)).find(visible) || null;
    const visiblePanels = Array.from(document.querySelectorAll(".view:not(.hidden)"))
      .filter(visible)
      .map((node) => node.id || node.getAttribute("data-view") || "unknown");
    return {
      found: Boolean(target),
      visiblePanels,
      hash: window.location.hash,
      title: document.title,
      bodyView: document.body?.dataset?.currentView || "",
    };
  }, { targetSelector: selector });
}

async function componentChecklist(page, route) {
  const pathOnly = normalizeRoutePath(route);
  const expected = EXPECTED_FAMILIES[pathOnly] || [];
  const raw = await page.evaluate(({ selectorsByFamily, expectedFamilies }) => {
    const visible = (node) => {
      if (!(node instanceof HTMLElement)) return false;
      const style = window.getComputedStyle(node);
      const rect = node.getBoundingClientRect();
      return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
    };
    const result = {};
    for (const [family, selectors] of Object.entries(selectorsByFamily)) {
      const matches = [];
      for (const selector of selectors) {
        for (const node of document.querySelectorAll(selector)) {
          if (!visible(node)) continue;
          matches.push({
            selector,
            tag: node.tagName.toLowerCase(),
            id: node.id || "",
            className: String(node.className || "").slice(0, 180),
            text: String(node.textContent || "").replace(/\s+/g, " ").trim().slice(0, 120),
          });
        }
      }
      const unique = [];
      const seen = new Set();
      for (const item of matches) {
        const key = `${item.selector}|${item.tag}|${item.id}|${item.className}|${item.text}`;
        if (seen.has(key)) continue;
        seen.add(key);
        unique.push(item);
      }
      const isExpected = expectedFamilies.includes(family);
      result[family] = {
        expected: isExpected,
        status: unique.length ? "present" : isExpected ? "missing" : "not-applicable",
        visibleCount: unique.length,
        samples: unique.slice(0, 5),
      };
    }
    return result;
  }, { selectorsByFamily: FAMILY_SELECTORS, expectedFamilies: expected });
  return raw;
}

async function collectPageProblems(page) {
  return page.evaluate(() => {
    const alerts = Array.from(document.querySelectorAll("[role='alert'], .toast.error, .toast.state-error, .view-runtime-hint.state-error:not(.hidden)"))
      .map((node) => String(node.textContent || "").replace(/\s+/g, " ").trim())
      .filter(Boolean)
      .slice(-10);
    const horizontalOverflow = document.documentElement.scrollWidth > window.innerWidth + 2;
    return { alerts, horizontalOverflow, scrollWidth: document.documentElement.scrollWidth, innerWidth: window.innerWidth };
  });
}

async function runSweep(config) {
  let playwright;
  try {
    playwright = await import("playwright");
  } catch (error) {
    throw new Error(`Playwright is unavailable: ${String(error?.message || error)}`);
  }

  const timestamp = kstTimestamp();
  const outputRoot = path.resolve(REPO_ROOT, config.outputBase, `${timestamp}-arls-ui-cleanup`);
  for (const label of Object.keys(VIEWPORTS)) {
    await fs.mkdir(path.join(outputRoot, label), { recursive: true });
  }

  const localServer = config.baseUrl ? null : await startStaticServer(REPO_ROOT);
  const baseUrl = config.baseUrl || `${localServer.origin}/frontend/index.html`;
  const apiBase = config.apiBase || localServer?.origin || new URL(baseUrl).origin;
  const token = makeJwt(SAMPLE_USER);
  const routes = config.only ? REQUIRED_ROUTES.filter((route) => route.includes(config.only)) : REQUIRED_ROUTES;
  if (!routes.length) throw new Error(`No routes matched --only=${config.only}`);

  const browser = await playwright.chromium.launch({ headless: !config.headful });
  const consoleRows = [];
  const networkRows = [];
  const manifestEntries = [];
  const missingPairs = [];

  try {
    const context = await browser.newContext({ locale: "ko-KR", timezoneId: "Asia/Seoul" });
    await installAuthInitScript(context, token);
    for (const [viewportLabel, viewport] of Object.entries(VIEWPORTS)) {
      for (const route of routes) {
        const page = await context.newPage();
        await installApiMock(page, token, networkRows);
        page.on("console", (msg) => {
          consoleRows.push({
            route,
            viewport: viewportLabel,
            type: msg.type(),
            text: msg.text(),
            location: msg.location(),
            timestamp: new Date().toISOString(),
          });
        });
        page.on("requestfailed", (request) => {
          networkRows.push({
            route,
            viewport: viewportLabel,
            url: request.url(),
            method: request.method(),
            failed: true,
            failureText: request.failure()?.errorText || "requestfailed",
            mocked: false,
            timestamp: new Date().toISOString(),
          });
        });
        await page.setViewportSize(viewport);
        const pathOnly = normalizeRoutePath(route);
        const selector = VIEW_SELECTOR_BY_ROUTE[pathOnly] || "#shell:not(.hidden)";
        const screenshotRel = `${viewportLabel}/${routeId(route)}.jpg`;
        const screenshotAbs = path.join(outputRoot, screenshotRel);
        const startedAt = new Date().toISOString();
        let panel = { found: false, visiblePanels: [], hash: "" };
        let checklist = {};
        let problems = { alerts: [], horizontalOverflow: false };
        let error = "";
        try {
          await page.goto(buildUrl(baseUrl, apiBase, route), { waitUntil: "domcontentloaded", timeout: 30_000 });
          await page.waitForSelector(selector, { state: "visible", timeout: config.visibleTimeoutMs });
          if (config.routeDelayMs) await page.waitForTimeout(config.routeDelayMs);
          panel = await visiblePanelInfo(page, selector);
          checklist = await componentChecklist(page, route);
          problems = await collectPageProblems(page);
          await page.screenshot({ path: screenshotAbs, type: "jpeg", quality: 82, fullPage: true });
        } catch (caught) {
          error = String(caught?.message || caught).split("\n")[0];
          try {
            await page.screenshot({ path: screenshotAbs, type: "jpeg", quality: 70, fullPage: true });
          } catch {
            // Missing screenshot is represented by screenshotExists=false below.
          }
        }
        const screenshotExists = await fileExists(screenshotAbs);
        const consoleErrorCount = consoleRows.filter((row) => row.route === route && row.viewport === viewportLabel && row.type === "error").length;
        const failedNetworkRequestCount = networkRows.filter((row) => row.route === route && row.viewport === viewportLabel && row.failed).length;
        const ok = Boolean(panel.found && screenshotExists && !error);
        const entry = {
          route,
          routePath: pathOnly,
          viewport: viewportLabel,
          width: viewport.width,
          height: viewport.height,
          screenshotPath: screenshotRel,
          screenshotExists,
          timestamp: startedAt,
          consoleErrorCount,
          failedNetworkRequestCount,
          checklist,
          pageProblems: problems,
          visiblePanel: panel,
          status: ok ? "pass" : "fail",
          error,
        };
        manifestEntries.push(entry);
        if (!ok) missingPairs.push({ route, viewport: viewportLabel, error: error || "route panel not visible or screenshot missing" });
        await page.close();
      }
    }
    await context.close();
  } finally {
    await browser.close();
    if (localServer && !config.keepServer) await localServer.close();
  }

  const manifest = {
    schemaVersion: 1,
    generatedAt: new Date().toISOString(),
    artifactRoot: path.relative(REPO_ROOT, outputRoot),
    baseUrl,
    apiBase,
    mockedAuth: true,
    mockedApi: true,
    requiredRoutes: REQUIRED_ROUTES,
    sweptRoutes: routes,
    viewports: VIEWPORTS,
    expectedPairCount: routes.length * Object.keys(VIEWPORTS).length,
    actualPairCount: manifestEntries.length,
    missingPairs,
    ok: missingPairs.length === 0,
    entries: manifestEntries,
  };

  await fs.writeFile(path.join(outputRoot, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
  await fs.writeFile(path.join(outputRoot, "console.json"), `${JSON.stringify(consoleRows, null, 2)}\n`, "utf8");
  await fs.writeFile(path.join(outputRoot, "network.json"), `${JSON.stringify(networkRows, null, 2)}\n`, "utf8");
  await fs.writeFile(path.join(outputRoot, "verdict.md"), buildVerdict(manifest), "utf8");
  await writeLatestPointer(outputRoot, manifest);
  return { outputRoot, manifest };
}

async function fileExists(filePath) {
  try {
    const stat = await fs.stat(filePath);
    return stat.isFile() && stat.size > 0;
  } catch {
    return false;
  }
}

function buildVerdict(manifest) {
  const lines = [
    "# ARLS Targeted UI Cleanup Route Sweep Verdict",
    "",
    `- Generated: ${manifest.generatedAt}`,
    `- Artifact root: \`${manifest.artifactRoot}\``,
    `- Base URL: ${manifest.baseUrl}`,
    `- API: ${manifest.mockedApi ? "mocked" : manifest.apiBase}`,
    `- Required route/viewport pairs: ${manifest.expectedPairCount}`,
    `- Captured route/viewport pairs: ${manifest.entries.filter((entry) => entry.status === "pass").length}`,
    `- Overall route completeness: ${manifest.ok ? "PASS" : "FAIL"}`,
    "",
  ];
  if (manifest.missingPairs.length) {
    lines.push("## Missing / Failed Route-Viewport Pairs", "");
    for (const pair of manifest.missingPairs) {
      lines.push(`- FAIL ${pair.viewport} ${pair.route}: ${pair.error}`);
    }
    lines.push("");
  }
  lines.push("## Component Family Presence", "", "| Viewport | Route | Tabs | Filters | Steppers | KPI | Detail panels | Approval flow | Notes |", "| --- | --- | --- | --- | --- | --- | --- | --- | --- |");
  for (const entry of manifest.entries) {
    const family = (name) => {
      const item = entry.checklist?.[name];
      if (!item) return "-";
      if (item.status === "present") return `PASS (${item.visibleCount})`;
      if (item.status === "missing") return "WARN missing";
      return "n/a";
    };
    const notes = [];
    if (entry.error) notes.push(entry.error);
    if (entry.consoleErrorCount) notes.push(`${entry.consoleErrorCount} console error(s)`);
    if (entry.failedNetworkRequestCount) notes.push(`${entry.failedNetworkRequestCount} failed network request(s)`);
    if (entry.pageProblems?.horizontalOverflow) notes.push(`horizontal overflow ${entry.pageProblems.scrollWidth}/${entry.pageProblems.innerWidth}`);
    if (entry.pageProblems?.alerts?.length) notes.push(`alerts: ${entry.pageProblems.alerts.join("; ").replaceAll("|", "\\|")}`);
    lines.push(`| ${entry.viewport} | ${entry.route} | ${family("tabs")} | ${family("filters")} | ${family("steppers")} | ${family("kpi")} | ${family("detailPanels")} | ${family("approvalFlow")} | ${notes.join("; ") || "-"} |`);
  }
  lines.push("", "## Artifact Contract", "", "- `manifest.json`: route, viewport, dimensions, screenshot path, timestamps, console/network counts, checklist status.", "- `console.json`: browser console messages captured during each route/viewport pass.", "- `network.json`: mocked API requests plus any request failures.", "- `desktop/`, `375/`, `768/`: full-page JPEG screenshots per required route.", "");
  return `${lines.join("\n")}\n`;
}

async function writeLatestPointer(outputRoot, manifest) {
  const latestDir = path.resolve(REPO_ROOT, "artifacts/ui-sweep/latest-arls-ui-cleanup");
  await fs.mkdir(latestDir, { recursive: true });
  const latest = {
    generatedAt: manifest.generatedAt,
    artifactRoot: manifest.artifactRoot,
    ok: manifest.ok,
    expectedPairCount: manifest.expectedPairCount,
    capturedPairCount: manifest.entries.filter((entry) => entry.status === "pass").length,
    missingPairs: manifest.missingPairs,
  };
  await fs.writeFile(path.join(latestDir, "latest-run.json"), `${JSON.stringify(latest, null, 2)}\n`, "utf8");
  await fs.writeFile(
    path.join(latestDir, "README.md"),
    `# Latest ARLS UI cleanup sweep\n\n- Generated: ${manifest.generatedAt}\n- Artifact root: \`${manifest.artifactRoot}\`\n- Overall: ${manifest.ok ? "PASS" : "FAIL"}\n\nOpen the timestamped artifact directory for screenshots and full verdict.\n`,
    "utf8",
  );
}

const config = parseArgs(process.argv.slice(2));
const result = await runSweep(config);
const relRoot = path.relative(REPO_ROOT, result.outputRoot);
console.log(JSON.stringify({ ok: result.manifest.ok, artifactRoot: relRoot, missingPairs: result.manifest.missingPairs }, null, 2));
if (!result.manifest.ok && !config.softFail) process.exit(1);
