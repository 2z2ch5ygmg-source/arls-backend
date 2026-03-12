# ARLS Backend Restore - Step 4A Manual Checklist

- Trigger a Sentrix-origin UPSERT for an approved self-staff day scope and confirm a single active ARLS schedule row appears.
- Trigger the same UPSERT twice and confirm no duplicate ARLS schedule row is created.
- Trigger a Sentrix-origin RETRACT for the same ticket/employee/date/shift and confirm the active support-origin row disappears.
- Confirm a linked base/manual row survives RETRACT unchanged.
- Confirm a support-origin night row remains visible in the original work date context, not shifted to the next day.
- Confirm calendar read path shows active support-origin rows and hides retracted ones.
- Confirm schedule detail/update context can still resolve the row without stale ghost data.
- Confirm monthly export reads the same active truth and does not double-write same-shift duplicates.
- Confirm malformed bridge payloads are rejected with explicit errors instead of creating orphan rows.
