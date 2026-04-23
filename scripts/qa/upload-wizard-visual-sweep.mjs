#!/usr/bin/env node
/**
 * Geometry-aware visual sweep for ARLS upload wizards.
 *
 * Captures schedule upload, support-worker upload, and Finance submission at
 * required desktop/laptop widths. The manifest is the completion evidence for
 * the unified wizard shell contract.
 */

import fs from "node:fs/promises";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const REPO_ROOT = path.resolve(__dirname, "../..");

const VIEWPORTS = Object.freeze({
  desktop: { width: 1366, height: 900 },
  "768": { width: 768, height: 1024 },
  "375": { width: 375, height: 812 },
});

const ROUTE_STATES = Object.freeze([
  { route: "/schedules/upload", flow: "schedule", stateKey: "mapping" },
  { route: "/schedules/upload", flow: "schedule", stateKey: "file" },
  { route: "/schedules/upload", flow: "schedule", stateKey: "review" },
  { route: "/schedules/upload", flow: "schedule", stateKey: "review", paginationPage: 2 },
  { route: "/schedules/upload", flow: "schedule", stateKey: "apply" },
  { route: "/schedules/hq-upload", flow: "hq", stateKey: "export" },
  { route: "/schedules/hq-upload", flow: "hq", stateKey: "upload" },
  { route: "/schedules/hq-upload", flow: "hq", stateKey: "preview" },
  { route: "/schedules/hq-upload", flow: "hq", stateKey: "preview", paginationPage: 2 },
  { route: "/schedules/hq-upload", flow: "hq", stateKey: "complete" },
  { route: "/schedules/hq-upload", flow: "hq", stateKey: "export", paginationPage: 2 },
]);

const SAMPLE_USER = Object.freeze({
  id: "wizard-sweep-user",
  username: "wizard-sweep",
  full_name: "Wizard Sweep Admin",
  role: "hq_admin",
  tenant_id: "tenant-srs-korea",
  tenant_code: "SRS_KOREA",
  tenant_name: "SRS Korea",
  employee_id: "emp-wizard-sweep",
  employee_code: "HQ001",
  site_id: "site-seoul",
  site_code: "SEOUL01",
});

const SAMPLE_REQUESTED_AT = "2026-04-13T09:12:00+09:00";

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

function todayDateKey() {
  return new Date().toISOString().slice(0, 10);
}

function makeJwt(user = SAMPLE_USER) {
  const encode = (obj) => Buffer.from(JSON.stringify(obj)).toString("base64url");
  return `${encode({ alg: "none", typ: "JWT" })}.${encode({
    sub: user.id,
    username: user.username,
    full_name: user.full_name,
    role: user.role,
    tenant_id: user.tenant_id,
    tenant_code: user.tenant_code,
    exp: Math.floor(Date.now() / 1000) + 24 * 60 * 60,
  })}.wizard-sweep`;
}

function sampleSites(count = 24) {
  const cityNames = [
    "서울",
    "부산",
    "대구",
    "인천",
    "광주",
    "대전",
    "울산",
    "수원",
    "성남",
    "고양",
    "용인",
    "청주",
    "천안",
    "전주",
  ];
  return Array.from({ length: count }, (_, index) => {
    const number = index + 1;
    const code = index === 0 ? "SEOUL01" : `SITE${String(number).padStart(2, "0")}`;
    const city = cityNames[index] || `지점 ${number}`;
    return {
      site_code: code,
      site_name: index === 0 ? "서울 센터" : `${city} 센터`,
      sheet_name: index === 0 ? "서울 센터" : `${city} 센터`,
      download_ready: true,
      selectable: true,
      source_state: "ready",
      source_revision: `source-wizard-${number}`,
      source_uploaded_at: SAMPLE_REQUESTED_AT,
      latest_status: "ready",
      latest_hq_revision: index === 0 ? "hq-wizard-1" : "",
      latest_hq_uploaded_at: index === 0 ? SAMPLE_REQUESTED_AT : "",
      hq_merge_stale: false,
      note: index === 0 ? "대표 지점" : "페이지네이션 검증용 지점입니다.",
    };
  });
}

function sampleBasePreviewRows(count = 36) {
  return Array.from({ length: count }, (_, index) => {
    if (index === 0) {
      return {
        row_no: 55,
        source_col: "U",
        schedule_date: "2026-04-18",
        section_label: "필요인원 수",
        source_block: "day_support_required_count",
        duty_type: "day_support",
        employee_code: "",
        employee_name: "",
        work_value: "",
        current_work_value: "",
        is_valid: false,
        is_blocking: true,
        action: "block",
        apply_action: "none",
        decision_stage: "block",
        status_label: "차단",
        validation_code: "SUPPORT_BLOCK_REQUIRED_COUNT_INVALID",
        validation_error:
          "필요 인원 수가 비어 있어 지원 요청 규모를 확정할 수 없습니다.",
      };
    }
    if (index === 1) {
      return {
        row_no: 54,
        source_col: "D",
        schedule_date: "2026-04-01",
        section_label: "외부인원 투입 수",
        source_block: "day_support_external_count",
        duty_type: "day_support",
        employee_code: "",
        employee_name: "",
        work_value: "미정",
        current_work_value: "",
        is_valid: false,
        is_blocking: false,
        action: "review",
        apply_action: "none",
        decision_stage: "review",
        status_label: "검토 필요",
        validation_code: "UNSUPPORTED_CELL_FORMAT",
        validation_error: "외부인원 투입 수를 숫자로 해석할 수 없습니다.",
      };
    }
    const rowNo = index + 1;
    const day = String((index % 28) + 1).padStart(2, "0");
    const shiftType = index % 3 === 0 ? "night" : "day";
    return {
      row_no: rowNo,
      source_col: "Q",
      schedule_date: `2026-04-${day}`,
      section_label: "기본 월간 업로드",
      source_block: "body",
      duty_type: shiftType,
      shift_type: shiftType,
      employee_code: `R${String(690 + rowNo).padStart(3, "0")}`,
      employee_name: `검증직원${rowNo}`,
      work_value: shiftType === "night" ? "야간" : "12",
      current_work_value: "",
      is_valid: true,
      is_blocking: false,
      action: "apply",
      apply_action: "upsert",
      decision_stage: "apply",
      status_label: "반영 예정",
      reason: "시각 검증 fixture",
    };
  });
}

function sampleHqReviewRows(count = 36) {
  return Array.from({ length: count }, (_, index) => {
    const rowNo = index + 1;
    const day = String((index % 28) + 1).padStart(2, "0");
    const shiftKind = index % 2 === 0 ? "day" : "night";
    return {
      sheet_name: `검증 시트 ${Math.floor(index / 6) + 1}`,
      site_code: `SITE${String((index % 24) + 1).padStart(2, "0")}`,
      site_name: `검증 센터 ${index + 1}`,
      work_date: `2026-04-${day}`,
      shift_kind: shiftKind,
      request_count: 2,
      valid_filled_count: 2,
      row_kind: "worker",
      parsed_display_value: `지원자${rowNo}`,
      target_status: "ready",
      status: "ready",
      reason: "",
    };
  });
}

function financeOverviewWorkspace() {
  const sites = sampleSites(12).map((site, index) => ({
    site_code: site.site_code,
    site_name: site.site_name,
    month: todayDateKey().slice(0, 7),
    submission_status: index % 2 === 0 ? "submitted" : "waiting_upload",
    submission_status_label: index % 2 === 0 ? "제출 완료" : "제출 대기",
    review_status: "ready",
    review_status_label: "1차 확인 가능",
    final_status: index === 0 ? "waiting_upload" : "not_uploaded",
    final_status_label: index === 0 ? "최종 업로드 대기" : "미업로드",
    last_updated_at: SAMPLE_REQUESTED_AT,
    blocked_reason: "",
  }));
  return {
    tenant_code: SAMPLE_USER.tenant_code,
    tenant_wide: true,
    month: todayDateKey().slice(0, 7),
    scope_label: "전체 지점",
    total_site_count: sites.length,
    submitted_site_count: 6,
    review_ready_site_count: 12,
    final_uploaded_site_count: 0,
    sites,
  };
}

function financeStatus() {
  return {
    site_code: "SEOUL01",
    month: todayDateKey().slice(0, 7),
    review_download_revision: "review-wizard-1",
    review_downloaded_at: SAMPLE_REQUESTED_AT,
    final_uploaded_at: "",
    final_upload_stale: false,
    blocked_reasons: [],
  };
}

function supportRoundtripHqWorkspace() {
  return {
    ok: true,
    month: todayDateKey().slice(0, 7),
    template_version: "wizard-sweep-v1",
    latest_artifact_id: "artifact-wizard-sweep-1",
    generated_at: SAMPLE_REQUESTED_AT,
    sites: sampleSites(14),
  };
}

function json(value, status = 200) {
  return { status, json: value };
}

function mockApiResponse(rawUrl, method = "GET", token = "") {
  const url = new URL(rawUrl);
  const lower = (url.pathname.replace(/^.*\/api(?:\/v1)?/, "") || "/")
    .replace(/\/+$/, "")
    .toLowerCase();
  if (lower === "/auth/me") return json(SAMPLE_USER);
  if (lower === "/auth/refresh")
    return json({ access_token: token, refresh_token: token, token, user: SAMPLE_USER });
  if (lower.startsWith("/auth/tenant-check"))
    return json({ ok: true, tenant_code: SAMPLE_USER.tenant_code, tenant_name: SAMPLE_USER.tenant_name });
  if (lower === "/companies")
    return json([{ id: SAMPLE_USER.tenant_id, tenant_code: SAMPLE_USER.tenant_code, tenant_name: SAMPLE_USER.tenant_name }]);
  if (lower === "/sites" || lower.startsWith("/sites?") || lower.startsWith("/dev/sites"))
    return json(sampleSites(14));
  if (lower.includes("/schedules/support-roundtrip/hq-workspace"))
    return json(supportRoundtripHqWorkspace());
  if (lower.includes("/schedules/finance-submission/overview-workspace"))
    return json(financeOverviewWorkspace());
  if (lower.includes("/schedules/finance-submission/status"))
    return json(financeStatus());
  if (lower.includes("schedule") || lower.includes("schedules"))
    return json({ rows: [], items: [], status: "ready", ok: true });
  if (method !== "GET") return json({ ok: true, id: "wizard-sweep-mock" });
  return json({ rows: [], items: [], data: [], total: 0, ok: true });
}

async function startStaticServer(rootDir) {
  const server = http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url || "/", "http://127.0.0.1");
      if (url.pathname.startsWith("/api/")) {
        res.writeHead(404, { "content-type": "application/json; charset=utf-8" });
        res.end(JSON.stringify({ detail: "API route should be mocked" }));
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
  return {
    origin: `http://127.0.0.1:${address.port}`,
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
    localStorage.setItem("rg-arls-session", JSON.stringify(session));
    localStorage.setItem("accessToken", sessionToken);
    localStorage.setItem("refreshToken", sessionToken);
    localStorage.setItem("rg-arls-ui-theme", "light");
    localStorage.setItem(
      "rg-arls-ui-active-tenant",
      JSON.stringify({ tenantId: user.tenant_id, tenantCode: user.tenant_code, tenantName: user.tenant_name }),
    );
  }, { sessionToken: token, user: SAMPLE_USER });
}

async function installApiMock(page, token, networkRows) {
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const response = mockApiResponse(request.url(), request.method(), token);
    const failed = Number(response.status || 200) >= 400;
    networkRows.push({
      url: request.url(),
      method: request.method(),
      status: response.status || 200,
      failed,
      mocked: true,
    });
    await route.fulfill({
      status: response.status || 200,
      contentType: "application/json; charset=utf-8",
      body: JSON.stringify(response.json ?? {}),
    });
  });
}

function buildUrl(baseUrl, apiBase, route) {
  const url = new URL(baseUrl);
  url.searchParams.set("api", apiBase);
  url.hash = route;
  return url.toString();
}

async function waitForWizard(page, flow) {
  const selector = flow === "finance"
    ? "#scheduleFinanceWizardView.arls-upload-wizard:not(.hidden)"
    : "#scheduleUploadPanel.arls-upload-wizard:not(.hidden)";
  await page.waitForSelector(selector, { state: "visible", timeout: 10000 });
}

async function prepareState(page, state) {
  if (state.flow === "schedule") {
    await waitForWizard(page, "schedule");
    if (state.stateKey === "mapping") {
      await page.waitForTimeout(350);
      return;
    }
    await page.evaluate(({ step, previewRows, page }) => {
      if (step === "review") {
        const blockedRows = previewRows.filter((row) => row?.is_blocking);
        const reviewRows = previewRows.filter(
          (row) =>
            !row?.is_blocking &&
            String(row?.decision_stage || "").toLowerCase() === "review",
        );
        const applyRows = previewRows.filter(
          (row) =>
            String(row?.decision_stage || "").toLowerCase() === "apply" &&
            !row?.is_blocking,
        );
        const issueExamples = blockedRows
          .concat(reviewRows)
          .map((row) => Number(row?.row_no || 0))
          .filter(Boolean)
          .slice(0, 3);
        const previewPayload = {
          preview_rows: previewRows,
          valid_rows: applyRows.length,
          applicable_rows: applyRows.length,
          warning_rows: reviewRows.length,
          invalid_rows: blockedRows.length,
          blocked_rows: blockedRows.length,
          blocked_reasons: blockedRows.length
            ? ["필요 인원 수가 비어 있어 지원 요청 규모를 확정할 수 없습니다."]
            : [],
          diff_counts: {
            create: applyRows.length,
            review: reviewRows.length,
            conflict: blockedRows.length,
          },
          issues: blockedRows.length
            ? [
                {
                  code: "SUPPORT_BLOCK_REQUIRED_COUNT_INVALID",
                  message:
                    "필요 인원 수가 비어 있어 지원 요청 규모를 확정할 수 없습니다.",
                  guidance: "필요 인원 수를 입력한 뒤 다시 분석하세요.",
                  count: blockedRows.length,
                  example_rows: issueExamples,
                },
              ]
            : [],
          metadata: { fixture: "long-preview" },
        };
        window.eval(`state.preview = ${JSON.stringify(previewPayload)}`);
        const uploadUi = window.getScheduleUploadUiState?.();
        if (uploadUi) {
          uploadUi.canApply = true;
          uploadUi.previewMode = page && page > 1 ? "all" : "actionable";
          uploadUi.previewPage = page || 1;
          uploadUi.previewPageSize = 20;
        }
        window.setScheduleImportUI?.({
          batchInfo: "검증 fixture",
          canApply: true,
          previewRows,
        });
      }
      if (step === "apply") {
        const uploadUi = window.getScheduleUploadUiState?.();
        if (uploadUi) {
          uploadUi.applyResult = "반영 완료";
          uploadUi.canApply = false;
        }
      }
      window.setScheduleBaseWizardStep?.(step, { scroll: false });
      window.renderScheduleUploadWorkspace?.();
      if (step === "review") {
        window.renderSchedulePreviewTable?.(previewRows);
      }
    }, {
      step: state.stateKey,
      previewRows: sampleBasePreviewRows(),
      page: state.paginationPage || 1,
    });
    await page.waitForTimeout(250);
    return;
  }
  if (state.flow === "hq") {
    await waitForWizard(page, "hq");
    await page.evaluate(({ step, reviewRows, page }) => {
      const workspace = window.ensureScheduleSupportHqWorkspaceState?.();
      if (workspace) {
        workspace.selectedSiteCodes = ["SEOUL01", "SITE02", "SITE03"];
        if (step === "upload") {
          workspace.uploadFileName = "hq-fixture.xlsx";
          workspace.contract = {
            latest_artifact_id: "artifact-fixture",
            template_version: "fixture-v1",
          };
        }
        if (step === "preview" || step === "complete") {
          workspace.uploadFileName = "hq-fixture.xlsx";
          workspace.inspectResult = {
            can_apply: true,
            next_step_message: "반영 가능합니다.",
            review_rows: reviewRows,
            scope_summaries: [],
          };
          workspace.previewMode = "all";
          workspace.previewPage = page || 1;
          workspace.previewPageSize = 20;
        }
        if (step === "complete") {
          workspace.applyResult = { applied_count: 20, skipped_count: 0 };
        }
      }
      window.setScheduleHqWizardStep?.(step, { scroll: false });
      window.renderScheduleUploadWorkspace?.();
      if (step === "preview" || step === "complete") {
        window.renderScheduleSupportHqReviewTable?.();
      }
    }, {
      step: state.stateKey,
      reviewRows: sampleHqReviewRows(),
      page: state.paginationPage || 1,
    });
    await page.waitForTimeout(350);
    if (state.paginationPage === 2 && state.stateKey === "export") {
      await page.evaluate(() => {
        const button = document.querySelector(
          '[data-action="schedule-support-hq-page"][data-page="2"]',
        );
        if (button instanceof HTMLElement) {
          button.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
        }
      });
      await page.waitForTimeout(250);
    }
    return;
  }
}

async function collectGeometry(page, flow) {
  return page.evaluate((targetFlow) => {
    const visible = (node) => {
      if (!(node instanceof HTMLElement)) return false;
      const style = window.getComputedStyle(node);
      const rect = node.getBoundingClientRect();
      return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0 && !node.classList.contains("hidden");
    };
    const shell =
      Array.from(document.querySelectorAll(".reference-upload-wizard")).find(visible) ||
      Array.from(document.querySelectorAll(".arls-upload-wizard")).find(visible);
    const referenceMode = Boolean(shell?.classList?.contains("reference-upload-wizard"));
    const content = document.querySelector(".shell-content") || document.body;
    const shellRect = shell?.getBoundingClientRect?.();
    const contentRect = content.getBoundingClientRect();
    const shellTitle = shell?.querySelector("#scheduleUploadHeaderTitle");
    const shellTitleRect = shellTitle?.getBoundingClientRect?.();
    const stepNodes = Array.from(shell?.querySelectorAll(".arls-upload-wizard__step, .reference-upload-step") || []).filter(visible);
    const circles = stepNodes.map((step) => {
      const marker = step.querySelector(".reference-upload-step span, .schedule-wizard-step-marker, .reports-panel-stepper-index");
      const rect = (marker || step).getBoundingClientRect();
      const label = step.querySelector(".reference-upload-step strong, .schedule-wizard-step-label, .reports-panel-stepper-label, .reports-panel-stepper-copy") || step;
      const labelRect = label.getBoundingClientRect();
      return {
        stateKey: step.dataset.stateKey || step.dataset.step || "",
        stepState: step.dataset.stepState || "",
        centerX: Math.round(rect.left + rect.width / 2),
        centerY: Math.round(rect.top + rect.height / 2),
        labelBox: {
          left: Math.round(labelRect.left),
          top: Math.round(labelRect.top),
          width: Math.round(labelRect.width),
          height: Math.round(labelRect.height),
        },
      };
    });
    const activeSteps = stepNodes
      .filter((step) => step.getAttribute("aria-current") === "step")
      .map((step) => step.dataset.stateKey || step.dataset.step || "")
      .filter(Boolean);
    const processActiveSteps = circles
      .filter((item) => item.stepState === "active")
      .map((item) => item.stateKey);
    const activeAxis = "x";
    let monotonic = true;
    let drift = 0;
    if (activeAxis === "x") {
      const centers = circles.map((item) => item.centerX);
      monotonic = centers.every((value, index) => index === 0 || value >= centers[index - 1]);
      const rows = circles.map((item) => item.centerY);
      drift = rows.length ? Math.max(...rows) - Math.min(...rows) : 0;
    } else {
      const yCenters = circles.map((item) => item.centerY);
      monotonic = yCenters.every((value, index) => index === 0 || value >= yCenters[index - 1]);
      const groupedRows = new Map();
      circles.forEach((item) => {
        const key = String(Math.round(item.centerY / 10) * 10);
        const row = groupedRows.get(key) || [];
        row.push(item.centerY);
        groupedRows.set(key, row);
      });
      drift = Array.from(groupedRows.values()).reduce((max, row) => {
        if (!row.length) return max;
        return Math.max(max, Math.max(...row) - Math.min(...row));
      }, 0);
    }
    const readPager = (selector) => {
      const node = shell?.querySelector(selector);
      if (!(node instanceof HTMLElement)) return null;
      return {
        id: node.id || "",
        visible: visible(node),
        page: node.dataset.page || "",
        pageSize: node.dataset.pageSize || "",
        totalItems: node.dataset.totalItems || "",
        totalPages: node.dataset.totalPages || "",
      };
    };
    const paginationPagers = [
      readPager("#schedulePreviewPager"),
      readPager("#scheduleSupportHqReviewPager"),
      readPager("#scheduleSupportHqPager"),
    ].filter(Boolean);
    const activePager =
      paginationPagers.find((item) => item.visible) || paginationPagers[0] || null;
    const footer = shell?.querySelector("#scheduleUploadFooterActions");
    const routeWideFooterVisible = footer instanceof HTMLElement ? visible(footer) : false;
    const mainCanvas = shell?.querySelector("#scheduleUploadMainCanvas") || shell;
    const visibleCards = Array.from(mainCanvas?.querySelectorAll("section, .reference-upload-stage, .reference-upload-card, .schedule-hq-site-selection-shell, .schedule-upload-progress, form") || [])
      .filter((node) => node instanceof HTMLElement && visible(node));
    const activeCard = visibleCards
      .filter((node) => node.querySelector?.(".schedule-source-actions button"))
      .sort((left, right) => right.getBoundingClientRect().height - left.getBoundingClientRect().height)[0] ||
      visibleCards[0] ||
      null;
    const activeCardRect = activeCard?.getBoundingClientRect?.();
    const actionRows = Array.from(activeCard?.querySelectorAll(".schedule-source-actions, .reference-upload-actions") || [])
      .filter((node) => node instanceof HTMLElement && visible(node));
    const inCardActions = actionRows.flatMap((row) =>
      Array.from(row.querySelectorAll("button") || [])
        .filter(visible)
        .map((button) => {
          const rect = button.getBoundingClientRect();
          const rowRect = row.getBoundingClientRect();
          return {
            label: String(button.textContent || "").trim(),
            dataAction: button.dataset.action || "",
            disabled: Boolean(button.disabled),
            id: button.id || "",
            placement:
              activeCardRect && rect.left < activeCardRect.left + activeCardRect.width / 2
                ? "left"
                : "right",
            datasetKeys: Object.keys(button.dataset || {}).sort(),
            box: {
              left: Math.round(rect.left),
              top: Math.round(rect.top),
              width: Math.round(rect.width),
              height: Math.round(rect.height),
            },
            rowBox: {
              left: Math.round(rowRect.left),
              top: Math.round(rowRect.top),
              width: Math.round(rowRect.width),
              height: Math.round(rowRect.height),
            },
          };
        }),
    );
    const footerActions = Array.from(footer?.querySelectorAll("button") || [])
      .filter(visible)
      .map((button) => {
        const rect = button.getBoundingClientRect();
        return {
          label: String(button.textContent || "").trim(),
          dataAction: button.dataset.action || "",
          disabled: Boolean(button.disabled),
          id: button.id || "",
          datasetKeys: Object.keys(button.dataset || {}).sort(),
          box: {
            left: Math.round(rect.left),
            top: Math.round(rect.top),
            width: Math.round(rect.width),
            height: Math.round(rect.height),
          },
        };
      });
    const visiblePanels = Array.from(document.querySelectorAll(".view:not(.hidden)"))
      .filter(visible)
      .map((node) => node.id || "unknown");
    return {
      flow: targetFlow,
      shellBox: shellRect ? {
        left: Math.round(shellRect.left),
        top: Math.round(shellRect.top),
        width: Math.round(shellRect.width),
        height: Math.round(shellRect.height),
      } : null,
      shellCenterDelta: shellRect
        ? Math.round((shellRect.left + shellRect.width / 2) - (contentRect.left + contentRect.width / 2))
        : null,
      shellTitle: shellTitle instanceof HTMLElement ? {
        visible: visible(shellTitle),
        text: String(shellTitle.textContent || "").trim(),
        box: shellTitleRect ? {
          left: Math.round(shellTitleRect.left),
          top: Math.round(shellTitleRect.top),
          width: Math.round(shellTitleRect.width),
          height: Math.round(shellTitleRect.height),
        } : null,
      } : null,
      stepCircleCenters: circles,
      activeSteps,
      processActiveSteps,
      circleAxis: activeAxis,
      circleCentersMonotonic: monotonic,
      circleRowOrColumnDrift: Math.round(drift),
      horizontalOverflow: document.documentElement.scrollWidth > window.innerWidth + 2,
      scrollWidth: document.documentElement.scrollWidth,
      innerWidth: window.innerWidth,
      visiblePanels,
      routePanelLeak: visiblePanels.length !== 1,
      pagination: activePager,
      paginationPagers,
      activeCard: activeCardRect ? {
        tagName: activeCard.tagName,
        id: activeCard.id || "",
        className: String(activeCard.className || ""),
        box: {
          left: Math.round(activeCardRect.left),
          top: Math.round(activeCardRect.top),
          width: Math.round(activeCardRect.width),
          height: Math.round(activeCardRect.height),
        },
      } : null,
      inCardActions,
      inCardActionEvidence: {
        routeWideFooterVisible,
        actionCount: inCardActions.length,
        allActionsHaveHooks: inCardActions.every((item) => Boolean(item.dataAction)),
        rowWithinCard: activeCardRect
          ? inCardActions.every((item) =>
              item.rowBox.left >= Math.floor(activeCardRect.left) &&
              item.rowBox.left + item.rowBox.width <= Math.ceil(activeCardRect.right || (activeCardRect.left + activeCardRect.width)),
            )
          : false,
        hasLeftPreviousWhenMultiple:
          inCardActions.length < 2 ||
          inCardActions.some((item) => item.placement === "left" && /(이전|취소)/.test(item.label)),
        hasRightPrimary:
          inCardActions.length > 0 &&
          inCardActions.some((item) => item.placement === "right"),
      },
      referenceMode,
      footerActions,
      footerActionDispatchEvidence: {
        visible: routeWideFooterVisible,
        actionCount: footerActions.length,
        allActionsHaveHooks: footerActions.every((item) => Boolean(item.dataAction)),
        clonedActionsAvoidDuplicateIds: footerActions.every((item) => !item.id),
      },
    };
  }, flow);
}

async function run() {
  const { chromium } = await import("playwright");
  const outputRoot = path.resolve(REPO_ROOT, "artifacts/upload-wizard-visual", kstTimestamp());
  await fs.mkdir(outputRoot, { recursive: true });
  const localServer = await startStaticServer(REPO_ROOT);
  const baseUrl = `${localServer.origin}/frontend/index.html`;
  const token = makeJwt();
  const browser = await chromium.launch({ headless: true });
  const manifest = {
    schemaVersion: 1,
    generatedAt: new Date().toISOString(),
    artifactRoot: path.relative(REPO_ROOT, outputRoot),
    baseUrl,
    mockedApi: true,
    viewports: VIEWPORTS,
    states: ROUTE_STATES,
    entries: [],
    ok: true,
  };
  try {
    const context = await browser.newContext({ locale: "ko-KR", timezoneId: "Asia/Seoul" });
    await installAuthInitScript(context, token);
    for (const [viewportName, viewport] of Object.entries(VIEWPORTS)) {
      await fs.mkdir(path.join(outputRoot, viewportName), { recursive: true });
      for (const state of ROUTE_STATES) {
        const page = await context.newPage();
        const networkRows = [];
        const consoleRows = [];
        page.on("console", (message) => {
          if (["error", "warning"].includes(message.type())) {
            consoleRows.push({ type: message.type(), text: message.text(), location: message.location() });
          }
        });
        page.on("requestfailed", (request) => {
          networkRows.push({ url: request.url(), method: request.method(), failed: true, failure: request.failure()?.errorText || "" });
        });
        await installApiMock(page, token, networkRows);
        await page.setViewportSize(viewport);
        const fileBase = `${state.flow}-${state.stateKey}${state.paginationPage ? `-page-${state.paginationPage}` : ""}.jpg`;
        const relScreenshot = `${viewportName}/${fileBase}`;
        const absScreenshot = path.join(outputRoot, relScreenshot);
        let geometry = null;
        let error = "";
        try {
          await page.goto(buildUrl(baseUrl, localServer.origin, state.route), {
            waitUntil: "domcontentloaded",
            timeout: 30000,
          });
          await prepareState(page, state);
          await page.waitForTimeout(700);
          geometry = await collectGeometry(page, state.flow);
          await page.screenshot({ path: absScreenshot, type: "jpeg", quality: 82, fullPage: true });
        } catch (caught) {
          error = String(caught?.message || caught).split("\n")[0];
          await page.screenshot({ path: absScreenshot, type: "jpeg", quality: 70, fullPage: true }).catch(() => {});
        } finally {
          await page.close();
        }
        const failedNetwork = networkRows.filter(
          (row) => row.failed && row.failure !== "net::ERR_ABORTED",
        );
        const centerOk = Math.abs(Number(geometry?.shellCenterDelta || 0)) <= 32 || viewportName === "half-756";
        const paginationRequired =
          Boolean(state.paginationPage) ||
          (state.flow === "hq" && state.stateKey === "export");
        const paginationOk = geometry?.referenceMode === true ||
          !paginationRequired ||
          (geometry?.pagination?.visible === true &&
            Number(geometry.pagination.totalItems || 0) > Number(geometry.pagination.pageSize || 0) &&
            (!state.paginationPage || String(geometry.pagination.page) === String(state.paginationPage)));
        const activeStateOk = Array.isArray(geometry?.activeSteps) &&
          geometry.activeSteps.length === 1 &&
          geometry.activeSteps[0] === state.stateKey;
        const footerActionsOk =
          geometry?.inCardActionEvidence?.routeWideFooterVisible === false &&
          geometry?.inCardActionEvidence?.actionCount > 0 &&
          geometry?.inCardActionEvidence?.allActionsHaveHooks === true &&
          geometry?.inCardActionEvidence?.rowWithinCard === true &&
          geometry?.inCardActionEvidence?.hasLeftPreviousWhenMultiple === true &&
          geometry?.inCardActionEvidence?.hasRightPrimary === true;
        const ok = Boolean(
          !error &&
          geometry?.shellBox &&
          geometry?.shellTitle?.visible === true &&
          activeStateOk &&
          centerOk &&
          geometry.circleCentersMonotonic &&
          Number(geometry.circleRowOrColumnDrift || 0) <= 10 &&
          !geometry.horizontalOverflow &&
          !geometry.routePanelLeak &&
          consoleRows.length === 0 &&
          failedNetwork.length === 0 &&
          paginationOk &&
          footerActionsOk,
        );
        if (!ok) manifest.ok = false;
        manifest.entries.push({
          ...state,
          viewport: viewportName,
          width: viewport.width,
          height: viewport.height,
          screenshotPath: relScreenshot,
          geometry,
          consoleRows,
          failedNetwork,
          status: ok ? "pass" : "fail",
          error,
        });
      }
    }
    await context.close();
  } finally {
    await browser.close();
    await localServer.close();
  }
  await fs.writeFile(path.join(outputRoot, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
  console.log(JSON.stringify({ ok: manifest.ok, artifactRoot: manifest.artifactRoot }, null, 2));
  if (!manifest.ok) process.exit(1);
}

run().catch((error) => {
  console.error(JSON.stringify({ ok: false, error: String(error?.message || error) }, null, 2));
  process.exit(1);
});
