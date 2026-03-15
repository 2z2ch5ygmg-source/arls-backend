# Monthly Blank Form Export Manual Test Checklist

## Single Site Download
- Open `스케쥴 > 근무표 업로드·자동등록`.
- Select tenant, site, and month.
- Click `빈 양식 다운로드`.
- Verify filename is `monthly_schedule_<site>_<YYYY-MM>.xlsx`.

## Header Autofill
- Open the visible sheet.
- Verify left top shows:
  - `YYYY년 M월`
  - `현장명  <selected site name>`
  - `현장주소` with the selected site address
- Verify row `2` shows the selected month’s dates across active day columns.
- Verify row `3` shows weekday labels for those dates.
- Verify row `4` shows holiday names where applicable.

## Holiday Styling
- Pick a month with a known holiday.
- Verify the holiday column header text is visibly red across rows `2~4`.
- Verify non-holiday columns keep normal styling.

## Short Month
- Download for February and verify:
  - day `28` or `29` is the last populated header
  - remaining columns after month end are blank in rows `2~4`
  - no stray holiday/weekday/date text remains

## Site-Dependent Data
- Download the same month for two different sites.
- Verify the year/month is the same.
- Verify site name and site address differ correctly by selected site.

## HQ ALL Workbook
- Request blank template with `site_code=ALL`.
- Verify a single workbook is returned.
- Verify one visible site sheet exists per site.
- Verify every site sheet has its own year/month, site name, address, dates, weekdays, and holiday names.

## Hidden Sheet Repair
- Open the hidden helper sheet if needed.
- Verify the delivered workbook does not contain `#REF!` in the repaired date anchor cell.

## Formatting Preservation
- Verify the delivered workbook keeps:
  - merged cells
  - print area
  - page setup
  - row heights
  - column widths
  - general sheet layout
