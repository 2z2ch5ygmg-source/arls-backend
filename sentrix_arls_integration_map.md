# Sentrix ARLS Integration Map

## Executive Summary

- There are two different integration stories in the repo:
  - the newer Sentrix HQ roster snapshot / bridge model in `app/routers/v1/schedules.py`
  - the older SOC `support_assignment` event model in `app/routers/v1/integrations.py`
- The new model contains a queue, materializer, retry route, and self-staff eligibility logic.
- In this repo, the queue producer is orphaned; only the manual processor route is still clearly wired.

## 1. Inbound From ARLS

### Canonical monthly schedule import
- `app/routers/v1/schedules.py:_sync_canonical_schedule_import_sentrix_support_requests`
- `app/routers/v1/schedules.py:_build_canonical_schedule_import_sentrix_scope_apply_specs`

What happens:
- Parses uploaded monthly workbook support blocks.
- Converts them into Sentrix support scope specs.
- Posts a replace-style support roster snapshot outward via `_post_sentrix_support_roster_handoff`.

This is the clearest current ARLS-to-Sentrix upstream handoff in the repo.

### HQ workspace bridge endpoints for Sentrix UI
- Router prefix:
  - `app/routers/v1/schedules.py:133`
  - `bridge_router = APIRouter(prefix="/schedules/bridge/sentrix-hq", ...)`

Endpoints:
- `GET /api/v1/schedules/bridge/sentrix-hq/workspace`
- `GET /api/v1/schedules/bridge/sentrix-hq/artifact/download`
- `POST /api/v1/schedules/bridge/sentrix-hq/upload/inspect`
- `POST /api/v1/schedules/bridge/sentrix-hq/upload/{batch_id}/apply`

Auth:
- `app/routers/v1/schedules.py:_require_sentrix_support_bridge_token`
- Uses `X-Sentrix-Bridge-Token`

### Legacy support-assignment inbound paths
- `app/routers/v1/integrations.py`
  - support-assignment SOC event types
  - `support_assignment_*` materialization rules
- `POST /api/v1/integrations/google-sheets/support-assignments/webhook`
  - still ingests support assignments from Google Sheets

This is internal integration, but it is legacy for the target Sentrix architecture.

## 2. Outbound From Sentrix Toward ARLS

### Intended outbox
- Table:
  - `migrations/013_sentrix_hq_postprocessing.sql:123-159`
  - `sentrix_support_arls_bridge_actions`
- Queue builder:
  - `app/routers/v1/schedules.py:_queue_sentrix_hq_arls_bridge_actions`

### Materialization target
- `migrations/014_arls_sentrix_support_materialization.sql:48-102`
  - `sentrix_support_schedule_materializations`
- `monthly_schedules` lineage columns:
  - `source_ticket_uuid`
  - `source_ticket_state`
  - `source_action`
  - `source_self_staff`

### Active processor
- `app/routers/v1/schedules.py:_process_sentrix_support_arls_bridge_actions`
- Manual route:
  - `POST /api/v1/schedules/support-roundtrip/arls-bridge/process`

What it does:
- Pulls `pending` bridge actions and optionally `failed` actions when `include_failed=true`
- Calls `_apply_sentrix_support_bridge_action`
- Marks each action `success` or `failed`
- Refreshes leader defaults for affected dates
- Publishes realtime events

## 3. UPSERT / RETRACT Generation Rules

### Candidate builder
- `app/routers/v1/schedules.py:_build_sentrix_hq_bridge_candidates`

Eligibility:
- `self_staff` must be true
- `employee_id` must exist
- `validity_state` must be `valid`
- duplicates collapse by employee ID

### Queue semantics
- `app/routers/v1/schedules.py:_queue_sentrix_hq_arls_bridge_actions`

Rules:
- current approved and previous approved
  - UPSERT new IDs
  - RETRACT removed IDs
- current approved and previous not approved
  - UPSERT all current IDs
- previous approved and current not approved
  - RETRACT previous IDs

Payload details:
- includes `source_ticket_id`
- includes `ticket_state`
- includes `self_staff: True`
- includes `scope_key`
- uses an idempotency key per ticket/date/shift/employee/action/batch

## 4. Payload Normalization

### Support roster handoff payload
- `app/routers/v1/schedules.py:_build_sentrix_support_roster_handoff_payload`

Normalizes:
- tenant/month/site scope
- affected dates
- request count
- valid vs invalid filled counts
- target status
- workbook lineage
- artifact lineage
- worker entries
- replace scope

### Bridge action payload validation
- `app/routers/v1/schedules.py:_validate_sentrix_support_bridge_action_payload`

Hard gates:
- rejects non-self-staff payloads
- rejects UPSERT when ticket state is not approved

### Site / employee resolution
- `app/routers/v1/schedules.py:_resolve_sentrix_support_bridge_site`
- `app/routers/v1/schedules.py:_resolve_sentrix_support_bridge_employee`

## 5. Self-Staff Eligibility Rules

### Upstream parsing
- `app/routers/v1/schedules.py:_parse_sentrix_hq_worker_cell`
  - self-staff must match exact `자체 {이름}` pattern
  - must match an active employee at the site/date

### Bridge eligibility
- `app/routers/v1/schedules.py:_build_sentrix_hq_bridge_candidates`
  - only valid self-staff with employee IDs become bridge candidates

### Materialization enforcement
- `app/routers/v1/schedules.py:_validate_sentrix_support_bridge_action_payload`
  - rejects bridge payloads where `self_staff` is false

## 6. Retry Logic and Outbox Reality

### What exists
- Outbox table with `pending/success/failed/superseded`
- Manual process route
- `include_failed=true` retry switch

### What was not found
- No scheduler or automatic backoff worker for this outbox
- No in-repo caller of `_queue_sentrix_hq_arls_bridge_actions`

### Practical reading
- The processor exists.
- The local queue creator is currently not wired from the active apply path in this repo.
- That makes the bridge processor partially live but producer-side incomplete in-repo.

## 7. Materialization Rules

### Main executor
- `app/routers/v1/schedules.py:_apply_sentrix_support_bridge_action`

UPSERT behavior:
- If existing schedule is another Sentrix-owned row for the same source, update it.
- If existing schedule is non-Sentrix, link it without overwriting.
- Otherwise create a new Sentrix-owned `monthly_schedules` row.

RETRACT behavior:
- Removes owned schedule rows when appropriate.
- Can retract linked/orphan cases for same-source Sentrix rows.
- Persists retracted materialization state.

Shift defaults:
- `app/routers/v1/schedules.py:_resolve_sentrix_support_materialized_shift_defaults`
  - night uses default night shift
  - supervisor-ish roles get supervisor day defaults
  - otherwise guard day defaults

## 8. Realtime Events

- `app/routers/v1/schedules.py:_publish_sentrix_support_schedule_realtime_event`
- `tests/test_sentrix_support_schedule_realtime.py`

Event types:
- `sentrix_support_schedule_upserted`
- `sentrix_support_schedule_retracted`
- consolidated under realtime payload type `schedule_changed`

The tests show the intended site/month-scoped publish behavior even though `pytest` could not be executed in this environment because the module is not installed.

## 9. Legacy Internal Integration Still Live

### Event sets
- `app/routers/v1/integrations.py:116-165`
  - `SOC_SUPPORT_ASSIGNMENT_EVENT_TYPES`
  - `SOC_SUPPORT_ASSIGNMENT_RETRACT_EVENT_TYPES`

### Legacy materializer
- `app/routers/v1/integrations.py:_apply_support_assignment_for_ticket`

What it still does:
- resolves support-assignment action from SOC event state
- retracts previous materialized rows for a ticket snapshot
- writes `support_assignment` rows
- syncs internal schedules

### Why it matters
- This is a second, older support-to-schedule bridge.
- It materially overlaps with the newer Sentrix HQ bridge model.

## 10. Bottom Line

- The repo contains a robust design for Sentrix-to-ARLS bridge emission and materialization.
- The active in-repo path clearly still posts upstream support snapshots outward.
- The downstream local outbox producer is present but not wired.
- The older `support_assignment` bridge path is still alive and is the main mixed-ownership risk.
