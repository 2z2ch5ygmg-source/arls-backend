#!/usr/bin/env node
/**
 * ARLS instant tab-latency verification probe.
 *
 * Usage:
 *   # Authenticated run against a deployed or local ARLS frontend:
 *   ARLS_PROBE_BASE_URL="https://host.example/index.html" \
 *     node qa/arls-instant-tab-latency-probe.mjs \
 *       --storage-state output/auth-state.json \
 *       --output output/arls-instant-tab-latency/probe.json
 *
 *   # Print route/action matrix without launching a browser:
 *   node qa/arls-instant-tab-latency-probe.mjs --dry-run
 *
 * The probe intentionally splits route shell visibility from API-settled timing:
 * - firstVisibleMs: route hash trigger -> target panel/shell/cache/skeleton visible.
 * - apiSettledMs: route hash trigger -> fetch/XHR quiet window after visibility.
 *
 * It also includes a rapid route-change stale-task race probe. The race check does
 * not force destructive actions; it verifies that route A background work cannot
 * move the browser off route B, reveal the wrong active panel, leave route B with
 * stale loading state, or emit route-entry errors after route B is active.
 */

import fs from "node:fs/promises";
import path from "node:path";
const DEFAULT_THRESHOLD_MS = 200;
const DEFAULT_API_QUIET_MS = 350;
const DEFAULT_API_TIMEOUT_MS = 15_000;
const DEFAULT_VISIBLE_TIMEOUT_MS = 5_000;
const DEFAULT_BETWEEN_ROUTES_MS = 100;

const PRIORITY_ROUTES = Object.freeze([
  { id: "home", hash: "#/home", view: "home", selector: "#view-home:not(.hidden)" },
  { id: "attendance", hash: "#/attendance", view: "attendance", selector: "#view-attendance:not(.hidden)" },
  { id: "requests", hash: "#/requests", view: "requests", selector: "#view-requests:not(.hidden)" },
  { id: "notices", hash: "#/feature/notices", view: "notices", selector: "#view-notices:not(.hidden)" },
  { id: "schedule-calendar", hash: "#/schedules/calendar", view: "schedule", selector: "#view-schedule:not(.hidden)" },
  { id: "schedule-list", hash: "#/schedules/list", view: "schedule", selector: "#view-schedule:not(.hidden)" },
  { id: "schedule-upload", hash: "#/schedules/upload", view: "schedule", selector: "#view-schedule:not(.hidden)" },
  { id: "schedule-hq-upload", hash: "#/schedules/hq-upload", view: "schedule", selector: "#view-schedule:not(.hidden)" },
  { id: "reports-finance", hash: "#/reports?tab=finance", view: "reports", selector: "#view-reports:not(.hidden)" },
  { id: "reports-finance-download", hash: "#/reports/finance-download", view: "reports", selector: "#view-reports:not(.hidden)" },
  { id: "employees", hash: "#/branch/employees", view: "employees", selector: "#view-employees:not(.hidden)" },
  { id: "sites", hash: "#/branch/sites", view: "org", selector: "#view-org:not(.hidden)" },
  { id: "leave", hash: "#/leave", view: "leave", selector: "#view-leave:not(.hidden)" },
  { id: "profile", hash: "#/profile", view: "profile", selector: "#view-profile:not(.hidden)" },
  { id: "ops", hash: "#/ops", view: "ops", selector: "#view-ops:not(.hidden)" },
  { id: "support-workers", hash: "#/ops/support-workers", view: "support-status", selector: "#view-support-status:not(.hidden)" },
  { id: "calendar-month", hash: "#/calendar/month", view: "calendar", selector: "#view-calendar:not(.hidden)" },
  { id: "hr", hash: "#/hr", view: "hr", selector: "#view-hr:not(.hidden)" },
]);

const PRE_ACTION_SHELLS = Object.freeze([
  {
    id: "finance-download-workspace-entry",
    hash: "#/reports/finance-download",
    view: "reports",
    selector: "#view-reports:not(.hidden) [data-reports-panel='finance-download'], #view-reports:not(.hidden) .reports-finance-download-panel, #view-reports:not(.hidden)",
  },
  {
    id: "schedule-upload-workspace-entry",
    hash: "#/schedules/upload",
    view: "schedule",
    selector: "#view-schedule:not(.hidden) .schedule-upload-workspace, #view-schedule:not(.hidden)",
  },
  {
    id: "support-worker-upload-workspace-entry",
    hash: "#/schedules/hq-upload",
    view: "schedule",
    selector: "#view-schedule:not(.hidden) .support-status-hq-review-table, #view-schedule:not(.hidden) .schedule-support-upload-actions, #view-schedule:not(.hidden)",
  },
  {
    id: "employee-import-route-entry",
    hash: "#/branch/employees/import",
    view: "employees",
    selector: "#view-employees:not(.hidden) .employee-import-head, #view-employees:not(.hidden)",
  },
  {
    id: "calendar-week-switch-entry",
    hash: "#/calendar/week",
    view: "calendar",
    selector: "#view-calendar:not(.hidden) #calendarWorkspaceRoot, #view-calendar:not(.hidden)",
  },
  {
    id: "calendar-day-switch-entry",
    hash: "#/calendar/day",
    view: "calendar",
    selector: "#view-calendar:not(.hidden) #calendarWorkspaceRoot, #view-calendar:not(.hidden)",
  },
  {
    id: "profile-logs-segment-entry",
    hash: "#/profile?segment=logs",
    view: "profile",
    selector: "#view-profile:not(.hidden) [data-profile-segment-panel='logs'], #view-profile:not(.hidden)",
  },
]);

const TARGETED_PYTEST_COMMAND = Object.freeze([
  "python",
  "-m",
  "pytest",
  "tests/test_schedule_finance_download_workspace.py",
  "tests/test_schedule_finance_submission.py",
  "tests/test_schedule_import_raw_workbook_runtime.py",
  "tests/test_schedule_support_roundtrip.py",
  "tests/test_leave_router_runtime.py",
  "tests/test_leave_request_review_runtime.py",
  "tests/test_notice_permissions.py",
]);

const MUTATION_JOB_SMOKES = Object.freeze([
  "Finance final upload/download: progress/loading remains visible until the backend response completes; no success toast before completion.",
  "Schedule base upload: inspect/apply buttons stay busy through API completion and review state refreshes after completion.",
  "Support-worker HQ upload/download/apply: file/progress state stays honest while roundtrip APIs run and refreshed results match the backend response.",
  "Leave/request submit/apply/delete/final actions: destructive or state-changing success is only shown after the awaited API resolves.",
]);

function parseArgs(argv) {
  const args = {
    baseUrl: process.env.ARLS_PROBE_BASE_URL || "http://127.0.0.1:5500/frontend/index.html",
    output: process.env.ARLS_PROBE_OUTPUT || "output/arls-instant-tab-latency/probe.json",
    thresholdMs: Number(process.env.ARLS_FIRST_VISIBLE_THRESHOLD_MS || DEFAULT_THRESHOLD_MS),
    apiQuietMs: Number(process.env.ARLS_API_QUIET_MS || DEFAULT_API_QUIET_MS),
    apiTimeoutMs: Number(process.env.ARLS_API_TIMEOUT_MS || DEFAULT_API_TIMEOUT_MS),
    visibleTimeoutMs: Number(process.env.ARLS_VISIBLE_TIMEOUT_MS || DEFAULT_VISIBLE_TIMEOUT_MS),
    betweenRoutesMs: Number(process.env.ARLS_BETWEEN_ROUTES_MS || DEFAULT_BETWEEN_ROUTES_MS),
    storageState: process.env.ARLS_PLAYWRIGHT_STORAGE_STATE || "",
    headful: false,
    dryRun: false,
    softFail: false,
    only: "",
  };
  for (let i = 0; i < argv.length; i += 1) {
    const key = argv[i];
    const next = argv[i + 1];
    if (key === "--base-url") {
      args.baseUrl = next;
      i += 1;
    } else if (key === "--output") {
      args.output = next;
      i += 1;
    } else if (key === "--threshold-ms") {
      args.thresholdMs = Number(next);
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
    } else if (key === "--between-routes-ms") {
      args.betweenRoutesMs = Number(next);
      i += 1;
    } else if (key === "--storage-state") {
      args.storageState = next;
      i += 1;
    } else if (key === "--only") {
      args.only = next;
      i += 1;
    } else if (key === "--headful") {
      args.headful = true;
    } else if (key === "--dry-run") {
      args.dryRun = true;
    } else if (key === "--soft-fail") {
      args.softFail = true;
    } else if (key === "--help" || key === "-h") {
      printHelpAndExit();
    }
  }
  if (!Number.isFinite(args.thresholdMs) || args.thresholdMs <= 0) {
    throw new Error("--threshold-ms must be a positive number");
  }
  return args;
}

function printHelpAndExit() {
  console.log(`ARLS instant tab-latency probe\n\nOptions:\n  --base-url <url>          Frontend URL (default ARLS_PROBE_BASE_URL or local index)\n  --storage-state <path>    Playwright auth storage state JSON\n  --output <path>           JSON report path\n  --threshold-ms <n>        firstVisibleMs pass threshold (default ${DEFAULT_THRESHOLD_MS})\n  --api-quiet-ms <n>        fetch/XHR quiet window for apiSettledMs\n  --api-timeout-ms <n>      API-settled wait timeout\n  --visible-timeout-ms <n>  target selector wait timeout\n  --between-routes-ms <n>   pause between matrix route triggers (default ${DEFAULT_BETWEEN_ROUTES_MS})\n  --only <routes|actions|race>\n  --headful                 show browser\n  --soft-fail               write failures but exit 0\n  --dry-run                 print matrix only\n`);
  process.exit(0);
}

function buildReportMarkdown(report) {
  const lines = [
    "# ARLS Instant Tab Latency Probe Report",
    "",
    `- Base URL: ${report.config.baseUrl}`,
    `- Threshold: ${report.config.thresholdMs}ms first-visible`,
    `- Generated: ${report.generatedAt}`,
    `- Overall: ${report.ok ? "PASS" : "FAIL"}`,
    "",
    "## First-visible routes",
    "",
    "| id | route | firstVisibleMs | apiSettledMs | shellKind | status | notes |",
    "| --- | --- | ---: | ---: | --- | --- | --- |",
  ];
  for (const row of report.firstVisible.routes) {
    lines.push(formatResultRow(row));
  }
  lines.push("", "## Pre-action shells", "", "| id | route | firstVisibleMs | apiSettledMs | shellKind | status | notes |", "| --- | --- | ---: | ---: | --- | --- | --- |");
  for (const row of report.firstVisible.preActions) {
    lines.push(formatResultRow(row));
  }
  lines.push("", "## Stale-task race", "");
  const race = report.race;
  lines.push(`- Status: ${race.ok ? "PASS" : "FAIL"}`);
  lines.push(`- Route A: ${race.routeA?.hash || "-"}`);
  lines.push(`- Route B: ${race.routeB?.hash || "-"}`);
  if (race.errors?.length) {
    lines.push(`- Errors: ${race.errors.join("; ")}`);
  }
  lines.push("", "## Targeted pytest", "", "```bash", TARGETED_PYTEST_COMMAND.join(" "), "```", "", "## Mutation/job smoke checks", "");
  for (const item of MUTATION_JOB_SMOKES) lines.push(`- ${item}`);
  return `${lines.join("\n")}\n`;
}

function formatResultRow(row) {
  const first = Number.isFinite(row.firstVisibleMs) ? row.firstVisibleMs.toFixed(1) : "-";
  const settled = Number.isFinite(row.apiSettledMs) ? row.apiSettledMs.toFixed(1) : "-";
  const notes = [row.error, row.apiSettledTimedOut ? "api-settle-timeout" : "", row.authBlocked ? "auth/permission-blocked" : ""]
    .filter(Boolean)
    .join("; ")
    .replaceAll("|", "\\|");
  return `| ${row.id} | ${row.hash} | ${first} | ${settled} | ${row.shellKind || "-"} | ${row.ok ? "PASS" : "FAIL"} | ${notes} |`;
}

async function addProbeInitScript(page) {
  await page.addInitScript(() => {
    const now = () => (typeof performance !== "undefined" ? performance.now() : Date.now());
    const net = {
      inflight: 0,
      lastActivityAt: now(),
      requests: [],
      errors: [],
    };
    Object.defineProperty(window, "__ARLS_PROBE_NET__", {
      value: net,
      configurable: true,
    });
    const markActivity = () => {
      net.lastActivityAt = now();
    };
    const originalFetch = window.fetch;
    if (typeof originalFetch === "function") {
      window.fetch = async (...args) => {
        const url = String(args?.[0]?.url || args?.[0] || "");
        net.inflight += 1;
        markActivity();
        const startedAt = now();
        try {
          const response = await originalFetch(...args);
          net.requests.push({ url, ok: response.ok, status: response.status, durationMs: now() - startedAt });
          return response;
        } catch (error) {
          net.errors.push({ url, message: String(error?.message || error) });
          throw error;
        } finally {
          net.inflight = Math.max(0, net.inflight - 1);
          markActivity();
        }
      };
    }
    const OriginalXhr = window.XMLHttpRequest;
    if (typeof OriginalXhr === "function") {
      const originalOpen = OriginalXhr.prototype.open;
      const originalSend = OriginalXhr.prototype.send;
      OriginalXhr.prototype.open = function patchedOpen(method, url, ...rest) {
        this.__arlsProbeUrl = String(url || "");
        return originalOpen.call(this, method, url, ...rest);
      };
      OriginalXhr.prototype.send = function patchedSend(...args) {
        const url = this.__arlsProbeUrl || "";
        const startedAt = now();
        net.inflight += 1;
        markActivity();
        this.addEventListener("loadend", () => {
          net.requests.push({ url, ok: this.status < 400, status: this.status, durationMs: now() - startedAt, transport: "xhr" });
          net.inflight = Math.max(0, net.inflight - 1);
          markActivity();
        }, { once: true });
        return originalSend.apply(this, args);
      };
    }
  });
}

async function waitForApiQuiet(page, { quietMs, timeoutMs }) {
  const startMs = await page.evaluate(() => performance.now());
  try {
    await page.waitForFunction(
      ({ quietMs: waitQuietMs }) => {
        const net = window.__ARLS_PROBE_NET__;
        if (!net) return true;
        return Number(net.inflight || 0) === 0 && performance.now() - Number(net.lastActivityAt || 0) >= waitQuietMs;
      },
      { quietMs },
      { timeout: timeoutMs },
    );
    const endMs = await page.evaluate(() => performance.now());
    return { timedOut: false, elapsedMs: endMs - startMs };
  } catch (error) {
    return { timedOut: true, elapsedMs: null, error: String(error?.message || error) };
  }
}

async function isAuthenticatedOrRouted(page, spec) {
  return page.evaluate(({ expectedSelector }) => {
    const loginVisible = Boolean(
      document.querySelector(
        "#loginPanel:not(.hidden), #loginForm:not(.hidden), [data-auth-view='login']:not(.hidden)",
      ),
    );
    const expectedVisible = Boolean(document.querySelector(expectedSelector));
    const visiblePanels = Array.from(document.querySelectorAll(".view:not(.hidden)"))
      .map((el) => el.id)
      .filter(Boolean);
    return { loginVisible, expectedVisible, visiblePanels, hash: window.location.hash };
  }, { expectedSelector: spec.selector });
}

async function triggerRoute(page, hash, selector = "") {
  await page.evaluate(
    ({ nextHash, targetSelector }) => {
      const startMs = performance.now();
      window.__ARLS_PROBE_ROUTE_START_MS__ = startMs;
      window.__ARLS_PROBE_ROUTE_VISIBLE_MS__ = 0;
      window.__ARLS_PROBE_ROUTE_HASH__ = nextHash;
      const isVisible = () => {
        if (!targetSelector) return false;
        const nodes = Array.from(document.querySelectorAll(targetSelector));
        return nodes.some((node) => {
          if (!(node instanceof HTMLElement)) return false;
          const style = window.getComputedStyle(node);
          const rect = node.getBoundingClientRect();
          return (
            style.display !== "none" &&
            style.visibility !== "hidden" &&
            rect.width > 0 &&
            rect.height > 0
          );
        });
      };
      const markIfVisible = () => {
        if (!window.__ARLS_PROBE_ROUTE_VISIBLE_MS__ && isVisible()) {
          window.__ARLS_PROBE_ROUTE_VISIBLE_MS__ = performance.now() - startMs;
          return true;
        }
        return false;
      };
      const observer = new MutationObserver(() => {
        if (markIfVisible()) observer.disconnect();
      });
      observer.observe(document.documentElement, {
        attributes: true,
        childList: true,
        subtree: true,
        attributeFilter: ["class", "style", "aria-busy"],
      });
      requestAnimationFrame(() => {
        if (markIfVisible()) observer.disconnect();
      });
      window.setTimeout(() => observer.disconnect(), 5000);
      window.location.hash = nextHash;
      markIfVisible();
    },
    { nextHash: hash, targetSelector: selector },
  );
}

async function measureSpec(page, spec, config) {
  await triggerRoute(page, spec.hash, spec.selector);
  try {
    await page.waitForFunction(
      ({ selector }) => {
        const nodes = Array.from(document.querySelectorAll(selector));
        return nodes.some((node) => {
          if (!(node instanceof HTMLElement)) return false;
          const style = window.getComputedStyle(node);
          const rect = node.getBoundingClientRect();
          return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
        });
      },
      { selector: spec.selector },
      { timeout: config.visibleTimeoutMs },
    );
    const data = await page.evaluate(({ selector, expectedView }) => {
      const startMs = Number(window.__ARLS_PROBE_ROUTE_START_MS__ || performance.now());
      const panel = document.querySelector(selector)?.closest(".view") || document.querySelector(selector);
      const panelId = panel?.id || "";
      const shellKind = resolveShellKind(panel);
      const perf = window.__RG_ARLS_PERF__?.getViewRuntimeStats?.() || null;
      const errors = Array.from(document.querySelectorAll(".view-runtime-hint.state-error:not(.hidden), .toast.state-error, .toast.error, [role='alert']"))
        .map((node) => String(node.textContent || "").trim())
        .filter(Boolean)
        .slice(-5);
      return {
        firstVisibleMs:
          Number(window.__ARLS_PROBE_ROUTE_VISIBLE_MS__ || 0) ||
          performance.now() - startMs,
        shellKind,
        panelId,
        bodyCurrentView: document.body?.dataset?.currentView || "",
        browserHash: window.location.hash,
        perf,
        routeErrors: errors,
        expectedView,
      };

      function resolveShellKind(root) {
        if (!root) return "unknown";
        if (root.querySelector?.(".skeleton-row, .skeleton-list, [class*='skeleton'], [class*='loading-card']")) return "skeleton";
        if (root.querySelector?.(".view-runtime-hint:not(.hidden), [aria-busy='true']")) return "loading-shell";
        if (root.querySelector?.("[class*='cache'], [data-cache-state]")) return "cache-or-shell";
        return "shell";
      }
    }, { selector: spec.selector, expectedView: spec.view });
    const apiQuiet = await waitForApiQuiet(page, {
      quietMs: config.apiQuietMs,
      timeoutMs: config.apiTimeoutMs,
    });
    const authState = await isAuthenticatedOrRouted(page, spec);
    const authBlocked = Boolean(authState.loginVisible && !authState.expectedVisible);
    return {
      ...spec,
      ...data,
      apiSettledMs: Number.isFinite(apiQuiet.elapsedMs) ? data.firstVisibleMs + apiQuiet.elapsedMs : null,
      apiSettledTimedOut: apiQuiet.timedOut,
      loginVisible: Boolean(authState.loginVisible),
      expectedVisible: Boolean(authState.expectedVisible),
      authBlocked,
      ok: Number(data.firstVisibleMs) <= config.thresholdMs && !authBlocked,
      error: apiQuiet.timedOut ? `API quiet wait timed out after ${config.apiTimeoutMs}ms` : "",
    };
  } catch (error) {
    const authState = await isAuthenticatedOrRouted(page, spec).catch(() => ({}));
    return {
      ...spec,
      ok: false,
      firstVisibleMs: null,
      apiSettledMs: null,
      apiSettledTimedOut: false,
      shellKind: "not-visible",
      authBlocked: Boolean(authState.loginVisible),
      error: String(error?.message || error).split("\n")[0],
      visiblePanels: authState.visiblePanels || [],
      browserHash: authState.hash || "",
    };
  }
}

async function runRaceProbe(page, config) {
  const routeA = PRIORITY_ROUTES.find((item) => item.id === "requests");
  const routeB = PRIORITY_ROUTES.find((item) => item.id === "profile");
  const errors = [];
  await triggerRoute(page, routeA.hash, routeA.selector);
  await page.waitForTimeout(50);
  await triggerRoute(page, routeB.hash, routeB.selector);
  const bVisible = await measureSpec(page, routeB, config);
  await page.waitForTimeout(1_250);
  const finalState = await page.evaluate(({ routeAHash, routeBHash }) => {
    const visiblePanels = Array.from(document.querySelectorAll(".view:not(.hidden)"))
      .map((node) => node.id)
      .filter(Boolean);
    const activeBusyPanels = visiblePanels.filter((id) => document.getElementById(id)?.getAttribute("aria-busy") === "true");
    const routeErrors = Array.from(document.querySelectorAll(".view-runtime-hint.state-error:not(.hidden), .toast.state-error, .toast.error, [role='alert']"))
      .map((node) => String(node.textContent || "").trim())
      .filter(Boolean)
      .slice(-8);
    const perf = window.__RG_ARLS_PERF__?.getViewRuntimeStats?.() || null;
    return {
      hash: window.location.hash,
      routeAHash,
      routeBHash,
      visiblePanels,
      activeBusyPanels,
      bodyCurrentView: document.body?.dataset?.currentView || "",
      routeErrors,
      activeScreenPerf: perf?.activeScreenPerf || null,
      lastScreenPerf: perf?.lastScreenPerf || {},
    };
  }, { routeAHash: routeA.hash, routeBHash: routeB.hash });

  if (!String(finalState.hash || "").includes(routeB.hash.replace(/^#/, ""))) {
    errors.push(`final hash is ${finalState.hash}, expected ${routeB.hash}`);
  }
  if (!finalState.visiblePanels.includes("view-profile")) {
    errors.push(`route B panel not visible; visible panels=${finalState.visiblePanels.join(",")}`);
  }
  if (finalState.visiblePanels.includes("view-requests")) {
    errors.push("stale route A panel is visible after route B");
  }
  if (finalState.routeErrors.length) {
    errors.push(`route-entry errors visible after route B: ${finalState.routeErrors.join(" | ")}`);
  }
  const activeRoute = String(finalState.activeScreenPerf?.route || "");
  if (activeRoute && activeRoute.includes("/requests")) {
    errors.push(`stale active perf session remained on ${activeRoute}`);
  }
  return {
    ok: errors.length === 0 && bVisible.ok,
    routeA,
    routeB,
    routeBFirstVisible: bVisible,
    finalState,
    errors,
  };
}

async function runProbe(config) {
  let playwright;
  try {
    playwright = await import("playwright");
  } catch (error) {
    throw new Error(`Playwright is not available: ${String(error?.message || error)}`);
  }
  const browser = await playwright.chromium.launch({ headless: !config.headful });
  const contextOptions = {};
  if (config.storageState) contextOptions.storageState = config.storageState;
  const context = await browser.newContext(contextOptions);
  const page = await context.newPage();
  await addProbeInitScript(page);

  const consoleErrors = [];
  page.on("console", (msg) => {
    if (["error", "warning"].includes(msg.type())) {
      consoleErrors.push({ type: msg.type(), text: msg.text() });
    }
  });

  try {
    await page.goto(config.baseUrl, { waitUntil: "domcontentloaded", timeout: 30_000 });
    await page.waitForLoadState("networkidle", { timeout: 10_000 }).catch(() => {});
    const routeSpecs = config.only === "actions" || config.only === "race" ? [] : PRIORITY_ROUTES;
    const actionSpecs = config.only === "routes" || config.only === "race" ? [] : PRE_ACTION_SHELLS;
    const routeResults = [];
    const actionResults = [];
    for (const spec of routeSpecs) {
      if (routeResults.length && config.betweenRoutesMs > 0) {
        await page.waitForTimeout(config.betweenRoutesMs);
      }
      routeResults.push(await measureSpec(page, spec, config));
    }
    for (const spec of actionSpecs) {
      if (actionResults.length && config.betweenRoutesMs > 0) {
        await page.waitForTimeout(config.betweenRoutesMs);
      }
      actionResults.push(await measureSpec(page, spec, config));
    }
    const race = config.only === "routes" || config.only === "actions" ? { ok: true, skipped: true } : await runRaceProbe(page, config);
    const report = {
      generatedAt: new Date().toISOString(),
      config: {
        baseUrl: config.baseUrl,
        thresholdMs: config.thresholdMs,
        apiQuietMs: config.apiQuietMs,
        apiTimeoutMs: config.apiTimeoutMs,
        visibleTimeoutMs: config.visibleTimeoutMs,
        betweenRoutesMs: config.betweenRoutesMs,
        storageState: config.storageState ? "provided" : "not-provided",
      },
      firstVisible: {
        routes: routeResults,
        preActions: actionResults,
      },
      race,
      targetedPytestCommand: TARGETED_PYTEST_COMMAND,
      mutationJobSmokes: MUTATION_JOB_SMOKES,
      consoleErrors,
    };
    report.ok = [...routeResults, ...actionResults].every((item) => item.ok) && race.ok;
    return report;
  } finally {
    await context.close();
    await browser.close();
  }
}

async function writeReport(outputPath, report) {
  await fs.mkdir(path.dirname(outputPath), { recursive: true });
  await fs.writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  const mdPath = outputPath.replace(/\.json$/i, ".md");
  await fs.writeFile(mdPath, buildReportMarkdown(report), "utf8");
  return { json: outputPath, markdown: mdPath };
}

function printDryRun(config) {
  console.log(JSON.stringify({
    config,
    priorityRoutes: PRIORITY_ROUTES,
    preActionShells: PRE_ACTION_SHELLS,
    targetedPytestCommand: TARGETED_PYTEST_COMMAND,
    mutationJobSmokes: MUTATION_JOB_SMOKES,
  }, null, 2));
}

const config = parseArgs(process.argv.slice(2));
if (config.dryRun) {
  printDryRun(config);
  process.exit(0);
}

const report = await runProbe(config);
const written = await writeReport(config.output, report);
console.log(JSON.stringify({ ok: report.ok, output: written, generatedAt: report.generatedAt }, null, 2));
if (!report.ok && !config.softFail) process.exit(1);
