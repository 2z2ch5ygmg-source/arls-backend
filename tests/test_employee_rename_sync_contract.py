from app.routers.v1 import employees


class _DummyResponse:
    def __init__(self, status_code: int = 202, text: str = "accepted"):
        self.status_code = status_code
        self.text = text


def test_employee_rename_sync_payload_uses_stable_identity(monkeypatch):
    captured: dict[str, object] = {}

    monkeypatch.setattr(employees.settings, "soc_integration_enabled", True)
    monkeypatch.setattr(employees.settings, "soc_employee_sync_url", "https://soc.example.test/employees/sync")

    def _fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return _DummyResponse()

    monkeypatch.setattr(employees.requests, "post", _fake_post)

    ok, status_code, reason = employees._post_employee_sync_to_soc(
        tenant_id="tenant-1",
        tenant_code="APPLE",
        tenant_name="Apple Korea",
        site_id="site-1",
        site_code="R692",
        site_name="Apple Garosu",
        employee_uuid="emp-123",
        employee_code="R692-0042",
        full_name="최미강",
        phone="010-1111-2222",
        linked_user_id="user-77",
        username="choi.guard",
        user_role="officer",
        soc_login_id="choi.guard",
        soc_role="Officer",
        old_display_name="최미가",
        new_display_name="최미강",
        event_type="EMPLOYEE_UPDATED",
    )

    assert ok is True
    assert status_code == 202
    assert reason is None

    payload = captured["json"]
    assert captured["url"] == "https://soc.example.test/employees/sync"
    assert captured["timeout"] == 5

    assert payload["event_type"] == "EMPLOYEE_UPDATED"
    assert payload["change_type"] == "UPDATE"
    assert payload["sync_mode"] == "UPSERT"
    assert payload["employee_id"] == "emp-123"
    assert payload["old_display_name"] == "최미가"
    assert payload["new_display_name"] == "최미강"

    assert payload["tenant"] == {
        "tenant_id": "tenant-1",
        "tenant_code": "APPLE",
        "tenant_name": "Apple Korea",
    }
    assert payload["site"] == {
        "site_id": "site-1",
        "site_code": "R692",
        "site_name": "Apple Garosu",
    }
    assert payload["linked_user"] == {
        "user_id": "user-77",
        "username": "choi.guard",
        "soc_login_id": "choi.guard",
        "user_role": "Officer",
        "soc_role": "Officer",
    }

    assert payload["identity"]["employee_id"] == "emp-123"
    assert payload["identity"]["employee_uuid"] == "emp-123"
    assert payload["identity"]["employee_code"] == "R692-0042"
    assert payload["identity"]["tenant_id"] == "tenant-1"
    assert payload["identity"]["tenant_code"] == "APPLE"
    assert payload["identity"]["site_id"] == "site-1"
    assert payload["identity"]["site_code"] == "R692"
    assert payload["identity"]["linked_user_id"] == "user-77"
    assert payload["identity"]["identity_key"] == "tenant-1:emp-123"

    assert payload["employee"]["employee_id"] == "emp-123"
    assert payload["employee"]["employee_uuid"] == "emp-123"
    assert payload["employee"]["employee_code"] == "R692-0042"
    assert payload["employee"]["name"] == "최미강"
    assert payload["employee"]["old_display_name"] == "최미가"
    assert payload["employee"]["new_display_name"] == "최미강"
    assert payload["employee"]["username"] == "choi.guard"
