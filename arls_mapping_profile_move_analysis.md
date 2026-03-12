# ARLS Mapping Profile Move Analysis

Inspection date: 2026-03-11  
Codebase inspected: `/Users/mark/Desktop/rg-arls-dev`

## 1. Where the mapping profile UI currently lives

Current visible entry points:
- `/Users/mark/Desktop/rg-arls-dev/frontend/index.html`
  - `#scheduleUploadPanel`
  - `#scheduleTemplatePanel`

Current buttons:
- `data-action="schedule-import-mapping-edit"` appears in the schedule template panel actions
- the same edit action is also available from the upload flow context

Current summary rendering location:
- `#scheduleTemplateMappingSummary`
- `#scheduleTemplateMappingBadge`
- `#scheduleTemplateMappingText`
- `#scheduleTemplateMappingMissing`

Important finding:
- The edit action is reachable from multiple places.
- The visible summary is still effectively anchored to the `근무 템플릿` panel, not the `근무표 간편 제작` upload workspace.

## 2. Where the mapping profile data is stored

Backend storage:
- table `schedule_import_mapping_profiles`
- table `schedule_import_mapping_entries`

Migration:
- `/Users/mark/Desktop/rg-arls-dev/migrations/010_schedule_import_mapping_profiles.sql`

Batch linkage:
- schedule import batches store:
  - `mapping_profile_id`
  - `mapping_profile_name`
  - `mapping_profile_updated_at`

Meaning:
- The mapping profile is not a purely visual setting.
- It is part of schedule import analysis and stale-check logic.

## 3. Files, services, and models that validate and persist it

### Frontend

Files:
- `/Users/mark/Desktop/rg-arls-dev/frontend/index.html`
- `/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js`
- `/Users/mark/Desktop/rg-arls-dev/frontend/css/styles.css`

Key frontend functions:
- `loadScheduleImportMappingProfile`
- `renderScheduleImportMappingProfileSummary`
- `openScheduleImportMappingEditor`
- `onScheduleImportMappingSave`
- `buildScheduleImportMappingTemplateOptions`
- `createScheduleImportMappingEntryEditorRow`

### Backend

File:
- `/Users/mark/Desktop/rg-arls-dev/app/routers/v1/schedules.py`

Key backend functions and endpoints:
- `_fetch_active_schedule_import_mapping_profile`
- `_build_schedule_import_mapping_summary`
- `_build_schedule_import_mapping_lookup`
- `_serialize_schedule_import_mapping_profile`
- `_resolve_schedule_import_mapping_templates`
- `GET /import-mapping-profile`
- `PUT /import-mapping-profile`

Validation coupling into import preview/apply:
- schedule import preview reads the active mapping profile
- mapping requirements are enforced during preview
- apply guards against stale mapping/profile changes

## 4. Whether it is tightly coupled to schedule template creation UI

### Backend coupling

Backend coupling to template creation UI:
- low

Reason:
- The backend contract is profile-based, not template-screen-based.
- Backend only needs active template ids and valid mapping entries.

### Frontend coupling

Frontend coupling to template screen:
- medium

Reason:
- `renderScheduleImportMappingProfileSummary` currently targets template-panel-only DOM ids
- the profile summary lives visually inside `근무 템플릿`
- the editor loads template rows and depends on template availability

Conclusion:
- The feature is not tightly coupled at contract level.
- It is only coupled at current frontend placement/rendering level.

## 5. Can it be moved into “근무표 간편 제작” without backend contract change

Answer:
- Yes.

Why:
- the backend endpoints already expose the profile independently
- the profile is used by the upload analysis path
- no API shape change is required just to move the UI
- the current editor already fetches template rows directly before opening

What remains true after the move:
- template rows still provide selectable mapping targets
- preview/apply stale protection still works
- profile persistence still uses the same endpoints and tables

## 6. Exact files that must change to move it cleanly

### Required frontend files

Must change:
- `/Users/mark/Desktop/rg-arls-dev/frontend/index.html`
  - move the visible summary block out of `#scheduleTemplatePanel`
  - place profile summary and edit affordance fully in `#scheduleUploadPanel`
- `/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js`
  - stop hardcoding summary rendering to template-panel ids
  - render the summary in the upload workspace
  - keep editor preload behavior for active templates
- `/Users/mark/Desktop/rg-arls-dev/frontend/css/styles.css`
  - restyle the moved summary/editor block so it fits the upload workspace layout

### Backend files

Likely no contract change required:
- `/Users/mark/Desktop/rg-arls-dev/app/routers/v1/schedules.py`

Possible backend change only if desired later:
- permission copy or response text only

## 7. Risks if the mapping profile UI is moved

### Functional risks

Risks:
- If only HTML is moved and the renderer is not updated, the summary will disappear.
- If upload workspace does not preload active template rows, the editor may open without valid template options.
- Users may lose visibility of missing required mappings if preview-state messaging is not carried over.
- Apply can still fail on stale mapping/profile changes if the upload UI does not preserve that explanation.

### UX risks

Risks:
- If both old and new entry points remain, the feature will keep feeling duplicated.
- If the old template-panel summary is removed without a replacement summary in upload, operators may not realize mapping is required before preview.

### Data risks

Risks:
- Low.
- Data stays in the same tables and endpoints.
- No migration is required for a UI-only move.

## 8. Final assessment

Best interpretation:
- Mapping profile belongs closer to `근무표 간편 제작` because it directly controls Excel import analysis.
- The backend already supports that placement.
- The current misplacement is mostly a frontend ownership problem, not a data-model problem.
