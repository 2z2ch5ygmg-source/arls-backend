from .v1.auth import router as auth_router
from .v1.auth_public import router as auth_public_router
from .v1.me import router as me_router
from .v1.approvals import router as approvals_router
from .v1.certificates import router as certificates_router
from .v1.admin_sites import router as admin_sites_router
from .v1.admin_soc import router as admin_soc_router
from .v1.admin_reset import router as admin_reset_router
from .v1.admin_tenants import router as admin_tenants_router
from .v1.dev_scope import router as dev_scope_router
from .v1.companies import router as companies_router
from .v1.employees import router as employees_router
from .v1.sites import router as sites_router
from .v1.tenants import router as tenants_router
from .v1.attendance import router as attendance_router
from .v1.attendance_requests import router as attendance_requests_router
from .v1.debug import router as debug_router
from .v1.leaves import router as leaves_router
from .v1.schedules import router as schedules_router, bridge_router as schedules_bridge_router
from .v1.users import router as users_router
from .v1.master_tenants import router as master_tenants_router
from .v1.master_reset import router as master_reset_router
from .v1.integrations import router as integrations_router
from .v1.apple_weekly_truth import router as apple_weekly_truth_router
from .v1.mail import router as mail_router
from .v1.meetings import router as meetings_router
from .v1.messenger import router as messenger_router
from .v1.reports import router as reports_router
from .v1.hr_documents import router as hr_documents_router
from .v1.groupware_foundation import router as groupware_foundation_router
from .v1.home import router as home_router
from .v1.calendar import router as calendar_router
from .v1.notifications import router as notifications_router
from .v1.notices import router as notices_router
from .v1.push import router as push_router

__all__ = [
    "auth_router",
    "auth_public_router",
    "me_router",
    "approvals_router",
    "certificates_router",
    "admin_sites_router",
    "admin_soc_router",
    "admin_reset_router",
    "admin_tenants_router",
    "dev_scope_router",
    "companies_router",
    "employees_router",
    "sites_router",
    "tenants_router",
    "attendance_router",
    "attendance_requests_router",
    "debug_router",
    "leaves_router",
    "schedules_router",
    "schedules_bridge_router",
    "users_router",
    "master_tenants_router",
    "master_reset_router",
    "integrations_router",
    "apple_weekly_truth_router",
    "mail_router",
    "meetings_router",
    "messenger_router",
    "reports_router",
    "hr_documents_router",
    "groupware_foundation_router",
    "home_router",
    "calendar_router",
    "notifications_router",
    "notices_router",
    "push_router",
]
