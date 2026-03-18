# Sentrix Risk Ledger

## Validation Note

- Static code inspection completed.
- Targeted Sentrix-adjacent tests could not be executed in this environment because `pytest` is not installed (`pytest` not on PATH and `python3 -m pytest` reported `No module named pytest`).

## Top Risks

| Severity | Risk | Why it matters | Evidence |
| --- | --- | --- | --- |
| Critical | Split ownership transition | The repo still models local Sentrix ticket/snapshot/notification/bridge ownership, but the active write paths now hand off externally. Reviewers can easily assume a local state engine that no longer runs here. | `_sync_canonical_schedule_import_sentrix_support_requests` and `_apply_sentrix_hq_roster_batch` post outward via `_post_sentrix_support_roster_handoff`; local ticket/snapshot/notification helpers have no in-repo caller. |
| Critical | Three support engines coexist | New Sentrix HQ handoff flow, old support-roundtrip workbook flow, and old SOC `support_assignment` bridge are all still present. | `app/routers/v1/schedules.py`, `app/routers/v1/integrations.py`, `app/services/p1_schedule.py` |
| High | Visible workbook ingress still lives in ARLS UI | The target architecture says Sentrix is not the visible workbook ingress owner, but this repo still renders workbook download/upload/inspect UI. | `frontend/index.html:1635-1710`, `frontend/js/app.js:onSupportStatusHqDownload`, `onSupportStatusHqInspect` |
| High | Support-status read-model mixes truths | Support status joins `sentrix_support_request_tickets` with `support_assignment`, so display behavior can reflect legacy assignments even when Sentrix ticket ownership has moved. | `app/routers/v1/schedules.py:_load_support_status_workspace_rows` |
| High | Orphaned local ticket/snapshot/bridge/notification code | Critical-looking functions exist but are not wired, which raises drift risk between intended architecture and active behavior. | No in-repo caller found for `_upsert_sentrix_support_request_ticket_row`, `_persist_sentrix_hq_roster_snapshot`, `_queue_sentrix_hq_arls_bridge_actions`, notification audit helpers |
| High | Legacy `support_assignment` APIs are still writable | Manual and webhook-driven writes can still create support state outside the newer Sentrix ownership model. | `POST/GET/DELETE /api/v1/schedules/support-assignments`, Google Sheets webhook in `app/routers/v1/integrations.py` |
| High | Deploy process can ship unrelated UI changes | Auto-deploy stages the entire repo before deploy, and frontend/backend deploys are not one release unit. | `scripts/auto-deploy-hr.sh`, `scripts/deploy-azure.sh` |
| Medium | Service-worker cache can preserve stale UI | Backend changes can land without shell refresh, or old UI can linger after frontend changes. | `frontend/sw.js` caches `index.html`, `config.js`, `js/app.js` |
| Medium | Hidden routes still remain reachable | Legacy or mixed-ownership routes can survive through route normalization and known-route handling even if tabs are hidden. | `frontend/js/app.js:isKnownRoute`, `normalizeRoutePath`, hidden `hq-upload` tab in `frontend/index.html` |
| Medium | Manual retry only for ARLS bridge outbox | Processor exists, but retry is manual and no automatic outbox worker was found. | `POST /api/v1/schedules/support-roundtrip/arls-bridge/process`, `_process_sentrix_support_arls_bridge_actions` |
| Medium | Schema/contract drift | Output models include fields like `snapshot_changed`, `assignments_created`, and `snapshots_created`, but current result builders do not populate them. | `app/schemas.py:1569-1640`, no in-repo writer hits for those fields |

## Duplicated Rules

### Support assignment state exists in more than one place
- `sentrix_support_request_tickets`
- `support_assignment`
- `schedule_support_roundtrip_assignments`
- `sentrix_support_schedule_materializations`

### Support event interpretation exists in more than one place
- New HQ roster inspect/apply logic in `app/routers/v1/schedules.py`
- SOC `support_assignment_*` event logic in `app/routers/v1/integrations.py`
- direct manual support-assignment CRUD in `app/services/p1_schedule.py`

### Replace semantics exist in more than one layer
- frontend REPLACE note
- support roster handoff payload replace scope
- old support-roundtrip batch apply clears and rewrites assignment/materialized rows by snapshot-like behavior

## Old Validators Still Alive

- `app/services/p1_schedule.py:upsert_support_assignment`
  - validates worker type, support period, slot assignment
- `app/schemas.py:SupportAssignmentCreate`
  - still validates manual support-assignment payloads
- `app/routers/v1/integrations.py:_resolve_support_assignment_materialization_action`
  - still interprets old support-assignment event statuses
- `POST /api/v1/integrations/google-sheets/support-assignments/webhook`
  - still accepts legacy sheet-driven support input

These are not passive leftovers. They still gate runtime behavior.

## Mixed Ownership Zones

### Mixed UI ownership
- Support-status HQ panel still exposes workbook ingress locally.
- Final apply redirects to external Sentrix.

### Mixed domain ownership
- New Sentrix HQ flow wants tickets/roster/state in Sentrix terms.
- Old support-roundtrip flow still owns workbook merge and local `support_assignment`.

### Mixed integration ownership
- New Sentrix bridge tables and processor exist.
- Old SOC support-assignment bridge still writes `support_assignment` rows and internal schedules.

## Fragile Integration Boundaries

### External handoff boundary
- `SOC_SUPPORT_ROSTER_HANDOFF_URL` is the critical ownership boundary.
- Local apply success now depends on remote response shape, counters, and status mapping.

### Bridge token boundary
- `/api/v1/schedules/bridge/sentrix-hq/*` depends on `X-Sentrix-Bridge-Token`.
- The token exists in config, but route behavior and external UI behavior are coupled by convention, not local type safety.

### Read-model boundary
- Support status UI can appear healthy even when true ticket writes moved elsewhere, because it reads mixed local tables.

## Most Dangerous Areas To Touch

### Highest danger
- `app/routers/v1/schedules.py`
  - one file contains new Sentrix domain logic, old roundtrip logic, read-model builders, bridge routes, and manual retry path
- `app/routers/v1/integrations.py`
  - still owns legacy support-assignment materialization
- `frontend/js/app.js`
  - route ownership and handoff behavior are centralized here
- `scripts/deploy-azure.sh`
  - controls backend/frontend release skew

### High danger supporting files
- `app/services/p1_schedule.py`
- `app/schemas.py`
- `frontend/index.html`
- `frontend/sw.js`
- Sentrix migrations `011` through `014`

## Bottom Line

- The biggest architecture risk is not one bug. It is unresolved coexistence between the intended Sentrix ownership model and the still-live legacy support-assignment/workbook stack.
- Any second-stage review should treat this repo as a transition-state codebase, not as a clean single-owner implementation.
