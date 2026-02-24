from __future__ import annotations

ROLE_DEV = "dev"
ROLE_BRANCH_MANAGER = "branch_manager"
ROLE_EMPLOYEE = "employee"

# Backward-compatible aliases for legacy DB values / imports.
ROLE_PLATFORM_ADMIN = ROLE_DEV
ROLE_TENANT_ADMIN = ROLE_BRANCH_MANAGER
ROLE_SITE_MANAGER = ROLE_BRANCH_MANAGER
ROLE_SUPERVISOR = ROLE_BRANCH_MANAGER
ROLE_STAFF = ROLE_EMPLOYEE

ROLE_ALIASES = {
    "platform_admin": ROLE_DEV,
    "tenant_admin": ROLE_BRANCH_MANAGER,
    "site_manager": ROLE_BRANCH_MANAGER,
    "supervisor": ROLE_BRANCH_MANAGER,
    "staff": ROLE_EMPLOYEE,
    "dev": ROLE_DEV,
    "branch_manager": ROLE_BRANCH_MANAGER,
    "employee": ROLE_EMPLOYEE,
}

ALL_ROLES = {ROLE_DEV, ROLE_BRANCH_MANAGER, ROLE_EMPLOYEE}
SUPER_ADMIN_ROLES = {ROLE_DEV}
TENANT_MANAGERS = {ROLE_DEV}
SITE_MANAGERS = {ROLE_DEV, ROLE_BRANCH_MANAGER}
SUPERVISOR_ROLES = {ROLE_DEV, ROLE_BRANCH_MANAGER}


def normalize_role(user_role: str | None) -> str:
    normalized = str(user_role or "").strip().lower()
    if not normalized:
        return ROLE_EMPLOYEE
    return ROLE_ALIASES.get(normalized, normalized)


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
