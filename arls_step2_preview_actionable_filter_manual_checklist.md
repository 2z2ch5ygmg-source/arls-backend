# ARLS Step 2 Preview Actionable Filter Manual Checklist

## Default mode
- Open `Excel로 근무표 간편 제작` Step 2 preview.
- Verify the default selected mode is `기본 보기`.
- Verify `반영 예정` rows are not shown by default.

## Protected support rows hidden
- Use a workbook that contains support metadata changes.
- Verify rows such as `주간 지원 근무자`, `야간 지원 근무자`, `작업 목적`, `외부인원 투입 수`, summary counts are not shown in the main preview table by default.
- Verify the grouped issue panel still retains awareness of those rows.

## Actionable base rows kept
- Use a workbook with a real base schedule blocking issue.
- Verify the body row still appears in the main preview table.
- Verify red blocking rows remain visible.

## Review rows kept
- Use a workbook with a true actionable non-blocking review row on a base schedule body cell.
- Verify the row remains visible in `기본 보기`.

## Toggle behavior
- Switch to `전체 보기`.
- Verify previously hidden non-actionable/protected info rows become visible.
- Switch back to `기본 보기`.
- Verify the table returns to actionable-only filtering.

## Empty actionable state
- Use a workbook with only `반영 예정` or protected informational rows.
- Verify the preview table shows the compact actionable-only empty message instead of flooding the table.
