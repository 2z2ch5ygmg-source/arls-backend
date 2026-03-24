from app.utils.permissions import (
    can_manage_schedule,
    is_site_scoped_manager_role,
    normalize_role,
    normalize_user_role,
)


def test_hq_aliases_map_to_hq_admin():
    assert normalize_user_role("HQ") == "hq_admin"
    assert normalize_user_role("hq_manager") == "hq_admin"
    assert normalize_user_role("branchManager") == "hq_admin"


def test_hq_aliases_can_manage_schedule():
    assert normalize_role("HQ") == "branch_manager"
    assert can_manage_schedule("HQ")
    assert can_manage_schedule("hq_manager")


def test_only_legacy_branch_manager_aliases_are_site_scoped():
    assert is_site_scoped_manager_role("branchManager")
    assert is_site_scoped_manager_role("site_manager")
    assert not is_site_scoped_manager_role("hq_admin")
    assert not is_site_scoped_manager_role("hq_manager")
