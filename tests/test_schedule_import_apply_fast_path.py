import uuid

import app.routers.v1.schedules as schedules


def test_canonical_apply_uses_persisted_preview_rows_without_rebuilding(monkeypatch):
    batch_id = uuid.uuid4()
    persisted_rows = [
        {
            "source_block": "body",
            "row_no": 10,
            "employee_name": "서성원",
            "schedule_date": "2026-04-01",
            "work_value": "12",
            "apply_action": "create",
        }
    ]

    monkeypatch.setattr(
        schedules,
        "_load_schedule_import_payload_rows",
        lambda conn, *, batch_id: persisted_rows,
    )

    def fail_if_rebuild(*args, **kwargs):
        raise AssertionError("apply should not reload/rebuild workbook when preview rows exist")

    monkeypatch.setattr(schedules, "_load_schedule_import_batch_raw_workbook", fail_if_rebuild)
    monkeypatch.setattr(schedules, "_build_schedule_import_preview_result", fail_if_rebuild)

    rows = schedules._load_canonical_schedule_import_apply_payload_rows(
        object(),
        batch_id=batch_id,
        batch={"month_key": "2026-04"},
        target_tenant={"id": "tenant-1"},
        site_row={"id": "site-1", "site_code": "R692"},
        user={"id": "user-1"},
    )

    assert rows == persisted_rows
