# ARLS Support-Origin Read Path Contract

## Calendar read rule
- Calendar reads `monthly_schedules` active truth.
- Active support-origin rows appear.
- Retracted support-origin rows disappear because owned rows are removed and linked rows are not duplicated.

## Detail modal read rule
- Detail/update context resolves the same `monthly_schedules` row used by calendar.
- Support-origin lineage metadata remains readable through schedule context fields.
- Retracted ghost rows must not appear.

## Export read rule
- Monthly export reads the same active `monthly_schedules` truth used by calendar.
- Active support-origin rows can affect export.
- Retracted support-origin rows do not export.

## Active vs retracted rule
- `owned_schedule` materializations become active through a real `monthly_schedules` row.
- RETRACT removes or deactivates that row from active truth.
- `linked_existing_schedule` never creates a second visible row.

## Duplicate suppression rule
- No duplicate visible row for same employee/date/shift from the same Sentrix ticket.
- No second visible same-shift row when a base/manual row already occupies that slot.
