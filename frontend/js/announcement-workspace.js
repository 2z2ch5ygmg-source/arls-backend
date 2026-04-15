(function initSocAnnouncementWorkspace() {
  const SOC_NOTICE_VIEW_MODE_LIST = "list";
  const SOC_NOTICE_VIEW_MODE_DETAIL = "detail";
  const SOC_NOTICE_VIEW_MODE_COMPOSE = "compose";
  const SOC_NOTICE_BODY_MODEL_LEGACY = "legacy_block_flow";
  const SOC_NOTICE_BODY_MODEL_FLOATING = "floating_scene_v1";
  const SOC_NOTICE_BODY_MODEL_FLOW_LANE = "flow_lane_v1";
  const SOC_NOTICE_FLOATING_DOCUMENT_VERSION = "floating_scene_v1";
  const SOC_NOTICE_FLOW_LANE_DOCUMENT_VERSION = "flow_lane_v1";
  const SOC_NOTICE_FLOATING_CANVAS_WIDTH = 880;
  const SOC_NOTICE_FLOATING_CANVAS_MIN_HEIGHT = 960;
  const SOC_NOTICE_FLOW_LANE_WIDTH = 1180;
  const SOC_NOTICE_PINNED_LIMIT = 3;
  const SOC_NOTICE_MAX_IMAGES = 6;
  const SOC_NOTICE_MAX_POLL_OPTIONS = 10;
  const SOC_NOTICE_MIN_POLL_OPTIONS = 2;
  const SOC_NOTICE_NEW_BADGE_WINDOW_HOURS = 72;
  const SOC_NOTICE_COMPOSE_AUTOSAVE_DELAY_MS = 650;
  const SOC_NOTICE_COMPOSE_DRAFT_STORAGE_PREFIX = "arls.notice.compose";
  const SOC_NOTICE_COMPOSE_FLOW_KINDS = Object.freeze(["body", "table", "poll"]);
  const SOC_NOTICE_CATEGORY_OPTIONS = Object.freeze([
    { value: "all", label: "전체" },
    { value: "ops", label: "운영" },
    { value: "attendance", label: "출퇴근" },
    { value: "schedule", label: "스케줄" },
    { value: "hr", label: "인사" },
    { value: "system", label: "시스템" },
    { value: "event", label: "이벤트" },
  ]);
  const SOC_NOTICE_RICH_ALIGN_OPTIONS = Object.freeze(["left", "center", "right"]);
  const SOC_NOTICE_RICH_TEXT_COLOR_OPTIONS = Object.freeze(["default", "orange", "red", "blue", "green", "gray"]);
  const SOC_NOTICE_RICH_BG_OPTIONS = Object.freeze(["none", "yellow-soft", "orange-soft", "red-soft", "blue-soft", "green-soft", "gray-soft"]);
  const SOC_NOTICE_RICH_FONT_SIZE_OPTIONS = Object.freeze(["8", "10", "11", "11.5", "12", "14", "16", "18", "20", "22", "24", "26", "28", "36", "48", "72"]);
  const SOC_NOTICE_RICH_FONT_SIZE_DEFAULT = "14";
  const SOC_NOTICE_RICH_TEXT_SWATCHES = Object.freeze([
    { token: "default", label: "기본", swatch: "#202430" },
    { token: "orange", label: "주황", swatch: "#ff7a00" },
    { token: "red", label: "빨강", swatch: "#e11d48" },
    { token: "blue", label: "파랑", swatch: "#2563eb" },
    { token: "green", label: "초록", swatch: "#16a34a" },
    { token: "gray", label: "회색", swatch: "#64748b" },
  ]);
  const SOC_NOTICE_RICH_BG_SWATCHES = Object.freeze([
    { token: "none", label: "없음", swatch: "transparent" },
    { token: "yellow-soft", label: "노랑", swatch: "#fff36a" },
    { token: "orange-soft", label: "주황", swatch: "#ffd7b8" },
    { token: "red-soft", label: "빨강", swatch: "#ffc9d2" },
    { token: "blue-soft", label: "파랑", swatch: "#c7dcff" },
    { token: "green-soft", label: "초록", swatch: "#cdeec9" },
    { token: "gray-soft", label: "회색", swatch: "#d8dde5" },
  ]);
  const SOC_NOTICE_RICH_ALLOWED_LINK_SCHEMES = new Set(["https:", "http:", "mailto:", "tel:"]);

  const rootState = typeof state !== "undefined" ? state : (window.state = window.state || {});
  let socNoticeComposeDragState = null;
  let socNoticeComposeRichSelection = null;
  let socNoticeFloatingSceneDragState = null;
  let socNoticeFlowLaneDragState = null;
  let socNoticeTableResizeState = null;

  function escapeHtml(value = "") {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function normalizeRichAlign(value = "left") {
    const normalized = String(value || "").trim().toLowerCase();
    return SOC_NOTICE_RICH_ALIGN_OPTIONS.includes(normalized) ? normalized : "left";
  }

  function normalizeRichPlainText(value = "") {
    return String(value || "")
      .replace(/\u00a0/g, " ")
      .replace(/\u200b/g, "")
      .replace(/\r\n/g, "\n")
      .replace(/[ \t]+\n/g, "\n")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
  }

  function richTextValueFromRaw(raw = null) {
    if (!raw || typeof raw !== "object") {
      return "";
    }
    return String(raw.richText || raw.rich_text || "").trim();
  }

  function plainTextToRichHtml(text = "") {
    const normalized = normalizeRichPlainText(text);
    if (!normalized) {
      return "";
    }
    return escapeHtml(normalized).replace(/\n/g, "<br>");
  }

  function createDefaultRichCell(text = "", align = "left") {
    return {
      text: normalizeRichPlainText(text),
      richText: "",
      align: normalizeRichAlign(align),
    };
  }

  function cloneRichCellDraft(rawCell = null, fallbackText = "", fallbackAlign = "left") {
    if (!rawCell || typeof rawCell !== "object") {
      return createDefaultRichCell(fallbackText, fallbackAlign);
    }
    return {
      text: normalizeRichPlainText(rawCell.text || fallbackText || ""),
      richText: richTextValueFromRaw(rawCell),
      align: normalizeRichAlign(rawCell.align || fallbackAlign || "left"),
    };
  }

  function cloneRichCellArray(rawArray = [], plainValues = []) {
    return plainValues.map((plainValue, index) => cloneRichCellDraft(rawArray[index], plainValue));
  }

  function cloneRichCellMatrix(rawMatrix = [], plainRows = []) {
    return plainRows.map((row, rowIndex) => {
      const rawRow = Array.isArray(rawMatrix[rowIndex]) ? rawMatrix[rowIndex] : [];
      return row.map((cellText, colIndex) => cloneRichCellDraft(rawRow[colIndex], cellText));
    });
  }

  function candidateRichTextValueFromHtml(rawHtml = "", plainText = "") {
    const html = String(rawHtml || "").trim();
    const normalizedPlain = normalizeRichPlainText(plainText);
    if (!html || !normalizedPlain) {
      return "";
    }
    return html === plainTextToRichHtml(normalizedPlain) ? "" : html;
  }

  function setRichEditorPresentation(editorEl, align = "left") {
    if (!(editorEl instanceof HTMLElement)) {
      return;
    }
    const normalizedAlign = normalizeRichAlign(align);
    editorEl.dataset.noticeRichAlign = normalizedAlign;
    editorEl.style.textAlign = normalizedAlign;
    Array.from(editorEl.querySelectorAll("[data-rt-size-px]")).forEach((node) => {
      if (!(node instanceof HTMLElement)) {
        return;
      }
      const value = String(node.getAttribute("data-rt-size-px") || "").trim();
      const numeric = Number(value);
      if (Number.isFinite(numeric) && numeric >= 1) {
        node.style.fontSize = `${numeric}px`;
      } else {
        node.style.removeProperty("font-size");
      }
    });
  }

  function setRichEditorContent(editorEl, text = "", richText = "", align = "left") {
    if (!(editorEl instanceof HTMLElement)) {
      return;
    }
    const normalizedPlain = normalizeRichPlainText(text);
    editorEl.innerHTML = String(richText || "").trim() || plainTextToRichHtml(normalizedPlain);
    setRichEditorPresentation(editorEl, align);
  }

  function readRichEditorPayload(editorEl) {
    if (!(editorEl instanceof HTMLElement)) {
      return createDefaultRichCell("", "left");
    }
    const plainText = normalizeRichPlainText(editorEl.innerText || editorEl.textContent || "");
    const candidateRichText = candidateRichTextValueFromHtml(String(editorEl.innerHTML || ""), plainText);
    return {
      text: plainText,
      richText: candidateRichText,
      align: normalizeRichAlign(editorEl.dataset.noticeRichAlign || "left"),
    };
  }

  function buildTableBlockBodyText(table = {}) {
    const lines = [];
    const title = normalizeRichPlainText(table.title || "");
    if (title) {
      lines.push(title);
    }
    const columns = Array.isArray(table.columns) ? table.columns.map((item) => normalizeRichPlainText(item)) : [];
    if (columns.length) {
      lines.push(columns.filter(Boolean).join(" ").trim());
    }
    (Array.isArray(table.rows) ? table.rows : []).forEach((row) => {
      const line = (Array.isArray(row) ? row : []).map((cell) => normalizeRichPlainText(cell)).filter(Boolean).join(" ").trim();
      if (line) {
        lines.push(line);
      }
    });
    return lines.filter(Boolean).join("\n\n");
  }

  function resolveNoticeImageUrl(rawValue = "") {
    const source = String(rawValue || "").trim();
    if (!source) {
      return "";
    }
    const adapter = window.__RG_ARLS_ANNOUNCEMENTS_ADAPTER__;
    if (
      adapter &&
      typeof adapter.getAttachmentUrl === "function" &&
      /^\/api\/attachments\/\d+\/file/i.test(source)
    ) {
      return adapter.getAttachmentUrl(source, { download: false }) || source;
    }
    if (typeof getAttachmentUrl === "function" && /^\/api\/attachments\/\d+\/file/i.test(source)) {
      return getAttachmentUrl(source, { download: false }) || source;
    }
    return source;
  }

  function getClosestRichEditorElement(node = null) {
    if (node instanceof HTMLElement) {
      return node.closest("[data-notice-rich-editor=\"true\"]");
    }
    if (node instanceof Node && node.parentElement instanceof HTMLElement) {
      return node.parentElement.closest("[data-notice-rich-editor=\"true\"]");
    }
    return null;
  }

  function getRichEditorDescriptor(editorEl = null) {
    if (!(editorEl instanceof HTMLElement)) {
      return null;
    }
    const kind = String(editorEl.dataset.noticeComposeEditorKind || "").trim();
    if (!kind) {
      return null;
    }
    return {
      kind,
      blockId: String(editorEl.dataset.noticeComposeBlockId || editorEl.dataset.noticeTableBlockId || "").trim(),
      tableField: String(editorEl.dataset.noticeTableField || "").trim(),
      rowIndex: editorEl.dataset.noticeTableRow != null ? Math.max(0, Number(editorEl.dataset.noticeTableRow || 0) || 0) : null,
      colIndex: editorEl.dataset.noticeTableCol != null ? Math.max(0, Number(editorEl.dataset.noticeTableCol || 0) || 0) : null,
    };
  }

  function getActiveRichEditorElement() {
    const selection = window.getSelection();
    if (selection && selection.rangeCount > 0) {
      const editorFromSelection = getClosestRichEditorElement(selection.anchorNode);
      if (editorFromSelection instanceof HTMLElement) {
        return editorFromSelection;
      }
    }
    return document.activeElement instanceof HTMLElement
      ? getClosestRichEditorElement(document.activeElement)
      : null;
  }

  function clearComposeRichSelection() {
    socNoticeComposeRichSelection = null;
  }

  function captureComposeRichSelection() {
    const selection = window.getSelection();
    if (!selection || !selection.rangeCount) {
      clearComposeRichSelection();
      return null;
    }
    const range = selection.getRangeAt(0);
    const editorEl = getClosestRichEditorElement(range.commonAncestorContainer || selection.anchorNode);
    if (!(editorEl instanceof HTMLElement)) {
      clearComposeRichSelection();
      return null;
    }
    socNoticeComposeRichSelection = {
      range: range.cloneRange(),
      descriptor: getRichEditorDescriptor(editorEl),
    };
    if (String(editorEl.dataset.noticeComposeEditorKind || "").trim() === "paragraph") {
      const offsets = getRichEditorSelectionOffsets(editorEl, range);
      const blockId = String(editorEl.dataset.noticeComposeBlockId || "").trim();
      if (offsets && blockId) {
        setComposeInsertionAnchor({
          blockId,
          start: offsets.start,
          end: offsets.end,
        });
      }
    }
    return socNoticeComposeRichSelection;
  }

  function restoreComposeRichSelection() {
    if (!socNoticeComposeRichSelection?.range) {
      return null;
    }
    const selection = window.getSelection();
    if (!selection) {
      return null;
    }
    selection.removeAllRanges();
    selection.addRange(socNoticeComposeRichSelection.range);
    const editorEl = getClosestRichEditorElement(socNoticeComposeRichSelection.range.commonAncestorContainer);
    if (editorEl instanceof HTMLElement) {
      editorEl.focus();
      return editorEl;
    }
    return null;
  }

  function getSelectionRangeInRichEditor({ requireExpanded = true } = {}) {
    const selection = window.getSelection();
    if (!selection || !selection.rangeCount) {
      return null;
    }
    const range = selection.getRangeAt(0);
    if (requireExpanded && range.collapsed) {
      return null;
    }
    const editorEl = getClosestRichEditorElement(range.commonAncestorContainer || selection.anchorNode);
    if (!(editorEl instanceof HTMLElement)) {
      return null;
    }
    return { selection, range, editorEl, descriptor: getRichEditorDescriptor(editorEl) };
  }

  function clearComposeLinkModalState() {
    const workspace = ensureWorkspaceState();
    workspace.composeLinkModalOpen = false;
    workspace.composeLinkModalUrlDraft = "";
    workspace.composeLinkModalSelectionRange = null;
    workspace.composeLinkModalEditorDescriptor = null;
    workspace.composeLinkModalAnchorHref = "";
    workspace.composeLinkModalHadExpandedSelection = false;
  }

  function resolveEditorFromDescriptor(descriptor = null) {
    if (!descriptor || typeof descriptor !== "object") {
      return null;
    }
    if (descriptor.kind === "paragraph") {
      const blockId = String(descriptor.blockId || "").trim();
      return blockId
        ? document.querySelector(`[data-notice-rich-editor="true"][data-notice-compose-block-id="${blockId}"]`)
        : null;
    }
    const blockId = String(descriptor.blockId || "").trim();
    const tableField = String(descriptor.tableField || "").trim();
    const colIndex = Math.max(0, Number(descriptor.colIndex || 0) || 0);
    const rowPart = descriptor.rowIndex == null ? "" : `[data-notice-table-row="${Math.max(0, Number(descriptor.rowIndex || 0) || 0)}"]`;
    return blockId
      ? document.querySelector(
        `[data-notice-rich-editor="true"][data-notice-table-block-id="${blockId}"][data-notice-table-field="${tableField}"][data-notice-table-col="${colIndex}"]${rowPart}`
      )
      : null;
  }

  function captureLinkModalSnapshot() {
    const workspace = ensureWorkspaceState();
    const activeSelection = getSelectionRangeInRichEditor({ requireExpanded: false });
    const existingAnchor = findSelectedAnchorElement();
    const editorEl = activeSelection?.editorEl || (existingAnchor ? getClosestRichEditorElement(existingAnchor) : null);
    if (!(editorEl instanceof HTMLElement)) {
      return false;
    }
    workspace.composeLinkModalSelectionRange = activeSelection?.range ? activeSelection.range.cloneRange() : null;
    workspace.composeLinkModalEditorDescriptor = getRichEditorDescriptor(editorEl);
    workspace.composeLinkModalAnchorHref = String(existingAnchor?.getAttribute("href") || "").trim();
    workspace.composeLinkModalHadExpandedSelection = Boolean(activeSelection && !activeSelection.range.collapsed);
    return true;
  }

  function restoreLinkModalContext() {
    const workspace = ensureWorkspaceState();
    const editorEl = resolveEditorFromDescriptor(workspace.composeLinkModalEditorDescriptor);
    if (!(editorEl instanceof HTMLElement)) {
      return { editorEl: null, anchorEl: null };
    }
    editorEl.focus();
    const selection = window.getSelection();
    if (selection && workspace.composeLinkModalSelectionRange instanceof Range) {
      try {
        selection.removeAllRanges();
        selection.addRange(workspace.composeLinkModalSelectionRange);
      } catch {
        selection.removeAllRanges();
      }
    }
    const anchorEl = findSelectedAnchorElement();
    return { editorEl, anchorEl: anchorEl instanceof HTMLElement ? anchorEl : null };
  }

  function insertPlainTextAtSelection(text = "") {
    const activeSelection = getSelectionRangeInRichEditor({ requireExpanded: false });
    if (!activeSelection) {
      return false;
    }
    const { selection, range, editorEl } = activeSelection;
    const lines = String(text || "").replace(/\r\n/g, "\n").split("\n");
    const fragment = document.createDocumentFragment();
    lines.forEach((line, index) => {
      if (index > 0) {
        fragment.appendChild(document.createElement("br"));
      }
      fragment.appendChild(document.createTextNode(line));
    });
    range.deleteContents();
    range.insertNode(fragment);
    selection.removeAllRanges();
    const nextRange = document.createRange();
    nextRange.selectNodeContents(editorEl);
    nextRange.collapse(false);
    selection.addRange(nextRange);
    captureComposeRichSelection();
    return true;
  }

  function wrapRichSelection(builder) {
    const activeSelection = getSelectionRangeInRichEditor({ requireExpanded: true });
    if (!activeSelection || typeof builder !== "function") {
      return false;
    }
    const { selection, range } = activeSelection;
    const wrapper = builder();
    if (!(wrapper instanceof HTMLElement)) {
      return false;
    }
    const contents = range.extractContents();
    wrapper.appendChild(contents);
    range.insertNode(wrapper);
    selection.removeAllRanges();
    const nextRange = document.createRange();
    nextRange.selectNodeContents(wrapper);
    selection.addRange(nextRange);
    captureComposeRichSelection();
    return true;
  }

  function canManageSocNotices() {
    const adapter = window.__RG_ARLS_ANNOUNCEMENTS_ADAPTER__;
    if (adapter && typeof adapter.canManageAnnouncements === "function") {
      return adapter.canManageAnnouncements();
    }
    return typeof canManageAnnouncements === "function" ? canManageAnnouncements() : false;
  }

  function canViewSocNotices() {
    const adapter = window.__RG_ARLS_ANNOUNCEMENTS_ADAPTER__;
    if (adapter && typeof adapter.canViewAnnouncements === "function") {
      return adapter.canViewAnnouncements();
    }
    return typeof canViewAnnouncements === "function" ? canViewAnnouncements() : true;
  }

  function apiRequest(path, options) {
    const adapter = window.__RG_ARLS_ANNOUNCEMENTS_ADAPTER__;
    if (adapter && typeof adapter.api === "function") {
      return adapter.api(path, options);
    }
    if (typeof api === "function") {
      return api(path, options);
    }
    if (typeof window.api === "function") {
      return window.api(path, options);
    }
    throw new Error("API helper is not available.");
  }

  function socToast(message, variant = "info", durationMs = 1600) {
    const adapter = window.__RG_ARLS_ANNOUNCEMENTS_ADAPTER__;
    if (adapter && typeof adapter.toast === "function") {
      adapter.toast(message, variant, durationMs);
      return;
    }
    if (typeof showSocToast === "function") {
      showSocToast(message, { variant, durationMs });
      return;
    }
    console.info(`[soc-notices:${variant}] ${message}`);
  }

  async function socConfirm(message) {
    const adapter = window.__RG_ARLS_ANNOUNCEMENTS_ADAPTER__;
    if (adapter && typeof adapter.confirm === "function") {
      return adapter.confirm(message);
    }
    if (typeof askConfirm === "function") {
      return askConfirm(message);
    }
    return window.confirm(message);
  }

  function normalizeNoticeCategory(value = "", allowAll = true) {
    const normalized = String(value || "").trim().toLowerCase();
    if (!normalized) {
      return allowAll ? "all" : "ops";
    }
    const allowed = SOC_NOTICE_CATEGORY_OPTIONS.map((item) => item.value);
    if (!allowed.includes(normalized)) {
      return allowAll ? "all" : "ops";
    }
    if (!allowAll && normalized === "all") {
      return "ops";
    }
    return normalized;
  }

  function normalizeNoticeMode(value = "", canCompose = canManageSocNotices()) {
    const normalized = String(value || "").trim().toLowerCase();
    if (canCompose && ["compose", "edit", "new"].includes(normalized)) {
      return SOC_NOTICE_VIEW_MODE_COMPOSE;
    }
    if (["detail", "view"].includes(normalized)) {
      return SOC_NOTICE_VIEW_MODE_DETAIL;
    }
    return SOC_NOTICE_VIEW_MODE_LIST;
  }

  function normalizeNoticeSearch(value = "") {
    return String(value || "").trim().slice(0, 120);
  }

  function createNoticeBlockId(prefix = "block") {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
      return `soc-notice-${prefix}-${crypto.randomUUID()}`;
    }
    return `soc-notice-${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  }

  function createDefaultPollOption(index = 0) {
    return {
      optionId: createNoticeBlockId(`poll-option-${index + 1}`),
      label: "",
    };
  }

  function createDefaultPollDraft() {
    return {
      enabled: false,
      pollId: "",
      question: "",
      options: [createDefaultPollOption(0), createDefaultPollOption(1)],
      allowMultiple: false,
      allowChangeVote: false,
      resultVisibility: "always",
      closesAt: "",
      totalVotes: 0,
      resultsVisible: true,
      isClosed: false,
      canVote: true,
      hasVoted: false,
      selectedOptionIds: [],
    };
  }

  function clonePollDraft(rawPoll = null) {
    const source = rawPoll && typeof rawPoll === "object" ? rawPoll : {};
    const options = Array.isArray(source.options) ? source.options : [];
    const normalizedOptions = options
      .map((option, index) => {
        const label = String(option?.label || "").trim();
        return {
          optionId: String(option?.optionId || option?.option_id || option?.id || "").trim() || createNoticeBlockId(`poll-option-${index + 1}`),
          label,
          voteCount: Math.max(0, Number(option?.voteCount || option?.vote_count || 0) || 0),
          voteRatio: Math.max(0, Math.min(1, Number(option?.voteRatio || option?.vote_ratio || 0) || 0)),
          selected: Boolean(option?.selected),
        };
      })
      .filter((option) => option.label || options.length <= SOC_NOTICE_MIN_POLL_OPTIONS);
    while (normalizedOptions.length < SOC_NOTICE_MIN_POLL_OPTIONS) {
      normalizedOptions.push(createDefaultPollOption(normalizedOptions.length));
    }
    return {
      enabled: Boolean(source.enabled),
      pollId: String(source.pollId || source.poll_id || "").trim(),
      question: String(source.question || "").trim(),
      options: normalizedOptions.slice(0, SOC_NOTICE_MAX_POLL_OPTIONS),
      allowMultiple: Boolean(source.allowMultiple ?? source.allow_multiple),
      allowChangeVote: Boolean(source.allowChangeVote || source.allow_change_vote),
      resultVisibility: String(source.resultVisibility || source.result_visibility || "always").trim().toLowerCase() === "after_close"
        ? "after_close"
        : "always",
      closesAt: String(source.closesAt || source.closes_at || "").trim(),
      totalVotes: Math.max(0, Number(source.totalVotes || source.total_votes || 0) || 0),
      resultsVisible: source.resultsVisible !== false && source.results_visible !== false,
      isClosed: Boolean(source.isClosed || source.is_closed),
      canVote: source.canVote !== false && source.can_vote !== false,
      hasVoted: Boolean(source.hasVoted || source.has_voted),
      selectedOptionIds: Array.isArray(source.selectedOptionIds || source.selected_option_ids)
        ? Array.from(new Set((source.selectedOptionIds || source.selected_option_ids).map((item) => String(item || "").trim()).filter(Boolean)))
        : [],
    };
  }

  function createDefaultTableDraft() {
    const columns = ["항목 1", "항목 2"];
    const rows = [["", ""], ["", ""]];
    return {
      enabled: false,
      title: "",
      hasHeader: true,
      columns,
      rows,
      columnWidths: Array.from({ length: columns.length }, () => 160),
      rowHeights: Array.from({ length: rows.length + 1 }, () => 44),
      columnsRich: cloneRichCellArray([], columns),
      rowsRich: cloneRichCellMatrix([], rows),
    };
  }

  function cloneTableDraft(rawTable = null) {
    const source = rawTable && typeof rawTable === "object" ? rawTable : {};
    const columns = Array.isArray(source.columns) && source.columns.length
      ? source.columns.slice(0, 6).map((item, index) => String(item || "").trim() || `항목 ${index + 1}`)
      : createDefaultTableDraft().columns.slice();
    const rowsSource = Array.isArray(source.rows) ? source.rows.slice(0, 20) : createDefaultTableDraft().rows;
    const rows = rowsSource.map((row) => {
      const cells = Array.isArray(row) ? row : [];
      return Array.from({ length: columns.length }, (_, index) => String(cells[index] || "").trim());
    });
    const defaultTable = createDefaultTableDraft();
    const sourceColumnWidths = Array.isArray(source.columnWidths || source.column_widths)
      ? (source.columnWidths || source.column_widths)
      : defaultTable.columnWidths;
    const sourceRowHeights = Array.isArray(source.rowHeights || source.row_heights)
      ? (source.rowHeights || source.row_heights)
      : defaultTable.rowHeights;
    return {
      enabled: Boolean(source.enabled),
      title: String(source.title || "").trim(),
      hasHeader: source.hasHeader !== false && source.has_header !== false,
      columns,
      rows: rows.length ? rows : createDefaultTableDraft().rows,
      columnWidths: Array.from({ length: columns.length }, (_, index) => Math.max(72, Number(sourceColumnWidths[index] || defaultTable.columnWidths[index] || 160) || 160)),
      rowHeights: Array.from({ length: (rows.length ? rows : defaultTable.rows).length + 1 }, (_, index) => Math.max(36, Number(sourceRowHeights[index] || defaultTable.rowHeights[index] || 44) || 44)),
      columnsRich: cloneRichCellArray(source.columnsRich || source.columns_rich || [], columns),
      rowsRich: cloneRichCellMatrix(source.rowsRich || source.rows_rich || [], rows.length ? rows : createDefaultTableDraft().rows),
    };
  }

  function cloneImageDrafts(rawImages = []) {
    return (Array.isArray(rawImages) ? rawImages : [])
      .map((item) => {
        const imageSrc = String(item?.imageSrc || item?.image_src || item?.dataUrl || "").trim();
        if (!imageSrc) {
          return null;
        }
        return {
          attachmentId: String(item?.attachmentId || item?.attachment_id || "").trim(),
          fileName: String(item?.fileName || item?.file_name || "notice-image.png").trim(),
          caption: String(item?.caption || "").trim(),
          imageSrc,
        };
      })
      .filter(Boolean);
  }

  function createDefaultComposeContentBlocks() {
    return [
      { id: createNoticeBlockId("paragraph"), kind: "paragraph", text: "", richText: "", align: "left" },
    ];
  }

  function createParagraphBlocksFromText(rawText = "", { firstBlockId = "", preserveEmpty = false } = {}) {
    const text = String(rawText || "").replace(/\r\n/g, "\n").replace(/^\n+|\n+$/g, "");
    if (!text) {
      return preserveEmpty
        ? [{ id: String(firstBlockId || "").trim() || createNoticeBlockId("paragraph"), kind: "paragraph", text: "", richText: "", align: "left" }]
        : [];
    }
    return [{
      id: String(firstBlockId || "").trim() || createNoticeBlockId("paragraph"),
      kind: "paragraph",
      text,
      richText: "",
      align: "left",
    }];
  }

  function createParagraphBlockFromPayload(payload = {}, { preserveEmpty = false } = {}) {
    const plainText = normalizeRichPlainText(payload.text || "");
    if (!plainText) {
      return preserveEmpty
        ? {
          id: String(payload.id || "").trim() || createNoticeBlockId("paragraph"),
          kind: "paragraph",
          text: "",
          richText: "",
          align: normalizeRichAlign(payload.align || "left"),
        }
        : null;
    }
    const richText = candidateRichTextValueFromHtml(String(payload.richText || ""), plainText);
    return {
      id: String(payload.id || "").trim() || createNoticeBlockId("paragraph"),
      kind: "paragraph",
      text: plainText,
      richText,
      align: normalizeRichAlign(payload.align || "left"),
    };
  }

  function normalizeNoticeBodyModel(value = "") {
    const normalized = String(value || "").trim().toLowerCase();
    if (normalized === SOC_NOTICE_BODY_MODEL_FLOW_LANE) {
      return SOC_NOTICE_BODY_MODEL_FLOW_LANE;
    }
    return normalized === SOC_NOTICE_BODY_MODEL_FLOATING
      ? SOC_NOTICE_BODY_MODEL_FLOATING
      : SOC_NOTICE_BODY_MODEL_LEGACY;
  }

  function isFloatingNoticeModel(value = "") {
    return normalizeNoticeBodyModel(value) === SOC_NOTICE_BODY_MODEL_FLOATING;
  }

  function isFlowLaneNoticeModel(value = "") {
    return normalizeNoticeBodyModel(value) === SOC_NOTICE_BODY_MODEL_FLOW_LANE;
  }

  function usesStructuredNoticeDocumentModel(value = "") {
    return isFloatingNoticeModel(value) || isFlowLaneNoticeModel(value);
  }

  function createFloatingParagraphDraft(index = 0, overrides = {}) {
    return {
      id: String(overrides.id || createNoticeBlockId("paragraph")).trim(),
      flow_index: Math.max(0, Number(overrides.flow_index ?? overrides.flowIndex ?? index) || 0),
      flowIndex: Math.max(0, Number(overrides.flow_index ?? overrides.flowIndex ?? index) || 0),
      text: normalizeRichPlainText(overrides.text || ""),
      rich_text: String(overrides.rich_text || overrides.richText || "").trim() || null,
      richText: String(overrides.rich_text || overrides.richText || "").trim() || null,
      align: normalizeRichAlign(overrides.align || "left"),
      font_size_px: overrides.font_size_px != null ? String(overrides.font_size_px).trim() : (overrides.fontSizePx != null ? String(overrides.fontSizePx).trim() : null),
      fontSizePx: overrides.font_size_px != null ? String(overrides.font_size_px).trim() : (overrides.fontSizePx != null ? String(overrides.fontSizePx).trim() : null),
    };
  }

  function createFloatingObjectFrame({ x = 80, y = 80, width = 320, height = 180 } = {}) {
    return {
      x: Math.max(0, Number(x) || 0),
      y: Math.max(0, Number(y) || 0),
      width: Math.max(1, Number(width) || 1),
      height: Math.max(1, Number(height) || 1),
    };
  }

  function createDefaultFloatingDocument() {
    return {
      version: SOC_NOTICE_FLOATING_DOCUMENT_VERSION,
      canvas: {
        width: SOC_NOTICE_FLOATING_CANVAS_WIDTH,
        minHeight: SOC_NOTICE_FLOATING_CANVAS_MIN_HEIGHT,
      },
      paragraphs: [
        createFloatingParagraphDraft(0, { id: createNoticeBlockId("paragraph"), text: "" }),
      ],
      objects: [],
    };
  }

  function createDefaultFlowLaneDocument() {
    return {
      version: SOC_NOTICE_FLOW_LANE_DOCUMENT_VERSION,
      canvas: {
        width: SOC_NOTICE_FLOW_LANE_WIDTH,
        minHeight: 320,
      },
      paragraphs: [
        createFloatingParagraphDraft(0, { id: createNoticeBlockId("paragraph"), text: "" }),
      ],
      objects: [],
    };
  }

  function sortFloatingDocumentInPlace(documentValue = null) {
    if (!documentValue || typeof documentValue !== "object") {
      return createDefaultFloatingDocument();
    }
    const paragraphs = Array.isArray(documentValue.paragraphs) ? documentValue.paragraphs.slice() : [];
    const objects = Array.isArray(documentValue.objects) ? documentValue.objects.slice() : [];
    paragraphs.sort((a, b) => {
      const aIndex = Math.max(0, Number(a?.flow_index ?? a?.flowIndex ?? 0) || 0);
      const bIndex = Math.max(0, Number(b?.flow_index ?? b?.flowIndex ?? 0) || 0);
      return aIndex - bIndex;
    });
    objects.sort((a, b) => {
      const aIndex = Math.max(0, Number(a?.flow_index ?? a?.flowIndex ?? 0) || 0);
      const bIndex = Math.max(0, Number(b?.flow_index ?? b?.flowIndex ?? 0) || 0);
      return aIndex - bIndex;
    });
    documentValue.paragraphs = paragraphs;
    documentValue.objects = objects;
    return documentValue;
  }

  function convertLegacyBlocksToFloatingDocument(bodyBlocks = [], fallbackBodyText = "") {
    const blocks = normalizeBodyBlocks(bodyBlocks, fallbackBodyText);
    const documentValue = createDefaultFloatingDocument();
    documentValue.paragraphs = [];
    documentValue.objects = [];
    let flowIndex = 0;
    let floatingY = 120;
    blocks.forEach((block) => {
      const kind = String(block?.kind || "").trim().toLowerCase();
      if (kind === "paragraph") {
        documentValue.paragraphs.push(createFloatingParagraphDraft(flowIndex, {
          id: createNoticeBlockId("paragraph"),
          flow_index: flowIndex,
          text: String(block.text || ""),
          rich_text: richTextValueFromRaw(block) || null,
          align: normalizeRichAlign(block.align || "left"),
        }));
        flowIndex += 1;
        return;
      }
      if (kind === "table") {
        documentValue.objects.push({
          id: createNoticeBlockId("table"),
          kind: "table",
          flow_index: flowIndex,
          flowIndex,
          z_index: flowIndex,
          zIndex: flowIndex,
          frame: createFloatingObjectFrame({ x: 120, y: floatingY, width: 520, height: 180 }),
          table: cloneTableDraft({
            enabled: true,
            ...(block || {}),
          }),
        });
        flowIndex += 1;
        floatingY += 220;
        return;
      }
      if (kind === "poll") {
        documentValue.objects.push({
          id: createNoticeBlockId("poll"),
          kind: "poll",
          flow_index: flowIndex,
          flowIndex,
          z_index: flowIndex,
          zIndex: flowIndex,
          frame: createFloatingObjectFrame({ x: 140, y: floatingY, width: 520, height: 220 }),
          poll: clonePollDraft({
            enabled: true,
            ...((block && block.poll) || {}),
          }),
        });
        flowIndex += 1;
        floatingY += 240;
        return;
      }
      if (kind === "image") {
        documentValue.objects.push({
          id: createNoticeBlockId("image"),
          kind: "image",
          flow_index: flowIndex,
          flowIndex,
          z_index: flowIndex,
          zIndex: flowIndex,
          frame: createFloatingObjectFrame({ x: 160, y: floatingY, width: 320, height: 240 }),
          attachment_id: String(block.attachmentId || block.attachment_id || "").trim() || null,
          attachmentId: String(block.attachmentId || block.attachment_id || "").trim() || null,
          file_name: String(block.fileName || block.file_name || "notice-image.png").trim() || "notice-image.png",
          fileName: String(block.fileName || block.file_name || "notice-image.png").trim() || "notice-image.png",
          caption: String(block.caption || "").trim() || null,
          image_src: String(block.imageSrc || block.image_src || "").trim() || null,
          imageSrc: String(block.imageSrc || block.image_src || "").trim() || null,
        });
        flowIndex += 1;
        floatingY += 260;
      }
    });
    if (!documentValue.paragraphs.length) {
      documentValue.paragraphs.push(createFloatingParagraphDraft(0, { id: createNoticeBlockId("paragraph"), text: "" }));
    }
    return sortFloatingDocumentInPlace(documentValue);
  }

  function convertSceneDocumentToFlowLaneDocument(bodyDocument = null, fallbackBodyText = "") {
    const source = normalizeFloatingDocumentDraft(bodyDocument, fallbackBodyText);
    const nextDocument = createDefaultFlowLaneDocument();
    nextDocument.paragraphs = (source.paragraphs || []).map((paragraph, index) => createFloatingParagraphDraft(index, {
      ...paragraph,
      flow_index: paragraph?.flow_index ?? paragraph?.flowIndex ?? index,
    }));
    nextDocument.objects = (source.objects || []).map((item, index) => ({
      ...item,
      flow_index: Math.max(0, Number(item?.flow_index ?? item?.flowIndex ?? (index + nextDocument.paragraphs.length)) || (index + nextDocument.paragraphs.length)),
      flowIndex: Math.max(0, Number(item?.flow_index ?? item?.flowIndex ?? (index + nextDocument.paragraphs.length)) || (index + nextDocument.paragraphs.length)),
      frame: createFloatingObjectFrame({
        x: Number(item?.frame?.x || 0) || 0,
        y: 0,
        width: Number(item?.frame?.width || (String(item?.kind || "").trim() === "image" ? 420 : 640)) || (String(item?.kind || "").trim() === "image" ? 420 : 640),
        height: Number(item?.frame?.height || (String(item?.kind || "").trim() === "image" ? 320 : 220)) || (String(item?.kind || "").trim() === "image" ? 320 : 220),
      }),
      z_index: 0,
      zIndex: 0,
    }));
    if (!nextDocument.paragraphs.length) {
      nextDocument.paragraphs.push(createFloatingParagraphDraft(0, { id: createNoticeBlockId("paragraph"), text: "" }));
    }
    return sortFloatingDocumentInPlace(nextDocument);
  }

  function normalizeFlowLaneDocumentDraft(rawDocument = null, fallbackBodyText = "", fallbackBodyBlocks = null) {
    const documentValue = rawDocument && typeof rawDocument === "object" ? rawDocument : {};
    const version = String(documentValue.version || "").trim();
    if (version && version !== SOC_NOTICE_FLOW_LANE_DOCUMENT_VERSION) {
      return convertSceneDocumentToFlowLaneDocument(rawDocument, fallbackBodyText);
    }
    const source = version ? documentValue : convertLegacyBlocksToFloatingDocument(fallbackBodyBlocks || [], fallbackBodyText);
    const sceneLike = version ? documentValue : source;
    const normalized = normalizeFloatingDocumentDraft(sceneLike, fallbackBodyText);
    const nextDocument = {
      ...normalized,
      version: SOC_NOTICE_FLOW_LANE_DOCUMENT_VERSION,
      canvas: {
        width: Math.max(640, Number(normalized?.canvas?.width || SOC_NOTICE_FLOW_LANE_WIDTH) || SOC_NOTICE_FLOW_LANE_WIDTH),
        minHeight: Math.max(320, Number(normalized?.canvas?.minHeight || normalized?.canvas?.min_height || 320) || 320),
      },
    };
    nextDocument.objects = (nextDocument.objects || []).map((item) => ({
      ...item,
      frame: createFloatingObjectFrame({
        x: Number(item?.frame?.x || 0) || 0,
        y: 0,
        width: Number(item?.frame?.width || (String(item?.kind || "").trim() === "image" ? 420 : 640)) || (String(item?.kind || "").trim() === "image" ? 420 : 640),
        height: Number(item?.frame?.height || (String(item?.kind || "").trim() === "image" ? 320 : 220)) || (String(item?.kind || "").trim() === "image" ? 320 : 220),
      }),
      z_index: 0,
      zIndex: 0,
    }));
    return sortFloatingDocumentInPlace(nextDocument);
  }

  function normalizeFloatingDocumentDraft(rawDocument = null, fallbackBodyText = "") {
    const source = rawDocument && typeof rawDocument === "object" ? rawDocument : {};
    const canvas = source.canvas && typeof source.canvas === "object" ? source.canvas : {};
    const documentValue = {
      version: String(source.version || SOC_NOTICE_FLOATING_DOCUMENT_VERSION).trim() || SOC_NOTICE_FLOATING_DOCUMENT_VERSION,
      canvas: {
        width: Math.max(320, Number(canvas.width || SOC_NOTICE_FLOATING_CANVAS_WIDTH) || SOC_NOTICE_FLOATING_CANVAS_WIDTH),
        minHeight: Math.max(320, Number(canvas.minHeight || canvas.min_height || SOC_NOTICE_FLOATING_CANVAS_MIN_HEIGHT) || SOC_NOTICE_FLOATING_CANVAS_MIN_HEIGHT),
      },
      paragraphs: [],
      objects: [],
    };
    (Array.isArray(source.paragraphs) ? source.paragraphs : []).forEach((paragraph, index) => {
      const normalized = createFloatingParagraphDraft(index, paragraph || {});
      if (!normalized.text && !normalized.richText) {
        return;
      }
      documentValue.paragraphs.push(normalized);
    });
    (Array.isArray(source.objects) ? source.objects : []).forEach((obj, index) => {
      const kind = String(obj?.kind || "").trim().toLowerCase();
      const flowIndex = Math.max(0, Number(obj?.flow_index ?? obj?.flowIndex ?? index) || 0);
      const base = {
        id: String(obj?.id || createNoticeBlockId(kind || "object")).trim() || createNoticeBlockId(kind || "object"),
        kind,
        flow_index: flowIndex,
        flowIndex,
        z_index: Math.max(0, Number(obj?.z_index ?? obj?.zIndex ?? flowIndex) || flowIndex),
        zIndex: Math.max(0, Number(obj?.z_index ?? obj?.zIndex ?? flowIndex) || flowIndex),
        frame: createFloatingObjectFrame(obj?.frame || {}),
      };
      if (kind === "image") {
        documentValue.objects.push({
          ...base,
          attachment_id: String(obj?.attachment_id || obj?.attachmentId || "").trim() || null,
          attachmentId: String(obj?.attachment_id || obj?.attachmentId || "").trim() || null,
          file_name: String(obj?.file_name || obj?.fileName || "notice-image.png").trim() || "notice-image.png",
          fileName: String(obj?.file_name || obj?.fileName || "notice-image.png").trim() || "notice-image.png",
          caption: String(obj?.caption || "").trim() || null,
          image_src: String(obj?.image_src || obj?.imageSrc || "").trim() || null,
          imageSrc: String(obj?.image_src || obj?.imageSrc || "").trim() || null,
        });
        return;
      }
      if (kind === "table") {
        documentValue.objects.push({
          ...base,
          table: cloneTableDraft({
            enabled: true,
            ...((obj && obj.table) || {}),
          }),
        });
        return;
      }
      if (kind === "poll") {
        documentValue.objects.push({
          ...base,
          poll: clonePollDraft({
            enabled: true,
            ...((obj && obj.poll) || {}),
          }),
        });
      }
    });
    if (!documentValue.paragraphs.length && String(fallbackBodyText || "").trim()) {
      documentValue.paragraphs = convertLegacyBlocksToFloatingDocument([], fallbackBodyText).paragraphs;
    }
    if (!documentValue.paragraphs.length) {
      documentValue.paragraphs.push(createFloatingParagraphDraft(0, { id: createNoticeBlockId("paragraph"), text: "" }));
    }
    return sortFloatingDocumentInPlace(documentValue);
  }

  function buildFloatingDocumentBodyText(documentValue = null) {
    if (!documentValue || typeof documentValue !== "object") {
      return "";
    }
    const items = [];
    (Array.isArray(documentValue.paragraphs) ? documentValue.paragraphs : []).forEach((paragraph) => {
      items.push({ kind: "paragraph", flowIndex: Math.max(0, Number(paragraph.flow_index ?? paragraph.flowIndex ?? 0) || 0), value: paragraph });
    });
    (Array.isArray(documentValue.objects) ? documentValue.objects : []).forEach((obj) => {
      items.push({ kind: String(obj?.kind || "").trim().toLowerCase(), flowIndex: Math.max(0, Number(obj?.flow_index ?? obj?.flowIndex ?? 0) || 0), value: obj });
    });
    items.sort((a, b) => a.flowIndex - b.flowIndex);
    const parts = [];
    items.forEach((item) => {
      if (item.kind === "paragraph") {
        const text = normalizeRichPlainText(item.value.text || "");
        if (text) {
          parts.push(text);
        }
        return;
      }
      if (item.kind === "image") {
        const caption = normalizeRichPlainText(item.value.caption || "");
        if (caption) {
          parts.push(caption);
        }
        return;
      }
      if (item.kind === "table") {
        parts.push(buildTableBlockBodyText(item.value.table || item.value));
        return;
      }
      if (item.kind === "poll") {
        const poll = clonePollDraft(item.value.poll || item.value);
        const optionText = (poll.options || []).map((option) => String(option.label || option.text || "").trim()).filter(Boolean).join(" ").trim();
        const segments = [String(poll.question || "").trim(), optionText].filter(Boolean).join("\n\n");
        if (segments) {
          parts.push(segments);
        }
      }
    });
    return parts.filter(Boolean).join("\n\n");
  }

  function updateComposeFloatingDocument(mutator, { markDirty = true, rerender = true } = {}) {
    const workspace = ensureWorkspaceState();
    const current = isFlowLaneNoticeModel(workspace.composeDraft?.bodyModel)
      ? normalizeFlowLaneDocumentDraft(workspace.composeDraft?.bodyDocument, workspace.composeDraft?.bodyText || "")
      : normalizeFloatingDocumentDraft(workspace.composeDraft?.bodyDocument, workspace.composeDraft?.bodyText || "");
    const nextDocument = typeof mutator === "function" ? (mutator(current) || current) : current;
    workspace.composeDraft = {
      ...(workspace.composeDraft || createDefaultComposeDraft(workspace.category === "all" ? "ops" : workspace.category)),
      bodyModel: isFlowLaneNoticeModel(workspace.composeDraft?.bodyModel)
        ? SOC_NOTICE_BODY_MODEL_FLOW_LANE
        : SOC_NOTICE_BODY_MODEL_FLOATING,
      bodyDocument: sortFloatingDocumentInPlace(nextDocument),
      bodyText: buildFloatingDocumentBodyText(nextDocument),
      imagesEnabled: (nextDocument.objects || []).some((item) => String(item.kind || "").trim() === "image"),
    };
    if (markDirty) {
      markComposeDraftDirty();
    }
    if (rerender) {
      renderWorkspace();
    }
    return workspace.composeDraft.bodyDocument;
  }

  function getFloatingDocumentObjectById(documentValue, objectId = "") {
    return (Array.isArray(documentValue?.objects) ? documentValue.objects : [])
      .find((item) => String(item?.id || "").trim() === String(objectId || "").trim()) || null;
  }

  function createDefaultFloatingObjectOrigin(kind = "image") {
    const workspace = ensureWorkspaceState();
    if (isFlowLaneNoticeModel(workspace.composeDraft?.bodyModel)) {
      if (kind === "table") {
        return createFloatingObjectFrame({ x: 0, y: 0, width: 640, height: 220 });
      }
      if (kind === "poll") {
        return createFloatingObjectFrame({ x: 0, y: 0, width: 640, height: 220 });
      }
      return createFloatingObjectFrame({ x: 0, y: 0, width: 420, height: 320 });
    }
    const documentValue = normalizeFloatingDocumentDraft(workspace.composeDraft?.bodyDocument, "");
    const maxBottom = (Array.isArray(documentValue.objects) ? documentValue.objects : []).reduce((current, item) => {
      const frame = item?.frame || {};
      return Math.max(current, (Number(frame.y || 0) || 0) + (Number(frame.height || 0) || 0));
    }, 120);
    if (kind === "table") {
      return createFloatingObjectFrame({ x: 120, y: maxBottom + 40, width: 520, height: 180 });
    }
    if (kind === "poll") {
      return createFloatingObjectFrame({ x: 140, y: maxBottom + 40, width: 520, height: 220 });
    }
    return createFloatingObjectFrame({ x: 160, y: maxBottom + 40, width: 320, height: 240 });
  }

  function insertFloatingObject(nextObject = null) {
    if (!nextObject || typeof nextObject !== "object") {
      return "";
    }
    const workspace = ensureWorkspaceState();
    const activeParagraphId = String(
      getActiveRichEditorElement()?.dataset?.noticeFloatingParagraphId
      || workspace.composeInsertionAnchor?.blockId
      || ""
    ).trim();
    const bodyDocument = updateComposeFloatingDocument((documentValue) => {
      const next = normalizeFloatingDocumentDraft(documentValue, "");
      const paragraphMatch = (next.paragraphs || []).find((paragraph) => String(paragraph?.id || "").trim() === activeParagraphId);
      const insertAfter = paragraphMatch
        ? Math.max(0, Number(paragraphMatch.flow_index ?? paragraphMatch.flowIndex ?? 0) || 0) + 1
        : getFloatingDocumentItems(next).length;
      next.paragraphs = (next.paragraphs || []).map((paragraph) => {
        const currentIndex = Math.max(0, Number(paragraph.flow_index ?? paragraph.flowIndex ?? 0) || 0);
        if (currentIndex >= insertAfter) {
          return {
            ...paragraph,
            flow_index: currentIndex + 1,
            flowIndex: currentIndex + 1,
          };
        }
        return paragraph;
      });
      next.objects = (next.objects || []).map((item) => {
        const currentIndex = Math.max(0, Number(item.flow_index ?? item.flowIndex ?? 0) || 0);
        if (currentIndex >= insertAfter) {
          return {
            ...item,
            flow_index: currentIndex + 1,
            flowIndex: currentIndex + 1,
          };
        }
        return item;
      });
      next.objects = [...(next.objects || []), {
        ...nextObject,
        flow_index: insertAfter,
        flowIndex: insertAfter,
      }];
      return next;
    });
    return String(getFloatingDocumentObjectById(bodyDocument, nextObject.id)?.id || nextObject.id || "").trim();
  }

  function removeFloatingObject(objectId = "") {
    const normalizedId = String(objectId || "").trim();
    if (!normalizedId) {
      return false;
    }
    updateComposeFloatingDocument((documentValue) => {
      const next = normalizeFloatingDocumentDraft(documentValue, "");
      next.objects = (next.objects || []).filter((item) => String(item?.id || "").trim() !== normalizedId);
      return next;
    }, { markDirty: true, rerender: true });
    return true;
  }

  function updateFloatingObjectFrame(objectId = "", nextFrame = {}) {
    const normalizedId = String(objectId || "").trim();
    if (!normalizedId) {
      return false;
    }
    updateComposeFloatingDocument((documentValue) => {
      const next = normalizeFloatingDocumentDraft(documentValue, "");
      next.objects = (next.objects || []).map((item) => {
        if (String(item?.id || "").trim() !== normalizedId) {
          return item;
        }
        return {
          ...item,
          frame: createFloatingObjectFrame({
            ...(item.frame || {}),
            ...(nextFrame || {}),
          }),
        };
      });
      return next;
    }, { markDirty: true, rerender: false });
    return true;
  }

  function updateFloatingTableObject(objectId = "", updater) {
    const normalizedId = String(objectId || "").trim();
    if (!normalizedId || typeof updater !== "function") {
      return false;
    }
    updateComposeFloatingDocument((documentValue) => {
      const next = normalizeFloatingDocumentDraft(documentValue, "");
      next.objects = (next.objects || []).map((item) => {
        if (String(item?.id || "").trim() !== normalizedId || String(item?.kind || "").trim() !== "table") {
          return item;
        }
        return {
          ...item,
          table: cloneTableDraft(updater(cloneTableDraft(item.table || {}))),
        };
      });
      return next;
    }, { markDirty: true, rerender: false });
    return true;
  }

  function updateFloatingPollObject(objectId = "", updater) {
    const normalizedId = String(objectId || "").trim();
    if (!normalizedId || typeof updater !== "function") {
      return false;
    }
    updateComposeFloatingDocument((documentValue) => {
      const next = normalizeFloatingDocumentDraft(documentValue, "");
      next.objects = (next.objects || []).map((item) => {
        if (String(item?.id || "").trim() !== normalizedId || String(item?.kind || "").trim() !== "poll") {
          return item;
        }
        return {
          ...item,
          poll: clonePollDraft(updater(clonePollDraft(item.poll || {}))),
        };
      });
      return next;
    }, { markDirty: true, rerender: false });
    return true;
  }

  function updateFloatingParagraphValue(paragraphId = "", payload = {}) {
    const normalizedId = String(paragraphId || "").trim();
    if (!normalizedId) {
      return false;
    }
    updateComposeFloatingDocument((documentValue) => {
      const next = normalizeFloatingDocumentDraft(documentValue, "");
      next.paragraphs = (next.paragraphs || []).map((paragraph) => {
        if (String(paragraph?.id || "").trim() !== normalizedId) {
          return paragraph;
        }
        return {
          ...paragraph,
          text: normalizeRichPlainText(payload.text || ""),
          rich_text: String(payload.richText || payload.rich_text || "").trim() || null,
          richText: String(payload.richText || payload.rich_text || "").trim() || null,
          align: normalizeRichAlign(payload.align || paragraph.align || "left"),
        };
      });
      return next;
    }, { markDirty: true, rerender: false });
    return true;
  }

  function readFloatingObjectFrameFromDom(objectId = "", fallbackFrame = {}) {
    const normalizedId = String(objectId || "").trim();
    const composePanel = document.querySelector("#noticesComposePanel:not(.hidden)");
    const objectEl = normalizedId
      ? (
        composePanel?.querySelector?.(`[data-notice-scene-object-id="${normalizedId}"]`)
        || document.querySelector(`#noticesComposeDocumentFlow [data-notice-scene-object-id="${normalizedId}"]`)
      )
      : null;
    if (!(objectEl instanceof HTMLElement)) {
      return createFloatingObjectFrame(fallbackFrame || {});
    }
    return createFloatingObjectFrame({
      x: Number.parseFloat(objectEl.dataset.noticeFrameX || objectEl.style.left || fallbackFrame?.x || 0),
      y: Number.parseFloat(objectEl.dataset.noticeFrameY || objectEl.style.top || fallbackFrame?.y || 0),
      width: Number.parseFloat(objectEl.dataset.noticeFrameWidth || objectEl.style.width || fallbackFrame?.width || 0),
      height: Number.parseFloat(objectEl.dataset.noticeFrameHeight || objectEl.style.minHeight || fallbackFrame?.height || 0),
    });
  }

  function readFloatingTableDraftFromDom(objectId = "", fallbackTable = {}) {
    const normalizedId = String(objectId || "").trim();
    const nextTable = cloneTableDraft(fallbackTable);
    if (!normalizedId) {
      return nextTable;
    }
    const composePanel = document.querySelector("#noticesComposePanel:not(.hidden)");
    const tableEl = composePanel?.querySelector?.(`.notices-compose-table-shell[data-notice-table-block-id="${normalizedId}"] .notices-compose-table`)
      || document.querySelector(`#noticesComposeDocumentFlow .notices-compose-table-shell[data-notice-table-block-id="${normalizedId}"] .notices-compose-table`);
    if (tableEl instanceof HTMLTableElement) {
      const colWidths = Array.from(tableEl.querySelectorAll("colgroup col")).map((col) => Math.max(72, Math.round(col.getBoundingClientRect().width || 0)));
      if (colWidths.length) {
        nextTable.columnWidths = colWidths;
      }
      const rowHeights = [];
      const headRow = tableEl.querySelector("thead tr");
      if (headRow instanceof HTMLElement) {
        rowHeights.push(Math.max(36, Math.round(headRow.getBoundingClientRect().height || 0)));
      }
      Array.from(tableEl.querySelectorAll("tbody tr")).forEach((row) => {
        if (row instanceof HTMLElement) {
          rowHeights.push(Math.max(36, Math.round(row.getBoundingClientRect().height || 0)));
        }
      });
      if (rowHeights.length) {
        nextTable.rowHeights = rowHeights;
      }
    }
    const headerEditors = Array.from(document.querySelectorAll(
      `[data-notice-rich-editor="true"][data-notice-table-block-id="${normalizedId}"][data-notice-table-field="header"]`
    ));
    if (headerEditors.length) {
      const columns = [];
      const columnsRich = [];
      headerEditors.forEach((editor) => {
        if (!(editor instanceof HTMLElement)) {
          return;
        }
        const colIndex = Math.max(0, Number(editor.dataset.noticeTableCol || 0) || 0);
        const payload = readRichEditorPayload(editor);
        columns[colIndex] = payload.text;
        columnsRich[colIndex] = payload;
      });
      nextTable.columns = columns.map((value) => String(value || ""));
      nextTable.columnsRich = columns.map((value, index) => cloneRichCellDraft(columnsRich[index], value));
    }

    const cellEditors = Array.from(document.querySelectorAll(
      `[data-notice-rich-editor="true"][data-notice-table-block-id="${normalizedId}"][data-notice-table-field="cell"]`
    ));
    if (cellEditors.length) {
      const rows = [];
      const rowsRich = [];
      cellEditors.forEach((editor) => {
        if (!(editor instanceof HTMLElement)) {
          return;
        }
        const rowIndex = Math.max(0, Number(editor.dataset.noticeTableRow || 0) || 0);
        const colIndex = Math.max(0, Number(editor.dataset.noticeTableCol || 0) || 0);
        const payload = readRichEditorPayload(editor);
        if (!Array.isArray(rows[rowIndex])) {
          rows[rowIndex] = Array.from({ length: nextTable.columns.length || 1 }, () => "");
        }
        if (!Array.isArray(rowsRich[rowIndex])) {
          rowsRich[rowIndex] = Array.from({ length: nextTable.columns.length || 1 }, () => createDefaultRichCell(""));
        }
        rows[rowIndex][colIndex] = payload.text;
        rowsRich[rowIndex][colIndex] = payload;
      });
      nextTable.rows = rows.map((row) => Array.isArray(row) ? row.map((value) => String(value || "")) : []);
      nextTable.rowsRich = nextTable.rows.map((row, rowIndex) => row.map((cell, colIndex) => (
        cloneRichCellDraft(rowsRich[rowIndex]?.[colIndex], cell)
      )));
    }
    nextTable.enabled = true;
    return nextTable;
  }

  function syncFloatingComposeDraftFromDom({ markDirty = false } = {}) {
    const workspace = ensureWorkspaceState();
    if (!usesStructuredNoticeDocumentModel(workspace.composeDraft?.bodyModel)) {
      return workspace.composeDraft?.bodyDocument || null;
    }
    const current = isFlowLaneNoticeModel(workspace.composeDraft?.bodyModel)
      ? normalizeFlowLaneDocumentDraft(workspace.composeDraft?.bodyDocument, workspace.composeDraft?.bodyText || "")
      : normalizeFloatingDocumentDraft(workspace.composeDraft?.bodyDocument, workspace.composeDraft?.bodyText || "");
    const paragraphEditors = Array.from(document.querySelectorAll(
      '[data-notice-rich-editor="true"][data-notice-compose-editor-kind="paragraph"][data-notice-compose-block-id]'
    ));
    const paragraphMap = new Map((current.paragraphs || []).map((paragraph) => [String(paragraph?.id || "").trim(), paragraph]));
    const paragraphs = paragraphEditors.length
      ? paragraphEditors.map((editor, index) => {
        const blockId = String(editor.dataset.noticeComposeBlockId || "").trim() || createNoticeBlockId("paragraph");
        const existing = paragraphMap.get(blockId) || {};
        const payload = readRichEditorPayload(editor);
        return createFloatingParagraphDraft(index, {
          ...existing,
          id: blockId,
          flow_index: editor.dataset.noticeFlowIndex != null
            ? Math.max(0, Number(editor.dataset.noticeFlowIndex || index) || index)
            : Math.max(0, Number(existing.flow_index ?? existing.flowIndex ?? index) || index),
          text: payload.text,
          rich_text: payload.richText || null,
          richText: payload.richText || null,
          align: payload.align,
        });
      })
      : (current.paragraphs || []);

    const objects = (current.objects || []).map((item) => {
      const normalizedId = String(item?.id || "").trim();
      const frame = readFloatingObjectFrameFromDom(normalizedId, item?.frame || {});
      if (String(item?.kind || "").trim() === "table") {
        return {
          ...item,
          frame,
          table: readFloatingTableDraftFromDom(normalizedId, item?.table || {}),
        };
      }
      return {
        ...item,
        frame,
      };
    });

    const nextDocument = sortFloatingDocumentInPlace({
      ...current,
      paragraphs,
      objects,
      version: isFlowLaneNoticeModel(workspace.composeDraft?.bodyModel)
        ? SOC_NOTICE_FLOW_LANE_DOCUMENT_VERSION
        : (current.version || SOC_NOTICE_FLOATING_DOCUMENT_VERSION),
    });
    workspace.composeDraft = {
      ...(workspace.composeDraft || createDefaultComposeDraft(workspace.category === "all" ? "ops" : workspace.category)),
      bodyModel: isFlowLaneNoticeModel(workspace.composeDraft?.bodyModel)
        ? SOC_NOTICE_BODY_MODEL_FLOW_LANE
        : SOC_NOTICE_BODY_MODEL_FLOATING,
      bodyDocument: nextDocument,
      bodyText: buildFloatingDocumentBodyText(nextDocument),
      imagesEnabled: objects.some((item) => String(item?.kind || "").trim() === "image"),
    };
    if (markDirty) {
      markComposeDraftDirty();
    }
    return nextDocument;
  }

  function readRichPlainTextFromNode(node = null) {
    if (!node) {
      return "";
    }
    if (node.nodeType === Node.TEXT_NODE) {
      return String(node.textContent || "");
    }
    if (node.nodeType === Node.DOCUMENT_FRAGMENT_NODE) {
      return Array.from(node.childNodes || []).map((child) => readRichPlainTextFromNode(child)).join("");
    }
    if (node instanceof HTMLBRElement) {
      return "\n";
    }
    if (!(node instanceof Node)) {
      return "";
    }
    return Array.from(node.childNodes || []).map((child) => readRichPlainTextFromNode(child)).join("");
  }

  function measureRichPlainTextLength(node = null) {
    return readRichPlainTextFromNode(node).length;
  }

  function collectRichTextUnits(root = null) {
    const units = [];
    let cursor = 0;
    const visit = (node) => {
      if (!node) {
        return;
      }
      if (node.nodeType === Node.TEXT_NODE) {
        const text = String(node.textContent || "");
        if (!text) {
          return;
        }
        units.push({ type: "text", node, start: cursor, end: cursor + text.length });
        cursor += text.length;
        return;
      }
      if (node instanceof HTMLBRElement) {
        units.push({ type: "br", node, start: cursor, end: cursor + 1 });
        cursor += 1;
        return;
      }
      Array.from(node.childNodes || []).forEach(visit);
    };
    Array.from(root?.childNodes || []).forEach(visit);
    return { units, length: cursor };
  }

  function locateRichTextBoundary(root = null, rawOffset = 0) {
    if (!(root instanceof HTMLElement)) {
      return { container: root || document.body, offset: 0 };
    }
    const { units, length } = collectRichTextUnits(root);
    const offset = Math.max(0, Math.min(length, Number(rawOffset) || 0));
    if (!units.length) {
      return { container: root, offset: 0 };
    }
    for (const unit of units) {
      if (unit.type === "text") {
        if (offset <= unit.end) {
          return {
            container: unit.node,
            offset: Math.max(0, Math.min(String(unit.node.textContent || "").length, offset - unit.start)),
          };
        }
        continue;
      }
      const parent = unit.node.parentNode || root;
      const index = Array.prototype.indexOf.call(parent.childNodes, unit.node);
      if (offset <= unit.start) {
        return { container: parent, offset: Math.max(0, index) };
      }
      if (offset <= unit.end) {
        return { container: parent, offset: Math.max(0, index) + 1 };
      }
    }
    const lastUnit = units[units.length - 1];
    if (lastUnit.type === "text") {
      return {
        container: lastUnit.node,
        offset: String(lastUnit.node.textContent || "").length,
      };
    }
    const parent = lastUnit.node.parentNode || root;
    const index = Array.prototype.indexOf.call(parent.childNodes, lastUnit.node);
    return { container: parent, offset: Math.max(0, index) + 1 };
  }

  function fragmentHtmlForRichOffsets(root = null, start = 0, end = 0) {
    if (!(root instanceof HTMLElement)) {
      return "";
    }
    const { length } = collectRichTextUnits(root);
    const clampedStart = Math.max(0, Math.min(length, Number(start) || 0));
    const clampedEnd = Math.max(clampedStart, Math.min(length, Number(end) || 0));
    if (clampedStart === clampedEnd) {
      return "";
    }
    const range = document.createRange();
    const startBoundary = locateRichTextBoundary(root, clampedStart);
    const endBoundary = locateRichTextBoundary(root, clampedEnd);
    range.setStart(startBoundary.container, startBoundary.offset);
    range.setEnd(endBoundary.container, endBoundary.offset);
    const container = document.createElement("div");
    container.appendChild(range.cloneContents());
    return container.innerHTML;
  }

  function getRichEditorSelectionOffsets(editorEl = null, range = null) {
    if (!(editorEl instanceof HTMLElement) || !(range instanceof Range)) {
      return null;
    }
    try {
      const prefixRange = document.createRange();
      prefixRange.selectNodeContents(editorEl);
      prefixRange.setEnd(range.startContainer, range.startOffset);
      const start = measureRichPlainTextLength(prefixRange.cloneContents());
      const selectedLength = measureRichPlainTextLength(range.cloneContents());
      return {
        start,
        end: start + selectedLength,
      };
    } catch {
      return null;
    }
  }

  function buildParagraphSplitPayload(block = {}, start = 0, end = 0) {
    const text = String(block?.text || "").replace(/\r\n/g, "\n");
    const richText = richTextValueFromRaw(block) || plainTextToRichHtml(text);
    const container = document.createElement("div");
    container.innerHTML = richText;
    const textLength = measureRichPlainTextLength(container);
    const splitStart = Math.max(0, Math.min(textLength, Number(start) || 0));
    const splitEnd = Math.max(splitStart, Math.min(textLength, Number(end) || 0));
    const beforeText = text.slice(0, splitStart);
    const afterText = text.slice(splitEnd);
    return {
      before: createParagraphBlockFromPayload({
        id: String(block?.id || "").trim() || createNoticeBlockId("paragraph"),
        text: beforeText,
        richText: fragmentHtmlForRichOffsets(container, 0, splitStart),
        align: normalizeRichAlign(block?.align || "left"),
      }),
      after: createParagraphBlockFromPayload({
        id: createNoticeBlockId("paragraph"),
        text: afterText,
        richText: fragmentHtmlForRichOffsets(container, splitEnd, textLength),
        align: normalizeRichAlign(block?.align || "left"),
      }),
    };
  }

  function normalizeRichFontSizeToken(value = "") {
    const normalized = String(value || "").trim().replace(/pt$/i, "");
    if (!normalized) {
      return "";
    }
    const numeric = Number(normalized);
    if (!Number.isFinite(numeric)) {
      return "";
    }
    const compact = Number.isInteger(numeric)
      ? String(numeric)
      : String(Number.parseFloat(numeric.toFixed(1)));
    return SOC_NOTICE_RICH_FONT_SIZE_OPTIONS.includes(compact) ? compact : "";
  }

  function normalizeRichFontSizePx(value = "") {
    const raw = String(value || "").trim().replace(/px$/i, "");
    if (!/^\d+(?:\.\d+)?$/.test(raw)) {
      return "";
    }
    const numeric = Number(raw);
    if (!Number.isFinite(numeric) || numeric < 1) {
      return "";
    }
    const rounded = Number(raw);
    const text = Number.isInteger(rounded)
      ? String(rounded)
      : String(Number.parseFloat(rounded.toFixed(3)));
    return text.replace(/\.0+$/, "").replace(/(\.\d*?)0+$/, "$1");
  }

  function resolveRichSwatchColor(kind = "text", token = "") {
    const normalizedKind = String(kind || "").trim().toLowerCase();
    const normalizedToken = String(token || "").trim().toLowerCase();
    const swatches = normalizedKind === "bg" ? SOC_NOTICE_RICH_BG_SWATCHES : SOC_NOTICE_RICH_TEXT_SWATCHES;
    return swatches.find((item) => item.token === normalizedToken)?.swatch
      || (normalizedKind === "bg" ? "#fff36a" : "#202430");
  }

  function clearComposeFormatMenuState() {
    ensureWorkspaceState().composeFormatMenu = "";
  }

  function renderComposeFormatControls(elements, workspace) {
    const activeMenu = String(workspace.composeFormatMenu || "").trim();
    const sizeOpen = activeMenu === "size";
    const textOpen = activeMenu === "text-color";
    const highlightOpen = activeMenu === "highlight";
    if (elements.composeFontSizeInput instanceof HTMLInputElement) {
      elements.composeFontSizeInput.value = String(workspace.composeFontSizeDraft || SOC_NOTICE_RICH_FONT_SIZE_DEFAULT);
    }
    if (elements.composeFontSizeMenu instanceof HTMLElement) {
      elements.composeFontSizeMenu.classList.toggle("hidden", !sizeOpen);
    }
    if (elements.composeFontSizeToggleBtn instanceof HTMLButtonElement) {
      elements.composeFontSizeToggleBtn.setAttribute("aria-expanded", sizeOpen ? "true" : "false");
      elements.composeFontSizeToggleBtn.classList.toggle("is-active", sizeOpen);
    }
    if (elements.composeTextColorPalette instanceof HTMLElement) {
      elements.composeTextColorPalette.classList.toggle("hidden", !textOpen);
    }
    if (elements.composeTextColorBtn instanceof HTMLButtonElement) {
      elements.composeTextColorBtn.setAttribute("aria-expanded", textOpen ? "true" : "false");
      elements.composeTextColorBtn.classList.toggle("is-active", textOpen);
      elements.composeTextColorBtn.style.setProperty("--notice-toolbar-text-color", resolveRichSwatchColor("text", workspace.composeTextColorToken || "default"));
    }
    if (elements.composeHighlightPalette instanceof HTMLElement) {
      elements.composeHighlightPalette.classList.toggle("hidden", !highlightOpen);
    }
    if (elements.composeHighlightBtn instanceof HTMLButtonElement) {
      elements.composeHighlightBtn.setAttribute("aria-expanded", highlightOpen ? "true" : "false");
      elements.composeHighlightBtn.classList.toggle("is-active", highlightOpen);
      elements.composeHighlightBtn.style.setProperty("--notice-toolbar-highlight-color", resolveRichSwatchColor("bg", workspace.composeHighlightToken || "yellow-soft"));
    }
  }

  function toggleComposeFormatMenu(menuName = "") {
    const workspace = ensureWorkspaceState();
    const normalized = String(menuName || "").trim();
    workspace.composeFormatMenu = workspace.composeFormatMenu === normalized ? "" : normalized;
    renderComposeFormatControls(getWorkspaceElements(), workspace);
  }

  function applyComposeFontSize(rawValue = "", { closeMenu = true } = {}) {
    const token = normalizeRichFontSizePx(rawValue);
    if (!token) {
      socToast("1 이상의 숫자 크기를 입력해 주세요.", "info", 2200);
      return false;
    }
    restoreComposeRichSelection();
    const applied = wrapRichSelection(() => {
      const el = document.createElement("span");
      el.setAttribute("data-rt-size-px", token);
      return el;
    });
    if (!applied) {
      socToast("서식을 적용할 텍스트를 먼저 선택해 주세요.", "info", 2200);
      return false;
    }
    const editorEl = getActiveRichEditorElement();
    notifyRichEditorMutation(editorEl);
    const workspace = ensureWorkspaceState();
    workspace.composeFontSizeDraft = token;
    if (closeMenu) {
      clearComposeFormatMenuState();
    }
    renderComposeFormatControls(getWorkspaceElements(), workspace);
    return true;
  }

  function applyComposeTextColor(token = "", { closeMenu = true } = {}) {
    const normalized = String(token || "").trim().toLowerCase();
    if (!applyInlineSpanToken("data-rt-color", normalized)) {
      return false;
    }
    const workspace = ensureWorkspaceState();
    workspace.composeTextColorToken = normalized;
    if (closeMenu) {
      clearComposeFormatMenuState();
    }
    renderComposeFormatControls(getWorkspaceElements(), workspace);
    return true;
  }

  function applyComposeHighlight(token = "", { closeMenu = true } = {}) {
    const normalized = String(token || "").trim().toLowerCase();
    if (!applyInlineSpanToken("data-rt-bg", normalized)) {
      return false;
    }
    const workspace = ensureWorkspaceState();
    workspace.composeHighlightToken = normalized;
    if (closeMenu) {
      clearComposeFormatMenuState();
    }
    renderComposeFormatControls(getWorkspaceElements(), workspace);
    return true;
  }

  function normalizeComposeContentBlocks(rawBlocks = null, fallbackBodyText = "", legacyTable = null, legacyPoll = null) {
    const normalized = [];
    if (Array.isArray(rawBlocks) && rawBlocks.length) {
      rawBlocks.forEach((item) => {
        const block = item && typeof item === "object" ? item : {};
        const kind = String(block.kind || "").trim().toLowerCase();
        const blockId = String(block.id || "").trim() || createNoticeBlockId(kind || "block");
        if (kind === "paragraph") {
          normalized.push({
            id: blockId,
            kind: "paragraph",
            text: String(block.text || "").replace(/\r\n/g, "\n"),
            richText: richTextValueFromRaw(block),
            align: normalizeRichAlign(block.align || "left"),
          });
          return;
        }
        if (kind === "table") {
          normalized.push({
            id: blockId,
            kind: "table",
            table: cloneTableDraft({
              enabled: true,
              ...((block.table && typeof block.table === "object") ? block.table : block),
            }),
          });
          return;
        }
        if (kind === "poll") {
          normalized.push({
            id: blockId,
            kind: "poll",
            poll: clonePollDraft({
              enabled: true,
              ...((block.poll && typeof block.poll === "object") ? block.poll : block),
            }),
          });
        }
      });
    }
    if (!normalized.length) {
      String(fallbackBodyText || "")
        .split(/\n{2,}/)
        .map((text) => text.trim())
        .filter(Boolean)
        .forEach((text) => {
          normalized.push({
            id: createNoticeBlockId("paragraph"),
            kind: "paragraph",
            text,
          });
        });
      const legacyTableDraft = cloneTableDraft(legacyTable);
      if (legacyTableDraft.enabled) {
        normalized.push({
          id: createNoticeBlockId("table"),
          kind: "table",
          table: legacyTableDraft,
        });
      }
      const legacyPollDraft = clonePollDraft(legacyPoll);
      if (legacyPollDraft.enabled && String(legacyPollDraft.question || "").trim()) {
        normalized.push({
          id: createNoticeBlockId("poll"),
          kind: "poll",
          poll: legacyPollDraft,
        });
      }
    }
    if (!normalized.length) {
      return createDefaultComposeContentBlocks();
    }
    const coalesced = [];
    normalized.forEach((block) => {
      if (block.kind !== "paragraph") {
        coalesced.push(block);
        return;
      }
      const prev = coalesced[coalesced.length - 1];
      const text = String(block.text || "").replace(/\r\n/g, "\n");
      const richText = richTextValueFromRaw(block);
      const align = normalizeRichAlign(block.align || "left");
      const prevHasFormatting = prev?.kind === "paragraph" && (String(prev.richText || "").trim() || normalizeRichAlign(prev.align || "left") !== "left");
      const nextHasFormatting = Boolean(richText) || align !== "left";
      if (prev?.kind === "paragraph" && !prevHasFormatting && !nextHasFormatting) {
        const prevText = String(prev.text || "");
        if (!prevText && !text) {
          return;
        }
        if (!prevText) {
          prev.text = text;
          return;
        }
        if (!text) {
          return;
        }
        prev.text = `${prevText}\n${text}`;
        return;
      }
      coalesced.push({
        id: String(block.id || "").trim() || createNoticeBlockId("paragraph"),
        kind: "paragraph",
        text,
        richText,
        align,
      });
    });
    if (!coalesced.some((block) => block.kind === "paragraph")) {
      coalesced.push({
        id: createNoticeBlockId("paragraph"),
        kind: "paragraph",
        text: "",
      });
    }
    return coalesced;
  }

  function cloneComposeContentBlocks(rawBlocks = null, fallbackBodyText = "", legacyTable = null, legacyPoll = null) {
    return normalizeComposeContentBlocks(rawBlocks, fallbackBodyText, legacyTable, legacyPoll).map((block) => {
      if (block.kind === "table") {
        return {
          id: String(block.id || "").trim() || createNoticeBlockId("table"),
          kind: "table",
          table: cloneTableDraft(block.table),
        };
      }
      if (block.kind === "poll") {
        return {
          id: String(block.id || "").trim() || createNoticeBlockId("poll"),
          kind: "poll",
          poll: clonePollDraft(block.poll),
        };
      }
      return {
        id: String(block.id || "").trim() || createNoticeBlockId("paragraph"),
        kind: "paragraph",
        text: String(block.text || ""),
        richText: richTextValueFromRaw(block),
        align: normalizeRichAlign(block.align || "left"),
      };
    });
  }

  function buildComposeBodyTextFromContentBlocks(rawBlocks = null) {
    return normalizeComposeContentBlocks(rawBlocks)
      .map((block) => {
        if (block.kind === "paragraph") {
          return normalizeRichPlainText(block.text || "");
        }
        if (block.kind === "table") {
          return buildTableBlockBodyText(block.table || block);
        }
        return "";
      })
      .filter(Boolean)
      .join("\n\n");
  }

  function getComposeContentBlocks(draft = null) {
    const source = draft && typeof draft === "object" ? draft : {};
    return cloneComposeContentBlocks(source.composeContentBlocks, source.bodyText, source.table, source.poll);
  }

  function createDefaultComposeDraft(category = "ops") {
    const bodyDocument = createDefaultFlowLaneDocument();
    return {
      category: normalizeNoticeCategory(category, false),
      title: "",
      bodyText: buildFloatingDocumentBodyText(bodyDocument),
      bodyModel: SOC_NOTICE_BODY_MODEL_FLOW_LANE,
      bodyDocument,
      composeContentBlocks: createDefaultComposeContentBlocks(),
      flowOrder: ["body"],
      isPinned: false,
      imagesEnabled: false,
      images: [],
      table: createDefaultTableDraft(),
      poll: createDefaultPollDraft(),
    };
  }

  function createInitialWorkspaceState() {
    return {
      category: "all",
      search: "",
      searchDraft: "",
      searchExpanded: false,
      mode: SOC_NOTICE_VIEW_MODE_LIST,
      selectedNoticeId: "",
      selectedRow: null,
      rows: [],
      loading: false,
      detailLoading: false,
      pollSubmittingId: "",
      error: "",
      composeDraft: createDefaultComposeDraft("ops"),
      composeEditingId: "",
      composeAutosaveTimer: 0,
      composeDirtySinceLoad: false,
      draftSavedAt: "",
      draftStorageMessage: "",
      composeTablePickerOpen: false,
      composeTablePickerRows: 2,
      composeTablePickerCols: 2,
      composePollModalOpen: false,
      composePollModalDraft: createDefaultPollDraft(),
      composePollModalBlockId: "",
      composeInsertionAnchor: null,
      composePollModalTriggerEl: null,
      composeLinkModalOpen: false,
      composeLinkModalUrlDraft: "",
      composeLinkModalSelectionRange: null,
      composeLinkModalEditorDescriptor: null,
      composeLinkModalAnchorHref: "",
      composeLinkModalHadExpandedSelection: false,
      composeFormatMenu: "",
      composeFontSizeDraft: SOC_NOTICE_RICH_FONT_SIZE_DEFAULT,
      composeTextColorToken: "default",
      composeHighlightToken: "yellow-soft",
    };
  }

  function ensureWorkspaceState() {
    if (!rootState.socNoticeWorkspace || typeof rootState.socNoticeWorkspace !== "object") {
      rootState.socNoticeWorkspace = createInitialWorkspaceState();
    }
    return rootState.socNoticeWorkspace;
  }

  function getComposeActorKey() {
    const user = rootState.user && typeof rootState.user === "object" ? rootState.user : {};
    const tenantId = String(user.tenant_id || user.tenantId || "tenant").trim() || "tenant";
    const actorId = String(user.id || user.user_id || user.username || "user").trim() || "user";
    return `${tenantId}:${actorId}`;
  }

  function getComposeDraftStorageKey({ noticeId = "" } = {}) {
    const scope = String(noticeId || "").trim() ? `edit:${String(noticeId || "").trim()}` : "new";
    return `${SOC_NOTICE_COMPOSE_DRAFT_STORAGE_PREFIX}:${getComposeActorKey()}:${scope}`;
  }

  function readStoredJson(key = "", fallbackValue = null) {
    try {
      const raw = window.localStorage?.getItem(String(key || "").trim());
      if (!raw) {
        return fallbackValue;
      }
      return JSON.parse(raw);
    } catch {
      return fallbackValue;
    }
  }

  function writeStoredJson(key = "", value = null) {
    try {
      window.localStorage?.setItem(String(key || "").trim(), JSON.stringify(value));
    } catch {
      // no-op
    }
  }

  function clearComposeDraftStorage({ noticeId = "" } = {}) {
    try {
      window.localStorage?.removeItem(getComposeDraftStorageKey({ noticeId }));
    } catch {
      // no-op
    }
  }

  function buildSerializableComposeDraft(draft = null) {
    const source = draft && typeof draft === "object" ? draft : {};
    if (isFlowLaneNoticeModel(source.bodyModel) || isFloatingNoticeModel(source.bodyModel) || source.bodyDocument) {
      const bodyDocument = isFlowLaneNoticeModel(source.bodyModel)
        ? normalizeFlowLaneDocumentDraft(source.bodyDocument, source.bodyText || "", source.bodyBlocks)
        : normalizeFlowLaneDocumentDraft(source.bodyDocument, source.bodyText || "", source.bodyBlocks);
      return {
        category: normalizeNoticeCategory(source.category || "ops", false),
        title: String(source.title || ""),
        bodyModel: SOC_NOTICE_BODY_MODEL_FLOW_LANE,
        bodyDocument,
        bodyText: buildFloatingDocumentBodyText(bodyDocument),
        flowOrder: ["body"],
        isPinned: Boolean(source.isPinned),
        imagesEnabled: (bodyDocument.objects || []).some((item) => String(item.kind || "").trim() === "image"),
        images: [],
        table: createDefaultTableDraft(),
        poll: createDefaultPollDraft(),
      };
    }
    const composeContentBlocks = cloneComposeContentBlocks(source.composeContentBlocks, source.bodyText, source.table, source.poll);
    const tableBlock = composeContentBlocks.find((block) => block.kind === "table");
    const pollBlock = composeContentBlocks.find((block) => block.kind === "poll");
    return {
      category: normalizeNoticeCategory(source.category || "ops", false),
      title: String(source.title || ""),
      bodyText: buildComposeBodyTextFromContentBlocks(composeContentBlocks),
      composeContentBlocks,
      flowOrder: normalizeComposeFlowOrder(
        composeContentBlocks.map((block) => (block.kind === "paragraph" ? "body" : block.kind)),
        {
          ...source,
          table: tableBlock ? cloneTableDraft(tableBlock.table) : createDefaultTableDraft(),
          poll: pollBlock ? clonePollDraft(pollBlock.poll) : createDefaultPollDraft(),
        }
      ),
      isPinned: Boolean(source.isPinned),
      imagesEnabled: Boolean(source.imagesEnabled),
      images: cloneImageDrafts(source.images),
      table: tableBlock ? cloneTableDraft(tableBlock.table) : cloneTableDraft(source.table),
      poll: pollBlock ? clonePollDraft(pollBlock.poll) : clonePollDraft(source.poll),
    };
  }

  function normalizeSavedComposeDraft(raw = null, fallbackCategory = "ops") {
    const source = raw && typeof raw === "object" ? raw : {};
    if (isFlowLaneNoticeModel(source.bodyModel) || isFloatingNoticeModel(source.bodyModel) || source.bodyDocument) {
      const bodyDocument = normalizeFlowLaneDocumentDraft(source.bodyDocument, source.bodyText || "", source.bodyBlocks);
      return {
        category: normalizeNoticeCategory(source.category || fallbackCategory || "ops", false),
        title: String(source.title || ""),
        bodyText: buildFloatingDocumentBodyText(bodyDocument),
        bodyModel: SOC_NOTICE_BODY_MODEL_FLOW_LANE,
        bodyDocument,
        composeContentBlocks: createDefaultComposeContentBlocks(),
        flowOrder: ["body"],
        isPinned: Boolean(source.isPinned),
        imagesEnabled: (bodyDocument.objects || []).some((item) => String(item.kind || "").trim() === "image"),
        images: [],
        table: createDefaultTableDraft(),
        poll: createDefaultPollDraft(),
      };
    }
    const images = cloneImageDrafts(source.images);
    const composeContentBlocks = cloneComposeContentBlocks(source.composeContentBlocks, source.bodyText, source.table, source.poll);
    const bodyDocument = normalizeFlowLaneDocumentDraft(
      null,
      source.bodyText || ""
      ,
      normalizeBodyBlocks(composeContentBlocks, source.bodyText || "")
    );
    const tableBlock = composeContentBlocks.find((block) => block.kind === "table");
    const pollBlock = composeContentBlocks.find((block) => block.kind === "poll");
    const draft = {
      category: normalizeNoticeCategory(source.category || fallbackCategory || "ops", false),
      title: String(source.title || ""),
      bodyText: buildFloatingDocumentBodyText(bodyDocument),
      bodyModel: SOC_NOTICE_BODY_MODEL_FLOW_LANE,
      bodyDocument,
      composeContentBlocks,
      flowOrder: [],
      isPinned: Boolean(source.isPinned),
      imagesEnabled: (bodyDocument.objects || []).some((item) => String(item.kind || "").trim() === "image") || Boolean(source.imagesEnabled) || images.length > 0,
      images: [],
      table: tableBlock ? cloneTableDraft(tableBlock.table) : cloneTableDraft(source.table),
      poll: pollBlock ? clonePollDraft(pollBlock.poll) : clonePollDraft(source.poll),
    };
    draft.flowOrder = ["body"];
    return draft;
  }

  function resetComposeDraftMeta() {
    const workspace = ensureWorkspaceState();
    workspace.composeDirtySinceLoad = false;
    workspace.draftSavedAt = "";
    workspace.draftStorageMessage = "";
  }

  function restoreSavedComposeDraft({ noticeId = "", fallbackCategory = "ops" } = {}) {
    const saved = readStoredJson(getComposeDraftStorageKey({ noticeId }), null);
    if (!saved || typeof saved !== "object") {
      return false;
    }
    const workspace = ensureWorkspaceState();
    workspace.composeDraft = normalizeSavedComposeDraft(saved.draft, fallbackCategory);
    workspace.draftSavedAt = String(saved.savedAt || "").trim();
    workspace.draftStorageMessage = "자동 저장된 초안을 복원했습니다.";
    return true;
  }

  function renderComposeDraftMeta(elements = getWorkspaceElements()) {
    const draftMetaEl = elements?.composeDraftMeta;
    if (!(draftMetaEl instanceof HTMLElement)) {
      return;
    }
    const workspace = ensureWorkspaceState();
    const savedAtLabel = workspace.draftSavedAt
      ? formatDateTimeLabel(workspace.draftSavedAt, workspace.draftSavedAt)
      : "";
    if (String(workspace.draftStorageMessage || "").trim() && savedAtLabel) {
      draftMetaEl.textContent = `${String(workspace.draftStorageMessage || "").trim()} · 마지막 저장 ${savedAtLabel}`;
      return;
    }
    if (String(workspace.draftStorageMessage || "").trim()) {
      draftMetaEl.textContent = String(workspace.draftStorageMessage || "").trim();
      return;
    }
    if (savedAtLabel) {
      draftMetaEl.textContent = `자동 저장됨 · ${savedAtLabel}`;
      return;
    }
    draftMetaEl.textContent = "자동 저장 전입니다.";
  }

  function clearComposeAutosaveTimer() {
    const workspace = ensureWorkspaceState();
    if (typeof workspace.composeAutosaveTimer === "number" && workspace.composeAutosaveTimer) {
      window.clearTimeout(workspace.composeAutosaveTimer);
    }
    workspace.composeAutosaveTimer = 0;
  }

  function saveComposeDraftToStorage({ message = "자동 저장됨" } = {}) {
    const workspace = ensureWorkspaceState();
    if (usesStructuredNoticeDocumentModel(workspace.composeDraft?.bodyModel)) {
      syncFloatingComposeDraftFromDom({ markDirty: false });
    }
    clearComposeAutosaveTimer();
    const noticeId = workspace.mode === SOC_NOTICE_VIEW_MODE_COMPOSE
      ? String(workspace.composeEditingId || workspace.selectedNoticeId || "").trim()
      : "";
    const savedAt = new Date().toISOString();
    writeStoredJson(getComposeDraftStorageKey({ noticeId }), {
      version: 1,
      savedAt,
      draft: buildSerializableComposeDraft(workspace.composeDraft),
    });
    workspace.draftSavedAt = savedAt;
    workspace.draftStorageMessage = message;
    renderComposeDraftMeta();
  }

  function scheduleComposeAutosave({ immediate = false } = {}) {
    if (!canManageSocNotices()) {
      return;
    }
    clearComposeAutosaveTimer();
    const commit = () => {
      saveComposeDraftToStorage({ message: "자동 저장됨" });
    };
    if (immediate) {
      commit();
      return;
    }
    const workspace = ensureWorkspaceState();
    workspace.composeAutosaveTimer = window.setTimeout(() => {
      commit();
    }, SOC_NOTICE_COMPOSE_AUTOSAVE_DELAY_MS);
  }

  function markComposeDraftDirty() {
    const workspace = ensureWorkspaceState();
    workspace.composeDirtySinceLoad = true;
    workspace.draftStorageMessage = "저장 중…";
    renderComposeDraftMeta();
    if (workspace.mode === SOC_NOTICE_VIEW_MODE_COMPOSE && canManageSocNotices()) {
      scheduleComposeAutosave();
    }
  }

  function getHashRouteParts(hashRaw = "") {
    const raw = String(hashRaw || window.location.hash || "").trim().replace(/^#/, "");
    const queryIndex = raw.indexOf("?");
    const path = queryIndex >= 0 ? raw.slice(0, queryIndex) : raw;
    const query = queryIndex >= 0 ? raw.slice(queryIndex + 1) : "";
    return {
      raw,
      path,
      query,
      params: new URLSearchParams(query),
    };
  }

  function parseAnnouncementHashState(hashRaw = "") {
    const parts = getHashRouteParts(hashRaw);
    const normalizedPath = String(parts.path || "").trim().replace(/^\/+/, "").toLowerCase();
    if (!(
      normalizedPath.startsWith("admin/announcement") ||
      normalizedPath.startsWith("admin/announcements") ||
      normalizedPath.startsWith("feature/notices")
    )) {
      return null;
    }
    const params = parts.params;
    const noticeId = String(params.get("notice") || params.get("announcement") || "").trim();
    const requestedMode = normalizeNoticeMode(params.get("mode") || "");
    let mode = requestedMode;
    if (requestedMode !== SOC_NOTICE_VIEW_MODE_COMPOSE && noticeId) {
      mode = SOC_NOTICE_VIEW_MODE_DETAIL;
    }
    return {
      category: normalizeNoticeCategory(params.get("category") || "all"),
      search: normalizeNoticeSearch(params.get("q") || params.get("search") || ""),
      noticeId,
      mode,
    };
  }

  function normalizeNoticeRecord(raw = {}) {
    const bodyBlocks = Array.isArray(raw.bodyBlocks)
      ? raw.bodyBlocks
      : (Array.isArray(raw.body_blocks) ? raw.body_blocks : []);
    const bodyModel = normalizeNoticeBodyModel(raw.bodyModel || raw.body_model || "");
    const bodyDocument = raw.bodyDocument && typeof raw.bodyDocument === "object"
      ? raw.bodyDocument
      : (raw.body_document && typeof raw.body_document === "object" ? raw.body_document : null);
    return {
      id: String(raw.id || "").trim(),
      title: String(raw.title || "").trim(),
      category: normalizeNoticeCategory(raw.category || "ops", false),
      bodyText: String(raw.bodyText || raw.body_text || raw.message || raw.bodyPreview || "").trim(),
      bodyBlocks,
      bodyModel,
      bodyDocument,
      bodyPreview: String(raw.bodyPreview || raw.body_preview || raw.message || "").trim(),
      isPinned: Boolean(raw.isPinned || raw.is_pinned),
      isImportant: Boolean(raw.isImportant || raw.is_important),
      createdAt: String(raw.createdAt || raw.created_at || raw.publishedAt || raw.published_at || "").trim(),
      updatedAt: String(raw.updatedAt || raw.updated_at || raw.createdAt || raw.created_at || "").trim(),
      publishedAt: String(raw.publishedAt || raw.published_at || raw.createdAt || raw.created_at || "").trim(),
      createdByName: String(raw.createdByName || raw.created_by_name || raw.sender_name || "").trim(),
      senderName: String(raw.senderName || raw.sender_name || raw.createdByName || raw.created_by_name || "").trim(),
      targetMode: String(raw.targetMode || raw.target_mode || "all").trim() || "all",
      targets: Array.isArray(raw.targets) ? raw.targets : [],
      attachments: Array.isArray(raw.attachments) ? raw.attachments : [],
      siteId: String(raw.siteId || raw.site_id || "").trim(),
      location: String(raw.location || raw.siteId || raw.site_id || "본사 공지").trim() || "본사 공지",
      message: String(raw.message || raw.bodyPreview || raw.body_preview || raw.bodyText || raw.body_text || "").trim(),
    };
  }

  function getCompatNoticeRows() {
    return (Array.isArray(rootState.announcements) ? rootState.announcements : []).map((row) => normalizeNoticeRecord(row));
  }

  function seedWorkspaceRowsFromCompat(workspace = ensureWorkspaceState()) {
    if (!workspace || (Array.isArray(workspace.rows) && workspace.rows.length)) {
      return false;
    }
    const compatRows = getCompatNoticeRows();
    if (!compatRows.length) {
      return false;
    }
    workspace.rows = compatRows;
    if (workspace.selectedNoticeId) {
      workspace.selectedRow = compatRows.find((row) => String(row?.id || "").trim() === workspace.selectedNoticeId) || workspace.selectedRow || null;
    }
    return true;
  }

  function buildNoticePreviewShellItem(item = null) {
    if (!item || typeof item !== "object") {
      return null;
    }
    if (usesStructuredNoticeDocumentModel(item.bodyModel) && item.bodyDocument && typeof item.bodyDocument === "object") {
      return item;
    }
    if (Array.isArray(item.bodyBlocks) && item.bodyBlocks.length) {
      return item;
    }
    const previewText = String(item.bodyPreview || item.bodyText || item.message || "").trim();
    if (!previewText) {
      return item;
    }
    return {
      ...item,
      bodyBlocks: [
        {
          kind: "paragraph",
          variant: "body",
          text: previewText,
          align: "left",
        },
      ],
    };
  }

  function getCategoryLabel(category = "all") {
    return SOC_NOTICE_CATEGORY_OPTIONS.find((item) => item.value === normalizeNoticeCategory(category))?.label || "전체";
  }

  function formatDateLabel(value = "", fallback = "-") {
    const text = String(value || "").trim();
    if (!text) {
      return fallback;
    }
    const parsed = new Date(text);
    if (Number.isNaN(parsed.getTime())) {
      return text;
    }
    return new Intl.DateTimeFormat("ko-KR", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(parsed).replace(/\.\s?/g, ".").replace(/\.$/, "");
  }

  function formatDateTimeLabel(value = "", fallback = "-") {
    const text = String(value || "").trim();
    if (!text) {
      return fallback;
    }
    const parsed = new Date(text);
    if (Number.isNaN(parsed.getTime())) {
      return text;
    }
    return new Intl.DateTimeFormat("ko-KR", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(parsed).replace(/\.\s?/g, ".").replace(/\.$/, "");
  }

  function isNoticeFresh(value = "") {
    const parsed = new Date(String(value || "").trim());
    if (Number.isNaN(parsed.getTime())) {
      return false;
    }
    return Date.now() - parsed.getTime() <= SOC_NOTICE_NEW_BADGE_WINDOW_HOURS * 60 * 60 * 1000;
  }

  function createNoticeMetaTags(item = {}) {
    const tags = [];
    if (item.isPinned) {
      tags.push({ tone: "neutral", label: "상단고정" });
    }
    if (isNoticeFresh(item.publishedAt || item.createdAt)) {
      tags.push({ tone: "accent", label: "N" });
    }
    return tags;
  }

  function createEmptyState(title, detail = "") {
    const wrapper = document.createElement("div");
    wrapper.className = "notices-empty-state";
    const strong = document.createElement("strong");
    strong.textContent = title;
    wrapper.appendChild(strong);
    if (detail) {
      const desc = document.createElement("p");
      desc.className = "muted";
      desc.textContent = detail;
      wrapper.appendChild(desc);
    }
    return wrapper;
  }

  function parseParagraphBlocks(bodyBlocks = [], fallbackText = "") {
    const paragraphs = (Array.isArray(bodyBlocks) ? bodyBlocks : [])
      .filter((block) => String(block?.kind || "").trim() === "paragraph")
      .map((block) => String(block?.text || "").trim())
      .filter(Boolean);
    if (paragraphs.length) {
      return paragraphs.join("\n\n");
    }
    return String(fallbackText || "").trim();
  }

  function splitParagraphBody(bodyText = "") {
    const cleaned = String(bodyText || "").replace(/\r\n/g, "\n").trim();
    if (!cleaned) {
      return [];
    }
    return cleaned.split(/\n{2,}/).map((text) => text.trim()).filter(Boolean);
  }

  function normalizeComposeFlowOrder(rawOrder = null, draft = null) {
    const normalized = [];
    (Array.isArray(rawOrder) ? rawOrder : []).forEach((kind) => {
      const value = String(kind || "").trim().toLowerCase();
      if (!SOC_NOTICE_COMPOSE_FLOW_KINDS.includes(value) || normalized.includes(value)) {
        return;
      }
      normalized.push(value);
    });
    if (!normalized.includes("body")) {
      normalized.unshift("body");
    }
    const source = draft && typeof draft === "object" ? draft : {};
    if (source.table?.enabled && !normalized.includes("table")) {
      normalized.push("table");
    }
    if (source.poll?.enabled && !normalized.includes("poll")) {
      normalized.push("poll");
    }
    return normalized.filter((kind) => {
      if (kind === "body") {
        return true;
      }
      if (kind === "table") {
        return Boolean(source.table?.enabled);
      }
      if (kind === "poll") {
        return Boolean(source.poll?.enabled);
      }
      return false;
    });
  }

  function resolveActiveComposeFlowKind() {
    const activeEl = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const blockEl = activeEl?.closest?.("[data-notice-compose-flow-kind]");
    const kind = String(blockEl?.dataset?.noticeComposeFlowKind || "").trim().toLowerCase();
    return SOC_NOTICE_COMPOSE_FLOW_KINDS.includes(kind) ? kind : "body";
  }

  function insertComposeFlowKind(kind = "", draft = null) {
    const normalizedKind = String(kind || "").trim().toLowerCase();
    const source = draft && typeof draft === "object" ? draft : {};
    const order = normalizeComposeFlowOrder(source.flowOrder, source);
    if (!["table", "poll"].includes(normalizedKind) || order.includes(normalizedKind)) {
      return order;
    }
    const anchorKind = resolveActiveComposeFlowKind();
    const nextOrder = order.slice();
    const anchorIndex = nextOrder.indexOf(anchorKind);
    if (anchorIndex >= 0) {
      nextOrder.splice(anchorIndex + 1, 0, normalizedKind);
    } else {
      nextOrder.push(normalizedKind);
    }
    return normalizeComposeFlowOrder(nextOrder, {
      ...source,
      [normalizedKind]: {
        ...(source[normalizedKind] || {}),
        enabled: true,
      },
    });
  }

  function setComposeContentBlocks(nextBlocks = [], { markDirty = false, rerender = false, preserveExistingRich = true } = {}) {
    const workspace = ensureWorkspaceState();
    const composeDraft = workspace.composeDraft && typeof workspace.composeDraft === "object"
      ? workspace.composeDraft
      : createDefaultComposeDraft(workspace.category === "all" ? "ops" : workspace.category);
    const previousBlocks = getComposeContentBlocks(composeDraft);
    let composeContentBlocks = cloneComposeContentBlocks(
      nextBlocks,
      composeDraft.bodyText,
      composeDraft.table,
      composeDraft.poll
    );
    composeContentBlocks = composeContentBlocks.map((block) => {
      const previousBlock = previousBlocks.find((candidate) => String(candidate.id || "").trim() === String(block.id || "").trim());
      if (!preserveExistingRich) {
        return block;
      }
      if (block.kind === "paragraph" && previousBlock?.kind === "paragraph") {
        if (!richTextValueFromRaw(block) && richTextValueFromRaw(previousBlock) && normalizeRichPlainText(previousBlock.text || "") === normalizeRichPlainText(block.text || "")) {
          return {
            ...block,
            richText: richTextValueFromRaw(previousBlock),
            align: normalizeRichAlign(previousBlock.align || block.align || "left"),
          };
        }
        return block;
      }
      if (block.kind === "table" && previousBlock?.kind === "table") {
        const nextTable = cloneTableDraft(block.table);
        const prevTable = cloneTableDraft(previousBlock.table);
        nextTable.columnsRich = nextTable.columnsRich.map((cell, index) => {
          const prevCell = prevTable.columnsRich[index];
          if (!richTextValueFromRaw(cell) && richTextValueFromRaw(prevCell) && normalizeRichPlainText(prevCell?.text || "") === normalizeRichPlainText(cell?.text || "")) {
            return { ...prevCell };
          }
          return cell;
        });
        nextTable.rowsRich = nextTable.rowsRich.map((row, rowIndex) => row.map((cell, colIndex) => {
          const prevCell = prevTable.rowsRich?.[rowIndex]?.[colIndex];
          if (!richTextValueFromRaw(cell) && richTextValueFromRaw(prevCell) && normalizeRichPlainText(prevCell?.text || "") === normalizeRichPlainText(cell?.text || "")) {
            return { ...prevCell };
          }
          return cell;
        }));
        return {
          ...block,
          table: nextTable,
        };
      }
      return block;
    });
    const firstTableBlock = composeContentBlocks.find((block) => block.kind === "table");
    const firstPollBlock = composeContentBlocks.find((block) => block.kind === "poll");
    const flowOrder = normalizeComposeFlowOrder(
      composeContentBlocks.map((block) => (block.kind === "paragraph" ? "body" : block.kind)),
      {
        ...composeDraft,
        table: firstTableBlock ? cloneTableDraft(firstTableBlock.table) : createDefaultTableDraft(),
        poll: firstPollBlock ? clonePollDraft(firstPollBlock.poll) : createDefaultPollDraft(),
      }
    );
    workspace.composeDraft = {
      ...composeDraft,
      bodyText: buildComposeBodyTextFromContentBlocks(composeContentBlocks),
      composeContentBlocks,
      flowOrder,
      table: firstTableBlock ? cloneTableDraft(firstTableBlock.table) : createDefaultTableDraft(),
      poll: firstPollBlock ? clonePollDraft(firstPollBlock.poll) : createDefaultPollDraft(),
    };
    if (markDirty) {
      markComposeDraftDirty();
    }
    if (rerender) {
      renderWorkspace();
    }
  }

  function getComposeTableBlockIndex(blockId = "", draft = null) {
    const blocks = getComposeContentBlocks(draft || ensureWorkspaceState().composeDraft);
    const normalizedId = String(blockId || "").trim();
    if (!normalizedId) {
      return -1;
    }
    return blocks.findIndex((block) => block.kind === "table" && String(block.id || "").trim() === normalizedId);
  }

  function getComposePollBlockIndex(blockId = "", draft = null) {
    const blocks = getComposeContentBlocks(draft || ensureWorkspaceState().composeDraft);
    const normalizedId = String(blockId || "").trim();
    if (!normalizedId) {
      return -1;
    }
    return blocks.findIndex((block) => block.kind === "poll" && String(block.id || "").trim() === normalizedId);
  }

  function updateComposeTableBlock(blockId = "", updater = null, { markDirty = true, rerender = false, preserveExistingRich = true } = {}) {
    const workspace = ensureWorkspaceState();
    const blocks = getComposeContentBlocks(workspace.composeDraft);
    const normalizedId = String(blockId || "").trim();
    const nextBlocks = blocks.map((block) => {
      if (block.kind !== "table" || String(block.id || "").trim() !== normalizedId) {
        return block;
      }
      const nextTable = cloneTableDraft(typeof updater === "function" ? updater(block.table) : block.table);
      nextTable.enabled = true;
      return {
        id: block.id,
        kind: "table",
        table: nextTable,
      };
    });
    setComposeContentBlocks(nextBlocks, { markDirty, rerender, preserveExistingRich });
  }

  function removeComposeTableBlock(blockId = "", { markDirty = true, rerender = true } = {}) {
    const workspace = ensureWorkspaceState();
    const normalizedId = String(blockId || "").trim();
    const nextBlocks = getComposeContentBlocks(workspace.composeDraft)
      .filter((block) => !(block.kind === "table" && String(block.id || "").trim() === normalizedId));
    setComposeContentBlocks(nextBlocks, { markDirty, rerender });
  }

  function updateComposePollBlock(blockId = "", updater = null, { markDirty = true, rerender = true } = {}) {
    const workspace = ensureWorkspaceState();
    const blocks = getComposeContentBlocks(workspace.composeDraft);
    const normalizedId = String(blockId || "").trim();
    const nextBlocks = blocks.map((block) => {
      if (block.kind !== "poll" || String(block.id || "").trim() !== normalizedId) {
        return block;
      }
      const nextPoll = clonePollDraft(typeof updater === "function" ? updater(block.poll) : block.poll);
      nextPoll.enabled = true;
      return {
        id: block.id,
        kind: "poll",
        poll: nextPoll,
      };
    });
    setComposeContentBlocks(nextBlocks, { markDirty, rerender });
  }

  function removeComposePollBlock(blockId = "", { markDirty = true, rerender = true } = {}) {
    const workspace = ensureWorkspaceState();
    const normalizedId = String(blockId || "").trim();
    const nextBlocks = getComposeContentBlocks(workspace.composeDraft)
      .filter((block) => !(block.kind === "poll" && String(block.id || "").trim() === normalizedId));
    setComposeContentBlocks(nextBlocks, { markDirty, rerender });
  }

  function resolveComposeInsertionContext(blocks = []) {
    const activeRichEditor = getActiveRichEditorElement();
    if (activeRichEditor instanceof HTMLElement) {
      const descriptor = getRichEditorDescriptor(activeRichEditor);
      const blockId = String(descriptor?.blockId || "").trim();
      const blockIndex = blocks.findIndex((block) => String(block.id || "").trim() === blockId);
      if (descriptor?.kind === "paragraph" && blockIndex !== -1) {
        const selection = window.getSelection();
        const range = selection?.rangeCount ? selection.getRangeAt(0) : null;
        const offsets = range instanceof Range ? getRichEditorSelectionOffsets(activeRichEditor, range) : null;
        const text = String(blocks[blockIndex]?.text || "");
        return {
          blockId,
          blockIndex,
          selectionStart: offsets ? offsets.start : text.length,
          selectionEnd: offsets ? offsets.end : text.length,
          text,
        };
      }
      if (blockIndex !== -1) {
        return {
          blockId,
          blockIndex,
          selectionStart: null,
          selectionEnd: null,
          text: String(blocks[blockIndex]?.text || ""),
        };
      }
    }
    const activeInput = document.activeElement instanceof HTMLTextAreaElement
      && document.activeElement.dataset.noticeComposeParagraphInput === "true"
      ? document.activeElement
      : null;
    if (activeInput instanceof HTMLTextAreaElement) {
      const blockId = String(activeInput.dataset.noticeComposeBlockId || "").trim();
      const blockIndex = blocks.findIndex((block) => String(block.id || "").trim() === blockId);
      return {
        blockId,
        blockIndex,
        selectionStart: Number.isInteger(activeInput.selectionStart) ? activeInput.selectionStart : String(activeInput.value || "").length,
        selectionEnd: Number.isInteger(activeInput.selectionEnd) ? activeInput.selectionEnd : Number.isInteger(activeInput.selectionStart) ? activeInput.selectionStart : String(activeInput.value || "").length,
        text: String(activeInput.value || ""),
      };
    }
    const storedAnchor = ensureWorkspaceState().composeInsertionAnchor && typeof ensureWorkspaceState().composeInsertionAnchor === "object"
      ? ensureWorkspaceState().composeInsertionAnchor
      : null;
    if (storedAnchor) {
      const blockId = String(storedAnchor.blockId || "").trim();
      const blockIndex = blocks.findIndex((block) => String(block.id || "").trim() === blockId);
      if (blockIndex !== -1 && blocks[blockIndex]?.kind === "paragraph") {
        const text = String(blocks[blockIndex]?.text || "");
        const selectionStart = Math.min(text.length, Math.max(0, Number.parseInt(String(storedAnchor.start || 0), 10) || 0));
        const selectionEnd = Math.min(text.length, Math.max(selectionStart, Number.parseInt(String(storedAnchor.end ?? selectionStart), 10) || selectionStart));
        return {
          blockId,
          blockIndex,
          selectionStart,
          selectionEnd,
          text,
        };
      }
    }
    const activeFlow = document.activeElement instanceof HTMLElement
      ? document.activeElement.closest("[data-notice-compose-flow-index]")
      : null;
    const activeIndex = activeFlow instanceof HTMLElement
      ? Number.parseInt(String(activeFlow.dataset.noticeComposeFlowIndex || "-1"), 10)
      : -1;
    const activeBlock = activeIndex >= 0 ? blocks[activeIndex] : null;
    if (activeBlock) {
      return {
        blockId: String(activeBlock.id || "").trim(),
        blockIndex: activeIndex,
        selectionStart: null,
        selectionEnd: null,
        text: String(activeBlock.text || ""),
      };
    }
    const lastParagraph = [...blocks]
      .map((block, index) => ({ block, index }))
      .reverse()
      .find((entry) => entry.block?.kind === "paragraph");
    if (lastParagraph) {
      const text = String(lastParagraph.block.text || "");
      return {
        blockId: String(lastParagraph.block.id || "").trim(),
        blockIndex: lastParagraph.index,
        selectionStart: text.length,
        selectionEnd: text.length,
        text,
      };
    }
    return {
      blockId: "",
      blockIndex: blocks.length - 1,
      selectionStart: null,
      selectionEnd: null,
      text: "",
    };
  }

  function insertComposeFlowBlock(nextBlock = null) {
    if (!nextBlock || typeof nextBlock !== "object") {
      return "";
    }
    const workspace = ensureWorkspaceState();
    const blocks = getComposeContentBlocks(workspace.composeDraft);
    const insertion = resolveComposeInsertionContext(blocks);
    const currentBlock = insertion.blockIndex >= 0 ? blocks[insertion.blockIndex] : null;
    const nextBlocks = [];
    if (
      currentBlock?.kind === "paragraph"
      && Number.isInteger(insertion.selectionStart)
      && Number.isInteger(insertion.selectionEnd)
    ) {
      const splitPayload = buildParagraphSplitPayload(currentBlock, insertion.selectionStart, insertion.selectionEnd);
      blocks.forEach((block, index) => {
        if (index !== insertion.blockIndex) {
          nextBlocks.push(block);
          return;
        }
        if (splitPayload.before) {
          nextBlocks.push(splitPayload.before);
        }
        nextBlocks.push(nextBlock);
        if (splitPayload.after) {
          nextBlocks.push(splitPayload.after);
        }
        if (!splitPayload.before && !splitPayload.after) {
          nextBlocks.push({
            id: createNoticeBlockId("paragraph"),
            kind: "paragraph",
            text: "",
            richText: "",
            align: normalizeRichAlign(currentBlock.align || "left"),
          });
        }
      });
    } else {
      const insertIndex = insertion.blockIndex >= 0 ? insertion.blockIndex + 1 : blocks.length;
      blocks.forEach((block, index) => {
        if (index === insertIndex) {
          nextBlocks.push(nextBlock);
        }
        nextBlocks.push(block);
      });
      if (insertIndex >= blocks.length) {
        nextBlocks.push(nextBlock);
      }
      if (!nextBlocks.some((block) => block.kind === "paragraph")) {
        nextBlocks.push({
          id: createNoticeBlockId("paragraph"),
          kind: "paragraph",
          text: "",
        });
      }
    }
    setComposeContentBlocks(nextBlocks, { markDirty: true, rerender: true });
    return String(nextBlock.id || "").trim();
  }

  function setComposeInsertionAnchor(nextAnchor = null) {
    const workspace = ensureWorkspaceState();
    if (!nextAnchor || typeof nextAnchor !== "object") {
      workspace.composeInsertionAnchor = null;
      return;
    }
    const blockId = String(nextAnchor.blockId || "").trim();
    if (!blockId) {
      workspace.composeInsertionAnchor = null;
      return;
    }
    const start = Math.max(0, Number.parseInt(String(nextAnchor.start || 0), 10) || 0);
    const end = Math.max(start, Number.parseInt(String(nextAnchor.end ?? start), 10) || start);
    workspace.composeInsertionAnchor = { blockId, start, end };
  }

  function captureComposeInsertionAnchor(input = null) {
    const richTarget = input instanceof HTMLElement && input.dataset.noticeRichEditor === "true"
      ? input
      : (
        document.activeElement instanceof HTMLElement
        && document.activeElement.dataset.noticeRichEditor === "true"
          ? document.activeElement
          : null
      );
    if (richTarget instanceof HTMLElement && String(richTarget.dataset.noticeComposeEditorKind || "").trim() === "paragraph") {
      const selection = window.getSelection();
      const range = selection?.rangeCount ? selection.getRangeAt(0) : null;
      const offsets = range instanceof Range ? getRichEditorSelectionOffsets(richTarget, range) : null;
      const blockId = String(richTarget.dataset.noticeComposeBlockId || "").trim();
      if (!blockId || !offsets) {
        return null;
      }
      setComposeInsertionAnchor({
        blockId,
        start: offsets.start,
        end: offsets.end,
      });
      return ensureWorkspaceState().composeInsertionAnchor;
    }
    const target = input instanceof HTMLTextAreaElement
      && input.dataset.noticeComposeParagraphInput === "true"
      ? input
      : (
        document.activeElement instanceof HTMLTextAreaElement
        && document.activeElement.dataset.noticeComposeParagraphInput === "true"
          ? document.activeElement
          : null
      );
    if (!(target instanceof HTMLTextAreaElement)) {
      return null;
    }
    const blockId = String(target.dataset.noticeComposeBlockId || "").trim();
    if (!blockId) {
      return null;
    }
    setComposeInsertionAnchor({
      blockId,
      start: Number.isInteger(target.selectionStart) ? target.selectionStart : String(target.value || "").length,
      end: Number.isInteger(target.selectionEnd) ? target.selectionEnd : Number.isInteger(target.selectionStart) ? target.selectionStart : String(target.value || "").length,
    });
    return ensureWorkspaceState().composeInsertionAnchor;
  }

  function getComposeParagraphSplitOffsets(rawText = "") {
    const text = String(rawText || "").replace(/\r\n/g, "\n");
    const lines = text.split("\n");
    const offsets = [0];
    let cursor = 0;
    lines.forEach((line, index) => {
      cursor += String(line || "").length;
      if (index < lines.length - 1) {
        offsets.push(cursor);
        cursor += 1;
      }
    });
    offsets.push(text.length);
    return Array.from(new Set(offsets)).sort((a, b) => a - b);
  }

  function resolveComposeParagraphSplitOffsetFromPoint(blockEl = null, clientY = 0) {
    if (!(blockEl instanceof HTMLElement)) {
      return null;
    }
    const input = blockEl.querySelector("[data-notice-compose-paragraph-input=\"true\"]");
    if (!(input instanceof HTMLElement)) {
      return null;
    }
    const blockId = String(input.dataset.noticeComposeBlockId || "").trim();
    const paragraphBlock = getComposeContentBlocks(ensureWorkspaceState().composeDraft)
      .find((block) => block.kind === "paragraph" && String(block.id || "").trim() === blockId);
    const text = String(paragraphBlock?.text || input.innerText || "");
    const offsets = getComposeParagraphSplitOffsets(text);
    const rect = input.getBoundingClientRect();
    const styles = window.getComputedStyle(input);
    const lineHeight = Math.max(18, Number.parseFloat(styles.lineHeight || "28") || 28);
    const paddingTop = Number.parseFloat(styles.paddingTop || "0") || 0;
    const relativeY = Math.max(0, clientY - rect.top - paddingTop);
    const lineIndex = Math.max(0, Math.min(offsets.length - 1, Math.round(relativeY / lineHeight)));
    return offsets[lineIndex] ?? text.length;
  }

  function reorderComposeFlowBlock(blockId = "", targetId = "", placement = "after") {
    const workspace = ensureWorkspaceState();
    const normalizedBlockId = String(blockId || "").trim();
    const normalizedTargetId = String(targetId || "").trim();
    const blocks = getComposeContentBlocks(workspace.composeDraft);
    const fromIndex = blocks.findIndex((block) => String(block.id || "").trim() === normalizedBlockId);
    const targetIndex = blocks.findIndex((block) => String(block.id || "").trim() === normalizedTargetId);
    if (fromIndex === -1 || targetIndex === -1 || fromIndex === targetIndex) {
      return false;
    }
    const nextBlocks = blocks.slice();
    const [movedBlock] = nextBlocks.splice(fromIndex, 1);
    let insertIndex = placement === "before" ? targetIndex : targetIndex + 1;
    if (fromIndex < insertIndex) {
      insertIndex -= 1;
    }
    nextBlocks.splice(insertIndex, 0, movedBlock);
    setComposeContentBlocks(nextBlocks, { markDirty: true, rerender: true });
    return true;
  }

  function moveComposeFlowBlockToParagraphSplit(blockId = "", targetId = "", splitOffset = 0) {
    const workspace = ensureWorkspaceState();
    const normalizedBlockId = String(blockId || "").trim();
    const normalizedTargetId = String(targetId || "").trim();
    const blocks = getComposeContentBlocks(workspace.composeDraft);
    const fromIndex = blocks.findIndex((block) => String(block.id || "").trim() === normalizedBlockId);
    const targetIndex = blocks.findIndex((block) => String(block.id || "").trim() === normalizedTargetId);
    if (fromIndex === -1 || targetIndex === -1 || fromIndex === targetIndex) {
      return false;
    }
    const targetBlock = blocks[targetIndex];
    if (targetBlock?.kind !== "paragraph") {
      return reorderComposeFlowBlock(normalizedBlockId, normalizedTargetId, "after");
    }
    const nextBlocks = blocks.slice();
    const [movedBlock] = nextBlocks.splice(fromIndex, 1);
    const adjustedTargetIndex = nextBlocks.findIndex((block) => String(block.id || "").trim() === normalizedTargetId);
    if (adjustedTargetIndex === -1) {
      return false;
    }
    const adjustedTarget = nextBlocks[adjustedTargetIndex];
    const text = String(adjustedTarget?.text || "");
    const clampedOffset = Math.max(0, Math.min(text.length, Number.parseInt(String(splitOffset || 0), 10) || 0));
    const splitPayload = buildParagraphSplitPayload(adjustedTarget, clampedOffset, clampedOffset);
    const replacement = [];
    if (splitPayload.before) {
      replacement.push(splitPayload.before);
    }
    replacement.push(movedBlock);
    if (splitPayload.after) {
      replacement.push(splitPayload.after);
    }
    if (!replacement.some((block) => block.kind === "paragraph")) {
      replacement.push({
        id: String(adjustedTarget.id || "").trim() || createNoticeBlockId("paragraph"),
        kind: "paragraph",
        text: "",
        richText: "",
        align: normalizeRichAlign(adjustedTarget.align || "left"),
      });
    }
    nextBlocks.splice(adjustedTargetIndex, 1, ...replacement);
    setComposeContentBlocks(nextBlocks, { markDirty: true, rerender: true });
    return true;
  }

  function reorderComposeFlowKind(blockKind = "", targetKind = "", placement = "after") {
    const workspace = ensureWorkspaceState();
    const normalizedBlockKind = String(blockKind || "").trim().toLowerCase();
    const normalizedTargetKind = String(targetKind || "").trim().toLowerCase();
    if (!SOC_NOTICE_COMPOSE_FLOW_KINDS.includes(normalizedBlockKind) || !SOC_NOTICE_COMPOSE_FLOW_KINDS.includes(normalizedTargetKind)) {
      return false;
    }
    if (normalizedBlockKind === normalizedTargetKind) {
      return false;
    }
    const currentDraft = workspace.composeDraft || createDefaultComposeDraft(workspace.category === "all" ? "ops" : workspace.category);
    const order = normalizeComposeFlowOrder(currentDraft.flowOrder, currentDraft);
    const fromIndex = order.indexOf(normalizedBlockKind);
    const targetIndex = order.indexOf(normalizedTargetKind);
    if (fromIndex === -1 || targetIndex === -1) {
      return false;
    }
    const nextOrder = order.slice();
    const [movedKind] = nextOrder.splice(fromIndex, 1);
    let insertIndex = placement === "before" ? targetIndex : targetIndex + 1;
    if (fromIndex < insertIndex) {
      insertIndex -= 1;
    }
    nextOrder.splice(insertIndex, 0, movedKind);
    updateComposeDraft({ flowOrder: normalizeComposeFlowOrder(nextOrder, currentDraft) });
    renderWorkspace();
    return true;
  }

  function clearComposeFlowDropIndicators() {
    document.querySelectorAll(".notices-compose-flow-drop-before, .notices-compose-flow-drop-after, .notices-compose-flow-drop-inline, .is-notice-compose-flow-dragging")
      .forEach((element) => {
        if (!(element instanceof HTMLElement)) {
          return;
        }
        element.classList.remove("notices-compose-flow-drop-before", "notices-compose-flow-drop-after", "notices-compose-flow-drop-inline", "is-notice-compose-flow-dragging");
        element.style.removeProperty("--notice-compose-drop-line-top");
        delete element.dataset.noticeComposeDropSplitOffset;
      });
  }

  function applyComposeFlowDropIndicator(targetEl = null, placement = "after", splitOffset = null) {
    if (!(targetEl instanceof HTMLElement)) {
      return;
    }
    const kind = String(targetEl.dataset.noticeComposeFlowKind || "").trim().toLowerCase();
    if (kind === "paragraph" && Number.isInteger(splitOffset)) {
      const input = targetEl.querySelector("[data-notice-compose-paragraph-input=\"true\"]");
      if (input instanceof HTMLTextAreaElement) {
        const text = String(input.value || "");
        const offsets = getComposeParagraphSplitOffsets(text);
        const splitIndex = Math.max(0, offsets.findIndex((offset) => offset === splitOffset));
        const styles = window.getComputedStyle(input);
        const lineHeight = Math.max(18, Number.parseFloat(styles.lineHeight || "28") || 28);
        const paddingTop = Number.parseFloat(styles.paddingTop || "0") || 0;
        const inputRect = input.getBoundingClientRect();
        const blockRect = targetEl.getBoundingClientRect();
        const lineTop = Math.max(0, Math.min(
          blockRect.height,
          (inputRect.top - blockRect.top) + paddingTop + (splitIndex * lineHeight)
        ));
        targetEl.classList.add("notices-compose-flow-drop-inline");
        targetEl.style.setProperty("--notice-compose-drop-line-top", `${lineTop}px`);
        targetEl.dataset.noticeComposeDropSplitOffset = String(splitOffset);
        return;
      }
    }
    targetEl.classList.add(placement === "before" ? "notices-compose-flow-drop-before" : "notices-compose-flow-drop-after");
  }

  function resolveComposeFlowDropTarget(clientY = 0, draggedBlockId = "") {
    const flowBlocks = Array.from(document.querySelectorAll("#noticesComposeDocumentFlow [data-notice-compose-flow-index]"))
      .filter((element) => element instanceof HTMLElement && !element.classList.contains("hidden"));
    if (!flowBlocks.length) {
      return { targetId: "", placement: "after" };
    }
    let resolved = null;
    flowBlocks.forEach((element) => {
      if (!(element instanceof HTMLElement)) {
        return;
      }
      const blockId = String(element.dataset.noticeComposeBlockId || "").trim();
      if (!blockId || blockId === String(draggedBlockId || "").trim()) {
        return;
      }
      const rect = element.getBoundingClientRect();
      const midpoint = rect.top + (rect.height / 2);
      const placement = clientY <= midpoint ? "before" : "after";
      const distance = Math.abs(clientY - midpoint);
      if (!resolved || distance < resolved.distance) {
        resolved = { targetId: blockId, placement, distance, element };
      }
    });
    if (!resolved) {
      return { targetId: "", placement: "after" };
    }
    return {
      targetId: resolved.targetId,
      placement: resolved.placement,
      element: resolved.element,
      splitOffset: resolved.element instanceof HTMLElement
        && String(resolved.element.dataset.noticeComposeFlowKind || "").trim().toLowerCase() === "paragraph"
        ? resolveComposeParagraphSplitOffsetFromPoint(resolved.element, clientY)
        : null,
    };
  }

  function beginComposeFlowDrag(kind = "", sourceEvent = null, blockId = "") {
    if (!(sourceEvent instanceof MouseEvent) || ensureWorkspaceState().mode !== SOC_NOTICE_VIEW_MODE_COMPOSE) {
      return;
    }
    const normalizedKind = String(kind || "").trim().toLowerCase();
    if (!["table", "poll"].includes(normalizedKind)) {
      return;
    }
    socNoticeComposeDragState = {
      blockId: String(blockId || "").trim(),
      kind: normalizedKind,
      startX: sourceEvent.clientX,
      startY: sourceEvent.clientY,
      didMove: false,
      dropTargetId: "",
      dropPlacement: "after",
      dropSplitOffset: null,
    };
    const draggedBlock = document.querySelector(`[data-notice-compose-block-id="${String(blockId || "").trim()}"]`);
    if (draggedBlock instanceof HTMLElement) {
      draggedBlock.classList.add("is-notice-compose-flow-dragging");
    }
    document.body.classList.add("notices-compose-dragging");
    sourceEvent.preventDefault();
  }

  function handleComposeFlowDragMove(event) {
    if (!(event instanceof MouseEvent) || !socNoticeComposeDragState) {
      return;
    }
    const session = socNoticeComposeDragState;
    const deltaX = Math.abs(event.clientX - session.startX);
    const deltaY = Math.abs(event.clientY - session.startY);
    if (deltaX < 2 && deltaY < 2) {
      return;
    }
    session.didMove = true;
    const dropTarget = resolveComposeFlowDropTarget(event.clientY, session.blockId);
    clearComposeFlowDropIndicators();
    const draggedBlock = document.querySelector(`[data-notice-compose-block-id="${session.blockId}"]`);
    if (draggedBlock instanceof HTMLElement) {
      draggedBlock.classList.add("is-notice-compose-flow-dragging");
    }
    if (dropTarget.targetId) {
      const targetEl = dropTarget.element instanceof HTMLElement
        ? dropTarget.element
        : document.querySelector(`[data-notice-compose-block-id="${dropTarget.targetId}"]`);
      if (targetEl instanceof HTMLElement) {
        applyComposeFlowDropIndicator(targetEl, dropTarget.placement, dropTarget.splitOffset);
      }
      session.dropTargetId = dropTarget.targetId;
      session.dropPlacement = dropTarget.placement;
      session.dropSplitOffset = Number.isInteger(dropTarget.splitOffset) ? dropTarget.splitOffset : null;
    }
  }

  function finishComposeFlowDrag() {
    if (!socNoticeComposeDragState) {
      return;
    }
    const session = socNoticeComposeDragState;
    socNoticeComposeDragState = null;
    document.body.classList.remove("notices-compose-dragging");
    const dropTargetEl = session.dropTargetId
      ? document.querySelector(`[data-notice-compose-block-id="${session.dropTargetId}"]`)
      : null;
    const dropKind = dropTargetEl instanceof HTMLElement
      ? String(dropTargetEl.dataset.noticeComposeFlowKind || "").trim().toLowerCase()
      : "";
    const didReorder = session.dropTargetId
      ? (
        dropKind === "paragraph" && Number.isInteger(session.dropSplitOffset)
          ? moveComposeFlowBlockToParagraphSplit(session.blockId, session.dropTargetId, session.dropSplitOffset)
          : reorderComposeFlowBlock(session.blockId, session.dropTargetId, session.dropPlacement)
      )
      : false;
    clearComposeFlowDropIndicators();
    if (!didReorder && session.didMove) {
      markComposeDraftDirty();
    }
  }

  function normalizeBodyBlocks(bodyBlocks = [], fallbackBodyText = "") {
    const blocks = [];
    (Array.isArray(bodyBlocks) ? bodyBlocks : []).forEach((rawBlock) => {
      if (!rawBlock || typeof rawBlock !== "object") {
        return;
      }
      const kind = String(rawBlock.kind || "").trim().toLowerCase();
      if (kind === "paragraph") {
        const text = String(rawBlock.text || "").trim();
        if (!text) {
          return;
        }
        const normalized = {
          kind: "paragraph",
          variant: String(rawBlock.variant || "").trim().toLowerCase() === "lead" ? "lead" : "body",
          text,
          richText: richTextValueFromRaw(rawBlock),
          align: normalizeRichAlign(rawBlock.align || "left"),
        };
        const title = String(rawBlock.title || "").trim();
        if (title) {
          normalized.title = title;
        }
        blocks.push(normalized);
        return;
      }
      if (kind === "image") {
        const attachmentId = String(rawBlock.attachment_id || rawBlock.attachmentId || "").trim();
        const imageSrc = String(rawBlock.image_src || rawBlock.imageSrc || "").trim();
        if (!attachmentId && !imageSrc) {
          return;
        }
        const normalized = {
          kind: "image",
          attachmentId,
          imageSrc,
        };
        const fileName = String(rawBlock.file_name || rawBlock.fileName || "").trim();
        const caption = String(rawBlock.caption || "").trim();
        if (fileName) {
          normalized.fileName = fileName;
        }
        if (caption) {
          normalized.caption = caption;
        }
        blocks.push(normalized);
        return;
      }
      if (kind === "table") {
        const table = cloneTableDraft({
          enabled: true,
          title: String(rawBlock.title || "").trim(),
          hasHeader: rawBlock.hasHeader ?? rawBlock.has_header ?? true,
          columns: Array.isArray(rawBlock.columns) ? rawBlock.columns : [],
          rows: Array.isArray(rawBlock.rows) ? rawBlock.rows : [],
          columnsRich: Array.isArray(rawBlock.columnsRich || rawBlock.columns_rich) ? (rawBlock.columnsRich || rawBlock.columns_rich) : [],
          rowsRich: Array.isArray(rawBlock.rowsRich || rawBlock.rows_rich) ? (rawBlock.rowsRich || rawBlock.rows_rich) : [],
        });
        const hasTableContent = table.columns.some((item) => String(item || "").trim())
          || table.rows.some((row) => Array.isArray(row) && row.some((cell) => String(cell || "").trim()));
        if (!hasTableContent) {
          return;
        }
        blocks.push({
          kind: "table",
          title: table.title,
          hasHeader: Boolean(table.hasHeader),
          columns: table.columns.slice(),
          rows: table.rows.map((row) => row.slice()),
          columnsRich: table.columnsRich.map((cell) => ({ ...cell })),
          rowsRich: table.rowsRich.map((row) => row.map((cell) => ({ ...cell }))),
        });
        return;
      }
      if (kind === "poll") {
        const poll = clonePollDraft(rawBlock.poll || {});
        const filledOptions = poll.options.filter((item) => String(item.label || "").trim());
        if (!poll.question || filledOptions.length < SOC_NOTICE_MIN_POLL_OPTIONS) {
          return;
        }
        blocks.push({
          kind: "poll",
          poll: {
            pollId: poll.pollId,
            question: poll.question,
            options: filledOptions.map((item, index) => ({
              optionId: item.optionId,
              label: item.label,
              voteCount: Math.max(0, Number(item.voteCount || item.vote_count || 0) || 0),
              voteRatio: Math.max(0, Number(item.voteRatio || item.vote_ratio || 0) || 0),
              selected: Boolean(item.selected),
              index,
            })),
            allowMultiple: Boolean(poll.allowMultiple),
            allowChangeVote: Boolean(poll.allowChangeVote),
            resultVisibility: poll.resultVisibility,
            closesAt: String(poll.closesAt || "").trim(),
            selectedOptionIds: Array.isArray(poll.selectedOptionIds) ? poll.selectedOptionIds.slice() : [],
            totalVotes: Math.max(0, Number(poll.totalVotes || 0) || 0),
            resultsVisible: Boolean(poll.resultsVisible),
            isClosed: Boolean(poll.isClosed),
            canVote: Boolean(poll.canVote),
            hasVoted: Boolean(poll.hasVoted),
          },
        });
      }
    });
    if (blocks.length) {
      return blocks;
    }
    const fallback = String(fallbackBodyText || "").trim();
    if (!fallback) {
      return [];
    }
    return fallback
      .split(/\n{2,}/)
      .map((block) => block.trim())
      .filter(Boolean)
      .map((text) => ({ kind: "paragraph", variant: "body", text }));
  }

  function normalizeDraftFromRow(row = null) {
    const record = normalizeNoticeRecord(row || {});
    if (isFlowLaneNoticeModel(record.bodyModel) && record.bodyDocument) {
      const bodyDocument = normalizeFlowLaneDocumentDraft(record.bodyDocument, record.bodyText || record.bodyPreview || record.message || "", record.bodyBlocks);
      return {
        category: normalizeNoticeCategory(record.category || "ops", false),
        title: record.title,
        bodyText: buildFloatingDocumentBodyText(bodyDocument),
        bodyModel: SOC_NOTICE_BODY_MODEL_FLOW_LANE,
        bodyDocument,
        composeContentBlocks: createDefaultComposeContentBlocks(),
        isPinned: Boolean(record.isPinned),
        imagesEnabled: bodyDocument.objects.some((item) => String(item.kind || "").trim() === "image"),
        images: [],
        table: createDefaultTableDraft(),
        poll: createDefaultPollDraft(),
        flowOrder: ["body"],
      };
    }
    if (isFloatingNoticeModel(record.bodyModel) && record.bodyDocument) {
      const bodyDocument = normalizeFlowLaneDocumentDraft(record.bodyDocument, record.bodyText || record.bodyPreview || record.message || "", record.bodyBlocks);
      return {
        category: normalizeNoticeCategory(record.category || "ops", false),
        title: record.title,
        bodyText: buildFloatingDocumentBodyText(bodyDocument),
        bodyModel: SOC_NOTICE_BODY_MODEL_FLOW_LANE,
        bodyDocument,
        composeContentBlocks: createDefaultComposeContentBlocks(),
        isPinned: Boolean(record.isPinned),
        imagesEnabled: bodyDocument.objects.some((item) => String(item.kind || "").trim() === "image"),
        images: [],
        table: createDefaultTableDraft(),
        poll: createDefaultPollDraft(),
        flowOrder: ["body"],
      };
    }
    const bodyBlocks = normalizeBodyBlocks(record.bodyBlocks, record.bodyText || record.bodyPreview || record.message || "");
    const bodyDocument = normalizeFlowLaneDocumentDraft(null, record.bodyText || record.bodyPreview || record.message || "", bodyBlocks);
    const draft = {
      category: normalizeNoticeCategory(record.category || "ops", false),
      title: record.title,
      bodyText: buildFloatingDocumentBodyText(bodyDocument),
      bodyModel: SOC_NOTICE_BODY_MODEL_FLOW_LANE,
      bodyDocument,
      composeContentBlocks: createDefaultComposeContentBlocks(),
      isPinned: Boolean(record.isPinned),
      imagesEnabled: bodyDocument.objects.some((item) => String(item.kind || "").trim() === "image"),
      images: [],
      table: createDefaultTableDraft(),
      poll: createDefaultPollDraft(),
    };
    draft.flowOrder = ["body"];
    return draft;
  }

  function buildBodyBlocksFromDraft(draft = {}) {
    const blocks = [];
    const composeContentBlocks = getComposeContentBlocks(draft);
    composeContentBlocks.forEach((block) => {
      if (block.kind === "paragraph") {
        const text = String(block.text || "").trim();
        if (text) {
          blocks.push({
            kind: "paragraph",
            variant: String(block.variant || "body").trim().toLowerCase() === "lead" ? "lead" : "body",
            text,
            rich_text: richTextValueFromRaw(block) || undefined,
            richText: richTextValueFromRaw(block) || undefined,
            align: normalizeRichAlign(block.align || "left"),
          });
        }
        return;
      }
      if (block.kind === "table") {
        const table = cloneTableDraft(block.table);
        const rows = Array.isArray(table.rows)
          ? table.rows.map((row) => (Array.isArray(row) ? row.map((cell) => String(cell || "").trim()) : []))
          : [];
        blocks.push({
          kind: "table",
          title: String(table.title || "").trim() || null,
          hasHeader: table.hasHeader !== false,
          columns: Array.isArray(table.columns) ? table.columns.map((item) => String(item || "").trim()) : [],
          rows,
          columns_rich: Array.isArray(table.columnsRich)
            ? table.columnsRich.map((cell) => ({
              text: normalizeRichPlainText(cell?.text || ""),
              rich_text: richTextValueFromRaw(cell) || undefined,
              richText: richTextValueFromRaw(cell) || undefined,
              align: normalizeRichAlign(cell?.align || "left"),
            }))
            : [],
          columnsRich: Array.isArray(table.columnsRich)
            ? table.columnsRich.map((cell) => ({
              text: normalizeRichPlainText(cell?.text || ""),
              rich_text: richTextValueFromRaw(cell) || undefined,
              richText: richTextValueFromRaw(cell) || undefined,
              align: normalizeRichAlign(cell?.align || "left"),
            }))
            : [],
          rows_rich: Array.isArray(table.rowsRich)
            ? table.rowsRich.map((row) => (Array.isArray(row) ? row.map((cell) => ({
              text: normalizeRichPlainText(cell?.text || ""),
              rich_text: richTextValueFromRaw(cell) || undefined,
              richText: richTextValueFromRaw(cell) || undefined,
              align: normalizeRichAlign(cell?.align || "left"),
            })) : []))
            : [],
          rowsRich: Array.isArray(table.rowsRich)
            ? table.rowsRich.map((row) => (Array.isArray(row) ? row.map((cell) => ({
              text: normalizeRichPlainText(cell?.text || ""),
              rich_text: richTextValueFromRaw(cell) || undefined,
              richText: richTextValueFromRaw(cell) || undefined,
              align: normalizeRichAlign(cell?.align || "left"),
            })) : []))
            : [],
        });
        return;
      }
      if (block.kind === "poll") {
        const poll = clonePollDraft(block.poll);
        const options = poll.options
          .map((option) => ({
            optionId: String(option.optionId || "").trim(),
            label: String(option.label || "").trim(),
          }))
          .filter((option) => option.label);
        if (String(poll.question || "").trim() && options.length >= SOC_NOTICE_MIN_POLL_OPTIONS) {
          blocks.push({
            kind: "poll",
            poll: {
              pollId: poll.pollId,
              question: String(poll.question || "").trim(),
              options,
              allowMultiple: Boolean(poll.allowMultiple),
              allowChangeVote: Boolean(poll.allowChangeVote),
              resultVisibility: poll.resultVisibility,
              closesAt: String(poll.closesAt || "").trim(),
            },
          });
        }
      }
    });
    cloneImageDrafts(draft.images).forEach((image) => {
      blocks.push({
        kind: "image",
        attachmentId: image.attachmentId || undefined,
        imageSrc: image.imageSrc,
        fileName: image.fileName,
        caption: image.caption || undefined,
      });
    });
    return blocks;
  }

  function setCompatAnnouncements(rows = []) {
    rootState.announcements = (Array.isArray(rows) ? rows : []).map((row) => {
      const record = normalizeNoticeRecord(row);
      return {
        ...record,
        id: Number(record.id || 0) || record.id,
        created_at: record.createdAt,
        message: record.bodyPreview || record.bodyText || record.message,
        description: record.bodyPreview || record.bodyText || record.message,
        location: record.location || "본사 공지",
        is_deleted: false,
      };
    });
    if (typeof renderIncidents === "function") {
      renderIncidents();
    }
  }

  async function fetchNoticeRows(stateValue) {
    const query = new URLSearchParams();
    if (stateValue.category !== "all") {
      query.set("category", stateValue.category);
    }
    if (stateValue.search) {
      query.set("q", stateValue.search);
    }
    query.set("limit", "80");
    const payload = await apiRequest(`/api/announcements?${query.toString()}`);
    const rows = Array.isArray(payload?.items)
      ? payload.items
      : (Array.isArray(payload?.rows) ? payload.rows : (Array.isArray(payload?.announcements) ? payload.announcements : []));
    return rows.map((row) => {
      const normalized = normalizeNoticeRecord(row);
      normalized.bodyModel = normalizeNoticeBodyModel(row?.bodyModel || row?.body_model || normalized.bodyModel || "");
      normalized.bodyDocument = row?.bodyDocument && typeof row.bodyDocument === "object"
        ? row.bodyDocument
        : (row?.body_document && typeof row.body_document === "object" ? row.body_document : normalized.bodyDocument || null);
      return normalized;
    });
  }

  async function fetchNoticeDetailRow(noticeId = "") {
    const targetId = String(noticeId || "").trim();
    if (!targetId) {
      return null;
    }
    const payload = await apiRequest(`/api/announcements/${encodeURIComponent(targetId)}`);
    const record = payload?.notice || payload?.announcement || payload || {};
    const normalized = normalizeNoticeRecord(record);
    normalized.bodyModel = normalizeNoticeBodyModel(record?.bodyModel || record?.body_model || normalized.bodyModel || "");
    normalized.bodyDocument = record?.bodyDocument && typeof record.bodyDocument === "object"
      ? record.bodyDocument
      : (record?.body_document && typeof record.body_document === "object" ? record.body_document : normalized.bodyDocument || null);
    return normalized;
  }

  async function submitNoticePollVote(noticeId = "", pollId = "", optionIds = []) {
    const payload = await apiRequest(`/api/announcements/${encodeURIComponent(String(noticeId || "").trim())}/polls/${encodeURIComponent(String(pollId || "").trim())}/vote`, {
      method: "POST",
      body: JSON.stringify({
        option_ids: Array.isArray(optionIds) ? optionIds : [],
      }),
    });
    return normalizeNoticeRecord(payload?.notice || payload?.announcement || payload || {});
  }

  async function saveNoticeDraft() {
    const workspace = ensureWorkspaceState();
    if (usesStructuredNoticeDocumentModel(workspace.composeDraft?.bodyModel)) {
      syncFloatingComposeDraftFromDom({ markDirty: false });
    }
    const draft = workspace.composeDraft || createDefaultComposeDraft(workspace.category || "ops");
    const title = String(draft.title || "").trim();
    const isStructured = usesStructuredNoticeDocumentModel(draft.bodyModel);
    const bodyDocument = isStructured
      ? (isFlowLaneNoticeModel(draft.bodyModel)
        ? normalizeFlowLaneDocumentDraft(draft.bodyDocument, draft.bodyText || "")
        : normalizeFloatingDocumentDraft(draft.bodyDocument, draft.bodyText || ""))
      : null;
    const bodyBlocks = isStructured ? [] : buildBodyBlocksFromDraft(draft);
    const bodyText = isStructured ? buildFloatingDocumentBodyText(bodyDocument) : buildComposeBodyTextFromContentBlocks(draft.composeContentBlocks);
    const editingNoticeId = String(workspace.composeEditingId || workspace.selectedNoticeId || "").trim();
    if (!title) {
      throw new Error("공지 제목을 입력해 주세요.");
    }
    if (!bodyBlocks.length && !bodyText && !(isStructured && bodyDocument?.objects?.length)) {
      throw new Error("공지 본문을 입력해 주세요.");
    }
    const payload = {
      category: normalizeNoticeCategory(draft.category || "ops", false),
      title,
      body_text: bodyText,
      body_blocks: bodyBlocks,
      is_pinned: Boolean(draft.isPinned),
    };
    if (isStructured && bodyDocument) {
      payload.body_model = isFlowLaneNoticeModel(draft.bodyModel)
        ? SOC_NOTICE_BODY_MODEL_FLOW_LANE
        : SOC_NOTICE_BODY_MODEL_FLOATING;
      payload.body_document = bodyDocument;
    }
    const response = await apiRequest(editingNoticeId ? `/api/announcements/${encodeURIComponent(editingNoticeId)}` : "/api/announcements", {
      method: editingNoticeId ? "PATCH" : "POST",
      body: JSON.stringify(payload),
    });
    return normalizeNoticeRecord(response?.notice || response?.announcement || response || {});
  }

  async function deleteNoticeRecord(noticeId = "") {
    const targetId = String(noticeId || "").trim();
    if (!targetId) {
      return null;
    }
    return apiRequest(`/api/announcements/${encodeURIComponent(targetId)}`, {
      method: "DELETE",
    });
  }

  function getWorkspaceElements() {
    return {
      panel: document.getElementById("announcementPanel"),
      readonlyPill: document.getElementById("noticesReadonlyPill"),
      createBtn: document.getElementById("noticesCreateBtn"),
      subtitle: document.getElementById("noticesViewSubtitle"),
      categoryTabs: document.getElementById("noticesCategoryTabs"),
      searchForm: document.getElementById("noticesSearchForm"),
      searchInputWrap: document.getElementById("noticesSearchInputWrap"),
      searchInput: document.getElementById("noticesSearchInput"),
      searchToggleBtn: document.getElementById("noticesSearchToggleBtn"),
      searchIcon: document.getElementById("noticesSearchIconSearch"),
      clearIcon: document.getElementById("noticesSearchIconClear"),
      listPanel: document.getElementById("noticesListPanel"),
      list: document.getElementById("noticesList"),
      detailPanel: document.getElementById("noticesDetailPanel"),
      detailTitle: document.getElementById("noticesDetailTitle"),
      detailMeta: document.getElementById("noticesDetailMeta"),
      detailBody: document.getElementById("noticesDetailBody"),
      detailEditBtn: document.getElementById("noticesDetailEditBtn"),
      detailDeleteBtn: document.getElementById("noticesDetailDeleteBtn"),
      composePanel: document.getElementById("noticesComposePanel"),
      composeCategory: document.getElementById("noticesComposeCategory"),
      composePinnedToggle: document.getElementById("noticesComposePinnedToggle"),
      composeTitle: document.getElementById("noticesComposeTitle"),
      composeTablePicker: document.getElementById("noticesComposeTablePicker"),
      composeTablePickerGrid: document.getElementById("noticesComposeTablePickerGrid"),
      composeTablePickerLabel: document.getElementById("noticesComposeTablePickerLabel"),
      composeDocumentFlow: document.getElementById("noticesComposeDocumentFlow"),
      composeImageBlock: document.getElementById("noticesComposeImageBlock"),
      composeImageInput: document.getElementById("noticesComposeImageInput"),
      composeImageDropzone: document.getElementById("noticesComposeImageDropzone"),
      composeImageList: document.getElementById("noticesComposeImageList"),
      composeDraftMeta: document.getElementById("noticesComposeDraftMeta"),
      composeFontSizeInput: document.getElementById("noticesComposeFontSizeInput"),
      composeFontSizeToggleBtn: document.getElementById("noticesComposeFontSizeToggleBtn"),
      composeFontSizeMenu: document.getElementById("noticesComposeFontSizeMenu"),
      composeTextColorBtn: document.getElementById("noticesComposeTextColorBtn"),
      composeTextColorPalette: document.getElementById("noticesComposeTextColorPalette"),
      composeHighlightBtn: document.getElementById("noticesComposeHighlightBtn"),
      composeHighlightPalette: document.getElementById("noticesComposeHighlightPalette"),
      publishBtn: document.getElementById("noticesPublishBtn"),
      pollModalBackdrop: document.getElementById("noticesPollModalBackdrop"),
      pollModal: document.getElementById("noticesPollModal"),
      pollModalQuestion: document.getElementById("noticesComposePollModalQuestion"),
      pollModalVisibility: document.getElementById("noticesComposePollModalVisibility"),
      pollModalClosesAt: document.getElementById("noticesComposePollModalClosesAt"),
      pollModalAllowChangeToggle: document.getElementById("noticesComposePollModalAllowChangeToggle"),
      pollModalOptionList: document.getElementById("noticesComposePollModalOptionList"),
      pollModalAddOptionBtn: document.getElementById("noticesComposePollModalAddOptionBtn"),
      linkModalBackdrop: document.getElementById("noticesLinkModalBackdrop"),
      linkModal: document.getElementById("noticesLinkModal"),
      linkModalUrl: document.getElementById("noticesComposeLinkUrl"),
      linkModalRemoveBtn: document.getElementById("noticesLinkRemoveBtn"),
    };
  }

  function renderCategoryTabs(elements, workspace) {
    if (!(elements.categoryTabs instanceof HTMLElement)) {
      return;
    }
    elements.categoryTabs.innerHTML = "";
    SOC_NOTICE_CATEGORY_OPTIONS.forEach((item) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `workspace-tab${workspace.category === item.value ? " active" : ""}`;
      button.dataset.action = "notices-set-category";
      button.dataset.category = item.value;
      button.textContent = item.label;
      elements.categoryTabs.appendChild(button);
    });
  }

  function renderSearchControls(elements, workspace) {
    const hasValue = Boolean(String(workspace.searchDraft || "").trim());
    const expanded = Boolean(workspace.searchExpanded || workspace.search || hasValue);
    workspace.searchExpanded = expanded;
    if (elements.searchForm instanceof HTMLElement) {
      elements.searchForm.classList.toggle("is-expanded", expanded);
      elements.searchForm.classList.toggle("has-value", hasValue);
    }
    if (elements.searchInputWrap instanceof HTMLElement) {
      elements.searchInputWrap.setAttribute("aria-hidden", expanded ? "false" : "true");
    }
    if (elements.searchInput instanceof HTMLInputElement) {
      if (elements.searchInput.value !== workspace.searchDraft) {
        elements.searchInput.value = workspace.searchDraft;
      }
      if (!expanded && document.activeElement === elements.searchInput) {
        elements.searchInput.blur();
      }
    }
    if (elements.searchToggleBtn instanceof HTMLElement) {
      elements.searchToggleBtn.setAttribute("aria-label", hasValue ? "검색어 지우기" : (expanded ? "검색 닫기" : "검색 열기"));
    }
    if (elements.searchIcon instanceof HTMLElement) {
      elements.searchIcon.classList.toggle("hidden", hasValue);
    }
    if (elements.clearIcon instanceof HTMLElement) {
      elements.clearIcon.classList.toggle("hidden", !hasValue);
    }
  }

  function createNoticeListRow(item = {}) {
    const li = document.createElement("li");
    li.className = "notices-list-item";

    const button = document.createElement("button");
    button.type = "button";
    button.className = "notices-list-button";
    button.dataset.action = "notices-open-detail";
    button.dataset.noticeId = String(item.id || "").trim();
    button.dataset.category = normalizeNoticeCategory(item.category || "all");

    const categoryEl = document.createElement("span");
    categoryEl.className = "notices-list-category";
    categoryEl.textContent = getCategoryLabel(item.category || "all");

    const main = document.createElement("div");
    main.className = "notices-list-main";

    const titleRow = document.createElement("div");
    titleRow.className = "notices-list-title-row";

    const titleEl = document.createElement("strong");
    titleEl.className = "notices-list-title";
    titleEl.textContent = String(item.title || "-").trim() || "-";
    titleRow.appendChild(titleEl);

    createNoticeMetaTags(item).forEach((tag) => {
      const tagEl = document.createElement("span");
      tagEl.className = `notice-meta-tag notice-meta-tag-${tag.tone}`;
      tagEl.textContent = tag.label;
      titleRow.appendChild(tagEl);
    });
    main.appendChild(titleRow);

    const dateEl = document.createElement("time");
    dateEl.className = "notices-list-date";
    dateEl.dateTime = String(item.publishedAt || item.createdAt || "").trim();
    dateEl.textContent = formatDateLabel(item.publishedAt || item.createdAt || "", "-");

    button.append(categoryEl, main, dateEl);
    li.appendChild(button);
    return li;
  }

  function renderListPanel(elements, workspace) {
    if (!(elements.list instanceof HTMLElement)) {
      return;
    }
    elements.list.innerHTML = "";
    if (workspace.loading && !workspace.rows.length) {
      if (typeof renderSkeleton === "function") {
        renderSkeleton(elements.list, 4);
      } else {
        elements.list.appendChild(createEmptyState("공지 목록을 불러오는 중입니다.", "잠시만 기다려 주세요."));
      }
      return;
    }
    if (!workspace.rows.length) {
      const title = workspace.error
        ? "공지 목록을 다시 불러오지 못했습니다."
        : (workspace.search
          ? "검색 조건에 맞는 공지가 없습니다."
          : (canManageSocNotices()
            ? "첫 공지를 등록하면 홈 상단 티저와 공지 목록에 바로 반영됩니다."
            : "새 공지가 등록되면 카테고리, 제목, 날짜 형식으로 이 목록에서 확인할 수 있습니다."));
      const detail = workspace.error
        ? workspace.error
        : (workspace.search
          ? "카테고리를 바꾸거나 검색어를 지우고 다시 확인해 주세요."
          : (canManageSocNotices()
            ? `상단고정은 최대 ${SOC_NOTICE_PINNED_LIMIT}개까지 유지됩니다.`
            : `최근 ${Math.round(SOC_NOTICE_NEW_BADGE_WINDOW_HOURS / 24)}일 이내 공지는 새 배지로 구분됩니다.`));
      elements.list.appendChild(createEmptyState(title, detail));
      return;
    }
    workspace.rows.forEach((row) => {
      elements.list.appendChild(createNoticeListRow(row));
    });
  }

  function buildPollMetaTags(poll = {}) {
    const tags = [];
    if (String(poll.resultVisibility || poll.result_visibility || "always").trim().toLowerCase() === "after_close") {
      tags.push({ tone: "neutral", label: "마감 후 공개" });
    }
    const closesAt = String(poll.closesAt || poll.closes_at || "").trim();
    if (closesAt) {
      tags.push({
        tone: Boolean(poll.isClosed || poll.is_closed) ? "neutral" : "accent",
        label: `${Boolean(poll.isClosed || poll.is_closed) ? "마감" : "마감 예정"} ${formatDateTimeLabel(closesAt, closesAt)}`,
      });
    }
    return tags;
  }

  function createPollBlock(item = {}, poll = {}, options = {}) {
    const previewOnly = Boolean(options.previewOnly);
    const forceResultsVisible = Boolean(options.forceResultsVisible);
    const showResults = forceResultsVisible || Boolean(poll.resultsVisible || poll.results_visible);
    const totalVotes = Math.max(0, Number(poll.totalVotes || poll.total_votes || 0) || 0);
    const section = document.createElement("section");
    section.className = "notices-detail-block notices-detail-poll-block";
    const card = document.createElement("div");
    card.className = "notices-poll-card";
    card.dataset.noticePollId = String(poll.pollId || poll.poll_id || "").trim();

    const head = document.createElement("div");
    head.className = "notices-poll-head";
    const titleWrap = document.createElement("div");
    titleWrap.className = "notices-poll-title-wrap";
    const title = document.createElement("h4");
    title.className = "notices-detail-block-title";
    title.textContent = String(poll.question || "").trim() || "공지 투표";
    titleWrap.appendChild(title);
    head.appendChild(titleWrap);

    const meta = document.createElement("div");
    meta.className = "notices-poll-meta";
    buildPollMetaTags(poll).forEach((tag) => {
      const tagEl = document.createElement("span");
      tagEl.className = `notice-meta-tag notice-meta-tag-${tag.tone}`;
      tagEl.textContent = tag.label;
      meta.appendChild(tagEl);
    });
    if (meta.childNodes.length) {
      head.appendChild(meta);
    }
    card.appendChild(head);

    const summaryRow = document.createElement("div");
    summaryRow.className = "notices-poll-status-row";
    const summary = document.createElement("p");
    summary.className = "notices-poll-summary";
    summary.textContent = `참여 ${totalVotes}명`;
    summaryRow.appendChild(summary);
    if (!previewOnly && (poll.hasVoted || poll.has_voted)) {
      const statePill = document.createElement("span");
      statePill.className = "status-pill notices-poll-complete-pill";
      statePill.textContent = "참여 완료";
      summaryRow.appendChild(statePill);
    }
    card.appendChild(summaryRow);

    const optionsWrap = document.createElement("div");
    optionsWrap.className = "notices-poll-options";
    const inputType = Boolean(poll.allowMultiple || poll.allow_multiple) ? "checkbox" : "radio";
    const selectedOptionIds = Array.isArray(poll.selectedOptionIds || poll.selected_option_ids)
      ? (poll.selectedOptionIds || poll.selected_option_ids).map((value) => String(value || "").trim()).filter(Boolean)
      : [];
    (Array.isArray(poll.options) ? poll.options : []).forEach((option, index) => {
      const optionId = String(option.optionId || option.option_id || "").trim() || (previewOnly ? `preview-option-${index + 1}` : "");
      if (!optionId) {
        return;
      }
      const row = document.createElement("label");
      row.className = "notices-poll-option";

      const input = document.createElement("input");
      input.type = inputType;
      input.name = `notice-poll-${String(poll.pollId || poll.poll_id || "").trim() || "poll"}`;
      input.value = optionId;
      input.checked = selectedOptionIds.includes(optionId);
      input.disabled = Boolean(poll.isClosed || poll.is_closed) || (!Boolean(poll.canVote || poll.can_vote) && !input.checked) || previewOnly;
      input.dataset.noticePollOptionId = optionId;
      input.dataset.noticePollId = String(poll.pollId || poll.poll_id || "").trim();
      row.appendChild(input);

      const content = document.createElement("div");
      content.className = "notices-poll-option-content";
      const labelRow = document.createElement("div");
      labelRow.className = "notices-poll-option-label-row";
      const labelEl = document.createElement("strong");
      labelEl.className = "notices-poll-option-label";
      labelEl.textContent = String(option.label || `선택지 ${index + 1}`).trim();
      labelRow.appendChild(labelEl);
      const countEl = document.createElement("span");
      countEl.className = "notices-poll-option-votes";
      const ratio = Math.max(0, Math.min(1, Number(option.voteRatio || option.vote_ratio || 0) || 0));
      countEl.textContent = showResults
        ? `${Math.round(ratio * 100)}%`
        : (input.checked ? "내 선택" : "");
      labelRow.appendChild(countEl);
      content.appendChild(labelRow);
      const resultBar = document.createElement("div");
      resultBar.className = "notices-poll-result-bar";
      const fill = document.createElement("span");
      fill.className = "notices-poll-result-fill";
      fill.style.width = `${Math.round(ratio * 100)}%`;
      resultBar.appendChild(fill);
      content.appendChild(resultBar);
      row.appendChild(content);
      optionsWrap.appendChild(row);
    });
    card.appendChild(optionsWrap);

    const actionRow = document.createElement("div");
    actionRow.className = "notices-poll-actions";
    const pollId = String(poll.pollId || poll.poll_id || "").trim();
    if (!previewOnly && Boolean(poll.canVote || poll.can_vote) && pollId && String(item?.id || "").trim()) {
      const submitBtn = document.createElement("button");
      submitBtn.type = "button";
      submitBtn.className = "btn btn-primary";
      submitBtn.dataset.action = "notices-poll-submit";
      submitBtn.dataset.noticeId = String(item.id || "").trim();
      submitBtn.dataset.noticePollId = pollId;
      submitBtn.disabled = ensureWorkspaceState().pollSubmittingId === pollId;
      submitBtn.textContent = ensureWorkspaceState().pollSubmittingId === pollId
        ? "제출 중..."
        : ((poll.hasVoted || poll.has_voted) && (poll.allowChangeVote || poll.allow_change_vote) ? "다시 투표" : "투표하기");
      actionRow.appendChild(submitBtn);
    }
    let hintText = "";
    if ((poll.hasVoted || poll.has_voted) && (poll.allowChangeVote || poll.allow_change_vote) && !(poll.isClosed || poll.is_closed)) {
      hintText = "마감 전까지 다시 제출하면 선택을 변경할 수 있습니다.";
    } else if (poll.isClosed || poll.is_closed) {
      hintText = "마감된 투표입니다.";
    } else if (!(poll.resultsVisible || poll.results_visible)) {
      hintText = "결과는 마감 후 공개됩니다.";
    }
    if (!previewOnly && hintText) {
      const hint = document.createElement("p");
      hint.className = "muted notices-poll-hint";
      hint.textContent = hintText;
      actionRow.appendChild(hint);
    }
    if (actionRow.childNodes.length) {
      card.appendChild(actionRow);
    }

    section.appendChild(card);
    return section;
  }

  function renderRichFragment(target, richText = "", fallbackText = "", align = "left") {
    if (!(target instanceof HTMLElement)) {
      return;
    }
    target.classList.add("notices-rich-content");
    target.innerHTML = String(richText || "").trim() || plainTextToRichHtml(fallbackText) || "";
    target.style.textAlign = normalizeRichAlign(align);
    setRichEditorPresentation(target, align);
  }

  function getFloatingDocumentItems(documentValue = null) {
    if (!documentValue || typeof documentValue !== "object") {
      return [];
    }
    const items = [];
    (Array.isArray(documentValue.paragraphs) ? documentValue.paragraphs : []).forEach((paragraph) => {
      items.push({
        itemType: "paragraph",
        flowIndex: Math.max(0, Number(paragraph?.flow_index ?? paragraph?.flowIndex ?? 0) || 0),
        value: paragraph,
      });
    });
    (Array.isArray(documentValue.objects) ? documentValue.objects : []).forEach((obj) => {
      items.push({
        itemType: "object",
        flowIndex: Math.max(0, Number(obj?.flow_index ?? obj?.flowIndex ?? 0) || 0),
        value: obj,
      });
    });
    items.sort((a, b) => a.flowIndex - b.flowIndex);
    return items;
  }

  function createFloatingSceneRoot(documentValue = null, options = {}) {
    const detail = Boolean(options.detail);
    const editable = Boolean(options.editable);
    const scene = document.createElement("div");
    scene.className = `notices-floating-scene${detail ? " notices-detail-floating-scene" : " notices-compose-floating-scene"}`;
    scene.dataset.noticeFloatingScene = "true";
    scene.dataset.noticeBodyModel = SOC_NOTICE_BODY_MODEL_FLOATING;
    if (editable) {
      scene.dataset.noticeComposeScene = "true";
      scene.dataset.noticeComposeModel = SOC_NOTICE_BODY_MODEL_FLOATING;
    } else {
      scene.dataset.noticeDetailModel = SOC_NOTICE_BODY_MODEL_FLOATING;
    }
    const canvas = documentValue?.canvas && typeof documentValue.canvas === "object" ? documentValue.canvas : {};
    const canvasWidth = Math.max(320, Number(canvas.width || SOC_NOTICE_FLOATING_CANVAS_WIDTH) || SOC_NOTICE_FLOATING_CANVAS_WIDTH);
    const minHeight = Math.max(320, Number(canvas.minHeight || canvas.min_height || SOC_NOTICE_FLOATING_CANVAS_MIN_HEIGHT) || SOC_NOTICE_FLOATING_CANVAS_MIN_HEIGHT);
    scene.style.setProperty("--notices-scene-width", `${canvasWidth}px`);
    scene.style.setProperty("--notices-scene-min-height", `${minHeight}px`);
    return scene;
  }

  function createFloatingSceneObjectElement(item = {}, context = {}) {
    const kind = String(item?.kind || "").trim().toLowerCase();
    const editable = Boolean(context.editable);
    const wrapper = document.createElement("div");
    wrapper.className = `notices-floating-object notices-floating-object-${kind}`;
    wrapper.dataset.noticeSceneObjectId = String(item?.id || "");
    wrapper.dataset.noticeComposeSceneObjectId = String(item?.id || "");
    wrapper.dataset.noticeFloatingObjectId = String(item?.id || "");
    wrapper.dataset.noticeFlowIndex = String(item?.flow_index ?? item?.flowIndex ?? 0);
    wrapper.dataset.noticeFrameX = String(item?.frame?.x ?? "");
    wrapper.dataset.noticeFrameY = String(item?.frame?.y ?? "");
    wrapper.dataset.noticeFrameWidth = String(item?.frame?.width ?? "");
    wrapper.dataset.noticeFrameHeight = String(item?.frame?.height ?? "");
    wrapper.style.left = `${Number(item?.frame?.x || 0) || 0}px`;
    wrapper.style.top = `${Number(item?.frame?.y || 0) || 0}px`;
    wrapper.style.width = `${Math.max(1, Number(item?.frame?.width || 1) || 1)}px`;
    wrapper.style.minHeight = `${Math.max(1, Number(item?.frame?.height || 1) || 1)}px`;
    wrapper.style.zIndex = String(Math.max(0, Number(item?.z_index ?? item?.zIndex ?? 0) || 0));

    const chrome = document.createElement("div");
    chrome.className = "notices-floating-object-chrome";
    if (editable) {
      const handle = document.createElement("button");
      handle.type = "button";
      handle.className = "notices-floating-object-handle";
      handle.dataset.noticeSceneDragHandle = String(item?.id || "");
      handle.setAttribute("aria-label", `${kind} 이동`);
      chrome.appendChild(handle);

      if (kind === "poll") {
        const editBtn = document.createElement("button");
        editBtn.type = "button";
        editBtn.className = "notices-floating-object-edit";
        editBtn.dataset.action = "notices-edit-poll-block";
        editBtn.dataset.noticePollBlockId = String(item?.id || "");
        editBtn.setAttribute("aria-label", "투표 편집");
        chrome.appendChild(editBtn);
      }

      const removeBtn = document.createElement("button");
      removeBtn.type = "button";
      removeBtn.className = "notices-floating-object-remove";
      removeBtn.dataset.action = kind === "image"
        ? "notices-image-remove-floating"
        : (kind === "table" ? "notices-remove-table-block" : "notices-remove-poll-block");
      removeBtn.dataset.noticeFloatingObjectId = String(item?.id || "");
      removeBtn.dataset.noticeTableBlockId = String(item?.id || "");
      removeBtn.dataset.noticePollBlockId = String(item?.id || "");
      removeBtn.dataset.noticeImageObjectId = String(item?.id || "");
      removeBtn.setAttribute("aria-label", `${kind} 삭제`);
      chrome.appendChild(removeBtn);
    }
    wrapper.appendChild(chrome);

    if (kind === "image") {
      if (editable) {
        wrapper.dataset.noticeSceneDragBody = String(item?.id || "");
      }
      const img = document.createElement("img");
      img.className = "notices-floating-object-image";
      img.loading = "lazy";
      img.draggable = false;
      img.alt = String(item?.caption || item?.fileName || item?.file_name || "공지 이미지").trim() || "공지 이미지";
      img.src = resolveNoticeImageUrl(item?.imageSrc || item?.image_src || "");
      if (editable) {
        img.dataset.noticeSceneDragBody = String(item?.id || "");
      }
      wrapper.appendChild(img);
      if (editable) {
        const resize = document.createElement("button");
        resize.type = "button";
        resize.className = "notices-floating-object-resize";
        resize.dataset.noticeSceneResizeHandle = String(item?.id || "");
        resize.setAttribute("aria-label", "이미지 크기 조절");
        wrapper.appendChild(resize);
      }
      return wrapper;
    }

    if (kind === "table") {
      const tablePayload = cloneTableDraft(item?.table || {});
      if (editable) {
        wrapper.appendChild(buildTableGridElement(tablePayload, String(item?.id || "")));
      } else {
        const section = document.createElement("section");
        section.className = "notices-detail-block";
        const tableWrap = document.createElement("div");
        tableWrap.className = "notices-detail-table-wrap";
        const table = document.createElement("table");
        table.className = "notices-detail-table";
        const totalTableWidth = (Array.isArray(tablePayload.columnWidths) ? tablePayload.columnWidths : []).reduce((sum, value) => sum + (Number(value || 0) || 0), 0);
        if (totalTableWidth > 0) {
          table.style.width = `${totalTableWidth}px`;
        }
        const columns = Array.isArray(tablePayload.columns) ? tablePayload.columns : [];
        const columnsRich = Array.isArray(tablePayload.columnsRich) ? tablePayload.columnsRich : [];
        const colgroup = document.createElement("colgroup");
        columns.forEach((_, index) => {
          const col = document.createElement("col");
          const width = Math.max(72, Number(tablePayload.columnWidths?.[index] || 160) || 160);
          col.style.width = `${width}px`;
          colgroup.appendChild(col);
        });
        table.appendChild(colgroup);
        if (tablePayload.hasHeader && columns.length) {
          const thead = document.createElement("thead");
          const row = document.createElement("tr");
          row.style.height = `${Math.max(36, Number(tablePayload.rowHeights?.[0] || 44) || 44)}px`;
          columns.forEach((column, index) => {
            const th = document.createElement("th");
            renderRichFragment(th, richTextValueFromRaw(columnsRich[index] || {}), String(column || "").trim(), normalizeRichAlign(columnsRich[index]?.align || "left"));
            row.appendChild(th);
          });
          thead.appendChild(row);
          table.appendChild(thead);
        }
        const tbody = document.createElement("tbody");
        if (!tablePayload.hasHeader && columns.length) {
          const row = document.createElement("tr");
          columns.forEach((column, index) => {
            const td = document.createElement("td");
            renderRichFragment(td, richTextValueFromRaw(columnsRich[index] || {}), String(column || "").trim(), normalizeRichAlign(columnsRich[index]?.align || "left"));
            row.appendChild(td);
          });
          tbody.appendChild(row);
        }
        (tablePayload.rows || []).forEach((rowValue, rowIndex) => {
          const row = document.createElement("tr");
          (rowValue || []).forEach((cell, colIndex) => {
            const td = document.createElement("td");
            renderRichFragment(td, richTextValueFromRaw(tablePayload.rowsRich?.[rowIndex]?.[colIndex] || {}), String(cell || "").trim(), normalizeRichAlign(tablePayload.rowsRich?.[rowIndex]?.[colIndex]?.align || "left"));
            row.appendChild(td);
          });
          tbody.appendChild(row);
        });
        table.appendChild(tbody);
        tableWrap.appendChild(table);
        section.appendChild(tableWrap);
        wrapper.appendChild(section);
      }
      return wrapper;
    }

    if (kind === "poll") {
      const pollPayload = clonePollDraft(item?.poll || {});
      wrapper.appendChild(createPollBlock(context.noticeItem || null, pollPayload, { previewOnly: editable, forceResultsVisible: true }));
      return wrapper;
    }
    return wrapper;
  }

  function renderFloatingScene(target, documentValue, options = {}) {
    if (!(target instanceof HTMLElement)) {
      return;
    }
    target.innerHTML = "";
    const detail = Boolean(options.detail);
    const editable = Boolean(options.editable);
    const scene = createFloatingSceneRoot(documentValue, { detail, editable });
    const flow = document.createElement("div");
    flow.className = `notices-floating-scene-flow${editable ? " notices-compose-scene-flow" : " notices-detail-scene-flow"}`;
    const items = getFloatingDocumentItems(documentValue);
    items.forEach((entry) => {
      if (entry.itemType !== "paragraph") {
        return;
      }
      const paragraph = entry.value;
      if (editable) {
        const section = document.createElement("section");
        section.className = "notices-compose-inline-block notices-compose-text-block notices-floating-scene-paragraph";
        section.dataset.noticeComposeFlowKind = "paragraph";
        section.dataset.noticeComposeBlockId = String(paragraph.id || "");
        section.dataset.noticeFlowIndex = String(paragraph.flow_index ?? paragraph.flowIndex ?? 0);
        const editor = document.createElement("div");
        editor.className = "notices-compose-body-input notices-compose-rich-editor notices-compose-floating-paragraph-input";
        editor.contentEditable = "true";
        editor.spellcheck = true;
        editor.dataset.noticeRichEditor = "true";
        editor.dataset.noticeComposeEditorKind = "paragraph";
        editor.dataset.noticeComposeParagraphInput = "true";
        editor.dataset.noticeComposeBlockId = String(paragraph.id || "");
        editor.dataset.noticeFloatingParagraphId = String(paragraph.id || "");
        editor.dataset.noticeFlowIndex = String(paragraph.flow_index ?? paragraph.flowIndex ?? 0);
        editor.dataset.noticeRichPlaceholder = "문서를 입력하세요.";
        if (!target.querySelector("#noticesComposeBody")) {
          editor.id = "noticesComposeBody";
        }
        setRichEditorContent(editor, String(paragraph.text || ""), String(paragraph.richText || paragraph.rich_text || ""), normalizeRichAlign(paragraph.align || "left"));
        const paragraphFontSize = normalizeRichFontSizePx(paragraph.font_size_px || paragraph.fontSizePx || "");
        if (paragraphFontSize) {
          editor.style.fontSize = `${paragraphFontSize}px`;
        }
        section.appendChild(editor);
        flow.appendChild(section);
      } else {
        const section = document.createElement("section");
        section.className = "notices-detail-block notices-floating-scene-paragraph";
        section.dataset.noticeFlowIndex = String(paragraph.flow_index ?? paragraph.flowIndex ?? 0);
        const paragraphEl = document.createElement("p");
        renderRichFragment(paragraphEl, String(paragraph.richText || paragraph.rich_text || ""), String(paragraph.text || ""), normalizeRichAlign(paragraph.align || "left"));
        const paragraphFontSize = normalizeRichFontSizePx(paragraph.font_size_px || paragraph.fontSizePx || "");
        if (paragraphFontSize) {
          paragraphEl.style.fontSize = `${paragraphFontSize}px`;
        }
        section.appendChild(paragraphEl);
        flow.appendChild(section);
      }
    });
    scene.appendChild(flow);

    const objectLayer = document.createElement("div");
    objectLayer.className = `notices-floating-scene-objects${editable ? " notices-compose-scene-objects" : " notices-detail-scene-objects"}`;
    (Array.isArray(documentValue?.objects) ? documentValue.objects : []).forEach((obj) => {
      objectLayer.appendChild(createFloatingSceneObjectElement(obj, {
        editable,
        noticeItem: options.noticeItem || null,
      }));
    });
    scene.appendChild(objectLayer);
    target.appendChild(scene);
  }

  function applyFlowLaneObjectMetrics(wrapper = null, item = {}) {
    if (!(wrapper instanceof HTMLElement)) {
      return;
    }
    const offsetX = Math.max(0, Number(item?.frame?.x || 0) || 0);
    const width = Math.max(1, Number(item?.frame?.width || (String(item?.kind || "").trim() === "image" ? 420 : 640)) || (String(item?.kind || "").trim() === "image" ? 420 : 640));
    const height = Math.max(1, Number(item?.frame?.height || (String(item?.kind || "").trim() === "image" ? 320 : 220)) || (String(item?.kind || "").trim() === "image" ? 320 : 220));
    wrapper.dataset.noticeFrameX = String(offsetX);
    wrapper.dataset.noticeFrameY = "0";
    wrapper.dataset.noticeFrameWidth = String(width);
    wrapper.dataset.noticeFrameHeight = String(height);
    wrapper.style.setProperty("--notice-flow-object-offset-x", `${offsetX}px`);
    wrapper.style.setProperty("--notice-flow-object-width", `${width}px`);
    wrapper.style.setProperty("--notice-flow-object-height", `${height}px`);
  }

  function createFlowLaneObjectElement(item = {}, context = {}) {
    const kind = String(item?.kind || "").trim().toLowerCase();
    const editable = Boolean(context.editable);
    const wrapper = document.createElement("section");
    wrapper.className = `notices-flow-lane-object notices-flow-lane-object-${kind}`;
    wrapper.dataset.noticeSceneObjectId = String(item?.id || "");
    wrapper.dataset.noticeComposeSceneObjectId = String(item?.id || "");
    wrapper.dataset.noticeFloatingObjectId = String(item?.id || "");
    wrapper.dataset.noticeFlowIndex = String(item?.flow_index ?? item?.flowIndex ?? 0);
    applyFlowLaneObjectMetrics(wrapper, item);

    const body = document.createElement("div");
    body.className = "notices-flow-lane-object-body";

    if (editable) {
      const chrome = document.createElement("div");
      chrome.className = "notices-floating-object-chrome";
      const moveBtn = document.createElement("button");
      moveBtn.type = "button";
      moveBtn.className = "notices-floating-object-handle";
      moveBtn.dataset.noticeFlowLaneDragBody = String(item?.id || "");
      moveBtn.setAttribute("aria-label", `${kind} 이동`);
      chrome.appendChild(moveBtn);
      const removeBtn = document.createElement("button");
      removeBtn.type = "button";
      removeBtn.className = "notices-floating-object-remove";
      removeBtn.dataset.action = kind === "image"
        ? "notices-image-remove-floating"
        : (kind === "table" ? "notices-remove-table-block" : "notices-remove-poll-block");
      removeBtn.dataset.noticeFloatingObjectId = String(item?.id || "");
      removeBtn.dataset.noticeTableBlockId = String(item?.id || "");
      removeBtn.dataset.noticePollBlockId = String(item?.id || "");
      removeBtn.dataset.noticeImageObjectId = String(item?.id || "");
      removeBtn.setAttribute("aria-label", `${kind} 삭제`);
      chrome.appendChild(removeBtn);
      body.appendChild(chrome);
    }

    if (kind === "image") {
      const img = document.createElement("img");
      img.className = "notices-floating-object-image";
      img.loading = "lazy";
      img.draggable = false;
      img.alt = String(item?.caption || item?.fileName || item?.file_name || "공지 이미지").trim() || "공지 이미지";
      img.src = resolveNoticeImageUrl(item?.imageSrc || item?.image_src || "");
      if (editable) {
        img.dataset.noticeFlowLaneDragBody = String(item?.id || "");
      }
      body.appendChild(img);
      if (editable) {
        const resize = document.createElement("button");
        resize.type = "button";
        resize.className = "notices-flow-lane-resize";
        resize.dataset.noticeFlowLaneResizeHandle = String(item?.id || "");
        resize.setAttribute("aria-label", "이미지 크기 조절");
        body.appendChild(resize);
      }
    } else if (kind === "table") {
      const tablePayload = cloneTableDraft(item?.table || {});
      if (editable) {
        body.appendChild(buildTableGridElement(tablePayload, String(item?.id || "")));
      } else {
        const section = document.createElement("section");
        section.className = "notices-detail-block";
        const tableWrap = document.createElement("div");
        tableWrap.className = "notices-detail-table-wrap";
        const table = document.createElement("table");
        table.className = "notices-detail-table";
        const columns = Array.isArray(tablePayload.columns) ? tablePayload.columns : [];
        const columnsRich = Array.isArray(tablePayload.columnsRich) ? tablePayload.columnsRich : [];
        if (tablePayload.hasHeader && columns.length) {
          const thead = document.createElement("thead");
          const row = document.createElement("tr");
          columns.forEach((column, index) => {
            const th = document.createElement("th");
            renderRichFragment(th, richTextValueFromRaw(columnsRich[index] || {}), String(column || "").trim(), normalizeRichAlign(columnsRich[index]?.align || "left"));
            row.appendChild(th);
          });
          thead.appendChild(row);
          table.appendChild(thead);
        }
        const tbody = document.createElement("tbody");
        (tablePayload.rows || []).forEach((rowValue, rowIndex) => {
          const row = document.createElement("tr");
          row.style.height = `${Math.max(36, Number(tablePayload.rowHeights?.[rowIndex + 1] || 44) || 44)}px`;
          (rowValue || []).forEach((cell, colIndex) => {
            const td = document.createElement("td");
            renderRichFragment(td, richTextValueFromRaw(tablePayload.rowsRich?.[rowIndex]?.[colIndex] || {}), String(cell || "").trim(), normalizeRichAlign(tablePayload.rowsRich?.[rowIndex]?.[colIndex]?.align || "left"));
            row.appendChild(td);
          });
          tbody.appendChild(row);
        });
        table.appendChild(tbody);
        tableWrap.appendChild(table);
        section.appendChild(tableWrap);
        body.appendChild(section);
      }
    } else if (kind === "poll") {
      const pollPayload = clonePollDraft(item?.poll || {});
      body.appendChild(createPollBlock(context.noticeItem || null, pollPayload, { previewOnly: editable, forceResultsVisible: true }));
    }

    wrapper.appendChild(body);
    return wrapper;
  }

  function renderFlowLaneDocument(target, documentValue, options = {}) {
    if (!(target instanceof HTMLElement)) {
      return;
    }
    target.innerHTML = "";
    const editable = Boolean(options.editable);
    const detail = Boolean(options.detail);
    const documentDraft = normalizeFlowLaneDocumentDraft(documentValue, options.fallbackBodyText || "", options.fallbackBodyBlocks || null);
    const root = document.createElement("div");
    root.className = `notices-flow-lane-document${editable ? " notices-compose-flow-lane" : " notices-detail-flow-lane"}`;
    root.dataset.noticeBodyModel = SOC_NOTICE_BODY_MODEL_FLOW_LANE;
    if (editable) {
      root.dataset.noticeComposeModel = SOC_NOTICE_BODY_MODEL_FLOW_LANE;
    } else {
      root.dataset.noticeDetailModel = SOC_NOTICE_BODY_MODEL_FLOW_LANE;
    }
    const items = getFloatingDocumentItems(documentDraft);
    items.forEach((entry) => {
      if (entry.itemType === "paragraph") {
        const paragraph = entry.value;
        if (editable) {
          const section = document.createElement("section");
          section.className = "notices-compose-inline-block notices-compose-text-block notices-flow-lane-paragraph";
          section.dataset.noticeComposeFlowKind = "paragraph";
          section.dataset.noticeComposeBlockId = String(paragraph.id || "");
          section.dataset.noticeFlowIndex = String(paragraph.flow_index ?? paragraph.flowIndex ?? 0);
          const editor = document.createElement("div");
          editor.className = "notices-compose-body-input notices-compose-rich-editor notices-compose-flow-lane-paragraph-input";
          editor.contentEditable = "true";
          editor.spellcheck = true;
          editor.dataset.noticeRichEditor = "true";
          editor.dataset.noticeComposeEditorKind = "paragraph";
          editor.dataset.noticeComposeParagraphInput = "true";
          editor.dataset.noticeComposeBlockId = String(paragraph.id || "");
          editor.dataset.noticeFloatingParagraphId = String(paragraph.id || "");
          editor.dataset.noticeFlowIndex = String(paragraph.flow_index ?? paragraph.flowIndex ?? 0);
          editor.dataset.noticeRichPlaceholder = "문서를 입력하세요.";
          if (!root.querySelector("#noticesComposeBody")) {
            editor.id = "noticesComposeBody";
          }
          setRichEditorContent(editor, String(paragraph.text || ""), String(paragraph.richText || paragraph.rich_text || ""), normalizeRichAlign(paragraph.align || "left"));
          section.appendChild(editor);
          root.appendChild(section);
        } else {
          const section = document.createElement("section");
          section.className = "notices-detail-block notices-flow-lane-paragraph";
          const paragraphEl = document.createElement("p");
          renderRichFragment(paragraphEl, String(paragraph.richText || paragraph.rich_text || ""), String(paragraph.text || ""), normalizeRichAlign(paragraph.align || "left"));
          section.appendChild(paragraphEl);
          root.appendChild(section);
        }
        return;
      }
      root.appendChild(createFlowLaneObjectElement(entry.value, {
        editable,
        detail,
        noticeItem: options.noticeItem || null,
      }));
    });
    target.appendChild(root);
  }

  function getComposeFloatingSceneElement() {
    return document.querySelector('#noticesComposeDocumentFlow [data-notice-compose-scene="true"]');
  }

  function getComposeFloatingSceneScale(sceneEl = null) {
    if (!(sceneEl instanceof HTMLElement)) {
      return 1;
    }
    const rect = sceneEl.getBoundingClientRect();
    const canvasWidth = Number.parseFloat(sceneEl.style.getPropertyValue("--notices-scene-width") || "") || SOC_NOTICE_FLOATING_CANVAS_WIDTH;
    if (!canvasWidth || !rect.width) {
      return 1;
    }
    return rect.width / canvasWidth;
  }

  function resolveFloatingScenePoint(sceneEl = null, clientX = 0, clientY = 0) {
    if (!(sceneEl instanceof HTMLElement)) {
      return { x: 0, y: 0 };
    }
    const rect = sceneEl.getBoundingClientRect();
    const scale = getComposeFloatingSceneScale(sceneEl) || 1;
    return {
      x: Math.max(0, Math.round((clientX - rect.left) / scale)),
      y: Math.max(0, Math.round((clientY - rect.top) / scale)),
    };
  }

  function beginFloatingSceneInteraction(objectId = "", mode = "move", event = null) {
    const normalizedId = String(objectId || "").trim();
    if (!normalizedId || !(event instanceof MouseEvent) || !isFloatingNoticeModel(ensureWorkspaceState().composeDraft?.bodyModel)) {
      return;
    }
    const sceneEl = getComposeFloatingSceneElement();
    const objectEl = document.querySelector(`[data-notice-scene-object-id="${normalizedId}"]`);
    const objectValue = getFloatingDocumentObjectById(ensureWorkspaceState().composeDraft?.bodyDocument, normalizedId);
    if (!(sceneEl instanceof HTMLElement) || !(objectEl instanceof HTMLElement) || !objectValue) {
      return;
    }
    event.preventDefault();
    const scale = getComposeFloatingSceneScale(sceneEl) || 1;
    socNoticeFloatingSceneDragState = {
      objectId: normalizedId,
      mode,
      sceneEl,
      objectEl,
      scale,
      startClientX: event.clientX,
      startClientY: event.clientY,
      frame: {
        x: Number(objectValue.frame?.x || 0) || 0,
        y: Number(objectValue.frame?.y || 0) || 0,
        width: Math.max(1, Number(objectValue.frame?.width || 1) || 1),
        height: Math.max(1, Number(objectValue.frame?.height || 1) || 1),
      },
      nextFrame: null,
    };
    document.body.classList.add("notices-scene-object-dragging");
  }

  function handleFloatingScenePointerMove(event) {
    if (!(event instanceof MouseEvent) || !socNoticeFloatingSceneDragState) {
      return;
    }
    const session = socNoticeFloatingSceneDragState;
    const dx = (event.clientX - session.startClientX) / (session.scale || 1);
    const dy = (event.clientY - session.startClientY) / (session.scale || 1);
    const nextFrame = { ...session.frame };
    if (session.mode === "resize") {
      nextFrame.width = Math.max(80, Math.round(session.frame.width + dx));
      nextFrame.height = Math.max(80, Math.round(session.frame.height + dy));
    } else {
      nextFrame.x = Math.max(0, Math.round(session.frame.x + dx));
      nextFrame.y = Math.max(0, Math.round(session.frame.y + dy));
    }
    session.nextFrame = nextFrame;
    session.objectEl.style.left = `${nextFrame.x}px`;
    session.objectEl.style.top = `${nextFrame.y}px`;
    session.objectEl.style.width = `${nextFrame.width}px`;
    session.objectEl.style.minHeight = `${nextFrame.height}px`;
    session.objectEl.dataset.noticeFrameX = String(nextFrame.x);
    session.objectEl.dataset.noticeFrameY = String(nextFrame.y);
    session.objectEl.dataset.noticeFrameWidth = String(nextFrame.width);
    session.objectEl.dataset.noticeFrameHeight = String(nextFrame.height);
  }

  function finishFloatingSceneInteraction() {
    if (!socNoticeFloatingSceneDragState) {
      return;
    }
    const session = socNoticeFloatingSceneDragState;
    socNoticeFloatingSceneDragState = null;
    document.body.classList.remove("notices-scene-object-dragging");
    if (session.nextFrame) {
      updateFloatingObjectFrame(session.objectId, session.nextFrame);
    }
  }

  function beginFlowLaneInteraction(objectId = "", mode = "move", event = null) {
    const normalizedId = String(objectId || "").trim();
    if (!normalizedId || !(event instanceof MouseEvent) || !isFlowLaneNoticeModel(ensureWorkspaceState().composeDraft?.bodyModel)) {
      return;
    }
    const objectEl = document.querySelector(`[data-notice-scene-object-id="${normalizedId}"].notices-flow-lane-object`);
    const objectValue = getFloatingDocumentObjectById(ensureWorkspaceState().composeDraft?.bodyDocument, normalizedId);
    if (!(objectEl instanceof HTMLElement) || !objectValue) {
      return;
    }
    event.preventDefault();
    const naturalRatio = (() => {
      const img = objectEl.querySelector("img.notices-floating-object-image");
      if (!(img instanceof HTMLImageElement) || !img.naturalWidth || !img.naturalHeight) {
        return null;
      }
      return img.naturalHeight / img.naturalWidth;
    })();
    socNoticeFlowLaneDragState = {
      objectId: normalizedId,
      mode,
      objectEl,
      naturalRatio,
      startClientX: event.clientX,
      startClientY: event.clientY,
      frame: {
        x: Number(objectValue.frame?.x || 0) || 0,
        y: 0,
        width: Math.max(1, Number(objectValue.frame?.width || 1) || 1),
        height: Math.max(1, Number(objectValue.frame?.height || 1) || 1),
      },
      nextFrame: null,
    };
    document.body.classList.add("notices-scene-object-dragging");
  }

  function handleFlowLanePointerMove(event) {
    if (!(event instanceof MouseEvent) || !socNoticeFlowLaneDragState) {
      return;
    }
    const session = socNoticeFlowLaneDragState;
    const dx = event.clientX - session.startClientX;
    const nextFrame = { ...session.frame };
    if (session.mode === "resize") {
      nextFrame.width = Math.max(120, Math.round(session.frame.width + dx));
      if (session.naturalRatio) {
        nextFrame.height = Math.max(80, Math.round(nextFrame.width * session.naturalRatio));
      }
    } else {
      nextFrame.x = Math.max(0, Math.round(session.frame.x + dx));
    }
    session.nextFrame = nextFrame;
    applyFlowLaneObjectMetrics(session.objectEl, { ...session, frame: nextFrame });
  }

  function finishFlowLaneInteraction() {
    if (!socNoticeFlowLaneDragState) {
      return;
    }
    const session = socNoticeFlowLaneDragState;
    socNoticeFlowLaneDragState = null;
    document.body.classList.remove("notices-scene-object-dragging");
    if (session.nextFrame) {
      updateFloatingObjectFrame(session.objectId, session.nextFrame);
    }
  }

  function beginTableResizeInteraction(target = null, event = null) {
    if (!(target instanceof HTMLElement) || !(event instanceof MouseEvent) || !isFlowLaneNoticeModel(ensureWorkspaceState().composeDraft?.bodyModel)) {
      return;
    }
    const blockId = String(target.dataset.noticeTableBlockId || "").trim();
    const objectValue = getFloatingDocumentObjectById(ensureWorkspaceState().composeDraft?.bodyDocument, blockId);
    if (!blockId || !objectValue) {
      return;
    }
    event.preventDefault();
    socNoticeTableResizeState = {
      blockId,
      kind: String(target.dataset.noticeTableResizeKind || "").trim(),
      direction: String(target.dataset.noticeTableResizeDirection || "").trim(),
      index: target.dataset.noticeTableResizeIndex == null
        ? -1
        : Math.max(-1, Number.parseInt(String(target.dataset.noticeTableResizeIndex || "-1"), 10)),
      startClientX: event.clientX,
      startClientY: event.clientY,
      frame: { ...(objectValue.frame || {}) },
      table: cloneTableDraft(objectValue.table || {}),
      nextFrame: null,
      nextTable: null,
    };
    document.body.classList.add("notices-scene-object-dragging");
  }

  function handleTableResizePointerMove(event) {
    if (!(event instanceof MouseEvent) || !socNoticeTableResizeState) {
      return;
    }
    const session = socNoticeTableResizeState;
    const dx = event.clientX - session.startClientX;
    const dy = event.clientY - session.startClientY;
    const nextFrame = {
      x: Math.max(0, Number(session.frame.x || 0) || 0),
      y: 0,
      width: Math.max(120, Number(session.frame.width || 120) || 120),
      height: Math.max(72, Number(session.frame.height || 72) || 72),
    };
    const nextTable = cloneTableDraft(session.table);
    const minWidth = Math.max(72 * Math.max(1, nextTable.columns.length), 160);
    const minHeight = Math.max(36 * Math.max(1, nextTable.rowHeights.length), 72);

    if (session.kind === "outer") {
      if (session.direction.includes("left")) {
        const proposedX = Math.max(0, Math.round((Number(session.frame.x || 0) || 0) + dx));
        const widthDelta = proposedX - (Number(session.frame.x || 0) || 0);
        nextFrame.x = proposedX;
        nextFrame.width = Math.max(minWidth, Math.round((Number(session.frame.width || minWidth) || minWidth) - widthDelta));
      }
      if (session.direction.includes("right")) {
        nextFrame.width = Math.max(minWidth, Math.round((Number(session.frame.width || minWidth) || minWidth) + dx));
      }
      if (session.direction.includes("top")) {
        nextFrame.height = Math.max(minHeight, Math.round((Number(session.frame.height || minHeight) || minHeight) - dy));
      }
      if (session.direction.includes("bottom")) {
        nextFrame.height = Math.max(minHeight, Math.round((Number(session.frame.height || minHeight) || minHeight) + dy));
      }
      nextTable.columnWidths = scaleNumericParts(nextTable.columnWidths, nextFrame.width, 72);
      nextTable.rowHeights = scaleNumericParts(nextTable.rowHeights, nextFrame.height, 36);
    } else if (session.kind === "col" && session.index >= 0 && session.index < nextTable.columnWidths.length - 1) {
      const leftWidth = Math.max(72, Math.round(nextTable.columnWidths[session.index] + dx));
      const rightWidth = Math.max(72, Math.round(nextTable.columnWidths[session.index + 1] - dx));
      nextTable.columnWidths[session.index] = leftWidth;
      nextTable.columnWidths[session.index + 1] = rightWidth;
      nextFrame.width = nextTable.columnWidths.reduce((sum, value) => sum + value, 0);
    } else if (session.kind === "row" && session.index >= 0 && session.index < nextTable.rowHeights.length - 1) {
      const upperHeight = Math.max(36, Math.round(nextTable.rowHeights[session.index] + dy));
      const lowerHeight = Math.max(36, Math.round(nextTable.rowHeights[session.index + 1] - dy));
      nextTable.rowHeights[session.index] = upperHeight;
      nextTable.rowHeights[session.index + 1] = lowerHeight;
      nextFrame.height = nextTable.rowHeights.reduce((sum, value) => sum + value, 0);
    }

    session.nextFrame = nextFrame;
    session.nextTable = nextTable;
    applyTableDraftToDom(session.blockId, nextTable, nextFrame);
  }

  function finishTableResizeInteraction() {
    if (!socNoticeTableResizeState) {
      return;
    }
    const session = socNoticeTableResizeState;
    socNoticeTableResizeState = null;
    document.body.classList.remove("notices-scene-object-dragging");
    if (!session.nextFrame || !session.nextTable) {
      return;
    }
    updateComposeFloatingDocument((documentValue) => {
      const next = normalizeFlowLaneDocumentDraft(documentValue, "");
      next.objects = (next.objects || []).map((item) => {
        if (String(item?.id || "").trim() !== session.blockId) {
          return item;
        }
        return {
          ...item,
          frame: createFloatingObjectFrame(session.nextFrame),
          table: cloneTableDraft(session.nextTable),
        };
      });
      return next;
    }, { markDirty: true, rerender: true });
  }

  function renderNoticeDetailBody(target, item) {
    if (!(target instanceof HTMLElement)) {
      return;
    }
    target.innerHTML = "";
    if (isFlowLaneNoticeModel(item?.bodyModel) && item?.bodyDocument && typeof item.bodyDocument === "object") {
      renderFlowLaneDocument(target, item.bodyDocument, {
        detail: true,
        editable: false,
        noticeItem: item,
        fallbackBodyText: item.bodyText || item.bodyPreview || item.message || "",
        fallbackBodyBlocks: item.bodyBlocks || [],
      });
      return;
    }
    if (isFloatingNoticeModel(item?.bodyModel) && item?.bodyDocument && typeof item.bodyDocument === "object") {
      renderFloatingScene(target, normalizeFloatingDocumentDraft(item.bodyDocument, item.bodyText || item.bodyPreview || item.message || ""), {
        detail: true,
        editable: false,
        noticeItem: item,
      });
      return;
    }
    const bodyBlocks = normalizeBodyBlocks(item?.bodyBlocks, item?.bodyText || item?.bodyPreview || item?.message || "");
    if (!bodyBlocks.length) {
      target.appendChild(createEmptyState("공지 본문이 없습니다.", ""));
      return;
    }

    const prose = document.createElement("div");
    prose.className = "notices-detail-prose";
    bodyBlocks.forEach((block) => {
      const kind = String(block?.kind || "").trim();
      if (kind === "paragraph") {
        const section = document.createElement("section");
        section.className = "notices-detail-block";
        if (block.title) {
          const heading = document.createElement("h4");
          heading.className = "notices-detail-block-title";
          heading.textContent = String(block.title || "").trim();
          section.appendChild(heading);
        }
        const paragraph = document.createElement("p");
        if (String(block.variant || "").trim() === "lead") {
          paragraph.className = "notices-detail-lead";
        }
        renderRichFragment(paragraph, richTextValueFromRaw(block), String(block.text || "").trim(), normalizeRichAlign(block.align || "left"));
        section.appendChild(paragraph);
        prose.appendChild(section);
        return;
      }
      if (kind === "image") {
        const section = document.createElement("section");
        section.className = "notices-detail-block";
        const wrap = document.createElement("figure");
        wrap.className = "notices-detail-image-wrap";
        const img = document.createElement("img");
        img.className = "notices-detail-image";
        img.loading = "lazy";
        img.alt = String(block.caption || block.fileName || block.file_name || "공지 이미지").trim() || "공지 이미지";
        img.src = resolveNoticeImageUrl(block.imageSrc || block.image_src || "");
        wrap.appendChild(img);
        const captionText = String(block.caption || "").trim();
        if (captionText) {
          const caption = document.createElement("figcaption");
          caption.className = "notices-detail-image-caption";
          caption.textContent = captionText;
          wrap.appendChild(caption);
        }
        section.appendChild(wrap);
        prose.appendChild(section);
        return;
      }
      if (kind === "table") {
        const section = document.createElement("section");
        section.className = "notices-detail-block";
        if (block.title) {
          const heading = document.createElement("h4");
          heading.className = "notices-detail-block-title";
          heading.textContent = String(block.title || "").trim();
          section.appendChild(heading);
        }
        const wrap = document.createElement("div");
        wrap.className = "notices-detail-table-wrap";
        const table = document.createElement("table");
        table.className = "notices-detail-table";
        const columns = Array.isArray(block.columns) ? block.columns : [];
        const columnsRich = Array.isArray(block.columnsRich || block.columns_rich) ? (block.columnsRich || block.columns_rich) : [];
        const hasHeader = block.hasHeader ?? block.has_header ?? true;
        if (hasHeader && columns.length) {
          const thead = document.createElement("thead");
          const headRow = document.createElement("tr");
          columns.forEach((column, index) => {
            const th = document.createElement("th");
            th.scope = "col";
            renderRichFragment(th, richTextValueFromRaw(columnsRich[index] || {}), String(column || "").trim() || "-", normalizeRichAlign(columnsRich[index]?.align || "left"));
            headRow.appendChild(th);
          });
          thead.appendChild(headRow);
          table.appendChild(thead);
        }
        const tbody = document.createElement("tbody");
        if (!hasHeader && columns.length) {
          const columnsAsRow = document.createElement("tr");
          columns.forEach((column, index) => {
            const td = document.createElement("td");
            renderRichFragment(td, richTextValueFromRaw(columnsRich[index] || {}), String(column || "").trim() || "-", normalizeRichAlign(columnsRich[index]?.align || "left"));
            columnsAsRow.appendChild(td);
          });
          tbody.appendChild(columnsAsRow);
        }
        const rowsRich = Array.isArray(block.rowsRich || block.rows_rich) ? (block.rowsRich || block.rows_rich) : [];
        (Array.isArray(block.rows) ? block.rows : []).forEach((row, rowIndex) => {
          if (!Array.isArray(row)) {
            return;
          }
          const tr = document.createElement("tr");
          row.forEach((cell, colIndex) => {
            const td = document.createElement("td");
            renderRichFragment(td, richTextValueFromRaw(rowsRich[rowIndex]?.[colIndex] || {}), String(cell || "").trim() || "-", normalizeRichAlign(rowsRich[rowIndex]?.[colIndex]?.align || "left"));
            tr.appendChild(td);
          });
          tbody.appendChild(tr);
        });
        table.appendChild(tbody);
        wrap.appendChild(table);
        section.appendChild(wrap);
        prose.appendChild(section);
        return;
      }
      if (kind === "poll") {
        prose.appendChild(createPollBlock(item, block.poll || {}));
      }
    });
    target.appendChild(prose);
  }

  function renderDetailPanel(elements, workspace) {
    if (!(elements.detailBody instanceof HTMLElement)) {
      return;
    }
    const selected = workspace.selectedRow;
    if (elements.detailTitle instanceof HTMLElement) {
      elements.detailTitle.textContent = selected?.title || "공지 상세";
    }
    if (elements.detailMeta instanceof HTMLElement) {
      if (selected) {
        const bits = [
          getCategoryLabel(selected.category || "all"),
          formatDateLabel(selected.publishedAt || selected.createdAt || "", "-"),
        ];
        if (selected.createdByName) {
          bits.push(selected.createdByName);
        }
        elements.detailMeta.textContent = bits.filter(Boolean).join(" · ");
      } else if (workspace.error) {
        elements.detailMeta.textContent = workspace.error;
      } else {
        elements.detailMeta.textContent = "공지 목록에서 항목을 선택하면 상세가 열립니다.";
      }
    }
    if (elements.detailEditBtn instanceof HTMLElement) {
      elements.detailEditBtn.classList.toggle("hidden", !canManageSocNotices() || !selected);
    }
    if (elements.detailDeleteBtn instanceof HTMLElement) {
      elements.detailDeleteBtn.classList.toggle("hidden", !canManageSocNotices() || !selected);
      elements.detailDeleteBtn.dataset.noticeId = String(selected?.id || "").trim();
    }
    elements.detailBody.innerHTML = "";
    if (workspace.detailLoading && selected) {
      renderNoticeDetailBody(elements.detailBody, buildNoticePreviewShellItem(selected) || selected);
      return;
    }
    if (!selected) {
      elements.detailBody.appendChild(createEmptyState(
        workspace.error ? "공지 상세를 불러오지 못했습니다." : "공지 상세를 선택해 주세요.",
        workspace.error || "목록에서 항목을 열면 제목, 날짜, 본문을 이 화면에서 확인할 수 있습니다."
      ));
      return;
    }
    renderNoticeDetailBody(elements.detailBody, selected);
  }

  function renderComposeSettings(elements, workspace) {
    const draft = workspace.composeDraft;
    if (elements.composeCategory instanceof HTMLSelectElement) {
      if (!elements.composeCategory.options.length) {
        SOC_NOTICE_CATEGORY_OPTIONS.filter((item) => item.value !== "all").forEach((item) => {
          const option = document.createElement("option");
          option.value = item.value;
          option.textContent = item.label;
          elements.composeCategory.appendChild(option);
        });
      }
      elements.composeCategory.value = normalizeNoticeCategory(draft.category || "ops", false);
    }
    if (elements.composePinnedToggle instanceof HTMLButtonElement) {
      const active = Boolean(draft.isPinned);
      elements.composePinnedToggle.classList.toggle("is-active", active);
      elements.composePinnedToggle.setAttribute("aria-pressed", active ? "true" : "false");
      const copy = elements.composePinnedToggle.querySelector(".notices-switch-copy");
      if (copy instanceof HTMLElement) {
        copy.textContent = active ? "켜짐" : "꺼짐";
      }
    }
    if (elements.composeTitle instanceof HTMLInputElement && elements.composeTitle.value !== draft.title) {
      elements.composeTitle.value = draft.title;
    }
    if (elements.publishBtn instanceof HTMLButtonElement) {
      elements.publishBtn.textContent = workspace.composeEditingId ? "수정 저장" : "발행";
    }
    renderComposeDraftMeta(elements);
  }

  function renderTablePicker(elements, workspace) {
    if (!(elements.composeTablePicker instanceof HTMLElement) || !(elements.composeTablePickerGrid instanceof HTMLElement)) {
      return;
    }
    elements.composeTablePicker.classList.toggle("hidden", !workspace.composeTablePickerOpen);
    elements.composeTablePickerGrid.innerHTML = "";
    if (elements.composeTablePickerLabel instanceof HTMLElement) {
      elements.composeTablePickerLabel.textContent = `${workspace.composeTablePickerRows} x ${workspace.composeTablePickerCols} 표`;
    }
    for (let row = 1; row <= 6; row += 1) {
      for (let col = 1; col <= 6; col += 1) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = `notices-table-picker-cell${row <= workspace.composeTablePickerRows && col <= workspace.composeTablePickerCols ? " is-active" : ""}`;
        button.dataset.action = "notices-table-picker-select";
        button.dataset.rows = String(row);
        button.dataset.cols = String(col);
        button.setAttribute("aria-label", `${row} x ${col} 표`);
        elements.composeTablePickerGrid.appendChild(button);
      }
    }
  }

  function buildTableGridElement(tableDraft, blockId = "") {
    const createCellEditor = ({ kind = "table-cell", field = "cell", rowIndex = null, colIndex = 0, text = "", cell = null, placeholder = "" } = {}) => {
      const editor = document.createElement("div");
      editor.className = "notices-compose-table-input notices-compose-rich-editor";
      editor.contentEditable = "true";
      editor.spellcheck = true;
      editor.dataset.noticeRichEditor = "true";
      editor.dataset.noticeComposeEditorKind = kind;
      editor.dataset.noticeTableBlockId = String(blockId || "").trim();
      editor.dataset.noticeTableField = field;
      editor.dataset.noticeTableCol = String(colIndex);
      editor.dataset.noticeRichPlaceholder = placeholder;
      if (rowIndex != null) {
        editor.dataset.noticeTableRow = String(rowIndex);
      }
      setRichEditorContent(editor, String(text || ""), richTextValueFromRaw(cell || {}), normalizeRichAlign(cell?.align || "left"));
      return editor;
    };
    const shell = document.createElement("div");
    shell.className = "notices-compose-table-shell";
    shell.dataset.noticeTableBlockId = String(blockId || "").trim();
    const table = document.createElement("table");
    table.className = "notices-compose-table";
    const totalTableWidth = (Array.isArray(tableDraft.columnWidths) ? tableDraft.columnWidths : []).reduce((sum, value) => sum + (Number(value || 0) || 0), 0);
    if (totalTableWidth > 0) {
      table.style.width = `${totalTableWidth}px`;
    }
    const colgroup = document.createElement("colgroup");
    tableDraft.columns.forEach((_, index) => {
      const col = document.createElement("col");
      const width = Math.max(72, Number(tableDraft.columnWidths?.[index] || 160) || 160);
      col.style.width = `${width}px`;
      colgroup.appendChild(col);
    });
    table.appendChild(colgroup);
    if (tableDraft.hasHeader) {
      const thead = document.createElement("thead");
      const row = document.createElement("tr");
      row.style.height = `${Math.max(36, Number(tableDraft.rowHeights?.[0] || 44) || 44)}px`;
      tableDraft.columns.forEach((column, index) => {
        const th = document.createElement("th");
        th.appendChild(createCellEditor({
          kind: "table-header",
          field: "header",
          colIndex: index,
          text: String(column || ""),
          cell: tableDraft.columnsRich?.[index] || null,
          placeholder: `열 ${index + 1}`,
        }));
        row.appendChild(th);
      });
      thead.appendChild(row);
      table.appendChild(thead);
    }
    const tbody = document.createElement("tbody");
    if (!tableDraft.hasHeader) {
      const firstRow = document.createElement("tr");
      tableDraft.columns.forEach((column, index) => {
        const td = document.createElement("td");
        td.appendChild(createCellEditor({
          kind: "table-header",
          field: "header",
          colIndex: index,
          text: String(column || ""),
          cell: tableDraft.columnsRich?.[index] || null,
          placeholder: `열 ${index + 1}`,
        }));
        firstRow.appendChild(td);
      });
      tbody.appendChild(firstRow);
    }
    tableDraft.rows.forEach((row, rowIndex) => {
      const tr = document.createElement("tr");
      tr.style.height = `${Math.max(36, Number(tableDraft.rowHeights?.[rowIndex + 1] || 44) || 44)}px`;
      row.forEach((cell, colIndex) => {
        const td = document.createElement("td");
        td.appendChild(createCellEditor({
          kind: "table-cell",
          field: "cell",
          rowIndex,
          colIndex,
          text: String(cell || ""),
          cell: tableDraft.rowsRich?.[rowIndex]?.[colIndex] || null,
          placeholder: `행 ${rowIndex + 1}`,
        }));
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    shell.appendChild(table);

    const rowControls = document.createElement("div");
    rowControls.className = "notices-compose-table-edge-controls notices-compose-table-edge-controls-rows";
    const removeRowBtn = document.createElement("button");
    removeRowBtn.type = "button";
    removeRowBtn.className = "notices-compose-table-edge-button";
    removeRowBtn.dataset.action = "notices-table-remove-row";
    removeRowBtn.dataset.noticeTableBlockId = String(blockId || "").trim();
    removeRowBtn.setAttribute("aria-label", "행 삭제");
    removeRowBtn.textContent = "-";
    const addRowBtn = document.createElement("button");
    addRowBtn.type = "button";
    addRowBtn.className = "notices-compose-table-edge-button";
    addRowBtn.dataset.action = "notices-table-add-row";
    addRowBtn.dataset.noticeTableBlockId = String(blockId || "").trim();
    addRowBtn.setAttribute("aria-label", "행 추가");
    addRowBtn.textContent = "+";
    rowControls.append(removeRowBtn, addRowBtn);

    const columnControls = document.createElement("div");
    columnControls.className = "notices-compose-table-edge-controls notices-compose-table-edge-controls-columns";
    const removeColumnBtn = document.createElement("button");
    removeColumnBtn.type = "button";
    removeColumnBtn.className = "notices-compose-table-edge-button";
    removeColumnBtn.dataset.action = "notices-table-remove-column";
    removeColumnBtn.dataset.noticeTableBlockId = String(blockId || "").trim();
    removeColumnBtn.setAttribute("aria-label", "열 삭제");
    removeColumnBtn.textContent = "-";
    const addColumnBtn = document.createElement("button");
    addColumnBtn.type = "button";
    addColumnBtn.className = "notices-compose-table-edge-button";
    addColumnBtn.dataset.action = "notices-table-add-column";
    addColumnBtn.dataset.noticeTableBlockId = String(blockId || "").trim();
    addColumnBtn.setAttribute("aria-label", "열 추가");
    addColumnBtn.textContent = "+";
    columnControls.append(removeColumnBtn, addColumnBtn);

    const shouldUseResizeHandles = isFlowLaneNoticeModel(ensureWorkspaceState().composeDraft?.bodyModel);
    if (shouldUseResizeHandles) {
      shell.appendChild(buildTableResizeOverlay(tableDraft, String(blockId || "").trim()));
    } else {
      shell.append(rowControls, columnControls);
    }
    return shell;
  }

  function calculateTableDraftMetrics(tableDraft = {}) {
    const columnWidths = Array.isArray(tableDraft.columnWidths) ? tableDraft.columnWidths.map((value) => Math.max(72, Number(value || 0) || 72)) : [];
    const rowHeights = Array.isArray(tableDraft.rowHeights) ? tableDraft.rowHeights.map((value) => Math.max(36, Number(value || 0) || 36)) : [];
    return {
      columnWidths,
      rowHeights,
      totalWidth: columnWidths.reduce((sum, value) => sum + value, 0),
      totalHeight: rowHeights.reduce((sum, value) => sum + value, 0),
    };
  }

  function buildTableResizeHandle({ kind = "", direction = "", index = -1, left = null, top = null } = {}, blockId = "") {
    const handle = document.createElement("button");
    handle.type = "button";
    handle.className = `notices-table-resize-handle notices-table-resize-handle-${kind}${direction ? ` notices-table-resize-handle-${direction}` : ""}`;
    handle.dataset.noticeTableResizeKind = kind;
    handle.dataset.noticeTableResizeDirection = direction;
    handle.dataset.noticeTableBlockId = String(blockId || "").trim();
    if (index >= 0) {
      handle.dataset.noticeTableResizeIndex = String(index);
    }
    if (left != null) {
      handle.style.left = `${left}px`;
    }
    if (top != null) {
      handle.style.top = `${top}px`;
    }
    return handle;
  }

  function buildTableResizeOverlay(tableDraft = {}, blockId = "") {
    const metrics = calculateTableDraftMetrics(tableDraft);
    const layer = document.createElement("div");
    layer.className = "notices-table-resize-layer";
    layer.dataset.noticeTableBlockId = String(blockId || "").trim();

    ["top", "right", "bottom", "left", "top-left", "top-right", "bottom-left", "bottom-right"].forEach((direction) => {
      layer.appendChild(buildTableResizeHandle({ kind: "outer", direction }, blockId));
    });

    let currentLeft = 0;
    metrics.columnWidths.forEach((width, index) => {
      currentLeft += width;
      if (index < metrics.columnWidths.length - 1) {
        layer.appendChild(buildTableResizeHandle({ kind: "col", index, left: currentLeft }, blockId));
      }
    });

    let currentTop = 0;
    metrics.rowHeights.forEach((height, index) => {
      currentTop += height;
      if (index < metrics.rowHeights.length - 1) {
        layer.appendChild(buildTableResizeHandle({ kind: "row", index, top: currentTop }, blockId));
      }
    });
    return layer;
  }

  function scaleNumericParts(parts = [], nextTotal = 0, minimum = 1) {
    const values = Array.isArray(parts) ? parts.map((value) => Math.max(minimum, Number(value || 0) || minimum)) : [];
    if (!values.length) {
      return values;
    }
    const currentTotal = values.reduce((sum, value) => sum + value, 0);
    const safeTotal = Math.max(minimum * values.length, Number(nextTotal || 0) || currentTotal);
    if (!currentTotal) {
      return Array.from({ length: values.length }, () => safeTotal / values.length);
    }
    let remaining = safeTotal;
    return values.map((value, index) => {
      if (index === values.length - 1) {
        return Math.max(minimum, Math.round(remaining));
      }
      const nextValue = Math.max(minimum, Math.round((value / currentTotal) * safeTotal));
      remaining -= nextValue;
      return nextValue;
    });
  }

  function applyTableDraftToDom(blockId = "", tableDraft = {}, frame = null) {
    const normalizedId = String(blockId || "").trim();
    if (!normalizedId) {
      return;
    }
    const metrics = calculateTableDraftMetrics(tableDraft);
    const shells = Array.from(document.querySelectorAll(`.notices-compose-table-shell[data-notice-table-block-id="${normalizedId}"]`));
    shells.forEach((shell) => {
      if (!(shell instanceof HTMLElement)) {
        return;
      }
      const table = shell.querySelector(".notices-compose-table");
      if (table instanceof HTMLTableElement && metrics.totalWidth > 0) {
        table.style.width = `${metrics.totalWidth}px`;
        Array.from(table.querySelectorAll("colgroup col")).forEach((col, index) => {
          if (col instanceof HTMLElement) {
            col.style.width = `${metrics.columnWidths[index] || 160}px`;
          }
        });
        const headRow = table.querySelector("thead tr");
        if (headRow instanceof HTMLElement) {
          headRow.style.height = `${metrics.rowHeights[0] || 44}px`;
        }
        Array.from(table.querySelectorAll("tbody tr")).forEach((row, index) => {
          if (row instanceof HTMLElement) {
            row.style.height = `${metrics.rowHeights[index + 1] || 44}px`;
          }
        });
      }
      const oldLayer = shell.querySelector(".notices-table-resize-layer");
      if (oldLayer instanceof HTMLElement) {
        oldLayer.remove();
      }
      shell.appendChild(buildTableResizeOverlay(tableDraft, normalizedId));
    });
    if (frame && isFlowLaneNoticeModel(ensureWorkspaceState().composeDraft?.bodyModel)) {
      const objectEl = document.querySelector(`[data-notice-scene-object-id="${normalizedId}"].notices-flow-lane-object`);
      if (objectEl instanceof HTMLElement) {
        applyFlowLaneObjectMetrics(objectEl, { frame, kind: "table" });
      }
    }
  }

  function resizeComposeParagraphInput() {
    // Contenteditable surfaces size via CSS; kept as a compatibility no-op for old callers.
  }

  function createComposeParagraphBlockElement(block, index = 0, options = {}) {
    const isPrimarySurface = Boolean(options?.primarySurface);
    const showPlaceholder = options?.showPlaceholder !== false;
    const section = document.createElement("section");
    section.className = "notices-compose-inline-block notices-compose-text-block notices-compose-flow-block notices-compose-flow-paragraph";
    section.dataset.noticeInlineKind = "body";
    section.dataset.noticeComposeFlowIndex = String(index);
    section.dataset.noticeComposeFlowKind = "paragraph";
    section.dataset.noticeComposeBlockId = String(block.id || "");

    const surface = document.createElement("div");
    surface.className = "notices-compose-editor-surface notices-compose-flow-surface";
    const editor = document.createElement("div");
    editor.className = "notices-compose-body-input notices-compose-rich-editor notices-compose-flow-textarea";
    editor.contentEditable = "true";
    editor.spellcheck = true;
    editor.dataset.noticeComposeSurfaceMode = isPrimarySurface ? "primary" : "inline";
    editor.dataset.noticeComposeParagraphInput = "true";
    editor.dataset.noticeRichEditor = "true";
    editor.dataset.noticeComposeEditorKind = "paragraph";
    editor.dataset.noticeComposeBlockId = String(block.id || "");
    editor.dataset.noticeRichPlaceholder = showPlaceholder
      ? "문단은 빈 줄로 구분합니다. 긴 안내, 절차, 유의사항을 순서대로 정리하세요."
      : "";
    if (isPrimarySurface) {
      editor.classList.add("is-primary-body-surface");
    }
    if (index === 0) {
      editor.id = "noticesComposeBody";
    }
    setRichEditorContent(editor, String(block.text || ""), richTextValueFromRaw(block), normalizeRichAlign(block.align || "left"));
    surface.appendChild(editor);
    section.appendChild(surface);
    return section;
  }

  function createComposeTableBlockElement(block, index = 0) {
    const tableDraft = cloneTableDraft({
      enabled: true,
      ...(block.table || {}),
    });
    const section = document.createElement("section");
    section.className = "notices-compose-flow-block notices-compose-flow-embed-block notices-compose-flow-table-block";
    section.setAttribute("aria-label", "표 블록");
    section.dataset.noticeInlineKind = "table";
    section.dataset.noticeComposeFlowIndex = String(index);
    section.dataset.noticeComposeFlowKind = "table";
    section.dataset.noticeComposeBlockId = String(block.id || "");
    section.dataset.noticeTableBlockId = String(block.id || "");

    const panel = document.createElement("div");
    panel.className = "notices-table-panel";
    const grid = document.createElement("div");
    grid.className = "notices-compose-table-grid";
    grid.dataset.noticeTableBlockId = String(block.id || "");
    grid.appendChild(buildTableGridElement(tableDraft, String(block.id || "")));
    panel.appendChild(grid);

    const actions = document.createElement("div");
    actions.className = "notices-compose-flow-block-actions";
    const moveBtn = document.createElement("button");
    moveBtn.type = "button";
    moveBtn.className = "notices-inline-drag-handle notices-inline-drag-handle-edge";
    moveBtn.dataset.noticeInlineDragHandle = "table";
    moveBtn.dataset.noticeTableBlockId = String(block.id || "");
    moveBtn.setAttribute("aria-label", "표 이동");
    const moveGlyph = document.createElement("span");
    moveGlyph.className = "notices-inline-handle-dots";
    moveBtn.appendChild(moveGlyph);
    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "notices-inline-remove notices-inline-remove-icon";
    removeBtn.dataset.action = "notices-remove-table-block";
    removeBtn.dataset.noticeTableBlockId = String(block.id || "");
    removeBtn.setAttribute("aria-label", "표 삭제");
    const removeGlyph = document.createElement("span");
    removeGlyph.className = "notices-inline-remove-glyph";
    removeBtn.appendChild(removeGlyph);
    actions.append(moveBtn, removeBtn);

    section.append(panel, actions);
    return section;
  }

  function createComposePollBlockElement(block, index = 0) {
    const previewDraft = clonePollDraft({
      enabled: true,
      ...(block.poll || {}),
    });
    const section = createPollBlock(null, {
      ...previewDraft,
      enabled: true,
      canVote: false,
      hasVoted: false,
      resultsVisible: true,
      options: previewDraft.options.map((option, optionIndex) => ({
        optionId: option.optionId || createNoticeBlockId(`poll-option-${optionIndex + 1}`),
        label: option.label || `선택지 ${optionIndex + 1}`,
        voteCount: 0,
        voteRatio: 0,
      })),
    }, { previewOnly: true, forceResultsVisible: true });
    section.classList.add("notices-compose-flow-block", "notices-compose-flow-embed-block", "notices-compose-flow-poll-block");
    section.setAttribute("aria-label", "투표 블록");
    section.dataset.noticeInlineKind = "poll";
    section.dataset.noticeComposeFlowIndex = String(index);
    section.dataset.noticeComposeFlowKind = "poll";
    section.dataset.noticeComposeBlockId = String(block.id || "");
    section.dataset.noticePollBlockId = String(block.id || "");

    const actions = document.createElement("div");
    actions.className = "notices-compose-flow-block-actions";
    const moveBtn = document.createElement("button");
    moveBtn.type = "button";
    moveBtn.className = "notices-inline-drag-handle notices-inline-drag-handle-edge";
    moveBtn.dataset.noticeInlineDragHandle = "poll";
    moveBtn.dataset.noticePollBlockId = String(block.id || "");
    moveBtn.setAttribute("aria-label", "투표 이동");
    const moveGlyph = document.createElement("span");
    moveGlyph.className = "notices-inline-handle-dots";
    moveBtn.appendChild(moveGlyph);
    const editBtn = document.createElement("button");
    editBtn.type = "button";
    editBtn.className = "notices-editor-action notices-editor-action-icon";
    editBtn.dataset.action = "notices-edit-poll-block";
    editBtn.dataset.noticePollBlockId = String(block.id || "");
    editBtn.setAttribute("aria-label", "투표 편집");
    const editGlyph = document.createElement("span");
    editGlyph.className = "notices-inline-edit-glyph";
    editBtn.appendChild(editGlyph);
    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "notices-inline-remove notices-inline-remove-icon";
    removeBtn.dataset.action = "notices-remove-poll-block";
    removeBtn.dataset.noticePollBlockId = String(block.id || "");
    removeBtn.setAttribute("aria-label", "투표 삭제");
    const removeGlyph = document.createElement("span");
    removeGlyph.className = "notices-inline-remove-glyph";
    removeBtn.appendChild(removeGlyph);
    actions.append(moveBtn, editBtn, removeBtn);
    section.appendChild(actions);
    return section;
  }

  function renderComposeDocument(elements, workspace) {
    if (!(elements.composeDocumentFlow instanceof HTMLElement)) {
      return;
    }
    elements.composeDocumentFlow.innerHTML = "";
    if (isFlowLaneNoticeModel(workspace.composeDraft?.bodyModel)) {
      const bodyDocument = normalizeFlowLaneDocumentDraft(
        workspace.composeDraft?.bodyDocument,
        workspace.composeDraft?.bodyText || ""
      );
      workspace.composeDraft.bodyDocument = bodyDocument;
      workspace.composeDraft.bodyText = buildFloatingDocumentBodyText(bodyDocument);
      renderFlowLaneDocument(elements.composeDocumentFlow, bodyDocument, {
        detail: false,
        editable: true,
        fallbackBodyText: workspace.composeDraft?.bodyText || "",
      });
      return;
    }
    if (isFloatingNoticeModel(workspace.composeDraft?.bodyModel)) {
      const bodyDocument = normalizeFloatingDocumentDraft(
        workspace.composeDraft?.bodyDocument,
        workspace.composeDraft?.bodyText || ""
      );
      workspace.composeDraft.bodyDocument = bodyDocument;
      workspace.composeDraft.bodyText = buildFloatingDocumentBodyText(bodyDocument);
      renderFloatingScene(elements.composeDocumentFlow, bodyDocument, {
        detail: false,
        editable: true,
      });
      return;
    }
    const composeContentBlocks = getComposeContentBlocks(workspace.composeDraft);
    const primaryParagraphId = composeContentBlocks.length === 1 && composeContentBlocks[0]?.kind === "paragraph"
      ? String(composeContentBlocks[0].id || "").trim()
      : "";
    const hasEmbeddedBlock = composeContentBlocks.some((block) => block.kind === "table" || block.kind === "poll");
    const contentStream = document.createElement("div");
    contentStream.className = "notices-compose-flow-stream";
    if (hasEmbeddedBlock) {
      contentStream.classList.add("has-embed");
    }
    composeContentBlocks.forEach((block, index) => {
      if (block.kind === "paragraph") {
        const paragraphEl = createComposeParagraphBlockElement(block, index, {
          primarySurface: Boolean(primaryParagraphId && String(block.id || "").trim() === primaryParagraphId),
          showPlaceholder: !hasEmbeddedBlock,
        });
        if (hasEmbeddedBlock) {
          paragraphEl.classList.add("is-stream-fragment");
          if (!String(block.text || "").trim()) {
            paragraphEl.classList.add("is-empty-fragment");
          }
        }
        contentStream.appendChild(paragraphEl);
        return;
      }
      if (block.kind === "table") {
        contentStream.appendChild(createComposeTableBlockElement(block, index));
        return;
      }
      if (block.kind === "poll") {
        contentStream.appendChild(createComposePollBlockElement(block, index));
      }
    });

    elements.composeDocumentFlow.appendChild(contentStream);
    if (elements.composeImageBlock instanceof HTMLElement) {
      elements.composeImageBlock.classList.add("notices-compose-flow-block", "notices-compose-flow-embed-block");
      elements.composeDocumentFlow.appendChild(elements.composeImageBlock);
    }

    const imageBtn = document.getElementById("noticesComposeInsertImageBtn");
    const tableBtn = document.getElementById("noticesComposeInsertTableBtn");
    const pollBtn = document.getElementById("noticesComposeInsertPollBtn");
    if (imageBtn instanceof HTMLElement) {
      const active = Boolean(workspace.composeDraft.imagesEnabled);
      imageBtn.classList.toggle("is-active", active);
      imageBtn.setAttribute("aria-pressed", active ? "true" : "false");
    }
    if (tableBtn instanceof HTMLElement) {
      const active = Boolean(workspace.composeDraft.table?.enabled || workspace.composeTablePickerOpen);
      tableBtn.classList.toggle("is-active", active);
      tableBtn.setAttribute("aria-pressed", active ? "true" : "false");
    }
    if (pollBtn instanceof HTMLElement) {
      const active = Boolean(workspace.composeDraft.poll?.enabled);
      pollBtn.classList.toggle("is-active", active);
      pollBtn.setAttribute("aria-pressed", active ? "true" : "false");
    }
  }

  function renderImageList(elements, workspace) {
    if (!(elements.composeImageBlock instanceof HTMLElement) || !(elements.composeImageList instanceof HTMLElement)) {
      return;
    }
    if (usesStructuredNoticeDocumentModel(workspace.composeDraft?.bodyModel)) {
      elements.composeImageBlock.classList.add("hidden");
      elements.composeImageList.innerHTML = "";
      return;
    }
    const images = cloneImageDrafts(workspace.composeDraft.images);
    const enabled = workspace.composeDraft.imagesEnabled || images.length > 0;
    elements.composeImageBlock.classList.toggle("hidden", !enabled);
    elements.composeImageList.innerHTML = "";
    if (!enabled) {
      return;
    }
    images.forEach((image, index) => {
      const item = document.createElement("figure");
      item.className = "notices-image-item";
      item.setAttribute("role", "listitem");
      const media = document.createElement("div");
      media.className = "notices-image-media";
      const preview = document.createElement("img");
      preview.className = "notices-image-preview";
      preview.loading = "lazy";
      preview.alt = String(image.caption || image.fileName || `공지 이미지 ${index + 1}`).trim() || `공지 이미지 ${index + 1}`;
      preview.src = resolveNoticeImageUrl(image.imageSrc || "");
      media.appendChild(preview);

      const actions = document.createElement("div");
      actions.className = "notices-image-actions";
      const removeBtn = document.createElement("button");
      removeBtn.type = "button";
      removeBtn.className = "notices-inline-remove notices-inline-remove-icon";
      removeBtn.dataset.action = "notices-image-remove";
      removeBtn.dataset.noticeImageIndex = String(index);
      removeBtn.setAttribute("aria-label", "이미지 제거");
      const removeGlyph = document.createElement("span");
      removeGlyph.className = "notices-inline-remove-glyph";
      removeBtn.appendChild(removeGlyph);
      actions.appendChild(removeBtn);
      media.appendChild(actions);

      const fields = document.createElement("figcaption");
      fields.className = "notices-image-fields";
      const label = document.createElement("label");
      label.className = "input-field notices-compose-inline-input-field";
      const labelText = document.createElement("span");
      labelText.className = "sr-only";
      labelText.textContent = "캡션";
      const input = document.createElement("input");
      input.type = "text";
      input.value = String(image.caption || "");
      input.placeholder = "캡션을 입력하세요.";
      input.dataset.noticeImageIndex = String(index);
      input.dataset.noticeImageField = "caption";
      label.append(labelText, input);
      fields.append(label);

      item.append(media, fields);
      elements.composeImageList.appendChild(item);
    });
  }

  function renderPollModal(elements, workspace) {
    const draft = clonePollDraft(workspace.composePollModalDraft);
    if (elements.pollModal instanceof HTMLElement) {
      elements.pollModal.classList.toggle("hidden", !workspace.composePollModalOpen);
    }
    if (elements.pollModalBackdrop instanceof HTMLElement) {
      elements.pollModalBackdrop.classList.toggle("hidden", !workspace.composePollModalOpen);
    }
    if (!workspace.composePollModalOpen) {
      document.body.classList.remove("notices-poll-modal-open");
      return;
    }
    document.body.classList.add("notices-poll-modal-open");
    if (elements.pollModalQuestion instanceof HTMLInputElement) {
      elements.pollModalQuestion.value = draft.question;
    }
    if (elements.pollModalVisibility instanceof HTMLSelectElement) {
      elements.pollModalVisibility.value = draft.resultVisibility;
    }
    if (elements.pollModalClosesAt instanceof HTMLInputElement) {
      elements.pollModalClosesAt.value = draft.closesAt ? formatDateTimeLocalInput(draft.closesAt) : "";
    }
    if (elements.pollModalAllowChangeToggle instanceof HTMLButtonElement) {
      const active = Boolean(draft.allowChangeVote);
      elements.pollModalAllowChangeToggle.classList.toggle("is-active", active);
      elements.pollModalAllowChangeToggle.setAttribute("aria-pressed", active ? "true" : "false");
      const copy = elements.pollModalAllowChangeToggle.querySelector(".notices-switch-copy");
      if (copy instanceof HTMLElement) {
        copy.textContent = active ? "허용" : "허용 안 함";
      }
    }
    if (elements.pollModalOptionList instanceof HTMLElement) {
      elements.pollModalOptionList.innerHTML = "";
      draft.options.forEach((option, index) => {
        const item = document.createElement("li");
        item.className = "notices-poll-option-item";

        const label = document.createElement("label");
        label.className = "input-field notices-compose-inline-input-field";
        const labelText = document.createElement("span");
        labelText.className = "sr-only";
        labelText.textContent = `선택지 ${index + 1}`;
        const input = document.createElement("input");
        input.type = "text";
        input.placeholder = `선택지 ${index + 1}`;
        input.value = String(option.label || "");
        input.dataset.noticePollModalOptionIndex = String(index);
        label.append(labelText, input);
        item.appendChild(label);

        if (draft.options.length > SOC_NOTICE_MIN_POLL_OPTIONS) {
          const actions = document.createElement("div");
          actions.className = "notices-poll-option-actions";
          const removeBtn = document.createElement("button");
          removeBtn.type = "button";
          removeBtn.className = "notices-editor-action";
          removeBtn.dataset.action = "notices-poll-modal-remove-option";
          removeBtn.dataset.noticePollModalOptionIndex = String(index);
          removeBtn.textContent = "제거";
          actions.appendChild(removeBtn);
          item.appendChild(actions);
        }
        elements.pollModalOptionList.appendChild(item);
      });
    }
    if (elements.pollModalAddOptionBtn instanceof HTMLButtonElement) {
      elements.pollModalAddOptionBtn.disabled = draft.options.length >= SOC_NOTICE_MAX_POLL_OPTIONS;
    }
  }

  function renderLinkModal(elements, workspace) {
    if (elements.linkModal instanceof HTMLElement) {
      elements.linkModal.classList.toggle("hidden", !workspace.composeLinkModalOpen);
    }
    if (elements.linkModalBackdrop instanceof HTMLElement) {
      elements.linkModalBackdrop.classList.toggle("hidden", !workspace.composeLinkModalOpen);
    }
    if (elements.linkModalUrl instanceof HTMLInputElement) {
      elements.linkModalUrl.value = String(workspace.composeLinkModalUrlDraft || "");
    }
    if (elements.linkModalRemoveBtn instanceof HTMLButtonElement) {
      elements.linkModalRemoveBtn.disabled = !workspace.composeLinkModalAnchorHref;
    }
    if (workspace.composeLinkModalOpen && elements.linkModalUrl instanceof HTMLInputElement) {
      window.requestAnimationFrame(() => {
        elements.linkModalUrl.focus();
        elements.linkModalUrl.select();
      });
    }
  }

  function renderWorkspace() {
    if (!canViewSocNotices()) {
      return;
    }
    const workspace = ensureWorkspaceState();
    const elements = getWorkspaceElements();
    if (!(elements.panel instanceof HTMLElement)) {
      return;
    }

    if (elements.subtitle instanceof HTMLElement) {
      elements.subtitle.textContent = canManageSocNotices()
        ? "운영 공지를 등록하고, 중요 공지는 상단고정으로 먼저 노출할 수 있습니다."
        : "운영 공지와 안내를 카테고리, 제목, 날짜 기준으로 읽고, 공지 안 투표에는 바로 참여할 수 있습니다.";
    }
    if (elements.readonlyPill instanceof HTMLElement) {
      elements.readonlyPill.classList.toggle("hidden", canManageSocNotices());
    }
    if (elements.createBtn instanceof HTMLElement) {
      elements.createBtn.classList.toggle("hidden", !canManageSocNotices());
    }

    renderCategoryTabs(elements, workspace);
    renderSearchControls(elements, workspace);
    renderListPanel(elements, workspace);
    renderDetailPanel(elements, workspace);
    renderComposeSettings(elements, workspace);
    renderTablePicker(elements, workspace);
    renderComposeFormatControls(elements, workspace);
    renderComposeDocument(elements, workspace);
    renderImageList(elements, workspace);
    renderPollModal(elements, workspace);
    renderLinkModal(elements, workspace);

    if (elements.listPanel instanceof HTMLElement) {
      elements.listPanel.classList.toggle("hidden", workspace.mode !== SOC_NOTICE_VIEW_MODE_LIST);
    }
    if (elements.detailPanel instanceof HTMLElement) {
      elements.detailPanel.classList.toggle("hidden", workspace.mode !== SOC_NOTICE_VIEW_MODE_DETAIL);
    }
    if (elements.composePanel instanceof HTMLElement) {
      elements.composePanel.classList.toggle("hidden", workspace.mode !== SOC_NOTICE_VIEW_MODE_COMPOSE || !canManageSocNotices());
    }
    if (workspace.mode !== SOC_NOTICE_VIEW_MODE_COMPOSE) {
      clearComposeFormatMenuState();
      renderComposeFormatControls(elements, workspace);
    }
  }

  function formatDateTimeLocalInput(rawValue = "") {
    const text = String(rawValue || "").trim();
    if (!text) {
      return "";
    }
    const parsed = new Date(text);
    if (Number.isNaN(parsed.getTime())) {
      return "";
    }
    const offset = parsed.getTimezoneOffset() * 60 * 1000;
    return new Date(parsed.getTime() - offset).toISOString().slice(0, 16);
  }

  function applyDraftToComposeFields() {
    const elements = getWorkspaceElements();
    const workspace = ensureWorkspaceState();
    renderComposeSettings(elements, workspace);
    renderComposeFormatControls(elements, workspace);
    renderComposeDocument(elements, workspace);
    renderImageList(elements, workspace);
  }

  function buildAnnouncementHash(options = {}) {
    const workspace = ensureWorkspaceState();
    const mode = normalizeNoticeMode(options.mode || workspace.mode, canManageSocNotices());
    const noticeId = String((options.noticeId ?? workspace.selectedNoticeId) || "").trim();
    const category = normalizeNoticeCategory((options.category ?? workspace.category) || "all");
    const search = normalizeNoticeSearch((options.search ?? workspace.search) || "");
    const params = new URLSearchParams();
    if (category !== "all") {
      params.set("category", category);
    }
    if (search) {
      params.set("q", search);
    }
    if (mode === SOC_NOTICE_VIEW_MODE_COMPOSE && canManageSocNotices()) {
      params.set("mode", noticeId ? "edit" : "new");
      if (noticeId) {
        params.set("notice", noticeId);
      }
    } else if (noticeId) {
      params.set("notice", noticeId);
    }
    const query = params.toString();
    return query ? `#/feature/notices?${query}` : "#/feature/notices";
  }

  function writeHash(nextHash = "", historyMode = "replace") {
    try {
      const url = new URL(window.location.href);
      const currentHash = String(url.hash || "").trim();
      if (currentHash === nextHash) {
        if (historyMode === "replace") {
          window.history.replaceState({}, "", `${url.pathname}${url.search}${currentHash}`);
        }
        return true;
      }
      url.hash = nextHash.replace(/^#/, "");
      const nextUrl = `${url.pathname}${url.search}${url.hash}`;
      if (historyMode === "push") {
        window.history.pushState({}, "", nextUrl);
      } else {
        window.history.replaceState({}, "", nextUrl);
      }
      return true;
    } catch {
      return false;
    }
  }

  async function loadWorkspaceRouteState() {
    const workspace = ensureWorkspaceState();
    workspace.error = "";
    if (workspace.mode === SOC_NOTICE_VIEW_MODE_DETAIL && workspace.selectedNoticeId) {
      const cachedRow = (Array.isArray(workspace.rows) ? workspace.rows : []).find((row) => String(row?.id || "").trim() === workspace.selectedNoticeId) || null;
      if (cachedRow) {
        workspace.selectedRow = cachedRow;
      }
      workspace.detailLoading = true;
      renderWorkspace();
      try {
        workspace.selectedRow = await fetchNoticeDetailRow(workspace.selectedNoticeId);
      } catch (error) {
        workspace.selectedRow = null;
        workspace.error = String(error?.message || "").trim() || "공지 상세를 불러오지 못했습니다.";
      } finally {
        workspace.detailLoading = false;
        renderWorkspace();
      }
      return true;
    }
    if (workspace.mode === SOC_NOTICE_VIEW_MODE_COMPOSE) {
      if (!canManageSocNotices()) {
        workspace.mode = workspace.selectedNoticeId ? SOC_NOTICE_VIEW_MODE_DETAIL : SOC_NOTICE_VIEW_MODE_LIST;
        renderWorkspace();
        return loadWorkspaceRouteState();
      }
      if (workspace.selectedNoticeId) {
        const cachedRow = workspace.selectedRow && String(workspace.selectedRow?.id || "").trim() === workspace.selectedNoticeId
          ? workspace.selectedRow
          : ((Array.isArray(workspace.rows) ? workspace.rows : []).find((row) => String(row?.id || "").trim() === workspace.selectedNoticeId) || null);
        if (cachedRow) {
          workspace.selectedRow = cachedRow;
          workspace.composeEditingId = String(cachedRow?.id || "").trim();
          workspace.composeDraft = normalizeDraftFromRow(cachedRow);
          resetComposeDraftMeta();
          restoreSavedComposeDraft({
            noticeId: workspace.composeEditingId,
            fallbackCategory: cachedRow?.category || workspace.category || "ops",
          });
          renderWorkspace();
          workspace.detailLoading = true;
          void fetchNoticeDetailRow(workspace.selectedNoticeId)
            .then((row) => {
              if (!row || String(row?.id || "").trim() !== workspace.composeEditingId) {
                return;
              }
              workspace.selectedRow = row;
              if (!workspace.composeDirtySinceLoad) {
                workspace.composeDraft = normalizeDraftFromRow(row);
                resetComposeDraftMeta();
                restoreSavedComposeDraft({
                  noticeId: workspace.composeEditingId,
                  fallbackCategory: row?.category || workspace.category || "ops",
                });
              }
            })
            .catch((error) => {
              workspace.error = String(error?.message || "").trim() || "공지 상세를 불러오지 못했습니다.";
            })
            .finally(() => {
              workspace.detailLoading = false;
              renderWorkspace();
            });
        } else {
          workspace.detailLoading = true;
          renderWorkspace();
          try {
            const row = await fetchNoticeDetailRow(workspace.selectedNoticeId);
            workspace.selectedRow = row;
            workspace.composeEditingId = String(row?.id || "").trim();
            workspace.composeDraft = normalizeDraftFromRow(row);
            resetComposeDraftMeta();
            restoreSavedComposeDraft({
              noticeId: workspace.composeEditingId,
              fallbackCategory: row?.category || workspace.category || "ops",
            });
          } catch (error) {
            workspace.error = String(error?.message || "").trim() || "공지 상세를 불러오지 못했습니다.";
          } finally {
            workspace.detailLoading = false;
            renderWorkspace();
          }
        }
      } else {
        workspace.selectedRow = null;
        if (!workspace.composeDirtySinceLoad) {
          workspace.composeEditingId = "";
          workspace.composeDraft = createDefaultComposeDraft(workspace.category === "all" ? "ops" : workspace.category);
          resetComposeDraftMeta();
          restoreSavedComposeDraft({
            noticeId: "",
            fallbackCategory: workspace.category === "all" ? "ops" : workspace.category || "ops",
          });
        } else {
          workspace.composeEditingId = "";
        }
        renderWorkspace();
      }
      return true;
    }
    seedWorkspaceRowsFromCompat(workspace);
    workspace.loading = false;
    renderWorkspace();
    try {
      const rows = await fetchNoticeRows(workspace);
      workspace.rows = rows;
      if (workspace.selectedNoticeId) {
        workspace.selectedRow = rows.find((row) => String(row?.id || "").trim() === workspace.selectedNoticeId) || null;
      } else {
        workspace.selectedRow = null;
      }
      setCompatAnnouncements(rows);
    } catch (error) {
      workspace.rows = [];
      workspace.error = String(error?.message || "").trim() || "공지 목록을 불러오지 못했습니다.";
      setCompatAnnouncements([]);
    } finally {
      workspace.loading = false;
      if (typeof markNotificationSyncNow === "function") {
        markNotificationSyncNow();
      }
      renderWorkspace();
    }
    return true;
  }

  function syncAnnouncementRouteState(options = {}) {
    const workspace = ensureWorkspaceState();
    const composeRequested = Object.prototype.hasOwnProperty.call(options, "compose")
      ? Boolean(options.compose)
      : workspace.mode === SOC_NOTICE_VIEW_MODE_COMPOSE;
    const nextMode = composeRequested
      ? SOC_NOTICE_VIEW_MODE_COMPOSE
      : (String((options.noticeId ?? workspace.selectedNoticeId) || "").trim() ? SOC_NOTICE_VIEW_MODE_DETAIL : SOC_NOTICE_VIEW_MODE_LIST);
    return writeHash(
      buildAnnouncementHash({
        mode: options.mode || nextMode,
        noticeId: Object.prototype.hasOwnProperty.call(options, "noticeId")
          ? options.noticeId
          : workspace.selectedNoticeId,
        category: options.category ?? workspace.category,
        search: options.search ?? workspace.search,
      }),
      String(options.historyMode || "replace").trim() === "push" ? "push" : "replace",
    );
  }

  async function openAnnouncementsTab(options = {}) {
    return openAnnouncementsPage(options);
  }

  async function openAnnouncementsPage(options = {}) {
    if (!canViewSocNotices()) {
      return false;
    }
    const workspace = ensureWorkspaceState();
    const panel = document.getElementById("announcementPanel");
    const adapter = window.__RG_ARLS_ANNOUNCEMENTS_ADAPTER__;
    if (adapter && typeof adapter.openRoute === "function") {
      adapter.openRoute();
    } else if (typeof closeNavMenu === "function") {
      closeNavMenu();
    }
    if (adapter && typeof adapter.ensurePanelVisible === "function") {
      adapter.ensurePanelVisible(panel);
    } else if (typeof setAdminTab === "function") {
      if (rootState.adminTab !== "announcement") {
        setAdminTab("announcement", { preserveAnnouncementView: true });
      } else if (panel && typeof ensureOnlyOneAdminPanelVisible === "function") {
        ensureOnlyOneAdminPanelVisible(panel);
      }
    }
    workspace.category = normalizeNoticeCategory((options.category ?? workspace.category) || "all");
    workspace.search = normalizeNoticeSearch((options.search ?? workspace.search) || "");
    workspace.searchDraft = workspace.search;
    workspace.searchExpanded = Boolean(workspace.search);
    if (Object.prototype.hasOwnProperty.call(options, "noticeId")) {
      workspace.selectedNoticeId = String(options.noticeId || "").trim();
    }
    if (Object.prototype.hasOwnProperty.call(options, "compose")) {
      workspace.mode = options.compose
        ? SOC_NOTICE_VIEW_MODE_COMPOSE
        : (workspace.selectedNoticeId ? SOC_NOTICE_VIEW_MODE_DETAIL : SOC_NOTICE_VIEW_MODE_LIST);
    } else if (options.mode) {
      workspace.mode = normalizeNoticeMode(options.mode, canManageSocNotices());
    } else if (!workspace.selectedNoticeId && workspace.mode === SOC_NOTICE_VIEW_MODE_DETAIL) {
      workspace.mode = SOC_NOTICE_VIEW_MODE_LIST;
    }
    if (workspace.mode !== SOC_NOTICE_VIEW_MODE_COMPOSE) {
      workspace.composeTablePickerOpen = false;
      workspace.composePollModalOpen = false;
      clearComposeLinkModalState();
      clearComposeFormatMenuState();
    }
    if (options.syncRoute !== false) {
      syncAnnouncementRouteState({
        historyMode: options.historyMode || "push",
        category: workspace.category,
        search: workspace.search,
        noticeId: workspace.selectedNoticeId,
        mode: workspace.mode,
      });
    }
    return loadWorkspaceRouteState();
  }

  async function applyAnnouncementRouteState() {
    if (!canViewSocNotices()) {
      return false;
    }
    const workspace = ensureWorkspaceState();
    const routeState = parseAnnouncementHashState(window.location.hash);
    workspace.category = normalizeNoticeCategory(routeState?.category || "all");
    workspace.search = normalizeNoticeSearch(routeState?.search || "");
    workspace.searchDraft = workspace.search;
    workspace.searchExpanded = Boolean(workspace.search);
    workspace.selectedNoticeId = String(routeState?.noticeId || "").trim();
    workspace.mode = routeState?.mode || (workspace.selectedNoticeId ? SOC_NOTICE_VIEW_MODE_DETAIL : SOC_NOTICE_VIEW_MODE_LIST);
    workspace.composeTablePickerOpen = false;
    workspace.composePollModalOpen = false;
    clearComposeLinkModalState();
    clearComposeFormatMenuState();

    const panel = document.getElementById("announcementPanel");
    const adapter = window.__RG_ARLS_ANNOUNCEMENTS_ADAPTER__;
    if (adapter && typeof adapter.ensurePanelVisible === "function") {
      adapter.ensurePanelVisible(panel);
    } else if (typeof setAdminTab === "function") {
      if (rootState.adminTab !== "announcement") {
        setAdminTab("announcement", { preserveAnnouncementView: true });
      } else if (panel && typeof ensureOnlyOneAdminPanelVisible === "function") {
        ensureOnlyOneAdminPanelVisible(panel);
      }
    }
    return loadWorkspaceRouteState();
  }

  function openAnnouncementComposerModal(options = {}) {
    const workspace = ensureWorkspaceState();
    workspace.mode = SOC_NOTICE_VIEW_MODE_COMPOSE;
    workspace.selectedNoticeId = "";
    workspace.selectedRow = null;
    workspace.composeEditingId = "";
    workspace.composeDraft = createDefaultComposeDraft(workspace.category === "all" ? "ops" : workspace.category);
    clearComposeAutosaveTimer();
    clearComposeDraftStorage({ noticeId: "" });
    resetComposeDraftMeta();
    workspace.composeTablePickerOpen = false;
    workspace.composePollModalOpen = false;
    clearComposeLinkModalState();
    clearComposeFormatMenuState();
    renderWorkspace();
    if (options.syncRoute !== false) {
      syncAnnouncementRouteState({
        historyMode: options.historyMode || "push",
        mode: SOC_NOTICE_VIEW_MODE_COMPOSE,
        noticeId: "",
      });
    }
    return true;
  }

  function closeAnnouncementComposerModal(options = {}) {
    const workspace = ensureWorkspaceState();
    if (workspace.mode === SOC_NOTICE_VIEW_MODE_COMPOSE) {
      workspace.mode = workspace.selectedNoticeId ? SOC_NOTICE_VIEW_MODE_DETAIL : SOC_NOTICE_VIEW_MODE_LIST;
    }
    workspace.composeTablePickerOpen = false;
    workspace.composePollModalOpen = false;
    clearComposeLinkModalState();
    clearComposeFormatMenuState();
    renderWorkspace();
    if (options.syncRoute) {
      syncAnnouncementRouteState({
        historyMode: options.historyMode || "replace",
      });
    }
  }

  function refreshAnnouncementPanelMode() {
    renderWorkspace();
  }

  async function loadAnnouncements() {
    const workspace = ensureWorkspaceState();
    return loadWorkspaceRouteState({
      mode: workspace.mode,
    });
  }

  function renderAnnouncements() {
    renderWorkspace();
  }

  async function deleteAnnouncementById(announcementIdRaw) {
    const noticeId = String(announcementIdRaw || "").trim();
    if (!noticeId) {
      return false;
    }
    const workspace = ensureWorkspaceState();
    const title = String(workspace.selectedRow?.title || "").trim() || "선택 공지";
    const confirmed = await socConfirm(`"${title}" 공지를 삭제하시겠습니까?`);
    if (!confirmed) {
      return false;
    }
    await deleteNoticeRecord(noticeId);
    socToast("공지를 삭제했습니다.", "success", 1800);
    clearComposeAutosaveTimer();
    clearComposeDraftStorage({ noticeId });
    resetComposeDraftMeta();
    workspace.selectedNoticeId = "";
    workspace.selectedRow = null;
    workspace.mode = SOC_NOTICE_VIEW_MODE_LIST;
    workspace.composeEditingId = "";
    syncAnnouncementRouteState({
      historyMode: "replace",
      noticeId: "",
      mode: SOC_NOTICE_VIEW_MODE_LIST,
    });
    return loadWorkspaceRouteState();
  }

  function notifyRichEditorMutation(editorEl) {
    if (!(editorEl instanceof HTMLElement)) {
      return;
    }
    editorEl.dispatchEvent(new Event("input", { bubbles: true }));
    editorEl.focus();
    captureComposeRichSelection();
  }

  function applyInlineTagFormat(tagName = "") {
    const normalizedTag = String(tagName || "").trim().toLowerCase();
    if (!["strong", "em", "u"].includes(normalizedTag)) {
      return false;
    }
    restoreComposeRichSelection();
    const applied = wrapRichSelection(() => document.createElement(normalizedTag));
    if (!applied) {
      socToast("서식을 적용할 텍스트를 먼저 선택해 주세요.", "info", 2200);
      return false;
    }
    const editorEl = getActiveRichEditorElement();
    notifyRichEditorMutation(editorEl);
    return true;
  }

  function applyInlineSpanToken(attrName = "", token = "") {
    const normalizedAttr = String(attrName || "").trim();
    const normalizedToken = String(token || "").trim().toLowerCase();
    const allowedValues = normalizedAttr === "data-rt-size"
      ? SOC_NOTICE_RICH_FONT_SIZE_OPTIONS
      : (normalizedAttr === "data-rt-color" ? SOC_NOTICE_RICH_TEXT_COLOR_OPTIONS : SOC_NOTICE_RICH_BG_OPTIONS);
    if (!normalizedAttr || !allowedValues.includes(normalizedToken)) {
      return false;
    }
    restoreComposeRichSelection();
    const applied = wrapRichSelection(() => {
      const el = normalizedAttr === "data-rt-bg" ? document.createElement("mark") : document.createElement("span");
      el.setAttribute(normalizedAttr, normalizedToken);
      return el;
    });
    if (!applied) {
      socToast("서식을 적용할 텍스트를 먼저 선택해 주세요.", "info", 2200);
      return false;
    }
    const editorEl = getActiveRichEditorElement();
    notifyRichEditorMutation(editorEl);
    return true;
  }

  function applyRichAlignment(align = "left") {
    const editorEl = restoreComposeRichSelection() || getActiveRichEditorElement();
    if (!(editorEl instanceof HTMLElement)) {
      socToast("정렬할 문단이나 셀을 먼저 선택해 주세요.", "info", 2200);
      return false;
    }
    setRichEditorPresentation(editorEl, align);
    notifyRichEditorMutation(editorEl);
    return true;
  }

  function findSelectedAnchorElement() {
    const selection = window.getSelection();
    if (!selection || !selection.rangeCount) {
      return null;
    }
    const editorEl = getClosestRichEditorElement(selection.anchorNode);
    if (!(editorEl instanceof HTMLElement)) {
      return null;
    }
    const anchorNode = selection.anchorNode instanceof HTMLElement
      ? selection.anchorNode
      : selection.anchorNode?.parentElement;
    return anchorNode instanceof HTMLElement ? anchorNode.closest("a") : null;
  }

  function unwrapLinkElement(anchorEl) {
    if (!(anchorEl instanceof HTMLElement) || anchorEl.tagName.toLowerCase() !== "a") {
      return false;
    }
    const parent = anchorEl.parentNode;
    if (!parent) {
      return false;
    }
    while (anchorEl.firstChild) {
      parent.insertBefore(anchorEl.firstChild, anchorEl);
    }
    parent.removeChild(anchorEl);
    return true;
  }

  function openLinkModal() {
    const activeSelection = getSelectionRangeInRichEditor({ requireExpanded: true });
    const existingAnchor = findSelectedAnchorElement();
    if (!activeSelection && !existingAnchor) {
      socToast("링크를 걸 텍스트를 먼저 선택해 주세요.", "info", 2200);
      return false;
    }
    if (!captureLinkModalSnapshot()) {
      socToast("링크 대상을 준비하지 못했습니다.", "error", 2200);
      return false;
    }
    const workspace = ensureWorkspaceState();
    workspace.composeLinkModalUrlDraft = String(existingAnchor?.getAttribute("href") || "").trim() || "https://";
    workspace.composeLinkModalOpen = true;
    renderLinkModal(getWorkspaceElements(), workspace);
    return true;
  }

  function closeLinkModal({ restoreFocus = true } = {}) {
    const workspace = ensureWorkspaceState();
    const editorEl = restoreFocus ? resolveEditorFromDescriptor(workspace.composeLinkModalEditorDescriptor) : null;
    clearComposeLinkModalState();
    renderLinkModal(getWorkspaceElements(), workspace);
    if (restoreFocus && editorEl instanceof HTMLElement) {
      editorEl.focus();
    }
  }

  function applyLinkModal() {
    const workspace = ensureWorkspaceState();
    const elements = getWorkspaceElements();
    workspace.composeLinkModalUrlDraft = String(elements.linkModalUrl instanceof HTMLInputElement ? elements.linkModalUrl.value : workspace.composeLinkModalUrlDraft || "").trim();
    const url = String(workspace.composeLinkModalUrlDraft || "").trim();
    if (!url) {
      return removeLinkModalLink();
    }
    const { editorEl, anchorEl } = restoreLinkModalContext();
    if (anchorEl instanceof HTMLElement) {
      anchorEl.setAttribute("href", url);
      notifyRichEditorMutation(editorEl);
      closeLinkModal({ restoreFocus: false });
      return true;
    }
    const applied = wrapRichSelection(() => {
      const anchor = document.createElement("a");
      anchor.setAttribute("href", url);
      return anchor;
    });
    if (!applied) {
      socToast("링크를 걸 텍스트를 먼저 선택해 주세요.", "info", 2200);
      return false;
    }
    notifyRichEditorMutation(editorEl || getActiveRichEditorElement());
    closeLinkModal({ restoreFocus: false });
    return true;
  }

  function removeLinkModalLink() {
    const { editorEl, anchorEl } = restoreLinkModalContext();
    if (!(anchorEl instanceof HTMLElement) || !unwrapLinkElement(anchorEl)) {
      socToast("해제할 링크를 찾지 못했습니다.", "info", 2200);
      return false;
    }
    notifyRichEditorMutation(editorEl || getActiveRichEditorElement());
    closeLinkModal({ restoreFocus: false });
    return true;
  }

  function updateComposeDraft(partial = {}) {
    const workspace = ensureWorkspaceState();
    workspace.composeDraft = {
      ...(workspace.composeDraft || createDefaultComposeDraft(workspace.category === "all" ? "ops" : workspace.category)),
      ...partial,
    };
    markComposeDraftDirty();
  }

  function insertBodySnippet(snippet = "", caretOffset = 0) {
    const activeRichEditor = document.activeElement instanceof HTMLElement && document.activeElement.dataset.noticeRichEditor === "true"
      ? document.activeElement
      : (document.getElementById("noticesComposeBody") instanceof HTMLElement ? document.getElementById("noticesComposeBody") : null);
    if (activeRichEditor instanceof HTMLElement) {
      restoreComposeRichSelection();
      if (insertPlainTextAtSelection(snippet)) {
        notifyRichEditorMutation(activeRichEditor);
        return true;
      }
    }
    const bodyInput = (
      document.activeElement instanceof HTMLTextAreaElement
      && document.activeElement.dataset.noticeComposeParagraphInput === "true"
    )
      ? document.activeElement
      : document.getElementById("noticesComposeBody");
    if (!(bodyInput instanceof HTMLTextAreaElement)) {
      return false;
    }
    const start = bodyInput.selectionStart || 0;
    const end = bodyInput.selectionEnd || 0;
    const nextValue = `${bodyInput.value.slice(0, start)}${snippet}${bodyInput.value.slice(end)}`;
    bodyInput.value = nextValue;
    const caret = start + Math.max(0, Number(caretOffset) || 0);
    bodyInput.selectionStart = caret;
    bodyInput.selectionEnd = caret;
    resizeComposeParagraphInput(bodyInput);
    const blockId = String(bodyInput.dataset.noticeComposeBlockId || "").trim();
    const blocks = getComposeContentBlocks(ensureWorkspaceState().composeDraft).map((block) => {
      if (block.kind !== "paragraph" || String(block.id || "").trim() !== blockId) {
        return block;
      }
      return {
        id: block.id,
        kind: "paragraph",
        text: nextValue,
      };
    });
    setComposeContentBlocks(blocks, { markDirty: true, rerender: false });
    bodyInput.focus();
    return true;
  }

  function setTablePreset(rowsRaw = 2, colsRaw = 2) {
    const rows = Math.max(1, Math.min(20, Number(rowsRaw) || 2));
    const cols = Math.max(1, Math.min(6, Number(colsRaw) || 2));
    const workspace = ensureWorkspaceState();
    if (usesStructuredNoticeDocumentModel(workspace.composeDraft?.bodyModel)) {
      syncFloatingComposeDraftFromDom({ markDirty: false });
    }
    const nextTable = {
      enabled: true,
      title: String(workspace.composeDraft.table?.title || "").trim(),
      hasHeader: true,
      columns: Array.from({ length: cols }, (_, index) => `항목 ${index + 1}`),
      rows: Array.from({ length: rows }, () => Array.from({ length: cols }, () => "")),
    };
    workspace.composeTablePickerOpen = false;
    if (usesStructuredNoticeDocumentModel(workspace.composeDraft?.bodyModel)) {
      const objectId = insertFloatingObject({
        id: createNoticeBlockId("table"),
        kind: "table",
        flow_index: (sortFloatingDocumentInPlace(workspace.composeDraft?.bodyDocument || createDefaultFlowLaneDocument()).objects || []).length
          + (sortFloatingDocumentInPlace(workspace.composeDraft?.bodyDocument || createDefaultFlowLaneDocument()).paragraphs || []).length,
        flowIndex: (sortFloatingDocumentInPlace(workspace.composeDraft?.bodyDocument || createDefaultFlowLaneDocument()).objects || []).length
          + (sortFloatingDocumentInPlace(workspace.composeDraft?.bodyDocument || createDefaultFlowLaneDocument()).paragraphs || []).length,
        z_index: 10,
        zIndex: 10,
        frame: createFloatingObjectFrame({ x: 0, y: 0, width: 640, height: 220 }),
        table: cloneTableDraft(nextTable),
      });
      window.requestAnimationFrame(() => {
        const firstCell = document.querySelector(`[data-notice-table-block-id="${objectId}"][data-notice-table-field="header"][data-notice-table-col="0"], [data-notice-table-block-id="${objectId}"][data-notice-table-field="cell"][data-notice-table-row="0"][data-notice-table-col="0"]`);
        if (firstCell instanceof HTMLElement) {
          firstCell.focus({ preventScroll: false });
        }
      });
      return;
    }
    renderWorkspace();
    const blockId = insertComposeFlowBlock({
      id: createNoticeBlockId("table"),
      kind: "table",
      table: cloneTableDraft(nextTable),
    });
    workspace.composeDraft = {
      ...(workspace.composeDraft || {}),
      table: cloneTableDraft(nextTable),
    };
    window.requestAnimationFrame(() => {
      const firstCell = document.querySelector(`[data-notice-table-block-id="${blockId}"][data-notice-table-field="header"][data-notice-table-col="0"], [data-notice-table-block-id="${blockId}"][data-notice-table-field="cell"][data-notice-table-row="0"][data-notice-table-col="0"]`);
      if (firstCell instanceof HTMLElement) {
        firstCell.focus({ preventScroll: false });
      }
    });
  }

  function openPollModal(triggerEl = null) {
    const workspace = ensureWorkspaceState();
    workspace.composePollModalOpen = true;
    workspace.composePollModalTriggerEl = triggerEl instanceof HTMLElement ? triggerEl : null;
    workspace.composePollModalBlockId = String(triggerEl?.dataset?.noticePollBlockId || triggerEl?.dataset?.noticeFloatingObjectId || "").trim();
    const currentPollBlock = workspace.composePollModalBlockId
      ? (
        isFloatingNoticeModel(workspace.composeDraft?.bodyModel)
          || isFlowLaneNoticeModel(workspace.composeDraft?.bodyModel)
          ? getFloatingDocumentObjectById(workspace.composeDraft?.bodyDocument, workspace.composePollModalBlockId)
          : getComposeContentBlocks(workspace.composeDraft).find((block) => block.kind === "poll" && String(block.id || "").trim() === workspace.composePollModalBlockId)
      )
      : null;
    workspace.composePollModalDraft = clonePollDraft((currentPollBlock && (currentPollBlock.poll || currentPollBlock)) || workspace.composeDraft.poll);
    renderWorkspace();
    const questionInput = document.getElementById("noticesComposePollModalQuestion");
    if (questionInput instanceof HTMLInputElement) {
      window.requestAnimationFrame(() => questionInput.focus());
    }
  }

  function closePollModal() {
    const workspace = ensureWorkspaceState();
    workspace.composePollModalOpen = false;
    workspace.composePollModalBlockId = "";
    workspace.composePollModalTriggerEl = null;
    renderWorkspace();
  }

  function savePollModal() {
    const workspace = ensureWorkspaceState();
    if (usesStructuredNoticeDocumentModel(workspace.composeDraft?.bodyModel)) {
      syncFloatingComposeDraftFromDom({ markDirty: false });
    }
    const draft = clonePollDraft(workspace.composePollModalDraft);
    const question = String(draft.question || "").trim();
    const options = draft.options
      .map((option) => ({
        optionId: String(option.optionId || "").trim() || createNoticeBlockId("poll-option"),
        label: String(option.label || "").trim(),
      }))
      .filter((option) => option.label);
    if (!question) {
      socToast("투표 질문을 입력해 주세요.", "error", 2200);
      return;
    }
    if (options.length < SOC_NOTICE_MIN_POLL_OPTIONS) {
      socToast("선택지는 최소 2개 이상 입력해 주세요.", "error", 2200);
      return;
    }
    const nextPoll = {
      ...draft,
      enabled: true,
      question,
      options,
    };
    const existingBlockId = String(workspace.composePollModalBlockId || "").trim();
    if (usesStructuredNoticeDocumentModel(workspace.composeDraft?.bodyModel)) {
      if (existingBlockId && getFloatingDocumentObjectById(workspace.composeDraft?.bodyDocument, existingBlockId)) {
        updateFloatingPollObject(existingBlockId, () => nextPoll);
      } else {
        insertFloatingObject({
          id: createNoticeBlockId("poll"),
          kind: "poll",
          flow_index: (sortFloatingDocumentInPlace(workspace.composeDraft?.bodyDocument || createDefaultFlowLaneDocument()).objects || []).length
            + (sortFloatingDocumentInPlace(workspace.composeDraft?.bodyDocument || createDefaultFlowLaneDocument()).paragraphs || []).length,
          flowIndex: (sortFloatingDocumentInPlace(workspace.composeDraft?.bodyDocument || createDefaultFlowLaneDocument()).objects || []).length
            + (sortFloatingDocumentInPlace(workspace.composeDraft?.bodyDocument || createDefaultFlowLaneDocument()).paragraphs || []).length,
          z_index: 11,
          zIndex: 11,
          frame: createFloatingObjectFrame({ x: 0, y: 0, width: 640, height: 220 }),
          poll: clonePollDraft(nextPoll),
        });
      }
    } else {
      if (existingBlockId && getComposePollBlockIndex(existingBlockId, workspace.composeDraft) !== -1) {
        updateComposePollBlock(existingBlockId, () => nextPoll, { markDirty: true, rerender: true });
      } else {
        insertComposeFlowBlock({
          id: createNoticeBlockId("poll"),
          kind: "poll",
          poll: clonePollDraft(nextPoll),
        });
      }
    }
    workspace.composeDraft = {
      ...(workspace.composeDraft || {}),
      poll: clonePollDraft(nextPoll),
    };
    closePollModal();
  }

  async function appendImages(files = [], options = {}) {
    const workspace = ensureWorkspaceState();
    if (usesStructuredNoticeDocumentModel(workspace.composeDraft?.bodyModel)) {
      syncFloatingComposeDraftFromDom({ markDirty: false });
    }
    const fileRows = Array.from(files).filter((file) => file instanceof File);
    if (!fileRows.length) {
      return;
    }
    const existingCount = usesStructuredNoticeDocumentModel(workspace.composeDraft?.bodyModel)
      ? (normalizeFloatingDocumentDraft(workspace.composeDraft?.bodyDocument, "").objects || []).filter((item) => String(item.kind || "").trim() === "image").length
      : cloneImageDrafts(workspace.composeDraft.images).length;
    if (existingCount >= SOC_NOTICE_MAX_IMAGES) {
      socToast(`이미지는 최대 ${SOC_NOTICE_MAX_IMAGES}장까지 첨부할 수 있습니다.`, "info", 2200);
      return;
    }
    const available = fileRows.slice(0, Math.max(0, SOC_NOTICE_MAX_IMAGES - existingCount));
    const readResults = await Promise.all(available.map((file) => new Promise((resolve, reject) => {
      if (!String(file.type || "").startsWith("image/")) {
        reject(new Error("이미지 파일만 첨부할 수 있습니다."));
        return;
      }
      const reader = new FileReader();
      reader.onload = () => resolve({
        attachmentId: "",
        fileName: file.name || "notice-image.png",
        caption: "",
        imageSrc: String(reader.result || ""),
      });
      reader.onerror = () => reject(new Error("이미지를 읽지 못했습니다."));
      reader.readAsDataURL(file);
    })));
    if (usesStructuredNoticeDocumentModel(workspace.composeDraft?.bodyModel)) {
      const baseIndex = getFloatingDocumentItems(workspace.composeDraft?.bodyDocument).length;
      readResults.filter(Boolean).forEach((image, index) => {
        const insertionPoint = options.insertionPoint && typeof options.insertionPoint === "object"
          ? options.insertionPoint
          : null;
        const frame = isFlowLaneNoticeModel(workspace.composeDraft?.bodyModel)
          ? createFloatingObjectFrame({
            x: insertionPoint ? Math.max(0, Math.round(insertionPoint.x || 0)) : 0,
            y: 0,
            width: 420,
            height: 320,
          })
          : insertionPoint
          ? createFloatingObjectFrame({
            x: insertionPoint.x,
            y: insertionPoint.y,
            width: 320,
            height: 240,
          })
          : createDefaultFloatingObjectOrigin("image");
        insertFloatingObject({
          id: createNoticeBlockId("image"),
          kind: "image",
          flow_index: baseIndex + index,
          flowIndex: baseIndex + index,
          z_index: 20 + index,
          zIndex: 20 + index,
          frame,
          attachment_id: "",
          attachmentId: "",
          file_name: image.fileName || "notice-image.png",
          fileName: image.fileName || "notice-image.png",
          caption: image.caption || null,
          image_src: image.imageSrc,
          imageSrc: image.imageSrc,
        });
      });
    } else {
      const existing = cloneImageDrafts(workspace.composeDraft.images);
      updateComposeDraft({
        imagesEnabled: true,
        images: [...existing, ...readResults.filter(Boolean)],
      });
      renderWorkspace();
    }
    const input = document.getElementById("noticesComposeImageInput");
    if (input instanceof HTMLInputElement) {
      input.value = "";
    }
  }

  function syncDraftFieldInput(event) {
    const target = event.target instanceof HTMLElement ? event.target : null;
    if (!target) {
      return;
    }
    const workspace = ensureWorkspaceState();
    if (target.id === "noticesComposeTitle" && target instanceof HTMLInputElement) {
      updateComposeDraft({ title: target.value });
      return;
    }
    if (target.id === "noticesComposeLinkUrl" && target instanceof HTMLInputElement) {
      workspace.composeLinkModalUrlDraft = target.value;
      return;
    }
    if (target.id === "noticesComposeFontSizeInput" && target instanceof HTMLInputElement) {
      workspace.composeFontSizeDraft = target.value;
      return;
    }
    if (target instanceof HTMLElement && target.dataset.noticeRichEditor === "true") {
      const payload = readRichEditorPayload(target);
      if (target.dataset.noticeComposeEditorKind === "paragraph") {
        const paragraphId = String(target.dataset.noticeFloatingParagraphId || target.dataset.noticeComposeBlockId || "").trim();
        if (usesStructuredNoticeDocumentModel(workspace.composeDraft?.bodyModel)) {
          syncFloatingComposeDraftFromDom({ markDirty: true });
        } else {
          const blocks = getComposeContentBlocks(workspace.composeDraft).map((block) => {
            if (block.kind !== "paragraph" || String(block.id || "").trim() !== paragraphId) {
              return block;
            }
            return {
              ...block,
              text: payload.text,
              richText: payload.richText,
              align: payload.align,
            };
          });
          setComposeContentBlocks(blocks, { markDirty: true, rerender: false, preserveExistingRich: false });
        }
        captureComposeRichSelection();
        return;
      }
      if (target.dataset.noticeTableField) {
        const blockId = String(target.dataset.noticeTableBlockId || "").trim();
        const table = usesStructuredNoticeDocumentModel(workspace.composeDraft?.bodyModel)
          ? cloneTableDraft(getFloatingDocumentObjectById(workspace.composeDraft?.bodyDocument, blockId)?.table)
          : cloneTableDraft(
            getComposeContentBlocks(workspace.composeDraft).find((block) => block.kind === "table" && String(block.id || "").trim() === blockId)?.table
          );
        const colIndex = Math.max(0, Number(target.dataset.noticeTableCol || 0) || 0);
        if (target.dataset.noticeTableField === "header") {
          table.columns[colIndex] = payload.text;
          table.columnsRich[colIndex] = payload;
        } else {
          const rowIndex = Math.max(0, Number(target.dataset.noticeTableRow || 0) || 0);
          if (!Array.isArray(table.rows[rowIndex])) {
            table.rows[rowIndex] = Array.from({ length: table.columns.length }, () => "");
          }
          if (!Array.isArray(table.rowsRich[rowIndex])) {
            table.rowsRich[rowIndex] = Array.from({ length: table.columns.length }, (_, index) => createDefaultRichCell(table.rows[rowIndex][index] || ""));
          }
          table.rows[rowIndex][colIndex] = payload.text;
          table.rowsRich[rowIndex][colIndex] = payload;
        }
        if (usesStructuredNoticeDocumentModel(workspace.composeDraft?.bodyModel)) {
          syncFloatingComposeDraftFromDom({ markDirty: true });
        } else {
          updateComposeTableBlock(blockId, () => table, { markDirty: true, rerender: false, preserveExistingRich: false });
        }
        captureComposeRichSelection();
        return;
      }
    }
    if (target instanceof HTMLTextAreaElement && target.dataset.noticeComposeParagraphInput === "true") {
      resizeComposeParagraphInput(target);
      const blockId = String(target.dataset.noticeComposeBlockId || "").trim();
      const blocks = getComposeContentBlocks(workspace.composeDraft).map((block) => {
        if (block.kind !== "paragraph" || String(block.id || "").trim() !== blockId) {
          return block;
        }
        return {
          id: block.id,
          kind: "paragraph",
          text: target.value,
        };
      });
      setComposeContentBlocks(blocks, { markDirty: true, rerender: false });
      return;
    }
    if (target instanceof HTMLInputElement && target.dataset.noticeImageField === "caption") {
      const index = Math.max(0, Number(target.dataset.noticeImageIndex || 0) || 0);
      if (usesStructuredNoticeDocumentModel(workspace.composeDraft?.bodyModel)) {
        const objectId = String(target.dataset.noticeImageObjectId || "").trim();
        updateComposeFloatingDocument((documentValue) => {
          const next = isFlowLaneNoticeModel(workspace.composeDraft?.bodyModel)
            ? normalizeFlowLaneDocumentDraft(documentValue, "")
            : normalizeFloatingDocumentDraft(documentValue, "");
          next.objects = (next.objects || []).map((item) => (
            String(item?.id || "").trim() === objectId
              ? { ...item, caption: target.value || null }
              : item
          ));
          return next;
        });
      } else {
        const images = cloneImageDrafts(workspace.composeDraft.images);
        if (images[index]) {
          images[index].caption = target.value;
          updateComposeDraft({ images });
        }
      }
      return;
    }
    if (target instanceof HTMLInputElement && target.dataset.noticeTableField) {
      const blockId = String(target.dataset.noticeTableBlockId || "").trim();
      const table = usesStructuredNoticeDocumentModel(workspace.composeDraft?.bodyModel)
        ? cloneTableDraft(getFloatingDocumentObjectById(workspace.composeDraft?.bodyDocument, blockId)?.table)
        : cloneTableDraft(
          getComposeContentBlocks(workspace.composeDraft).find((block) => block.kind === "table" && String(block.id || "").trim() === blockId)?.table
        );
      const colIndex = Math.max(0, Number(target.dataset.noticeTableCol || 0) || 0);
      if (target.dataset.noticeTableField === "header") {
        table.columns[colIndex] = target.value;
      } else {
        const rowIndex = Math.max(0, Number(target.dataset.noticeTableRow || 0) || 0);
        if (!Array.isArray(table.rows[rowIndex])) {
          table.rows[rowIndex] = Array.from({ length: table.columns.length }, () => "");
        }
        table.rows[rowIndex][colIndex] = target.value;
      }
      if (usesStructuredNoticeDocumentModel(workspace.composeDraft?.bodyModel)) {
        updateFloatingTableObject(blockId, () => table);
      } else {
        updateComposeTableBlock(blockId, () => table, { markDirty: true, rerender: false });
      }
      return;
    }
    if (target.id === "noticesComposePollModalQuestion" && target instanceof HTMLInputElement) {
      workspace.composePollModalDraft = clonePollDraft({
        ...workspace.composePollModalDraft,
        question: target.value,
      });
      return;
    }
    if (target instanceof HTMLInputElement && target.dataset.noticePollModalOptionIndex != null) {
      const index = Math.max(0, Number(target.dataset.noticePollModalOptionIndex || 0) || 0);
      const nextDraft = clonePollDraft(workspace.composePollModalDraft);
      if (nextDraft.options[index]) {
        nextDraft.options[index].label = target.value;
        workspace.composePollModalDraft = nextDraft;
      }
      return;
    }
  }

  function syncDraftFieldChange(event) {
    const target = event.target instanceof HTMLElement ? event.target : null;
    if (!target) {
      return;
    }
    const workspace = ensureWorkspaceState();
    if (target.id === "noticesComposeCategory" && target instanceof HTMLSelectElement) {
      updateComposeDraft({ category: normalizeNoticeCategory(target.value, false) });
      return;
    }
    if (target.id === "noticesComposeFontSizeInput" && target instanceof HTMLInputElement) {
      if (!String(target.value || "").trim()) {
        target.value = String(workspace.composeFontSizeDraft || SOC_NOTICE_RICH_FONT_SIZE_DEFAULT);
        return;
      }
      if (!applyComposeFontSize(target.value)) {
        renderComposeFormatControls(getWorkspaceElements(), workspace);
      }
      return;
    }
    if (target.id === "noticesComposeImageInput" && target instanceof HTMLInputElement) {
      if (target.files?.length) {
        void appendImages(target.files).catch((error) => {
          socToast(String(error?.message || "이미지를 추가하지 못했습니다."), "error", 2200);
        });
      }
      return;
    }
    if (target.id === "noticesComposePollModalVisibility" && target instanceof HTMLSelectElement) {
      workspace.composePollModalDraft = clonePollDraft({
        ...workspace.composePollModalDraft,
        resultVisibility: target.value,
      });
      return;
    }
    if (target.id === "noticesComposePollModalClosesAt" && target instanceof HTMLInputElement) {
      const nextValue = target.value ? new Date(target.value).toISOString() : "";
      workspace.composePollModalDraft = clonePollDraft({
        ...workspace.composePollModalDraft,
        closesAt: nextValue,
      });
      return;
    }
  }

  async function handleClick(event) {
    const target = event.target instanceof Element ? event.target.closest("[data-action]") : null;
    const action = String(target?.getAttribute("data-action") || "").trim();
    if (!action || !action.startsWith("notices-")) {
      return;
    }
    event.preventDefault();
    const workspace = ensureWorkspaceState();

    if (action === "notices-open-compose") {
      openAnnouncementComposerModal({ historyMode: "push" });
      return;
    }
    if (action === "notices-go-list") {
      workspace.mode = SOC_NOTICE_VIEW_MODE_LIST;
      workspace.selectedNoticeId = "";
      workspace.selectedRow = null;
      workspace.composeEditingId = "";
      clearComposeAutosaveTimer();
      syncAnnouncementRouteState({
        historyMode: "push",
        mode: SOC_NOTICE_VIEW_MODE_LIST,
        noticeId: "",
      });
      void loadWorkspaceRouteState();
      return;
    }
    if (action === "notices-set-category") {
      workspace.category = normalizeNoticeCategory(target.dataset.category || "all");
      workspace.search = "";
      workspace.searchDraft = "";
      workspace.selectedNoticeId = "";
      workspace.selectedRow = null;
      workspace.mode = SOC_NOTICE_VIEW_MODE_LIST;
      clearComposeAutosaveTimer();
      syncAnnouncementRouteState({
        historyMode: "push",
        mode: SOC_NOTICE_VIEW_MODE_LIST,
        category: workspace.category,
        search: "",
        noticeId: "",
      });
      void loadWorkspaceRouteState();
      return;
    }
    if (action === "notices-open-detail") {
      const noticeId = String(target.dataset.noticeId || "").trim();
      if (!noticeId) {
        return;
      }
      const nextSelected = (Array.isArray(workspace.rows) ? workspace.rows : []).find((row) => String(row?.id || "").trim() === noticeId) || null;
      workspace.selectedNoticeId = noticeId;
      workspace.selectedRow = nextSelected || workspace.selectedRow || null;
      workspace.mode = SOC_NOTICE_VIEW_MODE_DETAIL;
      workspace.detailLoading = true;
      renderWorkspace();
      syncAnnouncementRouteState({
        historyMode: "push",
        mode: SOC_NOTICE_VIEW_MODE_DETAIL,
        noticeId,
      });
      void loadWorkspaceRouteState();
      return;
    }
    if (action === "notices-search-toggle") {
      const hasValue = Boolean(String(workspace.searchDraft || "").trim());
      if (hasValue) {
        workspace.search = "";
        workspace.searchDraft = "";
        workspace.searchExpanded = false;
        syncAnnouncementRouteState({
          historyMode: "replace",
          mode: SOC_NOTICE_VIEW_MODE_LIST,
          noticeId: "",
          search: "",
        });
        void loadWorkspaceRouteState();
        return;
      }
      workspace.searchExpanded = !workspace.searchExpanded;
      renderWorkspace();
      if (workspace.searchExpanded) {
        const input = document.getElementById("noticesSearchInput");
        if (input instanceof HTMLInputElement) {
          window.requestAnimationFrame(() => input.focus());
        }
      }
      return;
    }
    if (action === "notices-open-edit") {
      if (!canManageSocNotices() || !workspace.selectedRow) {
        return;
      }
      workspace.mode = SOC_NOTICE_VIEW_MODE_COMPOSE;
      workspace.composeEditingId = String(workspace.selectedRow?.id || workspace.selectedNoticeId || "").trim();
      workspace.composeDraft = normalizeDraftFromRow(workspace.selectedRow);
      resetComposeDraftMeta();
      restoreSavedComposeDraft({
        noticeId: workspace.composeEditingId,
        fallbackCategory: workspace.selectedRow?.category || workspace.category || "ops",
      });
      syncAnnouncementRouteState({
        historyMode: "push",
        mode: SOC_NOTICE_VIEW_MODE_COMPOSE,
        noticeId: workspace.composeEditingId,
      });
      renderWorkspace();
      workspace.detailLoading = true;
      void fetchNoticeDetailRow(workspace.composeEditingId)
        .then((freshRow) => {
          if (!freshRow || String(freshRow?.id || "").trim() !== workspace.composeEditingId) {
            return;
          }
          workspace.selectedRow = freshRow;
          if (!workspace.composeDirtySinceLoad) {
            workspace.composeDraft = normalizeDraftFromRow(freshRow);
            resetComposeDraftMeta();
            restoreSavedComposeDraft({
              noticeId: workspace.composeEditingId,
              fallbackCategory: freshRow?.category || workspace.category || "ops",
            });
          }
        })
        .catch((error) => {
          workspace.error = String(error?.message || "").trim() || "공지 상세를 불러오지 못했습니다.";
        })
        .finally(() => {
          workspace.detailLoading = false;
          renderWorkspace();
        });
      return;
    }
    if (action === "notices-toggle-pinned") {
      updateComposeDraft({ isPinned: !Boolean(workspace.composeDraft?.isPinned) });
      renderWorkspace();
      return;
    }
    if (action === "notices-format-bold") {
      applyInlineTagFormat("strong");
      return;
    }
    if (action === "notices-format-italic") {
      applyInlineTagFormat("em");
      return;
    }
    if (action === "notices-format-underline") {
      applyInlineTagFormat("u");
      return;
    }
    if (action === "notices-format-link") {
      clearComposeFormatMenuState();
      renderComposeFormatControls(getWorkspaceElements(), workspace);
      openLinkModal();
      return;
    }
    if (action === "notices-toggle-font-size-menu") {
      toggleComposeFormatMenu("size");
      return;
    }
    if (action === "notices-apply-font-size") {
      applyComposeFontSize(target.dataset.value || "");
      return;
    }
    if (action === "notices-toggle-text-color-palette") {
      toggleComposeFormatMenu("text-color");
      return;
    }
    if (action === "notices-apply-text-color") {
      applyComposeTextColor(target.dataset.value || "");
      return;
    }
    if (action === "notices-toggle-highlight-palette") {
      toggleComposeFormatMenu("highlight");
      return;
    }
    if (action === "notices-apply-highlight-color") {
      applyComposeHighlight(target.dataset.value || "");
      return;
    }
    if (action === "notices-link-modal-close") {
      closeLinkModal();
      return;
    }
    if (action === "notices-link-modal-apply") {
      applyLinkModal();
      return;
    }
    if (action === "notices-link-modal-remove") {
      removeLinkModalLink();
      return;
    }
    if (action === "notices-format-align-left") {
      applyRichAlignment("left");
      return;
    }
    if (action === "notices-format-align-center") {
      applyRichAlignment("center");
      return;
    }
    if (action === "notices-format-align-right") {
      applyRichAlignment("right");
      return;
    }
    if (action === "notices-delete") {
      await deleteAnnouncementById(target.dataset.noticeId || workspace.selectedNoticeId || "");
      return;
    }
    if (action === "notices-insert-image-block" || action === "notices-image-pick") {
      clearComposeFormatMenuState();
      renderComposeFormatControls(getWorkspaceElements(), workspace);
      const input = document.getElementById("noticesComposeImageInput");
      if (input instanceof HTMLInputElement) {
        input.click();
      }
      return;
    }
    if (action === "notices-image-remove") {
      const index = Math.max(0, Number(target.dataset.noticeImageIndex || 0) || 0);
      if (usesStructuredNoticeDocumentModel(workspace.composeDraft?.bodyModel)) {
        removeFloatingObject(String(target.dataset.noticeImageObjectId || target.dataset.noticeFloatingObjectId || "").trim());
      } else {
        const images = cloneImageDrafts(workspace.composeDraft.images);
        images.splice(index, 1);
        updateComposeDraft({ imagesEnabled: images.length > 0, images });
        renderWorkspace();
      }
      return;
    }
    if (action === "notices-image-remove-floating") {
      removeFloatingObject(String(target.dataset.noticeImageObjectId || target.dataset.noticeFloatingObjectId || "").trim());
      return;
    }
    if (action === "notices-insert-table-block") {
      clearComposeFormatMenuState();
      workspace.composeTablePickerOpen = !workspace.composeTablePickerOpen;
      renderWorkspace();
      return;
    }
    if (action === "notices-table-picker-select") {
      setTablePreset(target.dataset.rows, target.dataset.cols);
      return;
    }
    if (action === "notices-remove-table-block") {
      const blockId = String(target.dataset.noticeTableBlockId || target.dataset.noticeFloatingObjectId || "").trim();
      if (usesStructuredNoticeDocumentModel(workspace.composeDraft?.bodyModel)) {
        removeFloatingObject(blockId);
      } else {
        removeComposeTableBlock(blockId, { markDirty: true, rerender: true });
      }
      return;
    }
    if (action === "notices-table-add-row" || action === "notices-table-remove-row" || action === "notices-table-add-column" || action === "notices-table-remove-column") {
      const blockId = String(target.dataset.noticeTableBlockId || "").trim();
      const table = usesStructuredNoticeDocumentModel(workspace.composeDraft?.bodyModel)
        ? cloneTableDraft(getFloatingDocumentObjectById(workspace.composeDraft?.bodyDocument, blockId)?.table)
        : cloneTableDraft(
          getComposeContentBlocks(workspace.composeDraft).find((block) => block.kind === "table" && String(block.id || "").trim() === blockId)?.table
        );
      if (action === "notices-table-add-row") {
        if (table.rows.length >= 20) {
          socToast("표 행은 최대 20개까지 추가할 수 있습니다.", "info", 2200);
          return;
        }
        table.rows.push(Array.from({ length: table.columns.length }, () => ""));
      } else if (action === "notices-table-remove-row") {
        if (table.rows.length <= 1) {
          socToast("표 행은 최소 1개 이상 유지해야 합니다.", "info", 2200);
          return;
        }
        table.rows.pop();
      } else if (action === "notices-table-add-column") {
        if (table.columns.length >= 6) {
          socToast("표 열은 최대 6개까지 추가할 수 있습니다.", "info", 2200);
          return;
        }
        table.columns.push(`항목 ${table.columns.length + 1}`);
        table.rows = table.rows.map((row) => [...row, ""]);
      } else if (action === "notices-table-remove-column") {
        if (table.columns.length <= 1) {
          socToast("표 열은 최소 1개 이상 유지해야 합니다.", "info", 2200);
          return;
        }
        table.columns.pop();
        table.rows = table.rows.map((row) => row.slice(0, table.columns.length));
      }
      if (usesStructuredNoticeDocumentModel(workspace.composeDraft?.bodyModel)) {
        updateFloatingTableObject(blockId, () => ({ ...table, enabled: true }));
      } else {
        updateComposeTableBlock(blockId, () => ({ ...table, enabled: true }), { markDirty: true, rerender: true });
      }
      return;
    }
    if (action === "notices-insert-poll-block" || action === "notices-edit-poll-block") {
      clearComposeFormatMenuState();
      renderComposeFormatControls(getWorkspaceElements(), workspace);
      openPollModal(target);
      return;
    }
    if (action === "notices-remove-poll-block") {
      const blockId = String(target.dataset.noticePollBlockId || target.dataset.noticeFloatingObjectId || "").trim();
      if (usesStructuredNoticeDocumentModel(workspace.composeDraft?.bodyModel)) {
        removeFloatingObject(blockId);
      } else {
        removeComposePollBlock(blockId, { markDirty: true, rerender: true });
      }
      return;
    }
    if (action === "notices-poll-modal-close") {
      closePollModal();
      return;
    }
    if (action === "notices-poll-modal-save") {
      savePollModal();
      return;
    }
    if (action === "notices-toggle-poll-modal-allow-change") {
      workspace.composePollModalDraft = clonePollDraft({
        ...workspace.composePollModalDraft,
        allowChangeVote: !Boolean(workspace.composePollModalDraft.allowChangeVote),
      });
      renderWorkspace();
      return;
    }
    if (action === "notices-poll-modal-add-option") {
      const nextDraft = clonePollDraft(workspace.composePollModalDraft);
      if (nextDraft.options.length >= SOC_NOTICE_MAX_POLL_OPTIONS) {
        socToast("투표 선택지는 최대 10개까지 추가할 수 있습니다.", "info", 2200);
        return;
      }
      nextDraft.options.push(createDefaultPollOption(nextDraft.options.length));
      workspace.composePollModalDraft = nextDraft;
      renderWorkspace();
      return;
    }
    if (action === "notices-poll-modal-remove-option") {
      const index = Math.max(0, Number(target.dataset.noticePollModalOptionIndex || 0) || 0);
      const nextDraft = clonePollDraft(workspace.composePollModalDraft);
      if (nextDraft.options.length <= SOC_NOTICE_MIN_POLL_OPTIONS) {
        socToast("투표 선택지는 최소 2개 이상 유지해야 합니다.", "info", 2200);
        return;
      }
      nextDraft.options.splice(index, 1);
      workspace.composePollModalDraft = nextDraft;
      renderWorkspace();
      return;
    }
    if (action === "notices-insert-divider") {
      if (insertBodySnippet("\n\n---\n\n", 6)) {
        socToast("구분선을 본문에 추가했습니다.", "success", 1600);
      }
      return;
    }
    if (action === "notices-insert-link") {
      openLinkModal();
      return;
    }
    if (action === "notices-poll-submit") {
      const noticeId = String(target.dataset.noticeId || "").trim();
      const pollId = String(target.dataset.noticePollId || "").trim();
      if (!noticeId || !pollId) {
        socToast("투표 정보를 찾지 못했습니다.", "error", 2200);
        return;
      }
      const card = target.closest(".notices-poll-card");
      const selectedOptionIds = Array.from(card?.querySelectorAll?.('input[data-notice-poll-option-id]:checked') || [])
        .map((input) => String(input instanceof HTMLInputElement ? input.value : "").trim())
        .filter(Boolean);
      if (!selectedOptionIds.length) {
        socToast("투표 항목을 선택해 주세요.", "info", 2200);
        return;
      }
      workspace.pollSubmittingId = pollId;
      renderWorkspace();
      try {
        const saved = await submitNoticePollVote(noticeId, pollId, selectedOptionIds);
        workspace.selectedRow = saved;
        workspace.selectedNoticeId = String(saved?.id || noticeId).trim();
        socToast("투표를 반영했습니다.", "success", 1800);
        renderWorkspace();
      } catch (error) {
        socToast(String(error?.message || "투표를 반영하지 못했습니다."), "error", 2200);
      } finally {
        workspace.pollSubmittingId = "";
        renderWorkspace();
      }
      return;
    }
    if (action === "notices-publish") {
      try {
        const saved = await saveNoticeDraft();
        socToast(workspace.composeEditingId ? "공지를 수정했습니다." : "공지를 발행했습니다.", "success", 1800);
        clearComposeAutosaveTimer();
        clearComposeDraftStorage({ noticeId: workspace.composeEditingId || workspace.selectedNoticeId || "" });
        resetComposeDraftMeta();
        workspace.category = normalizeNoticeCategory(saved.category || workspace.category || "all");
        workspace.selectedNoticeId = String(saved.id || "").trim();
        workspace.selectedRow = saved;
        workspace.composeEditingId = "";
        workspace.mode = SOC_NOTICE_VIEW_MODE_DETAIL;
        syncAnnouncementRouteState({
          historyMode: "replace",
          mode: SOC_NOTICE_VIEW_MODE_DETAIL,
          noticeId: workspace.selectedNoticeId,
        });
        renderWorkspace();
        await loadWorkspaceRouteState();
      } catch (error) {
        socToast(String(error?.message || "공지를 저장하지 못했습니다."), "error", 2400);
      }
    }
  }

  function handleKeydown(event) {
    const target = event.target instanceof HTMLElement ? event.target : null;
    if (!target) {
      return;
    }
    if (target.id === "noticesComposeLinkUrl" && event.key === "Enter") {
      event.preventDefault();
      applyLinkModal();
      return;
    }
    if (target.id === "noticesComposeLinkUrl" && event.key === "Escape") {
      event.preventDefault();
      closeLinkModal();
      return;
    }
    if (target.id === "noticesComposeFontSizeInput" && event.key === "Enter") {
      event.preventDefault();
      target.blur();
      return;
    }
    if (target.id === "noticesComposeFontSizeInput" && event.key === "Escape") {
      event.preventDefault();
      clearComposeFormatMenuState();
      renderComposeFormatControls(getWorkspaceElements(), ensureWorkspaceState());
      return;
    }
    if (target.id === "noticesComposeFontSizeInput" && event.key === "ArrowDown") {
      event.preventDefault();
      toggleComposeFormatMenu("size");
      return;
    }
    if (target.dataset.noticeRichEditor === "true" && event.key === "Enter") {
      event.preventDefault();
      insertPlainTextAtSelection("\n");
      notifyRichEditorMutation(target);
      return;
    }
    if ((target.id === "noticesComposeImageDropzone") && (event.key === "Enter" || event.key === " ")) {
      event.preventDefault();
      const input = document.getElementById("noticesComposeImageInput");
      if (input instanceof HTMLInputElement) {
        input.click();
      }
    }
  }

  function handleMouseDown(event) {
    const target = event.target instanceof HTMLElement ? event.target : null;
    if (!target) {
      return;
    }
    const sceneResizeHandle = target.closest("[data-notice-scene-resize-handle]");
    if (sceneResizeHandle instanceof HTMLElement) {
      beginFloatingSceneInteraction(sceneResizeHandle.dataset.noticeSceneResizeHandle || "", "resize", event);
      return;
    }
    const flowLaneResizeHandle = target.closest("[data-notice-flow-lane-resize-handle]");
    if (flowLaneResizeHandle instanceof HTMLElement) {
      beginFlowLaneInteraction(flowLaneResizeHandle.dataset.noticeFlowLaneResizeHandle || "", "resize", event);
      return;
    }
    const tableResizeHandle = target.closest("[data-notice-table-resize-kind]");
    if (tableResizeHandle instanceof HTMLElement) {
      beginTableResizeInteraction(tableResizeHandle, event);
      return;
    }
    const flowLaneDragBody = target.closest("[data-notice-flow-lane-drag-body]");
    if (
      flowLaneDragBody instanceof HTMLElement
      && !target.closest("[data-notice-flow-lane-resize-handle]")
    ) {
      beginFlowLaneInteraction(flowLaneDragBody.dataset.noticeFlowLaneDragBody || "", "move", event);
      return;
    }
    const sceneDragBody = target.closest("[data-notice-scene-drag-body]");
    if (
      sceneDragBody instanceof HTMLElement
      && !target.closest(".notices-floating-object-chrome")
      && !target.closest("[data-notice-scene-resize-handle]")
    ) {
      beginFloatingSceneInteraction(sceneDragBody.dataset.noticeSceneDragBody || "", "move", event);
      return;
    }
    const sceneDragHandle = target.closest("[data-notice-scene-drag-handle]");
    if (sceneDragHandle instanceof HTMLElement) {
      beginFloatingSceneInteraction(sceneDragHandle.dataset.noticeSceneDragHandle || "", "move", event);
      return;
    }
    const workspace = ensureWorkspaceState();
    if (
      workspace.composeFormatMenu
      && !target.closest(".notices-toolbar-floating-control")
      && !target.closest(".notices-toolbar-popover")
    ) {
      clearComposeFormatMenuState();
      renderComposeFormatControls(getWorkspaceElements(), workspace);
    }
    if (target.closest("[data-notice-rich-toolbar=\"true\"]") && !target.closest(".notices-toolbar-size-input")) {
      event.preventDefault();
      restoreComposeRichSelection();
      return;
    }
    if (target.closest(".notices-toolbar-size-input")) {
      captureComposeInsertionAnchor(getActiveRichEditorElement());
      return;
    }
    const activeRichParagraph = getActiveRichEditorElement();
    if (
      activeRichParagraph instanceof HTMLElement
      && String(activeRichParagraph.dataset.noticeComposeEditorKind || "").trim() === "paragraph"
      && target !== activeRichParagraph
      && !target.closest("[data-notice-compose-paragraph-input=\"true\"]")
    ) {
      captureComposeInsertionAnchor(activeRichParagraph);
    }
    const activeComposeInput = document.activeElement instanceof HTMLTextAreaElement
      && document.activeElement.dataset.noticeComposeParagraphInput === "true"
      ? document.activeElement
      : null;
    if (activeComposeInput && target !== activeComposeInput && !target.closest("[data-notice-compose-paragraph-input=\"true\"]")) {
      captureComposeInsertionAnchor(activeComposeInput);
    }
    const dragHandle = target.closest(".notices-inline-drag-handle");
    if (!(dragHandle instanceof HTMLElement)) {
      return;
    }
    beginComposeFlowDrag(
      dragHandle.dataset.noticeInlineDragHandle || "",
      event,
      dragHandle.dataset.noticeTableBlockId || dragHandle.dataset.noticePollBlockId || dragHandle.closest("[data-notice-compose-block-id]")?.dataset?.noticeComposeBlockId || ""
    );
  }

  function handlePaste(event) {
    const target = event.target instanceof HTMLElement ? event.target : null;
    const workspace = ensureWorkspaceState();
    const imageFiles = Array.from(event.clipboardData?.files || []).filter((file) => String(file?.type || "").startsWith("image/"));
    if (workspace.mode === SOC_NOTICE_VIEW_MODE_COMPOSE && usesStructuredNoticeDocumentModel(workspace.composeDraft?.bodyModel) && imageFiles.length) {
      event.preventDefault();
      void appendImages(imageFiles).catch((error) => {
        socToast(String(error?.message || "이미지를 붙여넣지 못했습니다."), "error", 2200);
      });
      return;
    }
    if (!(target instanceof HTMLElement) || target.dataset.noticeRichEditor !== "true") {
      return;
    }
    event.preventDefault();
    const text = event.clipboardData?.getData("text/plain") || "";
    insertPlainTextAtSelection(text);
    notifyRichEditorMutation(target);
  }

  function handleMouseOver(event) {
    const target = event.target instanceof HTMLElement ? event.target.closest('[data-action="notices-table-picker-select"]') : null;
    if (!(target instanceof HTMLElement)) {
      return;
    }
    const workspace = ensureWorkspaceState();
    const rows = Math.max(1, Math.min(6, Number(target.dataset.rows) || 1));
    const cols = Math.max(1, Math.min(6, Number(target.dataset.cols) || 1));
    if (workspace.composeTablePickerRows === rows && workspace.composeTablePickerCols === cols) {
      return;
    }
    workspace.composeTablePickerRows = rows;
    workspace.composeTablePickerCols = cols;
    renderTablePicker(getWorkspaceElements(), workspace);
  }

  function handleDragOver(event) {
    const workspace = ensureWorkspaceState();
    if (!usesStructuredNoticeDocumentModel(workspace.composeDraft?.bodyModel) || workspace.mode !== SOC_NOTICE_VIEW_MODE_COMPOSE) {
      return;
    }
    const hasImageFile = Array.from(event.dataTransfer?.items || []).some((item) => String(item?.type || "").startsWith("image/"));
    if (!hasImageFile) {
      return;
    }
    event.preventDefault();
    const sceneEl = getComposeFloatingSceneElement();
    if (!(sceneEl instanceof HTMLElement)) {
      return;
    }
    const point = resolveFloatingScenePoint(sceneEl, event.clientX, event.clientY);
    sceneEl.style.setProperty("--notices-scene-drop-x", `${point.x}px`);
    sceneEl.style.setProperty("--notices-scene-drop-y", `${point.y}px`);
    sceneEl.classList.add("is-drop-target");
  }

  function handleDrop(event) {
    const workspace = ensureWorkspaceState();
    const sceneEl = getComposeFloatingSceneElement();
    if (sceneEl instanceof HTMLElement) {
      sceneEl.classList.remove("is-drop-target");
    }
    if (!usesStructuredNoticeDocumentModel(workspace.composeDraft?.bodyModel) || workspace.mode !== SOC_NOTICE_VIEW_MODE_COMPOSE) {
      return;
    }
    const files = Array.from(event.dataTransfer?.files || []).filter((file) => String(file?.type || "").startsWith("image/"));
    if (!files.length) {
      return;
    }
    event.preventDefault();
    void appendImages(files, {
      insertionPoint: sceneEl instanceof HTMLElement
        ? resolveFloatingScenePoint(sceneEl, event.clientX, event.clientY)
        : null,
    }).catch((error) => {
      socToast(String(error?.message || "이미지를 드롭하지 못했습니다."), "error", 2200);
    });
  }

  function handleSubmit(event) {
    const target = event.target instanceof HTMLElement ? event.target : null;
    if (!target || target.id !== "noticesSearchForm") {
      return;
    }
    event.preventDefault();
    const workspace = ensureWorkspaceState();
    const input = document.getElementById("noticesSearchInput");
    const nextValue = input instanceof HTMLInputElement ? normalizeNoticeSearch(input.value) : "";
    workspace.search = nextValue;
    workspace.searchDraft = nextValue;
    workspace.searchExpanded = Boolean(nextValue);
    workspace.mode = SOC_NOTICE_VIEW_MODE_LIST;
    workspace.selectedNoticeId = "";
    workspace.selectedRow = null;
    syncAnnouncementRouteState({
      historyMode: "push",
      mode: SOC_NOTICE_VIEW_MODE_LIST,
      search: nextValue,
      noticeId: "",
    });
    void loadWorkspaceRouteState();
  }

  document.addEventListener("click", (event) => {
    void handleClick(event);
  });
  document.addEventListener("mousedown", handleMouseDown);
  document.addEventListener("mouseover", handleMouseOver);
  document.addEventListener("mousemove", handleComposeFlowDragMove);
  document.addEventListener("mouseup", finishComposeFlowDrag);
  document.addEventListener("mousemove", handleFloatingScenePointerMove);
  document.addEventListener("mouseup", finishFloatingSceneInteraction);
  document.addEventListener("mousemove", handleFlowLanePointerMove);
  document.addEventListener("mouseup", finishFlowLaneInteraction);
  document.addEventListener("mousemove", handleTableResizePointerMove);
  document.addEventListener("mouseup", finishTableResizeInteraction);
  document.addEventListener("input", syncDraftFieldInput);
  document.addEventListener("change", syncDraftFieldChange);
  document.addEventListener("dragover", handleDragOver);
  document.addEventListener("drop", handleDrop);
  document.addEventListener("selectionchange", () => {
    const workspace = ensureWorkspaceState();
    const activeRichEditor = getActiveRichEditorElement();
    if (activeRichEditor instanceof HTMLElement) {
      captureComposeRichSelection();
      return;
    }
    if (workspace.composeLinkModalOpen) {
      return;
    }
    const activeComposeInput = document.activeElement instanceof HTMLTextAreaElement
      && document.activeElement.dataset.noticeComposeParagraphInput === "true"
      ? document.activeElement
      : null;
    if (activeComposeInput) {
      captureComposeInsertionAnchor(activeComposeInput);
      return;
    }
    const activeElement = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    if (activeElement?.closest?.("[data-notice-rich-toolbar=\"true\"]")) {
      return;
    }
    clearComposeRichSelection();
  });
  document.addEventListener("keydown", handleKeydown);
  document.addEventListener("paste", handlePaste);
  document.addEventListener("submit", handleSubmit);

  function resetWorkspaceFromHash() {
    const routeState = parseAnnouncementHashState(window.location.hash);
    if (!routeState) {
      return;
    }
    const workspace = ensureWorkspaceState();
    workspace.category = routeState.category;
    workspace.search = routeState.search;
    workspace.searchDraft = routeState.search;
    workspace.searchExpanded = Boolean(routeState.search);
    workspace.selectedNoticeId = routeState.noticeId;
    workspace.mode = routeState.mode;
  }

  window.syncAnnouncementRouteState = syncAnnouncementRouteState;
  window.openAnnouncementsTab = openAnnouncementsTab;
  window.openAnnouncementsPage = openAnnouncementsPage;
  window.applyAnnouncementRouteState = applyAnnouncementRouteState;
  window.openAnnouncementComposerModal = openAnnouncementComposerModal;
  window.closeAnnouncementComposerModal = closeAnnouncementComposerModal;
  window.refreshAnnouncementPanelMode = refreshAnnouncementPanelMode;
  window.loadAnnouncements = loadAnnouncements;
  window.renderAnnouncements = renderAnnouncements;
  window.deleteAnnouncementById = deleteAnnouncementById;

  window.socOpenAnnouncementsTab = function socOpenAnnouncementsTab(options = {}) {
    return openAnnouncementsTab(options);
  };
  window.socOpenAnnouncementComposerModal = function socOpenAnnouncementComposerModal(options = {}) {
    return openAnnouncementComposerModal(options);
  };

  window.__SOC_ARLS_NOTICE_WORKSPACE__ = true;
  window.__RG_ARLS_ANNOUNCEMENT_WORKSPACE_READY__ = true;

  resetWorkspaceFromHash();
})();
