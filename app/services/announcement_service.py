from __future__ import annotations

import base64
import json
import mimetypes
import re
import uuid
from typing import Any

from .announcement_documents import (
    ANNOUNCEMENT_NOTICE_BODY_MODEL_LEGACY,
    build_announcement_notice_body_preview,
    build_announcement_notice_body_preview_from_document,
    extract_announcement_attachment_ids_from_body_blocks,
    extract_announcement_attachment_ids_from_body_document,
    flatten_announcement_notice_body_text,
    flatten_announcement_notice_body_text_from_document,
    infer_announcement_notice_body_model_from_document,
    is_structured_announcement_notice_body_model,
    normalize_announcement_notice_body_blocks,
    normalize_announcement_notice_body_document,
    normalize_announcement_notice_body_model,
    normalize_announcement_notice_bool,
    normalize_announcement_notice_category,
    normalize_announcement_notice_search,
    parse_announcement_notice_targets,
)
from .announcement_polls import (
    fetch_announcement_poll_bundle,
    serialize_announcement_datetime,
    sync_announcement_poll_blocks,
    sync_announcement_poll_document,
    vote_announcement_poll,
)

ANNOUNCEMENT_PINNED_LIMIT = 3
ANNOUNCEMENT_IMAGE_MIME_PREFIX = "image/"
ANNOUNCEMENT_ATTACHMENT_MAX_BYTES = 5 * 1024 * 1024


class AnnouncementNotFound(LookupError):
    pass


class AnnouncementValidationError(ValueError):
    pass


def _new_uuid() -> str:
    return str(uuid.uuid4())


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _normalize_user_id(user: dict[str, Any]) -> str:
    return str(user.get("id") or "").strip()


def _normalize_username(user: dict[str, Any]) -> str:
    return str(user.get("username") or "").strip()


def _build_attachment_data_url(mime_type: Any, raw_bytes: Any) -> str | None:
    payload = bytes(raw_bytes or b"")
    normalized_mime = str(mime_type or "").strip().lower()
    if not payload or not normalized_mime.startswith(ANNOUNCEMENT_IMAGE_MIME_PREFIX):
        return None
    encoded = base64.b64encode(payload).decode("ascii")
    return f"data:{normalized_mime};base64,{encoded}"


def _parse_image_data_url(image_src: Any, fallback_name: str = "notice-image.png") -> dict[str, Any] | None:
    raw = str(image_src or "").strip()
    match = re.match(r"^data:(image/[a-zA-Z0-9.+-]+);base64,([A-Za-z0-9+/=\\s]+)$", raw, re.I)
    if not match:
        return None
    content_type = str(match.group(1) or "").strip().lower()
    data_base64 = re.sub(r"\s+", "", str(match.group(2) or "").strip())
    try:
        raw_bytes = base64.b64decode(data_base64, validate=True)
    except Exception as exc:
        raise AnnouncementValidationError("공지 이미지를 읽을 수 없습니다.") from exc
    if not raw_bytes:
        raise AnnouncementValidationError("비어 있는 이미지는 업로드할 수 없습니다.")
    if len(raw_bytes) > ANNOUNCEMENT_ATTACHMENT_MAX_BYTES:
        raise AnnouncementValidationError("이미지 크기는 5MB 이하만 업로드할 수 있습니다.")
    file_name = str(fallback_name or "notice-image.png").strip() or "notice-image.png"
    if "." not in file_name:
        extension = mimetypes.guess_extension(content_type) or ".png"
        file_name = f"{file_name}{extension}"
    return {"file_name": file_name[:200], "mime_type": content_type, "raw_bytes": raw_bytes}


def create_announcement_attachment(
    conn,
    *,
    tenant_id: str,
    actor_id: str,
    file_name: str,
    mime_type: str,
    raw_bytes: bytes,
) -> dict[str, Any]:
    attachment_id = _new_uuid()
    normalized_mime = str(mime_type or "").strip().lower()
    if not normalized_mime.startswith(ANNOUNCEMENT_IMAGE_MIME_PREFIX):
        raise AnnouncementValidationError("공지 이미지는 이미지 파일만 업로드할 수 있습니다.")
    if not raw_bytes:
        raise AnnouncementValidationError("비어 있는 이미지는 업로드할 수 없습니다.")
    if len(raw_bytes) > ANNOUNCEMENT_ATTACHMENT_MAX_BYTES:
        raise AnnouncementValidationError("이미지 크기는 5MB 이하만 업로드할 수 있습니다.")
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO notice_attachments (id, tenant_id, file_name, mime_type, raw_bytes, created_by)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (attachment_id, tenant_id, str(file_name or "notice-image")[:200], normalized_mime, raw_bytes, actor_id),
        )
    return {
        "id": attachment_id,
        "file_name": str(file_name or "notice-image")[:200],
        "fileName": str(file_name or "notice-image")[:200],
        "mime_type": normalized_mime,
        "mimeType": normalized_mime,
        "image_src": _build_attachment_data_url(normalized_mime, raw_bytes),
        "imageSrc": _build_attachment_data_url(normalized_mime, raw_bytes),
    }


def fetch_announcement_attachment_rows(
    conn,
    *,
    tenant_id: str,
    attachment_ids: list[str],
) -> dict[str, dict[str, Any]]:
    normalized_ids = [str(item or "").strip() for item in attachment_ids if str(item or "").strip()]
    if not normalized_ids:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, file_name, mime_type, raw_bytes
            FROM notice_attachments
            WHERE tenant_id = %s
              AND id = ANY(%s)
            """,
            (tenant_id, normalized_ids),
        )
        rows = [dict(row) for row in (cur.fetchall() or [])]
    payload: dict[str, dict[str, Any]] = {}
    for row in rows:
        attachment_id = str(row.get("id") or "").strip()
        image_src = _build_attachment_data_url(row.get("mime_type"), row.get("raw_bytes"))
        payload[attachment_id] = {
            "id": attachment_id,
            "file_name": str(row.get("file_name") or "").strip(),
            "fileName": str(row.get("file_name") or "").strip(),
            "mime_type": str(row.get("mime_type") or "").strip(),
            "mimeType": str(row.get("mime_type") or "").strip(),
            "image_src": image_src,
            "imageSrc": image_src,
            "download_path": image_src,
            "downloadPath": image_src,
        }
    return payload


def _replace_image_blocks(
    conn,
    *,
    tenant_id: str,
    notice_id: str,
    actor_id: str,
    body_blocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    next_blocks: list[dict[str, Any]] = []
    kept_attachment_ids: set[str] = set()
    for block in body_blocks:
        if not isinstance(block, dict) or str(block.get("kind") or "").strip() != "image":
            next_blocks.append(block)
            continue
        next_block = dict(block)
        attachment_id = str(next_block.get("attachment_id") or next_block.get("attachmentId") or "").strip()
        if attachment_id:
            kept_attachment_ids.add(attachment_id)
            next_block["attachment_id"] = attachment_id
            next_block["attachmentId"] = attachment_id
            next_block.pop("image_src", None)
            next_block.pop("imageSrc", None)
            next_blocks.append(next_block)
            continue
        image_src = str(next_block.get("image_src") or next_block.get("imageSrc") or "").strip()
        upload = _parse_image_data_url(image_src, str(next_block.get("file_name") or next_block.get("fileName") or "notice-image.png"))
        if not upload:
            continue
        attachment = create_announcement_attachment(conn, tenant_id=tenant_id, actor_id=actor_id, **upload)
        attachment_id = str(attachment["id"])
        kept_attachment_ids.add(attachment_id)
        next_block["attachment_id"] = attachment_id
        next_block["attachmentId"] = attachment_id
        next_block["file_name"] = attachment["file_name"]
        next_block["fileName"] = attachment["file_name"]
        next_block.pop("image_src", None)
        next_block.pop("imageSrc", None)
        next_blocks.append(next_block)
    _cleanup_unreferenced_attachments(conn, tenant_id=tenant_id, notice_id=notice_id, kept_attachment_ids=kept_attachment_ids)
    return next_blocks


def _replace_document_images(
    conn,
    *,
    tenant_id: str,
    notice_id: str,
    actor_id: str,
    body_document: dict[str, Any],
) -> dict[str, Any]:
    document = dict(body_document or {})
    next_objects: list[dict[str, Any]] = []
    kept_attachment_ids: set[str] = set()
    for obj in list(document.get("objects") or []):
        if not isinstance(obj, dict) or str(obj.get("kind") or "").strip() != "image":
            next_objects.append(obj)
            continue
        next_obj = dict(obj)
        attachment_id = str(next_obj.get("attachment_id") or next_obj.get("attachmentId") or "").strip()
        if attachment_id:
            kept_attachment_ids.add(attachment_id)
            next_obj["attachment_id"] = attachment_id
            next_obj["attachmentId"] = attachment_id
            next_obj.pop("image_src", None)
            next_obj.pop("imageSrc", None)
            next_objects.append(next_obj)
            continue
        image_src = str(next_obj.get("image_src") or next_obj.get("imageSrc") or "").strip()
        upload = _parse_image_data_url(image_src, str(next_obj.get("file_name") or next_obj.get("fileName") or "notice-image.png"))
        if not upload:
            continue
        attachment = create_announcement_attachment(conn, tenant_id=tenant_id, actor_id=actor_id, **upload)
        attachment_id = str(attachment["id"])
        kept_attachment_ids.add(attachment_id)
        next_obj["attachment_id"] = attachment_id
        next_obj["attachmentId"] = attachment_id
        next_obj["file_name"] = attachment["file_name"]
        next_obj["fileName"] = attachment["file_name"]
        next_obj.pop("image_src", None)
        next_obj.pop("imageSrc", None)
        next_objects.append(next_obj)
    document["objects"] = next_objects
    _cleanup_unreferenced_attachments(conn, tenant_id=tenant_id, notice_id=notice_id, kept_attachment_ids=kept_attachment_ids)
    return document


def _cleanup_unreferenced_attachments(conn, *, tenant_id: str, notice_id: str, kept_attachment_ids: set[str]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT body_blocks, body_document
            FROM notices
            WHERE tenant_id = %s
              AND id = %s
            LIMIT 1
            """,
            (tenant_id, notice_id),
        )
        row = cur.fetchone()
    if not row:
        return
    existing_ids = set(extract_announcement_attachment_ids_from_body_blocks(row.get("body_blocks")))
    existing_ids.update(extract_announcement_attachment_ids_from_body_document(row.get("body_document")))
    removable = [item for item in existing_ids if item and item not in kept_attachment_ids]
    if not removable:
        return
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM notice_attachments
            WHERE tenant_id = %s
              AND id = ANY(%s)
            """,
            (tenant_id, removable),
        )


def _inject_attachment_rows_into_blocks(
    body_blocks: list[dict[str, Any]],
    attachment_rows: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    next_blocks: list[dict[str, Any]] = []
    for block in body_blocks:
        if not isinstance(block, dict) or str(block.get("kind") or "").strip() != "image":
            next_blocks.append(block)
            continue
        attachment_id = str(block.get("attachment_id") or block.get("attachmentId") or "").strip()
        row = attachment_rows.get(attachment_id)
        image_block = dict(block)
        if row:
            image_block["file_name"] = row.get("file_name")
            image_block["fileName"] = row.get("file_name")
            image_block["image_src"] = row.get("image_src")
            image_block["imageSrc"] = row.get("image_src")
        next_blocks.append(image_block)
    return next_blocks


def _inject_attachment_rows_into_document(
    body_document: dict[str, Any],
    attachment_rows: dict[str, dict[str, Any]],
    poll_rows: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    document = dict(body_document or {})
    next_objects: list[dict[str, Any]] = []
    for obj in document.get("objects") or []:
        if not isinstance(obj, dict):
            continue
        next_obj = dict(obj)
        kind = str(next_obj.get("kind") or "").strip()
        if kind == "image":
            attachment_id = str(next_obj.get("attachment_id") or next_obj.get("attachmentId") or "").strip()
            row = attachment_rows.get(attachment_id)
            if row:
                next_obj["file_name"] = row.get("file_name")
                next_obj["fileName"] = row.get("file_name")
                next_obj["image_src"] = row.get("image_src")
                next_obj["imageSrc"] = row.get("image_src")
        elif kind == "poll":
            poll = next_obj.get("poll") or {}
            poll_key = str(poll.get("poll_id") or poll.get("pollId") or "").strip()
            next_obj["poll"] = poll_rows.get(poll_key, poll)
        next_objects.append(next_obj)
    document["objects"] = next_objects
    return document


def _announcement_visible_to_user(row: dict[str, Any], user: dict[str, Any]) -> bool:
    target_mode = str(row.get("target_mode") or "all").strip().lower()
    if target_mode != "selected":
        return True
    username = _normalize_username(user)
    targets = set(parse_announcement_notice_targets(row.get("target_usernames")))
    if username and username in targets:
        return True
    return str(row.get("created_by") or "").strip() == _normalize_user_id(user)


def fetch_announcement_row(conn, *, tenant_id: str, announcement_id: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT n.id,
                   n.tenant_id,
                   n.category,
                   n.title,
                   n.body_text,
                   n.body_blocks,
                   n.body_model,
                   n.body_document,
                   n.target_mode,
                   n.target_usernames,
                   n.is_important,
                   n.is_pinned,
                   n.published_at,
                   n.created_by,
                   n.updated_by,
                   n.created_at,
                   n.updated_at,
                   COALESCE(u.full_name, u.username, '-') AS created_by_name,
                   COALESCE(u.username, '') AS sender_username,
                   t.tenant_code
            FROM notices n
            LEFT JOIN arls_users u ON u.id = n.created_by
            LEFT JOIN tenants t ON t.id = n.tenant_id
            WHERE n.tenant_id = %s
              AND n.id = %s
            LIMIT 1
            """,
            (tenant_id, announcement_id),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def list_announcements(
    conn,
    *,
    tenant_id: str,
    user: dict[str, Any],
    category: str = "all",
    q: str = "",
    limit: int = 80,
    scope: str = "all",
) -> dict[str, Any]:
    normalized_category = normalize_announcement_notice_category(category, allow_all=True)
    search = normalize_announcement_notice_search(q)
    normalized_limit = max(1, min(200, int(limit or 80)))
    search_like = f"%{search}%"
    sql = """
        SELECT n.id,
               n.tenant_id,
               n.category,
               n.title,
               n.body_text,
               n.body_blocks,
               n.body_model,
               n.body_document,
               n.target_mode,
               n.target_usernames,
               n.is_important,
               n.is_pinned,
               n.published_at,
               n.created_by,
               n.created_at,
               n.updated_at,
               COALESCE(u.full_name, u.username, '-') AS created_by_name,
               COALESCE(u.username, '') AS sender_username,
               t.tenant_code
        FROM notices n
        LEFT JOIN arls_users u ON u.id = n.created_by
        LEFT JOIN tenants t ON t.id = n.tenant_id
        WHERE n.tenant_id = %s
    """
    params: list[Any] = [tenant_id]
    if str(scope or "").strip().lower() == "mine":
        sql += " AND n.created_by = %s"
        params.append(_normalize_user_id(user))
    if normalized_category != "all":
        sql += " AND n.category = %s"
        params.append(normalized_category)
    if search:
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
    params.append(normalized_limit)
    with conn.cursor() as cur:
        cur.execute(sql, tuple(params))
        rows = [dict(row) for row in (cur.fetchall() or [])]
    items = [map_announcement_summary(row) for row in rows if _announcement_visible_to_user(row, user)]
    return {
        "scope": str(scope or "all").strip().lower() or "all",
        "category": normalized_category,
        "search": search,
        "items": items,
        "rows": items,
        "announcements": items,
    }


def map_announcement_summary(row: dict[str, Any]) -> dict[str, Any]:
    body_model = normalize_announcement_notice_body_model(row.get("body_model"))
    if is_structured_announcement_notice_body_model(body_model) and row.get("body_document"):
        document, _ = normalize_announcement_notice_body_document(
            row.get("body_document"),
            fallback_body_text=row.get("body_text") or "",
        )
        preview = build_announcement_notice_body_preview_from_document(document, row.get("body_text") or "")
    else:
        blocks = normalize_announcement_notice_body_blocks(row.get("body_blocks"), fallback_body_text=row.get("body_text") or "")
        preview = build_announcement_notice_body_preview(row.get("body_text") or "", blocks)
    created_at = serialize_announcement_datetime(row.get("created_at"))
    updated_at = serialize_announcement_datetime(row.get("updated_at")) or created_at
    published_at = serialize_announcement_datetime(row.get("published_at")) or created_at
    targets = parse_announcement_notice_targets(row.get("target_usernames"))
    tenant_id = str(row.get("tenant_code") or row.get("tenant_id") or "").strip()
    payload = {
        "id": str(row.get("id") or "").strip(),
        "title": str(row.get("title") or "").strip(),
        "category": normalize_announcement_notice_category(row.get("category")),
        "body_preview": preview,
        "bodyPreview": preview,
        "body_model": body_model,
        "bodyModel": body_model,
        "message": preview,
        "is_pinned": bool(row.get("is_pinned")),
        "isPinned": bool(row.get("is_pinned")),
        "published_at": published_at,
        "publishedAt": published_at,
        "created_at": created_at,
        "createdAt": created_at,
        "updated_at": updated_at,
        "updatedAt": updated_at,
        "created_by_name": str(row.get("created_by_name") or "").strip() or None,
        "createdByName": str(row.get("created_by_name") or "").strip() or None,
        "sender_name": str(row.get("created_by_name") or "").strip() or None,
        "sender_username": str(row.get("sender_username") or "").strip() or None,
        "target_mode": str(row.get("target_mode") or "all").strip() or "all",
        "targetMode": str(row.get("target_mode") or "all").strip() or "all",
        "targets": targets,
        "tenant_id": tenant_id,
        "tenantId": tenant_id,
        "is_important": bool(row.get("is_important")),
        "isImportant": bool(row.get("is_important")),
        "attachments": [],
    }
    return payload


def map_announcement_detail(
    conn,
    row: dict[str, Any],
    *,
    actor_user_id: str,
) -> dict[str, Any]:
    tenant_id = str(row.get("tenant_id") or "").strip()
    body_model = normalize_announcement_notice_body_model(row.get("body_model"))
    if is_structured_announcement_notice_body_model(body_model) and row.get("body_document"):
        document, _ = normalize_announcement_notice_body_document(row.get("body_document"), fallback_body_text=row.get("body_text") or "")
        attachment_rows = fetch_announcement_attachment_rows(
            conn,
            tenant_id=tenant_id,
            attachment_ids=extract_announcement_attachment_ids_from_body_document(document),
        )
        poll_rows = fetch_announcement_poll_bundle(conn, tenant_id=tenant_id, notice_id=str(row["id"]), user_id=actor_user_id)
        detail_document = _inject_attachment_rows_into_document(document, attachment_rows, poll_rows)
        body_text = flatten_announcement_notice_body_text_from_document(detail_document, row.get("body_text") or "")
        preview = build_announcement_notice_body_preview_from_document(detail_document, row.get("body_text") or "")
        body_blocks: list[dict[str, Any]] = []
    else:
        body_blocks = normalize_announcement_notice_body_blocks(row.get("body_blocks"), fallback_body_text=row.get("body_text") or "")
        attachment_rows = fetch_announcement_attachment_rows(
            conn,
            tenant_id=tenant_id,
            attachment_ids=extract_announcement_attachment_ids_from_body_blocks(body_blocks),
        )
        poll_rows = fetch_announcement_poll_bundle(conn, tenant_id=tenant_id, notice_id=str(row["id"]), user_id=actor_user_id)
        detail_document = None
        body_blocks = _inject_attachment_rows_into_blocks(body_blocks, attachment_rows)
        detail_blocks: list[dict[str, Any]] = []
        for block in body_blocks:
            if str(block.get("kind") or "") == "poll":
                poll = block.get("poll") or {}
                poll_key = str(poll.get("poll_id") or poll.get("pollId") or "").strip()
                detail_blocks.append({"kind": "poll", "poll": poll_rows.get(poll_key, poll)})
            else:
                detail_blocks.append(block)
        body_blocks = detail_blocks
        body_text = flatten_announcement_notice_body_text(body_blocks, row.get("body_text") or "")
        preview = build_announcement_notice_body_preview(body_text, body_blocks)

    summary = map_announcement_summary({**row, "body_text": body_text, "body_model": body_model})
    payload = {
        **summary,
        "message": body_text,
        "body_text": body_text,
        "bodyText": body_text,
        "body_blocks": body_blocks,
        "bodyBlocks": body_blocks,
        "body_model": body_model,
        "bodyModel": body_model,
        "body_document": detail_document,
        "bodyDocument": detail_document,
        "body_preview": preview,
        "bodyPreview": preview,
        "attachments": list(attachment_rows.values()),
    }
    return payload


def _enforce_pinned_limit(conn, *, tenant_id: str, actor_id: str, keep_notice_id: str | None = None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH ranked AS (
              SELECT id,
                     ROW_NUMBER() OVER (
                       ORDER BY
                         CASE WHEN id = %s THEN 0 ELSE 1 END,
                         published_at DESC,
                         created_at DESC,
                         id DESC
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
            (keep_notice_id, tenant_id, actor_id, ANNOUNCEMENT_PINNED_LIMIT),
        )


def _normalize_write_payload(payload: dict[str, Any], *, current_row: dict[str, Any] | None = None) -> dict[str, Any]:
    current_row = current_row or {}
    title = str(payload.get("title", current_row.get("title") or "") or "").strip()
    category = normalize_announcement_notice_category(payload.get("category", current_row.get("category") or "ops"))
    fallback_body_text = (
        payload.get("body_text")
        if "body_text" in payload
        else payload.get("bodyText")
        if "bodyText" in payload
        else payload.get("message", current_row.get("body_text") or "")
    )
    raw_body_document = payload.get("body_document") if "body_document" in payload else payload.get("bodyDocument")
    if raw_body_document is None:
        raw_body_document = current_row.get("body_document")
    requested_model = normalize_announcement_notice_body_model(
        payload.get("body_model") if "body_model" in payload else payload.get("bodyModel", current_row.get("body_model") or "")
    )
    body_model = infer_announcement_notice_body_model_from_document(raw_body_document, requested_model)
    if is_structured_announcement_notice_body_model(body_model) or raw_body_document is not None:
        body_document, body_text = normalize_announcement_notice_body_document(raw_body_document, fallback_body_text=fallback_body_text)
        body_blocks: list[dict[str, Any]] = []
    else:
        raw_body_blocks = payload.get("body_blocks") if "body_blocks" in payload else payload.get("bodyBlocks", current_row.get("body_blocks") or [])
        body_blocks = normalize_announcement_notice_body_blocks(raw_body_blocks, fallback_body_text=fallback_body_text)
        body_document = None
        body_text = flatten_announcement_notice_body_text(body_blocks, fallback_body_text)
        body_model = ANNOUNCEMENT_NOTICE_BODY_MODEL_LEGACY
    target_mode = str(payload.get("target_mode") or payload.get("targetMode") or current_row.get("target_mode") or "all").strip().lower()
    if target_mode not in {"all", "selected"}:
        raise AnnouncementValidationError("대상 구분 값이 올바르지 않습니다.")
    raw_targets = payload.get("target_usernames") if "target_usernames" in payload else payload.get("targets", current_row.get("target_usernames") or [])
    targets = parse_announcement_notice_targets(raw_targets)
    if target_mode == "selected" and not targets:
        raise AnnouncementValidationError("특정 대상 공지는 최소 1명의 계정을 선택해야 합니다.")
    if not title:
        raise AnnouncementValidationError("공지 제목을 입력하세요.")
    has_structured_objects = bool(body_document and list(body_document.get("objects") or []))
    if not body_blocks and not body_text and not has_structured_objects:
        raise AnnouncementValidationError("공지 본문을 입력하세요.")
    return {
        "title": title[:160],
        "category": category,
        "body_text": body_text,
        "body_blocks": body_blocks,
        "body_model": body_model,
        "body_document": body_document,
        "target_mode": target_mode,
        "targets": targets,
        "is_important": normalize_announcement_notice_bool(payload.get("is_important") if "is_important" in payload else payload.get("isImportant", current_row.get("is_important")), False),
        "is_pinned": normalize_announcement_notice_bool(payload.get("is_pinned") if "is_pinned" in payload else payload.get("isPinned", current_row.get("is_pinned")), False),
    }


def create_announcement(
    conn,
    *,
    tenant_id: str,
    user: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    actor_id = _normalize_user_id(user)
    normalized = _normalize_write_payload(payload)
    notice_id = _new_uuid()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO notices (
                id, tenant_id, category, title, body_text, body_blocks, body_model,
                body_document, target_mode, target_usernames, is_important,
                is_pinned, created_by, updated_by
            )
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s::jsonb, %s, %s::jsonb, %s, %s, %s, %s)
            """,
            (
                notice_id,
                tenant_id,
                normalized["category"],
                normalized["title"],
                normalized["body_text"],
                _json_dumps(normalized["body_blocks"]),
                normalized["body_model"],
                _json_dumps(normalized["body_document"]) if normalized["body_document"] else None,
                normalized["target_mode"],
                _json_dumps(normalized["targets"]),
                bool(normalized["is_important"]),
                bool(normalized["is_pinned"]),
                actor_id,
                actor_id,
            ),
        )

    _postprocess_announcement_body(conn, tenant_id=tenant_id, notice_id=notice_id, actor_id=actor_id, normalized=normalized)
    if normalized["is_pinned"]:
        _enforce_pinned_limit(conn, tenant_id=tenant_id, actor_id=actor_id, keep_notice_id=notice_id)
    row = fetch_announcement_row(conn, tenant_id=tenant_id, announcement_id=notice_id)
    if not row:
        raise AnnouncementValidationError("공지 저장에 실패했습니다.")
    return map_announcement_detail(conn, row, actor_user_id=actor_id)


def update_announcement(
    conn,
    *,
    tenant_id: str,
    announcement_id: str,
    user: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    actor_id = _normalize_user_id(user)
    current_row = fetch_announcement_row(conn, tenant_id=tenant_id, announcement_id=announcement_id)
    if not current_row:
        raise AnnouncementNotFound("해당 공지를 찾을 수 없습니다.")
    normalized = _normalize_write_payload(payload, current_row=current_row)
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE notices
            SET category = %s,
                title = %s,
                body_text = %s,
                body_blocks = %s::jsonb,
                body_model = %s,
                body_document = %s::jsonb,
                target_mode = %s,
                target_usernames = %s::jsonb,
                is_important = %s,
                is_pinned = %s,
                updated_at = timezone('utc', now()),
                updated_by = %s
            WHERE tenant_id = %s
              AND id = %s
            """,
            (
                normalized["category"],
                normalized["title"],
                normalized["body_text"],
                _json_dumps(normalized["body_blocks"]),
                normalized["body_model"],
                _json_dumps(normalized["body_document"]) if normalized["body_document"] else None,
                normalized["target_mode"],
                _json_dumps(normalized["targets"]),
                bool(normalized["is_important"]),
                bool(normalized["is_pinned"]),
                actor_id,
                tenant_id,
                announcement_id,
            ),
        )
    _postprocess_announcement_body(conn, tenant_id=tenant_id, notice_id=announcement_id, actor_id=actor_id, normalized=normalized)
    if normalized["is_pinned"]:
        _enforce_pinned_limit(conn, tenant_id=tenant_id, actor_id=actor_id, keep_notice_id=announcement_id)
    row = fetch_announcement_row(conn, tenant_id=tenant_id, announcement_id=announcement_id)
    if not row:
        raise AnnouncementValidationError("공지 수정에 실패했습니다.")
    return map_announcement_detail(conn, row, actor_user_id=actor_id)


def _postprocess_announcement_body(
    conn,
    *,
    tenant_id: str,
    notice_id: str,
    actor_id: str,
    normalized: dict[str, Any],
) -> None:
    if is_structured_announcement_notice_body_model(normalized["body_model"]) and normalized["body_document"]:
        body_document = _replace_document_images(
            conn,
            tenant_id=tenant_id,
            notice_id=notice_id,
            actor_id=actor_id,
            body_document=normalized["body_document"],
        )
        body_document = sync_announcement_poll_document(
            conn,
            tenant_id=tenant_id,
            notice_id=notice_id,
            actor_id=actor_id,
            body_document=body_document,
        )
        body_text = flatten_announcement_notice_body_text_from_document(body_document, normalized["body_text"])
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE notices
                SET body_text = %s,
                    body_blocks = '[]'::jsonb,
                    body_model = %s,
                    body_document = %s::jsonb,
                    updated_at = timezone('utc', now()),
                    updated_by = %s
                WHERE tenant_id = %s
                  AND id = %s
                """,
                (body_text, normalized["body_model"], _json_dumps(body_document), actor_id, tenant_id, notice_id),
            )
        return
    body_blocks = _replace_image_blocks(
        conn,
        tenant_id=tenant_id,
        notice_id=notice_id,
        actor_id=actor_id,
        body_blocks=normalized["body_blocks"],
    )
    body_blocks = sync_announcement_poll_blocks(
        conn,
        tenant_id=tenant_id,
        notice_id=notice_id,
        actor_id=actor_id,
        body_blocks=body_blocks,
    )
    body_text = flatten_announcement_notice_body_text(body_blocks, normalized["body_text"])
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE notices
            SET body_text = %s,
                body_blocks = %s::jsonb,
                body_model = %s,
                body_document = NULL,
                updated_at = timezone('utc', now()),
                updated_by = %s
            WHERE tenant_id = %s
              AND id = %s
            """,
            (body_text, _json_dumps(body_blocks), ANNOUNCEMENT_NOTICE_BODY_MODEL_LEGACY, actor_id, tenant_id, notice_id),
        )


def get_announcement_detail(
    conn,
    *,
    tenant_id: str,
    announcement_id: str,
    user: dict[str, Any],
) -> dict[str, Any]:
    row = fetch_announcement_row(conn, tenant_id=tenant_id, announcement_id=announcement_id)
    if not row or not _announcement_visible_to_user(row, user):
        raise AnnouncementNotFound("해당 공지를 찾을 수 없습니다.")
    return map_announcement_detail(conn, row, actor_user_id=_normalize_user_id(user))


def delete_announcement(conn, *, tenant_id: str, announcement_id: str) -> dict[str, Any]:
    row = fetch_announcement_row(conn, tenant_id=tenant_id, announcement_id=announcement_id)
    if not row:
        raise AnnouncementNotFound("해당 공지를 찾을 수 없습니다.")
    with conn.cursor() as cur:
        cur.execute("DELETE FROM notices WHERE tenant_id = %s AND id = %s", (tenant_id, announcement_id))
    return {"ok": True, "announcement_id": announcement_id, "deleted_attachments": 0}


def vote_announcement(
    conn,
    *,
    tenant_id: str,
    announcement_id: str,
    poll_id: str,
    option_ids: list[str],
    user: dict[str, Any],
) -> dict[str, Any]:
    row = fetch_announcement_row(conn, tenant_id=tenant_id, announcement_id=announcement_id)
    if not row or not _announcement_visible_to_user(row, user):
        raise AnnouncementNotFound("해당 공지를 찾을 수 없습니다.")
    vote_announcement_poll(
        conn,
        tenant_id=tenant_id,
        notice_id=announcement_id,
        poll_key=poll_id,
        option_keys=option_ids,
        user_id=_normalize_user_id(user),
    )
    refreshed = fetch_announcement_row(conn, tenant_id=tenant_id, announcement_id=announcement_id)
    return map_announcement_detail(conn, refreshed or row, actor_user_id=_normalize_user_id(user))
