# ARLS Employee Rename Sync Contract

## Scope

This contract defines the outbound employee-master sync payload ARLS emits to downstream consumers when an employee record is created, updated, or deleted.

The primary purpose of this patch is to ensure a name correction is emitted as an update against a stable employee identity.

## Rename Contract

When an ARLS employee name changes:

- canonical employee identity must remain unchanged
- outbound payload must use `event_type=EMPLOYEE_UPDATED`
- outbound payload must use `change_type=UPDATE`
- downstream consumers must treat the event as an update/upsert on the same employee identity
- downstream consumers must not infer a new employee entity from `new_display_name`

## Required Fields For Rename / Update

Top-level:

- `event_type`: `EMPLOYEE_UPDATED`
- `change_type`: `UPDATE`
- `sync_mode`: `UPSERT`
- `employee_id`: canonical ARLS employee id
- `tenant_id`: canonical tenant id when available
- `tenant_code`
- `site_id` when available
- `site_code`
- `linked_user_id` when available
- `old_display_name`
- `new_display_name`

Tenant scope:

- `tenant.tenant_id`
- `tenant.tenant_code`
- `tenant.tenant_name`

Site scope:

- `site.site_id`
- `site.site_code`
- `site.site_name`

Linked account scope:

- `linked_user.user_id`
- `linked_user.username`
- `linked_user.soc_login_id`
- `linked_user.user_role`
- `linked_user.soc_role`

Canonical employee identity:

- `identity.employee_id`
- `identity.employee_uuid`
- `identity.employee_code`
- `identity.tenant_id`
- `identity.tenant_code`
- `identity.site_id`
- `identity.site_code`
- `identity.linked_user_id`
- `identity.identity_key`

Employee payload:

- `employee.employee_id`
- `employee.employee_uuid`
- `employee.employee_code`
- `employee.identity_key`
- `employee.name`
- `employee.old_display_name`
- `employee.new_display_name`

## Consumer Rules

Downstream consumers such as Sentrix must:

- key employee upsert logic by canonical employee identity
- prefer `employee_id` / `identity.employee_id` over display name
- use `change_type=UPDATE` to distinguish rename from create
- use `old_display_name` and `new_display_name` only for reconciliation or UI migration, not identity matching

Downstream consumers must not:

- key identity by display name alone
- create a new logical employee profile solely because the display name changed
- interpret `EMPLOYEE_UPDATED` + `change_type=UPDATE` as `CREATE`

## Acceptance Mapping

- ARLS emits rename/update using stable employee identity: satisfied by `employee_id` and `identity.*`
- downstream systems can distinguish rename from new profile creation: satisfied by `event_type`, `change_type`, `sync_mode`, and old/new display names
- name correction no longer behaves like profile duplication: enabled by canonical identity contract and update semantics
