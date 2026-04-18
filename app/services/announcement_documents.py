from __future__ import annotations

import html
import json
import re
import uuid
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

ANNOUNCEMENT_NOTICE_CATEGORY_VALUES = ("ops", "attendance", "schedule", "hr", "system", "event")
ANNOUNCEMENT_NOTICE_POLL_RESULT_VISIBILITY_VALUES = ("always", "after_close")
ANNOUNCEMENT_NOTICE_PREVIEW_LENGTH = 200
ANNOUNCEMENT_NOTICE_BODY_TEXT_LIMIT = 20000
ANNOUNCEMENT_NOTICE_PARAGRAPH_TEXT_LIMIT = 4000
ANNOUNCEMENT_NOTICE_PARAGRAPH_RICH_LIMIT = 16000
ANNOUNCEMENT_NOTICE_TABLE_HEADER_TEXT_LIMIT = 120
ANNOUNCEMENT_NOTICE_TABLE_HEADER_RICH_LIMIT = 2000
ANNOUNCEMENT_NOTICE_TABLE_CELL_TEXT_LIMIT = 240
ANNOUNCEMENT_NOTICE_TABLE_CELL_RICH_LIMIT = 4000
ANNOUNCEMENT_NOTICE_TABLE_TITLE_LIMIT = 120
ANNOUNCEMENT_NOTICE_TABLE_MAX_COLUMNS = 6
ANNOUNCEMENT_NOTICE_TABLE_MAX_ROWS = 20
ANNOUNCEMENT_NOTICE_ALIGN_VALUES = {"left", "center", "right"}
ANNOUNCEMENT_NOTICE_RICH_COLOR_TOKENS = {"default", "orange", "red", "blue", "green", "gray"}
ANNOUNCEMENT_NOTICE_RICH_BG_TOKENS = {
    "none",
    "yellow-soft",
    "orange-soft",
    "red-soft",
    "blue-soft",
    "green-soft",
    "gray-soft",
}
ANNOUNCEMENT_NOTICE_RICH_SIZE_TOKENS = {
    "xs",
    "sm",
    "base",
    "lg",
    "xl",
    "8",
    "10",
    "11",
    "11.5",
    "12",
    "14",
    "16",
    "18",
    "20",
    "22",
    "24",
    "26",
    "28",
    "36",
    "48",
    "72",
}
ANNOUNCEMENT_NOTICE_RICH_SIZE_PX_ATTR = "data-rt-size-px"
ANNOUNCEMENT_NOTICE_BODY_MODEL_LEGACY = "legacy_block_flow"
ANNOUNCEMENT_NOTICE_BODY_MODEL_FLOATING = "floating_scene_v1"
ANNOUNCEMENT_NOTICE_BODY_MODEL_FLOW_LANE = "flow_lane_v1"
ANNOUNCEMENT_NOTICE_FLOATING_DOCUMENT_VERSION = "floating_scene_v1"
ANNOUNCEMENT_NOTICE_FLOW_LANE_DOCUMENT_VERSION = "flow_lane_v1"
ANNOUNCEMENT_NOTICE_FLOATING_CANVAS_WIDTH = 880.0
ANNOUNCEMENT_NOTICE_FLOATING_CANVAS_MIN_HEIGHT = 960.0


def _error(field_name: str, detail: str) -> ValueError:
    return ValueError(f"{field_name or 'body_blocks'} {detail}")


def parse_json_value(value: Any, fallback: Any = None) -> Any:
    if value is None:
        return fallback
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return fallback
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return fallback
    return fallback


def normalize_announcement_notice_category(value: Any, *, allow_all: bool = False) -> str:
    normalized = str(value or "").strip().lower()
    allowed = set(ANNOUNCEMENT_NOTICE_CATEGORY_VALUES)
    if allow_all:
        allowed.add("all")
    if normalized in allowed:
        return normalized
    return "all" if allow_all else "ops"


def normalize_announcement_notice_search(value: Any) -> str:
    return " ".join(str(value or "").strip().split())[:120]


def normalize_announcement_notice_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = str(value or "").strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return bool(default)


def normalize_announcement_notice_body_model(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized == ANNOUNCEMENT_NOTICE_BODY_MODEL_FLOATING:
        return ANNOUNCEMENT_NOTICE_BODY_MODEL_FLOATING
    if normalized == ANNOUNCEMENT_NOTICE_BODY_MODEL_FLOW_LANE:
        return ANNOUNCEMENT_NOTICE_BODY_MODEL_FLOW_LANE
    return ANNOUNCEMENT_NOTICE_BODY_MODEL_LEGACY


def is_structured_announcement_notice_body_model(value: Any) -> bool:
    return normalize_announcement_notice_body_model(value) in {
        ANNOUNCEMENT_NOTICE_BODY_MODEL_FLOATING,
        ANNOUNCEMENT_NOTICE_BODY_MODEL_FLOW_LANE,
    }


def infer_announcement_notice_body_model_from_document(raw_document: Any, fallback_model: Any = "") -> str:
    document = parse_json_value(raw_document, fallback=None)
    if not isinstance(document, dict):
        return normalize_announcement_notice_body_model(fallback_model)
    version = str(document.get("version") or "").strip()
    if version == ANNOUNCEMENT_NOTICE_FLOW_LANE_DOCUMENT_VERSION:
        return ANNOUNCEMENT_NOTICE_BODY_MODEL_FLOW_LANE
    if version == ANNOUNCEMENT_NOTICE_FLOATING_DOCUMENT_VERSION:
        return ANNOUNCEMENT_NOTICE_BODY_MODEL_FLOATING
    return normalize_announcement_notice_body_model(fallback_model)


def _validate_text_limit(value: Any, limit: int, field_name: str) -> str:
    text = str(value or "")
    if len(text) > int(limit):
        raise _error(field_name, f"길이는 최대 {int(limit)}자까지 허용됩니다.")
    return text


def _validate_rich_limit(value: Any, limit: int, field_name: str) -> str:
    text = str(value or "")
    if len(text) > int(limit):
        raise _error(field_name, f"rich_text 원문 길이는 최대 {int(limit)}자까지 허용됩니다.")
    return text


def _normalize_alignment(value: Any, default: str = "left") -> str:
    normalized = str(value or default or "left").strip().lower()
    if normalized not in ANNOUNCEMENT_NOTICE_ALIGN_VALUES:
        return default
    return normalized


def _normalize_inline_plain_text(value: Any) -> str:
    text = str(value or "").replace("\xa0", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _candidate_rich_fragment(source: Any) -> str | None:
    if not isinstance(source, dict):
        return None
    for key in ("rich_text", "richText"):
        if key not in source:
            continue
        value = str(source.get(key) or "")
        if value.strip():
            return value
    return None


def _candidate_plain_text(source: Any, fallback_plain: Any = "") -> str:
    if isinstance(source, dict) and "text" in source:
        return str(source.get("text") or "").strip()
    return str(fallback_plain or "").strip()


def _normalize_href(raw_href: Any) -> dict[str, str | None] | None:
    href = html.unescape(str(raw_href or "").strip())
    if not href:
        return None
    parsed = urlparse(href)
    scheme = str(parsed.scheme or "").strip().lower()
    if href.startswith("#"):
        return {"href": href, "target": None, "rel": None}
    if not scheme:
        if href.startswith("//"):
            return None
        return {"href": href, "target": None, "rel": None}
    if scheme not in {"https", "http", "mailto", "tel"}:
        return None
    if scheme in {"https", "http"}:
        return {"href": href, "target": "_blank", "rel": "noopener noreferrer nofollow"}
    return {"href": href, "target": None, "rel": None}


class _RichFragmentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root: dict[str, Any] = {"tag": None, "attrs": {}, "children": []}
        self.stack: list[dict[str, Any]] = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._open_tag(tag, attrs, self_closing=False)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._open_tag(tag, attrs, self_closing=True)

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = str(tag or "").strip().lower()
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].get("tag") == normalized_tag:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        if data:
            self.stack[-1]["children"].append({"tag": "#text", "data": data})

    def _open_tag(self, tag: str, attrs: list[tuple[str, str | None]], *, self_closing: bool) -> None:
        normalized_tag = str(tag or "").strip().lower()
        if normalized_tag == "br":
            self.stack[-1]["children"].append({"tag": "br", "attrs": {}, "children": []})
            return
        if normalized_tag not in {"a", "strong", "em", "u", "span", "mark"}:
            return
        attr_lookup: dict[str, str] = {}
        for key, value in attrs or []:
            normalized_key = str(key or "").strip().lower()
            if normalized_key and normalized_key not in attr_lookup:
                attr_lookup[normalized_key] = str(value or "")
        node_attrs: dict[str, str] = {}
        if normalized_tag == "a":
            safe_link = _normalize_href(attr_lookup.get("href"))
            if not safe_link:
                return
            node_attrs["href"] = str(safe_link["href"] or "")
            if safe_link.get("target"):
                node_attrs["target"] = str(safe_link["target"])
            if safe_link.get("rel"):
                node_attrs["rel"] = str(safe_link["rel"])
        elif normalized_tag in {"span", "mark"}:
            size_token = str(attr_lookup.get("data-rt-size") or "").strip().lower()
            size_px = str(attr_lookup.get(ANNOUNCEMENT_NOTICE_RICH_SIZE_PX_ATTR) or "").strip()
            color_token = str(attr_lookup.get("data-rt-color") or "").strip().lower()
            bg_token = str(attr_lookup.get("data-rt-bg") or "").strip().lower()
            if size_token in ANNOUNCEMENT_NOTICE_RICH_SIZE_TOKENS:
                node_attrs["data-rt-size"] = size_token
            if size_px:
                node_attrs[ANNOUNCEMENT_NOTICE_RICH_SIZE_PX_ATTR] = _normalize_decimal_string(
                    size_px,
                    f"{normalized_tag}.{ANNOUNCEMENT_NOTICE_RICH_SIZE_PX_ATTR}",
                    minimum="1",
                )
            if color_token in ANNOUNCEMENT_NOTICE_RICH_COLOR_TOKENS:
                node_attrs["data-rt-color"] = color_token
            if bg_token in ANNOUNCEMENT_NOTICE_RICH_BG_TOKENS:
                node_attrs["data-rt-bg"] = bg_token
            if normalized_tag == "span" and not node_attrs:
                return
        node = {"tag": normalized_tag, "attrs": node_attrs, "children": []}
        self.stack[-1]["children"].append(node)
        if not self_closing:
            self.stack.append(node)


def _render_rich_node(node: dict[str, Any]) -> str:
    tag = str(node.get("tag") or "")
    if tag == "#text":
        return html.escape(str(node.get("data") or ""), quote=False)
    if tag == "br":
        return "<br>"
    children_html = "".join(_render_rich_node(child) for child in node.get("children") or [])
    if not children_html:
        return ""
    attrs = node.get("attrs") or {}
    attr_chunks: list[str] = []
    if tag == "a":
        keys = ("href", "target", "rel")
    elif tag == "span":
        keys = ("data-rt-size", ANNOUNCEMENT_NOTICE_RICH_SIZE_PX_ATTR, "data-rt-color", "data-rt-bg")
    elif tag == "mark":
        keys = ("data-rt-bg", "data-rt-color", "data-rt-size", ANNOUNCEMENT_NOTICE_RICH_SIZE_PX_ATTR)
    else:
        keys = ()
    for key in keys:
        if attrs.get(key):
            attr_chunks.append(f'{key}="{html.escape(str(attrs[key]), quote=True)}"')
    attr_text = f" {' '.join(attr_chunks)}" if attr_chunks else ""
    return f"<{tag}{attr_text}>{children_html}</{tag}>"


def _extract_rich_plain_text(node: dict[str, Any]) -> str:
    tag = str(node.get("tag") or "")
    if tag == "#text":
        return str(node.get("data") or "")
    if tag == "br":
        return "\n"
    return "".join(_extract_rich_plain_text(child) for child in node.get("children") or [])


def _canonicalize_rich_fragment(raw_fragment: Any, field_name: str) -> tuple[str | None, str]:
    fragment = str(raw_fragment or "")
    if not fragment.strip():
        return None, ""
    parser = _RichFragmentParser()
    try:
        parser.feed(fragment)
        parser.close()
    except Exception as exc:
        raise _error(field_name, f"rich_text 파싱에 실패했습니다: {exc}") from exc
    children = parser.root.get("children") or []
    canonical_html = "".join(_render_rich_node(child) for child in children).strip()
    plain_text = _normalize_inline_plain_text("".join(_extract_rich_plain_text(child) for child in children))
    if not canonical_html:
        return None, plain_text
    return canonical_html, plain_text


def _build_rich_cell(
    source: Any,
    fallback_plain: Any,
    field_name: str,
    text_limit: int,
    rich_limit: int,
) -> tuple[str, dict[str, Any] | None]:
    has_source = isinstance(source, dict)
    cell_source = source if has_source else {}
    align = _normalize_alignment(cell_source.get("align"))
    rich_candidate = _candidate_rich_fragment(cell_source)
    if rich_candidate is not None:
        _validate_rich_limit(rich_candidate, rich_limit, f"{field_name}.rich_text")
        canonical_rich, plain_text = _canonicalize_rich_fragment(rich_candidate, f"{field_name}.rich_text")
        plain_text = _validate_text_limit(plain_text, text_limit, f"{field_name}.text").strip()
        if not plain_text and align == "left":
            return "", None
        if not canonical_rich and align == "left":
            return plain_text, None
        return plain_text, {"text": plain_text, "rich_text": canonical_rich, "richText": canonical_rich, "align": align}
    plain_text = _validate_text_limit(
        _candidate_plain_text(cell_source, fallback_plain),
        text_limit,
        f"{field_name}.text",
    ).strip()
    if not has_source or align == "left":
        return plain_text, None
    return plain_text, {"text": plain_text, "rich_text": None, "richText": None, "align": align}


def _has_plain_blocks(body_blocks: list[dict[str, Any]]) -> bool:
    for block in body_blocks or []:
        kind = str(block.get("kind") or "").strip()
        if kind == "paragraph" and str(block.get("text") or "").strip():
            return True
        if kind == "table":
            if str(block.get("title") or "").strip():
                return True
            if any(str(value or "").strip() for value in block.get("columns") or []):
                return True
            for row in block.get("rows") or []:
                if any(str(value or "").strip() for value in row or []):
                    return True
    return False


def _table_line(values: Any) -> str:
    return " ".join(str(value or "").strip() for value in values or [] if str(value or "").strip()).strip()


def _normalize_poll_option(option_raw: Any, index: int) -> dict[str, Any] | None:
    if not isinstance(option_raw, dict):
        option_raw = {"label": str(option_raw or "").strip()}
    label = str(option_raw.get("label") or option_raw.get("text") or "").strip()
    if not label:
        return None
    option_id = str(option_raw.get("option_id") or option_raw.get("optionId") or "").strip() or f"option-{uuid.uuid4().hex[:12]}"
    vote_count = max(0, int(option_raw.get("vote_count") or option_raw.get("voteCount") or 0))
    return {
        "option_id": option_id[:64],
        "optionId": option_id[:64],
        "label": label[:160],
        "vote_count": vote_count,
        "voteCount": vote_count,
        "vote_ratio": 0,
        "voteRatio": 0,
        "selected": bool(option_raw.get("selected")),
    }


def normalize_announcement_notice_poll_block(poll_raw: Any) -> dict[str, Any] | None:
    if not isinstance(poll_raw, dict):
        return None
    question = str(poll_raw.get("question") or "").strip()
    if not question:
        return None
    poll_id = str(poll_raw.get("poll_id") or poll_raw.get("pollId") or "").strip() or f"poll-{uuid.uuid4().hex[:12]}"
    options: list[dict[str, Any]] = []
    for index, option_raw in enumerate(poll_raw.get("options") or []):
        normalized = _normalize_poll_option(option_raw, index)
        if normalized:
            options.append(normalized)
    if len(options) < 2:
        return None
    options = options[:10]
    result_visibility = str(poll_raw.get("result_visibility") or poll_raw.get("resultVisibility") or "always").strip().lower()
    if result_visibility not in ANNOUNCEMENT_NOTICE_POLL_RESULT_VISIBILITY_VALUES:
        result_visibility = "always"
    allow_multiple = normalize_announcement_notice_bool(poll_raw.get("allow_multiple") or poll_raw.get("allowMultiple"), False)
    selected_option_ids: list[str] = []
    for raw_option_id in poll_raw.get("selected_option_ids") or poll_raw.get("selectedOptionIds") or []:
        option_id = str(raw_option_id or "").strip()
        if option_id and option_id not in selected_option_ids:
            selected_option_ids.append(option_id)
    if not allow_multiple:
        selected_option_ids = selected_option_ids[:1]
    total_votes = max(0, int(poll_raw.get("total_votes") or poll_raw.get("totalVotes") or 0))
    return {
        "poll_id": poll_id[:64],
        "pollId": poll_id[:64],
        "question": question[:240],
        "options": options,
        "allow_multiple": allow_multiple,
        "allowMultiple": allow_multiple,
        "is_anonymous": normalize_announcement_notice_bool(poll_raw.get("is_anonymous") or poll_raw.get("isAnonymous"), True),
        "isAnonymous": normalize_announcement_notice_bool(poll_raw.get("is_anonymous") or poll_raw.get("isAnonymous"), True),
        "result_visibility": result_visibility,
        "resultVisibility": result_visibility,
        "closes_at": str(poll_raw.get("closes_at") or poll_raw.get("closesAt") or "").strip() or None,
        "closesAt": str(poll_raw.get("closes_at") or poll_raw.get("closesAt") or "").strip() or None,
        "allow_change_vote": normalize_announcement_notice_bool(poll_raw.get("allow_change_vote") or poll_raw.get("allowChangeVote"), False),
        "allowChangeVote": normalize_announcement_notice_bool(poll_raw.get("allow_change_vote") or poll_raw.get("allowChangeVote"), False),
        "total_votes": total_votes,
        "totalVotes": total_votes,
        "selected_option_ids": selected_option_ids,
        "selectedOptionIds": selected_option_ids,
        "results_visible": normalize_announcement_notice_bool(poll_raw.get("results_visible") or poll_raw.get("resultsVisible"), True),
        "resultsVisible": normalize_announcement_notice_bool(poll_raw.get("results_visible") or poll_raw.get("resultsVisible"), True),
        "is_closed": normalize_announcement_notice_bool(poll_raw.get("is_closed") or poll_raw.get("isClosed"), False),
        "isClosed": normalize_announcement_notice_bool(poll_raw.get("is_closed") or poll_raw.get("isClosed"), False),
        "can_vote": normalize_announcement_notice_bool(poll_raw.get("can_vote") or poll_raw.get("canVote"), True),
        "canVote": normalize_announcement_notice_bool(poll_raw.get("can_vote") or poll_raw.get("canVote"), True),
        "has_voted": normalize_announcement_notice_bool(poll_raw.get("has_voted") or poll_raw.get("hasVoted"), False),
        "hasVoted": normalize_announcement_notice_bool(poll_raw.get("has_voted") or poll_raw.get("hasVoted"), False),
    }


def normalize_announcement_notice_body_blocks(
    raw_blocks: Any,
    *,
    fallback_body_text: Any = "",
    fallback_attachments: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    blocks_source = parse_json_value(raw_blocks, fallback=[])
    if not isinstance(blocks_source, list):
        blocks_source = []

    normalized: list[dict[str, Any]] = []
    for block_index, block in enumerate(blocks_source):
        if hasattr(block, "model_dump"):
            block = block.model_dump()
        if not isinstance(block, dict):
            continue
        kind = str(block.get("kind") or "").strip().lower()
        if kind == "paragraph":
            rich_candidate = _candidate_rich_fragment(block)
            align = _normalize_alignment(block.get("align"))
            if rich_candidate is not None:
                _validate_rich_limit(rich_candidate, ANNOUNCEMENT_NOTICE_PARAGRAPH_RICH_LIMIT, f"body_blocks[{block_index}].rich_text")
                rich_text, text = _canonicalize_rich_fragment(rich_candidate, f"body_blocks[{block_index}].rich_text")
                text = _validate_text_limit(text, ANNOUNCEMENT_NOTICE_PARAGRAPH_TEXT_LIMIT, f"body_blocks[{block_index}].text").strip()
            else:
                rich_text = None
                text = _validate_text_limit(block.get("text"), ANNOUNCEMENT_NOTICE_PARAGRAPH_TEXT_LIMIT, f"body_blocks[{block_index}].text").strip()
            if not text:
                continue
            variant = str(block.get("variant") or "body").strip().lower()
            normalized.append(
                {
                    "kind": "paragraph",
                    "variant": "lead" if variant == "lead" else "body",
                    "title": str(block.get("title") or "").strip()[:120] or None,
                    "text": text,
                    "rich_text": rich_text,
                    "richText": rich_text,
                    "align": align,
                }
            )
            continue
        if kind == "image":
            attachment_id = str(block.get("attachment_id") or block.get("attachmentId") or "").strip()
            image_src = str(block.get("image_src") or block.get("imageSrc") or "").strip()
            if not attachment_id and not image_src:
                continue
            normalized.append(
                {
                    "kind": "image",
                    "attachment_id": attachment_id or None,
                    "attachmentId": attachment_id or None,
                    "file_name": str(block.get("file_name") or block.get("fileName") or "").strip()[:200] or None,
                    "fileName": str(block.get("file_name") or block.get("fileName") or "").strip()[:200] or None,
                    "caption": str(block.get("caption") or "").strip()[:240] or None,
                    "image_src": image_src or None,
                    "imageSrc": image_src or None,
                }
            )
            continue
        if kind == "poll":
            poll = normalize_announcement_notice_poll_block(block.get("poll") if isinstance(block.get("poll"), dict) else block)
            if poll:
                normalized.append({"kind": "poll", "poll": poll})
            continue
        if kind != "table":
            continue

        title = str(block.get("title") or "").strip()[:ANNOUNCEMENT_NOTICE_TABLE_TITLE_LIMIT] or None
        has_header = normalize_announcement_notice_bool(block.get("hasHeader", block.get("has_header")), False)
        raw_columns = block.get("columns") if isinstance(block.get("columns"), list) else []
        raw_rows = block.get("rows") if isinstance(block.get("rows"), list) else []
        raw_columns_rich = block.get("columns_rich") or block.get("columnsRich") or []
        raw_rows_rich = block.get("rows_rich") or block.get("rowsRich") or []
        raw_column_widths = block.get("column_widths") or block.get("columnWidths") or []
        raw_row_heights = block.get("row_heights") or block.get("rowHeights") or []

        row_count = len(raw_rows)
        if row_count > ANNOUNCEMENT_NOTICE_TABLE_MAX_ROWS:
            raise _error(f"body_blocks[{block_index}].rows", f"행 수는 최대 {ANNOUNCEMENT_NOTICE_TABLE_MAX_ROWS}개까지 허용됩니다.")
        column_count = max(
            len(raw_columns),
            max((len(row) for row in raw_rows if isinstance(row, list)), default=0),
            len(raw_columns_rich) if isinstance(raw_columns_rich, list) else 0,
        )
        if column_count > ANNOUNCEMENT_NOTICE_TABLE_MAX_COLUMNS:
            raise _error(f"body_blocks[{block_index}].columns", f"열 수는 최대 {ANNOUNCEMENT_NOTICE_TABLE_MAX_COLUMNS}개까지 허용됩니다.")
        if column_count <= 0:
            continue
        columns: list[str] = []
        columns_rich: list[dict[str, Any] | None] = []
        for column_index in range(column_count):
            fallback_plain = raw_columns[column_index] if column_index < len(raw_columns) else ""
            rich_source = raw_columns_rich[column_index] if isinstance(raw_columns_rich, list) and column_index < len(raw_columns_rich) else None
            plain_text, rich_cell = _build_rich_cell(
                rich_source,
                fallback_plain,
                f"body_blocks[{block_index}].columns_rich[{column_index}]",
                ANNOUNCEMENT_NOTICE_TABLE_HEADER_TEXT_LIMIT,
                ANNOUNCEMENT_NOTICE_TABLE_HEADER_RICH_LIMIT,
            )
            columns.append(plain_text)
            columns_rich.append(rich_cell)
        rows: list[list[str]] = []
        rows_rich: list[list[dict[str, Any] | None]] = []
        for row_index, row_plain_source in enumerate(raw_rows):
            if not isinstance(row_plain_source, list):
                continue
            row_rich_source = raw_rows_rich[row_index] if isinstance(raw_rows_rich, list) and row_index < len(raw_rows_rich) else []
            normalized_row: list[str] = []
            normalized_row_rich: list[dict[str, Any] | None] = []
            for column_index in range(column_count):
                fallback_plain = row_plain_source[column_index] if column_index < len(row_plain_source) else ""
                rich_source = row_rich_source[column_index] if isinstance(row_rich_source, list) and column_index < len(row_rich_source) else None
                plain_text, rich_cell = _build_rich_cell(
                    rich_source,
                    fallback_plain,
                    f"body_blocks[{block_index}].rows_rich[{row_index}][{column_index}]",
                    ANNOUNCEMENT_NOTICE_TABLE_CELL_TEXT_LIMIT,
                    ANNOUNCEMENT_NOTICE_TABLE_CELL_RICH_LIMIT,
                )
                normalized_row.append(plain_text)
                normalized_row_rich.append(rich_cell)
            rows.append(normalized_row)
            rows_rich.append(normalized_row_rich)
        if not title and not any(columns) and not any(any(cell for cell in row) for row in rows):
            continue
        payload: dict[str, Any] = {
            "kind": "table",
            "title": title,
            "hasHeader": bool(has_header),
            "columns": columns,
            "rows": rows,
            "columns_rich": columns_rich,
            "columnsRich": columns_rich,
            "rows_rich": rows_rich,
            "rowsRich": rows_rich,
        }
        if isinstance(raw_column_widths, list) and raw_column_widths:
            payload["column_widths"] = [
                _normalize_decimal_float(raw_column_widths[index] if index < len(raw_column_widths) else 160, f"body_blocks[{block_index}].column_widths[{index}]", minimum="48")
                for index in range(len(columns))
            ]
            payload["columnWidths"] = payload["column_widths"]
        if isinstance(raw_row_heights, list) and raw_row_heights:
            payload["row_heights"] = [
                _normalize_decimal_float(raw_row_heights[index] if index < len(raw_row_heights) else 44, f"body_blocks[{block_index}].row_heights[{index}]", minimum="28")
                for index in range(len(rows) + 1)
            ]
            payload["rowHeights"] = payload["row_heights"]
        normalized.append(payload)

    fallback_text = str(fallback_body_text or "").strip()
    if fallback_text and not _has_plain_blocks(normalized):
        fallback_text = _validate_text_limit(fallback_text, ANNOUNCEMENT_NOTICE_PARAGRAPH_TEXT_LIMIT, "body_text").strip()
        if fallback_text:
            normalized.insert(
                0,
                {
                    "kind": "paragraph",
                    "variant": "body",
                    "title": None,
                    "text": fallback_text,
                    "rich_text": None,
                    "richText": None,
                    "align": "left",
                },
            )

    seen_attachment_ids = {
        str(block.get("attachment_id") or block.get("attachmentId") or "").strip()
        for block in normalized
        if str(block.get("kind") or "") == "image" and str(block.get("attachment_id") or block.get("attachmentId") or "").strip()
    }
    for attachment in fallback_attachments or []:
        attachment_id = str(attachment.get("id") or "").strip()
        if not attachment_id or attachment_id in seen_attachment_ids:
            continue
        normalized.append(
            {
                "kind": "image",
                "attachment_id": attachment_id,
                "attachmentId": attachment_id,
                "file_name": str(attachment.get("file_name") or "").strip() or None,
                "fileName": str(attachment.get("file_name") or "").strip() or None,
                "caption": None,
                "image_src": str(attachment.get("download_path") or attachment.get("image_src") or "").strip() or None,
                "imageSrc": str(attachment.get("download_path") or attachment.get("image_src") or "").strip() or None,
            }
        )
    return normalized


def flatten_announcement_notice_body_text(body_blocks: Any, fallback_body_text: Any = "") -> str:
    segments: list[str] = []
    for block in normalize_announcement_notice_body_blocks(body_blocks):
        kind = str(block.get("kind") or "").strip()
        if kind == "paragraph":
            text = str(block.get("text") or "").strip()
            if text:
                segments.append(text)
            continue
        if kind == "poll":
            poll = block.get("poll") or {}
            chunks = [str(poll.get("question") or "").strip()]
            chunks.extend(str(option.get("label") or "").strip() for option in poll.get("options") or [] if isinstance(option, dict))
            line = "\n".join(chunk for chunk in chunks if chunk)
            if line:
                segments.append(line)
            continue
        if kind != "table":
            continue
        table_segments: list[str] = []
        title = str(block.get("title") or "").strip()
        if title:
            table_segments.append(title)
        header_line = _table_line(block.get("columns") or [])
        if header_line:
            table_segments.append(header_line)
        for row in block.get("rows") or []:
            row_line = _table_line(row or [])
            if row_line:
                table_segments.append(row_line)
        if table_segments:
            segments.append("\n\n".join(table_segments))
    if segments:
        return "\n\n".join(segments)[:ANNOUNCEMENT_NOTICE_BODY_TEXT_LIMIT]
    return str(fallback_body_text or "").strip()[:ANNOUNCEMENT_NOTICE_BODY_TEXT_LIMIT]


def build_announcement_notice_body_preview(body_text: Any = "", body_blocks: Any = None) -> str:
    preview_text = str(body_text or "").strip()
    if not preview_text:
        preview_text = flatten_announcement_notice_body_text(body_blocks or [], "")
    preview_text = " ".join(preview_text.split())
    if len(preview_text) > ANNOUNCEMENT_NOTICE_PREVIEW_LENGTH:
        preview_text = f"{preview_text[:ANNOUNCEMENT_NOTICE_PREVIEW_LENGTH - 1].rstrip()}..."
    return preview_text


def parse_announcement_notice_targets(raw_targets: Any) -> list[str]:
    targets = parse_json_value(raw_targets, fallback=raw_targets)
    if not isinstance(targets, list):
        return []
    rows: list[str] = []
    for item in targets:
        text = str(item or "").strip()
        if text and text not in rows:
            rows.append(text)
    return rows


def _normalize_decimal_string(value: Any, field_name: str, *, minimum: str = "0", max_fraction_digits: int = 3) -> str:
    raw = "" if value is None else str(value).strip()
    if not raw:
        raise _error(field_name, "값이 비어 있습니다.")
    if not re.fullmatch(r"\d+(?:\.\d+)?", raw):
        raise _error(field_name, "숫자 형식이 올바르지 않습니다.")
    try:
        numeric = Decimal(raw)
    except (InvalidOperation, ValueError) as exc:
        raise _error(field_name, "숫자 형식이 올바르지 않습니다.") from exc
    if not numeric.is_finite():
        raise _error(field_name, "숫자 형식이 올바르지 않습니다.")
    minimum_value = Decimal(str(minimum))
    if numeric < minimum_value:
        raise _error(field_name, f"값은 최소 {minimum_value} 이상이어야 합니다.")
    quant = Decimal("1").scaleb(-int(max_fraction_digits))
    normalized = numeric.quantize(quant, rounding=ROUND_HALF_UP)
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _normalize_decimal_float(value: Any, field_name: str, *, minimum: str = "0", max_fraction_digits: int = 3) -> float:
    return float(_normalize_decimal_string(value, field_name, minimum=minimum, max_fraction_digits=max_fraction_digits))


def _normalize_flow_index(value: Any, default_index: int = 0) -> int:
    try:
        numeric = int(str(value if value is not None else default_index).strip() or default_index)
    except Exception:
        numeric = int(default_index)
    return max(0, numeric)


def _normalize_frame(raw_frame: Any, field_name: str) -> dict[str, float]:
    frame = raw_frame if isinstance(raw_frame, dict) else {}
    raw_x = frame.get("x", 0)
    raw_y = frame.get("y", 0)
    raw_width = frame.get("width", 320)
    raw_height = frame.get("height", 120)
    return {
        "x": _normalize_decimal_float(0 if raw_x in (None, "") else raw_x, f"{field_name}.x", minimum="0"),
        "y": _normalize_decimal_float(0 if raw_y in (None, "") else raw_y, f"{field_name}.y", minimum="0"),
        "width": _normalize_decimal_float(320 if raw_width in (None, "") else raw_width, f"{field_name}.width", minimum="1"),
        "height": _normalize_decimal_float(120 if raw_height in (None, "") else raw_height, f"{field_name}.height", minimum="1"),
    }


def _normalize_document_canvas(raw_canvas: Any) -> dict[str, float]:
    canvas = raw_canvas if isinstance(raw_canvas, dict) else {}
    raw_min_height = canvas.get("min_height", canvas.get("minHeight", ANNOUNCEMENT_NOTICE_FLOATING_CANVAS_MIN_HEIGHT))
    return {
        "width": _normalize_decimal_float(canvas.get("width", ANNOUNCEMENT_NOTICE_FLOATING_CANVAS_WIDTH), "body_document.canvas.width", minimum="320"),
        "min_height": _normalize_decimal_float(raw_min_height, "body_document.canvas.min_height", minimum="0"),
        "minHeight": _normalize_decimal_float(raw_min_height, "body_document.canvas.minHeight", minimum="0"),
    }


def _normalize_document_paragraph(raw_paragraph: Any, index: int) -> dict[str, Any] | None:
    if not isinstance(raw_paragraph, dict):
        raw_paragraph = {}
    field_name = f"body_document.paragraphs[{index}]"
    rich_candidate = _candidate_rich_fragment(raw_paragraph)
    if rich_candidate is not None:
        _validate_rich_limit(rich_candidate, ANNOUNCEMENT_NOTICE_PARAGRAPH_RICH_LIMIT, f"{field_name}.rich_text")
        rich_text, text = _canonicalize_rich_fragment(rich_candidate, f"{field_name}.rich_text")
        text = _validate_text_limit(text, ANNOUNCEMENT_NOTICE_PARAGRAPH_TEXT_LIMIT, f"{field_name}.text").strip()
    else:
        rich_text = None
        text = _validate_text_limit(str(raw_paragraph.get("text") or "").strip(), ANNOUNCEMENT_NOTICE_PARAGRAPH_TEXT_LIMIT, f"{field_name}.text").strip()
    if not text:
        return None
    font_size_px = None
    raw_font_size_px = raw_paragraph.get("font_size_px", raw_paragraph.get("fontSizePx"))
    if raw_font_size_px not in (None, ""):
        font_size_px = _normalize_decimal_string(raw_font_size_px, f"{field_name}.font_size_px", minimum="1")
    payload: dict[str, Any] = {
        "id": str(raw_paragraph.get("id") or f"paragraph-{uuid.uuid4().hex[:12]}").strip()[:64],
        "flow_index": _normalize_flow_index(raw_paragraph.get("flow_index", raw_paragraph.get("flowIndex", index)), index),
        "flowIndex": _normalize_flow_index(raw_paragraph.get("flow_index", raw_paragraph.get("flowIndex", index)), index),
        "text": text,
        "rich_text": rich_text,
        "richText": rich_text,
        "align": _normalize_alignment(raw_paragraph.get("align")),
    }
    if font_size_px:
        payload["font_size_px"] = font_size_px
        payload["fontSizePx"] = font_size_px
    return payload


def _normalize_document_object(raw_object: Any, index: int) -> dict[str, Any] | None:
    if not isinstance(raw_object, dict):
        return None
    kind = str(raw_object.get("kind") or "").strip().lower()
    if kind not in {"image", "table", "poll"}:
        return None
    field_name = f"body_document.objects[{index}]"
    payload: dict[str, Any] = {
        "id": str(raw_object.get("id") or f"{kind}-{uuid.uuid4().hex[:12]}").strip()[:64],
        "kind": kind,
        "flow_index": _normalize_flow_index(raw_object.get("flow_index", raw_object.get("flowIndex", index)), index),
        "flowIndex": _normalize_flow_index(raw_object.get("flow_index", raw_object.get("flowIndex", index)), index),
        "zIndex": _normalize_flow_index(raw_object.get("zIndex", raw_object.get("z_index", index)), index),
        "frame": _normalize_frame(raw_object.get("frame"), f"{field_name}.frame"),
    }
    if kind == "image":
        attachment_id = str(raw_object.get("attachment_id") or raw_object.get("attachmentId") or "").strip()
        image_src = str(raw_object.get("image_src") or raw_object.get("imageSrc") or "").strip()
        if not attachment_id and not image_src:
            return None
        payload.update(
            {
                "attachment_id": attachment_id or None,
                "attachmentId": attachment_id or None,
                "file_name": str(raw_object.get("file_name") or raw_object.get("fileName") or "").strip()[:200] or None,
                "fileName": str(raw_object.get("file_name") or raw_object.get("fileName") or "").strip()[:200] or None,
                "caption": str(raw_object.get("caption") or "").strip()[:240] or None,
                "image_src": image_src or None,
                "imageSrc": image_src or None,
            }
        )
        return payload
    if kind == "poll":
        poll = normalize_announcement_notice_poll_block(raw_object.get("poll") or raw_object)
        if not poll:
            return None
        payload["poll"] = poll
        return payload
    table_source = raw_object.get("table") if isinstance(raw_object.get("table"), dict) else raw_object
    table_blocks = normalize_announcement_notice_body_blocks([{"kind": "table", **table_source}])
    if not table_blocks:
        return None
    payload["table"] = {key: value for key, value in table_blocks[0].items() if key != "kind"}
    return payload


def normalize_announcement_notice_body_document(raw_document: Any, *, fallback_body_text: Any = "") -> tuple[dict[str, Any], str]:
    document = parse_json_value(raw_document, fallback={})
    if not isinstance(document, dict):
        document = {}
    version = str(document.get("version") or ANNOUNCEMENT_NOTICE_FLOATING_DOCUMENT_VERSION).strip()
    if version not in {ANNOUNCEMENT_NOTICE_FLOATING_DOCUMENT_VERSION, ANNOUNCEMENT_NOTICE_FLOW_LANE_DOCUMENT_VERSION}:
        version = ANNOUNCEMENT_NOTICE_FLOATING_DOCUMENT_VERSION
    paragraphs: list[dict[str, Any]] = []
    for index, raw_paragraph in enumerate(document.get("paragraphs") or []):
        paragraph = _normalize_document_paragraph(raw_paragraph, index)
        if paragraph:
            paragraphs.append(paragraph)
    objects: list[dict[str, Any]] = []
    for index, raw_object in enumerate(document.get("objects") or []):
        obj = _normalize_document_object(raw_object, index)
        if obj:
            objects.append(obj)
    if not paragraphs and not objects and str(fallback_body_text or "").strip():
        paragraph = _normalize_document_paragraph({"text": str(fallback_body_text or "").strip(), "flow_index": 0}, 0)
        if paragraph:
            paragraphs.append(paragraph)
    normalized = {
        "version": version,
        "canvas": _normalize_document_canvas(document.get("canvas")),
        "paragraphs": paragraphs,
        "objects": objects,
    }
    return normalized, flatten_announcement_notice_body_text_from_document(normalized, fallback_body_text)


def build_announcement_notice_body_blocks_projection_from_document(body_document: Any) -> list[dict[str, Any]]:
    document = body_document if isinstance(body_document, dict) else {}
    items: list[tuple[str, int, dict[str, Any]]] = []
    for paragraph in document.get("paragraphs") or []:
        if isinstance(paragraph, dict):
            items.append(("paragraph", int(paragraph.get("flow_index") or paragraph.get("flowIndex") or 0), paragraph))
    for obj in document.get("objects") or []:
        if isinstance(obj, dict):
            items.append(("object", int(obj.get("flow_index") or obj.get("flowIndex") or 0), obj))
    items.sort(key=lambda item: (item[1], 0 if item[0] == "paragraph" else 1))
    projected: list[dict[str, Any]] = []
    for item_kind, _, item in items:
        if item_kind == "paragraph":
            projected.append(
                {
                    "kind": "paragraph",
                    "variant": "body",
                    "text": str(item.get("text") or "").strip(),
                    "rich_text": item.get("rich_text") or item.get("richText"),
                    "richText": item.get("richText") or item.get("rich_text"),
                    "align": _normalize_alignment(item.get("align")),
                }
            )
            continue
        object_kind = str(item.get("kind") or "").strip().lower()
        if object_kind == "image":
            projected.append(
                {
                    "kind": "image",
                    "attachment_id": item.get("attachment_id") or item.get("attachmentId"),
                    "attachmentId": item.get("attachmentId") or item.get("attachment_id"),
                    "file_name": item.get("file_name") or item.get("fileName"),
                    "fileName": item.get("fileName") or item.get("file_name"),
                    "caption": item.get("caption"),
                    "image_src": item.get("image_src") or item.get("imageSrc"),
                    "imageSrc": item.get("imageSrc") or item.get("image_src"),
                }
            )
        elif object_kind == "table":
            projected.append({"kind": "table", **(item.get("table") or {})})
        elif object_kind == "poll":
            projected.append({"kind": "poll", "poll": item.get("poll") or {}})
    return normalize_announcement_notice_body_blocks(projected)


def flatten_announcement_notice_body_text_from_document(body_document: Any, fallback_body_text: Any = "") -> str:
    return flatten_announcement_notice_body_text(
        build_announcement_notice_body_blocks_projection_from_document(body_document),
        fallback_body_text,
    )


def build_announcement_notice_body_preview_from_document(body_document: Any, fallback_body_text: Any = "") -> str:
    return build_announcement_notice_body_preview(
        flatten_announcement_notice_body_text_from_document(body_document, fallback_body_text),
        [],
    )


def extract_announcement_attachment_ids_from_body_blocks(body_blocks: Any) -> list[str]:
    attachment_ids: list[str] = []
    for block in normalize_announcement_notice_body_blocks(body_blocks):
        if str(block.get("kind") or "").strip() != "image":
            continue
        attachment_id = str(block.get("attachment_id") or block.get("attachmentId") or "").strip()
        if attachment_id and attachment_id not in attachment_ids:
            attachment_ids.append(attachment_id)
    return attachment_ids


def extract_announcement_attachment_ids_from_body_document(body_document: Any) -> list[str]:
    attachment_ids: list[str] = []
    document = body_document if isinstance(body_document, dict) else {}
    for obj in document.get("objects") or []:
        if not isinstance(obj, dict) or str(obj.get("kind") or "").strip() != "image":
            continue
        attachment_id = str(obj.get("attachment_id") or obj.get("attachmentId") or "").strip()
        if attachment_id and attachment_id not in attachment_ids:
            attachment_ids.append(attachment_id)
    return attachment_ids
