# ARLS Risk Ledger

## Highest-Risk Findings

| Severity | Risk | Evidence | Why it matters |
| --- | --- | --- | --- |
| High | `app/routers/v1/schedules.py` is a monolithic hotfix zone | One file owns base import, mapping profiles, HQ roster, finance workflow, Sentrix bridge, realtime side effects | A small change can regress multiple ownership surfaces at once |
| High | Duplicate inbound support-origin materialization paths | `app/routers/v1/schedules.py` bridge processor and `app/routers/v1/integrations.py` legacy SOC/Sentrix materialization both write support-origin schedule rows | Competing write paths make ownership unclear and regressions hard to isolate |
| High | Duplicate HQ roster workflow surfaces | New `/schedules/support-roundtrip/hq-roster-*` flow coexists with legacy `/schedules/support-roundtrip/hq-*` preview/apply/final-excel flow | Architecture review must decide which path is authoritative before refactor |
| High | Mapping-profile selector implies a capability the backend does not actually support | `frontend/js/app.js` keeps `importMappingSelectedProfileId`, but backend preview/apply only call `_fetch_active_schedule_import_mapping_profile` | Operators can believe they selected a different profile when they did not |
| High | Deploy wrapper auto-commits the whole dirty worktree | `scripts/auto-deploy-hr.sh` runs `git add .` then commits and pushes | Unreviewed files can be shipped during operational deployment |
| Medium | Deployment scripts still support root-layout and `backend/` sub-layout | `scripts/deploy-azure.sh` and `scripts/publish-backend-origin.sh` branch on both layouts | Manual deploys can target stale packaging assumptions |
| Medium | Runtime repair SQL can conceal migration drift | `app/db.py` applies repair SQL for raw workbook columns and HQ scope constraint | Production can appear healthy while schema history is out of sync |
| Medium | Legacy Google Sheets support-assignment webhook is gated, not removed | `POST /api/v1/integrations/google-sheets/support-assignments/webhook` remains live and is only blocked when support-roundtrip source is active | Wrong ingress path can reactivate stale ownership unexpectedly |
| Medium | Stale/possibly unused Sentrix HQ helper code remains in core router | `_build_sentrix_hq_roster_ticket_detail_json`, `_persist_sentrix_hq_roster_snapshot`, `_queue_sentrix_hq_arls_bridge_actions` exist without obvious local call sites | Dead or half-dead paths raise hotfix risk because intent is unclear |
| Medium | Frontend is a raw static monolith with no compile/build guardrail | `frontend/js/app.js` is large, stateful, and deployed as-is | UI contract regressions are easy to introduce and hard to lint structurally |

## Duplicate Workflow Surfaces

### Support-origin ingestion

- New path
  - `app/routers/v1/schedules.py`
  - `POST /api/v1/schedules/support-roundtrip/arls-bridge/process`
- Legacy path
  - `app/routers/v1/integrations.py`
  - `POST /api/v1/integrations/soc/events`
  - `POST /api/v1/integrations/google-sheets/support-assignments/webhook`

### HQ roster flow

- New Sentrix-facing path
  - `/api/v1/schedules/support-roundtrip/hq-workspace`
  - `/api/v1/schedules/support-roundtrip/hq-roster-workbook`
  - `/api/v1/schedules/support-roundtrip/hq-roster-upload/inspect`
  - `/api/v1/schedules/support-roundtrip/hq-roster-upload/{batch_id}/apply`
- Legacy local roundtrip path
  - `/api/v1/schedules/support-roundtrip/hq-workbook`
  - `/api/v1/schedules/support-roundtrip/hq-upload/preview`
  - `/api/v1/schedules/support-roundtrip/hq-upload/{batch_id}/apply`
  - `/api/v1/schedules/support-roundtrip/final-excel`

## Stale Validators / Wrong Ownership Remnants

- Mapping profile UI presents selection semantics beyond the backend contract
- `HQ_ROUNDTRIP` schedule-row ownership still exists even though the newer flow pushes normalized snapshots to Sentrix
- `app/routers/v1/integrations.py` still treats support assignment events as snapshot-based direct schedule truth materialization
- `backend/` packaging compatibility remains in deploy scripts even though root `app/` is the active code root

## Fragile Integration Points

### Sentrix boundary

- `_build_sentrix_support_roster_handoff_payload`
- `_post_sentrix_support_roster_handoff`
- `_process_sentrix_support_arls_bridge_actions`
- `_apply_sentrix_support_bridge_action`

### Finance boundary

- `_sync_finance_submission_state`
- `_load_finance_submission_final_artifact_for_site`
- `_record_finance_submission_download_ack`

### Canonical import boundary

- `_build_schedule_import_preview_result`
- `_load_canonical_schedule_import_apply_context`
- `_apply_canonical_schedule_import_batch`

## Risky Hotfix Zones

### Backend

- `app/routers/v1/schedules.py`
- `app/routers/v1/integrations.py`
- `app/db.py`

### Frontend

- `frontend/js/app.js`
- `frontend/index.html`

### Deployment

- `scripts/deploy-azure.sh`
- `scripts/auto-deploy-hr.sh`
- `scripts/publish-backend-origin.sh`

## Current-Worktree Risk Context

- Current dirty tracked files already include:
  - `app/routers/v1/schedules.py`
  - `app/schemas.py`
  - `frontend/index.html`
  - `frontend/js/app.js`
  - `scripts/deploy-azure.sh`
  - finance/import tests
- There is also an untracked finance migration:
  - `migrations/020_schedule_finance_download_acks.sql`

## Existing Test Coverage That Reduces Risk

- `tests/test_schedule_monthly_import_canonical.py`
- `tests/test_schedule_support_roundtrip.py`
- `tests/test_arls_support_origin_materialization.py`
- `tests/test_schedule_finance_submission.py`
- `tests/test_schedule_finance_review_export.py`
- `tests/test_soc_support_assignment_bridge.py`

## Architecture Review Notes

- The main architectural problem is not lack of functionality; it is duplicate ownership and accumulated workflow overlap.
- The first thing the second-stage review should decide is which support/HQ ingress and materialization paths are authoritative and which are legacy.
