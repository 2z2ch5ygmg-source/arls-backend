ARLS Backend Restore - Step 3A Manual Checklist

1. Upload an HQ-filled workbook into ARLS Step 4 and confirm inspect succeeds.
2. Confirm exact sheet-name resolution maps each sheet to the intended site.
3. Rename a sheet incorrectly but keep BC34 site text valid; confirm BC34 fallback resolves the site.
4. Upload a workbook containing a sheet for an unselected site and confirm it is excluded, not silently included.
5. Use a workbook where one selected site is stale and one is current; confirm partial continue is allowed.
6. Confirm requested_count in preview matches ARLS artifact scope, not workbook-entered request text.
7. Confirm preview rows are aggregated one row per site/date/shift.
8. Confirm worker names are joined in workbook order.
9. Confirm apply sends normalized snapshot to Sentrix and does not report full success if handoff fails.
10. Confirm failed handoff returns retryable state without requiring workbook re-upload.
