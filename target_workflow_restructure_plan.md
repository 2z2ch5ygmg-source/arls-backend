# Target Workflow Restructure Plan

Goal date context: analysis-only planning as of 2026-03-11

## Target ownership by operator workflow order

### 1. Supervisor base monthly schedule upload

Operator:
- Supervisor

System owner:
- ARLS

Screen owner:
- ARLS `/schedule/upload`

Actions:
- choose site/month
- download blank template or latest base
- upload base monthly schedule workbook
- run preview
- apply canonical schedule

Data ownership:
- ARLS owns base schedule truth in `monthly_schedules`
- ARLS owns upload analysis and mapping-profile logic

### 2. Support-demand extraction after base apply

System owner:
- ARLS

What happens:
- ARLS derives support-demand rows from canonical monthly schedule truth
- ARLS updates support-demand lineage and source revision
- ARLS generates the support-demand workbook artifact for the selected site/month

Where it happens:
- ARLS backend

Ownership:
- ARLS owns artifact generation
- ARLS owns artifact revision
- ARLS owns `artifact_id`/revision/site/month linkage

### 3. Support-demand ticket handoff into Sentrix

System owner:
- Sentrix for ticket truth
- ARLS for source artifact truth

Target behavior:
- ARLS must hand off support-demand context into Sentrix as support-request/ticket inputs
- Sentrix becomes the support request/ticket state engine

Important target rule:
- ARLS should not look like the final roster/ticket engine
- Sentrix should not look like the Excel ingress app

### 4. HQ support-demand workbook download

Operator:
- HQ

System owner:
- ARLS

Screen owner:
- ARLS

Recommended visible place:
- ARLS report/support submission workspace
- or ARLS support-status HQ workspace
- but only one visible owner

What happens:
- HQ opens site/month context in ARLS
- HQ downloads the latest ARLS-generated support-demand workbook artifact

Ownership:
- download ownership = ARLS
- artifact truth = ARLS

### 5. HQ fills support-worker roster in Excel

Operator:
- HQ

System owner during offline editing:
- neither app

What matters:
- the workbook remains an ARLS-issued artifact with preserved metadata

### 6. HQ uploads the completed workbook back through ARLS

Operator:
- HQ

System owner:
- ARLS

Screen owner:
- ARLS

What happens:
- upload completed workbook to ARLS
- ARLS validates metadata, month, site scope, revision freshness, and sheet shape
- ARLS builds review/inspect result

Ownership:
- upload ownership = ARLS
- workbook parser ownership = ARLS
- artifact contract validation ownership = ARLS

### 7. HQ review and apply trigger

Operator:
- HQ

Visible screen owner:
- ARLS

Processing split:
- ARLS owns preview/inspect UI and artifact validation
- Sentrix owns resulting support roster state and ticket reconciliation

Target implementation meaning:
- The operator presses review/apply in ARLS
- ARLS should submit structured roster results into Sentrix-owned state handling
- ARLS should not present Sentrix as the raw workbook UI owner

### 8. Support worker roster state reconciliation

System owner:
- Sentrix

What Sentrix owns:
- support worker roster truth
- support request ticket truth
- exact-filled / pending recalculation
- self-staff validation
- support request status updates
- operational notifications

What Sentrix should receive:
- normalized roster submission result
- stable site/month/ticket/employee context
- not necessarily the user-facing raw Excel workflow

### 9. Notifications

System owner:
- Sentrix

What happens:
- Sentrix recalculates support ticket state
- Sentrix notifies relevant users
- Sentrix emits outbound events/webhooks back to ARLS for schedule-side effects

### 10. ARLS materialization of approved self-staff assignments

System owner:
- ARLS

Trigger source:
- Sentrix-approved support roster and ticket state

What ARLS does:
- materializes only valid Sentrix-approved self-staff assignments into ARLS schedule truth
- preserves lineage to ticket/employee/site/date

What ARLS does not own here:
- support ticket decision truth
- support roster operational truth

## Ownership summary by concern

### UI ownership

ARLS should own:
- Excel download
- Excel upload
- inspect/review/apply entry for the workbook

Sentrix should own:
- support request and support worker operational workspace
- ticket and roster state screens

### Data ownership

ARLS should own:
- base monthly schedule truth
- workbook artifact truth
- artifact revision lineage
- final schedule materialization

Sentrix should own:
- support ticket truth
- support worker roster truth
- exact-filled / pending recalculation
- self-staff validation outcomes

### Upload/download ownership

ARLS:
- workbook download
- workbook upload

Sentrix:
- none as operator-facing Excel ingress owner

### Source-of-truth ownership

ARLS:
- schedule truth
- artifact truth

Sentrix:
- support roster truth
- support ticket truth

## Recommended end-state principle

The corrected workflow should read like this:

1. Supervisor uploads base schedule in ARLS.
2. ARLS creates canonical schedule truth and support-demand artifact.
3. HQ downloads the artifact from ARLS.
4. HQ uploads the completed workbook back to ARLS.
5. ARLS validates and submits normalized roster intent into Sentrix.
6. Sentrix recalculates roster/ticket state and notifies operators.
7. ARLS materializes only Sentrix-approved self-staff assignments into final schedule truth.

That structure restores:
- ARLS as Excel ingress app
- Sentrix as support-worker state engine
- a cleaner separation between artifact handling and ticket/roster truth
