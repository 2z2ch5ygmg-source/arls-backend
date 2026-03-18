# Sentrix Codebase Inventory

## Scope
This inventory is limited to the Sentrix-related support workflow surface inside this repo. The repo also contains broader attendance, HR, finance, and admin features that are out of scope unless they directly touch Sentrix support ownership.

## Top-Level Layout

| Path | What it does | Category | Sentrix relevance |
| --- | --- | --- | --- |
| `app/` | FastAPI backend code | backend | Main backend runtime for Sentrix-adjacent support APIs |
| `frontend/` | Static SPA shell | UI | Contains the visible support-status and legacy workbook surfaces |
| `migrations/` | PostgreSQL schema migrations | backend-domain | Defines Sentrix ticket, batch, snapshot, notification, and bridge tables |
| `scripts/` | Azure deploy/publish helpers | deployment | Defines backend/frontend packaging and release coupling |
| `tests/` | Unit tests | tests | Confirms some intended Sentrix semantics even where runtime wiring is now partial |

## Major Modules

| Path | What it does | Category | Notes |
| --- | --- | --- | --- |
| `app/main.py` | FastAPI app composition, router inclusion, CORS, health/root endpoints | deployment | API-only runtime. It does not serve `frontend/`; `/` returns JSON, not the SPA. |
| `app/config.py` | Environment-backed settings | integration / deployment | Holds the external Sentrix handoff URL, bridge token, push flags, and CORS inputs. |
| `app/routers/v1/schedules.py` | Main Sentrix support router | backend-domain / integration / read-model | Central file for support ticket scope loading, HQ roster preview/apply, legacy support-roundtrip routes, bridge routes, and support-status read models. |
| `app/routers/v1/integrations.py` | Legacy SOC and sheet integration router | integration | Still owns old `support_assignment_*` event handling and Google Sheets webhook ingestion. |
| `app/routers/v1/notifications.py` | In-app notification read APIs | read-model | Lists and marks `in_app_notifications` rows; no Sentrix-specific write logic here. |
| `app/services/p1_schedule.py` | Legacy schedule/support-assignment service layer | backend-domain | Still provides `support_assignment` CRUD helpers used by old support paths. |
| `app/services/push_notifications.py` | Generic FCM push sending | integration | Shared notification transport used by Sentrix-adjacent helper code. |
| `app/schemas.py` | API request/response models | backend-domain | Defines the Sentrix support workspace, inspect/apply, support-status, and legacy support-roundtrip contracts. |
| `frontend/index.html` | Visible SPA markup | UI | Contains `/ops/support-workers` workspace panels and hidden legacy schedule tabs. |
| `frontend/js/app.js` | SPA behavior and route ownership | UI | Contains route table, support-status UI, external Sentrix handoff URL builder, and legacy schedule-tab routing. |
| `frontend/config.js` | Runtime frontend backend/build injection | deployment / frontend | Backend URL and build ID are mutated during deploy. |
| `frontend/sw.js` | Service worker shell/static cache | deployment / frontend | Can preserve stale UI assets across backend-only deploys. |
| `frontend/manifest.json` | PWA metadata | deployment / frontend | `start_url` is backend-coupled. |
| `migrations/011_schedule_import_apply_and_sentrix_tickets.sql` | Adds `sentrix_support_request_tickets` | backend-domain | Ticket truth schema. |
| `migrations/012_sentrix_hq_roster_batches.sql` | Adds HQ roster preview batch tables | backend-domain | Preview/persistence for HQ workbook inspect flow. |
| `migrations/013_sentrix_hq_postprocessing.sql` | Adds notifications, snapshots, bridge-action tables | backend-domain / integration | Intended downstream Sentrix state engine persistence. |
| `migrations/014_arls_sentrix_support_materialization.sql` | Adds ARLS materialization lineage tables/indexes | integration | Defines how approved self-staff support lands in `monthly_schedules`. |
| `migrations/016_sentrix_snapshot_entries_updated_at.sql` | Extends snapshot entry timestamps | backend-domain | Small follow-up migration. |
| `migrations/019_sentrix_hq_roster_batches_allow_selected_scope.sql` | Keeps `selected` scope valid | backend-domain | Matches current selected-site download behavior. |
| `Dockerfile` | Backend container build | deployment | Builds the backend from the whole repo root. |
| `scripts/deploy-azure.sh` | Primary backend/frontend deploy script | deployment | Separately deploys backend and static frontend, injects build/backend values into frontend. |
| `scripts/auto-deploy-hr.sh` | Auto-commit + deploy wrapper | deployment | Stages the whole repo via `git add .` before deploy. |
| `scripts/publish-backend-origin.sh` | Backend-only repo sync script | deployment | Publishes backend paths without frontend files. |

## Sentrix Category Map

### UI
- `frontend/index.html`
- `frontend/js/app.js`
- `frontend/config.js`
- `frontend/sw.js`
- `frontend/manifest.json`

### Core support-domain logic
- `app/routers/v1/schedules.py`
- `app/schemas.py`
- `migrations/011_schedule_import_apply_and_sentrix_tickets.sql`
- `migrations/012_sentrix_hq_roster_batches.sql`
- `migrations/013_sentrix_hq_postprocessing.sql`
- `migrations/014_arls_sentrix_support_materialization.sql`

### Internal integrations
- `app/routers/v1/integrations.py`
- `app/services/p1_schedule.py`
- `app/services/push_notifications.py`
- `app/config.py`

### Read-model / display-only
- `app/routers/v1/notifications.py`
- `app/routers/v1/schedules.py` support-status routes and workspace payload builders
- `frontend/index.html` support-status table and review panels
- `frontend/js/app.js` support-status presenter and route mapping

### Deployment / packaging sensitive
- `app/main.py`
- `Dockerfile`
- `scripts/deploy-azure.sh`
- `scripts/auto-deploy-hr.sh`
- `scripts/publish-backend-origin.sh`
- `frontend/config.js`
- `frontend/sw.js`
- `frontend/manifest.json`

## Immediate Architecture Reading

- The repo still contains a large local Sentrix support implementation, but the active apply path now hands off to an external Sentrix endpoint from `app/routers/v1/schedules.py:_post_sentrix_support_roster_handoff`.
- The visible workbook UI is still present in the SPA, even though the final apply button now opens an external Sentrix workspace from `frontend/js/app.js:buildSentrixHqSupportSubmissionUrl` and `onSupportStatusHqApply`.
- The old `support_assignment` stack is still live through backend routes and the SOC/sheet integration router, so this codebase currently mixes new Sentrix ownership with older workbook-driven ownership.
