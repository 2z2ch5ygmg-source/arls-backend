# ARLS Mapping Profile Map

## Ownership Summary

- Work templates and mapping profiles are both owned by ARLS.
- Backend currently exposes one active mapping profile per tenant, not a true selectable profile collection.
- Frontend presents a selector UI, but selection is effectively local-only because preview/apply use the backend’s single active profile.

## D. Mapping Profiles

## 1. Where Templates Are Managed

### Backend routes

- `GET /api/v1/schedules/work-templates`
- `POST /api/v1/schedules/work-templates`
- `PUT /api/v1/schedules/work-templates/{template_id}`
- `DELETE /api/v1/schedules/work-templates/{template_id}`

### Backend functions

- `_fetch_schedule_templates`
- `_fetch_template_by_id_for_scope`

### Frontend ownership

- `frontend/index.html`
  - template owner panel inside schedule template/profile management area
- `frontend/js/app.js`
  - `loadScheduleTemplateRows`
  - template create/update/delete calls to `/schedules/work-templates`

### Persistence

- `migrations/004_schedule_templates_and_monthly_meta.sql`
  - `schedule_templates`

## 2. Where Mapping Profiles Are Managed

### Backend routes

- `GET /api/v1/schedules/import-mapping-profile`
- `PUT /api/v1/schedules/import-mapping-profile`
- `DELETE /api/v1/schedules/import-mapping-profile`

### Backend functions

- `_fetch_active_schedule_import_mapping_profile`
- `_build_schedule_import_mapping_summary`
- `_build_schedule_import_mapping_lookup`
- `_resolve_schedule_import_mapping_templates`

### Frontend ownership

- `frontend/js/app.js`
  - `loadScheduleImportMappingProfile`
  - `openScheduleImportMappingEditor`
  - `onScheduleImportMappingSave`
  - `onScheduleImportMappingDelete`

### Persistence

- `migrations/010_schedule_import_mapping_profiles.sql`
  - `schedule_import_mapping_profiles`
  - `schedule_import_mapping_entries`
- `migrations/011_schedule_template_delete_cascade.sql`
  - preserves mapping entries with `template_id = NULL` on template delete

## 3. How Profiles Are Selected In Upload Flow

### Backend reality

- Canonical import preview/apply calls `_fetch_active_schedule_import_mapping_profile`
- There is no backend route that lists multiple active profiles for user choice
- Preview stores:
  - `mapping_profile_id`
  - `mapping_profile_name`
  - `mapping_profile_updated_at`
  - summary metadata in `schedule_import_batches`
- Apply revalidates the same active-profile identity and `updated_at` before allowing apply

### Frontend behavior

- Selector/UI state
  - `#scheduleImportMappingProfileSelect`
  - `state.schedule.importMappingSelectedProfileId`
- Functions
  - `getScheduleImportMappingProfiles`
  - `ensureSelectedScheduleImportMappingProfileId`
  - `getSelectedScheduleImportMappingProfile`
- Key implementation detail
  - `getScheduleImportMappingProfiles()` wraps the single fetched profile into an array of one
  - selector change only updates local state and invalidates analysis
  - preview request does not submit a chosen profile id
  - backend preview/apply still resolve the active profile server-side

## 4. Current UI Ownership And Backend Contract

### Backend contract files

- `app/routers/v1/schedules.py`
- `app/schemas.py`
  - `ScheduleTemplateOut`
  - `ScheduleImportMappingProfileOut`
  - `ImportPreviewOut`

### Frontend contract files

- `frontend/index.html`
- `frontend/js/app.js`

### Contract mismatch to call out in second review

- UI implies multiple profile choice
- Backend contract only supports one active tenant profile
- The selector is therefore a presentation affordance, not true backend selection

## 5. Template Delete Behavior And Risk

### Current behavior

- Template deletion can invalidate linked mapping entries
- Backend marks affected mapping profiles inactive
- Mapping entries may survive with missing `template_id`
- Summary/build functions surface invalid entries and require operator repair

### Evidence

- `tests/test_schedule_template_delete_runtime.py`

## Exact Files / Functions / Routes

- `app/routers/v1/schedules.py`
  - `_fetch_schedule_templates`
  - `_fetch_active_schedule_import_mapping_profile`
  - `_build_schedule_import_mapping_summary`
  - `_build_schedule_import_mapping_lookup`
  - `_resolve_schedule_import_mapping_templates`
- `app/schemas.py`
  - `ScheduleTemplateOut`
  - `ScheduleImportMappingProfileOut`
- `frontend/js/app.js`
  - `loadScheduleTemplateRows`
  - `loadScheduleImportMappingProfile`
  - `getScheduleImportMappingProfiles`
  - `ensureSelectedScheduleImportMappingProfileId`
  - `openScheduleImportMappingEditor`
  - `onScheduleImportMappingSave`
  - `onScheduleImportMappingDelete`
- `frontend/index.html`
- `migrations/004_schedule_templates_and_monthly_meta.sql`
- `migrations/010_schedule_import_mapping_profiles.sql`
- `migrations/011_schedule_template_delete_cascade.sql`

## Architecture Review Notes

- Mapping/template ownership is cleanly inside ARLS, but the UI and backend contract are out of sync on profile multiplicity.
- Any second-stage redesign should decide whether ARLS truly supports multiple selectable profiles or intentionally collapses to one active profile per tenant.
