## Manual Checklist

1. Open Sentrix as HQ user.
2. Call:
   - `/api/ops/support-submissions/workspace?month=2026-03`
3. Confirm HTTP status is `200`.
4. Confirm JSON contains:
   - `month`
   - `scope_mode`
   - `selected_site`
   - `artifact_available`
   - `artifact_metadata`
   - `upload_readiness`
   - `review_readiness`
   - `empty_state`
   - `degraded_state`
   - `action_state`
5. Confirm request without explicit `tenant_code` resolves to authenticated tenant.
6. Confirm no-artifact month returns:
   - `200`
   - `artifact_available=false`
   - non-empty `empty_state.reason`
7. Confirm valid month with no submission data returns:
   - `200`
   - `review_state.is_empty=true`
   - `review_readiness.ready=false`
8. Confirm invalid month still returns `400`.
9. Confirm degraded dependency path returns:
   - `200`
   - `degraded_state.is_degraded=true`
   - non-empty `degraded_state.reason`
10. Confirm logs include:
    - month
    - scope
    - site
    - artifact lookup result
    - review aggregation result
    - exact degraded exception
