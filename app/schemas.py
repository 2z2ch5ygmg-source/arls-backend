from __future__ import annotations

from datetime import date, datetime
import re
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

from .utils.permissions import ALL_USER_ROLES, normalize_user_role


class LoginRequest(BaseModel):
    tenant_code: str
    username: str
    password: str


class AuthUser(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID
    username: str
    full_name: str
    tenant_id: UUID
    tenant_code: str
    role: str
    employee_id: Optional[UUID] = None
    employee_code: Optional[str] = None
    is_master: Optional[bool] = Field(default=None, serialization_alias="isMaster")
    tenant_scope: Optional[str] = Field(default=None, serialization_alias="tenantScope")


class MeResponse(BaseModel):
    user_id: UUID
    tenant_id: UUID
    site_code: Optional[str] = None
    role: Literal["OFFICER", "VICE_SUPERVISOR", "SUPERVISOR", "HQ_ADMIN", "DEVELOPER"]
    group: Literal["STAFF", "ADMIN", "DEV"]


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    user: AuthUser


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class TenantCreate(BaseModel):
    tenant_code: Optional[str] = Field(default=None, min_length=1)
    tenant_name: str = Field(min_length=1)
    is_active: bool = True

    @field_validator("tenant_code", "tenant_name", mode="before")
    @classmethod
    def _trim_tenant_create_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return str(value).strip()


class TenantOut(BaseModel):
    id: UUID
    tenant_code: str
    tenant_name: str
    is_active: bool = True
    is_deleted: bool = False


class TenantUpdate(BaseModel):
    tenant_name: str = Field(min_length=1)
    is_active: bool = True


class TenantProfileUpdate(BaseModel):
    ceo_name: Optional[str] = None
    biz_reg_no: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    seal_attachment_id: Optional[str] = None

    @field_validator("ceo_name", "biz_reg_no", "address", "phone", "email", "seal_attachment_id", mode="before")
    @classmethod
    def _trim_tenant_profile_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None


class TenantProfileOut(BaseModel):
    tenant_id: UUID
    ceo_name: Optional[str] = None
    biz_reg_no: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    seal_attachment_id: Optional[str] = None
    updated_at: Optional[datetime] = None


class UserAdminCreate(BaseModel):
    tenant_id: Optional[UUID] = Field(
        default=None,
        validation_alias=AliasChoices("tenant_id", "tenantId"),
    )
    tenant_code: Optional[str] = Field(default=None, min_length=1, max_length=64)
    username: str = Field(min_length=1, max_length=120)
    full_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=120)
    role: str = Field(min_length=1, max_length=64)
    is_active: bool = True
    employee_code: Optional[str] = Field(default=None, max_length=64)

    @field_validator("tenant_code", "username", "full_name", "employee_code")
    @classmethod
    def _trimmed(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return value.strip()

    @model_validator(mode="after")
    def _tenant_ref_required(self) -> "UserAdminCreate":
        if self.tenant_id is not None:
            return self
        if str(self.tenant_code or "").strip():
            return self
        raise ValueError("tenant_id or tenant_code is required")

    @field_validator("role")
    @classmethod
    def _role(cls, value: str) -> str:
        normalized = normalize_user_role(value)
        if normalized not in ALL_USER_ROLES:
            raise ValueError("role must be officer/vice_supervisor/supervisor/hq_admin/developer")
        return normalized


class UserAdminRoleUpdate(BaseModel):
    role: str = Field(min_length=1, max_length=64)

    @field_validator("role")
    @classmethod
    def _role(cls, value: str) -> str:
        normalized = normalize_user_role(value)
        if normalized not in ALL_USER_ROLES:
            raise ValueError("role must be officer/vice_supervisor/supervisor/hq_admin/developer")
        return normalized


class UserAdminPasswordReset(BaseModel):
    new_password: str = Field(min_length=8, max_length=120)


class UserSelfPasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=120)
    new_password: str = Field(min_length=8, max_length=120)


class UserAdminActiveUpdate(BaseModel):
    is_active: bool


class UserAdminOut(BaseModel):
    id: UUID
    tenant_id: UUID
    tenant_code: str
    username: str
    full_name: str
    role: str
    is_active: bool
    employee_id: Optional[UUID] = None
    employee_code: Optional[str] = None
    last_login_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class CompanyCreate(BaseModel):
    company_code: str = Field(min_length=1)
    company_name: str = Field(min_length=1)


class CompanyOut(BaseModel):
    id: UUID
    company_code: str
    company_name: str
    tenant_code: str


class SiteCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    tenant_id: Optional[str] = Field(
        default=None,
        max_length=64,
        validation_alias=AliasChoices("tenant_id", "tenantId", "tenant_code", "tenantCode"),
    )
    company_code: Optional[str] = Field(default=None, max_length=64)
    site_code: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("site_code", "siteCode", "site_id", "siteId"),
    )
    site_name: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("site_name", "siteName", "name"),
    )
    address: Optional[str] = None
    place_id: Optional[str] = None
    latitude: Optional[float] = Field(
        default=None,
        validation_alias=AliasChoices("latitude", "lat"),
    )
    longitude: Optional[float] = Field(
        default=None,
        validation_alias=AliasChoices("longitude", "lng"),
    )
    radius_meters: Optional[float] = Field(
        default=None,
        validation_alias=AliasChoices("radius_meters", "radius_m", "radius"),
    )
    is_active: bool = True

    @field_validator("tenant_id", "company_code", "site_code", "site_name", "address", "place_id", mode="before")
    @classmethod
    def _trim_site_create_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return str(value).strip()


class SiteUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    tenant_id: Optional[str] = Field(
        default=None,
        max_length=64,
        validation_alias=AliasChoices("tenant_id", "tenantId", "tenant_code", "tenantCode"),
    )
    company_code: Optional[str] = Field(default=None, max_length=64)
    site_code: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("site_code", "siteCode", "site_id", "siteId"),
    )
    site_name: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("site_name", "siteName", "name"),
    )
    address: Optional[str] = None
    place_id: Optional[str] = None
    latitude: Optional[float] = Field(
        default=None,
        validation_alias=AliasChoices("latitude", "lat"),
    )
    longitude: Optional[float] = Field(
        default=None,
        validation_alias=AliasChoices("longitude", "lng"),
    )
    radius_meters: Optional[float] = Field(
        default=None,
        validation_alias=AliasChoices("radius_meters", "radius_m", "radius"),
    )
    is_active: bool = True

    @field_validator("tenant_id", "company_code", "site_code", "site_name", "address", "place_id", mode="before")
    @classmethod
    def _trim_site_update_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return str(value).strip()


class SiteActiveUpdate(BaseModel):
    is_active: bool


class SiteOut(BaseModel):
    id: UUID
    tenant_id: Optional[UUID] = None
    tenant_code: Optional[str] = None
    company_code: str
    site_code: str
    site_name: str
    address: Optional[str] = None
    place_id: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    radius_meters: Optional[float] = None
    is_active: bool = True


class SiteGeofenceOut(BaseModel):
    site_id: UUID
    site_code: str
    site_name: str
    lat: float
    lng: float
    radius_m: float


_GENDER_VALUE_MAP = {
    "M": "M",
    "MALE": "M",
    "남": "M",
    "남자": "M",
    "F": "F",
    "FEMALE": "F",
    "여": "F",
    "여자": "F",
}


def _normalize_gender_value(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    mapped = _GENDER_VALUE_MAP.get(normalized.upper()) or _GENDER_VALUE_MAP.get(normalized)
    if mapped:
        return mapped
    raise ValueError("gender must be one of M/F/male/female/남자/여자")


def _normalize_resident_no_value(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    digits = re.sub(r"\D+", "", normalized)
    if not digits:
        return None
    if len(digits) == 13:
        return f"{digits[:6]}-{digits[6:]}"
    # 형식이 완전하지 않은 경우도 값 자체는 보존하되 공백만 정리
    return normalized


class EmployeeCreate(BaseModel):
    tenant_id: Optional[UUID] = None
    site_id: Optional[UUID] = None
    company_code: Optional[str] = Field(default=None, min_length=1)
    site_code: Optional[str] = Field(default=None, min_length=1)
    # 직원 코드는 서버에서 <site_code>-NNN 형식으로 자동 생성한다.
    employee_code: Optional[str] = Field(default=None, min_length=1)
    management_no_str: Optional[str] = Field(default=None, max_length=64)
    full_name: str = Field(min_length=1)
    gender: Optional[str] = Field(default=None, max_length=16, validation_alias=AliasChoices("gender", "sex"))
    resident_no: Optional[str] = Field(
        default=None,
        max_length=32,
        validation_alias=AliasChoices("resident_no", "residentNo", "resident_number"),
    )
    phone: Optional[str] = None
    email: Optional[str] = Field(default=None, max_length=255)
    birth_date: Optional[date] = Field(default=None, validation_alias=AliasChoices("birth_date", "birthdate"))
    address: Optional[str] = Field(default=None, max_length=255)
    hire_date: Optional[date] = None
    leave_date: Optional[date] = Field(default=None, validation_alias=AliasChoices("leave_date", "leaveDate"))
    employment_status: Optional[str] = Field(
        default="active",
        max_length=32,
        validation_alias=AliasChoices("employment_status", "employmentStatus"),
    )
    loa_start_date: Optional[date] = Field(default=None, validation_alias=AliasChoices("loa_start_date", "loaStartDate"))
    loa_end_date: Optional[date] = Field(default=None, validation_alias=AliasChoices("loa_end_date", "loaEndDate"))
    guard_training_cert_no: Optional[str] = Field(
        default=None,
        max_length=120,
        validation_alias=AliasChoices("guard_training_cert_no", "training_cert_no"),
    )
    note: Optional[str] = Field(default=None, max_length=1000)
    roster_docx_attachment_id: Optional[str] = Field(
        default=None,
        max_length=64,
        validation_alias=AliasChoices("roster_docx_attachment_id", "roster_docx_id"),
    )
    photo_attachment_id: Optional[str] = Field(
        default=None,
        max_length=64,
        validation_alias=AliasChoices("photo_attachment_id", "photo_id"),
    )
    soc_login_id: Optional[str] = Field(default=None, max_length=120)
    soc_temp_password: Optional[str] = Field(default=None, max_length=120)
    soc_role: Optional[str] = Field(default=None, max_length=64)

    @field_validator(
        "company_code",
        "site_code",
        "employee_code",
        "management_no_str",
        "full_name",
        "gender",
        "resident_no",
        "phone",
        "email",
        "address",
        "employment_status",
        "guard_training_cert_no",
        "note",
        "roster_docx_attachment_id",
        "photo_attachment_id",
        "soc_login_id",
        "soc_temp_password",
        "soc_role",
    )
    @classmethod
    def _trimmed(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None

    @field_validator("gender", mode="before")
    @classmethod
    def _normalize_gender(cls, value: Optional[str]) -> Optional[str]:
        return _normalize_gender_value(value)

    @field_validator("resident_no", mode="before")
    @classmethod
    def _normalize_resident_no(cls, value: Optional[str]) -> Optional[str]:
        return _normalize_resident_no_value(value)

    @field_validator("email", mode="before")
    @classmethod
    def _normalize_email(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = str(value).strip().lower()
        if not normalized:
            return None
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("email must be a valid email")
        return normalized

    @field_validator("employment_status", mode="before")
    @classmethod
    def _normalize_employment_status(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return "active"
        normalized = str(value).strip().lower()
        if not normalized:
            return "active"
        aliases = {
            "active": "active",
            "재직": "active",
            "재직중": "active",
            "leave_of_absence": "leave_of_absence",
            "loa": "leave_of_absence",
            "휴직": "leave_of_absence",
            "terminated": "terminated",
            "retired": "terminated",
            "퇴직": "terminated",
            "inactive": "inactive",
            "비활성": "inactive",
        }
        resolved = aliases.get(normalized)
        if not resolved:
            raise ValueError("employment_status must be active/leave_of_absence/terminated/inactive")
        return resolved

    @model_validator(mode="after")
    def _site_ref_optional(self) -> "EmployeeCreate":
        # 지점관리자는 서버 세션(site scope)으로 site/company를 강제 주입하므로
        # 스키마 단계에서 site/company 필수로 막지 않는다.
        # DEV의 상세 검증은 employees 라우터에서 처리한다.
        return self

class EmployeeOut(BaseModel):
    id: UUID
    tenant_id: Optional[UUID] = None
    tenant_code: Optional[str] = None
    tenant_name: Optional[str] = None
    employee_code: str
    management_no_str: Optional[str] = None
    sequence_no: Optional[int] = None
    full_name: str
    gender: Optional[str] = None
    resident_no: Optional[str] = None
    phone: Optional[str]
    email: Optional[str] = None
    site_code: str
    site_name: Optional[str] = None
    company_code: str
    user_id: Optional[UUID] = None
    username: Optional[str] = None
    user_role: Optional[str] = None
    is_active: Optional[bool] = None
    is_deleted: Optional[bool] = None
    birth_date: Optional[date] = None
    address: Optional[str] = None
    hire_date: Optional[date] = None
    leave_date: Optional[date] = None
    employment_status: Optional[str] = None
    loa_start_date: Optional[date] = None
    loa_end_date: Optional[date] = None
    guard_training_cert_no: Optional[str] = None
    note: Optional[str] = None
    roster_docx_attachment_id: Optional[str] = None
    photo_attachment_id: Optional[str] = None
    soc_login_id: Optional[str] = None
    soc_role: Optional[str] = None


class EmployeeUpdate(BaseModel):
    full_name: str = Field(min_length=1)
    management_no_str: Optional[str] = Field(default=None, max_length=64)
    gender: Optional[str] = Field(default=None, max_length=16, validation_alias=AliasChoices("gender", "sex"))
    resident_no: Optional[str] = Field(
        default=None,
        max_length=32,
        validation_alias=AliasChoices("resident_no", "residentNo", "resident_number"),
    )
    phone: Optional[str] = None
    email: Optional[str] = Field(default=None, max_length=255)
    birth_date: Optional[date] = Field(default=None, validation_alias=AliasChoices("birth_date", "birthdate"))
    address: Optional[str] = Field(default=None, max_length=255)
    hire_date: Optional[date] = None
    leave_date: Optional[date] = Field(default=None, validation_alias=AliasChoices("leave_date", "leaveDate"))
    employment_status: Optional[str] = Field(
        default=None,
        max_length=32,
        validation_alias=AliasChoices("employment_status", "employmentStatus"),
    )
    loa_start_date: Optional[date] = Field(default=None, validation_alias=AliasChoices("loa_start_date", "loaStartDate"))
    loa_end_date: Optional[date] = Field(default=None, validation_alias=AliasChoices("loa_end_date", "loaEndDate"))
    guard_training_cert_no: Optional[str] = Field(
        default=None,
        max_length=120,
        validation_alias=AliasChoices("guard_training_cert_no", "training_cert_no"),
    )
    note: Optional[str] = Field(default=None, max_length=1000)
    roster_docx_attachment_id: Optional[str] = Field(
        default=None,
        max_length=64,
        validation_alias=AliasChoices("roster_docx_attachment_id", "roster_docx_id"),
    )
    photo_attachment_id: Optional[str] = Field(
        default=None,
        max_length=64,
        validation_alias=AliasChoices("photo_attachment_id", "photo_id"),
    )
    soc_login_id: Optional[str] = Field(default=None, max_length=120)
    soc_role: Optional[str] = Field(default=None, max_length=64)

    @field_validator(
        "full_name",
        "management_no_str",
        "gender",
        "resident_no",
        "phone",
        "address",
        "employment_status",
        "guard_training_cert_no",
        "note",
        "roster_docx_attachment_id",
        "photo_attachment_id",
        "soc_login_id",
        "soc_role",
    )
    @classmethod
    def _trimmed(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None

    @field_validator("gender", mode="before")
    @classmethod
    def _normalize_gender(cls, value: Optional[str]) -> Optional[str]:
        return _normalize_gender_value(value)

    @field_validator("employment_status", mode="before")
    @classmethod
    def _normalize_employment_status(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = str(value).strip().lower()
        if not normalized:
            return None
        aliases = {
            "active": "active",
            "재직": "active",
            "재직중": "active",
            "leave_of_absence": "leave_of_absence",
            "loa": "leave_of_absence",
            "휴직": "leave_of_absence",
            "terminated": "terminated",
            "retired": "terminated",
            "퇴직": "terminated",
            "inactive": "inactive",
            "비활성": "inactive",
        }
        resolved = aliases.get(normalized)
        if not resolved:
            raise ValueError("employment_status must be active/leave_of_absence/terminated/inactive")
        return resolved

    @field_validator("resident_no", mode="before")
    @classmethod
    def _normalize_resident_no(cls, value: Optional[str]) -> Optional[str]:
        return _normalize_resident_no_value(value)

    @field_validator("email", mode="before")
    @classmethod
    def _normalize_email(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = str(value).strip().lower()
        if not normalized:
            return None
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("email must be a valid email")
        return normalized


class AttendanceCreate(BaseModel):
    tenant_code: str
    employee_code: str
    site_code: str
    event_type: str
    event_at: datetime
    latitude: float
    longitude: float

    @field_validator("event_type")
    @classmethod
    def _event_type(cls, v: str) -> str:
        if v not in {"check_in", "check_out"}:
            raise ValueError("event_type must be check_in or check_out")
        return v


class AttendanceOut(BaseModel):
    id: UUID
    employee_code: str
    event_type: str
    event_at: datetime
    site_name: str
    distance_meters: float
    is_within_radius: bool
    auto_checkout: bool = False


class AttendanceRecordUpsertOut(BaseModel):
    record: AttendanceOut
    already_exists: bool = False


class AttendanceTodayStatusOut(BaseModel):
    status: str
    check_in_at: Optional[datetime] = None
    check_out_at: Optional[datetime] = None
    today_record_id: Optional[UUID] = None
    button_mode: Optional[str] = None
    button_label: Optional[str] = None
    auto_checkout: Optional[bool] = None
    site_id: Optional[UUID] = None
    site_code: Optional[str] = None
    site_name: Optional[str] = None
    employee_id: Optional[UUID] = None
    employee_name: Optional[str] = None
    business_date: Optional[str] = None
    schedule_id: Optional[UUID] = None
    shift_type: Optional[str] = None
    shift_start_at: Optional[datetime] = None
    shift_end_at: Optional[datetime] = None
    session_status: Optional[str] = None
    check_in_status: Optional[str] = None
    check_out_status: Optional[str] = None
    worked_minutes: Optional[int] = None
    open_session: bool = False


class PushDeviceRegisterIn(BaseModel):
    token: str
    platform: str
    device_id: Optional[str] = None

    @field_validator("token")
    @classmethod
    def _token_required(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("token is required")
        if len(normalized) > 4096:
            raise ValueError("token is too long")
        return normalized

    @field_validator("platform")
    @classmethod
    def _platform_required(cls, value: str) -> str:
        normalized = str(value or "").strip().lower()
        if not normalized:
            raise ValueError("platform is required")
        if normalized not in {"ios", "android", "web"}:
            raise ValueError("platform must be ios/android/web")
        return normalized


class PushDeviceRegisterOut(BaseModel):
    id: UUID
    platform: str
    is_active: bool
    last_seen_at: datetime


class AttendanceRequestCreate(BaseModel):
    tenant_code: str
    employee_code: str
    site_code: str
    request_type: str = "check_in"
    reason_code: str
    reason_detail: Optional[str] = None
    requested_at: datetime
    latitude: float
    longitude: float
    accuracy_meters: float = Field(ge=0)
    distance_meters: float = Field(ge=0)
    radius_meters: float = Field(gt=0)
    device_info: Optional[str] = None
    photo_names: list[str] = Field(default_factory=list, max_length=3)

    @field_validator("request_type")
    @classmethod
    def _request_type(cls, v: str) -> str:
        normalized = (v or "").strip().lower()
        if normalized not in {"check_in", "check_out"}:
            raise ValueError("request_type must be check_in/check_out")
        return normalized

    @field_validator("reason_code")
    @classmethod
    def _reason_code(cls, v: str) -> str:
        normalized = (v or "").strip().lower()
        if normalized not in {"gps_error", "site_request", "late", "other"}:
            raise ValueError("reason_code must be gps_error/site_request/late/other")
        return normalized


class AttendanceRequestReview(BaseModel):
    status: str
    review_note: Optional[str] = None

    @field_validator("status")
    @classmethod
    def _status(cls, v: str) -> str:
        normalized = (v or "").strip().lower()
        if normalized not in {"approved", "rejected"}:
            raise ValueError("status must be approved/rejected")
        return normalized


class AttendanceRequestOut(BaseModel):
    id: UUID
    tenant_code: str
    employee_code: str
    employee_name: Optional[str]
    site_code: str
    site_name: str
    site_latitude: float
    site_longitude: float
    request_type: str
    reason_code: str
    reason_detail: Optional[str]
    requested_at: datetime
    latitude: float
    longitude: float
    accuracy_meters: float
    distance_meters: float
    radius_meters: float
    device_info: Optional[str]
    photo_names: list[str]
    status: str
    review_note: Optional[str]
    reviewed_at: Optional[datetime]
    reviewed_by_username: Optional[str]
    created_at: datetime


class LeaveRequestCreate(BaseModel):
    tenant_code: str
    employee_code: str
    leave_type: str
    half_day_slot: Optional[str] = None
    start_at: date
    end_at: date
    reason: str = ""
    attachment_names: list[str] = Field(default_factory=list, max_length=3)

    @field_validator("leave_type")
    @classmethod
    def _leave_type(cls, v: str) -> str:
        normalized = (v or "").strip().lower()
        if normalized not in {"annual", "half", "sick", "other"}:
            raise ValueError("leave_type must be annual/half/sick/other")
        return normalized

    @field_validator("half_day_slot")
    @classmethod
    def _half_day_slot(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        normalized = v.strip().lower()
        if not normalized:
            return None
        if normalized not in {"am", "pm"}:
            raise ValueError("half_day_slot must be am/pm")
        return normalized

    @field_validator("attachment_names")
    @classmethod
    def _attachment_names(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in values or []:
            name = str(item or "").strip()
            if not name:
                continue
            if name not in normalized:
                normalized.append(name)
        if len(normalized) > 3:
            raise ValueError("attachment_names must be up to 3")
        return normalized

    @model_validator(mode="after")
    def _cross_validate(self) -> "LeaveRequestCreate":
        if self.start_at > self.end_at:
            raise ValueError("start_at must be before or equal to end_at")

        if self.leave_type == "half":
            if not self.half_day_slot:
                raise ValueError("half_day_slot is required when leave_type is half")
            if self.start_at != self.end_at:
                raise ValueError("half leave must use the same start_at and end_at date")
        else:
            self.half_day_slot = None

        return self


class LeaveRequestOut(BaseModel):
    id: UUID
    tenant_code: str
    employee_code: str
    employee_name: Optional[str] = None
    site_code: Optional[str] = None
    site_name: Optional[str] = None
    leave_type: str
    half_day_slot: Optional[str] = None
    start_at: date
    end_at: date
    reason: str
    attachment_names: list[str] = Field(default_factory=list)
    status: str
    requested_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    review_note: Optional[str] = None
    reviewed_by_username: Optional[str] = None


class LeaveRequestReview(BaseModel):
    status: str
    review_note: Optional[str] = None

    @field_validator("status")
    @classmethod
    def _status(cls, v: str) -> str:
        normalized = (v or "").strip().lower()
        if normalized not in {"approved", "rejected"}:
            raise ValueError("status must be approved/rejected")
        return normalized


class LeaveGrantCreate(BaseModel):
    employee_code: str = Field(min_length=1, max_length=64)
    policy_id: UUID
    grant_type: str = Field(default="manual", min_length=1, max_length=32)
    granted_days: float = Field(gt=0, le=366)
    effective_from: date
    effective_to: Optional[date] = None

    @field_validator("employee_code", mode="before")
    @classmethod
    def _trim_employee_code(cls, value: Optional[str]) -> str:
        return str(value or "").strip()

    @field_validator("grant_type")
    @classmethod
    def _grant_type(cls, value: str) -> str:
        normalized = str(value or "").strip().lower()
        if normalized not in {"manual", "annual"}:
            raise ValueError("grant_type must be manual/annual")
        return normalized

    @model_validator(mode="after")
    def _validate_dates(self) -> "LeaveGrantCreate":
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to must be after or equal to effective_from")
        return self


class LeaveGrantOut(BaseModel):
    id: UUID
    tenant_code: str
    employee_code: str
    employee_name: Optional[str] = None
    site_code: Optional[str] = None
    site_name: Optional[str] = None
    policy_id: Optional[UUID] = None
    policy_name: Optional[str] = None
    grant_type: str
    granted_days: float
    effective_from: date
    effective_to: Optional[date] = None
    reference_key: Optional[str] = None
    created_at: Optional[datetime] = None


class ScheduleCreateRow(BaseModel):
    tenant_code: str
    company_code: str
    site_code: str
    employee_code: str
    schedule_date: date
    shift_type: str

    @field_validator("shift_type")
    @classmethod
    def _shift_type(cls, v: str) -> str:
        normalized = v.strip().lower()
        aliases = {"leave": "off"}
        normalized = aliases.get(normalized, normalized)

        if normalized not in {"day", "night", "off", "holiday"}:
            raise ValueError("shift_type invalid")
        return normalized


class MonthlyScheduleRow(BaseModel):
    id: UUID
    tenant_code: str
    company_code: str
    site_code: str
    employee_code: str
    schedule_date: date
    shift_type: str
    leader_user_id: Optional[UUID] = None
    leader_username: Optional[str] = None
    leader_full_name: Optional[str] = None


class ScheduleUpdate(BaseModel):
    shift_type: str
    leader_user_id: Optional[UUID] = None
    schedule_note: Optional[str] = Field(default=None, max_length=500)

    @field_validator("shift_type")
    @classmethod
    def _shift_type(cls, v: str) -> str:
        normalized = v.strip().lower()
        aliases = {"leave": "off"}
        normalized = aliases.get(normalized, normalized)

        if normalized not in {"day", "overtime", "night", "off", "holiday"}:
            raise ValueError("shift_type invalid")
        return normalized

    @field_validator("schedule_note", mode="before")
    @classmethod
    def _schedule_note(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None


class ScheduleCloserUpdate(BaseModel):
    enabled: bool = True


class ScheduleLeaderCandidateOut(BaseModel):
    user_id: UUID
    username: str
    full_name: str
    employee_code: str
    duty_role: str
    display_role_label: Optional[str] = None
    is_recommended: bool = False


class ScheduleLeaderCandidatesOut(BaseModel):
    schedule_id: UUID
    site_code: str
    schedule_date: date
    current_leader_user_id: Optional[UUID] = None
    recommended_leader_user_id: Optional[UUID] = None
    candidates: list[ScheduleLeaderCandidateOut] = Field(default_factory=list)


class ScheduleTemplateBase(BaseModel):
    template_name: str = Field(min_length=1, max_length=120)
    duty_type: str = Field(min_length=1, max_length=32)
    start_time: Optional[str] = Field(default=None, max_length=8)
    end_time: Optional[str] = Field(default=None, max_length=8)
    paid_hours: Optional[float] = Field(default=None, ge=0, le=24)
    break_minutes: Optional[int] = Field(default=None, ge=0, le=1440)
    site_id: Optional[UUID] = None
    is_default: bool = False
    is_active: bool = True

    @field_validator("template_name")
    @classmethod
    def _template_name(cls, value: str) -> str:
        return str(value or "").strip()

    @field_validator("duty_type")
    @classmethod
    def _duty_type(cls, value: str) -> str:
        normalized = str(value or "").strip().lower()
        aliases = {
            "주간근무": "day",
            "초과근무": "overtime",
            "야간근무": "night",
            "daytime": "day",
            "nighttime": "night",
            "ot": "overtime",
        }
        mapped = aliases.get(normalized, normalized)
        if mapped not in {"day", "overtime", "night"}:
            raise ValueError("duty_type must be one of day/overtime/night")
        return mapped

    @field_validator("start_time", "end_time")
    @classmethod
    def _time_text(cls, value: Optional[str]) -> Optional[str]:
        text = str(value or "").strip()
        if not text:
            return None
        if re.fullmatch(r"\d{1,2}:\d{2}", text):
            hour, minute = text.split(":")
            hh = int(hour)
            mm = int(minute)
            if 0 <= hh <= 23 and 0 <= mm <= 59:
                return f"{hh:02d}:{mm:02d}:00"
        if re.fullmatch(r"\d{2}:\d{2}:\d{2}", text):
            hh, mm, ss = [int(part) for part in text.split(":")]
            if 0 <= hh <= 23 and 0 <= mm <= 59 and 0 <= ss <= 59:
                return f"{hh:02d}:{mm:02d}:{ss:02d}"
        raise ValueError("time must be HH:MM or HH:MM:SS")


class ScheduleTemplateCreate(ScheduleTemplateBase):
    pass


class ScheduleTemplateUpdate(BaseModel):
    template_name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    duty_type: Optional[str] = Field(default=None, min_length=1, max_length=32)
    start_time: Optional[str] = Field(default=None, max_length=8)
    end_time: Optional[str] = Field(default=None, max_length=8)
    paid_hours: Optional[float] = Field(default=None, ge=0, le=24)
    break_minutes: Optional[int] = Field(default=None, ge=0, le=1440)
    site_id: Optional[UUID] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None

    @field_validator("template_name")
    @classmethod
    def _template_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return str(value).strip()

    @field_validator("duty_type")
    @classmethod
    def _duty_type(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = str(value).strip().lower()
        aliases = {
            "주간근무": "day",
            "초과근무": "overtime",
            "야간근무": "night",
            "daytime": "day",
            "nighttime": "night",
            "ot": "overtime",
        }
        mapped = aliases.get(normalized, normalized)
        if mapped not in {"day", "overtime", "night"}:
            raise ValueError("duty_type must be one of day/overtime/night")
        return mapped

    @field_validator("start_time", "end_time")
    @classmethod
    def _time_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        if re.fullmatch(r"\d{1,2}:\d{2}", text):
            hour, minute = text.split(":")
            hh = int(hour)
            mm = int(minute)
            if 0 <= hh <= 23 and 0 <= mm <= 59:
                return f"{hh:02d}:{mm:02d}:00"
        if re.fullmatch(r"\d{2}:\d{2}:\d{2}", text):
            hh, mm, ss = [int(part) for part in text.split(":")]
            if 0 <= hh <= 23 and 0 <= mm <= 59 and 0 <= ss <= 59:
                return f"{hh:02d}:{mm:02d}:{ss:02d}"
        raise ValueError("time must be HH:MM or HH:MM:SS")


class ScheduleTemplateOut(BaseModel):
    id: UUID
    tenant_id: UUID
    template_name: str
    duty_type: str
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    paid_hours: Optional[float] = None
    break_minutes: Optional[int] = None
    site_id: Optional[UUID] = None
    site_code: Optional[str] = None
    site_name: Optional[str] = None
    is_default: bool = False
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ScheduleTemplateDeleteAffectedProfileOut(BaseModel):
    profile_id: str
    profile_name: str


class ScheduleTemplateDeleteOut(BaseModel):
    status: str = "deleted"
    template_id: UUID
    template_name: str
    deactivated_profile_count: int = 0
    invalidated_entry_count: int = 0
    deactivated_profiles: list[ScheduleTemplateDeleteAffectedProfileOut] = Field(default_factory=list)
    profile_notice: Optional[str] = None


class ScheduleTemplateSingleCreateIn(BaseModel):
    site_code: str = Field(min_length=1, max_length=64)
    employee_code: str = Field(min_length=1, max_length=64)
    template_id: UUID
    schedule_date: date
    tenant_code: Optional[str] = Field(default=None, max_length=64)

    @field_validator("site_code", "employee_code", "tenant_code")
    @classmethod
    def _trim_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return str(value).strip()


class ScheduleTemplateBulkCreateIn(BaseModel):
    site_code: str = Field(min_length=1, max_length=64)
    employee_code: str = Field(min_length=1, max_length=64)
    template_id: UUID
    schedule_dates: list[date] = Field(min_length=1, max_length=93)
    tenant_code: Optional[str] = Field(default=None, max_length=64)

    @field_validator("site_code", "employee_code", "tenant_code")
    @classmethod
    def _trim_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return str(value).strip()


class ScheduleBulkCreateIn(BaseModel):
    site_id: Optional[UUID] = None
    employee_id: Optional[UUID] = None
    site_code: Optional[str] = Field(default=None, max_length=64)
    employee_code: Optional[str] = Field(default=None, max_length=64)
    template_id: Optional[UUID] = None
    shift_type: Optional[str] = Field(default=None, max_length=32)
    shift_start_time: Optional[str] = Field(default=None, max_length=8)
    shift_end_time: Optional[str] = Field(default=None, max_length=8)
    schedule_note: Optional[str] = Field(default=None, max_length=500)
    dates: list[date] = Field(min_length=1, max_length=93)
    tenant_code: Optional[str] = Field(default=None, max_length=64)

    @field_validator(
        "site_code",
        "employee_code",
        "tenant_code",
        "shift_type",
        "shift_start_time",
        "shift_end_time",
        "schedule_note",
    )
    @classmethod
    def _trim_bulk_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @field_validator("shift_type")
    @classmethod
    def _normalize_bulk_shift_type(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = str(value).strip().lower()
        aliases = {"leave": "off"}
        normalized = aliases.get(normalized, normalized)
        if normalized not in {"day", "night", "off", "holiday"}:
            raise ValueError("shift_type invalid")
        return normalized

    @model_validator(mode="after")
    def _validate_scope_fields(self):
        if not self.site_id and not self.site_code:
            raise ValueError("site_id or site_code is required")
        if not self.employee_id and not self.employee_code:
            raise ValueError("employee_id or employee_code is required")
        if not self.template_id and not self.shift_type:
            raise ValueError("template_id or shift_type is required")
        return self


class ScheduleBulkCreateOut(BaseModel):
    created_count: int = 0
    skipped_duplicates: int = 0
    errors: list[str] = Field(default_factory=list)
    created_rows: list[dict] = Field(default_factory=list)


class ImportPreviewIssueLocationOut(BaseModel):
    sheet: Optional[str] = None
    row: Optional[int] = None
    col: Optional[int] = None
    col_label: Optional[str] = None
    section: Optional[str] = None


class ImportPreviewIssueOut(BaseModel):
    code: str
    severity: str
    message: str
    guidance: Optional[str] = None
    count: int = 1
    example_rows: list[int] = Field(default_factory=list)
    location: Optional[ImportPreviewIssueLocationOut] = None


class ScheduleImportMappingEntryOut(BaseModel):
    row_type: str
    numeric_hours: Optional[float] = None
    template_id: Optional[str] = None
    template_name: Optional[str] = None
    template_site_code: Optional[str] = None
    status: str = "ready"
    issue_code: Optional[str] = None
    issue_message: Optional[str] = None


class ScheduleImportMappingProfileOut(BaseModel):
    profile_id: Optional[str] = None
    profile_name: Optional[str] = None
    is_active: bool = False
    entry_count: int = 0
    updated_at: Optional[datetime] = None
    missing_required_entries: list[str] = Field(default_factory=list)
    missing_required_entry_labels: list[str] = Field(default_factory=list)
    entries: list[ScheduleImportMappingEntryOut] = Field(default_factory=list)


class ScheduleImportMappingEntryUpsert(BaseModel):
    row_type: Literal["day", "overtime", "night"]
    numeric_hours: float = Field(gt=0, le=24)
    template_id: UUID

    @field_validator("row_type", mode="before")
    @classmethod
    def _normalize_mapping_row_type(cls, value: str) -> str:
        normalized = str(value or "").strip().lower()
        if normalized not in {"day", "overtime", "night"}:
            raise ValueError("row_type must be day/overtime/night")
        return normalized


class ScheduleImportMappingProfileUpsert(BaseModel):
    profile_name: Optional[str] = Field(default=None, max_length=120)
    entries: list[ScheduleImportMappingEntryUpsert] = Field(default_factory=list)

    @field_validator("profile_name", mode="before")
    @classmethod
    def _trim_profile_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None


class ImportPreviewRowOut(BaseModel):
    row_no: int
    tenant_code: str
    company_code: str
    site_code: str
    employee_code: str
    employee_name: Optional[str] = None
    schedule_date: Optional[str] = None
    shift_type: str
    duty_type: Optional[str] = None
    source_sheet: Optional[str] = None
    source_col: Optional[str] = None
    source_block: Optional[str] = None
    section_label: Optional[str] = None
    template_id: Optional[str] = None
    template_name: Optional[str] = None
    work_value: Optional[str] = None
    current_work_value: Optional[str] = None
    parsed_semantic_type: Optional[str] = None
    mapped_hours: Optional[float] = None
    mapping_key: Optional[str] = None
    status_label: Optional[str] = None
    is_valid: bool
    is_blocking: bool = False
    diff_category: Optional[str] = None
    apply_action: Optional[str] = None
    is_protected: bool = False
    protected_reason: Optional[str] = None
    validation_code: Optional[str] = None
    validation_error: Optional[str] = None
    validator_kind: Optional[str] = None
    decision_stage: Optional[str] = None
    support_origin_type: Optional[str] = None
    preview_visibility_class: Optional[str] = None
    actionable: bool = False
    protected_info_only: bool = False


class ImportPreviewMetadataOut(BaseModel):
    tenant_code: Optional[str] = None
    site_code: Optional[str] = None
    month: Optional[str] = None
    template_family: Optional[str] = None
    export_revision: Optional[str] = None
    template_version: Optional[str] = None
    export_source_version: Optional[str] = None
    current_revision: Optional[str] = None
    workbook_kind: Optional[str] = None
    workbook_valid: bool = False
    revision_status: Optional[str] = None
    is_stale: bool = False
    analysis_run_id: Optional[str] = None
    analysis_context_key: Optional[str] = None
    analysis_file_sha256: Optional[str] = None
    analysis_stage: Optional[str] = None
    analysis_locked_fields: list[str] = Field(default_factory=list)
    stale_context_fields: list[str] = Field(default_factory=list)
    analysis_timings_ms: dict[str, float] = Field(default_factory=dict)
    mapping_profile: Optional[ScheduleImportMappingProfileOut] = None


class ImportPreviewOut(BaseModel):
    batch_id: UUID
    total_rows: int
    valid_rows: int
    invalid_rows: int
    applicable_rows: int = 0
    unchanged_rows: int = 0
    blocked_rows: int = 0
    warning_rows: int = 0
    invalid_samples: list[str]
    preview_rows: list[ImportPreviewRowOut] = Field(default_factory=list)
    error_counts: dict[str, int] = Field(default_factory=dict)
    diff_counts: dict[str, int] = Field(default_factory=dict)
    issues: list[ImportPreviewIssueOut] = Field(default_factory=list)
    blocked_reasons: list[str] = Field(default_factory=list)
    metadata: Optional[ImportPreviewMetadataOut] = None
    can_apply: bool = False


class ImportApplyRowOut(BaseModel):
    row_no: int
    employee_code: str
    site_code: str
    schedule_date: Optional[str] = None
    shift_type: str
    section_label: Optional[str] = None
    status: str
    reason: str


class ImportApplyOut(BaseModel):
    batch_id: UUID
    applied: int
    skipped: int
    applied_rows: list[ImportApplyRowOut] = Field(default_factory=list)
    skipped_rows: list[ImportApplyRowOut] = Field(default_factory=list)
    blocked: bool = False
    blocked_reasons: list[str] = Field(default_factory=list)
    apply_status: str = "blocked"
    upload_batch_id: Optional[UUID] = None
    audit_timestamp: Optional[datetime] = None
    base_schedule_created: int = 0
    base_schedule_updated: int = 0
    base_schedule_removed: int = 0
    artifact_generated: bool = False
    artifact_id: Optional[str] = None
    artifact_revision: Optional[str] = None
    artifact_generated_at: Optional[datetime] = None
    support_scope_count: int = 0
    sentrix_tickets_created: int = 0
    sentrix_tickets_updated: int = 0
    sentrix_tickets_retracted: int = 0
    failed_items: int = 0
    blocking_failures: list[str] = Field(default_factory=list)
    partial_failures: list[str] = Field(default_factory=list)


class SupportRoundtripStatusOut(BaseModel):
    site_code: str
    month: str
    source_state: str
    source_revision: Optional[str] = None
    artifact_id: Optional[str] = None
    artifact_revision: Optional[str] = None
    artifact_generated_at: Optional[datetime] = None
    source_uploaded_at: Optional[datetime] = None
    source_uploaded_by: Optional[str] = None
    source_filename: Optional[str] = None
    hq_merge_available: bool = False
    hq_merge_stale: bool = False
    final_download_enabled: bool = False
    latest_hq_uploaded_at: Optional[datetime] = None
    latest_hq_uploaded_by: Optional[str] = None
    latest_hq_filename: Optional[str] = None
    latest_hq_revision: Optional[str] = None
    latest_merged_revision: Optional[str] = None
    support_assignment_count: int = 0
    conflict_count: int = 0
    blocked_reasons: list[str] = Field(default_factory=list)


class SupportRoundtripPreviewRowOut(BaseModel):
    row_no: int
    site_code: str
    schedule_date: str
    support_period: str
    slot_index: int
    section_label: Optional[str] = None
    workbook_value: Optional[str] = None
    current_value: Optional[str] = None
    resolved_worker_type: Optional[str] = None
    resolved_worker_name: Optional[str] = None
    employee_code: Optional[str] = None
    employee_name: Optional[str] = None
    diff_category: str
    apply_action: str
    validation_code: Optional[str] = None
    validation_error: Optional[str] = None
    is_blocking: bool = False
    is_protected: bool = False
    protected_reason: Optional[str] = None


class SupportRoundtripPreviewMetadataOut(BaseModel):
    tenant_code: Optional[str] = None
    site_code: Optional[str] = None
    site_name: Optional[str] = None
    month: Optional[str] = None
    source_revision: Optional[str] = None
    current_source_revision: Optional[str] = None
    template_version: Optional[str] = None
    support_form_version: Optional[str] = None
    extracted_at_kst: Optional[str] = None
    is_stale: bool = False


class SupportRoundtripPreviewOut(BaseModel):
    batch_id: UUID
    total_rows: int
    valid_rows: int
    invalid_rows: int
    preview_rows: list[SupportRoundtripPreviewRowOut] = Field(default_factory=list)
    diff_counts: dict[str, int] = Field(default_factory=dict)
    blocked_reasons: list[str] = Field(default_factory=list)
    metadata: Optional[SupportRoundtripPreviewMetadataOut] = None
    can_apply: bool = False


class SupportRoundtripApplyRowOut(BaseModel):
    row_no: int
    site_code: str
    schedule_date: str
    support_period: str
    slot_index: int
    status: str
    reason: str
    worker_name: Optional[str] = None
    employee_name: Optional[str] = None


class SupportRoundtripApplyOut(BaseModel):
    batch_id: UUID
    applied: int
    skipped: int
    applied_rows: list[SupportRoundtripApplyRowOut] = Field(default_factory=list)
    skipped_rows: list[SupportRoundtripApplyRowOut] = Field(default_factory=list)
    blocked: bool = False
    blocked_reasons: list[str] = Field(default_factory=list)


class SupportRosterHqWorkspaceSiteOut(BaseModel):
    site_code: str
    site_name: str
    sheet_name: str
    sheet_name_valid: bool = True
    download_ready: bool = False
    source_state: str = "source_missing"
    upload_state: str = "파일 없음"
    selectable: bool = False
    selected: bool = False
    last_uploaded_at: Optional[datetime] = None
    source_uploaded_at: Optional[datetime] = None
    note: Optional[str] = None
    stale: bool = False
    stale_reason: Optional[str] = None
    blocked_reason: Optional[str] = None
    source_revision: Optional[str] = None
    latest_hq_revision: Optional[str] = None
    latest_status: str = "source_missing"
    hq_merge_stale: bool = False


class SupportRosterHqWorkspaceOut(BaseModel):
    tenant_code: str
    month: str
    tenant_name: Optional[str] = None
    actor_role: Optional[str] = None
    default_scope: str = "all"
    workbook_family: str
    template_version: str
    latest_status: str = "latest"
    current_step: str = "step3_extract"
    total_site_count: int = 0
    ready_site_count: int = 0
    available_site_codes: list[str] = Field(default_factory=list)
    selected_site_codes: list[str] = Field(default_factory=list)
    can_select_tenant: bool = False
    can_select_site_set: bool = True
    selection_capabilities: dict[str, bool] = Field(default_factory=dict)
    tenant_context: dict[str, Any] = Field(default_factory=dict)
    ui_summary: dict[str, Any] = Field(default_factory=dict)
    technical_details: dict[str, Any] = Field(default_factory=dict)
    resume_state: dict[str, Any] = Field(default_factory=dict)
    success_banner_summary: dict[str, Any] = Field(default_factory=dict)
    latest_artifact_id: Optional[str] = None
    generated_at: Optional[datetime] = None
    sites: list[SupportRosterHqWorkspaceSiteOut] = Field(default_factory=list)


class SupportRosterHqUploadMetaOut(BaseModel):
    file_name: str
    month: Optional[str] = None
    download_scope: str = "all"
    workbook_family: Optional[str] = None
    template_version: Optional[str] = None
    revision: Optional[str] = None
    latest_status: str = "unknown"
    latest: bool = False
    site_count: int = 0
    site_names: list[str] = Field(default_factory=list)
    site_codes: list[str] = Field(default_factory=list)
    selected_site_codes: list[str] = Field(default_factory=list)
    selected_site_code: Optional[str] = None
    selected_site_name: Optional[str] = None
    ui_summary: dict[str, Any] = Field(default_factory=dict)
    technical_details: dict[str, Any] = Field(default_factory=dict)


class SupportRosterHqReviewIssueOut(BaseModel):
    code: str
    severity: str
    title: str
    message: str
    guidance: Optional[str] = None
    count: int = 1
    sheet_name: Optional[str] = None
    site_code: Optional[str] = None
    site_name: Optional[str] = None
    work_date: Optional[date] = None
    shift_kind: Optional[str] = None


class SupportRosterHqReviewRowOut(BaseModel):
    row_kind: str = "worker"
    sheet_name: str
    site_name: Optional[str] = None
    site_code: Optional[str] = None
    work_date: Optional[date] = None
    shift_kind: Optional[str] = None
    slot_index: int = 0
    raw_cell_text: Optional[str] = None
    parsed_display_value: Optional[str] = None
    ticket_id: Optional[UUID] = None
    request_count: int = 0
    workbook_required_count: Optional[int] = None
    workbook_required_raw: Optional[str] = None
    valid_filled_count: int = 0
    target_status: Optional[str] = None
    status: str = "pending"
    reason: Optional[str] = None
    issue_code: Optional[str] = None


class SupportRosterHqAggregatedReviewRowOut(BaseModel):
    scope_key: str
    sheet_name: str
    site_name: Optional[str] = None
    site_code: Optional[str] = None
    work_date: Optional[date] = None
    shift_kind: Optional[str] = None
    request_count: int = 0
    entered_count: int = 0
    worker_names: str = ""
    ticket_status: Optional[str] = None
    ticket_status_label: Optional[str] = None
    reason: Optional[str] = None
    review_level: str = "review"
    blocking_errors: list[str] = Field(default_factory=list)
    blocking_issue_count: int = 0
    warning_issue_count: int = 0
    excluded: bool = False
    exclusion_reason: Optional[str] = None
    artifact_source_batch_id: Optional[str] = None
    artifact_source_revision: Optional[str] = None


class SupportRosterHqSiteProcessOut(BaseModel):
    sheet_name: str
    site_name: Optional[str] = None
    site_code: Optional[str] = None
    resolution_method: Optional[str] = None
    status: str
    message: Optional[str] = None
    expected_revision: Optional[str] = None
    current_revision: Optional[str] = None
    source_batch_id: Optional[str] = None
    fallback_text: Optional[str] = None


class SupportRosterHqScopeSummaryOut(BaseModel):
    scope_key: str
    sheet_name: str
    site_name: Optional[str] = None
    site_code: Optional[str] = None
    work_date: Optional[date] = None
    shift_kind: Optional[str] = None
    ticket_id: Optional[UUID] = None
    request_count: int = 0
    valid_filled_count: int = 0
    invalid_filled_count: int = 0
    target_status: Optional[str] = None
    current_status: Optional[str] = None
    workbook_required_count: Optional[int] = None
    workbook_required_raw: Optional[str] = None
    external_count_raw: Optional[str] = None
    purpose_text: Optional[str] = None
    scope_reason: Optional[str] = None
    day_reason_text: Optional[str] = None
    review_level: Optional[str] = None
    blocking_errors: list[str] = Field(default_factory=list)
    warning_messages: list[str] = Field(default_factory=list)
    matched_ticket: bool = False
    matched_artifact_scope: bool = False
    artifact_source_batch_id: Optional[str] = None
    artifact_source_revision: Optional[str] = None
    worker_entries: list[dict[str, Any]] = Field(default_factory=list)
    sheet_resolution_method: Optional[str] = None
    excluded: bool = False
    excluded_reason: Optional[str] = None
    blocking_issue_count: int = 0
    warning_issue_count: int = 0


class SupportRosterHqUploadInspectOut(BaseModel):
    batch_id: Optional[UUID] = None
    workbook_valid: bool = False
    can_apply: bool = False
    upload_meta: SupportRosterHqUploadMetaOut
    total_sheet_count: int = 0
    valid_sheet_count: int = 0
    total_scope_count: int = 0
    valid_scope_count: int = 0
    processed_site_count: int = 0
    stale_site_count: int = 0
    excluded_site_count: int = 0
    issue_count: int = 0
    summary: dict[str, int] = Field(default_factory=dict)
    issues: list[SupportRosterHqReviewIssueOut] = Field(default_factory=list)
    validated_sheets: list[SupportRosterHqSiteProcessOut] = Field(default_factory=list)
    missing_selected_sites: list[SupportRosterHqSiteProcessOut] = Field(default_factory=list)
    extra_unselected_sites: list[SupportRosterHqSiteProcessOut] = Field(default_factory=list)
    unresolved_sheets: list[SupportRosterHqSiteProcessOut] = Field(default_factory=list)
    stale_sites: list[SupportRosterHqSiteProcessOut] = Field(default_factory=list)
    blocking_errors: list[SupportRosterHqReviewIssueOut] = Field(default_factory=list)
    processed_sites: list[SupportRosterHqSiteProcessOut] = Field(default_factory=list)
    excluded_sites: list[SupportRosterHqSiteProcessOut] = Field(default_factory=list)
    scope_summaries: list[SupportRosterHqScopeSummaryOut] = Field(default_factory=list)
    review_rows: list[SupportRosterHqReviewRowOut] = Field(default_factory=list)
    aggregated_review_rows: list[SupportRosterHqAggregatedReviewRowOut] = Field(default_factory=list)
    next_step_message: Optional[str] = None
    ui_summary: dict[str, Any] = Field(default_factory=dict)
    technical_details: dict[str, Any] = Field(default_factory=dict)


class SupportRosterHqApplyScopeOut(BaseModel):
    scope_key: str
    sheet_name: str
    site_name: Optional[str] = None
    site_code: Optional[str] = None
    work_date: Optional[date] = None
    shift_kind: Optional[str] = None
    ticket_id: Optional[UUID] = None
    request_count: int = 0
    valid_filled_count: int = 0
    previous_status: Optional[str] = None
    target_status: Optional[str] = None
    assignment_count: int = 0
    bridge_action_count: int = 0
    snapshot_changed: bool = False
    handoff_status: Optional[str] = None
    handoff_message: Optional[str] = None
    sentrix_ticket_id: Optional[str] = None
    excluded: bool = False
    exclusion_reason: Optional[str] = None
    artifact_source_batch_id: Optional[str] = None
    artifact_source_revision: Optional[str] = None


class SupportRosterHqApplyOut(BaseModel):
    batch_id: UUID
    applied: bool = False
    partial_success: bool = False
    blocked: bool = False
    blocked_reasons: list[str] = Field(default_factory=list)
    issue_count: int = 0
    artifact_id: Optional[str] = None
    retry_token: Optional[str] = None
    handoff_status: str = "not_started"
    handoff_message: Optional[str] = None
    handoff_success_count: int = 0
    handoff_failed_count: int = 0
    created_scope_count: int = 0
    updated_scope_count: int = 0
    affected_scope_count: int = 0
    excluded_scope_count: int = 0
    affected_site_codes: list[str] = Field(default_factory=list)
    processed_site_codes: list[str] = Field(default_factory=list)
    excluded_site_codes: list[str] = Field(default_factory=list)
    stale_site_codes: list[str] = Field(default_factory=list)
    affected_dates: list[str] = Field(default_factory=list)
    assignments_created: int = 0
    assignments_removed: int = 0
    tickets_updated: int = 0
    tickets_auto_approved: int = 0
    tickets_pending: int = 0
    snapshots_created: int = 0
    notifications_created: int = 0
    notification_sites: int = 0
    push_sent: int = 0
    push_failed: int = 0
    bridge_actions_created: int = 0
    bridge_upserts: int = 0
    bridge_retracts: int = 0
    bridge_processed: int = 0
    bridge_failed: int = 0
    arls_materialized_created: int = 0
    arls_materialized_updated: int = 0
    arls_materialized_linked: int = 0
    arls_materialized_retracted: int = 0
    arls_materialized_noop: int = 0
    applied_scope_count: int = 0
    failed_scope_count: int = 0
    audit_timestamp: datetime
    completion_summary: dict[str, Any] = Field(default_factory=dict)
    technical_details: dict[str, Any] = Field(default_factory=dict)
    scope_results: list[SupportRosterHqApplyScopeOut] = Field(default_factory=list)


class InAppNotificationOut(BaseModel):
    id: UUID
    message: str
    type: str = "info"
    read: bool = False
    created_at: datetime
    read_at: Optional[datetime] = None
    payload: dict = Field(default_factory=dict)
    dedupe_key: Optional[str] = None


class InAppNotificationListOut(BaseModel):
    items: list[InAppNotificationOut] = Field(default_factory=list)
    unread_count: int = 0


NOTICE_CATEGORY_LITERAL = Literal["ops", "attendance", "schedule", "hr", "system", "event"]
NOTICE_BODY_BLOCK_KIND_LITERAL = Literal["paragraph", "image", "table", "poll"]
NOTICE_BODY_PARAGRAPH_VARIANT_LITERAL = Literal["lead", "body"]
NOTICE_POLL_RESULT_VISIBILITY_LITERAL = Literal["always", "after_close"]


class NoticePollOption(BaseModel):
    option_id: Optional[str] = Field(default=None, max_length=64)
    label: str = Field(min_length=1, max_length=160)
    vote_count: int = 0
    vote_ratio: float = 0
    selected: bool = False

    @field_validator("option_id", "label", mode="before")
    @classmethod
    def _trim_notice_poll_option_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None


class NoticePollBlock(BaseModel):
    poll_id: Optional[str] = Field(default=None, max_length=64)
    question: str = Field(min_length=1, max_length=240)
    options: list[NoticePollOption] = Field(default_factory=list, min_length=2, max_length=10)
    allow_multiple: bool = False
    is_anonymous: bool = True
    result_visibility: NOTICE_POLL_RESULT_VISIBILITY_LITERAL = "always"
    closes_at: Optional[datetime] = None
    allow_change_vote: bool = False
    total_votes: int = 0
    selected_option_ids: list[str] = Field(default_factory=list, max_length=10)
    results_visible: bool = True
    is_closed: bool = False
    can_vote: bool = True
    has_voted: bool = False

    @field_validator("poll_id", "question", mode="before")
    @classmethod
    def _trim_notice_poll_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @field_validator("selected_option_ids", mode="before")
    @classmethod
    def _normalize_notice_poll_selected_option_ids(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, (list, tuple)):
            return []
        seen: set[str] = set()
        rows: list[str] = []
        for item in value:
            normalized = str(item or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            rows.append(normalized)
        return rows[:10]

    @model_validator(mode="after")
    def _validate_notice_poll_block(self):
        valid_options = [option for option in self.options if str(option.label or "").strip()]
        if len(valid_options) < 2:
            raise ValueError("notice poll requires at least two options")
        self.options = valid_options[:10]
        if not self.allow_multiple and len(self.selected_option_ids) > 1:
            self.selected_option_ids = self.selected_option_ids[:1]
        self.total_votes = max(0, int(self.total_votes or 0))
        return self


class NoticeBodyBlock(BaseModel):
    kind: NOTICE_BODY_BLOCK_KIND_LITERAL
    variant: Optional[NOTICE_BODY_PARAGRAPH_VARIANT_LITERAL] = None
    title: Optional[str] = Field(default=None, max_length=120)
    text: Optional[str] = Field(default=None, max_length=4000)
    attachment_id: Optional[str] = Field(default=None, max_length=64)
    file_name: Optional[str] = Field(default=None, max_length=200)
    caption: Optional[str] = Field(default=None, max_length=240)
    image_src: Optional[str] = Field(default=None, max_length=5000000)
    columns: list[str] = Field(default_factory=list, max_length=6)
    rows: list[list[str]] = Field(default_factory=list, max_length=20)
    poll: Optional[NoticePollBlock] = None

    @field_validator("title", "text", "attachment_id", "file_name", "caption", mode="before")
    @classmethod
    def _trim_notice_block_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @field_validator("columns", mode="before")
    @classmethod
    def _normalize_notice_block_columns(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, (list, tuple)):
            return [str(item or "").strip() for item in value][:6]
        return []

    @field_validator("rows", mode="before")
    @classmethod
    def _normalize_notice_block_rows(cls, value: Any) -> list[list[str]]:
        if value is None:
            return []
        if not isinstance(value, (list, tuple)):
            return []
        rows: list[list[str]] = []
        for row in value[:20]:
            if isinstance(row, (list, tuple)):
                rows.append([str(cell or "").strip() for cell in row][:6])
        return rows

    @model_validator(mode="after")
    def _validate_notice_body_block(self):
        if self.kind == "paragraph":
            if not self.text:
                raise ValueError("paragraph text is required")
            if self.variant is None:
                self.variant = "body"
            self.attachment_id = None
            self.file_name = None
            self.caption = None
            self.image_src = None
            self.columns = []
            self.rows = []
            return self
        if self.kind == "image":
            if not self.attachment_id and not self.image_src:
                raise ValueError("image attachment_id is required")
            self.variant = None
            self.text = None
            self.columns = []
            self.rows = []
            self.poll = None
            return self
        if self.kind == "poll":
            if self.poll is None:
                raise ValueError("poll data is required")
            self.variant = None
            self.title = None
            self.text = None
            self.attachment_id = None
            self.file_name = None
            self.caption = None
            self.image_src = None
            self.columns = []
            self.rows = []
            return self
        if not self.columns and not self.rows:
            raise ValueError("table columns or rows are required")
        self.variant = None
        self.text = None
        self.attachment_id = None
        self.file_name = None
        self.caption = None
        self.image_src = None
        self.poll = None
        return self


class NoticeCreateIn(BaseModel):
    category: NOTICE_CATEGORY_LITERAL
    title: str = Field(min_length=1, max_length=160)
    body_text: str = Field(default="", max_length=20000)
    body_blocks: list[NoticeBodyBlock] = Field(default_factory=list)
    is_pinned: bool = False

    @field_validator("title", mode="before")
    @classmethod
    def _trim_notice_title(cls, value: Optional[str]) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("value is required")
        return normalized

    @field_validator("body_text", mode="before")
    @classmethod
    def _trim_notice_body_text(cls, value: Optional[str]) -> str:
        return str(value or "").strip()


class NoticeUpdateIn(NoticeCreateIn):
    pass


class NoticeSummaryOut(BaseModel):
    id: UUID
    category: NOTICE_CATEGORY_LITERAL
    title: str
    body_preview: Optional[str] = None
    is_pinned: bool = False
    published_at: datetime
    created_at: datetime
    updated_at: datetime
    created_by_name: Optional[str] = None


class NoticeDetailOut(NoticeSummaryOut):
    body_text: str
    body_blocks: list[NoticeBodyBlock] = Field(default_factory=list)


class NoticeListOut(BaseModel):
    items: list[NoticeSummaryOut] = Field(default_factory=list)


HOME_BRIEFING_AUDIENCE_LITERAL = Literal["hq", "supervisor", "vice", "officer"]
HOME_BRIEFING_TONE_LITERAL = Literal["neutral", "info", "warn", "success", "error", "accent"]


class HomeBriefingListRowOut(BaseModel):
    title: str
    subtitle: Optional[str] = None
    value: Optional[str] = None
    pill_label: Optional[str] = None
    pill_tone: HOME_BRIEFING_TONE_LITERAL = "neutral"


class HomeBriefingOpsSummaryOut(BaseModel):
    attendance_rate: int = 0
    scheduled_count: int = 0
    present_count: int = 0
    missing_count: int = 0
    issue_count: int = 0
    pending_approval_count: int = 0
    vacancy_site_count: int = 0
    site_count: int = 0


class HomeBriefingRequestSummaryOut(BaseModel):
    total_pending_count: int = 0
    leave_pending_count: int = 0
    attendance_pending_count: int = 0
    correction_pending_count: int = 0
    unread_count: int = 0


class HomeBriefingSiteSummaryOut(BaseModel):
    site_code: Optional[str] = None
    site_name: Optional[str] = None
    scheduled_count: int = 0
    present_count: int = 0
    missing_count: int = 0
    pending_request_count: int = 0
    leave_or_night_count: int = 0
    schedule_gap_count: int = 0


class HomeBriefingSiteReadinessOut(BaseModel):
    site_code: Optional[str] = None
    site_name: Optional[str] = None
    scheduled_count: int = 0
    present_count: int = 0
    missing_count: int = 0
    pending_request_count: int = 0
    readiness_issue_count: int = 0


class HomeBriefingPersonalSummaryOut(BaseModel):
    employee_name: Optional[str] = None
    site_code: Optional[str] = None
    site_name: Optional[str] = None
    site_latitude: Optional[float] = None
    site_longitude: Optional[float] = None
    site_radius_meters: Optional[float] = None
    today_status: str = "NONE"
    button_mode: Optional[str] = None
    check_in_at: Optional[datetime] = None
    check_out_at: Optional[datetime] = None
    auto_checkout: bool = False
    next_shift_label: Optional[str] = None
    pending_leave_count: int = 0
    pending_attendance_count: int = 0
    unread_count: int = 0


class HomeBriefingWeekSummaryOut(BaseModel):
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    scheduled_days: int = 0
    worked_days: int = 0
    off_days: int = 0


class HomeNoticeHighlightOut(BaseModel):
    notice_id: Optional[UUID] = None
    title: str = ""
    summary: str = ""
    category: Optional[NOTICE_CATEGORY_LITERAL] = None
    date_label: Optional[str] = None
    published_at: Optional[datetime] = None
    is_pinned: bool = False


class HomeAttendanceTrendPointOut(BaseModel):
    date: str
    label: str
    completed: int = 0
    missing: int = 0
    late: int = 0


class HomeSiteAttendanceOut(BaseModel):
    site_code: Optional[str] = None
    site_name: Optional[str] = None
    scheduled: int = 0
    present: int = 0
    missing: int = 0
    late: int = 0
    attendance_rate: int = 0


class HomeSupportWorkSummaryOut(BaseModel):
    requested: int = 0
    assigned: int = 0
    confirmed: int = 0
    cancelled: int = 0
    total: int = 0
    source_label: Optional[str] = None


class HomeTaskSummaryOut(BaseModel):
    approval_pending: int = 0
    leave_request: int = 0
    schedule_change_request: int = 0
    support_work_request: int = 0


class HomeTeamAttendanceBreakdownOut(BaseModel):
    total: int = 0
    normal: int = 0
    late: int = 0
    early: int = 0
    missing: int = 0
    other: int = 0
    normal_rate: int = 0
    late_rate: int = 0
    early_rate: int = 0
    missing_rate: int = 0


class HomeMissingStaffOut(BaseModel):
    employee_id: Optional[UUID] = None
    employee_code: Optional[str] = None
    employee_name: str
    role_label: Optional[str] = None
    site_code: Optional[str] = None
    site_name: Optional[str] = None
    phone: Optional[str] = None
    avatar_initials: Optional[str] = None
    photo_attachment_id: Optional[str] = None


class HomeWorkTimeSummaryOut(BaseModel):
    today_worked_minutes: int = 0
    today_expected_minutes: int = 0
    week_worked_minutes: int = 0
    week_target_minutes: int = 0
    today_progress_percent: int = 0
    week_progress_percent: int = 0


class HomeNextShiftOut(BaseModel):
    date: Optional[str] = None
    weekday: Optional[str] = None
    site_code: Optional[str] = None
    site_name: Optional[str] = None
    shift_type: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    label: Optional[str] = None


class HomeWeekDayOut(BaseModel):
    date: str
    weekday: str
    work_status: str = "-"
    check_in: Optional[str] = None
    check_out: Optional[str] = None
    worked_minutes: int = 0
    shift_type: Optional[str] = None
    site_name: Optional[str] = None


class HomeLeaveBalanceSummaryOut(BaseModel):
    remaining_days: Optional[float] = None
    used_days: Optional[float] = None
    total_days: Optional[float] = None
    pending_count: int = 0
    source_label: Optional[str] = None
    source_available: bool = False


class HomeDataSourceRegisterItemOut(BaseModel):
    field: str
    source_type: Literal["aggregate-only", "client-runtime", "domain-owned source addition required", "approved fallback-only"]
    source: str
    notes: Optional[str] = None


class HomeBriefingOut(BaseModel):
    audience: HOME_BRIEFING_AUDIENCE_LITERAL
    date: str
    role_label: str
    scope_label: str
    notice_rows: list[NoticeSummaryOut] = Field(default_factory=list)
    ops_summary: Optional[HomeBriefingOpsSummaryOut] = None
    attendance_issue_rows: list[HomeBriefingListRowOut] = Field(default_factory=list)
    schedule_risk_rows: list[HomeBriefingListRowOut] = Field(default_factory=list)
    approval_summary: Optional[HomeBriefingRequestSummaryOut] = None
    org_issue_rows: list[HomeBriefingListRowOut] = Field(default_factory=list)
    site_summary: Optional[HomeBriefingSiteSummaryOut] = None
    team_attention_rows: list[HomeBriefingListRowOut] = Field(default_factory=list)
    site_readiness_summary: Optional[HomeBriefingSiteReadinessOut] = None
    personal_summary: Optional[HomeBriefingPersonalSummaryOut] = None
    week_summary: Optional[HomeBriefingWeekSummaryOut] = None
    request_summary: Optional[HomeBriefingRequestSummaryOut] = None
    notice_highlight: Optional[HomeNoticeHighlightOut] = None
    attendance_trend: list[HomeAttendanceTrendPointOut] = Field(default_factory=list)
    site_attendance_rows: list[HomeSiteAttendanceOut] = Field(default_factory=list)
    support_work_summary: Optional[HomeSupportWorkSummaryOut] = None
    task_summary: Optional[HomeTaskSummaryOut] = None
    team_attendance_breakdown: Optional[HomeTeamAttendanceBreakdownOut] = None
    team_trend: list[HomeAttendanceTrendPointOut] = Field(default_factory=list)
    missing_staff_rows: list[HomeMissingStaffOut] = Field(default_factory=list)
    work_time_summary: Optional[HomeWorkTimeSummaryOut] = None
    next_shift: Optional[HomeNextShiftOut] = None
    week_rows: list[HomeWeekDayOut] = Field(default_factory=list)
    leave_balance: Optional[HomeLeaveBalanceSummaryOut] = None
    data_source_register: list[HomeDataSourceRegisterItemOut] = Field(default_factory=list)


CALENDAR_AUDIENCE_LITERAL = Literal["hq", "supervisor", "vice", "officer"]
CALENDAR_VIEW_LITERAL = Literal["week", "month", "agenda", "booking-links"]
CALENDAR_PERMISSION_LITERAL = Literal["view_only", "free_busy_only", "edit", "owner"]


class CalendarCapabilityOut(BaseModel):
    can_view: bool = True
    can_create: bool = False
    can_manage_shared: bool = False
    can_manage_booking_links: bool = False
    can_manage_sync: bool = False


class CalendarMiniMonthDayOut(BaseModel):
    date: str
    day: int
    in_month: bool = True
    is_today: bool = False
    is_selected: bool = False


class CalendarContainerOut(BaseModel):
    id: UUID
    scope_type: str
    name: str
    color: str = "#ff7a1a"
    provider: str = "arls"
    permission: CALENDAR_PERMISSION_LITERAL = "view_only"
    is_default: bool = False
    is_system: bool = False
    badge_label: Optional[str] = None
    owner_label: Optional[str] = None


class CalendarReminderOut(BaseModel):
    id: UUID
    channel: str = "in_app"
    minutes_before: Optional[int] = None
    absolute_trigger_at: Optional[datetime] = None
    snoozed_until: Optional[datetime] = None


class CalendarNoteOut(BaseModel):
    id: UUID
    note_type: str = "shared"
    body: str = ""
    author_label: Optional[str] = None
    updated_at: Optional[datetime] = None


class CalendarCommentOut(BaseModel):
    id: UUID
    body: str = ""
    author_label: Optional[str] = None
    is_internal: bool = False
    created_at: Optional[datetime] = None


class CalendarCommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    is_internal: bool = False

    @field_validator("body", mode="before")
    @classmethod
    def _trim_calendar_comment_body(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None


class CalendarActionItemOut(BaseModel):
    id: UUID
    body: str
    state: str = "open"
    assignee_label: Optional[str] = None
    due_at: Optional[datetime] = None


class CalendarAttachmentOut(BaseModel):
    id: UUID
    label: str
    url: str
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = None


class CalendarAttendeeOut(BaseModel):
    id: UUID
    display_name: str
    email: Optional[str] = None
    user_id: Optional[UUID] = None
    employee_id: Optional[UUID] = None
    is_required: bool = True
    is_organizer: bool = False
    rsvp_status: str = "needs_action"


class CalendarAttendeeOptionOut(BaseModel):
    user_id: Optional[UUID] = None
    employee_id: Optional[UUID] = None
    display_name: str
    subtitle: Optional[str] = None
    email: Optional[str] = None


class CalendarResourceOut(BaseModel):
    id: UUID
    resource_code: str
    resource_name: str
    resource_type: str = "room"
    capacity: Optional[int] = None
    site_label: Optional[str] = None


class CalendarBusySlotOut(BaseModel):
    starts_at: datetime
    ends_at: datetime
    title: Optional[str] = None
    status: str = "busy"


class CalendarAvailabilityLaneOut(BaseModel):
    lane_key: str
    lane_label: str
    lane_type: str = "attendee"
    slots: list[CalendarBusySlotOut] = Field(default_factory=list)


class CalendarSuggestedSlotOut(BaseModel):
    starts_at: datetime
    ends_at: datetime
    label: str
    attendee_match_count: int = 0
    attendee_total_count: int = 0
    resource_ready: bool = True


class CalendarAvailabilityOut(BaseModel):
    timezone: str = "Asia/Seoul"
    working_hours_label: str = "09:00-18:00"
    range_start: datetime
    range_end: datetime
    lanes: list[CalendarAvailabilityLaneOut] = Field(default_factory=list)
    suggested_slots: list[CalendarSuggestedSlotOut] = Field(default_factory=list)


class CalendarCustomFieldRowOut(BaseModel):
    key: str
    label: str
    value: str = ""
    field_type: str = "text"


class CalendarCustomFieldRowIn(BaseModel):
    key: Optional[str] = Field(default=None, max_length=64)
    label: str = Field(min_length=1, max_length=120)
    value: str = Field(default="", max_length=1000)
    field_type: str = Field(default="text", max_length=32)

    @field_validator("key", "label", "value", "field_type", mode="before")
    @classmethod
    def _trim_calendar_custom_field_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @field_validator("field_type")
    @classmethod
    def _normalize_calendar_custom_field_type(cls, value: Optional[str]) -> str:
        normalized = str(value or "text").strip().lower()
        if normalized not in {"text", "number", "select"}:
            return "text"
        return normalized


class CalendarEventOut(BaseModel):
    id: UUID
    container_id: UUID
    title: str
    starts_at: datetime
    ends_at: datetime
    timezone: str = "Asia/Seoul"
    is_all_day: bool = False
    recurrence_rule: Optional[str] = None
    availability_status: str = "busy"
    visibility: str = "private"
    location: Optional[str] = None
    conferencing_provider: Optional[str] = None
    conferencing_url: Optional[str] = None
    description: Optional[str] = None
    resource_id: Optional[UUID] = None
    resource_label: Optional[str] = None
    status: str = "confirmed"
    attendees: list[CalendarAttendeeOut] = Field(default_factory=list)
    reminders: list[CalendarReminderOut] = Field(default_factory=list)
    notes: list[CalendarNoteOut] = Field(default_factory=list)
    comments: list[CalendarCommentOut] = Field(default_factory=list)
    action_items: list[CalendarActionItemOut] = Field(default_factory=list)
    attachments: list[CalendarAttachmentOut] = Field(default_factory=list)
    custom_fields: list[CalendarCustomFieldRowOut] = Field(default_factory=list)


class CalendarBookingLinkOut(BaseModel):
    id: UUID
    container_id: Optional[UUID] = None
    slug: str
    title: str
    description: Optional[str] = None
    approval_required: bool = False
    approval_policy: str = "instant"
    assignment_mode: str = "single_host"
    is_public: bool = True
    booking_window_days: int = 14
    buffer_before_minutes: int = 0
    buffer_after_minutes: int = 0
    duration_minutes: int = 30
    availability_start_time: str = "09:00"
    availability_end_time: str = "18:00"
    expires_at: Optional[datetime] = None
    host_notes: Optional[str] = None
    intake_questions: list["CalendarBookingQuestionOut"] = Field(default_factory=list)
    owner_label: Optional[str] = None


class CalendarBookingQuestionOut(BaseModel):
    key: str
    label: str
    answer_type: str = "short_text"
    required: bool = True
    options: list[str] = Field(default_factory=list)


class CalendarBookingQuestionIn(BaseModel):
    key: Optional[str] = Field(default=None, max_length=64)
    label: str = Field(min_length=1, max_length=160)
    answer_type: str = Field(default="short_text", max_length=32)
    required: bool = True
    options: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("key", "label", "answer_type", mode="before")
    @classmethod
    def _trim_calendar_booking_question_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @field_validator("answer_type")
    @classmethod
    def _normalize_calendar_booking_answer_type(cls, value: str) -> str:
        normalized = str(value or "short_text").strip().lower()
        if normalized not in {"short_text", "long_text", "select"}:
            raise ValueError("answer_type must be short_text, long_text, or select")
        return normalized

    @field_validator("options", mode="before")
    @classmethod
    def _normalize_calendar_booking_options(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, (list, tuple)):
            return []
        rows: list[str] = []
        seen: set[str] = set()
        for item in value:
            normalized = str(item or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            rows.append(normalized)
        return rows[:12]


class CalendarBookingLinkCreateIn(BaseModel):
    container_id: UUID
    title: str = Field(min_length=1, max_length=160)
    description: Optional[str] = Field(default=None, max_length=4000)
    is_public: bool = True
    approval_required: bool = False
    approval_policy: str = Field(default="instant", max_length=32)
    assignment_mode: str = Field(default="single_host", max_length=32)
    booking_window_days: int = Field(default=14, ge=1, le=90)
    buffer_before_minutes: int = Field(default=0, ge=0, le=180)
    buffer_after_minutes: int = Field(default=0, ge=0, le=180)
    duration_minutes: int = Field(default=30, ge=15, le=240)
    availability_start_time: str = Field(default="09:00", max_length=5)
    availability_end_time: str = Field(default="18:00", max_length=5)
    expires_at: Optional[datetime] = None
    host_notes: Optional[str] = Field(default=None, max_length=4000)
    intake_questions: list[CalendarBookingQuestionIn] = Field(default_factory=list, max_length=8)

    @field_validator(
        "title",
        "description",
        "availability_start_time",
        "availability_end_time",
        "host_notes",
        mode="before",
    )
    @classmethod
    def _trim_calendar_booking_link_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @field_validator("availability_start_time", "availability_end_time")
    @classmethod
    def _validate_calendar_booking_time_text(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", normalized):
            raise ValueError("availability time must be HH:MM")
        return normalized

    @field_validator("approval_policy")
    @classmethod
    def _normalize_calendar_booking_approval_policy(cls, value: str) -> str:
        normalized = str(value or "instant").strip().lower()
        if normalized not in {"instant", "manual"}:
            raise ValueError("approval_policy must be instant or manual")
        return normalized

    @field_validator("assignment_mode")
    @classmethod
    def _normalize_calendar_booking_assignment_mode(cls, value: str) -> str:
        normalized = str(value or "single_host").strip().lower()
        if normalized not in {"single_host", "collective", "round_robin"}:
            raise ValueError("assignment_mode must be single_host, collective, or round_robin")
        return normalized

    @model_validator(mode="after")
    def _validate_calendar_booking_window(self):
        if self.approval_required:
            self.approval_policy = "manual"
        self.approval_required = self.approval_policy == "manual"
        if self.availability_start_time >= self.availability_end_time:
            raise ValueError("availability_end_time must be later than availability_start_time")
        return self


class CalendarBookingLinkUpdateIn(CalendarBookingLinkCreateIn):
    pass


class CalendarBookingSlotOut(BaseModel):
    starts_at: datetime
    ends_at: datetime
    label: str
    date_label: Optional[str] = None


class CalendarBookingLinkPublicOut(BaseModel):
    slug: str
    title: str
    description: Optional[str] = None
    owner_label: Optional[str] = None
    approval_required: bool = False
    approval_policy: str = "instant"
    assignment_mode: str = "single_host"
    booking_window_days: int = 14
    buffer_before_minutes: int = 0
    buffer_after_minutes: int = 0
    duration_minutes: int = 30
    availability_start_time: str = "09:00"
    availability_end_time: str = "18:00"
    expires_at: Optional[datetime] = None
    intake_questions: list[CalendarBookingQuestionOut] = Field(default_factory=list)
    slots: list[CalendarBookingSlotOut] = Field(default_factory=list)


class CalendarPublicBookingSubmitIn(BaseModel):
    guest_name: str = Field(min_length=1, max_length=120)
    guest_email: str = Field(min_length=3, max_length=255)
    starts_at: datetime
    title: Optional[str] = Field(default=None, max_length=160)
    note: Optional[str] = Field(default=None, max_length=4000)
    answers: dict[str, str] = Field(default_factory=dict)

    @field_validator("guest_name", "guest_email", "title", "note", mode="before")
    @classmethod
    def _trim_calendar_public_booking_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @field_validator("guest_email")
    @classmethod
    def _normalize_calendar_public_booking_email(cls, value: str) -> str:
        normalized = str(value or "").strip().lower()
        if "@" not in normalized:
            raise ValueError("guest_email must be a valid email")
        return normalized

    @field_validator("answers", mode="before")
    @classmethod
    def _normalize_calendar_public_booking_answers(cls, value: Any) -> dict[str, str]:
        if not isinstance(value, dict):
            return {}
        rows: dict[str, str] = {}
        for key, item in value.items():
            normalized_key = str(key or "").strip()
            normalized_value = str(item or "").strip()
            if not normalized_key:
                continue
            rows[normalized_key] = normalized_value
        return rows


class CalendarPublicBookingSubmitOut(BaseModel):
    event_id: UUID
    status: str = "confirmed"
    starts_at: datetime
    ends_at: datetime
    approval_required: bool = False
    approval_policy: str = "instant"


class CalendarSyncConnectionUpsertIn(BaseModel):
    provider: str = Field(default="google", max_length=32)
    access_scope: str = Field(default="read_write", max_length=32)
    account_email: Optional[str] = Field(default=None, max_length=255)
    account_label: Optional[str] = Field(default=None, max_length=160)
    default_container_id: Optional[UUID] = None
    selected_external_calendars: list[str] = Field(default_factory=list, max_length=16)

    @field_validator("provider", "access_scope", "account_email", "account_label", mode="before")
    @classmethod
    def _trim_calendar_sync_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @field_validator("provider")
    @classmethod
    def _normalize_calendar_sync_provider(cls, value: str) -> str:
        normalized = str(value or "google").strip().lower()
        if normalized not in {"google", "outlook"}:
            raise ValueError("provider must be google or outlook")
        return normalized

    @field_validator("access_scope")
    @classmethod
    def _normalize_calendar_sync_scope(cls, value: str) -> str:
        normalized = str(value or "read_write").strip().lower()
        if normalized not in {"read", "read_write"}:
            raise ValueError("access_scope must be read or read_write")
        return normalized

    @field_validator("account_email")
    @classmethod
    def _normalize_calendar_sync_email(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = str(value).strip().lower()
        if normalized and "@" not in normalized:
            raise ValueError("account_email must be a valid email")
        return normalized or None

    @field_validator("selected_external_calendars", mode="before")
    @classmethod
    def _normalize_calendar_sync_selected_calendars(cls, value: Any) -> list[str]:
        if not isinstance(value, (list, tuple)):
            return []
        rows: list[str] = []
        seen: set[str] = set()
        for item in value:
            normalized = str(item or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            rows.append(normalized)
        return rows[:16]


class CalendarSyncConnectionOut(BaseModel):
    id: UUID
    provider: str
    access_scope: str = "read"
    account_email: Optional[str] = None
    account_label: Optional[str] = None
    default_container_id: Optional[UUID] = None
    default_container_label: Optional[str] = None
    selected_external_calendars: list[str] = Field(default_factory=list)
    sync_state: str = "disconnected"
    last_synced_at: Optional[datetime] = None
    last_sync_error: Optional[str] = None


class CalendarTemplateOut(BaseModel):
    code: str
    label: str
    description: str
    duration_minutes: int = 30
    reminder_minutes: list[int] = Field(default_factory=list)
    conferencing_provider: Optional[str] = None
    visibility: str = "private"
    recurrence_preset: str = "none"
    title_template: Optional[str] = None


class CalendarWorkspaceOut(BaseModel):
    audience: CALENDAR_AUDIENCE_LITERAL
    view: CALENDAR_VIEW_LITERAL
    date: str
    anchor_date: str
    selected_date: str
    range_label: str
    role_label: str
    scope_label: str
    capabilities: CalendarCapabilityOut
    mini_month_days: list[CalendarMiniMonthDayOut] = Field(default_factory=list)
    containers: list[CalendarContainerOut] = Field(default_factory=list)
    selected_container_id: Optional[UUID] = None
    booking_links: list[CalendarBookingLinkOut] = Field(default_factory=list)
    templates: list[CalendarTemplateOut] = Field(default_factory=list)
    sync_connections: list[CalendarSyncConnectionOut] = Field(default_factory=list)
    attendee_options: list[CalendarAttendeeOptionOut] = Field(default_factory=list)
    resources: list[CalendarResourceOut] = Field(default_factory=list)
    events: list[CalendarEventOut] = Field(default_factory=list)
    selected_event: Optional[CalendarEventOut] = None


class CalendarAttendeeIn(BaseModel):
    user_id: Optional[UUID] = None
    employee_id: Optional[UUID] = None
    email: Optional[str] = None
    display_name: Optional[str] = None
    is_required: bool = True


class CalendarReminderIn(BaseModel):
    channel: str = Field(default="in_app", max_length=32)
    minutes_before: Optional[int] = Field(default=None, ge=0, le=10080)
    absolute_trigger_at: Optional[datetime] = None


class CalendarEventUpsertIn(BaseModel):
    container_id: UUID
    title: str = Field(min_length=1, max_length=200)
    starts_at: datetime
    ends_at: datetime
    timezone: str = Field(default="Asia/Seoul", max_length=64)
    is_all_day: bool = False
    recurrence_rule: Optional[str] = Field(default=None, max_length=255)
    availability_status: str = Field(default="busy", max_length=32)
    visibility: str = Field(default="private", max_length=32)
    location: Optional[str] = Field(default=None, max_length=255)
    conferencing_provider: Optional[str] = Field(default=None, max_length=64)
    conferencing_url: Optional[str] = Field(default=None, max_length=500)
    description: Optional[str] = Field(default=None, max_length=4000)
    resource_id: Optional[UUID] = None
    attendees: list[CalendarAttendeeIn] = Field(default_factory=list)
    reminders: list[CalendarReminderIn] = Field(default_factory=list)
    shared_note: Optional[str] = Field(default=None, max_length=8000)
    private_memo: Optional[str] = Field(default=None, max_length=8000)
    action_items: list[str] = Field(default_factory=list, max_length=20)
    custom_fields: list[CalendarCustomFieldRowIn] = Field(default_factory=list, max_length=12)


class NoticeDeleteOut(BaseModel):
    deleted: bool = True
    id: UUID


class NoticePollVoteIn(BaseModel):
    option_ids: list[str] = Field(default_factory=list, min_length=1, max_length=10)

    @field_validator("option_ids", mode="before")
    @classmethod
    def _normalize_notice_poll_vote_ids(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, (list, tuple)):
            return []
        rows: list[str] = []
        seen: set[str] = set()
        for item in value:
            normalized = str(item or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            rows.append(normalized)
        return rows[:10]


class NoticeAttachmentOut(BaseModel):
    id: UUID
    file_name: str
    mime_type: str
    image_src: str


class FinanceSubmissionStatusOut(BaseModel):
    site_code: str
    month: str
    state: str
    current_revision: Optional[str] = None
    review_download_ready: bool = False
    review_download_revision: Optional[str] = None
    review_downloaded_at: Optional[datetime] = None
    review_downloaded_by: Optional[str] = None
    review_download_filename: Optional[str] = None
    final_download_enabled: bool = False
    final_upload_stale: bool = False
    active_final_revision: Optional[str] = None
    active_final_source_revision: Optional[str] = None
    active_final_filename: Optional[str] = None
    final_uploaded_at: Optional[datetime] = None
    final_uploaded_by: Optional[str] = None
    last_event: Optional[str] = None
    blocked_reasons: list[str] = Field(default_factory=list)


class FinanceSubmissionOverviewSiteOut(BaseModel):
    site_code: str
    site_name: str
    month: str
    submission_status: str = "not_started"
    submission_status_label: str = "제출 전"
    review_status: str = "pending"
    review_status_label: str = "미다운로드"
    final_status: str = "not_uploaded"
    final_status_label: str = "미업로드"
    last_updated_at: Optional[datetime] = None
    blocked_reason: Optional[str] = None


class FinanceSubmissionOverviewOut(BaseModel):
    tenant_code: str
    month: str
    tenant_name: Optional[str] = None
    actor_role: Optional[str] = None
    scope_label: Optional[str] = None
    tenant_wide: bool = False
    total_site_count: int = 0
    submitted_site_count: int = 0
    review_ready_site_count: int = 0
    final_uploaded_site_count: int = 0
    generated_at: Optional[datetime] = None
    sites: list[FinanceSubmissionOverviewSiteOut] = Field(default_factory=list)


class FinanceDownloadWorkspaceSiteOut(BaseModel):
    site_code: str
    site_name: str
    uploaded: bool = False
    status: str = "not_uploaded"
    status_label: str = "미업로드"
    final_uploaded_at: Optional[datetime] = None
    final_uploaded_by: Optional[str] = None
    active_final_filename: Optional[str] = None
    final_upload_count: int = 0
    download_enabled: bool = False
    download_blocked_reason: Optional[str] = None
    note: Optional[str] = None


class FinanceDownloadWorkspaceOut(BaseModel):
    tenant_code: str
    month: str
    tenant_name: Optional[str] = None
    actor_role: Optional[str] = None
    total_site_count: int = 0
    uploaded_site_count: int = 0
    downloadable_site_count: int = 0
    generated_at: Optional[datetime] = None
    sites: list[FinanceDownloadWorkspaceSiteOut] = Field(default_factory=list)


class FinanceSubmissionPreviewOut(BaseModel):
    finance_batch_id: UUID
    import_batch_id: UUID
    total_rows: int
    valid_rows: int
    invalid_rows: int
    invalid_samples: list[str] = Field(default_factory=list)
    preview_rows: list[ImportPreviewRowOut] = Field(default_factory=list)
    error_counts: dict[str, int] = Field(default_factory=dict)
    diff_counts: dict[str, int] = Field(default_factory=dict)
    blocked_reasons: list[str] = Field(default_factory=list)
    metadata: Optional[ImportPreviewMetadataOut] = None
    can_apply: bool = False


class SiteShiftPolicyUpdate(BaseModel):
    tenant_code: Optional[str] = Field(default=None, max_length=64)
    site_code: str = Field(min_length=1, max_length=64)
    weekday_headcount: int = Field(ge=0, le=300)
    weekend_headcount: int = Field(ge=0, le=300)

    @field_validator("tenant_code", "site_code")
    @classmethod
    def _trimmed_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return value.strip()


class SiteShiftPolicyOut(BaseModel):
    tenant_code: str
    site_code: str
    weekday_headcount: int
    weekend_headcount: int
    updated_at: datetime


class AppleDaytimeShiftOut(BaseModel):
    tenant_code: str
    site_code: str
    work_date: date
    is_weekend: bool
    total_headcount: int
    supervisor_count: int
    guard_count: int
    supervisor_time: str
    guard_time: str
    supervisor_hours: float
    guard_hours: float


class AppleOvertimeCreate(BaseModel):
    tenant_code: Optional[str] = Field(default=None, max_length=64)
    site_code: str = Field(min_length=1, max_length=64)
    work_date: date
    reason: str = Field(min_length=1, max_length=120)
    leader_user_id: Optional[UUID] = None

    @field_validator("tenant_code", "site_code", "reason")
    @classmethod
    def _trimmed_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return value.strip()


class AppleOvertimeOut(BaseModel):
    id: UUID
    tenant_code: str
    site_code: str
    work_date: date
    leader_user_id: UUID
    leader_username: Optional[str] = None
    leader_full_name: Optional[str] = None
    reason: str
    hours: float
    source: str
    created_at: datetime


class LateShiftCreate(BaseModel):
    tenant_code: Optional[str] = Field(default=None, max_length=64)
    site_code: str = Field(min_length=1, max_length=64)
    work_date: date
    employee_code: str = Field(min_length=1, max_length=64)
    minutes_late: int = Field(ge=1, le=600)
    note: Optional[str] = Field(default=None, max_length=300)

    @field_validator("tenant_code", "site_code", "employee_code", "note")
    @classmethod
    def _trimmed_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return value.strip()


class LateShiftOut(BaseModel):
    id: UUID
    tenant_code: str
    site_code: str
    work_date: date
    employee_id: UUID
    employee_code: str
    employee_name: Optional[str] = None
    minutes_late: int
    note: Optional[str] = None
    created_at: datetime


class DailyEventCreate(BaseModel):
    tenant_code: Optional[str] = Field(default=None, max_length=64)
    site_code: str = Field(min_length=1, max_length=64)
    work_date: date
    type: str = Field(min_length=1, max_length=32)
    description: str = Field(min_length=1, max_length=300)

    @field_validator("tenant_code", "site_code", "description")
    @classmethod
    def _trimmed_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return value.strip()

    @field_validator("type")
    @classmethod
    def _normalize_type(cls, value: str) -> str:
        normalized = str(value or "").strip().upper()
        aliases = {
            "EVENT": "EVENT",
            "ADDITIONAL": "ADDITIONAL",
            "ADDITIONAL_WORK": "ADDITIONAL",
        }
        resolved = aliases.get(normalized, normalized)
        if resolved not in {"EVENT", "ADDITIONAL"}:
            raise ValueError("type must be EVENT/ADDITIONAL")
        return resolved


class DailyEventOut(BaseModel):
    id: UUID
    tenant_code: str
    site_code: str
    work_date: date
    type: str
    description: str
    created_at: datetime


class SupportAssignmentCreate(BaseModel):
    tenant_code: Optional[str] = Field(default=None, max_length=64)
    site_code: str = Field(min_length=1, max_length=64)
    work_date: date
    support_period: str = Field(default="day", min_length=1, max_length=16)
    slot_index: Optional[int] = Field(default=None, ge=1, le=32)
    worker_type: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=120)
    affiliation: Optional[str] = Field(default=None, max_length=120)
    employee_code: Optional[str] = Field(default=None, max_length=64)
    source: str = Field(default="MANUAL", max_length=32)

    @field_validator("tenant_code", "site_code", "name", "affiliation", "employee_code", "source")
    @classmethod
    def _trimmed_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return value.strip()

    @field_validator("worker_type")
    @classmethod
    def _normalize_worker_type(cls, value: str) -> str:
        normalized = str(value or "").strip().upper()
        aliases = {
            "F": "F",
            "FORWARD": "F",
            "BK": "BK",
            "BACK": "BK",
            "INTERNAL": "INTERNAL",
            "SELF": "INTERNAL",
            "자체": "INTERNAL",
            "UNAVAILABLE": "UNAVAILABLE",
            "NOT_AVAILABLE": "UNAVAILABLE",
            "지원불가": "UNAVAILABLE",
        }
        resolved = aliases.get(normalized, normalized)
        if resolved not in {"F", "BK", "INTERNAL", "UNAVAILABLE"}:
            raise ValueError("worker_type must be F/BK/INTERNAL/UNAVAILABLE")
        return resolved

    @field_validator("support_period")
    @classmethod
    def _normalize_support_period(cls, value: str) -> str:
        normalized = str(value or "").strip().lower()
        if normalized not in {"day", "night"}:
            raise ValueError("support_period must be day/night")
        return normalized


class SupportAssignmentOut(BaseModel):
    id: UUID
    tenant_code: str
    site_code: str
    work_date: date
    support_period: str = "day"
    slot_index: int = 1
    worker_type: str
    employee_id: Optional[UUID] = None
    employee_code: Optional[str] = None
    employee_name: Optional[str] = None
    name: str
    affiliation: Optional[str] = None
    source: str
    source_ticket_id: Optional[int] = None
    source_event_uid: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class SupportStatusAssignmentOut(BaseModel):
    id: UUID
    slot_index: int = 1
    worker_type: str
    employee_id: Optional[UUID] = None
    employee_code: Optional[str] = None
    employee_name: Optional[str] = None
    worker_name: str
    display_value: str
    affiliation: Optional[str] = None
    source: str
    source_ticket_id: Optional[int] = None
    source_event_uid: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class SupportStatusWorkspaceRowOut(BaseModel):
    row_key: str
    tenant_code: str
    site_code: str
    site_name: Optional[str] = None
    work_date: date
    shift_kind: str
    request_count: int = 0
    assigned_count: int = 0
    filled_count: int = 0
    request_status: Optional[str] = None
    work_purpose: Optional[str] = None
    source_workflow: Optional[str] = None
    source_batch_id: Optional[UUID] = None
    source_revision: Optional[str] = None
    source_labels: list[str] = Field(default_factory=list)
    worker_display_values: list[str] = Field(default_factory=list)
    assignments: list[SupportStatusAssignmentOut] = Field(default_factory=list)
    has_request_ticket: bool = False
    updated_at: Optional[datetime] = None


class SupportStatusWorkspaceOut(BaseModel):
    tenant_code: str
    month: str
    total_count: int = 0
    day_count: int = 0
    night_count: int = 0
    rows: list[SupportStatusWorkspaceRowOut] = Field(default_factory=list)
    generated_at: datetime


class DutyLogRowOut(BaseModel):
    work_date: date
    mark: str
    shift_type: Optional[str] = None
    leave_type: Optional[str] = None
    source: Optional[str] = None


class DutyLogOut(BaseModel):
    tenant_code: str
    employee_code: str
    month: str
    rows: list[DutyLogRowOut] = Field(default_factory=list)


class SupportSheetEntryIn(BaseModel):
    text: str = Field(min_length=1, max_length=160)

    @field_validator("text")
    @classmethod
    def _trim_text(cls, value: str) -> str:
        return value.strip()


class SupportSheetWebhookIn(BaseModel):
    tenant_code: str = Field(min_length=1, max_length=64)
    site_code: str = Field(min_length=1, max_length=64)
    work_date: date
    entries: list[SupportSheetEntryIn] = Field(default_factory=list)
    source: str = Field(default="SHEET", max_length=32)

    @field_validator("tenant_code", "site_code", "source")
    @classmethod
    def _trimmed_text(cls, value: str) -> str:
        return value.strip()


class SocTicketEnvelopeIn(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: Optional[int] = Field(default=None, validation_alias=AliasChoices("id", "ticketId"))
    template_type: Optional[str] = Field(
        default=None,
        max_length=120,
        validation_alias=AliasChoices("template_type", "templateType"),
    )
    tenant_id: Optional[str] = Field(
        default=None,
        max_length=120,
        validation_alias=AliasChoices("tenant_id", "tenantId"),
    )
    site_id: Optional[str] = Field(
        default=None,
        max_length=120,
        validation_alias=AliasChoices("site_id", "siteId"),
    )
    status: Optional[str] = Field(default=None, max_length=64)
    decision_at: Optional[datetime] = Field(
        default=None,
        validation_alias=AliasChoices("decision_at", "decisionAt", "approvedAt"),
    )
    approver_user_id: Optional[int] = Field(
        default=None,
        validation_alias=AliasChoices("approver_user_id", "approverUserId", "approvedBy"),
    )
    reporter_user_id: Optional[int] = Field(
        default=None,
        validation_alias=AliasChoices("reporter_user_id", "reporterUserId", "requesterUserId"),
    )
    reason: Optional[str] = Field(default=None, max_length=300)
    memo: Optional[str] = Field(default=None, max_length=300)

    @field_validator("template_type", "tenant_id", "site_id", "status", "reason", "memo")
    @classmethod
    def _trim_ticket_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return value.strip()


class SocEventEnvelopeIn(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    event_id: str = Field(
        min_length=1,
        max_length=200,
        validation_alias=AliasChoices("event_id", "eventId"),
    )
    event_type: str = Field(
        min_length=1,
        max_length=120,
        validation_alias=AliasChoices("event_type", "eventType"),
    )
    source: Optional[str] = Field(default=None, max_length=64)
    occurred_at: Optional[datetime] = Field(
        default=None,
        validation_alias=AliasChoices("occurred_at", "occurredAt"),
    )
    ticket: SocTicketEnvelopeIn
    template_fields: dict[str, object] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("template_fields", "templateFields"),
    )

    @field_validator("event_id", "event_type", "source")
    @classmethod
    def _trim_envelope_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return value.strip()


class SocEventIn(BaseModel):
    event_uid: str = Field(min_length=1, max_length=120)
    event_type: str = Field(min_length=1, max_length=120)
    tenant_code: str = Field(min_length=1, max_length=64)
    employee_code: str = Field(min_length=1, max_length=64)
    site_code: Optional[str] = Field(default=None, max_length=64)
    company_code: Optional[str] = Field(default=None, max_length=64)
    work_date: Optional[date] = None
    occurred_at: Optional[datetime] = None
    leave_type: Optional[str] = Field(default=None, max_length=32)
    approved_minutes: Optional[int] = Field(default=None, ge=0, le=1440)
    reason: Optional[str] = Field(default=None, max_length=300)
    metadata: dict[str, object] = Field(default_factory=dict)
    payload: dict[str, object] = Field(default_factory=dict)

    @field_validator(
        "event_uid",
        "event_type",
        "tenant_code",
        "employee_code",
        "site_code",
        "company_code",
        "leave_type",
        "reason",
    )
    @classmethod
    def _trimmed_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return value.strip()


class SocEventIngestOut(BaseModel):
    id: UUID
    event_uid: str
    event_type: str
    tenant_code: Optional[str] = None
    status: str
    duplicate: bool = False
    received_at: datetime
    processed_at: Optional[datetime] = None
    error_text: Optional[str] = None
    applied_changes: dict[str, object] = Field(default_factory=dict)


class SocWorkTemplateQueryIn(BaseModel):
    event_id: UUID
    tenant_code: str = Field(min_length=1, max_length=64)
    site_code: str = Field(min_length=1, max_length=64)
    duty_type: str = Field(min_length=1, max_length=32)

    @field_validator("tenant_code", "site_code", "duty_type")
    @classmethod
    def _trim_soc_template_query_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return str(value).strip()


class SocWorkTemplateOut(BaseModel):
    id: UUID
    tenant_id: UUID
    template_name: str
    duty_type: str
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    site_id: Optional[UUID] = None
    site_code: Optional[str] = None
    site_name: Optional[str] = None
    is_default: bool = False
    is_active: bool = True
    option_label: str


class SocEmployeeBackfillIn(BaseModel):
    event_id: UUID
    tenant_code: str = Field(min_length=1, max_length=64)
    site_code: Optional[str] = Field(default=None, max_length=64)
    include_inactive: bool = False

    @field_validator("tenant_code", "site_code")
    @classmethod
    def _trim_soc_employee_backfill_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None


class GoogleSheetProfileCreate(BaseModel):
    tenant_code: Optional[str] = Field(default=None, max_length=64)
    profile_name: str = Field(min_length=1, max_length=120)
    profile_scope: str = Field(default="PAYROLL_LEAVE_OVERTIME", max_length=64)
    profile_type: str = Field(default="KEY_ROW", max_length=32)
    site_codes: list[str] = Field(default_factory=list)
    spreadsheet_id: Optional[str] = Field(default=None, max_length=200)
    worksheet_schedule: Optional[str] = Field(default=None, max_length=120)
    worksheet_overtime: Optional[str] = Field(default=None, max_length=120)
    worksheet_overnight: Optional[str] = Field(default=None, max_length=120)
    webhook_url: Optional[str] = Field(default=None, max_length=500)
    auth_mode: str = Field(default="webhook", max_length=32)
    credential_ref: Optional[str] = Field(default=None, max_length=200)
    mapping_json: dict[str, object] = Field(default_factory=dict)
    options_json: dict[str, object] = Field(default_factory=dict)
    is_active: bool = False

    @field_validator(
        "tenant_code",
        "profile_name",
        "profile_scope",
        "profile_type",
        "spreadsheet_id",
        "worksheet_schedule",
        "worksheet_overtime",
        "worksheet_overnight",
        "webhook_url",
        "auth_mode",
        "credential_ref",
    )
    @classmethod
    def _trimmed_profile_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return value.strip()

    @field_validator("profile_scope")
    @classmethod
    def _profile_scope(cls, value: str) -> str:
        normalized = str(value or "").strip().upper()
        aliases = {
            "APPLE": "APPLE_OVERNIGHT",
            "OVERNIGHT": "APPLE_OVERNIGHT",
            "APPLE_OVERNIGHT": "APPLE_OVERNIGHT",
            "APPLE_DAYTIME": "APPLE_DAYTIME",
            "DAYTIME": "APPLE_DAYTIME",
            "APPLE_DAYTIME_P1": "APPLE_DAYTIME",
            "APPLE_OT": "APPLE_OT",
            "OT": "APPLE_OT",
            "APPLE_TOTAL_LATE": "APPLE_TOTAL_LATE",
            "TOTAL_LATE": "APPLE_TOTAL_LATE",
            "DUTY": "DUTY_LOG",
            "DUTY_LOG": "DUTY_LOG",
            "SUPPORT": "SUPPORT_ASSIGNMENT",
            "SUPPORT_ASSIGNMENT": "SUPPORT_ASSIGNMENT",
            "SHEET_TO_DB_SUPPORT": "SUPPORT_ASSIGNMENT",
            "PAYROLL": "PAYROLL_LEAVE_OVERTIME",
            "PAYROLL_LEAVE_OT": "PAYROLL_LEAVE_OVERTIME",
            "PAYROLL_LEAVE_OVERTIME": "PAYROLL_LEAVE_OVERTIME",
        }
        resolved = aliases.get(normalized, normalized)
        if resolved not in {
            "APPLE_OVERNIGHT",
            "PAYROLL_LEAVE_OVERTIME",
            "APPLE_DAYTIME",
            "APPLE_OT",
            "APPLE_TOTAL_LATE",
            "DUTY_LOG",
            "SUPPORT_ASSIGNMENT",
        }:
            raise ValueError(
                "profile_scope must be APPLE_OVERNIGHT/PAYROLL_LEAVE_OVERTIME/APPLE_DAYTIME/APPLE_OT/APPLE_TOTAL_LATE/DUTY_LOG/SUPPORT_ASSIGNMENT"
            )
        return resolved

    @field_validator("profile_type")
    @classmethod
    def _profile_type(cls, value: str) -> str:
        normalized = str(value or "").strip().upper()
        aliases = {
            "KEY_ROW": "KEY_ROW",
            "KEYROW": "KEY_ROW",
            "NAMED_RANGE": "NAMED_RANGE",
            "NAMEDRANGE": "NAMED_RANGE",
        }
        resolved = aliases.get(normalized, normalized)
        if resolved not in {"KEY_ROW", "NAMED_RANGE"}:
            raise ValueError("profile_type must be KEY_ROW/NAMED_RANGE")
        return resolved

    @field_validator("site_codes", mode="before")
    @classmethod
    def _site_codes(cls, value):
        if value in (None, ""):
            return []
        if isinstance(value, str):
            candidates = [item.strip() for item in value.split(",")]
        elif isinstance(value, (list, tuple, set)):
            candidates = [str(item).strip() for item in value]
        else:
            raise ValueError("site_codes must be an array or comma-separated string")

        normalized: list[str] = []
        seen: set[str] = set()
        for item in candidates:
            if not item:
                continue
            code = item.upper()
            if code in seen:
                continue
            seen.add(code)
            normalized.append(code)
        return normalized


class GoogleSheetProfileUpdate(BaseModel):
    profile_name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    profile_scope: Optional[str] = Field(default=None, max_length=64)
    profile_type: Optional[str] = Field(default=None, max_length=32)
    site_codes: Optional[list[str]] = None
    spreadsheet_id: Optional[str] = Field(default=None, max_length=200)
    worksheet_schedule: Optional[str] = Field(default=None, max_length=120)
    worksheet_overtime: Optional[str] = Field(default=None, max_length=120)
    worksheet_overnight: Optional[str] = Field(default=None, max_length=120)
    webhook_url: Optional[str] = Field(default=None, max_length=500)
    auth_mode: Optional[str] = Field(default=None, max_length=32)
    credential_ref: Optional[str] = Field(default=None, max_length=200)
    mapping_json: Optional[dict[str, object]] = None
    options_json: Optional[dict[str, object]] = None
    is_active: Optional[bool] = None

    @field_validator(
        "profile_name",
        "profile_scope",
        "profile_type",
        "spreadsheet_id",
        "worksheet_schedule",
        "worksheet_overtime",
        "worksheet_overnight",
        "webhook_url",
        "auth_mode",
        "credential_ref",
    )
    @classmethod
    def _trimmed_profile_update_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return value.strip()

    @field_validator("profile_scope")
    @classmethod
    def _profile_scope(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = str(value or "").strip().upper()
        aliases = {
            "APPLE": "APPLE_OVERNIGHT",
            "OVERNIGHT": "APPLE_OVERNIGHT",
            "APPLE_OVERNIGHT": "APPLE_OVERNIGHT",
            "APPLE_DAYTIME": "APPLE_DAYTIME",
            "DAYTIME": "APPLE_DAYTIME",
            "APPLE_DAYTIME_P1": "APPLE_DAYTIME",
            "APPLE_OT": "APPLE_OT",
            "OT": "APPLE_OT",
            "APPLE_TOTAL_LATE": "APPLE_TOTAL_LATE",
            "TOTAL_LATE": "APPLE_TOTAL_LATE",
            "DUTY": "DUTY_LOG",
            "DUTY_LOG": "DUTY_LOG",
            "SUPPORT": "SUPPORT_ASSIGNMENT",
            "SUPPORT_ASSIGNMENT": "SUPPORT_ASSIGNMENT",
            "SHEET_TO_DB_SUPPORT": "SUPPORT_ASSIGNMENT",
            "PAYROLL": "PAYROLL_LEAVE_OVERTIME",
            "PAYROLL_LEAVE_OT": "PAYROLL_LEAVE_OVERTIME",
            "PAYROLL_LEAVE_OVERTIME": "PAYROLL_LEAVE_OVERTIME",
        }
        resolved = aliases.get(normalized, normalized)
        if resolved not in {
            "APPLE_OVERNIGHT",
            "PAYROLL_LEAVE_OVERTIME",
            "APPLE_DAYTIME",
            "APPLE_OT",
            "APPLE_TOTAL_LATE",
            "DUTY_LOG",
            "SUPPORT_ASSIGNMENT",
        }:
            raise ValueError(
                "profile_scope must be APPLE_OVERNIGHT/PAYROLL_LEAVE_OVERTIME/APPLE_DAYTIME/APPLE_OT/APPLE_TOTAL_LATE/DUTY_LOG/SUPPORT_ASSIGNMENT"
            )
        return resolved

    @field_validator("profile_type")
    @classmethod
    def _profile_type(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = str(value or "").strip().upper()
        aliases = {
            "KEY_ROW": "KEY_ROW",
            "KEYROW": "KEY_ROW",
            "NAMED_RANGE": "NAMED_RANGE",
            "NAMEDRANGE": "NAMED_RANGE",
        }
        resolved = aliases.get(normalized, normalized)
        if resolved not in {"KEY_ROW", "NAMED_RANGE"}:
            raise ValueError("profile_type must be KEY_ROW/NAMED_RANGE")
        return resolved

    @field_validator("site_codes", mode="before")
    @classmethod
    def _site_codes(cls, value):
        if value in (None, ""):
            return []
        if isinstance(value, str):
            candidates = [item.strip() for item in value.split(",")]
        elif isinstance(value, (list, tuple, set)):
            candidates = [str(item).strip() for item in value]
        else:
            raise ValueError("site_codes must be an array or comma-separated string")

        normalized: list[str] = []
        seen: set[str] = set()
        for item in candidates:
            if not item:
                continue
            code = item.upper()
            if code in seen:
                continue
            seen.add(code)
            normalized.append(code)
        return normalized


class GoogleSheetProfileOut(BaseModel):
    id: UUID
    tenant_code: str
    profile_name: str
    profile_scope: str = "PAYROLL_LEAVE_OVERTIME"
    profile_type: str = "KEY_ROW"
    site_codes: list[str] = Field(default_factory=list)
    spreadsheet_id: Optional[str] = None
    worksheet_schedule: Optional[str] = None
    worksheet_overtime: Optional[str] = None
    worksheet_overnight: Optional[str] = None
    webhook_url: Optional[str] = None
    auth_mode: str
    credential_ref: Optional[str] = None
    mapping_json: dict[str, object] = Field(default_factory=dict)
    options_json: dict[str, object] = Field(default_factory=dict)
    is_active: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class GoogleSheetSyncRequest(BaseModel):
    start_date: Optional[date] = None
    end_date: Optional[date] = None


class GoogleSheetSyncOut(BaseModel):
    ok: bool
    sent: bool
    tenant_code: str
    profile_id: UUID
    row_counts: dict[str, int] = Field(default_factory=dict)
    payload_preview: dict[str, object] = Field(default_factory=dict)
    sync_message: str = ""


class GoogleSheetSyncLogOut(BaseModel):
    id: UUID
    tenant_code: str
    profile_id: Optional[UUID] = None
    profile_name: Optional[str] = None
    direction: str
    status: str
    error_message: Optional[str] = None
    created_at: datetime


class IntegrationFeatureFlagUpdate(BaseModel):
    tenant_code: Optional[str] = Field(default=None, max_length=64)
    flag_key: str = Field(min_length=1, max_length=120)
    enabled: bool

    @field_validator("tenant_code", "flag_key")
    @classmethod
    def _trim_flag_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return value.strip()


class IntegrationFeatureFlagOut(BaseModel):
    tenant_code: str
    flag_key: str
    enabled: bool
    updated_at: Optional[datetime] = None
