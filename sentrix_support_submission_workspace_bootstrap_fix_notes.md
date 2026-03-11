## Sentrix HQ Support Submission Workspace Bootstrap Fix - Pass 1

- Scope:
  - backend bootstrap only
  - target endpoint:
    - `/api/ops/support-submissions/workspace`
  - no UI redesign
  - no unrelated support ticket workflow changes

- Root cause fixed:
  - the workspace endpoint used `tenant_code` query defaulting to `apple`
  - production requests often omit `tenant_code`
  - actual tenant is `SRS_Korea`
  - ARLS bridge then returned tenant lookup failure
  - Sentrix converted that into a `502`

- Reliability changes:
  - tenant resolution now falls back to authenticated user tenant instead of hard defaulting to `apple`
  - ARLS bridge errors are normalized into structured degraded-state responses
  - no-artifact / not-ready / site-missing conditions now return `200`
  - workspace response always includes stable bootstrap fields for valid authenticated requests

- Bootstrap response now explicitly carries:
  - month
  - scope mode
  - selected site
  - artifact availability
  - artifact metadata
  - upload readiness
  - review readiness
  - disabled reasons
  - empty state
  - degraded state
  - bridge status summary

- Logging added:
  - bootstrap request month / scope / site / tenant
  - artifact lookup result
  - review aggregation result
  - exact degraded exception details

- Operational outcome:
  - frontend can distinguish:
    - not ready
    - empty
    - degraded
  - it no longer has to infer whether the endpoint is broken from a 502
