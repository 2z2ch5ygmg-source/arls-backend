from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import uuid

from .announcement_documents import (
    ANNOUNCEMENT_NOTICE_POLL_RESULT_VISIBILITY_VALUES,
    build_announcement_notice_body_blocks_projection_from_document,
    normalize_announcement_notice_body_blocks,
)


def serialize_announcement_datetime(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat()


def parse_announcement_datetime(value: Any) -> datetime | None:
    serialized = serialize_announcement_datetime(value)
    if not serialized:
        return None
    try:
        return datetime.fromisoformat(serialized.replace("Z", "+00:00"))
    except ValueError:
        return None


def _new_uuid() -> str:
    return str(uuid.uuid4())


def fetch_announcement_poll_bundle(
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
                   COALESCE(NULLIF(client_key, ''), id::text) AS client_key,
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
                   COALESCE(NULLIF(client_key, ''), id::text) AS client_key,
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
        if poll_id:
            option_rows_by_poll.setdefault(poll_id, []).append(row)

    option_counts: dict[tuple[str, str], int] = {}
    for row in option_count_rows:
        poll_id = str(row.get("poll_id") or "").strip()
        option_id = str(row.get("option_id") or "").strip()
        if poll_id and option_id:
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
        if poll_id and option_id:
            selected_option_ids_by_poll.setdefault(poll_id, []).append(option_id)

    option_client_by_id = {
        str(row.get("id") or "").strip(): str(row.get("client_key") or row.get("id") or "").strip()
        for row in option_rows
        if str(row.get("id") or "").strip()
    }

    now_utc = datetime.now(timezone.utc)
    bundle: dict[str, dict[str, Any]] = {}
    for poll_row in poll_rows:
        poll_db_id = str(poll_row.get("id") or "").strip()
        poll_client_key = str(poll_row.get("client_key") or poll_db_id).strip()
        if not poll_db_id or not poll_client_key:
            continue
        closes_at = parse_announcement_datetime(poll_row.get("closes_at"))
        is_closed = bool(closes_at and closes_at <= now_utc)
        selected_db_option_ids = selected_option_ids_by_poll.get(poll_db_id, [])
        has_voted = bool(selected_db_option_ids)
        results_visible = str(poll_row.get("result_visibility") or "always").strip().lower() == "always" or is_closed
        participant_count = total_votes_by_poll.get(poll_db_id, 0)
        options: list[dict[str, Any]] = []
        for option_row in option_rows_by_poll.get(poll_db_id, []):
            option_db_id = str(option_row.get("id") or "").strip()
            option_client_key = str(option_row.get("client_key") or option_db_id).strip()
            vote_count = option_counts.get((poll_db_id, option_db_id), 0)
            vote_ratio = (vote_count / participant_count) if participant_count > 0 else 0
            selected = option_db_id in selected_db_option_ids
            options.append(
                {
                    "option_id": option_client_key,
                    "optionId": option_client_key,
                    "label": str(option_row.get("label") or "").strip()[:160],
                    "vote_count": vote_count if results_visible else 0,
                    "voteCount": vote_count if results_visible else 0,
                    "vote_ratio": vote_ratio if results_visible else 0,
                    "voteRatio": vote_ratio if results_visible else 0,
                    "selected": selected,
                }
            )
        selected_client_option_ids = [
            option_client_by_id.get(option_id, option_id)
            for option_id in selected_db_option_ids
        ][:10]
        payload = {
            "poll_id": poll_client_key,
            "pollId": poll_client_key,
            "question": str(poll_row.get("question") or "").strip()[:240],
            "options": options,
            "allow_multiple": bool(poll_row.get("allow_multiple")),
            "allowMultiple": bool(poll_row.get("allow_multiple")),
            "is_anonymous": bool(poll_row.get("is_anonymous")),
            "isAnonymous": bool(poll_row.get("is_anonymous")),
            "result_visibility": str(poll_row.get("result_visibility") or "always").strip().lower() or "always",
            "resultVisibility": str(poll_row.get("result_visibility") or "always").strip().lower() or "always",
            "closes_at": serialize_announcement_datetime(closes_at),
            "closesAt": serialize_announcement_datetime(closes_at),
            "allow_change_vote": bool(poll_row.get("allow_change_vote")),
            "allowChangeVote": bool(poll_row.get("allow_change_vote")),
            "total_votes": participant_count if results_visible else 0,
            "totalVotes": participant_count if results_visible else 0,
            "selected_option_ids": selected_client_option_ids,
            "selectedOptionIds": selected_client_option_ids,
            "results_visible": results_visible,
            "resultsVisible": results_visible,
            "is_closed": is_closed,
            "isClosed": is_closed,
            "can_vote": (not is_closed) and (not has_voted or bool(poll_row.get("allow_change_vote"))),
            "canVote": (not is_closed) and (not has_voted or bool(poll_row.get("allow_change_vote"))),
            "has_voted": has_voted,
            "hasVoted": has_voted,
        }
        bundle[poll_client_key] = payload
        bundle[poll_db_id] = payload
    return bundle


def sync_announcement_poll_blocks(
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
            SELECT id,
                   COALESCE(NULLIF(client_key, ''), id::text) AS client_key
            FROM notice_polls
            WHERE tenant_id = %s
              AND notice_id = %s
            ORDER BY created_at ASC, id ASC
            """,
            (tenant_id, notice_id),
        )
        existing_poll_rows = [dict(row) for row in (cur.fetchall() or [])]
    poll_db_by_client = {
        str(row.get("client_key") or row.get("id") or "").strip(): str(row.get("id") or "").strip()
        for row in existing_poll_rows
        if str(row.get("id") or "").strip()
    }
    existing_poll_ids = set(poll_db_by_client.values())

    existing_option_rows: list[dict[str, Any]] = []
    if existing_poll_ids:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id,
                       COALESCE(NULLIF(client_key, ''), id::text) AS client_key,
                       poll_id
                FROM notice_poll_options
                WHERE tenant_id = %s
                  AND poll_id = ANY(%s)
                ORDER BY sort_order ASC, created_at ASC, id ASC
                """,
                (tenant_id, list(existing_poll_ids)),
            )
            existing_option_rows = [dict(row) for row in (cur.fetchall() or [])]
    option_db_by_poll_client: dict[tuple[str, str], str] = {}
    for row in existing_option_rows:
        poll_id = str(row.get("poll_id") or "").strip()
        client_key = str(row.get("client_key") or row.get("id") or "").strip()
        option_id = str(row.get("id") or "").strip()
        if poll_id and client_key and option_id:
            option_db_by_poll_client[(poll_id, client_key)] = option_id

    synced_blocks: list[dict[str, Any]] = []
    used_poll_ids: list[str] = []
    for block in normalized_blocks:
        if not isinstance(block, dict) or str(block.get("kind") or "").strip().lower() != "poll":
            synced_blocks.append(block)
            continue
        raw_poll = block.get("poll") if isinstance(block.get("poll"), dict) else {}
        incoming_poll_key = str(raw_poll.get("poll_id") or raw_poll.get("pollId") or "").strip() or f"poll-{uuid.uuid4().hex[:12]}"
        poll_db_id = poll_db_by_client.get(incoming_poll_key) or _new_uuid()
        allow_multiple = bool(raw_poll.get("allow_multiple") or raw_poll.get("allowMultiple"))
        is_anonymous = bool(raw_poll.get("is_anonymous", raw_poll.get("isAnonymous", True)))
        result_visibility = str(raw_poll.get("result_visibility") or raw_poll.get("resultVisibility") or "always").strip().lower()
        if result_visibility not in ANNOUNCEMENT_NOTICE_POLL_RESULT_VISIBILITY_VALUES:
            result_visibility = "always"
        closes_at = parse_announcement_datetime(raw_poll.get("closes_at") or raw_poll.get("closesAt"))
        allow_change_vote = bool(raw_poll.get("allow_change_vote") or raw_poll.get("allowChangeVote"))
        question = str(raw_poll.get("question") or "").strip()[:240]
        raw_options = raw_poll.get("options") if isinstance(raw_poll.get("options"), list) else []
        option_payloads: list[dict[str, Any]] = []
        for index, raw_option in enumerate(raw_options[:10]):
            if not isinstance(raw_option, dict):
                raw_option = {"label": str(raw_option or "").strip()}
            label = str(raw_option.get("label") or raw_option.get("text") or "").strip()[:160]
            if not label:
                continue
            incoming_option_key = str(raw_option.get("option_id") or raw_option.get("optionId") or raw_option.get("id") or "").strip() or f"option-{uuid.uuid4().hex[:12]}"
            option_db_id = option_db_by_poll_client.get((poll_db_id, incoming_option_key)) or _new_uuid()
            option_payloads.append(
                {
                    "option_id": option_db_id,
                    "client_key": incoming_option_key[:64],
                    "label": label,
                    "sort_order": index,
                }
            )
        if not question or len(option_payloads) < 2:
            continue

        with conn.cursor() as cur:
            if poll_db_id in existing_poll_ids:
                cur.execute(
                    """
                    UPDATE notice_polls
                    SET client_key = %s,
                        question = %s,
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
                        incoming_poll_key[:64],
                        question,
                        allow_multiple,
                        is_anonymous,
                        result_visibility,
                        closes_at,
                        allow_change_vote,
                        actor_id,
                        tenant_id,
                        notice_id,
                        poll_db_id,
                    ),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO notice_polls (
                        id, client_key, tenant_id, notice_id, question, allow_multiple,
                        is_anonymous, result_visibility, closes_at, allow_change_vote,
                        created_by, updated_by
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        poll_db_id,
                        incoming_poll_key[:64],
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
        with conn.cursor() as cur:
            for option_payload in option_payloads:
                if (poll_db_id, option_payload["client_key"]) in option_db_by_poll_client:
                    cur.execute(
                        """
                        UPDATE notice_poll_options
                        SET label = %s,
                            sort_order = %s,
                            client_key = %s
                        WHERE tenant_id = %s
                          AND poll_id = %s
                          AND id = %s
                        """,
                        (
                            option_payload["label"],
                            option_payload["sort_order"],
                            option_payload["client_key"],
                            tenant_id,
                            poll_db_id,
                            option_payload["option_id"],
                        ),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO notice_poll_options (id, client_key, tenant_id, poll_id, label, sort_order)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (
                            option_payload["option_id"],
                            option_payload["client_key"],
                            tenant_id,
                            poll_db_id,
                            option_payload["label"],
                            option_payload["sort_order"],
                        ),
                    )
            cur.execute(
                """
                DELETE FROM notice_poll_options
                WHERE tenant_id = %s
                  AND poll_id = %s
                  AND NOT (id = ANY(%s))
                """,
                (tenant_id, poll_db_id, kept_option_ids),
            )

        synced_blocks.append(
            {
                "kind": "poll",
                "poll": {
                    "poll_id": incoming_poll_key[:64],
                    "pollId": incoming_poll_key[:64],
                    "question": question,
                    "options": [
                        {
                            "option_id": item["client_key"],
                            "optionId": item["client_key"],
                            "label": item["label"],
                        }
                        for item in option_payloads
                    ],
                    "allow_multiple": allow_multiple,
                    "allowMultiple": allow_multiple,
                    "is_anonymous": is_anonymous,
                    "isAnonymous": is_anonymous,
                    "result_visibility": result_visibility,
                    "resultVisibility": result_visibility,
                    "closes_at": serialize_announcement_datetime(closes_at),
                    "closesAt": serialize_announcement_datetime(closes_at),
                    "allow_change_vote": allow_change_vote,
                    "allowChangeVote": allow_change_vote,
                },
            }
        )
        used_poll_ids.append(poll_db_id)

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


def sync_announcement_poll_document(
    conn,
    *,
    tenant_id: str,
    notice_id: str,
    actor_id: str,
    body_document: dict[str, Any],
) -> dict[str, Any]:
    projected_blocks = build_announcement_notice_body_blocks_projection_from_document(body_document)
    synced_blocks = sync_announcement_poll_blocks(
        conn,
        tenant_id=tenant_id,
        notice_id=notice_id,
        actor_id=actor_id,
        body_blocks=projected_blocks,
    )
    poll_by_original_key: dict[str, dict[str, Any]] = {}
    for block in synced_blocks:
        if isinstance(block, dict) and str(block.get("kind") or "") == "poll" and isinstance(block.get("poll"), dict):
            poll = block["poll"]
            poll_key = str(poll.get("poll_id") or poll.get("pollId") or "").strip()
            if poll_key:
                poll_by_original_key[poll_key] = poll
    next_document = dict(body_document or {})
    next_objects: list[dict[str, Any]] = []
    for obj in list(next_document.get("objects") or []):
        if not isinstance(obj, dict) or str(obj.get("kind") or "").strip() != "poll":
            next_objects.append(obj)
            continue
        poll = obj.get("poll") or {}
        poll_key = str(poll.get("poll_id") or poll.get("pollId") or "").strip()
        next_obj = dict(obj)
        next_obj["poll"] = poll_by_original_key.get(poll_key, poll)
        next_objects.append(next_obj)
    next_document["objects"] = next_objects
    return next_document


def vote_announcement_poll(
    conn,
    *,
    tenant_id: str,
    notice_id: str,
    poll_key: str,
    option_keys: list[str],
    user_id: str,
) -> None:
    normalized_poll_key = str(poll_key or "").strip()
    normalized_option_keys = []
    for item in option_keys or []:
        option_key = str(item or "").strip()
        if option_key and option_key not in normalized_option_keys:
            normalized_option_keys.append(option_key)
    if not normalized_option_keys:
        raise ValueError("투표 항목을 선택하세요.")

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id,
                   COALESCE(NULLIF(client_key, ''), id::text) AS client_key,
                   allow_multiple,
                   allow_change_vote,
                   closes_at
            FROM notice_polls
            WHERE tenant_id = %s
              AND notice_id = %s
              AND (client_key = %s OR id::text = %s)
            LIMIT 1
            """,
            (tenant_id, notice_id, normalized_poll_key, normalized_poll_key),
        )
        poll_row = cur.fetchone()
    if not poll_row:
        raise LookupError("해당 투표를 찾을 수 없습니다.")

    poll_db_id = str(poll_row.get("id") or "").strip()
    closes_at = parse_announcement_datetime(poll_row.get("closes_at"))
    if closes_at and closes_at <= datetime.now(timezone.utc):
        raise ValueError("마감된 투표입니다.")
    if not bool(poll_row.get("allow_multiple")) and len(normalized_option_keys) > 1:
        raise ValueError("하나의 선택지만 고를 수 있습니다.")

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id,
                   COALESCE(NULLIF(client_key, ''), id::text) AS client_key
            FROM notice_poll_options
            WHERE tenant_id = %s
              AND poll_id = %s
            """,
            (tenant_id, poll_db_id),
        )
        option_rows = [dict(row) for row in (cur.fetchall() or [])]
    option_db_by_client = {
        str(row.get("client_key") or row.get("id") or "").strip(): str(row.get("id") or "").strip()
        for row in option_rows
        if str(row.get("id") or "").strip()
    }
    invalid = [option_key for option_key in normalized_option_keys if option_key not in option_db_by_client]
    if invalid:
        raise ValueError("유효하지 않은 투표 항목이 포함되어 있습니다.")

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id
            FROM notice_poll_votes
            WHERE tenant_id = %s
              AND poll_id = %s
              AND user_id = %s
            LIMIT 1
            """,
            (tenant_id, poll_db_id, user_id),
        )
        has_existing_vote = bool(cur.fetchone())
    if has_existing_vote and not bool(poll_row.get("allow_change_vote")):
        raise ValueError("이미 참여한 투표입니다.")

    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM notice_poll_votes
            WHERE tenant_id = %s
              AND poll_id = %s
              AND user_id = %s
            """,
            (tenant_id, poll_db_id, user_id),
        )
        for option_key in normalized_option_keys:
            cur.execute(
                """
                INSERT INTO notice_poll_votes (id, tenant_id, poll_id, option_id, user_id)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (_new_uuid(), tenant_id, poll_db_id, option_db_by_client[option_key], user_id),
            )
