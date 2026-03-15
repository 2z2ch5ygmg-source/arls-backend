# Monthly Blank Form Export Notes

## Files Changed
- `/Users/mark/Desktop/rg-arls-dev/app/routers/v1/schedules.py`
- `/Users/mark/Desktop/rg-arls-dev/tests/test_schedule_blank_template_export.py`

## Template Sheets Used
- Visible monthly schedule sheet: `본사 스케쥴 양식`
- Hidden helper sheet: `출동.잔업 초과수당(2)`

## Header Mapping
- Left top:
  - `B1:C1` -> `YYYY년 M월`
  - `B2:C2` -> `현장명  <site_name>`
  - `B3:C4` -> `현장주소` + line break + `<site_address>`
- Day columns:
  - active day range starts at column `D` and ends at `AH`
  - row `2` -> actual date values for the selected month
  - row `3` -> weekday labels (`월/화/수/목/금/토/일`)
  - row `4` -> public holiday name if the date is a holiday, otherwise blank

## Holiday Coloring Rule
- Holiday names are loaded dynamically from the Korea public holiday feed used at runtime.
- Holiday columns keep the template layout and apply red font coloring across rows `2~4`.
- Non-holiday columns keep the base template styling.

## HQ 전체 Multi-Sheet Rule
- If `site_code=ALL` is requested, one workbook is generated.
- One visible site sheet is created per site in the target tenant.
- Each site sheet is prepared from the monthly schedule template and receives its own:
  - year/month header
  - site name
  - site address
  - day/date headers
  - weekday headers
  - holiday names

## Short Month Handling
- 28/29/30/31-day months are handled from the selected `YYYY-MM`.
- Columns after the last day of the month are cleared in rows `2~4`.
- No extra date/weekday/holiday text remains in unused columns.

## Broken Template References Fixed
- The hidden helper sheet shipped with `B3 = #REF!`.
- Blank export now repairs that dependency by writing the selected month’s first date into the hidden sheet before delivery.
- Delivered blank workbooks no longer contain that broken reference in the hidden helper sheet.

## What Was Intentionally Not Changed
- Full monthly schedule export layout and populated export workbook generation were left unchanged.
- Frontend site selector behavior was not redesigned in this pass.
- Existing template styling, merged cells, widths, heights, print setup, and visible sheet structure were preserved as-is.
