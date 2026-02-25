from __future__ import annotations

import json
import logging
import math
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import APIRouter, Depends, HTTPException, Query, status
from psycopg import errors as pg_errors
import requests

from ...config import settings
from ...deps import apply_rate_limit, get_current_user, get_db_conn, require_roles
from ...services.sites_match_index import (
    delete_site_match_index_entry,
    upsert_site_match_index_entry,
)
from ...schemas import SiteActiveUpdate, SiteCreate, SiteOut, SiteUpdate
from ...utils.permissions import (
    ROLE_BRANCH_MANAGER,
    ROLE_DEV,
    ROLE_EMPLOYEE,
    is_super_admin,
    normalize_role,
)
from ...utils.tenant_context import enforce_staff_site_scope, resolve_scoped_tenant

router = APIRouter(prefix="/sites", tags=["sites"], dependencies=[Depends(apply_rate_limit)])

SITE_WRITE_ROLES = (ROLE_DEV, ROLE_BRANCH_MANAGER)
SITE_READ_ROLES = SITE_WRITE_ROLES + (ROLE_EMPLOYEE,)
GOOGLE_PLACES_TEXTSEARCH_NEW_URL = "https://places.googleapis.com/v1/places:searchText"
logger = logging.getLogger(__name__)


def _active_filter_to_bool(raw: str | None) -> bool | None:
    value = str(raw or "all").strip().lower()
    if value in ("", "all"):
        return None
    if value in ("active", "true", "1"):
        return True
    if value in ("inactive", "false", "0"):
        return False
    raise HTTPException(status_code=400, detail="invalid active filter")


def _ensure_company(conn, tenant_id, company_code: str):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id
            FROM companies
            WHERE tenant_id = %s AND company_code = %s
            """,
            (tenant_id, company_code),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "COMPANY_NOT_FOUND", "message": "회사 코드를 찾을 수 없습니다."},
        )
    return row["id"]


def _resolve_default_company_code(conn, tenant_id) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT company_code
            FROM companies
            WHERE tenant_id = %s
            ORDER BY company_code
            LIMIT 1
            """,
            (tenant_id,),
        )
        row = cur.fetchone()
    company_code = str(row.get("company_code") or "").strip().upper() if row else ""
    if company_code:
        return company_code

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT tenant_code, tenant_name
            FROM tenants
            WHERE id = %s
              AND COALESCE(is_active, TRUE) = TRUE
              AND COALESCE(is_deleted, FALSE) = FALSE
            LIMIT 1
            """,
            (tenant_id,),
        )
        tenant_row = cur.fetchone()
    if not tenant_row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "TENANT_NOT_FOUND", "message": "tenant not found"},
        )

    default_company_code = "C001"
    tenant_name = str(tenant_row.get("tenant_name") or "").strip()
    default_company_name = f"{tenant_name} 기본회사" if tenant_name else "기본회사"

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO companies (id, tenant_id, company_code, company_name)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (tenant_id, company_code) DO NOTHING
            """,
            (uuid.uuid4(), tenant_id, default_company_code, default_company_name),
        )

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT company_code
            FROM companies
            WHERE tenant_id = %s
            ORDER BY company_code
            LIMIT 1
            """,
            (tenant_id,),
        )
        row = cur.fetchone()
    company_code = str(row.get("company_code") or "").strip().upper() if row else ""
    if not company_code:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "INTERNAL", "message": "기본 회사 코드 생성에 실패했습니다."},
        )
    logger.info(
        "auto-created default company for tenant=%s company_code=%s",
        tenant_row.get("tenant_code"),
        company_code,
    )
    return company_code


def _site_column_exists(conn, column_name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'sites'
                  AND column_name = %s
            ) AS present
            """,
            (column_name,),
        )
        row = cur.fetchone()
    return bool(row and row.get("present"))


def _site_place_id_select_sql(conn, table_alias: str = "s") -> str:
    if _site_column_exists(conn, "place_id"):
        return f"COALESCE({table_alias}.place_id, '') AS place_id"
    return "''::text AS place_id"


def _site_validation_error(fields: dict[str, str], *, message: str = "입력값을 확인해주세요.") -> None:
    cleaned = {
        str(key).strip(): str(value).strip()
        for key, value in (fields or {}).items()
        if str(key).strip() and str(value).strip()
    }
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "error": "VALIDATION_ERROR",
            "message": message,
            "fields": cleaned,
            "detail": {"fields": cleaned},
        },
    )


def _post_site_sync_to_soc(
    *,
    tenant_code: str | None,
    site_code: str | None,
    site_name: str | None,
    event_type: str = "SITE_CREATED",
) -> tuple[bool, int | None, str | None]:
    if not bool(settings.soc_integration_enabled):
        print("[HR->SOC] site-sync SKIP: soc_integration_enabled=false")
        return False, None, "soc_integration_enabled=false"

    url = str(getattr(settings, "soc_site_sync_url", "") or "").strip()
    if not url:
        print("[HR->SOC] site-sync SKIP: empty url")
        return False, None, "empty url"

    tenant_id_norm = str(tenant_code or "").strip().lower()
    site_code_norm = str(site_code or "").strip()
    site_name_norm = str(site_name or "").strip()
    normalized_event_type = str(event_type or "").strip().upper() or "SITE_CREATED"
    if normalized_event_type not in {"SITE_CREATED", "SITE_UPDATED"}:
        normalized_event_type = "SITE_CREATED"

    payload = {
        "event_type": normalized_event_type,
        "tenant_id": tenant_id_norm,
        "site_code": site_code_norm,
        "site_name": site_name_norm,
    }

    print(
        f"[HR->SOC] site-sync POST url={url} "
        f"event_type={normalized_event_type} tenant={tenant_id_norm} site={site_code_norm}"
    )
    try:
        response = requests.post(url, json=payload, timeout=5)
        print(f"[HR->SOC] site-sync status={response.status_code} body={(response.text or '')[:120]}")
        logger.info(
            "[HR->SOC] site-sync status=%s tenant=%s site=%s body=%s",
            response.status_code,
            tenant_id_norm,
            site_code_norm,
            (response.text or "")[:120],
        )
        if int(response.status_code) >= 400:
            return False, int(response.status_code), (response.text or "").strip()[:200]
        return True, int(response.status_code), None
    except Exception as exc:
        print(f"[HR->SOC] site-sync failed: {repr(exc)} url={url} tenant={tenant_id_norm} site={site_code_norm}")
        logger.warning(
            "[HR->SOC] site-sync failed: %s tenant=%s site=%s",
            str(exc),
            tenant_id_norm,
            site_code_norm,
        )
        return False, None, str(exc)


def _sync_site_match_index(
    conn,
    *,
    tenant_id: str,
    site_code: str,
    site_name: str,
    address_text: str | None,
    previous_site_code: str | None = None,
) -> None:
    normalized_site_code = str(site_code or "").strip()
    if previous_site_code:
        previous_code = str(previous_site_code or "").strip()
        if previous_code and previous_code != normalized_site_code:
            delete_site_match_index_entry(conn, tenant_id=tenant_id, site_id=previous_code)
    if not normalized_site_code:
        return
    upsert_site_match_index_entry(
        conn,
        tenant_id=tenant_id,
        site_id=normalized_site_code,
        site_name=str(site_name or "").strip(),
        address_text=str(address_text or "").strip(),
    )


def _resolve_tenant_row(conn, tenant_ref: str | None):
    ref = str(tenant_ref or "").strip()
    if not ref:
        return None
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, tenant_code
            FROM tenants
            WHERE (
                upper(tenant_code) = upper(%s)
                OR id::text = %s
            )
              AND COALESCE(is_active, TRUE) = TRUE
              AND COALESCE(is_deleted, FALSE) = FALSE
            LIMIT 1
            """,
            (ref, ref),
        )
        return cur.fetchone()


def _resolve_tenant_row_any(conn, tenant_ref: str | None):
    ref = str(tenant_ref or "").strip()
    if not ref:
        return None
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, tenant_code,
                   COALESCE(is_active, TRUE) AS is_active,
                   COALESCE(is_deleted, FALSE) AS is_deleted
            FROM tenants
            WHERE (
                upper(tenant_code) = upper(%s)
                OR id::text = %s
            )
            LIMIT 1
            """,
            (ref, ref),
        )
        return cur.fetchone()


def _resolve_super_admin_scoped_tenant(conn, tenant_ref: str | None, *, required: bool = False):
    requested = str(tenant_ref or "").strip().lower()
    if not requested:
        if required:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "TENANT_CONTEXT_REQUIRED", "message": "작업회사 선택이 필요합니다."},
            )
        return None

    row = _resolve_tenant_row_any(conn, requested)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "TENANT_NOT_FOUND", "message": "tenant not found"},
        )
    if not bool(row.get("is_active", True)) or bool(row.get("is_deleted", False)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "TENANT_DISABLED", "message": "tenant disabled"},
        )
    return row


def _resolve_target_tenant(conn, user, tenant_code: str | None, tenant_id: str | None = None):
    return resolve_scoped_tenant(
        conn,
        user,
        query_tenant_code=tenant_code,
        body_tenant_id=tenant_id,
        header_tenant_id=user.get("active_tenant_id"),
        require_dev_context=True,
    )


def _generate_next_site_code(conn, tenant_id: str) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT site_code
            FROM sites
            WHERE tenant_id = %s
              AND site_code ~ '^R[0-9]{3,4}$'
            """,
            (tenant_id,),
        )
        rows = cur.fetchall() or []
    max_number = 0
    for row in rows:
        code = str(row.get("site_code") or "").strip().upper()
        if not code.startswith("R"):
            continue
        tail = code[1:]
        if not tail.isdigit():
            continue
        max_number = max(max_number, int(tail))
    next_number = max_number + 1
    if next_number > 9999:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "SITE_ID_EXHAUSTED", "message": "현장 번호 생성 한도(9999)를 초과했습니다."},
        )
    width = 4 if next_number >= 1000 else 3
    return f"R{next_number:0{width}d}"


def _normalize_site_payload(payload: SiteCreate | SiteUpdate, *, require_site_code: bool = True) -> dict:
    tenant_id = str(getattr(payload, "tenant_id", "") or "").strip()
    company_code = str(getattr(payload, "company_code", "") or "").strip().upper()
    site_code = str(getattr(payload, "site_code", "") or "").strip()
    site_name = str(getattr(payload, "site_name", "") or "").strip()
    address = str(getattr(payload, "address", "") or "").strip()
    place_id = str(getattr(payload, "place_id", "") or "").strip()
    fields: dict[str, str] = {}

    latitude_raw = getattr(payload, "latitude", None)
    longitude_raw = getattr(payload, "longitude", None)
    radius_raw = getattr(payload, "radius_meters", None)
    latitude = math.nan
    longitude = math.nan
    radius_meters = math.nan

    if latitude_raw in (None, ""):
        fields["latitude"] = "required"
    else:
        try:
            latitude = float(latitude_raw)
        except Exception:
            fields["latitude"] = "invalid"

    if longitude_raw in (None, ""):
        fields["longitude"] = "required"
    else:
        try:
            longitude = float(longitude_raw)
        except Exception:
            fields["longitude"] = "invalid"

    if radius_raw in (None, ""):
        fields["radius_meters"] = "required"
    else:
        try:
            radius_meters = float(radius_raw)
        except Exception:
            fields["radius_meters"] = "invalid"

    is_active = bool(getattr(payload, "is_active", True))

    if require_site_code and not site_code:
        fields["site_id"] = "required"

    if not site_name:
        fields["name"] = "required"

    if ("latitude" not in fields) and ((not math.isfinite(latitude)) or latitude < -90 or latitude > 90):
        fields["latitude"] = "invalid"
    if ("longitude" not in fields) and ((not math.isfinite(longitude)) or longitude < -180 or longitude > 180):
        fields["longitude"] = "invalid"
    if ("radius_meters" not in fields) and ((not math.isfinite(radius_meters)) or radius_meters <= 0):
        fields["radius_meters"] = "invalid"

    if fields:
        _site_validation_error(fields)

    return {
        "tenant_id": tenant_id,
        "company_code": company_code,
        "site_code": site_code,
        "site_name": site_name,
        "address": address,
        "place_id": place_id,
        "latitude": latitude,
        "longitude": longitude,
        "radius_meters": radius_meters,
        "is_active": is_active,
    }


def _normalize_google_places_error(
    *,
    status_text: str | None = None,
    message_text: str | None = None,
    http_status: int | None = None,
) -> tuple[str, str]:
    status_code = str(status_text or "").strip().upper()
    message = str(message_text or "").strip()

    if status_code in {"PERMISSION_DENIED", "REQUEST_DENIED", "UNAUTHENTICATED"} or http_status in {401, 403}:
        return (
            "REQUEST_DENIED",
            "Places API 권한/활성화/키 제한 문제입니다. Google Cloud 설정을 확인하세요.",
        )
    if status_code in {"RESOURCE_EXHAUSTED", "OVER_QUERY_LIMIT"} or http_status == 429:
        return (
            "OVER_QUERY_LIMIT",
            "Places API 요청 한도를 초과했습니다. 잠시 후 다시 시도하세요.",
        )
    if status_code in {"ZERO_RESULTS", "NOT_FOUND"}:
        return ("ZERO_RESULTS", "검색 결과가 없습니다.")
    if status_code in {"INVALID_ARGUMENT", "FAILED_PRECONDITION"}:
        return (
            "INVALID_REQUEST",
            "주소 검색 요청 형식이 올바르지 않습니다. 검색어를 다시 확인해 주세요.",
        )

    return ("GOOGLE_PLACES_ERROR", message or "Google Places 검색 요청에 실패했습니다.")


def _search_geocode_google_places(query: str, limit: int) -> tuple[list[dict], dict | None]:
    api_key = str(settings.google_places_api_key or "").strip()
    if not api_key:
        return (
            [],
            {
                "code": "REQUEST_DENIED",
                "message": "Google Places API 키가 설정되지 않았습니다.",
            },
        )

    body = json.dumps(
        {
            "textQuery": query,
            "languageCode": "ko",
            "regionCode": "KR",
            "maxResultCount": limit,
        }
    ).encode("utf-8")
    req = Request(
        GOOGLE_PLACES_TEXTSEARCH_NEW_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.location",
            "User-Agent": "rg-arls-dev/1.0 (site-geofence-google-places)",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=7) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        body_text = ""
        try:
            body_text = exc.read().decode("utf-8", errors="ignore")
        except Exception:
            body_text = ""
        error_payload = {}
        if body_text:
            try:
                error_payload = json.loads(body_text)
            except Exception:
                error_payload = {}
        error_obj = error_payload.get("error") if isinstance(error_payload, dict) else {}
        status_text = (
            error_obj.get("status")
            if isinstance(error_obj, dict)
            else None
        )
        message_text = (
            error_obj.get("message")
            if isinstance(error_obj, dict)
            else body_text
        )
        code, message = _normalize_google_places_error(
            status_text=status_text,
            message_text=message_text,
            http_status=int(getattr(exc, "code", 0) or 0),
        )
        logger.warning("google places geocode request failed: code=%s status=%s http=%s", code, status_text, getattr(exc, "code", None))
        return ([], {"code": code, "message": message})
    except URLError as exc:
        logger.warning("google places geocode url error: %s", exc)
        return (
            [],
            {
                "code": "NETWORK_ERROR",
                "message": "Google Places 네트워크 연결에 실패했습니다.",
            },
        )
    except Exception as exc:
        logger.warning("google places geocode request failed: %s", exc)
        return (
            [],
            {
                "code": "GOOGLE_PLACES_ERROR",
                "message": "Google Places 검색 요청에 실패했습니다.",
            },
        )

    if isinstance(payload, dict) and payload.get("error"):
        err = payload.get("error")
        status_text = err.get("status") if isinstance(err, dict) else ""
        message_text = err.get("message") if isinstance(err, dict) else str(err)
        code, message = _normalize_google_places_error(status_text=status_text, message_text=message_text)
        logger.warning("google places new api error=%s", err)
        return ([], {"code": code, "message": message})

    results: list[dict] = []
    seen: set[tuple[float, float]] = set()
    rows = payload.get("places") if isinstance(payload.get("places"), list) else []
    for row in rows:
        location = row.get("location") if isinstance(row.get("location"), dict) else {}
        try:
            latitude = float(location.get("latitude"))
            longitude = float(location.get("longitude"))
        except Exception:
            continue

        dedup_key = (round(latitude, 6), round(longitude, 6))
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        display_name_obj = row.get("displayName") if isinstance(row.get("displayName"), dict) else {}
        place_name = str(display_name_obj.get("text") or "").strip()
        formatted_address = str(row.get("formattedAddress") or "").strip()
        display_name = " · ".join(part for part in [place_name, formatted_address] if part) or formatted_address or place_name
        results.append(
            {
                "display_name": display_name,
                "formatted_address": formatted_address or None,
                "place_name": place_name or None,
                "place_id": str(row.get("id") or "").strip() or None,
                "latitude": latitude,
                "longitude": longitude,
                "provider": "google_places",
            }
        )
        if len(results) >= limit:
            break

    return (results, None)


def _row_to_out(row) -> SiteOut:
    return SiteOut(
        id=row["id"],
        tenant_id=row.get("tenant_id"),
        tenant_code=row.get("tenant_code"),
        company_code=row["company_code"],
        site_code=row["site_code"],
        site_name=row["site_name"],
        address=row.get("address"),
        place_id=row.get("place_id") or None,
        latitude=float(row["latitude"]),
        longitude=float(row["longitude"]),
        radius_meters=float(row["radius_meters"]),
        is_active=bool(row.get("is_active", True)),
    )


def _fetch_site_row(conn, site_id: uuid.UUID, user):
    clauses = ["s.id = %s"]
    params: list = [site_id]
    if not is_super_admin(user["role"]):
        clauses.append("s.tenant_id = %s")
        params.append(user["tenant_id"])
    place_id_select_sql = _site_place_id_select_sql(conn, "s")
    sql = f"""
        SELECT s.id, s.tenant_id, t.tenant_code, s.site_code, s.site_name, COALESCE(s.address, '') AS address, COALESCE(s.place_id, '') AS place_id,
               s.latitude, s.longitude, s.radius_meters, COALESCE(s.is_active, TRUE) AS is_active,
               c.company_code
        FROM sites s
        JOIN tenants t ON t.id = s.tenant_id
        JOIN companies c ON c.id = s.company_id
        WHERE {' AND '.join(clauses)}
        LIMIT 1
    """
    sql = sql.replace("COALESCE(s.place_id, '') AS place_id", place_id_select_sql)
    with conn.cursor() as cur:
        cur.execute(sql, tuple(params))
        return cur.fetchone()


@router.get("", response_model=list[SiteOut])
def list_sites(
    q: str | None = Query(default=None, min_length=1, max_length=120),
    active: str | None = Query(default=None),
    include_inactive: bool = Query(default=False),
    include_deleted: bool = Query(default=False),
    company_code: str | None = Query(default=None, max_length=64),
    tenant_code: str | None = Query(default=None, max_length=64),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    role_scope = normalize_role(user.get("role"))
    if role_scope not in SITE_READ_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "FORBIDDEN", "message": "접근 권한이 없습니다."},
        )

    tenant = _resolve_target_tenant(conn, user, tenant_code)
    staff_scope = enforce_staff_site_scope(user)

    active_filter = _active_filter_to_bool(active)
    has_site_active = _site_column_exists(conn, "is_active")
    has_site_deleted = _site_column_exists(conn, "is_deleted")
    clauses = ["s.tenant_id = %s"]
    params: list = [tenant["id"]]
    if staff_scope:
        clauses.append("s.id = %s")
        params.append(staff_scope["site_id"])

    if company_code:
        clauses.append("c.company_code = %s")
        params.append(company_code.strip())

    if has_site_deleted and not include_deleted:
        clauses.append("COALESCE(s.is_deleted, FALSE) = FALSE")

    if has_site_active and active_filter is not None:
        clauses.append("COALESCE(s.is_active, TRUE) = %s")
        params.append(active_filter)
    elif has_site_active and not include_inactive:
        clauses.append("COALESCE(s.is_active, TRUE) = TRUE")

    keyword = (q or "").strip()
    if keyword:
        like = f"%{keyword}%"
        clauses.append(
            """
            (
                s.site_code ILIKE %s
                OR s.site_name ILIKE %s
                OR COALESCE(s.address, '') ILIKE %s
                OR c.company_code ILIKE %s
            )
            """
        )
        params.extend([like, like, like, like])

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    place_id_select_sql = _site_place_id_select_sql(conn, "s")
    sql = f"""
        SELECT s.id, s.tenant_id, t.tenant_code, s.site_code, s.site_name, COALESCE(s.address, '') AS address, {place_id_select_sql},
               s.latitude, s.longitude, s.radius_meters, COALESCE(s.is_active, TRUE) AS is_active,
               c.company_code
        FROM sites s
        JOIN tenants t ON t.id = s.tenant_id
        JOIN companies c ON c.id = s.company_id
        {where_sql}
        ORDER BY COALESCE(s.is_active, TRUE) DESC, c.company_code, s.site_code
    """
    with conn.cursor() as cur:
        cur.execute(sql, tuple(params))
        rows = cur.fetchall()
    return [_row_to_out(row) for row in rows]


@router.get("/geocode")
def geocode_site_address(
    q: str = Query(..., min_length=2, max_length=120),
    limit: int = Query(default=5, ge=1, le=10),
    user=Depends(get_current_user),
):
    if normalize_role(user.get("role")) not in SITE_WRITE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "FORBIDDEN", "message": "접근 권한이 없습니다."},
        )

    query = q.strip()
    google_results, google_error = _search_geocode_google_places(query, limit)
    if google_results:
        return google_results

    if google_error:
        error_code = str(google_error.get("code") or "").strip().upper()
        if error_code == "OVER_QUERY_LIMIT":
            http_status = status.HTTP_429_TOO_MANY_REQUESTS
        elif error_code == "REQUEST_DENIED":
            http_status = status.HTTP_503_SERVICE_UNAVAILABLE
        elif error_code == "INVALID_REQUEST":
            http_status = status.HTTP_400_BAD_REQUEST
        elif error_code == "NETWORK_ERROR":
            http_status = status.HTTP_503_SERVICE_UNAVAILABLE
        else:
            http_status = status.HTTP_502_BAD_GATEWAY
        raise HTTPException(
            status_code=http_status,
            detail={
                "code": error_code or "GOOGLE_PLACES_ERROR",
                "message": str(google_error.get("message") or "Google Places 검색 요청에 실패했습니다."),
            },
        )

    # 정상 처리지만 검색 결과가 없는 경우.
    return []


@router.post("", response_model=SiteOut, status_code=status.HTTP_201_CREATED)
def create_site(
    payload: SiteCreate,
    tenant_code: str | None = Query(default=None, max_length=64),
    tenant_id: str | None = Query(default=None, max_length=64),
    conn=Depends(get_db_conn),
    user=Depends(require_roles(*SITE_WRITE_ROLES)),
):
    normalized = _normalize_site_payload(payload, require_site_code=True)
    requested_tenant_id = str(tenant_id or normalized.get("tenant_id") or "").strip()
    tenant = _resolve_target_tenant(conn, user, tenant_code, requested_tenant_id)
    if not tenant or not tenant.get("id"):
        _site_validation_error({"tenant_id": "required"})

    tenant_id = tenant["id"]
    site_id = uuid.uuid4()

    resolved_company_code = str(normalized.get("company_code") or "").strip().upper()
    if resolved_company_code:
        try:
            _ensure_company(conn, tenant_id, resolved_company_code)
        except HTTPException:
            resolved_company_code = ""
    if not resolved_company_code:
        resolved_company_code = _resolve_default_company_code(conn, tenant_id)
    normalized["company_code"] = resolved_company_code
    logger.info(
        "create_site requested: tenant=%s company=%s site=%s actor=%s",
        tenant.get("tenant_code"),
        normalized["company_code"],
        normalized["site_code"],
        user.get("username"),
    )

    try:
        has_place_id = _site_column_exists(conn, "place_id")
        company_id = _ensure_company(conn, tenant_id, resolved_company_code)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM sites
                WHERE tenant_id = %s AND site_code = %s
                LIMIT 1
                """,
                (tenant_id, normalized["site_code"]),
            )
            if cur.fetchone():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"error": "SITE_EXISTS", "message": "이미 존재하는 현장 번호입니다."},
                )

            if has_place_id:
                cur.execute(
                    """
                    INSERT INTO sites (
                        id, tenant_id, company_id, site_code, site_name, address, place_id,
                        latitude, longitude, radius_meters, is_active
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, site_code, site_name, COALESCE(address, '') AS address, COALESCE(place_id, '') AS place_id,
                              latitude, longitude, radius_meters, COALESCE(is_active, TRUE) AS is_active
                    """,
                    (
                        site_id,
                        tenant_id,
                        company_id,
                        normalized["site_code"],
                        normalized["site_name"],
                        normalized["address"],
                        normalized["place_id"],
                        normalized["latitude"],
                        normalized["longitude"],
                        normalized["radius_meters"],
                        normalized["is_active"],
                    ),
                )
            else:
                logger.warning("sites.place_id column is missing; create_site will skip place_id storage")
                cur.execute(
                    """
                    INSERT INTO sites (
                        id, tenant_id, company_id, site_code, site_name, address,
                        latitude, longitude, radius_meters, is_active
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, site_code, site_name, COALESCE(address, '') AS address, ''::text AS place_id,
                              latitude, longitude, radius_meters, COALESCE(is_active, TRUE) AS is_active
                    """,
                    (
                        site_id,
                        tenant_id,
                        company_id,
                        normalized["site_code"],
                        normalized["site_name"],
                        normalized["address"],
                        normalized["latitude"],
                        normalized["longitude"],
                        normalized["radius_meters"],
                        normalized["is_active"],
                    ),
                )
            row = cur.fetchone()
            if not row:
                raise RuntimeError("failed to create site")
    except HTTPException:
        raise
    except pg_errors.UniqueViolation as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "SITE_EXISTS", "message": "이미 존재하는 현장 번호입니다."},
        ) from exc
    except Exception as exc:
        logger.exception(
            "create_site failed: tenant=%s company=%s site=%s payload={company_code:%s,site_code:%s,site_name:%s,radius_meters:%s}",
            tenant.get("tenant_code"),
            normalized.get("company_code"),
            normalized.get("site_code"),
            normalized.get("company_code"),
            normalized.get("site_code"),
            normalized.get("site_name"),
            normalized.get("radius_meters"),
            exc_info=exc,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "INTERNAL", "message": "서버 오류입니다. 잠시 후 다시 시도해주세요."},
        ) from exc

    row["tenant_id"] = tenant["id"]
    row["tenant_code"] = tenant.get("tenant_code")
    row["company_code"] = normalized["company_code"]
    _sync_site_match_index(
        conn,
        tenant_id=str(row["tenant_id"]),
        site_code=str(row.get("site_code") or ""),
        site_name=str(row.get("site_name") or ""),
        address_text=str(row.get("address") or ""),
    )
    _post_site_sync_to_soc(
        tenant_code=row.get("tenant_code"),
        site_code=row.get("site_code"),
        site_name=row.get("site_name"),
        event_type="SITE_CREATED",
    )
    return _row_to_out(row)


@router.put("/{site_id}", response_model=SiteOut)
def update_site(
    site_id: uuid.UUID,
    payload: SiteUpdate,
    conn=Depends(get_db_conn),
    user=Depends(require_roles(*SITE_WRITE_ROLES)),
):
    current = _fetch_site_row(conn, site_id, user)
    if not current:
        raise HTTPException(status_code=404, detail="site not found")

    normalized = _normalize_site_payload(payload)
    tenant_id = current["tenant_id"]
    resolved_company_code = str(normalized.get("company_code") or "").strip().upper() or str(current.get("company_code") or "").strip().upper()

    if resolved_company_code:
        try:
            _ensure_company(conn, tenant_id, resolved_company_code)
        except HTTPException:
            resolved_company_code = ""
    if not resolved_company_code:
        resolved_company_code = _resolve_default_company_code(conn, tenant_id)
    normalized["company_code"] = resolved_company_code

    try:
        company_id = _ensure_company(conn, tenant_id, resolved_company_code)

        with conn.cursor() as cur:
            has_place_id = _site_column_exists(conn, "place_id")
            if normalized["site_code"] != current["site_code"]:
                cur.execute(
                    """
                    SELECT 1
                    FROM sites
                    WHERE tenant_id = %s AND site_code = %s AND id <> %s
                    LIMIT 1
                    """,
                    (tenant_id, normalized["site_code"], site_id),
                )
                if cur.fetchone():
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail={"error": "SITE_EXISTS", "message": "이미 존재하는 사이트 코드입니다."},
                    )

            if has_place_id:
                cur.execute(
                    """
                    UPDATE sites
                    SET company_id = %s,
                        site_code = %s,
                        site_name = %s,
                        address = %s,
                        place_id = %s,
                        latitude = %s,
                        longitude = %s,
                        radius_meters = %s,
                        is_active = %s,
                        updated_at = timezone('utc', now())
                    WHERE id = %s
                    RETURNING id, site_code, site_name, COALESCE(address, '') AS address, COALESCE(place_id, '') AS place_id,
                              latitude, longitude, radius_meters, COALESCE(is_active, TRUE) AS is_active
                    """,
                    (
                        company_id,
                        normalized["site_code"],
                        normalized["site_name"],
                        normalized["address"],
                        normalized["place_id"],
                        normalized["latitude"],
                        normalized["longitude"],
                        normalized["radius_meters"],
                        normalized["is_active"],
                        site_id,
                    ),
                )
            else:
                logger.warning("sites.place_id column is missing; update_site will skip place_id storage")
                cur.execute(
                    """
                    UPDATE sites
                    SET company_id = %s,
                        site_code = %s,
                        site_name = %s,
                        address = %s,
                        latitude = %s,
                        longitude = %s,
                        radius_meters = %s,
                        is_active = %s,
                        updated_at = timezone('utc', now())
                    WHERE id = %s
                    RETURNING id, site_code, site_name, COALESCE(address, '') AS address, ''::text AS place_id,
                              latitude, longitude, radius_meters, COALESCE(is_active, TRUE) AS is_active
                    """,
                    (
                        company_id,
                        normalized["site_code"],
                        normalized["site_name"],
                        normalized["address"],
                        normalized["latitude"],
                        normalized["longitude"],
                        normalized["radius_meters"],
                        normalized["is_active"],
                        site_id,
                    ),
                )
            row = cur.fetchone()
    except HTTPException:
        raise
    except pg_errors.UniqueViolation as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "SITE_EXISTS", "message": "이미 존재하는 사이트 코드입니다."},
        ) from exc
    except Exception as exc:
        logger.exception(
            "update_site failed: site_id=%s tenant_id=%s company_code=%s site_code=%s",
            site_id,
            tenant_id,
            normalized.get("company_code"),
            normalized.get("site_code"),
            exc_info=exc,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "INTERNAL", "message": "서버 오류입니다. 잠시 후 다시 시도해주세요."},
        ) from exc

    if not row:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "INTERNAL", "message": "서버 오류입니다. 잠시 후 다시 시도해주세요."},
        )
    row["tenant_id"] = tenant_id
    row["tenant_code"] = current.get("tenant_code")
    row["company_code"] = resolved_company_code
    _sync_site_match_index(
        conn,
        tenant_id=str(tenant_id),
        site_code=str(row.get("site_code") or ""),
        site_name=str(row.get("site_name") or ""),
        address_text=str(row.get("address") or ""),
        previous_site_code=str(current.get("site_code") or ""),
    )
    _post_site_sync_to_soc(
        tenant_code=row.get("tenant_code"),
        site_code=row.get("site_code"),
        site_name=row.get("site_name"),
        event_type="SITE_UPDATED",
    )
    return _row_to_out(row)


@router.patch("/{site_id}/active", response_model=SiteOut)
def update_site_active(
    site_id: uuid.UUID,
    payload: SiteActiveUpdate,
    conn=Depends(get_db_conn),
    user=Depends(require_roles(*SITE_WRITE_ROLES)),
):
    current = _fetch_site_row(conn, site_id, user)
    if not current:
        raise HTTPException(status_code=404, detail="site not found")

    place_id_select_sql = _site_place_id_select_sql(conn, "sites")
    with conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE sites
            SET is_active = %s,
                updated_at = timezone('utc', now())
            WHERE id = %s
            RETURNING id, site_code, site_name, COALESCE(address, '') AS address, {place_id_select_sql},
                      latitude, longitude, radius_meters, COALESCE(is_active, TRUE) AS is_active
            """,
            (payload.is_active, site_id),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=500, detail="failed to update site status")
    row["tenant_id"] = current.get("tenant_id")
    row["tenant_code"] = current.get("tenant_code")
    row["company_code"] = current["company_code"]
    return _row_to_out(row)


@router.delete("/{site_id}")
def delete_site(
    site_id: uuid.UUID,
    conn=Depends(get_db_conn),
    user=Depends(require_roles(*SITE_WRITE_ROLES)),
):
    current = _fetch_site_row(conn, site_id, user)
    if not current:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "SITE_NOT_FOUND", "message": "현장 정보를 찾을 수 없습니다."},
        )

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM sites
                WHERE id = %s
                """,
                (site_id,),
            )
            if cur.rowcount == 0:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"error": "SITE_NOT_FOUND", "message": "현장 정보를 찾을 수 없습니다."},
                )
    except HTTPException:
        raise
    except pg_errors.ForeignKeyViolation as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "SITE_DELETE_CONFLICT",
                "message": "연결된 직원/근무 데이터가 있어 현장을 삭제할 수 없습니다. 비활성화를 사용해 주세요.",
            },
        ) from exc
    except Exception as exc:
        logger.exception("delete_site failed: site_id=%s", site_id, exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "INTERNAL", "message": "서버 오류입니다. 잠시 후 다시 시도해주세요."},
        ) from exc

    delete_site_match_index_entry(
        conn,
        tenant_id=str(current.get("tenant_id") or ""),
        site_id=str(current.get("site_code") or ""),
    )
    return {"deleted": True, "site_id": str(site_id)}
