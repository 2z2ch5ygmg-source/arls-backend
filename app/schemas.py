from __future__ import annotations

from datetime import date, datetime
from typing import Optional
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
    latitude: float
    longitude: float
    radius_meters: float
    is_active: bool = True


class EmployeeCreate(BaseModel):
    tenant_id: Optional[UUID] = None
    site_id: Optional[UUID] = None
    company_code: Optional[str] = Field(default=None, min_length=1)
    site_code: Optional[str] = Field(default=None, min_length=1)
    # 직원 코드는 서버에서 <site_code>-NNN 형식으로 자동 생성한다.
    employee_code: Optional[str] = Field(default=None, min_length=1)
    full_name: str = Field(min_length=1)
    phone: Optional[str] = None
    birth_date: Optional[date] = None
    hire_date: Optional[date] = None
    guard_training_cert_no: Optional[str] = Field(default=None, max_length=120)
    note: Optional[str] = Field(default=None, max_length=1000)
    soc_login_id: Optional[str] = Field(default=None, max_length=120)
    soc_temp_password: Optional[str] = Field(default=None, max_length=120)
    soc_role: Optional[str] = Field(default=None, max_length=64)

    @field_validator(
        "company_code",
        "site_code",
        "employee_code",
        "full_name",
        "phone",
        "guard_training_cert_no",
        "note",
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

    @model_validator(mode="after")
    def _site_ref_optional(self) -> "EmployeeCreate":
        # 지점관리자는 서버 세션(site scope)으로 site/company를 강제 주입하므로
        # 스키마 단계에서 site/company 필수로 막지 않는다.
        # DEV의 상세 검증은 employees 라우터에서 처리한다.
        return self

class EmployeeOut(BaseModel):
    id: UUID
    employee_code: str
    sequence_no: Optional[int] = None
    full_name: str
    phone: Optional[str]
    site_code: str
    company_code: str
    user_id: Optional[UUID] = None
    user_role: Optional[str] = None
    birth_date: Optional[date] = None
    hire_date: Optional[date] = None
    guard_training_cert_no: Optional[str] = None
    note: Optional[str] = None
    soc_login_id: Optional[str] = None
    soc_role: Optional[str] = None


class EmployeeUpdate(BaseModel):
    full_name: str = Field(min_length=1)
    phone: Optional[str] = None
    birth_date: Optional[date] = None
    hire_date: Optional[date] = None
    guard_training_cert_no: Optional[str] = Field(default=None, max_length=120)
    note: Optional[str] = Field(default=None, max_length=1000)
    soc_login_id: Optional[str] = Field(default=None, max_length=120)
    soc_role: Optional[str] = Field(default=None, max_length=64)

    @field_validator("full_name", "phone", "guard_training_cert_no", "note", "soc_login_id", "soc_role")
    @classmethod
    def _trimmed(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None


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

    @field_validator("shift_type")
    @classmethod
    def _shift_type(cls, v: str) -> str:
        normalized = v.strip().lower()
        aliases = {"leave": "off"}
        normalized = aliases.get(normalized, normalized)

        if normalized not in {"day", "night", "off", "holiday"}:
            raise ValueError("shift_type invalid")
        return normalized


class ScheduleCloserUpdate(BaseModel):
    enabled: bool = True


class ScheduleLeaderCandidateOut(BaseModel):
    user_id: UUID
    username: str
    full_name: str
    employee_code: str
    duty_role: str
    is_recommended: bool = False


class ScheduleLeaderCandidatesOut(BaseModel):
    schedule_id: UUID
    site_code: str
    schedule_date: date
    current_leader_user_id: Optional[UUID] = None
    recommended_leader_user_id: Optional[UUID] = None
    candidates: list[ScheduleLeaderCandidateOut] = Field(default_factory=list)


class ImportPreviewRowOut(BaseModel):
    row_no: int
    tenant_code: str
    company_code: str
    site_code: str
    employee_code: str
    schedule_date: Optional[str] = None
    shift_type: str
    is_valid: bool
    validation_code: Optional[str] = None
    validation_error: Optional[str] = None


class ImportPreviewOut(BaseModel):
    batch_id: UUID
    total_rows: int
    valid_rows: int
    invalid_rows: int
    invalid_samples: list[str]
    preview_rows: list[ImportPreviewRowOut] = Field(default_factory=list)
    error_counts: dict[str, int] = Field(default_factory=dict)


class ImportApplyRowOut(BaseModel):
    row_no: int
    employee_code: str
    site_code: str
    schedule_date: Optional[str] = None
    shift_type: str
    status: str
    reason: str


class ImportApplyOut(BaseModel):
    batch_id: UUID
    applied: int
    skipped: int
    applied_rows: list[ImportApplyRowOut] = Field(default_factory=list)
    skipped_rows: list[ImportApplyRowOut] = Field(default_factory=list)


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
    worker_type: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=120)
    employee_code: Optional[str] = Field(default=None, max_length=64)
    source: str = Field(default="MANUAL", max_length=32)

    @field_validator("tenant_code", "site_code", "name", "employee_code", "source")
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
        }
        resolved = aliases.get(normalized, normalized)
        if resolved not in {"F", "BK", "INTERNAL"}:
            raise ValueError("worker_type must be F/BK/INTERNAL")
        return resolved


class SupportAssignmentOut(BaseModel):
    id: UUID
    tenant_code: str
    site_code: str
    work_date: date
    worker_type: str
    employee_id: Optional[UUID] = None
    employee_code: Optional[str] = None
    employee_name: Optional[str] = None
    name: str
    source: str
    created_at: datetime


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
