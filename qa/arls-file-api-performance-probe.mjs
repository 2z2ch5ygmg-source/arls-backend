#!/usr/bin/env node
/**
 * ARLS file/API performance probe.
 *
 * Measures safe file-operation entry points and background API settle/fanout
 * without running destructive apply/delete flows. Direct API probes default to
 * read/download/contract endpoints; stateful review download is opt-in.
 *
 * Examples:
 *   node qa/arls-file-api-performance-probe.mjs --dry-run
 *   node qa/arls-file-api-performance-probe.mjs \
 *     --base-url "https://front.example/?api=https://backend.example" \
 *     --storage-state output/arls-instant-tab-latency/storage-state-live.json \
 *     --output output/arls-file-api-performance/probe-live.json --soft-fail
 */

import fs from "node:fs/promises";
import path from "node:path";
import { performance } from "node:perf_hooks";

const DEFAULT_BASE_URL = process.env.ARLS_PROBE_BASE_URL || "http://127.0.0.1:5500/frontend/index.html";
const DEFAULT_OUTPUT = process.env.ARLS_FILE_API_PROBE_OUTPUT || "output/arls-file-api-performance/file-api-probe.json";
const DEFAULT_API_QUIET_MS = 350;
const DEFAULT_API_TIMEOUT_MS = 8_000;
const DEFAULT_VISIBLE_TIMEOUT_MS = 4_000;
const DEFAULT_THRESHOLD_MS = 200;
const DEFAULT_MAX_DOWNLOAD_BYTES = 8 * 1024 * 1024;
const DEFAULT_HR_APPROVAL_POLICY_WARN_MS = 1_000;
const DEFAULT_HR_DOCUMENT_TYPE = "employment_certificate";

const BACKGROUND_ROUTE_SPECS = Object.freeze([
  { id: "home", hash: "#/home", selector: "#view-home:not(.hidden)" },
  { id: "attendance", hash: "#/attendance", selector: "#view-attendance:not(.hidden)" },
  { id: "schedule-calendar", hash: "#/schedules/calendar", selector: "#view-schedule:not(.hidden)" },
  { id: "schedule-upload", hash: "#/schedules/upload", selector: "#view-schedule:not(.hidden)" },
  { id: "reports-finance", hash: "#/reports?tab=finance", selector: "#view-reports:not(.hidden)" },
  { id: "reports-finance-download", hash: "#/reports/finance-download", selector: "#view-reports:not(.hidden)" },
  { id: "profile", hash: "#/profile", selector: "#view-profile:not(.hidden)" },
  { id: "support-workers", hash: "#/ops/support-workers", selector: "#view-support-status:not(.hidden)" },
  { id: "calendar-month", hash: "#/calendar/month", selector: "#view-calendar:not(.hidden)" },
  { id: "hr", hash: "#/hr", selector: "#view-hr:not(.hidden)" },
]);

const SAFE_UI_FLOW_SPECS = Object.freeze([
  {
    id: "finance-download-workspace",
    hash: "#/reports/finance-download",
    selector: "#view-reports:not(.hidden) [data-reports-panel='finance-download'], #view-reports:not(.hidden)",
    probes: [
      { name: "downloadRows", selector: ".reports-finance-download-row" },
      { name: "downloadableCheckboxes", selector: ".reports-finance-download-checkbox:not(:disabled)" },
      { name: "runButton", selector: "[data-action='reports-finance-download-run']", inspectDisabled: true },
    ],
  },
  {
    id: "finance-submission-review",
    hash: "#/reports?tab=finance",
    selector: "#view-reports:not(.hidden)",
    probes: [
      { name: "reviewDownloadButton", selector: "[data-action='schedule-finance-review-download']", inspectDisabled: true },
      { name: "finalUploadInput", selector: "#scheduleFinanceUploadFile" },
      { name: "finalPreviewButton", selector: "[data-action='schedule-finance-preview']", inspectDisabled: true },
      { name: "finalApplyButton", selector: "[data-action='schedule-finance-apply']", inspectDisabled: true },
    ],
  },
  {
    id: "schedule-support-hq-workspace",
    hash: "#/schedules/hq-upload",
    selector: "#view-schedule:not(.hidden) .schedule-support-upload-actions, #view-schedule:not(.hidden)",
    probes: [
      { name: "hqDownloadButton", selector: "[data-action='schedule-support-hq-download']", inspectDisabled: true },
      { name: "hqUploadInput", selector: "#scheduleSupportHqUploadFile" },
      { name: "hqInspectButton", selector: "[data-action='schedule-support-hq-inspect']", inspectDisabled: true },
      { name: "hqApplyButton", selector: "[data-action='schedule-support-apply']", inspectDisabled: true },
    ],
  },
  {
    id: "schedule-base-upload-workspace",
    hash: "#/schedules/upload",
    selector: "#view-schedule:not(.hidden) .schedule-upload-workspace, #view-schedule:not(.hidden)",
    probes: [
      { name: "templateDownloadButton", selector: "[data-action='schedule-download-blank-template']", inspectDisabled: true },
      { name: "latestBaseDownloadButton", selector: "[data-action='schedule-download-latest-base']", inspectDisabled: true },
      { name: "scheduleImportFile", selector: "#scheduleImportFile" },
      { name: "schedulePreviewButton", selector: "[data-action='preview-schedule']", inspectDisabled: true },
    ],
  },
]);

const STATEFUL_SAFE_ENDPOINTS = Object.freeze([
  {
    id: "finance-review-excel",
    method: "GET",
    path: "/schedules/finance-submission/review-excel",
    params: { month: "month", site_code: "siteCode", tenant_code: "tenantCode" },
    kind: "stateful-download",
    note: "Opt-in because backend records review_download state.",
  },
]);

function parseArgs(argv) {
  const args = {
    baseUrl: DEFAULT_BASE_URL,
    apiBase: process.env.ARLS_API_BASE_URL || "",
    storageState: process.env.ARLS_PLAYWRIGHT_STORAGE_STATE || "",
    output: DEFAULT_OUTPUT,
    month: process.env.ARLS_PROBE_MONTH || currentKstMonth(),
    tenantCode: process.env.ARLS_PROBE_TENANT_CODE || "SRS_KOREA",
    siteCode: process.env.ARLS_PROBE_SITE_CODE || "ALL",
    supportScope: process.env.ARLS_PROBE_SUPPORT_SCOPE || "all",
    apiQuietMs: Number(process.env.ARLS_API_QUIET_MS || DEFAULT_API_QUIET_MS),
    apiTimeoutMs: Number(process.env.ARLS_API_TIMEOUT_MS || DEFAULT_API_TIMEOUT_MS),
    visibleTimeoutMs: Number(process.env.ARLS_VISIBLE_TIMEOUT_MS || DEFAULT_VISIBLE_TIMEOUT_MS),
    thresholdMs: Number(process.env.ARLS_FIRST_VISIBLE_THRESHOLD_MS || DEFAULT_THRESHOLD_MS),
    maxDownloadBytes: Number(process.env.ARLS_PROBE_MAX_DOWNLOAD_BYTES || DEFAULT_MAX_DOWNLOAD_BYTES),
    duplicateThreshold: Number(process.env.ARLS_PROBE_DUPLICATE_THRESHOLD || 2),
    approvalPolicyWarnMs: Number(process.env.ARLS_HR_APPROVAL_POLICY_WARN_MS || DEFAULT_HR_APPROVAL_POLICY_WARN_MS),
    hrDocumentType: process.env.ARLS_PROBE_HR_DOCUMENT_TYPE || DEFAULT_HR_DOCUMENT_TYPE,
    only: "",
    dryRun: false,
    softFail: false,
    headful: false,
    includeStatefulDownloads: false,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const key = argv[i];
    const next = argv[i + 1];
    if (key === "--base-url") {
      args.baseUrl = next;
      i += 1;
    } else if (key === "--api-base") {
      args.apiBase = next;
      i += 1;
    } else if (key === "--storage-state") {
      args.storageState = next;
      i += 1;
    } else if (key === "--output") {
      args.output = next;
      i += 1;
    } else if (key === "--month") {
      args.month = next;
      i += 1;
    } else if (key === "--tenant-code") {
      args.tenantCode = next;
      i += 1;
    } else if (key === "--site-code") {
      args.siteCode = next;
      i += 1;
    } else if (key === "--support-scope") {
      args.supportScope = next;
      i += 1;
    } else if (key === "--api-quiet-ms") {
      args.apiQuietMs = Number(next);
      i += 1;
    } else if (key === "--api-timeout-ms") {
      args.apiTimeoutMs = Number(next);
      i += 1;
    } else if (key === "--visible-timeout-ms") {
      args.visibleTimeoutMs = Number(next);
      i += 1;
    } else if (key === "--threshold-ms") {
      args.thresholdMs = Number(next);
      i += 1;
    } else if (key === "--max-download-bytes") {
      args.maxDownloadBytes = Number(next);
      i += 1;
    } else if (key === "--duplicate-threshold") {
      args.duplicateThreshold = Number(next);
      i += 1;
    } else if (key === "--approval-policy-warn-ms") {
      args.approvalPolicyWarnMs = Number(next);
      i += 1;
    } else if (key === "--hr-document-type") {
      args.hrDocumentType = String(next || "").trim() || DEFAULT_HR_DOCUMENT_TYPE;
      i += 1;
    } else if (key === "--only") {
      args.only = next;
      i += 1;
    } else if (key === "--include-stateful-downloads") {
      args.includeStatefulDownloads = true;
    } else if (key === "--dry-run") {
      args.dryRun = true;
    } else if (key === "--soft-fail") {
      args.softFail = true;
    } else if (key === "--headful") {
      args.headful = true;
    } else if (key === "--help" || key === "-h") {
      printHelpAndExit();
    } else {
      throw new Error(`Unknown argument: ${key}`);
    }
  }
  args.apiBase = normalizeApiBase(args.apiBase || deriveApiBaseFromUrl(args.baseUrl));
  if (!args.apiBase) throw new Error("Unable to resolve API base; pass --api-base or use --base-url with ?api=");
  for (const [name, value] of Object.entries({ apiQuietMs: args.apiQuietMs, apiTimeoutMs: args.apiTimeoutMs, visibleTimeoutMs: args.visibleTimeoutMs, thresholdMs: args.thresholdMs, maxDownloadBytes: args.maxDownloadBytes, approvalPolicyWarnMs: args.approvalPolicyWarnMs })) {
    if (!Number.isFinite(value) || value <= 0) throw new Error(`${name} must be a positive number`);
  }
  if (!["", "api", "browser", "background"].includes(args.only)) {
    throw new Error("--only must be one of: api, browser, background");
  }
  return args;
}

function printHelpAndExit() {
  console.log(`ARLS file/API performance probe\n\nOptions:\n  --base-url <url>              Frontend URL (may include ?api=<backend>)\n  --api-base <url>              API base; /api/v1 is appended when omitted\n  --storage-state <path>        Playwright storage state with ARLS token\n  --output <path>               JSON report path\n  --month <YYYY-MM>             Probe month (default current KST month)\n  --tenant-code <code>          Tenant code (default SRS_KOREA)\n  --site-code <code>            Site code for single-site probes (default ALL)\n  --support-scope <all|site>    HQ roster workbook scope (default all)\n  --only <api|browser|background>\n  --include-stateful-downloads  Also run finance review download; backend records state\n  --soft-fail                   Write report and exit 0 even when checks fail\n  --dry-run                     Write/print probe plan without network/browser work\n`);
  process.exit(0);
}

function currentKstMonth() {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit" }).formatToParts(new Date());
  const byType = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${byType.year}-${byType.month}`;
}

function normalizeApiBase(raw) {
  const trimmed = String(raw || "").trim().replace(/\/+$/, "");
  if (!trimmed) return "";
  return /\/api\/v1$/i.test(trimmed) ? trimmed : `${trimmed}/api/v1`;
}

function deriveApiBaseFromUrl(baseUrl) {
  try {
    const url = new URL(baseUrl);
    const queryApi = url.searchParams.get("api");
    if (queryApi && !["undefined", "null"].includes(queryApi.toLowerCase())) return queryApi;
    if ((url.hostname || "").includes(".web.core.windows.net")) return "https://arls-wonseo-prod-260402.azurewebsites.net";
  } catch {
    // ignore and fall through
  }
  return "http://127.0.0.1:8000";
}

function extractAccessToken(storageState) {
  for (const origin of storageState?.origins || []) {
    const entries = new Map((origin.localStorage || []).map((item) => [item.name, item.value]));
    const direct = entries.get("accessToken") || entries.get("token");
    if (direct) return direct;
    const session = entries.get("rg-arls-session");
    if (session) {
      try {
        const parsed = JSON.parse(session);
        if (parsed?.token) return String(parsed.token);
      } catch {
        // ignore malformed localStorage session
      }
    }
  }
  return "";
}

async function loadStorageState(storageStatePath) {
  if (!storageStatePath) return { storageState: null, accessToken: "", error: "" };
  try {
    const storageState = JSON.parse(await fs.readFile(storageStatePath, "utf8"));
    return { storageState, accessToken: extractAccessToken(storageState), error: "" };
  } catch (error) {
    return { storageState: null, accessToken: "", error: String(error?.message || error) };
  }
}

function buildSafeApiSpecs(config) {
  const specs = [
    {
      id: "hr-approval-policy",
      method: "GET",
      path: "/admin/hr/documents/approval-policy",
      params: { document_type: config.hrDocumentType },
      kind: "focused-safe-read",
      okStatuses: [200, 403],
      performanceWarnMs: config.approvalPolicyWarnMs,
      note: "Focused HR approval-policy timing probe; 403 is accepted for unauthenticated/insufficient-role runs.",
    },
    {
      id: "finance-download-workspace",
      method: "GET",
      path: "/schedules/finance-submission/download-workspace",
      params: { month: config.month, tenant_code: config.tenantCode },
      kind: "contract-read",
      okStatuses: [200, 403],
    },
    {
      id: "finance-final-excel-availability",
      method: "GET",
      path: "/schedules/finance-submission/final-excel",
      params: { month: config.month, site_code: config.siteCode, tenant_code: config.tenantCode },
      kind: "safe-download-if-ready",
      okStatuses: [200, 403, 404, 409],
      note: "409 is accepted because final workbook may not be available for the selected site/month.",
    },
    {
      id: "support-hq-workspace",
      method: "GET",
      path: "/schedules/support-roundtrip/hq-workspace",
      params: { month: config.month, tenant_code: config.tenantCode },
      kind: "contract-read",
      okStatuses: [200, 403],
    },
    {
      id: "support-hq-roster-workbook",
      method: "GET",
      path: "/schedules/support-roundtrip/hq-roster-workbook",
      params: { month: config.month, scope: config.supportScope, tenant_code: config.tenantCode },
      kind: "safe-download-generation",
      okStatuses: [200, 403, 404, 409],
    },
    {
      id: "support-final-excel-availability",
      method: "GET",
      path: "/schedules/support-roundtrip/final-excel",
      params: { month: config.month, site_code: config.siteCode, tenant_code: config.tenantCode },
      kind: "safe-download-if-ready",
      okStatuses: [200, 403, 404, 409],
      note: "409 is accepted because final workbook may not be available for the selected site/month.",
    },
  ];
  if (config.includeStatefulDownloads) {
    specs.push(...STATEFUL_SAFE_ENDPOINTS.map((spec) => ({
      ...spec,
      params: resolveParamTemplate(spec.params, config),
      okStatuses: [200, 403, 404, 409],
    })));
  }
  return specs;
}

function resolveParamTemplate(template, config) {
  const values = { month: config.month, siteCode: config.siteCode, tenantCode: config.tenantCode };
  return Object.fromEntries(Object.entries(template).map(([key, value]) => [key, values[value] || value]));
}

function buildUrl(apiBase, spec) {
  const url = new URL(`${apiBase}${spec.path}`);
  for (const [key, value] of Object.entries(spec.params || {})) {
    if (Array.isArray(value)) {
      for (const item of value) url.searchParams.append(key, item);
    } else if (value !== undefined && value !== null && String(value).trim() !== "") {
      url.searchParams.set(key, String(value));
    }
  }
  return url;
}

async function readResponseBytes(response, maxBytes) {
  const reader = response.body?.getReader?.();
  if (!reader) {
    const buffer = await response.arrayBuffer();
    return { bytesRead: buffer.byteLength, truncated: false };
  }
  let bytesRead = 0;
  let truncated = false;
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    bytesRead += value?.byteLength || 0;
    if (bytesRead >= maxBytes) {
      truncated = true;
      await reader.cancel().catch(() => {});
      break;
    }
  }
  return { bytesRead, truncated };
}

async function runSafeApiProbes(config, accessToken) {
  const headers = { "Accept": "application/json, application/vnd.openxmlformats-officedocument.spreadsheetml.sheet, */*" };
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  const results = [];
  for (const spec of buildSafeApiSpecs(config)) {
    const url = buildUrl(config.apiBase, spec);
    const startedAt = performance.now();
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), config.apiTimeoutMs);
    try {
      const response = await fetch(url, { method: spec.method, headers, signal: controller.signal });
      const headerMs = performance.now() - startedAt;
      const body = await readResponseBytes(response, config.maxDownloadBytes);
      const totalMs = performance.now() - startedAt;
      const okStatuses = Array.isArray(spec.okStatuses) ? spec.okStatuses : [200];
      results.push({
        ...spec,
        url: redactUrl(url),
        status: response.status,
        ok: okStatuses.includes(response.status),
        headerMs,
        totalMs,
        contentType: response.headers.get("content-type") || "",
        contentLength: response.headers.get("content-length") || "",
        bytesRead: body.bytesRead,
        truncated: body.truncated,
        authBlocked: [401, 403].includes(response.status),
        performanceOk: !spec.performanceWarnMs || headerMs <= spec.performanceWarnMs,
        performanceWarnMs: spec.performanceWarnMs || undefined,
      });
    } catch (error) {
      results.push({ ...spec, url: redactUrl(url), ok: false, error: String(error?.message || error), totalMs: performance.now() - startedAt });
    } finally {
      clearTimeout(timer);
    }
  }
  return results;
}

function redactUrl(url) {
  const copy = new URL(String(url));
  for (const key of Array.from(copy.searchParams.keys())) {
    if (/token|password|secret/i.test(key)) copy.searchParams.set(key, "REDACTED");
  }
  return copy.toString();
}

async function importPlaywright() {
  try {
    return await import("playwright");
  } catch (error) {
    throw new Error(`Playwright is not available: ${String(error?.message || error)}`);
  }
}

async function addNetworkCapture(page) {
  await page.addInitScript(() => {
    const now = () => (typeof performance !== "undefined" ? performance.now() : Date.now());
    const net = { inflight: 0, lastActivityAt: now(), requests: [], errors: [] };
    Object.defineProperty(window, "__ARLS_FILE_API_PROBE_NET__", { value: net, configurable: true });
    const mark = () => { net.lastActivityAt = now(); };
    const originalFetch = window.fetch;
    if (typeof originalFetch === "function") {
      window.fetch = async (...args) => {
        const url = String(args?.[0]?.url || args?.[0] || "");
        const startedAt = now();
        net.inflight += 1;
        mark();
        try {
          const response = await originalFetch(...args);
          net.requests.push({ url, method: String(args?.[1]?.method || "GET").toUpperCase(), status: response.status, ok: response.ok, durationMs: now() - startedAt });
          return response;
        } catch (error) {
          net.errors.push({ url, message: String(error?.message || error) });
          throw error;
        } finally {
          net.inflight = Math.max(0, net.inflight - 1);
          mark();
        }
      };
    }
    const OriginalXhr = window.XMLHttpRequest;
    if (typeof OriginalXhr === "function") {
      const originalOpen = OriginalXhr.prototype.open;
      const originalSend = OriginalXhr.prototype.send;
      OriginalXhr.prototype.open = function patchedOpen(method, url, ...rest) {
        this.__arlsProbeMethod = String(method || "GET").toUpperCase();
        this.__arlsProbeUrl = String(url || "");
        return originalOpen.call(this, method, url, ...rest);
      };
      OriginalXhr.prototype.send = function patchedSend(...args) {
        const startedAt = now();
        net.inflight += 1;
        mark();
        this.addEventListener("loadend", () => {
          net.requests.push({ url: this.__arlsProbeUrl || "", method: this.__arlsProbeMethod || "GET", status: this.status, ok: this.status < 400, durationMs: now() - startedAt, transport: "xhr" });
          net.inflight = Math.max(0, net.inflight - 1);
          mark();
        }, { once: true });
        return originalSend.apply(this, args);
      };
    }
  });
}

async function waitForApiQuiet(page, config) {
  try {
    await page.waitForFunction(({ quietMs }) => {
      const net = window.__ARLS_FILE_API_PROBE_NET__;
      if (!net) return true;
      return Number(net.inflight || 0) === 0 && performance.now() - Number(net.lastActivityAt || 0) >= quietMs;
    }, { quietMs: config.apiQuietMs }, { timeout: config.apiTimeoutMs });
    return { timedOut: false };
  } catch (error) {
    return { timedOut: true, error: String(error?.message || error).split("\n")[0] };
  }
}

async function resetNetworkCapture(page) {
  await page.evaluate(() => {
    const net = window.__ARLS_FILE_API_PROBE_NET__;
    if (!net) return;
    net.inflight = 0;
    net.lastActivityAt = performance.now();
    net.requests = [];
    net.errors = [];
  }).catch(() => {});
}

async function triggerRoute(page, hash, selector) {
  await page.evaluate(({ nextHash, targetSelector }) => {
    const startMs = performance.now();
    window.__ARLS_FILE_API_PROBE_ROUTE_START_MS__ = startMs;
    window.__ARLS_FILE_API_PROBE_ROUTE_VISIBLE_MS__ = 0;
    const markVisible = () => {
      const visible = Array.from(document.querySelectorAll(targetSelector)).some((node) => {
        if (!(node instanceof HTMLElement)) return false;
        const style = window.getComputedStyle(node);
        const rect = node.getBoundingClientRect();
        return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
      });
      if (visible && !window.__ARLS_FILE_API_PROBE_ROUTE_VISIBLE_MS__) {
        window.__ARLS_FILE_API_PROBE_ROUTE_VISIBLE_MS__ = performance.now() - startMs;
      }
      return visible;
    };
    const observer = new MutationObserver(() => {
      if (markVisible()) observer.disconnect();
    });
    observer.observe(document.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: ["class", "style", "aria-busy"] });
    requestAnimationFrame(() => {
      if (markVisible()) observer.disconnect();
    });
    window.setTimeout(() => observer.disconnect(), 5000);
    window.location.hash = nextHash;
    markVisible();
  }, { nextHash: hash, targetSelector: selector });
}

async function measureRoute(page, spec, config) {
  await resetNetworkCapture(page);
  await triggerRoute(page, spec.hash, spec.selector);
  try {
    await page.waitForFunction(({ selector }) => Array.from(document.querySelectorAll(selector)).some((node) => {
      if (!(node instanceof HTMLElement)) return false;
      const style = window.getComputedStyle(node);
      const rect = node.getBoundingClientRect();
      return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
    }), { selector: spec.selector }, { timeout: config.visibleTimeoutMs });
    const firstVisibleMs = await page.evaluate(() => Number(window.__ARLS_FILE_API_PROBE_ROUTE_VISIBLE_MS__ || 0) || (performance.now() - Number(window.__ARLS_FILE_API_PROBE_ROUTE_START_MS__ || performance.now())));
    const quiet = await waitForApiQuiet(page, config);
    const state = await page.evaluate(({ selector }) => {
      const net = window.__ARLS_FILE_API_PROBE_NET__ || { requests: [], errors: [] };
      const loginVisible = Boolean(document.querySelector("#loginPanel:not(.hidden), #loginForm:not(.hidden), [data-auth-view='login']:not(.hidden)"));
      return {
        browserHash: window.location.hash,
        bodyCurrentView: document.body?.dataset?.currentView || "",
        loginVisible,
        expectedVisible: Boolean(document.querySelector(selector)),
        requestCount: net.requests.length,
        requests: net.requests.slice(),
        networkErrors: net.errors.slice(),
      };
    }, { selector: spec.selector });
    const families = summarizeRequestFamilies(state.requests, config.duplicateThreshold);
    return {
      ...spec,
      firstVisibleMs,
      apiSettledTimedOut: quiet.timedOut,
      apiSettleOk: !quiet.timedOut,
      apiQuietError: quiet.error || "",
      authBlocked: Boolean(state.loginVisible && !state.expectedVisible),
      requestCount: state.requestCount,
      requestFamilies: families,
      networkErrors: state.networkErrors,
      browserHash: state.browserHash,
      bodyCurrentView: state.bodyCurrentView,
      ok: firstVisibleMs <= config.thresholdMs && !(state.loginVisible && !state.expectedVisible),
    };
  } catch (error) {
    return { ...spec, ok: false, error: String(error?.message || error).split("\n")[0] };
  }
}

async function inspectUiFlow(page, spec, config) {
  const route = await measureRoute(page, spec, config);
  const probes = await page.evaluate(({ probeSpecs }) => probeSpecs.map((probe) => {
    const nodes = Array.from(document.querySelectorAll(probe.selector));
    const first = nodes[0];
    return {
      name: probe.name,
      selector: probe.selector,
      count: nodes.length,
      exists: nodes.length > 0,
      disabled: probe.inspectDisabled ? Boolean(first?.disabled || first?.getAttribute?.("aria-disabled") === "true") : undefined,
      text: probe.inspectDisabled ? String(first?.textContent || "").trim().replace(/\s+/g, " ").slice(0, 120) : undefined,
    };
  }), { probeSpecs: spec.probes || [] }).catch((error) => [{ name: "probe-error", error: String(error?.message || error) }]);
  return { ...route, probes, ok: route.ok };
}

function summarizeRequestFamilies(requests, duplicateThreshold) {
  const byFamily = new Map();
  for (const request of requests || []) {
    const family = normalizeRequestFamily(request.url);
    const current = byFamily.get(family) || { family, count: 0, statuses: {}, totalMs: 0, maxMs: 0, errors: 0, examples: [] };
    current.count += 1;
    current.totalMs += Number(request.durationMs || 0);
    current.maxMs = Math.max(current.maxMs, Number(request.durationMs || 0));
    const status = String(request.status || "unknown");
    current.statuses[status] = (current.statuses[status] || 0) + 1;
    if (Number(request.status || 0) >= 400) current.errors += 1;
    if (current.examples.length < 2) current.examples.push(String(request.url || ""));
    byFamily.set(family, current);
  }
  return Array.from(byFamily.values())
    .map((row) => ({ ...row, avgMs: row.count ? row.totalMs / row.count : 0, duplicate: row.count > duplicateThreshold, has429: Boolean(row.statuses["429"]) }))
    .sort((a, b) => b.count - a.count || b.maxMs - a.maxMs);
}

function normalizeRequestFamily(rawUrl) {
  try {
    const url = new URL(String(rawUrl || ""), "https://placeholder.local");
    const pathName = url.pathname.replace(/\/[0-9a-f]{8}-[0-9a-f-]{27,}/gi, "/:uuid").replace(/\/\d+(?=\/|$)/g, "/:id");
    const keepParams = ["month", "site_code", "tenant_code", "tab", "segment"];
    const kept = keepParams
      .filter((key) => url.searchParams.has(key))
      .map((key) => `${key}=${url.searchParams.get(key)}`)
      .join("&");
    return kept ? `${pathName}?${kept}` : pathName;
  } catch {
    return String(rawUrl || "unknown").split("?")[0] || "unknown";
  }
}

async function runBrowserProbes(config) {
  const playwright = await importPlaywright();
  const contextOptions = {};
  if (config.storageState) contextOptions.storageState = config.storageState;
  const browser = await playwright.chromium.launch({ headless: !config.headful });
  const context = await browser.newContext({ ...contextOptions, acceptDownloads: true });
  const page = await context.newPage();
  await addNetworkCapture(page);
  const consoleMessages = [];
  page.on("console", (msg) => {
    if (["error", "warning"].includes(msg.type())) consoleMessages.push({ type: msg.type(), text: msg.text() });
  });
  try {
    await page.goto(config.baseUrl, { waitUntil: "domcontentloaded", timeout: 30_000 });
    await page.waitForLoadState("networkidle", { timeout: 10_000 }).catch(() => {});
    const backgroundRoutes = [];
    const uiFlows = [];
    if (config.only !== "browser") {
      for (const spec of BACKGROUND_ROUTE_SPECS) backgroundRoutes.push(await measureRoute(page, spec, config));
    }
    if (config.only !== "background") {
      for (const spec of SAFE_UI_FLOW_SPECS) uiFlows.push(await inspectUiFlow(page, spec, config));
    }
    return { backgroundRoutes, uiFlows, consoleMessages };
  } finally {
    await context.close();
    await browser.close();
  }
}

function buildDryRunReport(config) {
  return {
    generatedAt: new Date().toISOString(),
    dryRun: true,
    ok: true,
    config: publicConfig(config),
    safeApiSpecs: buildSafeApiSpecs(config).map((spec) => ({ ...spec, url: redactUrl(buildUrl(config.apiBase, spec)) })),
    backgroundRouteSpecs: BACKGROUND_ROUTE_SPECS,
    safeUiFlowSpecs: SAFE_UI_FLOW_SPECS,
    note: "Dry run only: no network/browser timing was measured.",
  };
}

function publicConfig(config) {
  return {
    baseUrl: config.baseUrl,
    apiBase: config.apiBase,
    storageState: config.storageState ? "provided" : "not-provided",
    output: config.output,
    month: config.month,
    tenantCode: config.tenantCode,
    siteCode: config.siteCode,
    supportScope: config.supportScope,
    apiQuietMs: config.apiQuietMs,
    apiTimeoutMs: config.apiTimeoutMs,
    visibleTimeoutMs: config.visibleTimeoutMs,
    thresholdMs: config.thresholdMs,
    maxDownloadBytes: config.maxDownloadBytes,
    duplicateThreshold: config.duplicateThreshold,
    approvalPolicyWarnMs: config.approvalPolicyWarnMs,
    hrDocumentType: config.hrDocumentType,
    only: config.only || "all",
    includeStatefulDownloads: config.includeStatefulDownloads,
  };
}

function buildReportMarkdown(report) {
  const lines = [
    "# ARLS File/API Performance Probe",
    "",
    `- Generated: ${report.generatedAt}`,
    `- Overall: ${report.ok ? "PASS" : "FAIL"}`,
    `- Dry run: ${report.dryRun ? "yes" : "no"}`,
    `- Base URL: ${report.config.baseUrl}`,
    `- API base: ${report.config.apiBase}`,
    `- Month/Tenant/Site: ${report.config.month} / ${report.config.tenantCode} / ${report.config.siteCode}`,
    "",
  ];
  if (report.storageStateError) lines.push(`- Storage state warning: ${report.storageStateError}`, "");
  if (report.directApi) {
    lines.push("## Safe direct API/file-operation probes", "", "| id | kind | status | totalMs | bytes | result | notes |", "| --- | --- | ---: | ---: | ---: | --- | --- |");
    for (const row of report.directApi.results || []) {
      const perfNote = row.performanceOk === false ? `over ${formatMs(row.performanceWarnMs)} warning` : "";
      const notes = [row.error, perfNote, row.authBlocked ? "auth/permission-blocked" : "", row.note].filter(Boolean).join("; ");
      lines.push(`| ${row.id} | ${row.kind || "-"} | ${row.status ?? "-"} | ${formatMs(row.totalMs)} | ${row.bytesRead ?? "-"}${row.truncated ? "+" : ""} | ${row.ok ? "PASS" : "FAIL"} | ${escapeCell(notes)} |`);
    }
    lines.push("");
  }
  if (report.focusedHomeHr) {
    lines.push("## Focused Home/HR performance summary", "");
    const home = report.focusedHomeHr.home || {};
    lines.push(`- Home attendance-records requests: ${home.attendanceRecordsRequestCount ?? 0} (${home.classification || "unknown"}); total Home requests: ${home.requestCount ?? 0}; api settle: ${home.apiSettleOk ? "PASS" : "TIMEOUT/UNKNOWN"}`);
    const hr = report.focusedHomeHr.hrApprovalPolicy || {};
    lines.push(`- HR approval-policy direct timing: ${formatMs(hr.directTotalMs)} (status ${hr.directStatus ?? "-"}, ${hr.classification || (hr.directPerformanceOk === false ? "over-warning-threshold" : "within/unknown-threshold")}); browser family requests: ${hr.browserRequestCount ?? 0}`);
    lines.push("");
  }
  if (report.browser?.backgroundRoutes?.length) {
    lines.push("## Background API settle routes", "", "| id | firstVisibleMs | requests | duplicate families | 429 families | result | notes |", "| --- | ---: | ---: | ---: | ---: | --- | --- |");
    for (const row of report.browser.backgroundRoutes) {
      const duplicates = (row.requestFamilies || []).filter((item) => item.duplicate).length;
      const has429 = (row.requestFamilies || []).filter((item) => item.has429).length;
      lines.push(`| ${row.id} | ${formatMs(row.firstVisibleMs)} | ${row.requestCount ?? 0} | ${duplicates} | ${has429} | ${row.ok ? "PASS" : "FAIL"} | ${escapeCell(row.error || (row.apiSettledTimedOut ? `api-settle-timeout: ${row.apiQuietError}` : "") || (row.authBlocked ? "auth/permission-blocked" : ""))} |`);
    }
    lines.push("");
  }
  if (report.browser?.uiFlows?.length) {
    lines.push("## Safe UI file-flow entry probes", "", "| id | firstVisibleMs | requests | probe counts | result | notes |", "| --- | ---: | ---: | --- | --- | --- |");
    for (const row of report.browser.uiFlows) {
      const counts = (row.probes || []).map((probe) => `${probe.name}:${probe.count ?? (probe.exists ? 1 : 0)}${probe.disabled === true ? " disabled" : ""}`).join(", ");
      lines.push(`| ${row.id} | ${formatMs(row.firstVisibleMs)} | ${row.requestCount ?? 0} | ${escapeCell(counts)} | ${row.ok ? "PASS" : "FAIL"} | ${escapeCell(row.error || row.apiQuietError || (row.authBlocked ? "auth/permission-blocked" : ""))} |`);
    }
    lines.push("");
  }
  if (report.directApi?.skipped?.length) {
    lines.push("## Skipped opt-in probes", "");
    for (const item of report.directApi.skipped) lines.push(`- ${item.id}: ${item.note || item.kind || "skipped"}`);
    lines.push("");
  }
  if (report.dryRun) {
    lines.push("## Dry-run plan", "", `- Safe API probes: ${report.safeApiSpecs?.length || 0}`, `- Background routes: ${report.backgroundRouteSpecs?.length || 0}`, `- UI flow probes: ${report.safeUiFlowSpecs?.length || 0}`, "");
  }
  return `${lines.join("\n")}\n`;
}

function buildFocusedHomeHrSummary(report) {
  const homeRoute = (report.browser?.backgroundRoutes || []).find((row) => row.id === "home");
  const hrRoute = (report.browser?.backgroundRoutes || []).find((row) => row.id === "hr");
  const hrDirect = (report.directApi?.results || []).find((row) => row.id === "hr-approval-policy");
  const homeAttendanceFamilies = filterRequestFamilies(homeRoute, "/attendance/records");
  const hrApprovalPolicyFamilies = filterRequestFamilies(hrRoute, "/admin/hr/documents/approval-policy");
  const attendanceRecordsRequestCount = sumFamilyCounts(homeAttendanceFamilies);
  const hrBrowserRequestCount = sumFamilyCounts(hrApprovalPolicyFamilies);
  return {
    home: {
      routeObserved: Boolean(homeRoute),
      requestCount: homeRoute?.requestCount ?? 0,
      firstVisibleMs: homeRoute?.firstVisibleMs,
      apiSettleOk: homeRoute ? Boolean(homeRoute.apiSettleOk) : false,
      attendanceRecordsRequestCount,
      attendanceRecordsFamilies: homeAttendanceFamilies,
      classification: classifyHomeAttendanceFanout(attendanceRecordsRequestCount),
    },
    hrApprovalPolicy: {
      routeObserved: Boolean(hrRoute),
      directObserved: Boolean(hrDirect),
      directStatus: hrDirect?.status,
      directHeaderMs: hrDirect?.headerMs,
      directTotalMs: hrDirect?.totalMs,
      directPerformanceOk: hrDirect?.performanceOk,
      performanceWarnMs: hrDirect?.performanceWarnMs,
      browserRequestCount: hrBrowserRequestCount,
      browserFamilies: hrApprovalPolicyFamilies,
      browserMaxMs: hrApprovalPolicyFamilies.reduce((max, family) => Math.max(max, Number(family.maxMs || 0)), 0),
      classification: classifyHrApprovalPolicyTiming(hrDirect, hrBrowserRequestCount),
    },
  };
}

function filterRequestFamilies(route, needle) {
  return (route?.requestFamilies || []).filter((family) => String(family.family || "").includes(needle));
}

function sumFamilyCounts(families) {
  return (families || []).reduce((sum, family) => sum + Number(family.count || 0), 0);
}

function classifyHomeAttendanceFanout(count) {
  if (count <= 0) return "not-observed";
  if (count === 1) return "single-request";
  return "fanout-or-repeated-request";
}

function classifyHrApprovalPolicyTiming(row, browserRequestCount) {
  if (!row && browserRequestCount <= 0) return "not-observed";
  if (row?.error) return "fetch-failed-or-unavailable";
  if (row?.authBlocked) return "auth-or-role-blocked";
  if (row?.performanceOk === false) return "over-warning-threshold";
  return "measured";
}

function formatMs(value) {
  return Number.isFinite(value) ? value.toFixed(1) : "-";
}

function escapeCell(value) {
  return String(value || "").replaceAll("|", "\\|").replace(/\s+/g, " ").trim();
}

async function writeReport(outputPath, report) {
  await fs.mkdir(path.dirname(outputPath), { recursive: true });
  await fs.writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  const markdownPath = outputPath.replace(/\.json$/i, ".md");
  await fs.writeFile(markdownPath, buildReportMarkdown(report), "utf8");
  return { json: outputPath, markdown: markdownPath };
}

async function run(config) {
  if (config.dryRun) return buildDryRunReport(config);
  const storage = await loadStorageState(config.storageState);
  const report = {
    generatedAt: new Date().toISOString(),
    dryRun: false,
    config: publicConfig(config),
    storageStateError: storage.error,
    directApi: { results: [], skipped: [] },
    browser: { backgroundRoutes: [], uiFlows: [], consoleMessages: [] },
  };
  if (!config.includeStatefulDownloads) report.directApi.skipped = STATEFUL_SAFE_ENDPOINTS;
  if (config.only !== "browser" && config.only !== "background") {
    report.directApi.results = await runSafeApiProbes(config, storage.accessToken);
  }
  if (config.only !== "api") {
    report.browser = await runBrowserProbes(config);
  }
  const directOk = (report.directApi.results || []).every((item) => item.ok);
  const backgroundOk = (report.browser.backgroundRoutes || []).every((item) => item.ok && !(item.requestFamilies || []).some((family) => family.has429));
  const uiOk = (report.browser.uiFlows || []).every((item) => item.ok);
  report.focusedHomeHr = buildFocusedHomeHrSummary(report);
  report.ok = directOk && backgroundOk && uiOk;
  return report;
}

const config = parseArgs(process.argv.slice(2));
const report = await run(config);
const written = await writeReport(config.output, report);
console.log(JSON.stringify({ ok: report.ok, output: written, generatedAt: report.generatedAt, dryRun: report.dryRun }, null, 2));
if (!report.ok && !config.softFail) process.exit(1);
