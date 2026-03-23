import pytest
from fastapi import HTTPException

from app.routers.v1.notices import _ensure_notice_manage_permission


def test_notice_manage_permission_allows_developer():
    _ensure_notice_manage_permission({"role": "developer"})


def test_notice_manage_permission_allows_hq_admin():
    _ensure_notice_manage_permission({"role": "hq_admin"})


@pytest.mark.parametrize("role", ["officer", "vice_supervisor", "supervisor"])
def test_notice_manage_permission_blocks_staff_roles(role: str):
    with pytest.raises(HTTPException) as exc_info:
        _ensure_notice_manage_permission({"role": role})

    assert exc_info.value.status_code == 403
