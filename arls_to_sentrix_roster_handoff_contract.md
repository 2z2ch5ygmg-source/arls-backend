# ARLS To Sentrix Roster Handoff Contract

## Normalized Support Roster Snapshot
- source: HQ-filled support roster workbook uploaded through ARLS STEP 4
- inspect endpoint: `/schedules/support-roundtrip/hq-roster-upload/inspect`
- apply endpoint: `/schedules/support-roundtrip/hq-roster-upload/{batch_id}/apply`

## Snapshot Schema Expectations
- artifact lineage:
  - `artifact_id`
  - `revision`
  - `month`
  - `site_code` or `ALL`
- upload lineage:
  - `batch_id`
  - file name
  - workbook family
  - template version
- review rows preserve:
  - `sheet_name`
  - `site_code`
  - `work_date`
  - `shift_kind`
  - `slot_index`
  - `raw_cell_text`
  - `parsed_display_value`
  - `ticket_id`
  - `request_count`
  - `valid_filled_count`
  - `target_status`
  - `issue_code`
  - `reason`

## Artifact / Revision / Upload Batch Usage
- ARLS uses the active source artifact/revision from STEP 3 as the lineage anchor.
- HQ roster inspect persists a review batch id.
- HQ roster apply uses that batch id as the deterministic handoff basis.
- site revision freshness is validated before apply so stale uploads do not apply silently.

## ARLS Apply -> Sentrix Handoff Rules
- apply is initiated by ARLS UI
- ARLS does not finalize ticket truth itself
- backend apply writes the normalized roster snapshot into the Sentrix support roster domain path
- Sentrix-side logic then performs:
  - replace snapshot handling
  - ticket update-in-place
  - exact-filled / pending recalculation
  - notification
  - ARLS bridge queueing

## Success / Failure Handling
- success:
  - apply result shows ticket updates, auto-approved count, pending count, notification count, bridge count
- blocked:
  - blocked reasons are returned and kept visible in ARLS
- failure:
  - ARLS does not pretend full success
  - error stays visible in ARLS
  - operator can retry from the same ARLS workflow

## Retry Rules
- inspect can be rerun with the same file/context
- apply can be retried when the batch remains valid
- stale source revision blocks apply and forces re-inspect

## What ARLS Intentionally Does Not Decide
- final support roster truth ownership
- final support ticket state ownership
- notification policy execution
- support-origin ARLS bridge policy decisions
