# ARLS Codebase Inventory

## Scope

- Analysis target: current working tree of `rg-arls-dev`
- External API mount point: `app/main.py` mounts routers under `/api/v1`
- Active runtime root: repository-root `app/` + `frontend/`
- Non-authoritative fallback: `backend/` currently contains mostly stale mirror artifacts and `__pycache__`, but deployment scripts still branch on it

## Primary Runtime Modules

| Path | What it does | Type |
| --- | --- | --- |
| `app/main.py` | FastAPI bootstrap, router registration, CORS/error envelope, mounts `schedules_router`, `schedules_bridge_router`, `integrations_router` | backend-domain |
| `app/config.py` | Runtime env contract, including Sentrix handoff URL/token settings | backend-domain |
| `app/db.py` | Database connection, bootstrap schema load, incremental migration runner, runtime schema repair SQL | backend-domain |
| `app/schemas.py` | Request/response contracts for schedule import, mapping profiles, HQ roster, Sentrix bridge, finance submission | backend-domain |
| `app/routers/v1/schedules.py` | Main ARLS schedule domain router: monthly upload, base apply, mapping/template CRUD, HQ roster ingest, finance publish/download, Sentrix bridge/materialization | backend-domain |
| `app/routers/v1/integrations.py` | Legacy SOC/Sentrix/Google Sheets integration router; still writes support-origin schedule rows and support assignments | integration |
| `app/services/p1_schedule.py` | Legacy support-assignment parsing/write helpers used by legacy integration paths | backend-domain |
| `app/integration_center/*.py` | Generic integration-center infra: feature flags, idempotency, audit log, receiver, sheets sync/adapters | integration |
| `app/templates/monthly_schedule_template.xlsx` | Canonical blank monthly workbook asset used by export/import flows | backend-domain |
| `app/templates/월간 근무표 템플릿 예시.xlsx` | Example workbook source used by template preparation flow | backend-domain |
| `frontend/index.html` | Single-page static UI shell; owns schedule upload, HQ roster, finance submission, mapping/template admin surfaces | frontend |
| `frontend/js/app.js` | Monolithic frontend controller; wires upload/inspect/apply/download flows to schedule APIs | frontend |
| `frontend/css/styles.css` | UI styling for the static PWA | frontend |
| `frontend/config.js` | Deployed frontend runtime config (`ENV_API_BASE`, `ENV_BUILD_ID`, maps key) | frontend |
| `migrations/*.sql` | Persistent schema history for schedule import, mapping, HQ roster, finance, Sentrix materialization | backend-domain |
| `scripts/deploy-azure.sh` | Primary Azure deploy implementation for backend container/zip and frontend static upload | deployment |
| `scripts/auto-deploy-hr.sh` | One-click deploy wrapper; also auto-add/commit/pushes dirty worktree before deploy | deployment |
| `scripts/publish-backend-origin.sh` | Syncs backend subset to `backend-origin`; preserves dual-layout packaging compatibility | deployment |
| `scripts/prepare_monthly_schedule_template.py` | Rebuilds blank monthly schedule workbook from sample file | deployment |
| `Dockerfile` | Active backend container build; runs `uvicorn app.main:app` | deployment |
| `requirements.txt` | Active backend runtime dependencies | deployment |
| `package.json` | Minimal Capacitor/dependency manifest; no real web build pipeline | deployment |
| `capacitor.config.json` | Capacitor packaging config; points mobile shell to static frontend URL | deployment |
| `tests/*.py` | Current regression coverage for canonical import, Sentrix boundary, HQ roster, finance, migrations/runtime repair | tests |

## Major Backend Ownership Areas

### Schedule domain owner

- `app/routers/v1/schedules.py`
  - Canonical monthly Excel import preview/apply
  - Mapping profiles and work templates
  - HQ roster workbook inspect/apply
  - Finance 1차/2차 workflow
  - Sentrix handoff and inbound support-origin materialization

### Legacy integration owner

- `app/routers/v1/integrations.py`
  - SOC webhook ingestion
  - Google Sheets support-assignment webhook
  - Legacy direct support schedule materialization
  - Parallel ownership risk for support-origin rows

### Schema/data owner

- `app/db.py`
  - Applies `migrations/001_init.sql` bootstrap
  - Applies incremental migrations
  - Runs runtime repair SQL:
    - `SCHEDULE_IMPORT_RAW_WORKBOOK_COLUMNS_SQL`
    - `MONTHLY_SCHEDULE_SHIFT_TYPE_CONSTRAINT_SQL`
    - `SENTRIX_SUPPORT_HQ_BATCH_SCOPE_CONSTRAINT_SQL`

## Key Frontend Ownership Areas

### Schedule upload and review UI

- `frontend/index.html`
  - Base upload wizard inputs: `#scheduleImportSite`, `#scheduleImportMonth`, `#scheduleImportFile`
  - Mapping profile selector: `#scheduleImportMappingProfileSelect`
- `frontend/js/app.js`
  - Base upload: `onScheduleTemplateDownload`, `onScheduleLatestBaseDownload`, `onSchedulePreview`, `onScheduleApply`
  - HQ roster: `loadScheduleSupportHqWorkspaceContract`, `onScheduleSupportHqInspect`, `onScheduleSupportHqApply`
  - Finance: `loadScheduleFinanceSubmissionStatus`, `loadScheduleFinanceHqWorkspace`, `onScheduleFinanceReviewDownload`, `onScheduleFinancePreview`, `onScheduleFinanceApply`, `onScheduleFinanceFinalDownload`

### Mapping/template admin UI

- `frontend/js/app.js`
  - Templates: `loadScheduleTemplateRows`
  - Profiles: `loadScheduleImportMappingProfile`, `openScheduleImportMappingEditor`, `onScheduleImportMappingSave`, `onScheduleImportMappingDelete`

## Schema / Migration Buckets

### Core schedule storage

- `migrations/001_init.sql`
  - `monthly_schedules`
  - import-batch baseline tables

### Template/mapping import support

- `migrations/004_schedule_templates_and_monthly_meta.sql`
- `migrations/005_schedule_import_roundtrip_hardening.sql`
- `migrations/010_schedule_import_mapping_profiles.sql`
- `migrations/011_schedule_import_apply_and_sentrix_tickets.sql`
- `migrations/011_schedule_template_delete_cascade.sql`

### HQ roster / Sentrix bridge

- `migrations/006_schedule_support_roundtrip.sql`
- `migrations/007_schedule_support_roundtrip_payload.sql`
- `migrations/012_sentrix_hq_roster_batches.sql`
- `migrations/013_sentrix_hq_postprocessing.sql`
- `migrations/014_arls_sentrix_support_materialization.sql`
- `migrations/019_sentrix_hq_roster_batches_allow_selected_scope.sql`

### Finance submission

- `migrations/008_schedule_finance_submission.sql`
- `migrations/020_schedule_finance_download_acks.sql`

## Test Clusters Worth Carrying Into Architecture Review

| Path group | What it covers | Type |
| --- | --- | --- |
| `tests/test_schedule_monthly_import_canonical.py` | Canonical workbook parse/preview/apply, support-demand handoff, lineage protections | tests |
| `tests/test_schedule_support_roundtrip.py` | HQ roster inspect/download/apply, support artifact semantics, replace-snapshot payload | tests |
| `tests/test_schedule_support_roundtrip_status.py` | Sentrix artifact/status payload for HQ workflow | tests |
| `tests/test_arls_support_origin_materialization.py` | Inbound Sentrix support-origin materialization/retract/link behavior | tests |
| `tests/test_sentrix_support_schedule_realtime.py` | Realtime publish behavior after bridge action processing | tests |
| `tests/test_schedule_finance_submission.py` | Finance permissions, status, publish/ack rules | tests |
| `tests/test_schedule_finance_review_export.py` | Finance 1차 export workbook generation and support block rendering | tests |
| `tests/test_schedule_template_delete_runtime.py` | Template delete side effects on mapping profiles | tests |
| `tests/test_sentrix_hq_roster_batch_scope_constraint_runtime.py` | Runtime/migration constraint repair for HQ roster scope | tests |
| `tests/test_soc_support_assignment_bridge.py` | Legacy integration materialization path still active in `integrations.py` | tests |

## Inventory Conclusions

- ARLS runtime authority lives in `app/routers/v1/schedules.py` plus `frontend/js/app.js`.
- `app/routers/v1/integrations.py` is not dead code; it remains a live parallel integration surface.
- Deployment is shell-script driven, not CI-driven.
- `backend/` should be treated as packaging compatibility residue, not as the primary review target.
