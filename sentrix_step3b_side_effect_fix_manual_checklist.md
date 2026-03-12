# Sentrix Support-Roster Side-Effect Band Fix - Manual Checklist

- Trigger ARLS HQ roster apply for one exact-filled support scope and confirm Sentrix no longer throws `NameError: get_ticket_status_label`.
- Verify Sentrix audit contains `SUPPORT_ROSTER_NOTIFY` for the applied ticket scope.
- Verify Sentrix audit contains `SUPPORT_ROSTER_BRIDGE_UPSERT` for an approved self-staff scope.
- Trigger a pending scope with prior approved self-staff and verify `SUPPORT_ROSTER_BRIDGE_RETRACT`.
- Force a notification-body failure in a local/dev harness and confirm `SUPPORT_ROSTER_SIDE_EFFECT_FAILED` logs:
  - ticket_id
  - site/date/shift
  - old/new state
  - source_upload_batch_id
- Confirm `integration_outbox` still receives ARLS bridge events when the notification stage fails.
- Confirm confirmed workers remain persisted and visible after the side-effect run.
- Confirm Step 2B ticket/request_count/status behavior remains unchanged after this patch.
