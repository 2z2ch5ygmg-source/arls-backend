# ARLS ↔ Sentrix Artifact Handoff Contract Analysis

Inspection date: 2026-03-11  
Codebases inspected:
- `/Users/mark/Desktop/rg-arls-dev`
- `/Users/mark/Desktop/security-ops-center`

## 1. What ARLS currently sends to Sentrix

### A. Operator deeplink context

ARLS currently opens Sentrix with:
- `month`
- `site`
- `artifact_id`
- `revision`
- `source_upload_batch_id`
- `tenant_code`

Builder:
- `/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js`
- `buildSentrixHqSupportSubmissionUrl`

Current target:
- `https://security-ops-center.../#/ops/support?...`

Meaning:
- ARLS sends the operator to Sentrix as if Sentrix owns the HQ Excel workspace.

### B. Pull-based bridge data exposed for Sentrix

ARLS bridge endpoints:
- `GET /api/v1/schedules/bridge/sentrix-hq/workspace`
- `GET /api/v1/schedules/bridge/sentrix-hq/artifact/download`
- `POST /api/v1/schedules/bridge/sentrix-hq/upload/inspect`
- `POST /api/v1/schedules/bridge/sentrix-hq/upload/{batch_id}/apply`

Bridge payload shape already includes:
- `artifact_id`
- `month`
- `site`
- `site_code`
- `revision`
- `source_upload_batch_id`

Bridge response also includes:
- `workspace_owner = sentrix_hq_support_submission`
- `bridge_source = arls_support_roundtrip`
- selected site context

Meaning:
- ARLS is already the real artifact provider and workbook processor.
- Sentrix is only consuming ARLS through a bridge.

### C. What ARLS does not appear to send directly

Not found in the current Excel workflow:
- a direct ARLS runtime API call that creates or updates live support request tickets inside Sentrix during base monthly import apply

What ARLS does instead:
- writes local ARLS table `sentrix_support_request_tickets`
- logs integration events such as:
  - `SENTRIX_SUPPORT_REQUEST_CREATED`
  - `SENTRIX_SUPPORT_REQUEST_UPDATED`
  - `SENTRIX_SUPPORT_REQUEST_RETRACTED`

This is a major ownership warning.

## 2. What Sentrix currently sends to ARLS

### A. Signed operational webhook events

Sentrix posts to ARLS:
- `/api/v1/integrations/soc/events`

Sentrix sender implementation:
- `/Users/mark/Desktop/security-ops-center/app.py`
- `_send_hr_webhook`
- `enqueue_hr_approval_outbox_event`

ARLS receiver implementation:
- `/Users/mark/Desktop/rg-arls-dev/app/routers/v1/integrations.py`
- `POST /integrations/soc/events`
- `_apply_soc_event`
- `_apply_support_assignment_for_ticket`

What these events drive:
- support assignment materialization in ARLS
- leave / overnight / OT related schedule sync
- final self-staff materialization behavior

### B. Sentrix HQ workspace does not own parsing itself

Even when Sentrix appears to own the HQ workbook UI:
- Sentrix `download` calls ARLS bridge
- Sentrix `inspect` calls ARLS bridge
- Sentrix `apply` calls ARLS bridge

So the current Sentrix->ARLS interaction has two very different shapes:
- webhook push for support/ticket operational state
- synchronous bridge proxy for Excel workflow

That mixed pattern is one reason ownership is confusing today.

## 3. Existing artifact linkage fields

### Present in bridge responses

Already present:
- `artifact_id`
- `month`
- `site`
- `site_code`
- `revision`
- `source_upload_batch_id`

### Present in hidden workbook metadata

Also already present in workbook metadata:
- `tenant_code`
- `month`
- `download_scope`
- `workbook_family`
- `template_version`
- `bundle_revision`
- `site_codes_json`
- `site_revision_map_json`
- `selected_site_code`
- `selected_site_name`

### Present in ARLS roundtrip lineage

Stored in ARLS tables:
- `schedule_support_roundtrip_sources.source_batch_id`
- `schedule_support_roundtrip_sources.source_revision`
- `schedule_support_roundtrip_sources.latest_hq_batch_id`
- `schedule_support_roundtrip_sources.latest_hq_revision`
- `schedule_support_roundtrip_sources.latest_merged_revision`

## 4. Which fields are missing or weak for a clean handoff

Missing or weak:
- `site_id` is not consistently surfaced in the visible cross-app artifact context
- there is no clearly enforced `workflow_owner` field aligned to the corrected business rule
- there is no single proven shared support ticket id between:
  - ARLS local `sentrix_support_request_tickets`
  - Sentrix live `tickets`
- bridge contract is artifact-rich, but the webhook contract is ticket/event-rich; they are not unified into one clear handoff model
- legacy ARLS `/support-roundtrip/hq-upload/*` contract is less aligned to the newer `artifact_context` shape

Most important missing guarantee:
- a canonical end-to-end identifier proving that the ARLS support-demand row and Sentrix support ticket are the same logical entity

## 5. Current source-of-truth boundaries in code

### ARLS current truth

ARLS is clearly the source of truth for:
- supervisor base monthly schedule import
- canonical monthly schedule export
- schedule revision generation
- support-demand workbook artifact generation
- schedule truth in `monthly_schedules`
- ARLS-side materialization records
- mapping profile and import analysis

ARLS is also currently storing:
- local `sentrix_support_request_tickets`
- local HQ roster preview/apply tables
- bridge action queues

### Sentrix current truth

Sentrix is clearly the source of truth for:
- support request ticket workflow in its own app
- confirmed worker state
- support request statuses
- operational roster/ticket reconciliation
- APNS and in-app notifications
- outbound support-state webhook events to ARLS

### Boundary that should exist but is blurred

Intended clean boundary:
- ARLS owns Excel ingress and artifact handling
- Sentrix owns support roster state and ticket state

Current blurred boundary:
- Sentrix owns the visible Excel UI
- ARLS owns the real Excel parser/apply engine
- ARLS also stores a local ticket-like table called `sentrix_support_request_tickets`

## 6. Places where ownership is currently confused

### Confusion point 1: visible UI owner vs real processing owner

Visible owner today:
- Sentrix

Real processing owner today:
- ARLS

### Confusion point 2: support ticket truth duplication

ARLS local table:
- `sentrix_support_request_tickets`

Sentrix actual engine:
- `tickets` plus `tickets_template_fields`

Risk:
- two systems can appear to own the same support-demand concept

### Confusion point 3: parallel materialization paths

Current ARLS materialization can be driven by:
- ARLS-native HQ upload/apply flow
- Sentrix bridge batch apply flow inside ARLS
- Sentrix webhook events to `/integrations/soc/events`

That means ownership is not only duplicated in UI.
It is duplicated in post-upload effect paths too.

## 7. Contract conclusion

What already exists and is reusable:
- artifact_id/month/site/revision/source_upload_batch_id
- workbook metadata for scope and revision
- Sentrix outbound webhook to ARLS for final operational effects

What is not clean yet:
- a single workflow owner
- a single ticket identity across both apps in this Excel path
- a single operator entry point

Rollback/restructure implication:
- ARLS can resume Excel download/upload ownership using the existing artifact contract.
- Sentrix should remain the ticket/roster truth engine behind that handoff, not the raw workbook UI owner.
