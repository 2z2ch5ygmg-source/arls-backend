# Sentrix HQ Support Submission Workspace Contract

## Owner Split

- ARLS
  - owns base schedule upload
  - owns support-demand extraction/export
  - owns canonical HQ roster workbook artifact generation

- Sentrix
  - owns HQ support roster submission workspace
  - owns HQ-filled workbook upload
  - owns apply/reconcile workflow entry
  - owns support worker roster operations
  - owns self-staff validation handling
  - owns exact-filled / pending recalculation state handling
  - owns ARLS bridge trigger initiation

## Bridge Endpoints

Base:

- `ARLS /api/v1/schedules/bridge/sentrix-hq`

Auth:

- header: `X-Sentrix-Bridge-Token: <shared token>`

### 1. Workspace

- `GET /workspace`

Query:

- `tenant_code`
- `month`
- `site_code` optional
- `artifact_id` optional
- `revision` optional
- `source_upload_batch_id` optional

Returns:

- ARLS latest HQ workspace status for the target month
- selected site metadata if a site was supplied
- `artifact_context`
- `workspace_owner = sentrix_hq_support_submission`

### 2. Artifact Download

- `GET /artifact/download`

Query:

- `tenant_code`
- `month`
- `scope = all | site`
- `site_code` optional

Returns:

- canonical ARLS-generated HQ workbook artifact

### 3. Upload Inspect

- `POST /upload/inspect`

Body:

```json
{
  "tenant_code": "apple",
  "month": "2026-03",
  "site_code": "R692",
  "artifact_id": "sentrix-hq:APPLE:2026-03:R692:abcd1234",
  "revision": "abcd1234",
  "source_upload_batch_id": "",
  "file_name": "hq_roster.xlsx",
  "file_base64": "<base64>"
}
```

Returns:

- ARLS inspect result
- `batch_id`
- `can_apply`
- grouped issue payload
- `artifact_context`
  - `artifact_id`
  - `month`
  - `site`
  - `revision`
  - `source_upload_batch_id`

### 4. Apply

- `POST /upload/{batch_id}/apply`

Body:

```json
{
  "tenant_code": "apple",
  "site_code": "R692",
  "artifact_id": "sentrix-hq:APPLE:2026-03:R692:abcd1234",
  "revision": "abcd1234",
  "source_upload_batch_id": "batch-id"
}
```

Returns:

- apply result payload
- Sentrix-visible ownership marker
- preserved `artifact_context`

## Deep Link Contract

ARLS -> Sentrix target:

```text
https://security-ops-center.../#/ops/support?mode=hq-submission&month={month}&site={site_code}&artifact_id={artifact_id}&revision={revision}&source_upload_batch_id={batch_id}&tenant_code={tenant_code}
```

Rules:

- Sentrix must open the HQ submission workspace using the supplied site/month context.
- Sentrix must prefer artifact consumption over workbook regeneration.
- ARLS must not treat rename/apply ownership as local HQ submit/apply after this patch.

## Acceptance Mapping

- HQ support roster submission/apply is owned by Sentrix:
  - user entry point now exists in Sentrix
  - ARLS apply button redirects into Sentrix

- Sentrix can consume the latest ARLS-generated artifact:
  - workspace bridge exposes latest site/month artifact context
  - download bridge streams the canonical workbook

- ARLS no longer incorrectly owns the HQ roster apply workflow:
  - ARLS frontend no longer performs local apply from the HQ workspace

- ARLS and Sentrix are cleanly linked by artifact context:
  - `artifact_id`
  - `month`
  - `site`
  - `revision`
  - `source_upload_batch_id`
