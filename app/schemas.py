from __future__ import annotations

from datetime import date, datetime
import re
from typing import Literal, Optional
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
    must_change_password: bool = Field(
        default=False,
        validation_alias=AliasChoices("must_change_password", "mustChangePassword"),
    )
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
    birth_date: Optional[date] = Field(default=None, validation_alias=AliasChoices("birth_date", "birthdate"))
    address: Optional[str] = Field(default=None, max_length=255)
    hire_date: Optional[date] = None
    leave_date: Optional[date] = Field(default=None, validation_alias=AliasChoices("leave_date", "leaveDate"))
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
        "address",
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
    site_code: str
    site_name: Optional[str] = None
    company_code: str
    user_id: Optional[UUID] = None
    user_role: Optional[str] = None
    birth_date: Optional[date] = None
    address: Optional[str] = None
    hire_date: Optional[date] = None
    leave_date: Optional[date] = None
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
    birth_date: Optional[date] = Field(default=None, validation_alias=AliasChoices("birth_date", "birthdate"))
    address: Optional[str] = Field(default=None, max_length=255)
    hire_date: Optional[date] = None
    leave_date: Optional[date] = Field(default=None, validation_alias=AliasChoices("leave_date", "leaveDate"))
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

    @field_validator("resident_no", mode="before")
    @classmethod
    def _normalize_resident_no(cls, value: Optional[str]) -> Optional[str]:
        return _normalize_resident_no_value(value)


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
    auto_checkout: Optional[bool] = None
    site_id: Optional[UUID] = None
    site_code: Optional[str] = None
    site_name: Optional[str] = None
    employee_id: Optional[UUID] = None
    employee_name: Optional[str] = None


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
    download_ready: bool = False
    source_state: str = "source_missing"
    source_revision: Optional[str] = None
    latest_hq_revision: Optional[str] = None
    latest_status: str = "source_missing"


class SupportRosterHqWorkspaceOut(BaseModel):
    tenant_code: str
    month: str
    default_scope: str = "all"
    workbook_family: str
    template_version: str
    latest_status: str = "latest"
    total_site_count: int = 0
    ready_site_count: int = 0
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
    selected_site_code: Optional[str] = None
    selected_site_name: Optional[str] = None


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
    valid_filled_count: int = 0
    target_status: Optional[str] = None
    status: str = "pending"
    reason: Optional[str] = None
    issue_code: Optional[str] = None


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
    matched_ticket: bool = False
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
    issue_count: int = 0
    summary: dict[str, int] = Field(default_factory=dict)
    issues: list[SupportRosterHqReviewIssueOut] = Field(default_factory=list)
    scope_summaries: list[SupportRosterHqScopeSummaryOut] = Field(default_factory=list)
    review_rows: list[SupportRosterHqReviewRowOut] = Field(default_factory=list)
    next_step_message: Optional[str] = None


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


class SupportRosterHqApplyOut(BaseModel):
    batch_id: UUID
    applied: bool = False
    blocked: bool = False
    blocked_reasons: list[str] = Field(default_factory=list)
    issue_count: int = 0
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
