from __future__ import annotations

import re

ROLE_OFFICER = "officer"
ROLE_VICE_SUPERVISOR = "vice_supervisor"
ROLE_SUPERVISOR = "supervisor"
ROLE_HQ_ADMIN = "hq_admin"
ROLE_DEVELOPER = "developer"

ROLE_ENUM_OFFICER = "OFFICER"
ROLE_ENUM_VICE_SUPERVISOR = "VICE_SUPERVISOR"
ROLE_ENUM_SUPERVISOR = "SUPERVISOR"
ROLE_ENUM_HQ_ADMIN = "HQ_ADMIN"
ROLE_ENUM_DEVELOPER = "DEVELOPER"

PERMISSION_GROUP_STAFF = "STAFF"
PERMISSION_GROUP_ADMIN = "ADMIN"
PERMISSION_GROUP_DEV = "DEV"

ALL_USER_ROLES = {
    ROLE_OFFICER,
    ROLE_VICE_SUPERVISOR,
    ROLE_SUPERVISOR,
    ROLE_HQ_ADMIN,
    ROLE_DEVELOPER,
}

# Access-scope roles for internal permission checks.
ROLE_DEV = "dev"
ROLE_BRANCH_MANAGER = "branch_manager"
ROLE_EMPLOYEE = "employee"

# Backward-compatible aliases for imports used by older modules.
ROLE_PLATFORM_ADMIN = ROLE_DEVELOPER
ROLE_TENANT_ADMIN = ROLE_HQ_ADMIN
ROLE_SITE_MANAGER = ROLE_HQ_ADMIN
ROLE_STAFF = ROLE_OFFICER

USER_ROLE_ALIASES = {
    "developer": ROLE_DEVELOPER,
    "dev": ROLE_DEVELOPER,
    "platform_admin": ROLE_DEVELOPER,
    "super_admin": ROLE_DEVELOPER,
    "hq_admin": ROLE_HQ_ADMIN,
    "hq": ROLE_HQ_ADMIN,
    "hqadmin": ROLE_HQ_ADMIN,
    "hq_manager": ROLE_HQ_ADMIN,
    "headquarters_admin": ROLE_HQ_ADMIN,
    "headquarters_manager": ROLE_HQ_ADMIN,
    "branch_manager": ROLE_HQ_ADMIN,
    "branchmanager": ROLE_HQ_ADMIN,
    "tenant_admin": ROLE_HQ_ADMIN,
    "site_manager": ROLE_HQ_ADMIN,
    "admin": ROLE_HQ_ADMIN,
    "manager": ROLE_HQ_ADMIN,
    "supervisor": ROLE_SUPERVISOR,
    "vice_supervisor": ROLE_VICE_SUPERVISOR,
    "vice": ROLE_VICE_SUPERVISOR,
    "vice_manager": ROLE_VICE_SUPERVISOR,
    "sub_manager": ROLE_VICE_SUPERVISOR,
    "officer": ROLE_OFFICER,
    "employee": ROLE_OFFICER,
    "staff": ROLE_OFFICER,
    "l1": ROLE_OFFICER,
    "l2": ROLE_VICE_SUPERVISOR,
}

ROLE_ENUM_BY_USER_ROLE = {
    ROLE_OFFICER: ROLE_ENUM_OFFICER,
    ROLE_VICE_SUPERVISOR: ROLE_ENUM_VICE_SUPERVISOR,
    ROLE_SUPERVISOR: ROLE_ENUM_SUPERVISOR,
    ROLE_HQ_ADMIN: ROLE_ENUM_HQ_ADMIN,
    ROLE_DEVELOPER: ROLE_ENUM_DEVELOPER,
}

ALL_ROLES = {ROLE_DEV, ROLE_BRANCH_MANAGER, ROLE_EMPLOYEE}
SUPER_ADMIN_ROLES = {ROLE_DEV}
TENANT_MANAGERS = {ROLE_DEV}
SITE_MANAGERS = {ROLE_DEV, ROLE_BRANCH_MANAGER}
SUPERVISOR_ROLES = {ROLE_DEV, ROLE_BRANCH_MANAGER}


def normalize_user_role(user_role: str | None) -> str:
    normalized = str(user_role or "").strip().lower()
    if not normalized:
        return ROLE_OFFICER
    normalized = normalized.replace("-", "_").replace(" ", "_")
    normalized = re.sub(r"_+", "_", normalized)
    return USER_ROLE_ALIASES.get(normalized, normalized)


def is_valid_user_role(user_role: str | None) -> bool:
    return normalize_user_role(user_role) in ALL_USER_ROLES


def user_role_sql_variants(user_role: str | None) -> tuple[str, ...]:
    target = normalize_user_role(user_role)
    values = {target}
    for raw, mapped in USER_ROLE_ALIASES.items():
        if mapped == target:
            values.add(raw)
    return tuple(sorted(values))


def normalize_role(user_role: str | None) -> str:
    normalized_user_role = normalize_user_role(user_role)
    if normalized_user_role == ROLE_DEVELOPER:
        return ROLE_DEV
    if normalized_user_role == ROLE_HQ_ADMIN:
        return ROLE_BRANCH_MANAGER
    return ROLE_EMPLOYEE


def to_role_enum(user_role: str | None) -> str:
    normalized = normalize_user_role(user_role)
    return ROLE_ENUM_BY_USER_ROLE.get(normalized, ROLE_ENUM_OFFICER)


def resolve_permission_group(user_role: str | None) -> str:
    normalized = normalize_user_role(user_role)
    if normalized == ROLE_DEVELOPER:
        return PERMISSION_GROUP_DEV
    if normalized == ROLE_HQ_ADMIN:
        return PERMISSION_GROUP_ADMIN
    return PERMISSION_GROUP_STAFF


def is_super_admin(user_role: str | None) -> bool:
    return normalize_role(user_role) in SUPER_ADMIN_ROLES


def can_manage_user_accounts(user_role: str | None, *, allow_branch_manager: bool = False) -> bool:
    normalized = normalize_role(user_role)
    if normalized in SUPER_ADMIN_ROLES:
        return True
    if allow_branch_manager and normalized == ROLE_BRANCH_MANAGER:
        return True
    return False


def can_manage_tenant(user_role: str) -> bool:
    return normalize_role(user_role) in TENANT_MANAGERS


def can_manage_site(user_role: str) -> bool:
    return normalize_role(user_role) in SITE_MANAGERS


def can_post_attendance(user_role: str) -> bool:
    return normalize_role(user_role) in ALL_ROLES


def can_review_attendance_request(user_role: str) -> bool:
    return normalize_role(user_role) in SUPERVISOR_ROLES


def can_request_leave(user_role: str) -> bool:
    return normalize_role(user_role) in ALL_ROLES


def can_review_leave_request(user_role: str) -> bool:
    return normalize_role(user_role) in SUPERVISOR_ROLES


def can_manage_leave(user_role: str) -> bool:
    # Backward-compatible alias: leave "manage" means at least request permission.
    return can_request_leave(user_role)


def can_manage_schedule(user_role: str) -> bool:
    return normalize_role(user_role) in SUPERVISOR_ROLES
