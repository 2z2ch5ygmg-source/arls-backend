from __future__ import annotations

from datetime import date
import unittest
from unittest.mock import patch

from app.routers.v1.schedules import (
    SENTRIX_ARLS_BRIDGE_ACTION_RETRACT,
    SENTRIX_ARLS_BRIDGE_ACTION_UPSERT,
    _process_sentrix_support_arls_bridge_actions,
)


class _CursorContext:
    def __init__(self, rows=None):
        self._rows = list(rows or [])
        self.executed: list[tuple[str, object]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.executed.append((str(sql), params))

    def fetchall(self):
        rows = list(self._rows)
        self._rows.clear()
        return rows

    def fetchone(self):
        if not self._rows:
            return None
        return self._rows.pop(0)


class _ConnectionStub:
    def __init__(self, cursor_rows=None):
        self._cursor_rows = list(cursor_rows or [])
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        rows = self._cursor_rows.pop(0) if self._cursor_rows else []
        return _CursorContext(rows)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class SentrixSupportScheduleRealtimeTests(unittest.TestCase):
    def _build_action_row(
        self,
        *,
        action_id: str,
        ticket_id: str,
        action: str,
        shift_kind: str,
        work_date: date,
        site_id: str = "site-1",
        site_code: str = "R692",
        employee_id: str = "emp-1",
    ) -> dict:
        return {
            "id": action_id,
            "tenant_id": "tenant-1",
            "batch_id": "batch-1",
            "snapshot_id": "snapshot-1",
            "ticket_id": ticket_id,
            "site_id": site_id,
            "site_code": site_code,
            "work_date": work_date,
            "shift_kind": shift_kind,
            "employee_id": employee_id,
            "employee_code": f"{site_code}-0001",
            "employee_name": "홍길동",
            "action": action,
            "ticket_state": "approved" if action == SENTRIX_ARLS_BRIDGE_ACTION_UPSERT else "pending",
            "payload_json": {},
        }

    def _build_action_result(
        self,
        *,
        action_row: dict,
        schedule_effect: str,
        status: str,
    ) -> dict:
        return {
            "bridge_action_id": action_row["id"],
            "ticket_id": action_row["ticket_id"],
            "site_id": action_row["site_id"],
            "site_code": action_row["site_code"],
            "work_date": action_row["work_date"].isoformat(),
            "shift_kind": action_row["shift_kind"],
            "employee_id": action_row["employee_id"],
            "action": action_row["action"],
            "status": status,
            "schedule_effect": schedule_effect,
        }

    def _run_process(self, *, action_rows: list[dict], action_results: list[dict]):
        conn = _ConnectionStub([action_rows])
        with patch(
            "app.routers.v1.schedules._apply_sentrix_support_bridge_action",
            side_effect=action_results,
        ) as mock_apply, patch(
            "app.routers.v1.schedules._mark_sentrix_support_bridge_action",
        ) as mock_mark, patch(
            "app.routers.v1.schedules._refresh_daily_leader_defaults_for_dates",
            return_value={},
        ) as mock_refresh, patch(
            "app.routers.v1.schedules.fetch_tenant_row_any",
            return_value={"id": "tenant-1", "tenant_code": "srs_kor"},
        ), patch(
            "app.routers.v1.schedules.schedule_event_bus.publish",
        ) as mock_publish:
            result = _process_sentrix_support_arls_bridge_actions(
                conn,
                tenant_id="tenant-1",
                batch_id="batch-1",
            )
        return result, conn, mock_apply, mock_mark, mock_refresh, mock_publish

    def test_day_support_bridge_publish_triggers_site_month_realtime_scope(self):
        action_row = self._build_action_row(
            action_id="bridge-day-1",
            ticket_id="ticket-day-1",
            action=SENTRIX_ARLS_BRIDGE_ACTION_UPSERT,
            shift_kind="day",
            work_date=date(2026, 4, 1),
        )

        result, conn, _mock_apply, _mock_mark, mock_refresh, mock_publish = self._run_process(
            action_rows=[action_row],
            action_results=[
                self._build_action_result(
                    action_row=action_row,
                    schedule_effect="created",
                    status="active",
                )
            ],
        )

        self.assertEqual(result["processed"], 1)
        self.assertEqual(result["materialized_created"], 1)
        self.assertEqual(conn.rollbacks, 0)
        self.assertEqual(conn.commits, 2)
        mock_refresh.assert_called_once_with(
            conn,
            tenant_id="tenant-1",
            site_id="site-1",
            schedule_dates=[date(2026, 4, 1)],
        )
        mock_publish.assert_called_once()
        payload = mock_publish.call_args.args[0]
        self.assertEqual(payload["type"], "schedule_changed")
        self.assertEqual(payload["tenant_id"], "tenant-1")
        self.assertEqual(payload["tenant_code"], "srs_kor")
        self.assertEqual(payload["site_code"], "R692")
        self.assertEqual(payload["month"], "2026-04")
        self.assertEqual(payload["work_date"], "2026-04-01")
        self.assertEqual(payload["event_type"], "sentrix_support_schedule_upserted")

    def test_day_support_bridge_update_still_triggers_site_month_realtime_scope(self):
        action_row = self._build_action_row(
            action_id="bridge-day-update-1",
            ticket_id="ticket-day-update-1",
            action=SENTRIX_ARLS_BRIDGE_ACTION_UPSERT,
            shift_kind="day",
            work_date=date(2026, 4, 7),
        )

        result, _conn, _mock_apply, _mock_mark, _mock_refresh, mock_publish = self._run_process(
            action_rows=[action_row],
            action_results=[
                self._build_action_result(
                    action_row=action_row,
                    schedule_effect="updated",
                    status="active",
                )
            ],
        )

        self.assertEqual(result["processed"], 1)
        self.assertEqual(result["materialized_updated"], 1)
        mock_publish.assert_called_once()
        payload = mock_publish.call_args.args[0]
        self.assertEqual(payload["site_code"], "R692")
        self.assertEqual(payload["month"], "2026-04")
        self.assertEqual(payload["work_date"], "2026-04-07")
        self.assertEqual(payload["event_type"], "sentrix_support_schedule_upserted")

    def test_night_support_bridge_publish_triggers_site_month_realtime_scope(self):
        action_row = self._build_action_row(
            action_id="bridge-night-1",
            ticket_id="ticket-night-1",
            action=SENTRIX_ARLS_BRIDGE_ACTION_UPSERT,
            shift_kind="night",
            work_date=date(2026, 4, 2),
        )

        result, _conn, _mock_apply, _mock_mark, _mock_refresh, mock_publish = self._run_process(
            action_rows=[action_row],
            action_results=[
                self._build_action_result(
                    action_row=action_row,
                    schedule_effect="created",
                    status="active",
                )
            ],
        )

        self.assertEqual(result["processed"], 1)
        self.assertEqual(result["upserts"], 1)
        self.assertEqual(result["materialized_created"], 1)
        mock_publish.assert_called_once()
        payload = mock_publish.call_args.args[0]
        self.assertEqual(payload["site_code"], "R692")
        self.assertEqual(payload["month"], "2026-04")
        self.assertEqual(payload["work_date"], "2026-04-02")
        self.assertEqual(payload["event_type"], "sentrix_support_schedule_upserted")

    def test_retract_support_bridge_publish_triggers_realtime_removal_scope(self):
        action_row = self._build_action_row(
            action_id="bridge-retract-1",
            ticket_id="ticket-retract-1",
            action=SENTRIX_ARLS_BRIDGE_ACTION_RETRACT,
            shift_kind="night",
            work_date=date(2026, 4, 3),
        )

        result, _conn, _mock_apply, _mock_mark, _mock_refresh, mock_publish = self._run_process(
            action_rows=[action_row],
            action_results=[
                self._build_action_result(
                    action_row=action_row,
                    schedule_effect="retracted",
                    status="retracted",
                )
            ],
        )

        self.assertEqual(result["processed"], 1)
        self.assertEqual(result["retracts"], 1)
        self.assertEqual(result["materialized_retracted"], 1)
        mock_publish.assert_called_once()
        payload = mock_publish.call_args.args[0]
        self.assertEqual(payload["site_code"], "R692")
        self.assertEqual(payload["month"], "2026-04")
        self.assertEqual(payload["work_date"], "2026-04-03")
        self.assertEqual(payload["event_type"], "sentrix_support_schedule_retracted")

    def test_same_site_month_actions_coalesce_to_single_realtime_publish(self):
        day_action = self._build_action_row(
            action_id="bridge-day-2",
            ticket_id="ticket-day-2",
            action=SENTRIX_ARLS_BRIDGE_ACTION_UPSERT,
            shift_kind="day",
            work_date=date(2026, 4, 4),
        )
        night_action = self._build_action_row(
            action_id="bridge-night-2",
            ticket_id="ticket-night-2",
            action=SENTRIX_ARLS_BRIDGE_ACTION_UPSERT,
            shift_kind="night",
            work_date=date(2026, 4, 4),
            employee_id="emp-2",
        )

        result, _conn, _mock_apply, _mock_mark, mock_refresh, mock_publish = self._run_process(
            action_rows=[day_action, night_action],
            action_results=[
                self._build_action_result(
                    action_row=day_action,
                    schedule_effect="created",
                    status="active",
                ),
                self._build_action_result(
                    action_row=night_action,
                    schedule_effect="created",
                    status="active",
                ),
            ],
        )

        self.assertEqual(result["processed"], 2)
        self.assertEqual(result["materialized_created"], 2)
        mock_refresh.assert_called_once_with(
            _conn,
            tenant_id="tenant-1",
            site_id="site-1",
            schedule_dates=[date(2026, 4, 4)],
        )
        mock_publish.assert_called_once()
        payload = mock_publish.call_args.args[0]
        self.assertEqual(payload["site_code"], "R692")
        self.assertEqual(payload["month"], "2026-04")
        self.assertEqual(payload["work_date"], "2026-04-04")

    def test_unrelated_site_or_month_publish_only_their_own_scope(self):
        april_action = self._build_action_row(
            action_id="bridge-april-1",
            ticket_id="ticket-april-1",
            action=SENTRIX_ARLS_BRIDGE_ACTION_UPSERT,
            shift_kind="day",
            work_date=date(2026, 4, 5),
            site_id="site-1",
            site_code="R692",
        )
        may_action = self._build_action_row(
            action_id="bridge-may-1",
            ticket_id="ticket-may-1",
            action=SENTRIX_ARLS_BRIDGE_ACTION_UPSERT,
            shift_kind="night",
            work_date=date(2026, 5, 6),
            site_id="site-2",
            site_code="R738",
            employee_id="emp-2",
        )

        result, _conn, _mock_apply, _mock_mark, mock_refresh, mock_publish = self._run_process(
            action_rows=[april_action, may_action],
            action_results=[
                self._build_action_result(
                    action_row=april_action,
                    schedule_effect="created",
                    status="active",
                ),
                self._build_action_result(
                    action_row=may_action,
                    schedule_effect="created",
                    status="active",
                ),
            ],
        )

        self.assertEqual(result["processed"], 2)
        self.assertEqual(mock_refresh.call_count, 2)
        self.assertEqual(mock_publish.call_count, 2)
        published_scopes = {
            (call.args[0]["site_code"], call.args[0]["month"])
            for call in mock_publish.call_args_list
        }
        self.assertEqual(
            published_scopes,
            {
                ("R692", "2026-04"),
                ("R738", "2026-05"),
            },
        )


if __name__ == "__main__":
    unittest.main()
