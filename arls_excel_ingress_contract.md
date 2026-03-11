# ARLS Excel Ingress Contract

## Primary Visible Owner
- primary owner workspace: `ARLS > 스케쥴 > 근무일정 > Excel로 근무표 간편 제작`

## Upload Modes
- `기본 월간 근무표 업로드`
  - workbook upload
  - analyze
  - preview
  - apply to ARLS base schedule truth
- `HQ 지원근무자 반영 업로드`
  - workbook upload
  - inspect
  - review
  - apply from ARLS
  - Sentrix state engine handoff internally

## Visible Ownership Rules
- ARLS owns the user-facing workbook ingress.
- Sentrix does not remain the required user-facing workbook processor.
- Sentrix still owns support ticket/state/notification/bridge truth internally.

## Inspect / Review / Apply Responsibilities
- ARLS inspect:
  - parses HQ-filled workbook
  - shows grouped issues
  - shows row-level review
  - determines whether apply can start
- ARLS apply:
  - submits normalized roster snapshot to the internal Sentrix support roster engine path
  - shows success/blocked/partial-failure result
- Sentrix logic kept internal:
  - exact-filled / underfilled / overfilled
  - ticket state update
  - notification
  - ARLS bridge decisions

## Report Tab Role After Correction
- report tab is export/shortcut only
- HQ 제출용 추출 shortcut may remain
- full HQ roster upload/review/apply ownership does not live in report tab

## Mapping Profile Functional Location
- mapping profile readiness is part of the Excel workflow owner workspace
- users do not need to bounce through a separate template-management owner screen to understand upload readiness

## ARLS Owns vs Sentrix Owns
- ARLS owns:
  - base workbook ingress
  - support-demand artifact export
  - HQ-filled roster workbook ingress
  - inspect / review / apply entrypoint
  - schedule truth for base upload
- Sentrix owns:
  - support roster truth
  - support ticket truth
  - approval/pending state engine
  - notification
  - bridge/materialization decisions
