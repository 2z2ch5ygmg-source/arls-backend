# Workspace Response Contract

Endpoint:

- `GET /api/ops/support-submissions/workspace?month=YYYY-MM[&site_code=R692][&tenant_code=SRS_Korea]`

Success:

- always `200` for valid authenticated requests, including no-data / not-ready / degraded workspace states

Minimum contract:

```json
{
  "ok": true,
  "month": "2026-03",
  "scope_mode": "all",
  "selected_site": {
    "site_code": "",
    "site_name": "",
    "site_id": "",
    "selected": false
  },
  "tenant_code": "srs_korea",
  "artifact_available": false,
  "artifact_metadata": {
    "artifact_id": "",
    "month": "2026-03",
    "site_code": "",
    "revision": "",
    "source_upload_batch_id": "",
    "workbook_family": "",
    "template_version": "",
    "latest_status": "unknown"
  },
  "upload_readiness": {
    "ready": false,
    "status": "not_ready",
    "disabled_reasons": []
  },
  "review_readiness": {
    "ready": false,
    "status": "empty",
    "disabled_reasons": []
  },
  "review_state": {
    "status": "empty",
    "is_empty": true,
    "has_submission_data": false,
    "batch_id": "",
    "issue_count": 0,
    "can_apply": false,
    "items": []
  },
  "empty_state": {
    "is_empty": true,
    "reason": "human-readable reason"
  },
  "degraded_state": {
    "is_degraded": false,
    "reason": "",
    "code": ""
  },
  "action_state": {
    "can_download_artifact": false,
    "can_upload_workbook": false,
    "can_review_submission": false,
    "can_apply_submission": false,
    "disabled_reasons": []
  },
  "site_options": [],
  "workspace_owner": "sentrix_hq_support_submission",
  "bridge_status": {
    "connected": true,
    "degraded": false,
    "artifact_lookup_result": "not_ready",
    "review_aggregation_result": "empty"
  }
}
```

State rules:

- `artifact_available=false`
  - no canonical ARLS artifact yet
  - or selected site artifact not ready
  - or lookup degraded

- `empty_state.is_empty=true`
  - no submission/review data yet
  - or no artifact yet

- `degraded_state.is_degraded=true`
  - dependency partially failed
  - endpoint still returned structured JSON

- `action_state.disabled_reasons`
  - must explain why download/upload/review/apply is unavailable
