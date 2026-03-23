from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
import mimetypes
from typing import Any
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status

from ...deps import apply_rate_limit, get_current_user, get_db_conn
from ...schemas import (
    NoticeAttachmentOut,
    NoticeCreateIn,
    NoticeDeleteOut,
    NoticeDetailOut,
    NoticeListOut,
    NoticePollVoteIn,
    NoticeSummaryOut,
    NoticeUpdateIn,
)
from ...utils.permissions import ROLE_BRANCH_MANAGER, ROLE_DEV, normalize_role
from ...utils.tenant_context import resolve_scoped_tenant

router = APIRouter(prefix="/notices", tags=["notices"], dependencies=[Depends(apply_rate_limit)])

NOTICE_CATEGORY_VALUES = {"ops", "attendance", "schedule", "hr", "system", "event"}
NOTICE_BODY_BLOCK_KIND_VALUES = {"paragraph", "image", "table", "poll"}
NOTICE_POLL_RESULT_VISIBILITY_VALUES = {"always", "after_close"}
PINNED_LIMIT = 3
NOTICE_IMAGE_MIME_PREFIX = "image/"
NOTICE_ATTACHMENT_MAX_BYTES = 5 * 1024 * 1024


def _normalize_notice_category(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in NOTICE_CATEGORY_VALUES else "all"


def _ensure_notice_manage_permission(user: dict[str, Any]) -> None:
    if normalize_role(user.get("role")) not in {ROLE_DEV, ROLE_BRANCH_MANAGER}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "FORBIDDEN", "message": "공지 작성 권한이 없습니다."},
        )


def _extract_notice_preview(body_text: str | None) -> str | None:
    raw = " ".join(str(body_text or "").strip().split())
    if not raw:
        return None
    if len(raw) <= 120:
        return raw
    return f"{raw[:117].rstrip()}..."


def _build_notice_attachment_data_url(mime_type: str | None, raw_bytes: bytes | None) -> str | None:
    payload = bytes(raw_bytes or b"")
    normalized_mime = str(mime_type or "").strip().lower()
    if not payload or not normalized_mime.startswith(NOTICE_IMAGE_MIME_PREFIX):
        return None
    encoded = base64.b64encode(payload).decode("ascii")
    return f"data:{normalized_mime};base64,{encoded}"


def _serialize_notice_datetime(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        if not text:
            return None
        normalized = text.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat()


def _parse_notice_datetime(value: Any) -> datetime | None:
    serialized = _serialize_notice_datetime(value)
    if not serialized:
        return None
    try:
        return datetime.fromisoformat(serialized.replace("Z", "+00:00"))
    except ValueError:
        return None


def _fetch_notice_attachment_rows(conn, *, tenant_id: str, attachment_ids: list[str]) -> dict[str, dict[str, Any]]:
    normalized_ids = [str(item or "").strip() for item in attachment_ids if str(item or "").strip()]
    if not normalized_ids:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id,
                   file_name,
                   mime_type,
                   raw_bytes
            FROM notice_attachments
            WHERE tenant_id = %s
              AND id = ANY(%s)
            """,
            (tenant_id, normalized_ids),
        )
        rows = cur.fetchall() or []
    return {str(row.get("id") or "").strip(): dict(row) for row in rows}


def _normalize_notice_body_blocks(
    raw_blocks: Any,
    *,
    fallback_body_text: str | None = None,
    attachment_rows: dict[str, dict[str, Any]] | None = None,
    poll_rows: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    blocks_source: list[Any] = []
    if isinstance(raw_blocks, str):
        try:
            parsed = json.loads(raw_blocks)
        except json.JSONDecodeError:
            parsed = []
        if isinstance(parsed, list):
            blocks_source = parsed
    elif isinstance(raw_blocks, list):
        blocks_source = raw_blocks

    normalized_blocks: list[dict[str, Any]] = []
    for block in blocks_source:
        if hasattr(block, "model_dump"):
            block = block.model_dump()
        if not isinstance(block, dict):
            continue
        kind = str(block.get("kind") or "").strip().lower()
        if kind not in NOTICE_BODY_BLOCK_KIND_VALUES:
            continue
        if kind == "paragraph":
            text = str(block.get("text") or "").strip()
            if not text:
                continue
            variant = str(block.get("variant") or "").strip().lower()
            normalized: dict[str, Any] = {
                "kind": "paragraph",
                "variant": "lead" if variant == "lead" else "body",
                "text": text[:4000],
            }
            title = str(block.get("title") or "").strip()
            if title:
                normalized["title"] = title[:120]
            normalized_blocks.append(normalized)
            continue
        if kind == "image":
            attachment_id = str(block.get("attachment_id") or "").strip()
            image_src = str(block.get("image_src") or "").strip()
            attachment_row = attachment_rows.get(attachment_id) if isinstance(attachment_rows, dict) else None
            if not image_src and attachment_row:
                image_src = str(_build_notice_attachment_data_url(attachment_row.get("mime_type"), attachment_row.get("raw_bytes")) or "").strip()
            if not attachment_id and not image_src:
                continue
            normalized = {
                "kind": "image",
            }
            if attachment_id:
                normalized["attachment_id"] = attachment_id
            file_name = str(
                block.get("file_name")
                or ((attachment_row or {}).get("file_name"))
                or ""
            ).strip()
            if file_name:
                normalized["file_name"] = file_name[:200]
            caption = str(block.get("caption") or "").strip()
            if caption:
                normalized["caption"] = caption[:240]
            if image_src:
                normalized["image_src"] = image_src
            normalized_blocks.append(normalized)
            continue
        if kind == "poll":
            raw_poll = block.get("poll")
            if hasattr(raw_poll, "model_dump"):
                raw_poll = raw_poll.model_dump()
            if not isinstance(raw_poll, dict):
                raw_poll = block
            poll_id = str(raw_poll.get("poll_id") or raw_poll.get("pollId") or "").strip()
            poll_row = poll_rows.get(poll_id) if isinstance(poll_rows, dict) and poll_id else None
            question = str(
                (poll_row or {}).get("question")
                or raw_poll.get("question")
                or ""
            ).strip()
            raw_options = (poll_row or {}).get("options") if poll_row else raw_poll.get("options")
            options: list[dict[str, Any]] = []
            if isinstance(raw_options, list):
                for raw_option in raw_options[:10]:
                    if hasattr(raw_option, "model_dump"):
                        raw_option = raw_option.model_dump()
                    if isinstance(raw_option, dict):
                        option_label = str(raw_option.get("label") or "").strip()
                        option_id = str(raw_option.get("option_id") or raw_option.get("optionId") or raw_option.get("id") or "").strip()
                        if not option_label:
                            continue
                        option_payload: dict[str, Any] = {"label": option_label[:160]}
                        if option_id:
                            option_payload["option_id"] = option_id
                        option_payload["vote_count"] = max(0, int(raw_option.get("vote_count") or 0))
                        option_payload["vote_ratio"] = max(0.0, float(raw_option.get("vote_ratio") or 0))
                        option_payload["selected"] = bool(raw_option.get("selected"))
                        options.append(option_payload)
                        continue
                    option_label = str(raw_option or "").strip()
                    if option_label:
                        options.append({"label": option_label[:160]})
            if not question or len(options) < 2:
                continue
            normalized_poll: dict[str, Any] = {
                "question": question[:240],
                "options": options[:10],
                "allow_multiple": bool(
                    (poll_row or {}).get("allow_multiple")
                    if poll_row
                    else raw_poll.get("allow_multiple")
                ),
                "is_anonymous": bool(
                    (poll_row or {}).get("is_anonymous")
                    if poll_row
                    else raw_poll.get("is_anonymous", True)
                ),
                "result_visibility": str(
                    (poll_row or {}).get("result_visibility")
                    or raw_poll.get("result_visibility")
                    or "always"
                ).strip().lower(),
                "allow_change_vote": bool(
                    (poll_row or {}).get("allow_change_vote")
                    if poll_row
                    else raw_poll.get("allow_change_vote")
                ),
            }
            if normalized_poll["result_visibility"] not in NOTICE_POLL_RESULT_VISIBILITY_VALUES:
                normalized_poll["result_visibility"] = "always"
            closes_at = _serialize_notice_datetime(
                (poll_row or {}).get("closes_at")
                if poll_row
                else raw_poll.get("closes_at")
            )
            if closes_at:
                normalized_poll["closes_at"] = closes_at
            if poll_id:
                normalized_poll["poll_id"] = poll_id
            selected_option_ids = raw_poll.get("selected_option_ids")
            if poll_row:
                selected_option_ids = poll_row.get("selected_option_ids")
            if isinstance(selected_option_ids, list):
                normalized_poll["selected_option_ids"] = [
                    str(item or "").strip()
                    for item in selected_option_ids
                    if str(item or "").strip()
                ][:10]
            normalized_poll["total_votes"] = max(0, int(((poll_row or {}).get("total_votes") if poll_row else raw_poll.get("total_votes")) or 0))
            normalized_poll["results_visible"] = bool(
                (poll_row or {}).get("results_visible")
                if poll_row
                else raw_poll.get("results_visible", True)
            )
            normalized_poll["is_closed"] = bool(
                (poll_row or {}).get("is_closed")
                if poll_row
                else raw_poll.get("is_closed")
            )
            normalized_poll["can_vote"] = bool(
                (poll_row or {}).get("can_vote")
                if poll_row
                else raw_poll.get("can_vote", True)
            )
            normalized_poll["has_voted"] = bool(
                (poll_row or {}).get("has_voted")
                if poll_row
                else raw_poll.get("has_voted")
            )
            normalized_blocks.append({
                "kind": "poll",
                "poll": normalized_poll,
            })
            continue

        title = str(block.get("title") or "").strip()[:120]
        raw_columns = block.get("columns")
        raw_rows = block.get("rows")
        columns = []
        if isinstance(raw_columns, list):
            columns = [str(item or "").strip()[:80] for item in raw_columns[:6]]
        rows_source = raw_rows if isinstance(raw_rows, list) else []
        width = min(
            max(
                len(columns),
                max((len(row) for row in rows_source if isinstance(row, list)), default=0),
            ),
            6,
        )
        if width <= 0:
            continue
        if not columns:
            columns = [f"항목 {index + 1}" for index in range(width)]
        elif len(columns) < width:
            columns = columns + [f"항목 {index + 1}" for index in range(len(columns), width)]
        else:
            columns = columns[:width]

        rows: list[list[str]] = []
        for row in rows_source[:20]:
            if not isinstance(row, list):
                continue
            normalized_row = [str(row[index] or "").strip()[:400] if index < len(row) else "" for index in range(width)]
            if any(normalized_row):
                rows.append(normalized_row)

        if not rows and not any(columns) and not title:
            continue
        normalized = {
            "kind": "table",
            "columns": columns,
            "rows": rows,
        }
        if title:
            normalized["title"] = title
        normalized_blocks.append(normalized)

    fallback = str(fallback_body_text or "").strip()
    if normalized_blocks:
        return normalized_blocks
    if fallback:
        return [{"kind": "paragraph", "variant": "body", "text": fallback[:4000]}]
    return []


def _flatten_notice_body_text(
    body_blocks: list[dict[str, Any]] | None,
    *,
    fallback_body_text: str | None = None,
) -> str:
    blocks = body_blocks or []
    if not blocks:
        return str(fallback_body_text or "").strip()

    chunks: list[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        kind = str(block.get("kind") or "").strip().lower()
        if kind == "paragraph":
            text = str(block.get("text") or "").strip()
            if text:
                chunks.append(text)
            continue
        if kind == "table":
            title = str(block.get("title") or "").strip()
            columns = [str(item or "").strip() for item in (block.get("columns") or []) if str(item or "").strip()]
            rows = block.get("rows") if isinstance(block.get("rows"), list) else []
            if title:
                chunks.append(title)
            if columns:
                chunks.append(" | ".join(columns))
            for row in rows:
                if isinstance(row, list):
                    line = " | ".join(str(cell or "").strip() for cell in row if str(cell or "").strip())
                    if line:
                        chunks.append(line)
            continue
        if kind == "image":
            caption = str(block.get("caption") or "").strip()
            if caption:
                chunks.append(caption)
            continue
        if kind == "poll":
            raw_poll = block.get("poll") if isinstance(block.get("poll"), dict) else {}
            question = str(raw_poll.get("question") or "").strip()
            if question:
                chunks.append(question)
            for option in raw_poll.get("options") or []:
                if isinstance(option, dict):
                    label = str(option.get("label") or "").strip()
                else:
                    label = str(option or "").strip()
                if label:
                    chunks.append(label)
    flattened = "\n\n".join(chunk for chunk in chunks if chunk)
    if flattened:
        return flattened[:20000]
    return str(fallback_body_text or "").strip()[:20000]


def _extract_notice_attachment_ids(raw_blocks: Any) -> list[str]:
    blocks_source = raw_blocks
    if isinstance(raw_blocks, str):
        try:
            blocks_source = json.loads(raw_blocks)
        except json.JSONDecodeError:
            blocks_source = []
    if not isinstance(blocks_source, list):
        return []
    ids: list[str] = []
    for block in blocks_source:
        if hasattr(block, "model_dump"):
            block = block.model_dump()
        if not isinstance(block, dict):
            continue
        if str(block.get("kind") or "").strip().lower() != "image":
            continue
        attachment_id = str(block.get("attachment_id") or "").strip()
        if attachment_id:
            ids.append(attachment_id)
    return ids


def _extract_notice_poll_ids(raw_blocks: Any) -> list[str]:
    blocks_source = raw_blocks
    if isinstance(raw_blocks, str):
        try:
            blocks_source = json.loads(raw_blocks)
        except json.JSONDecodeError:
            blocks_source = []
    if not isinstance(blocks_source, list):
        return []
    ids: list[str] = []
    for block in blocks_source:
        if hasattr(block, "model_dump"):
            block = block.model_dump()
        if not isinstance(block, dict):
            continue
        if str(block.get("kind") or "").strip().lower() != "poll":
            continue
        raw_poll = block.get("poll") if isinstance(block.get("poll"), dict) else block
        poll_id = str(raw_poll.get("poll_id") or raw_poll.get("pollId") or "").strip()
        if poll_id:
            ids.append(poll_id)
    return ids


def _fetch_notice_poll_bundle(
    conn,
    *,
    tenant_id: str,
    notice_id: str,
    user_id: str,
) -> dict[str, dict[str, Any]]:
    target_notice_id = str(notice_id or "").strip()
    if not target_notice_id:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id,
                   notice_id,
                   question,
                   allow_multiple,
                   is_anonymous,
                   result_visibility,
                   closes_at,
                   allow_change_vote
            FROM notice_polls
            WHERE tenant_id = %s
              AND notice_id = %s
            ORDER BY created_at ASC, id ASC
            """,
            (tenant_id, target_notice_id),
        )
        poll_rows = [dict(row) for row in (cur.fetchall() or [])]
    poll_ids = [str(row.get("id") or "").strip() for row in poll_rows if str(row.get("id") or "").strip()]
    if not poll_ids:
        return {}

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id,
                   poll_id,
                   label,
                   sort_order
            FROM notice_poll_options
            WHERE tenant_id = %s
              AND poll_id = ANY(%s)
            ORDER BY sort_order ASC, created_at ASC, id ASC
            """,
            (tenant_id, poll_ids),
        )
        option_rows = [dict(row) for row in (cur.fetchall() or [])]
        cur.execute(
            """
            SELECT poll_id,
                   option_id,
                   COUNT(*)::int AS vote_count
            FROM notice_poll_votes
            WHERE tenant_id = %s
              AND poll_id = ANY(%s)
            GROUP BY poll_id, option_id
            """,
            (tenant_id, poll_ids),
        )
        option_count_rows = [dict(row) for row in (cur.fetchall() or [])]
        cur.execute(
            """
            SELECT poll_id,
                   COUNT(DISTINCT user_id)::int AS total_votes
            FROM notice_poll_votes
            WHERE tenant_id = %s
              AND poll_id = ANY(%s)
            GROUP BY poll_id
            """,
            (tenant_id, poll_ids),
        )
        total_vote_rows = [dict(row) for row in (cur.fetchall() or [])]
        cur.execute(
            """
            SELECT poll_id,
                   option_id
            FROM notice_poll_votes
            WHERE tenant_id = %s
              AND poll_id = ANY(%s)
              AND user_id = %s
            """,
            (tenant_id, poll_ids, user_id),
        )
        user_vote_rows = [dict(row) for row in (cur.fetchall() or [])]

    option_rows_by_poll: dict[str, list[dict[str, Any]]] = {}
    for row in option_rows:
        poll_id = str(row.get("poll_id") or "").strip()
        if not poll_id:
            continue
        option_rows_by_poll.setdefault(poll_id, []).append(row)

    option_counts: dict[tuple[str, str], int] = {}
    for row in option_count_rows:
        poll_id = str(row.get("poll_id") or "").strip()
        option_id = str(row.get("option_id") or "").strip()
        if not poll_id or not option_id:
            continue
        option_counts[(poll_id, option_id)] = max(0, int(row.get("vote_count") or 0))

    total_votes_by_poll = {
        str(row.get("poll_id") or "").strip(): max(0, int(row.get("total_votes") or 0))
        for row in total_vote_rows
        if str(row.get("poll_id") or "").strip()
    }

    selected_option_ids_by_poll: dict[str, list[str]] = {}
    for row in user_vote_rows:
        poll_id = str(row.get("poll_id") or "").strip()
        option_id = str(row.get("option_id") or "").strip()
        if not poll_id or not option_id:
            continue
        selected_option_ids_by_poll.setdefault(poll_id, []).append(option_id)

    now_utc = datetime.now(timezone.utc)
    bundle: dict[str, dict[str, Any]] = {}
    for poll_row in poll_rows:
        poll_id = str(poll_row.get("id") or "").strip()
        if not poll_id:
            continue
        closes_at = _parse_notice_datetime(poll_row.get("closes_at"))
        is_closed = bool(closes_at and closes_at <= now_utc)
        has_voted = bool(selected_option_ids_by_poll.get(poll_id))
        results_visible = str(poll_row.get("result_visibility") or "always").strip().lower() == "always" or is_closed
        participant_count = total_votes_by_poll.get(poll_id, 0)
        options: list[dict[str, Any]] = []
        for option_row in option_rows_by_poll.get(poll_id, []):
            option_id = str(option_row.get("id") or "").strip()
            vote_count = option_counts.get((poll_id, option_id), 0)
            vote_ratio = (vote_count / participant_count) if participant_count > 0 else 0
            options.append(
                {
                    "option_id": option_id,
                    "label": str(option_row.get("label") or "").strip()[:160],
                    "vote_count": vote_count if results_visible else 0,
                    "vote_ratio": vote_ratio if results_visible else 0,
                    "selected": option_id in selected_option_ids_by_poll.get(poll_id, []),
                }
            )
        bundle[poll_id] = {
            "poll_id": poll_id,
            "question": str(poll_row.get("question") or "").strip()[:240],
            "options": options,
            "allow_multiple": bool(poll_row.get("allow_multiple")),
            "is_anonymous": bool(poll_row.get("is_anonymous")),
            "result_visibility": str(poll_row.get("result_visibility") or "always").strip().lower() or "always",
            "closes_at": _serialize_notice_datetime(closes_at),
            "allow_change_vote": bool(poll_row.get("allow_change_vote")),
            "total_votes": participant_count if results_visible else 0,
            "selected_option_ids": selected_option_ids_by_poll.get(poll_id, [])[:10],
            "results_visible": results_visible,
            "is_closed": is_closed,
            "can_vote": (not is_closed) and (not has_voted or bool(poll_row.get("allow_change_vote"))),
            "has_voted": has_voted,
        }
    return bundle


def _sync_notice_poll_blocks(
    conn,
    *,
    tenant_id: str,
    notice_id: str,
    actor_id: str,
    body_blocks: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    normalized_blocks = body_blocks or []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id
            FROM notice_polls
            WHERE tenant_id = %s
              AND notice_id = %s
            ORDER BY created_at ASC, id ASC
            """,
            (tenant_id, notice_id),
        )
        existing_poll_rows = [dict(row) for row in (cur.fetchall() or [])]
    existing_poll_ids = [str(row.get("id") or "").strip() for row in existing_poll_rows if str(row.get("id") or "").strip()]
    existing_option_rows: list[dict[str, Any]] = []
    if existing_poll_ids:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id,
                       poll_id,
                       label
                FROM notice_poll_options
                WHERE tenant_id = %s
                  AND poll_id = ANY(%s)
                ORDER BY sort_order ASC, created_at ASC, id ASC
                """,
                (tenant_id, existing_poll_ids),
            )
            existing_option_rows = [dict(row) for row in (cur.fetchall() or [])]
    existing_option_ids_by_poll: dict[str, set[str]] = {}
    for row in existing_option_rows:
        poll_id = str(row.get("poll_id") or "").strip()
        option_id = str(row.get("id") or "").strip()
        if not poll_id or not option_id:
            continue
        existing_option_ids_by_poll.setdefault(poll_id, set()).add(option_id)

    synced_blocks: list[dict[str, Any]] = []
    used_poll_ids: list[str] = []
    for block in normalized_blocks:
        if not isinstance(block, dict) or str(block.get("kind") or "").strip().lower() != "poll":
            synced_blocks.append(block)
            continue
        raw_poll = block.get("poll") if isinstance(block.get("poll"), dict) else {}
        incoming_poll_id = str(raw_poll.get("poll_id") or raw_poll.get("pollId") or "").strip()
        poll_id = incoming_poll_id if incoming_poll_id in existing_poll_ids else str(uuid.uuid4())
        allow_multiple = bool(raw_poll.get("allow_multiple"))
        is_anonymous = bool(raw_poll.get("is_anonymous", True))
        result_visibility = str(raw_poll.get("result_visibility") or "always").strip().lower()
        if result_visibility not in NOTICE_POLL_RESULT_VISIBILITY_VALUES:
            result_visibility = "always"
        closes_at = _parse_notice_datetime(raw_poll.get("closes_at"))
        allow_change_vote = bool(raw_poll.get("allow_change_vote"))
        question = str(raw_poll.get("question") or "").strip()[:240]
        raw_options = raw_poll.get("options") if isinstance(raw_poll.get("options"), list) else []
        option_payloads: list[dict[str, Any]] = []
        for index, raw_option in enumerate(raw_options[:10]):
            if hasattr(raw_option, "model_dump"):
                raw_option = raw_option.model_dump()
            if not isinstance(raw_option, dict):
                option_label = str(raw_option or "").strip()
                raw_option = {"label": option_label}
            option_label = str(raw_option.get("label") or "").strip()[:160]
            if not option_label:
                continue
            incoming_option_id = str(raw_option.get("option_id") or raw_option.get("optionId") or raw_option.get("id") or "").strip()
            existing_option_ids = existing_option_ids_by_poll.get(poll_id, set())
            option_id = incoming_option_id if incoming_option_id in existing_option_ids else str(uuid.uuid4())
            option_payloads.append(
                {
                    "option_id": option_id,
                    "label": option_label,
                    "sort_order": index,
                }
            )
        if not question or len(option_payloads) < 2:
            continue

        with conn.cursor() as cur:
            if poll_id in existing_poll_ids:
                cur.execute(
                    """
                    UPDATE notice_polls
                    SET question = %s,
                        allow_multiple = %s,
                        is_anonymous = %s,
                        result_visibility = %s,
                        closes_at = %s,
                        allow_change_vote = %s,
                        updated_at = timezone('utc', now()),
                        updated_by = %s
                    WHERE tenant_id = %s
                      AND notice_id = %s
                      AND id = %s
                    """,
                    (
                        question,
                        allow_multiple,
                        is_anonymous,
                        result_visibility,
                        closes_at,
                        allow_change_vote,
                        actor_id,
                        tenant_id,
                        notice_id,
                        poll_id,
                    ),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO notice_polls (
                        id,
                        tenant_id,
                        notice_id,
                        question,
                        allow_multiple,
                        is_anonymous,
                        result_visibility,
                        closes_at,
                        allow_change_vote,
                        created_by,
                        updated_by
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        poll_id,
                        tenant_id,
                        notice_id,
                        question,
                        allow_multiple,
                        is_anonymous,
                        result_visibility,
                        closes_at,
                        allow_change_vote,
                        actor_id,
                        actor_id,
                    ),
                )

        kept_option_ids = [row["option_id"] for row in option_payloads]
        existing_option_ids = existing_option_ids_by_poll.get(poll_id, set())
        with conn.cursor() as cur:
            for option_payload in option_payloads:
                if option_payload["option_id"] in existing_option_ids:
                    cur.execute(
                        """
                        UPDATE notice_poll_options
                        SET label = %s,
                            sort_order = %s
                        WHERE tenant_id = %s
                          AND poll_id = %s
                          AND id = %s
                        """,
                        (
                            option_payload["label"],
                            option_payload["sort_order"],
                            tenant_id,
                            poll_id,
                            option_payload["option_id"],
                        ),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO notice_poll_options (
                            id,
                            tenant_id,
                            poll_id,
                            label,
                            sort_order
                        )
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (
                            option_payload["option_id"],
                            tenant_id,
                            poll_id,
                            option_payload["label"],
                            option_payload["sort_order"],
                        ),
                    )
            if existing_option_ids:
                cur.execute(
                    """
                    DELETE FROM notice_poll_options
                    WHERE tenant_id = %s
                      AND poll_id = %s
                      AND NOT (id = ANY(%s))
                    """,
                    (tenant_id, poll_id, kept_option_ids),
                )

        synced_blocks.append(
            {
                "kind": "poll",
                "poll": {
                    "poll_id": poll_id,
                    "question": question,
                    "options": [{"option_id": item["option_id"], "label": item["label"]} for item in option_payloads],
                    "allow_multiple": allow_multiple,
                    "is_anonymous": is_anonymous,
                    "result_visibility": result_visibility,
                    "closes_at": _serialize_notice_datetime(closes_at),
                    "allow_change_vote": allow_change_vote,
                },
            }
        )
        used_poll_ids.append(poll_id)

    with conn.cursor() as cur:
        if used_poll_ids:
            cur.execute(
                """
                DELETE FROM notice_polls
                WHERE tenant_id = %s
                  AND notice_id = %s
                  AND NOT (id = ANY(%s))
                """,
                (tenant_id, notice_id, used_poll_ids),
            )
        else:
            cur.execute(
                """
                DELETE FROM notice_polls
                WHERE tenant_id = %s
                  AND notice_id = %s
                """,
                (tenant_id, notice_id),
            )
    return synced_blocks


def _map_notice_summary(row: dict[str, Any]) -> NoticeSummaryOut:
    return NoticeSummaryOut(
        id=row["id"],
        category=str(row.get("category") or "ops").strip() or "ops",
        title=str(row.get("title") or "").strip() or "-",
        body_preview=_extract_notice_preview(row.get("body_text")),
        is_pinned=bool(row.get("is_pinned")),
        published_at=row["published_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        created_by_name=str(row.get("created_by_name") or "").strip() or None,
    )


def _map_notice_detail(
    row: dict[str, Any],
    *,
    attachment_rows: dict[str, dict[str, Any]] | None = None,
    poll_rows: dict[str, dict[str, Any]] | None = None,
) -> NoticeDetailOut:
    body_blocks = _normalize_notice_body_blocks(
        row.get("body_blocks"),
        fallback_body_text=row.get("body_text"),
        attachment_rows=attachment_rows,
        poll_rows=poll_rows,
    )
    body_text = _flatten_notice_body_text(body_blocks, fallback_body_text=row.get("body_text"))
    return NoticeDetailOut(
        id=row["id"],
        category=str(row.get("category") or "ops").strip() or "ops",
        title=str(row.get("title") or "").strip() or "-",
        body_text=body_text,
        body_blocks=body_blocks,
        body_preview=_extract_notice_preview(body_text),
        is_pinned=bool(row.get("is_pinned")),
        published_at=row["published_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        created_by_name=str(row.get("created_by_name") or "").strip() or None,
    )


def _fetch_notice_row(conn, *, tenant_id: str, notice_id: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT n.id,
                   n.category,
                   n.title,
                   n.body_text,
                   n.body_blocks,
                   n.is_pinned,
                   n.published_at,
                   n.created_at,
                   n.updated_at,
                   COALESCE(u.full_name, u.username, '-') AS created_by_name
            FROM notices n
            LEFT JOIN arls_users u
              ON u.id = n.created_by
            WHERE n.tenant_id = %s
              AND n.id = %s
            LIMIT 1
            """,
            (tenant_id, notice_id),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def _fetch_notice_rows(
    conn,
    *,
    tenant_id: str,
    category: str = "all",
    query: str = "",
    limit: int = 80,
) -> list[dict[str, Any]]:
    normalized_category = _normalize_notice_category(category)
    normalized_query = str(query or "").strip()
    search_like = f"%{normalized_query}%"
    sql = """
        SELECT n.id,
               n.category,
               n.title,
               n.body_text,
               n.is_pinned,
               n.published_at,
               n.created_at,
               n.updated_at,
               COALESCE(u.full_name, u.username, '-') AS created_by_name
        FROM notices n
        LEFT JOIN arls_users u
          ON u.id = n.created_by
        WHERE n.tenant_id = %s
    """
    params: list[Any] = [tenant_id]
    if normalized_category != "all":
        sql += " AND n.category = %s"
        params.append(normalized_category)
    if normalized_query:
        sql += """
            AND (
              n.title ILIKE %s
              OR n.body_text ILIKE %s
            )
        """
        params.extend([search_like, search_like])
    sql += """
        ORDER BY n.is_pinned DESC, n.published_at DESC, n.created_at DESC, n.id DESC
        LIMIT %s
    """
    params.append(int(limit))

    with conn.cursor() as cur:
        cur.execute(sql, tuple(params))
        return [dict(row) for row in (cur.fetchall() or [])]


def _enforce_pinned_limit(conn, *, tenant_id: str, actor_id: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH ranked AS (
              SELECT id,
                     ROW_NUMBER() OVER (
                       ORDER BY published_at DESC, created_at DESC, id DESC
                     ) AS row_rank
              FROM notices
              WHERE tenant_id = %s
                AND is_pinned = TRUE
            )
            UPDATE notices AS n
            SET is_pinned = FALSE,
                updated_at = timezone('utc', now()),
                updated_by = %s
            FROM ranked
            WHERE n.id = ranked.id
              AND ranked.row_rank > %s
              AND n.is_pinned = TRUE
            """,
            (tenant_id, actor_id, PINNED_LIMIT),
        )


@router.get("/home-teaser", response_model=NoticeListOut)
def list_notice_home_teaser(
    limit: int = Query(default=3, ge=1, le=5),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant = resolve_scoped_tenant(
        conn,
        user,
        header_tenant_id=user.get("active_tenant_id"),
        require_dev_context=True,
    )
    tenant_id = str(tenant.get("id") or "").strip()

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT n.id,
                   n.category,
                   n.title,
                   n.body_text,
                   n.is_pinned,
                   n.published_at,
                   n.created_at,
                   n.updated_at,
                   COALESCE(u.full_name, u.username, '-') AS created_by_name
            FROM notices n
            LEFT JOIN arls_users u
              ON u.id = n.created_by
            WHERE n.tenant_id = %s
            ORDER BY n.is_pinned DESC, n.published_at DESC, n.created_at DESC, n.id DESC
            LIMIT %s
            """,
            (tenant_id, int(limit)),
        )
        rows = [dict(row) for row in (cur.fetchall() or [])]

    return NoticeListOut(items=[_map_notice_summary(row) for row in rows])


@router.get("", response_model=NoticeListOut)
def list_notices(
    category: str = Query(default="all"),
    q: str = Query(default="", max_length=120),
    limit: int = Query(default=80, ge=1, le=200),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant = resolve_scoped_tenant(
        conn,
        user,
        header_tenant_id=user.get("active_tenant_id"),
        require_dev_context=True,
    )
    tenant_id = str(tenant.get("id") or "").strip()
    rows = _fetch_notice_rows(
        conn,
        tenant_id=tenant_id,
        category=category,
        query=q,
        limit=limit,
    )

    return NoticeListOut(items=[_map_notice_summary(row) for row in rows])


@router.post("/attachments", response_model=NoticeAttachmentOut, status_code=status.HTTP_201_CREATED)
async def upload_notice_attachment(
    file: UploadFile | None = File(default=None),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _ensure_notice_manage_permission(user)
    tenant = resolve_scoped_tenant(
        conn,
        user,
        header_tenant_id=user.get("active_tenant_id"),
        require_dev_context=True,
    )
    tenant_id = str(tenant.get("id") or "").strip()
    actor_id = str(user.get("id") or "").strip()

    if file is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "VALIDATION_ERROR", "message": "이미지 파일을 선택해 주세요."},
        )

    file_name = str(file.filename or "notice-image").strip() or "notice-image"
    mime_type = str(file.content_type or mimetypes.guess_type(file_name)[0] or "").strip().lower()
    if not mime_type.startswith(NOTICE_IMAGE_MIME_PREFIX):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "VALIDATION_ERROR", "message": "이미지 파일만 첨부할 수 있습니다."},
        )

    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "VALIDATION_ERROR", "message": "비어 있는 이미지는 업로드할 수 없습니다."},
        )
    if len(raw_bytes) > NOTICE_ATTACHMENT_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "VALIDATION_ERROR", "message": "이미지 크기는 5MB 이하만 업로드할 수 있습니다."},
        )

    attachment_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO notice_attachments (
                id,
                tenant_id,
                file_name,
                mime_type,
                raw_bytes,
                created_by
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (attachment_id, tenant_id, file_name[:200], mime_type, raw_bytes, actor_id),
        )

    image_src = _build_notice_attachment_data_url(mime_type, raw_bytes)
    if not image_src:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "NOTICE_ATTACHMENT_FAILED", "message": "이미지 변환에 실패했습니다."},
        )

    return NoticeAttachmentOut(
        id=attachment_id,
        file_name=file_name[:200],
        mime_type=mime_type,
        image_src=image_src,
    )


@router.get("/{notice_id}", response_model=NoticeDetailOut)
def get_notice_detail(
    notice_id: str,
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant = resolve_scoped_tenant(
        conn,
        user,
        header_tenant_id=user.get("active_tenant_id"),
        require_dev_context=True,
    )
    tenant_id = str(tenant.get("id") or "").strip()
    row = _fetch_notice_row(conn, tenant_id=tenant_id, notice_id=notice_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NOT_FOUND", "message": "공지사항을 찾을 수 없습니다."},
        )
    actor_id = str(user.get("id") or "").strip()
    attachment_rows = _fetch_notice_attachment_rows(
        conn,
        tenant_id=tenant_id,
        attachment_ids=_extract_notice_attachment_ids(row.get("body_blocks")),
    )
    poll_rows = _fetch_notice_poll_bundle(
        conn,
        tenant_id=tenant_id,
        notice_id=notice_id,
        user_id=actor_id,
    )
    return _map_notice_detail(row, attachment_rows=attachment_rows, poll_rows=poll_rows)


@router.post("", response_model=NoticeDetailOut, status_code=status.HTTP_201_CREATED)
def create_notice(
    payload: NoticeCreateIn,
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _ensure_notice_manage_permission(user)
    tenant = resolve_scoped_tenant(
        conn,
        user,
        header_tenant_id=user.get("active_tenant_id"),
        require_dev_context=True,
    )
    tenant_id = str(tenant.get("id") or "").strip()
    actor_id = str(user.get("id") or "").strip()
    body_blocks = _normalize_notice_body_blocks(payload.body_blocks, fallback_body_text=payload.body_text)
    body_text = _flatten_notice_body_text(body_blocks, fallback_body_text=payload.body_text)

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO notices (
                tenant_id,
                category,
                title,
                body_text,
                body_blocks,
                is_pinned,
                created_by,
                updated_by
            )
            VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s)
            RETURNING id
            """,
            (
                tenant_id,
                payload.category,
                payload.title,
                body_text,
                json.dumps(body_blocks, ensure_ascii=False),
                bool(payload.is_pinned),
                actor_id,
                actor_id,
            ),
        )
        created_row = cur.fetchone() or {}
        created_id = str(created_row.get("id") or "").strip()

    body_blocks = _sync_notice_poll_blocks(
        conn,
        tenant_id=tenant_id,
        notice_id=created_id,
        actor_id=actor_id,
        body_blocks=body_blocks,
    )
    body_text = _flatten_notice_body_text(body_blocks, fallback_body_text=payload.body_text)
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE notices
            SET body_text = %s,
                body_blocks = %s::jsonb,
                updated_at = timezone('utc', now()),
                updated_by = %s
            WHERE tenant_id = %s
              AND id = %s
            """,
            (
                body_text,
                json.dumps(body_blocks, ensure_ascii=False),
                actor_id,
                tenant_id,
                created_id,
            ),
        )

    if payload.is_pinned:
        _enforce_pinned_limit(conn, tenant_id=tenant_id, actor_id=actor_id)

    row = _fetch_notice_row(conn, tenant_id=tenant_id, notice_id=created_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "NOTICE_CREATE_FAILED", "message": "공지 저장에 실패했습니다."},
        )
    attachment_rows = _fetch_notice_attachment_rows(
        conn,
        tenant_id=tenant_id,
        attachment_ids=_extract_notice_attachment_ids(row.get("body_blocks")),
    )
    poll_rows = _fetch_notice_poll_bundle(
        conn,
        tenant_id=tenant_id,
        notice_id=created_id,
        user_id=actor_id,
    )
    return _map_notice_detail(row, attachment_rows=attachment_rows, poll_rows=poll_rows)


@router.patch("/{notice_id}", response_model=NoticeDetailOut)
def update_notice(
    notice_id: str,
    payload: NoticeUpdateIn,
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _ensure_notice_manage_permission(user)
    tenant = resolve_scoped_tenant(
        conn,
        user,
        header_tenant_id=user.get("active_tenant_id"),
        require_dev_context=True,
    )
    tenant_id = str(tenant.get("id") or "").strip()
    actor_id = str(user.get("id") or "").strip()
    body_blocks = _normalize_notice_body_blocks(payload.body_blocks, fallback_body_text=payload.body_text)
    if not _fetch_notice_row(conn, tenant_id=tenant_id, notice_id=notice_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NOT_FOUND", "message": "공지사항을 찾을 수 없습니다."},
        )

    body_blocks = _sync_notice_poll_blocks(
        conn,
        tenant_id=tenant_id,
        notice_id=notice_id,
        actor_id=actor_id,
        body_blocks=body_blocks,
    )
    body_text = _flatten_notice_body_text(body_blocks, fallback_body_text=payload.body_text)

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE notices
            SET category = %s,
                title = %s,
                body_text = %s,
                body_blocks = %s::jsonb,
                is_pinned = %s,
                updated_at = timezone('utc', now()),
                updated_by = %s
            WHERE tenant_id = %s
              AND id = %s
            """,
            (
                payload.category,
                payload.title,
                body_text,
                json.dumps(body_blocks, ensure_ascii=False),
                bool(payload.is_pinned),
                actor_id,
                tenant_id,
                notice_id,
            ),
        )

    if payload.is_pinned:
        _enforce_pinned_limit(conn, tenant_id=tenant_id, actor_id=actor_id)

    row = _fetch_notice_row(conn, tenant_id=tenant_id, notice_id=notice_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "NOTICE_UPDATE_FAILED", "message": "공지 수정에 실패했습니다."},
        )
    attachment_rows = _fetch_notice_attachment_rows(
        conn,
        tenant_id=tenant_id,
        attachment_ids=_extract_notice_attachment_ids(row.get("body_blocks")),
    )
    poll_rows = _fetch_notice_poll_bundle(
        conn,
        tenant_id=tenant_id,
        notice_id=notice_id,
        user_id=actor_id,
    )
    return _map_notice_detail(row, attachment_rows=attachment_rows, poll_rows=poll_rows)


@router.post("/{notice_id}/polls/{poll_id}/vote", response_model=NoticeDetailOut)
def vote_notice_poll(
    notice_id: str,
    poll_id: str,
    payload: NoticePollVoteIn,
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant = resolve_scoped_tenant(
        conn,
        user,
        header_tenant_id=user.get("active_tenant_id"),
        require_dev_context=True,
    )
    tenant_id = str(tenant.get("id") or "").strip()
    actor_id = str(user.get("id") or "").strip()
    row = _fetch_notice_row(conn, tenant_id=tenant_id, notice_id=notice_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NOT_FOUND", "message": "공지사항을 찾을 수 없습니다."},
        )
    poll_rows = _fetch_notice_poll_bundle(
        conn,
        tenant_id=tenant_id,
        notice_id=notice_id,
        user_id=actor_id,
    )
    selected_poll = poll_rows.get(str(poll_id or "").strip())
    if not selected_poll:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NOT_FOUND", "message": "투표 항목을 찾을 수 없습니다."},
        )
    if bool(selected_poll.get("is_closed")):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "NOTICE_POLL_CLOSED", "message": "이미 마감된 투표입니다."},
        )
    if bool(selected_poll.get("has_voted")) and not bool(selected_poll.get("allow_change_vote")):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "NOTICE_POLL_LOCKED", "message": "이미 참여한 투표라 다시 선택할 수 없습니다."},
        )

    option_ids = [
        str(item or "").strip()
        for item in (payload.option_ids or [])
        if str(item or "").strip()
    ]
    valid_option_ids = {
        str(option.get("option_id") or "").strip()
        for option in (selected_poll.get("options") or [])
        if str(option.get("option_id") or "").strip()
    }
    if not option_ids or any(option_id not in valid_option_ids for option_id in option_ids):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "VALIDATION_ERROR", "message": "투표 항목을 다시 선택해 주세요."},
        )
    if not bool(selected_poll.get("allow_multiple")) and len(option_ids) != 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "VALIDATION_ERROR", "message": "단일 선택 투표는 1개 항목만 선택할 수 있습니다."},
        )

    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM notice_poll_votes
            WHERE tenant_id = %s
              AND poll_id = %s
              AND user_id = %s
            """,
            (tenant_id, poll_id, actor_id),
        )
        for option_id in option_ids:
            cur.execute(
                """
                INSERT INTO notice_poll_votes (
                    id,
                    tenant_id,
                    poll_id,
                    option_id,
                    user_id
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (str(uuid.uuid4()), tenant_id, poll_id, option_id, actor_id),
            )

    attachment_rows = _fetch_notice_attachment_rows(
        conn,
        tenant_id=tenant_id,
        attachment_ids=_extract_notice_attachment_ids(row.get("body_blocks")),
    )
    refreshed_poll_rows = _fetch_notice_poll_bundle(
        conn,
        tenant_id=tenant_id,
        notice_id=notice_id,
        user_id=actor_id,
    )
    refreshed_row = _fetch_notice_row(conn, tenant_id=tenant_id, notice_id=notice_id) or row
    return _map_notice_detail(refreshed_row, attachment_rows=attachment_rows, poll_rows=refreshed_poll_rows)


@router.delete("/{notice_id}", response_model=NoticeDeleteOut)
def delete_notice(
    notice_id: str,
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _ensure_notice_manage_permission(user)
    tenant = resolve_scoped_tenant(
        conn,
        user,
        header_tenant_id=user.get("active_tenant_id"),
        require_dev_context=True,
    )
    tenant_id = str(tenant.get("id") or "").strip()
    if not _fetch_notice_row(conn, tenant_id=tenant_id, notice_id=notice_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NOT_FOUND", "message": "공지사항을 찾을 수 없습니다."},
        )

    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM notices
            WHERE tenant_id = %s
              AND id = %s
            """,
            (tenant_id, notice_id),
        )

    return NoticeDeleteOut(deleted=True, id=notice_id)
