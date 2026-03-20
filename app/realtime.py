from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from queue import Empty, Full, Queue
import threading
import uuid
from typing import Any

from psycopg import connect

from .config import settings


logger = logging.getLogger(__name__)
SCHEDULE_EVENT_CHANNEL = "arls_schedule_events"


@dataclass
class ScheduleEventSubscription:
    id: str
    tenant_id: str
    month: str
    site_code: str | None
    queue: Queue


class ScheduleEventBus:
    def __init__(self, *, enable_database_transport: bool = False) -> None:
        self._lock = threading.Lock()
        self._subscriptions: dict[str, ScheduleEventSubscription] = {}
        self._database_transport_enabled = bool(enable_database_transport)
        self._listener_lock = threading.Lock()
        self._listener_stop_event = threading.Event()
        self._listener_thread: threading.Thread | None = None
        self._instance_id = uuid.uuid4().hex

    def enable_database_transport(self) -> None:
        if self._database_transport_enabled:
            self._ensure_listener()
            return
        self._database_transport_enabled = True
        self._ensure_listener()

    def disable_database_transport(self) -> None:
        self._database_transport_enabled = False
        self.stop()

    def stop(self) -> None:
        with self._listener_lock:
            thread = self._listener_thread
            if thread is None:
                return
            self._listener_thread = None
            self._listener_stop_event.set()
        if thread.is_alive():
            thread.join(timeout=1.5)
        self._listener_stop_event = threading.Event()

    def subscribe(self, *, tenant_id: str, month: str, site_code: str | None = None) -> ScheduleEventSubscription:
        if self._database_transport_enabled:
            self._ensure_listener()
        subscription = ScheduleEventSubscription(
            id=uuid.uuid4().hex,
            tenant_id=str(tenant_id or "").strip(),
            month=str(month or "").strip(),
            site_code=str(site_code or "").strip().upper() or None,
            queue=Queue(maxsize=32),
        )
        with self._lock:
            self._subscriptions[subscription.id] = subscription
        return subscription

    def unsubscribe(self, subscription_id: str) -> None:
        key = str(subscription_id or "").strip()
        if not key:
            return
        with self._lock:
            self._subscriptions.pop(key, None)

    def publish(self, event: dict[str, Any] | None, *, db_conn=None) -> None:
        normalized = self._normalize_event(event)
        if not normalized:
            return
        normalized["_origin_instance"] = self._instance_id
        self._deliver(normalized)
        if self._database_transport_enabled:
            self._ensure_listener()
            self._notify_database(normalized, db_conn=db_conn)

    def handle_remote_event(self, event: dict[str, Any] | None) -> None:
        normalized = self._normalize_event(event)
        if not normalized:
            return
        origin_instance = str(normalized.get("_origin_instance") or "").strip()
        if origin_instance and origin_instance == self._instance_id:
            return
        self._deliver(normalized)

    def _normalize_event(self, event: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(event, dict):
            return None
        tenant_id = str(event.get("tenant_id") or "").strip()
        month = str(event.get("month") or "").strip()
        site_code = str(event.get("site_code") or "").strip().upper()
        if not tenant_id or not month:
            return None
        normalized = dict(event)
        normalized["tenant_id"] = tenant_id
        normalized["month"] = month
        normalized["site_code"] = site_code
        return normalized

    def _deliver(self, event: dict[str, Any]) -> None:
        tenant_id = str(event.get("tenant_id") or "").strip()
        month = str(event.get("month") or "").strip()
        site_code = str(event.get("site_code") or "").strip().upper()
        if not tenant_id or not month:
            return
        with self._lock:
            subscriptions = list(self._subscriptions.values())
        for subscription in subscriptions:
            if subscription.tenant_id != tenant_id:
                continue
            if subscription.month != month:
                continue
            if subscription.site_code and site_code and subscription.site_code != site_code:
                continue
            try:
                subscription.queue.put_nowait(event)
            except Full:
                try:
                    subscription.queue.get_nowait()
                except Empty:
                    pass
                except Exception:
                    pass
                try:
                    subscription.queue.put_nowait(event)
                except Full:
                    continue

    def _ensure_listener(self) -> None:
        if not self._database_transport_enabled or not settings.database_url:
            return
        with self._listener_lock:
            if self._listener_thread and self._listener_thread.is_alive():
                return
            self._listener_stop_event = threading.Event()
            self._listener_thread = threading.Thread(
                target=self._listen_loop,
                name="arls-schedule-event-listener",
                daemon=True,
            )
            self._listener_thread.start()

    def _listen_loop(self) -> None:
        while not self._listener_stop_event.is_set():
            try:
                with connect(settings.database_url, autocommit=True) as conn:
                    with conn.cursor() as cur:
                        cur.execute(f"LISTEN {SCHEDULE_EVENT_CHANNEL}")
                    while not self._listener_stop_event.is_set():
                        received = False
                        for notify in conn.notifies(timeout=1.0, stop_after=10):
                            received = True
                            try:
                                payload = json.loads(str(notify.payload or "").strip() or "{}")
                            except Exception:
                                logger.warning("schedule realtime payload decode failed", exc_info=True)
                                continue
                            self.handle_remote_event(payload if isinstance(payload, dict) else None)
                        if not received:
                            self._listener_stop_event.wait(0.05)
            except Exception:
                if self._listener_stop_event.is_set():
                    break
                logger.exception("schedule realtime listener failed")
                self._listener_stop_event.wait(1.0)

    def _notify_database(self, event: dict[str, Any], *, db_conn=None) -> None:
        if not settings.database_url:
            return
        try:
            payload_text = json.dumps(event, ensure_ascii=False, default=str)
            if db_conn is not None:
                with db_conn.cursor() as cur:
                    cur.execute("SELECT pg_notify(%s, %s)", (SCHEDULE_EVENT_CHANNEL, payload_text))
                return
            with connect(settings.database_url, autocommit=True) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT pg_notify(%s, %s)", (SCHEDULE_EVENT_CHANNEL, payload_text))
        except Exception:
            logger.exception("schedule realtime notify failed")


schedule_event_bus = ScheduleEventBus()
