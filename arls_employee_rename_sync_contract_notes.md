# ARLS Employee Rename Sync Contract Notes

## Problem

- ARLS employee master rename was being emitted with a weak downstream identity contract.
- The outbound payload contained `employee_uuid` and `employee_code`, but did not explicitly mark a rename as a canonical `UPDATE`.
- The payload also omitted the previous display name and linked account identity.
- A downstream consumer such as Sentrix could therefore treat a corrected name as a new logical profile when its own matching logic was name-biased.

Real bug reproduced from production:

- ARLS employee renamed from `최미가` to `최미강`
- Sentrix displayed both profiles
- This indicates rename/update was not sufficiently distinguishable from create/upsert on the consumer side

## Patch Summary

The ARLS employee sync contract was hardened in the outbound employee update path.

### Outbound payload now includes

- stable canonical employee identity via `employee_id` and `identity.employee_id`
- tenant identity: `tenant.tenant_id`, `tenant.tenant_code`, `tenant.tenant_name`
- site identity: `site.site_id`, `site.site_code`, `site.site_name`
- linked account identity when available: `linked_user.user_id`, `linked_user.username`, `linked_user.soc_login_id`
- rename metadata: `old_display_name`, `new_display_name`
- explicit mutation semantics:
  - `event_type=EMPLOYEE_UPDATED`
  - `change_type=UPDATE`
  - `sync_mode=UPSERT`

### Identity rules

- downstream sync must not key by display name
- canonical identity key is stable employee identity, not mutable profile text
- payload now exposes `identity.identity_key` derived from stable tenant identity + canonical employee id

## Additional behavior change

- ARLS now updates linked `arls_users.full_name` when employee master name changes
- this keeps account metadata aligned with employee canonical name

## Result

- employee rename remains an update to the same logical employee entity
- downstream systems can detect a name correction instead of inferring a new employee create
- Sentrix-style profile duplication caused by rename drift is now contractually preventable
