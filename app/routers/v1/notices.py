from __future__ import annotations

import base64
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
    NoticeSummaryOut,
    NoticeUpdateIn,
)
from ...utils.permissions import ROLE_BRANCH_MANAGER, ROLE_DEV, normalize_role
from ...utils.tenant_context import resolve_scoped_tenant

router = APIRouter(prefix="/notices", tags=["notices"], dependencies=[Depends(apply_rate_limit)])

NOTICE_CATEGORY_VALUES = {"ops", "attendance", "schedule", "hr", "system", "event"}
NOTICE_BODY_BLOCK_KIND_VALUES = {"paragraph", "image", "table"}
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


def _map_notice_detail(row: dict[str, Any], *, attachment_rows: dict[str, dict[str, Any]] | None = None) -> NoticeDetailOut:
    body_blocks = _normalize_notice_body_blocks(
        row.get("body_blocks"),
        fallback_body_text=row.get("body_text"),
        attachment_rows=attachment_rows,
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
    attachment_rows = _fetch_notice_attachment_rows(
        conn,
        tenant_id=tenant_id,
        attachment_ids=_extract_notice_attachment_ids(row.get("body_blocks")),
    )
    return _map_notice_detail(row, attachment_rows=attachment_rows)


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
    return _map_notice_detail(row, attachment_rows=attachment_rows)


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
    body_text = _flatten_notice_body_text(body_blocks, fallback_body_text=payload.body_text)
    if not _fetch_notice_row(conn, tenant_id=tenant_id, notice_id=notice_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NOT_FOUND", "message": "공지사항을 찾을 수 없습니다."},
        )

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
    return _map_notice_detail(row, attachment_rows=attachment_rows)


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
