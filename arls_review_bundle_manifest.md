# ARLS Review Bundle Manifest

## Bundle Policy

- Goal: send a compact but sufficient ARLS package for second-stage architecture review
- Do not send `backend/` as an authority source; current runtime authority is repository-root `app/` + `frontend/`
- Prefer files that define ownership boundaries, persisted schema, deploy behavior, and regression tests

## MUST SHARE

| Exact path | Why it matters | Category |
| --- | --- | --- |
| `app/routers/v1/schedules.py` | Primary ARLS authority file for base schedule truth, Excel ingress, HQ roster, finance workflow, Sentrix handoff, and inbound bridge processing | backend-domain |
| `app/routers/v1/integrations.py` | Live legacy integration path that still materializes support-origin rows and support assignments; critical for duplicate-ownership review | integration |
| `app/schemas.py` | API contract layer for import preview/apply, HQ roster, Sentrix-related status, and finance submission | backend-domain |
| `app/db.py` | Shows actual schema bootstrap, migration execution, and runtime repair behavior | backend-domain |
| `frontend/js/app.js` | Frontend ownership file for base upload, mapping profiles, HQ roster inspect/apply, and finance publish/download UX | frontend |
| `frontend/index.html` | Declares the actual ARLS workflow surfaces and upload controls exposed to operators | frontend |
| `migrations/008_schedule_finance_submission.sql` | Defines finance submission state and batch persistence model | finance |
| `migrations/011_schedule_import_apply_and_sentrix_tickets.sql` | Defines canonical import apply lineage and Sentrix support-request tracking tables | integration |
| `migrations/012_sentrix_hq_roster_batches.sql` | Defines new HQ roster upload batch/row storage | integration |
| `migrations/013_sentrix_hq_postprocessing.sql` | Defines Sentrix HQ snapshots, notifications, and bridge-action tables | integration |
| `migrations/014_arls_sentrix_support_materialization.sql` | Defines support-origin materialization ledger and extra lineage columns on `monthly_schedules` | integration |
| `migrations/020_schedule_finance_download_acks.sql` | Defines finance download acknowledgement and “update needed” support | finance |
| `tests/test_schedule_monthly_import_canonical.py` | Best executable spec for canonical Excel import, lineage protection, and support-demand handoff | tests |
| `tests/test_schedule_support_roundtrip.py` | Best executable spec for HQ roster inspect/apply, artifact state, and Sentrix replace-snapshot payloads | tests |
| `tests/test_arls_support_origin_materialization.py` | Best executable spec for Sentrix -> ARLS materialize/link/retract behavior | tests |
| `tests/test_schedule_finance_submission.py` | Best executable spec for finance permissions, publish state, and download acknowledgement logic | tests |
| `Dockerfile` | Active backend packaging/runtime entrypoint | deployment |
| `scripts/deploy-azure.sh` | Real deployment implementation, including root-vs-backend layout detection and frontend config rewrite | deployment |

## SHOULD SHARE

| Exact path | Why it matters | Category |
| --- | --- | --- |
| `app/config.py` | Carries Sentrix handoff URL/token settings and other runtime integration knobs | integration |
| `app/services/p1_schedule.py` | Legacy support-assignment helpers still used by old integration paths | backend-domain |
| `migrations/004_schedule_templates_and_monthly_meta.sql` | Defines `schedule_templates` and schedule-row template/time metadata | backend-domain |
| `migrations/005_schedule_import_roundtrip_hardening.sql` | Adds import hardening and `site_daytime_need_counts`, which base upload owns | backend-domain |
| `migrations/006_schedule_support_roundtrip.sql` | Defines legacy support-roundtrip source/batch/row/assignment tables | integration |
| `migrations/007_schedule_support_roundtrip_payload.sql` | Extends legacy roundtrip rows with payload storage | integration |
| `migrations/010_schedule_import_mapping_profiles.sql` | Defines mapping-profile persistence model | backend-domain |
| `migrations/011_schedule_template_delete_cascade.sql` | Shows template-delete behavior that can invalidate mapping profiles | backend-domain |
| `tests/test_schedule_finance_review_export.py` | Covers 1차 workbook regeneration and support block rendering | tests |
| `tests/test_schedule_support_roundtrip_status.py` | Covers support artifact/status payload semantics | tests |
| `tests/test_sentrix_support_schedule_realtime.py` | Covers realtime effects after bridge processing | tests |
| `tests/test_soc_support_assignment_bridge.py` | Shows the still-live legacy integration/materialization behavior in `integrations.py` | tests |
| `scripts/auto-deploy-hr.sh` | Critical because it auto-adds/commits/pushes the dirty worktree before deploy | deployment |
| `frontend/config.js` | Shows deploy-time API/build-id coupling of the static frontend | frontend |

## OPTIONAL

| Exact path | Why it matters | Category |
| --- | --- | --- |
| `app/templates/monthly_schedule_template.xlsx` | Canonical workbook asset if reviewer needs physical sheet layout, not just code | backend-domain |
| `scripts/prepare_monthly_schedule_template.py` | Explains how the blank workbook asset is regenerated from sample input | deployment |
| `package.json` | Confirms there is no real frontend build pipeline; static deploy only | deployment |
| `capacitor.config.json` | Shows mobile shell coupling to deployed static frontend URL | deployment |
| `scripts/publish-backend-origin.sh` | Explains extra backend-only publishing path and layout compatibility residue | deployment |
| `tests/test_schedule_template_delete_runtime.py` | Useful if the review needs deeper mapping/template invalidation behavior | tests |
| `tests/test_sentrix_hq_roster_batch_scope_constraint_runtime.py` | Useful if the review needs runtime/migration constraint repair details | tests |
| `README.md` | Confirms current active layout and deployment policy in plain language | deployment |
| `REPO_STRUCTURE.md` | Confirms repository authority split and backend-origin fallback | deployment |

## Files Intentionally Omitted

- `backend/`
  - not an authoritative current source tree
  - mainly stale mirror artifacts and caches in this workspace
- broad unrelated modules outside ARLS schedule/import/integration/deploy ownership
  - not needed for the second-stage architecture review package

## Recommended Send Order

1. `app/routers/v1/schedules.py`
2. `app/routers/v1/integrations.py`
3. `app/schemas.py`
4. schema migrations from `MUST SHARE`
5. `frontend/js/app.js`
6. `frontend/index.html`
7. tests from `MUST SHARE`
8. deployment files

## Architecture Review Notes

- If the second-stage reviewer only takes one backend file, it must be `app/routers/v1/schedules.py`.
- If the reviewer ignores `app/routers/v1/integrations.py`, they will miss the biggest duplicate-ownership risk in the current architecture.
