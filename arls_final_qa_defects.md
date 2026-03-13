## ARLS Final Workflow Verification - Defects

### 1. Master account cannot see HQ technical metadata details

- Severity: Medium
- Scope: Tab B `지점별 스케쥴 업로드 확인` > Step 4 `HQ 작성본 업로드`
- Expected:
  - normal users: hidden
  - Development: visible
  - Master: visible
- Actual:
  - technical details section is shown only when `canSelectScheduleWorkflowTenant()` is true
  - this returns true only for `DEV`
  - `Master` is excluded even though requirement says `Development/Master can inspect technical details`

Evidence:
- [/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js#L9211](/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js#L9211)
- [/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js#L11302](/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js#L11302)

Impact:
- Master account cannot inspect artifact-level technical details while Development can.
- This creates a role-behavior mismatch in the final HQ workflow.

Recommended fix:
- replace `canSelectScheduleWorkflowTenant()` gating for `#scheduleSupportArtifactTechDetails`
- use a dedicated visibility rule such as:
  - `isMasterDeveloperAccount() || getNavigationRole() === 'DEV'`
  - or equivalent `canInspectScheduleArtifactTechnicalDetails()`

### No additional blocking defects found in this QA pass

- Wizard ownership: no blocking defect found
- Tab A/Tab B independence: no blocking defect found
- HQ site matrix flow: no blocking defect found
- Aggregated Step 5 preview: no blocking defect found
- Completion/reset flow: no blocking defect found
