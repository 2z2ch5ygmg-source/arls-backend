# Sentrix Support-Roster Notification Gate Fix - Manual Checklist

- Apply an initial underfilled HQ roster upload for a brand-new site/date/shift scope and verify notification fires even though final state is `pending`.
- Apply an initial overfilled HQ roster upload for a brand-new scope and verify notification fires with confirmed workers visible.
- Re-upload the same pending roster with a changed worker list and verify notification fires again.
- Re-upload an identical pending roster and verify notification does not spam.
- Confirm `approved -> pending` still emits notification and bridge retract.
- Confirm `pending -> approved` still emits notification and bridge upsert.
- Confirm notification title remains `[HQ] 지원근무자 업데이트 발생`.
- Confirm recipient targeting still includes:
  - site `Vice Supervisor`
  - site `Supervisor`
  - tenant `HQ`
  - tenant `Development`
