## ARLS Backend Restore - Step 2A Manual Checklist

### Safety / ownership
- Confirm `POST /api/v1/schedules/import/{batch_id}/apply` no longer creates or retracts Sentrix support tickets.
- Confirm base apply still succeeds for a valid canonical workbook batch.
- Confirm manual lineage rows are untouched.
- Confirm Sentrix support-origin rows are untouched.

### Base apply
- Upload a valid monthly base workbook.
- Run Step 2 apply.
- Verify ARLS base schedule rows are created/updated/removed only inside the selected site+month scope.
- Verify annual leave / off / holiday semantics remain intact after apply.

### Artifact generation
- After apply, verify result payload includes:
  - `artifact_generated`
  - `artifact_id`
  - `artifact_revision`
  - `artifact_generated_at`
  - `support_scope_count`
- Verify `artifact_generated=true` only when source registration succeeded.
- Verify `support_scope_count` matches the number of meaningful demand scopes in the workbook.

### Failure handling
- Force source registration failure and confirm:
  - base apply remains committed
  - result becomes partial failure
  - no false full success is reported
- Confirm retry can be performed from persisted source/import lineage without re-parsing through Sentrix.

### HQ exportability
- After a successful base apply, open the HQ support-demand download path.
- Verify HQ workbook export succeeds even when no Sentrix support tickets exist yet.
- Verify day/night request scopes in the generated workbook match the just-applied base workbook demand rows.

### Regression checks
- Verify old Sentrix-backed export still works if an active source batch is unavailable.
- Verify preview/apply stale checks still block when current revision changed.
