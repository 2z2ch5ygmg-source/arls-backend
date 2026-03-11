from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.utils.tenant_context import resolve_scoped_tenant


def _user(role: str = "hq_admin") -> dict:
    return {
        "id": "11111111-1111-1111-1111-111111111111",
        "tenant_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "tenant_code": "apple",
        "tenant_name": "Apple",
        "tenant_is_active": True,
        "tenant_is_deleted": False,
        "role": role,
    }


def test_branch_manager_allows_own_tenant_code_query_scope():
    user = _user("hq_admin")
    resolved = resolve_scoped_tenant(
        None,
        user,
        query_tenant_code="apple",
        require_dev_context=True,
    )
    assert str(resolved.get("id")) == str(user["tenant_id"])
    assert str(resolved.get("tenant_code")).lower() == "apple"


def test_branch_manager_rejects_other_tenant_code_query_scope():
    user = _user("hq_admin")
    with pytest.raises(HTTPException) as exc:
        resolve_scoped_tenant(
            None,
            user,
            query_tenant_code="jip",
            require_dev_context=True,
        )
    assert exc.value.status_code == 403


def test_employee_allows_own_tenant_code_query_scope():
    user = _user("officer")
    resolved = resolve_scoped_tenant(
        None,
        user,
        query_tenant_code="apple",
        require_dev_context=True,
    )
    assert str(resolved.get("id")) == str(user["tenant_id"])
    assert str(resolved.get("tenant_code")).lower() == "apple"


def test_hq_alias_allows_own_tenant_code_query_scope():
    user = _user("hq")
    resolved = resolve_scoped_tenant(
        None,
        user,
        query_tenant_code="apple",
        require_dev_context=True,
    )
    assert str(resolved.get("id")) == str(user["tenant_id"])
    assert str(resolved.get("tenant_code")).lower() == "apple"
