# Final ARLS ↔ Sentrix Excel Workflow Verification

## Scope
- Verification only
- No product code changed in this task
- Evidence combines:
  - live production read-only API/download checks
  - local automated ARLS unit/integration tests
  - local Sentrix temp-DB integration harness using current backend code

## Environment
- Date: 2026-03-12
- ARLS backend: `https://rg-arls-backend.azurewebsites.net`
- Sentrix app: `https://security-ops-center-prod-002-260227135557.azurewebsites.net`
- ARLS auth used for live checks:
  - tenant: `MASTER`
  - account: `platform_admin`

## Evidence Limits
- This shell session did not capture browser screenshots.
- Sentrix live `hq_admin / Admin123!` login returned `401`, so Sentrix production verification was limited to:
  - health / deployed asset inspection
  - local temp-DB execution of the current backend logic
- No production workbook upload/apply was executed in this verification pass to avoid mutating live operational data.

## Live Production Checks

### 1. Service health
- ARLS `/health` returned `200`
- Sentrix `/health` returned `200`

### 2. ARLS HQ workspace ownership
- `GET /api/v1/schedules/support-roundtrip/hq-workspace?tenant_code=SRS_Korea&month=2026-03`
  - `200`
  - `tenant_code = srs_korea`
  - `total_site_count = 2`
  - `ready_site_count = 1`
  - `R692` -> `download_ready = true`, `source_state = hq_merge_available`
  - `R738` -> `download_ready = false`, `source_state = source_missing`

### 3. ARLS site status
- `R692`
  - `source_revision = 1b11b4b3fc4a72cb`
  - `latest_hq_revision = d75aad9d9f4a40b3`
  - `latest_merged_revision = 9a340d29e5bb11cf`
  - `hq_merge_available = true`
  - `final_download_enabled = true`
- `R738`
  - `source_state = source_missing`
  - `blocked_reasons = ["Supervisor 기준 소스 월간 파일이 아직 업로드/반영되지 않았습니다."]`

### 4. ARLS HQ workbook download
- `GET /api/v1/schedules/support-roundtrip/hq-roster-workbook?tenant_code=SRS_Korea&month=2026-03&scope=site&site_code=R692`
  - `200`
  - filename: `2026년 3월 지원근무자 배정 workbook_R692_260312.xlsx`
  - visible sheet: `Apple_가로수길`
  - hidden metadata sheets:
    - `_ARLS_SUPPORT_META`
    - `_SENTRIX_SUPPORT_HQ_META`
- workbook metadata confirmed:
  - `tenant_code = srs_korea`
  - `site_code = R692`
  - `month = 2026-03`
  - `source_revision = 1b11b4b3fc4a72cb`
  - `workbook_family = support_roundtrip.phase3.v1`
  - `bundle_revision = 26a61b383dd4b21b`

### 5. ARLS final workbook download
- `GET /api/v1/schedules/support-roundtrip/final-excel?tenant_code=SRS_Korea&month=2026-03&site_code=R692`
  - `200`
  - filename: `2026년 3월 근무표_R692_지원병합_260312.xlsx`
  - visible sheet: `본사 스케쥴 양식`
  - support section non-empty cells found: `14`
  - sample values:
    - `2026-03-01 day -> BK 강상모`
    - `2026-03-03 day -> BK 강상모`
    - `2026-03-10 night -> BK 김주현`

## ARLS Automated Checks
- `/Users/mark/Desktop/rg-arls-dev/tests/test_schedule_support_roundtrip.py`
  - selected HQ inspect / stale / handoff payload tests: `6 passed`
- `/Users/mark/Desktop/rg-arls-dev/tests/test_soc_support_assignment_bridge.py`
- `/Users/mark/Desktop/rg-arls-dev/tests/test_arls_support_origin_materialization.py`
  - bridge + materialization + retract tests: `11 passed`

These test bands confirmed:
- overfilled scope is blocked at ARLS inspect
- stale site partial continue works
- handoff payload preserves artifact/scope lineage
- ARLS bridge apply/retract handlers materialize and retract support-origin schedule rows correctly in isolation

## Sentrix Local Integration Harness Checks

The current Sentrix backend was executed against a temp SQLite runtime using:
- `_consume_support_roster_scope_snapshots()`
- current ticket creation/update helpers
- current snapshot persistence helpers
- current side-effect band

### Step 2B core outcome
Confirmed locally:
- missing scope creates a support ticket
- existing scope updates the same ticket in place
- `request_count` is taken from the normalized snapshot
- latest roster snapshot replaces prior snapshot
- `approved` / `pending` state is recalculated from latest snapshot
- confirmed workers remain stored even when final state is `pending`
- night `purpose_text` is preserved as `work_purpose`

### Step 3B side-effect outcome
Blocked by a real defect:
- side-effect execution logs:
  - `[support-roster.consume] side-effect failed ticket_id=... error=NameError:name 'get_ticket_status_label' is not defined`
- effect:
  - ticket row update succeeds
  - snapshot persistence succeeds
  - `ticket_status_updated` broadcast still fires in some approved/pending transitions
  - required support-roster notification path does not complete
  - `integration_outbox` stays empty
  - fresh ARLS UPSERT / RETRACT emission is not confirmed end-to-end

## Scenario Summary

### Scenario 1. Base monthly upload only
- Result: PASS
- Basis:
  - ARLS source status exists for `R692`
  - HQ artifact workbook downloads from ARLS
  - no Sentrix workbook UI is needed to access the Excel flow

### Scenario 2. HQ exact-filled support upload
- Result: FAIL
- What worked:
  - Sentrix created ticket
  - status became `approved`
  - confirmed workers stored: `홍길동`, `김영희`
  - night `work_purpose = 야간 점검`
- Break point:
  - Step 3B side-effect crash before support-roster notification / outbox enqueue

### Scenario 3. HQ underfilled support upload
- Result: FAIL
- What worked:
  - same ticket updated in place
  - status became `pending`
  - confirmed worker remained visible: `홍길동`
- Break point:
  - no RETRACT outbox emitted because the same Step 3B crash aborted side effects

### Scenario 4. HQ overfilled support upload
- Result: FAIL
- What worked:
  - status stayed `pending`
  - confirmed workers stored: `홍길동`, `김영희`, `외부A`
- Break point:
  - no notification side effect observed for initial overfilled pending scope
  - no fresh bridge materialization path exercised

### Scenario 5. External worker only
- Result: FAIL
- What worked:
  - external workers counted toward fulfillment
  - status became `approved`
  - confirmed workers stored: `외부A`, `외부B`
  - no self-staff bridge targets were produced
- Break point:
  - required support-roster notifications still did not complete

### Scenario 6. Mixed external + self-staff
- Result: FAIL
- What worked:
  - all valid workers counted
  - status became `approved`
  - confirmed workers stored: `홍길동`, `외부A`
  - repeat identical upload remained deterministic at the ticket/status level
- Break point:
  - no fresh UPSERT outbox row emitted for the valid self-staff subset because side effects aborted

### Scenario 7. State reversal
- Result: FAIL
- What worked:
  - same ticket stayed in place
  - latest confirmed worker snapshot replaced the old one
  - status moved `approved -> pending`
- Break point:
  - no RETRACT outbox row emitted

### Scenario 8. Multi-site HQ workbook
- Result: PASS
- Basis:
  - live workspace shows mixed readiness (`R692` ready / `R738` source_missing)
  - ARLS stale partial-continue test passed
  - valid sites proceed, stale site excluded explicitly

## Ownership Validation
- ARLS remains the visible Excel ingress owner: confirmed
- Sentrix no longer visibly owns workbook upload/download: confirmed
- Sentrix remains the support ticket/state engine: confirmed at backend core level

## Final Conclusion
- The ownership correction is mostly in the right place.
- ARLS visible Excel ownership is working.
- Sentrix Step 2B support truth restore is working.
- Final acceptance is **NOT achieved yet** because Step 3B automation is broken:
  - notifications are not reliably completed
  - fresh ARLS UPSERT / RETRACT outbox emission is not completing
  - therefore a fully clean end-to-end pass cannot be claimed
