from .v1.auth import router as auth_router
from .v1.me import router as me_router
from .v1.admin_sites import router as admin_sites_router
from .v1.admin_soc import router as admin_soc_router
from .v1.admin_reset import router as admin_reset_router
from .v1.companies import router as companies_router
from .v1.employees import router as employees_router
from .v1.sites import router as sites_router
from .v1.tenants import router as tenants_router
from .v1.attendance import router as attendance_router
from .v1.attendance_requests import router as attendance_requests_router
from .v1.debug import router as debug_router
from .v1.leaves import router as leaves_router
from .v1.schedules import router as schedules_router
from .v1.users import router as users_router
from .v1.master_tenants import router as master_tenants_router
from .v1.master_reset import router as master_reset_router
from .v1.integrations import router as integrations_router
from .v1.reports import router as reports_router

__all__ = [
    "auth_router",
    "me_router",
    "admin_sites_router",
    "admin_soc_router",
    "admin_reset_router",
    "companies_router",
    "employees_router",
    "sites_router",
    "tenants_router",
    "attendance_router",
    "attendance_requests_router",
    "debug_router",
    "leaves_router",
    "schedules_router",
    "users_router",
    "master_tenants_router",
    "master_reset_router",
    "integrations_router",
    "reports_router",
]
