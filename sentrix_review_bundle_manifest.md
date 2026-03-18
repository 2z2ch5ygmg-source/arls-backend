# Sentrix Review Bundle Manifest

## Goal

This bundle is sized for a second-stage architecture review. The MUST set is the smallest set that still exposes:

- active Sentrix routes and state logic
- legacy overlap and mixed ownership
- visible UI ownership
- deployment/packaging coupling

## MUST SHARE

| Exact path | Why it matters | Category |
| --- | --- | --- |
| `app/routers/v1/schedules.py` | Central Sentrix file. Contains support-status read models, HQ roster inspect/apply, bridge routes, legacy support-roundtrip routes, and the external handoff boundary. | backend-domain |
| `app/routers/v1/integrations.py` | Shows the still-live older SOC `support_assignment` bridge and Google Sheets webhook paths that overlap with Sentrix ownership. | integration |
| `app/services/p1_schedule.py` | Contains live `support_assignment` CRUD rules and slot semantics that still back legacy support ownership. | backend-domain |
| `app/schemas.py` | Defines Sentrix support contracts, including support-status, HQ inspect/apply, legacy roundtrip, and support-assignment schemas. | backend-domain |
| `app/config.py` | Holds the external Sentrix handoff URL, bridge token, timeout, CORS, and push flags that define the real runtime boundary. | integration |
| `app/main.py` | Shows that the backend is API-only, includes both schedule routers, and does not serve the SPA. | deployment |
| `frontend/js/app.js` | Central route table and UI ownership logic. Shows external `mode=hq-submission` redirect, visible workbook ingress, hidden legacy routes, and support-status presenters. | frontend |
| `frontend/index.html` | Shows the actual visible support-status UI, HQ workbook workspace, REPLACE note, and hidden schedule HQ/report tabs. | frontend |
| `migrations/011_schedule_import_apply_and_sentrix_tickets.sql` | Defines `sentrix_support_request_tickets`, the intended ticket-truth table. | backend-domain |
| `migrations/012_sentrix_hq_roster_batches.sql` | Defines HQ roster preview batch persistence. | backend-domain |
| `migrations/013_sentrix_hq_postprocessing.sql` | Defines snapshots, notification audit, bridge outbox, and in-app notifications. | backend-domain |
| `migrations/014_arls_sentrix_support_materialization.sql` | Defines ARLS materialization lineage and bridge result persistence. | integration |
| `scripts/deploy-azure.sh` | Shows separate backend/frontend deployment, frontend config injection, CORS mutation, and release coupling. | deployment |

## SHOULD SHARE

| Exact path | Why it matters | Category |
| --- | --- | --- |
| `Dockerfile` | Shows backend image packaging from the whole repo root. | deployment |
| `app/services/push_notifications.py` | Generic push sender used by the Sentrix notification design. | integration |
| `app/routers/v1/notifications.py` | Read-model API for `in_app_notifications`. Useful to confirm the repo still owns notification inbox reads. | integration |
| `frontend/config.js` | Runtime backend/build injection point. | deployment |
| `frontend/sw.js` | Service-worker cache behavior; key frontend regression vector. | frontend |
| `frontend/manifest.json` | Shows PWA/backend coupling via `start_url`. | frontend |
| `migrations/016_sentrix_snapshot_entries_updated_at.sql` | Small but relevant follow-up migration on snapshot persistence. | backend-domain |
| `migrations/019_sentrix_hq_roster_batches_allow_selected_scope.sql` | Confirms current selected-site scope semantics. | backend-domain |
| `scripts/auto-deploy-hr.sh` | Shows risky repo-wide auto-commit deploy behavior. | deployment |
| `scripts/publish-backend-origin.sh` | Shows backend-only publish behavior that can diverge from frontend changes. | deployment |

## OPTIONAL

| Exact path | Why it matters | Category |
| --- | --- | --- |
| `tests/test_schedule_support_roundtrip.py` | Covers HQ roster inspect rules, status normalization, snapshot-signature behavior, and legacy support-roundtrip helpers. | tests |
| `tests/test_schedule_monthly_import_canonical.py` | Confirms canonical import posts full replace snapshots and empty-scope removals. | tests |
| `tests/test_sentrix_support_schedule_realtime.py` | Confirms intended realtime event behavior for bridge processing. | tests |
| `tests/test_soc_support_assignment_bridge.py` | Shows expected behavior for the old SOC support-assignment bridge. | tests |
| `tests/test_schedule_support_roundtrip_status.py` | Confirms legacy status payload shape and support-assignment counts. | tests |
| `tests/test_support_assignment_schema_bootstrap.py` | Useful for understanding legacy support-assignment schema invariants. | tests |
| `tests/test_sentrix_hq_roster_batch_scope_constraint_runtime.py` | Confirms selected/all/site scope constraint behavior. | tests |
| `tests/test_user_friendly_error_messages.py` | Useful for error-surface review, but not core architecture. | tests |

## Compact Review Order

If the reviewer wants the fastest useful pass, share files in this order:

1. `app/routers/v1/schedules.py`
2. `frontend/js/app.js`
3. `frontend/index.html`
4. `app/routers/v1/integrations.py`
5. `app/services/p1_schedule.py`
6. `app/schemas.py`
7. `migrations/011_schedule_import_apply_and_sentrix_tickets.sql`
8. `migrations/012_sentrix_hq_roster_batches.sql`
9. `migrations/013_sentrix_hq_postprocessing.sql`
10. `migrations/014_arls_sentrix_support_materialization.sql`
11. `app/config.py`
12. `scripts/deploy-azure.sh`

## Why This Bundle Is Sufficient

- It captures both the active Sentrix handoff flow and the older still-live support-assignment flow.
- It captures both backend and visible frontend ownership.
- It captures the schema that explains intended truth ownership.
- It captures the deployment scripts that can cause cross-surface regressions.
