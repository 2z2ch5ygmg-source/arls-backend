## Sentrix HQ Support Submission Workspace Ownership Patch Notes

- Problem:
  - ARLS was still exposing HQ roster submit/apply as if ARLS owned the workflow.
  - That violated the intended split: ARLS builds the canonical support-demand workbook, Sentrix owns HQ roster submission/upload/apply/reconcile.

- Ownership change:
  - ARLS remains the canonical workbook artifact producer.
  - Sentrix now becomes the workflow owner for:
    - HQ artifact download entry
    - HQ filled workbook upload
    - inspect/apply execution entry
    - support worker roster update / self-staff validation lifecycle
    - pending recalculation / exact-filled ownership
    - ARLS bridge trigger initiation

- Implementation shape:
  - Added ARLS bridge endpoints dedicated to Sentrix HQ submission consumption.
  - Added Sentrix HQ submission workspace section inside the existing HQ support roster workspace.
  - ARLS HQ apply button no longer applies locally; it deep-links to Sentrix with artifact context.

- Artifact linkage fields preserved across the bridge:
  - `artifact_id`
  - `month`
  - `site` / `site_code`
  - `revision`
  - `source_upload_batch_id`

- Contract direction:
  - ARLS -> Sentrix:
    - exposes latest site/month artifact context
    - streams canonical workbook artifact
    - accepts Sentrix bridge inspect/apply calls through bridge endpoints
  - Sentrix:
    - owns the user-facing HQ submission workspace
    - keeps site/month/artifact context stable
    - executes inspect/apply through Sentrix-owned endpoints

- Deep link:
  - ARLS now targets Sentrix route:
    - `#/ops/support?mode=hq-submission&month=...&site=...&artifact_id=...&revision=...&source_upload_batch_id=...`

- Operational note:
  - Shared app setting required on both services:
    - `SENTRIX_SUPPORT_BRIDGE_TOKEN`
  - Sentrix service also uses:
    - `ARLS_SUPPORT_BRIDGE_BASE_URL`

- Intended result:
  - HQ roster submit/apply no longer appears as ARLS-owned workflow.
  - Sentrix consumes ARLS artifacts instead of rebuilding the workbook separately.
