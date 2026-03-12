## ARLS Backend Restore - Step 2A

### Files changed
- `/Users/mark/Desktop/rg-arls-dev/app/routers/v1/schedules.py`
- `/Users/mark/Desktop/rg-arls-dev/app/schemas.py`
- `/Users/mark/Desktop/rg-arls-dev/tests/test_schedule_monthly_import_canonical.py`

### Canonical write path
- Base monthly upload still enters through `POST /api/v1/schedules/import/{batch_id}/apply`.
- Canonical base schedule rows are still applied by `_apply_canonical_schedule_import_batch(...)`.
- Step 2A removes Sentrix ticket create/update/retract from that apply path.
- The apply path now ends at:
  - ARLS base schedule truth update
  - ARLS daytime need-count update
  - ARLS support-demand artifact/source registration

### Lineage rules enforced
- Base schedule rows remain constrained to:
  - `source = arls_monthly_base_upload`
  - `source_batch_id = source_upload_batch_id`
  - `source_revision = workbook/source revision`
- Existing manual rows and Sentrix-origin support rows are still protected from overwrite.
- Support-demand artifact lineage remains anchored by:
  - `schedule_support_roundtrip_sources.source_batch_id`
  - `schedule_support_roundtrip_sources.source_revision`
  - persisted `schedule_import_rows.payload_json` from the analyzed base workbook batch

### Support-demand extraction behavior
- Support-demand rows are now rebuilt from the analyzed import payload itself, not from Sentrix ticket rows.
- Only meaningful scopes are kept:
  - `source_block = sentrix_support_ticket`
  - non-blocking
  - valid date
  - `request_count > 0`
- The extracted scope keeps:
  - date
  - day/night kind
  - requested_count
  - purpose text
  - raw requested-count text
  - required row provenance

### Artifact generation behavior
- After successful base apply, ARLS registers/updates the site+month source in `schedule_support_roundtrip_sources`.
- The artifact revision is now computed from:
  - ARLS schedule/base truth
  - ARLS demand rows
  - support-demand scopes reconstructed from the source import batch
- HQ workbook export can now read support-demand scopes from the active ARLS source batch, instead of requiring existing Sentrix tickets.
- Apply result now reports:
  - `artifact_generated`
  - `artifact_id`
  - `artifact_revision`
  - `artifact_generated_at`
  - `support_scope_count`

### What was intentionally not changed
- No HQ support roster upload parsing changes
- No Sentrix roster/state reconciliation changes
- No frontend redesign in this step
- No Sentrix ticket creation/upsert/retract in Step 2A
- Existing support roundtrip/HQ merge tables were reused instead of introducing a new artifact table
