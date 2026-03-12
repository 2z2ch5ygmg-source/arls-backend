# Rollback Scope and Restructure Risk Report

Inspection date: 2026-03-11

## 1. What must be removed from Sentrix UI

Must be removed or hidden because it wrongly owns Excel workflow:
- embedded `HQ 지원 제출 워크스페이스` in `/Users/mark/Desktop/security-ops-center/static/index.html`
- Sentrix buttons:
  - `컨텍스트 새로고침`
  - `ARLS artifact 다운로드`
  - `검토`
  - `적용`
  when they are acting as the operator-facing Excel flow
- hash/deeplink mode:
  - `#/ops/support?mode=hq-submission...`
- Sentrix-visible ownership messaging that says workbook is downloaded/uploaded/applied in Sentrix

Can be removed later after ARLS replacement is live:
- `/api/ops/support-submissions/workspace`
- `/api/ops/support-submissions/download`
- `/api/ops/support-submissions/inspect`
- `/api/ops/support-submissions/{batch_id}/apply`

Why:
- These are proxy surfaces over ARLS behavior, not genuine Sentrix-owned workbook services.

## 2. What must be restored or added in ARLS UI

ARLS must visibly own:
- HQ support-demand artifact download
- HQ-filled workbook upload
- workbook inspect/review
- apply trigger for the HQ file ingress flow

Best existing ARLS pieces to restore instead of inventing new ones:
- `/schedule/reports` support submission area for artifact context and download
- `/ops/support-workers` HQ Excel workspace for upload, inspect, and apply
- existing ARLS backend HQ upload/apply endpoints

What ARLS UI should regain later:
- one single operator flow that says:
  - download from ARLS
  - upload back to ARLS
  - Sentrix remains the roster/ticket truth behind the scenes

What should not remain duplicated:
- report tab telling the user to leave ARLS for submit/apply
- support-status panel also exposing a half-ARLS half-Sentrix version of the same job

## 3. What can stay in Sentrix safely

Safe to keep in Sentrix:
- support worker status page `/ops/support`
- support request month/site/status filtering
- confirmed worker edit/save flow
- ticket state reconciliation
- support request status labels and decision logic
- APNS / broker / outbox notifications
- webhook emission back to ARLS for schedule materialization effects

These match the corrected role:
- Sentrix as support worker state engine
- Sentrix as roster truth
- Sentrix as ticket truth

## 4. What can stay in ARLS safely

Safe to keep in ARLS:
- base monthly schedule upload workspace
- blank template download
- latest base download
- schedule import preview/apply
- support-demand artifact generation
- source revision tracking
- mapping profile management
- ARLS-side materialization of valid Sentrix-approved self-staff assignments into schedule truth

Also safe to keep technically:
- ARLS HQ upload/inspect/apply parser and tables

The issue is not that these ARLS pieces are wrong.
The issue is that they were partially hidden behind Sentrix-owned UI.

## 5. What will break if ownership is changed

### User-facing breakage if no redirect plan exists

Will break immediately:
- ARLS button that opens Sentrix HQ submission workspace
- existing Sentrix bookmarks to `mode=hq-submission`
- any operator habit or documentation that says HQ uploads in Sentrix

### Technical breakage if Sentrix UI is removed first

Will block HQ workflow if ARLS replacement is not live at the same time:
- artifact download
- workbook upload
- inspect/review
- apply entry

### Hidden coupling risks

Risks:
- ARLS report tab copy and hints currently say Sentrix owns submit/apply
- ARLS support-status HQ panel currently redirects apply to Sentrix
- Sentrix and ARLS currently both represent support-ticket-like state in different tables
- bridge endpoints and deep links currently assume Sentrix is the visible owner

### Existing implementation fragility

Additional risk:
- Sentrix inspect/apply dispatch is wired in a way that already looks method-fragile.
- That means rollback should simplify ownership, not add another proxy layer.

## 6. Whether data migration or cleanup is required

### Required migration

Strict DB migration required for the UI rollback itself:
- not necessarily

Reason:
- ARLS already has the HQ workbook parser/apply storage tables
- Sentrix HQ submission UI does not appear to own durable workbook batch tables

### Cleanup strongly recommended

Recommended cleanup:
- retire or archive documentation that moved HQ workbook ownership into Sentrix
- remove stale Sentrix-only deeplink references
- collapse duplicate ARLS UI surfaces into one owner flow

### Data cleanup risk area

Most important cleanup/reconciliation question:
- ARLS local `sentrix_support_request_tickets` vs Sentrix live support `tickets`

This is not a simple UI cleanup issue.
It is a source-of-truth cleanup risk.

If ownership is corrected but this duplication remains ambiguous:
- support-demand and support-ticket lineage can still diverge
- operators may still see “same logical request, different systems” behavior

### Preview/batch tables

ARLS tables such as:
- `schedule_support_roundtrip_batches`
- `sentrix_support_hq_roster_batches`

can likely remain without destructive migration.

They may need:
- retention policy
- stale batch cleanup
- clearer distinction between legacy and current flow records

## 7. Rollback scope conclusion

What must be rolled back:
- Sentrix as the operator-facing Excel owner
- ARLS report-tab messaging that says Sentrix owns HQ submit/apply

What must be restored:
- ARLS as the visible download/upload/review/apply ingress app for HQ workbook handling

What must remain unchanged:
- Sentrix support worker state engine
- Sentrix ticket truth
- Sentrix notification flow
- ARLS schedule truth and artifact generation

Most important implementation caution:
- Do not move ownership again without also collapsing duplicated surfaces and clarifying which ticket table is canonical in this workflow.
