# ARLS Functional Restore Pass 2 Notes

## Files Changed
- `/Users/mark/Desktop/rg-arls-dev/frontend/index.html`
- `/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js`
- `/Users/mark/Desktop/rg-arls-dev/arls_functional_restore_pass2_notes.md`
- `/Users/mark/Desktop/rg-arls-dev/arls_functional_restore_pass2_manual_checklist.md`
- `/Users/mark/Desktop/rg-arls-dev/arls_excel_ingress_contract.md`
- `/Users/mark/Desktop/rg-arls-dev/arls_to_sentrix_roster_handoff_contract.md`

## Restored Workflow Ownership
- `Excel로 근무표 간편 제작` STEP 4가 이제 실제 HQ 지원근무자 반영 업로드의 주 workflow owner가 된다.
- ARLS 안에서 HQ 작성본 workbook을 업로드하고, inspect/review/apply를 끝까지 진행할 수 있게 복구했다.
- apply는 Sentrix UI로 이동시키지 않고 ARLS에서 바로 실행되며, 내부적으로 Sentrix roster/ticket 엔진으로 handoff된다.

## Removed Or Demoted Wrong Flows
- STEP 4의 기존 `Sentrix에서 지원근무자 제출 열기` 주 workflow를 secondary shortcut으로 강등했다.
- STEP 3 status card의 문구를 `Sentrix handoff` 중심에서 `ARLS STEP 4 다음 단계` 중심으로 정리했다.
- 보고 탭은 Pass 1에서 demote한 shortcut 역할을 유지하고, 이번 패스에서는 다시 main owner로 올라오지 않게 유지했다.

## How HQ Support Roster Upload Now Works In ARLS
1. STEP 3에서 source artifact를 만든다.
2. STEP 4에서 HQ 작성본 workbook을 업로드한다.
3. ARLS가 `/schedules/support-roundtrip/hq-roster-upload/inspect`로 workbook을 검토한다.
4. 사용자는 issue groups, review rows, scope summary를 ARLS 안에서 확인한다.
5. `ARLS에서 적용`을 누르면 `/schedules/support-roundtrip/hq-roster-upload/{batch_id}/apply`를 호출한다.
6. backend가 normalized roster snapshot을 Sentrix state engine 경로로 반영하고, 결과를 ARLS UI에 되돌린다.

## Sentrix Handoff
- ARLS는 user-facing ingress owner다.
- Sentrix는 여전히 roster truth, exact-filled/pending 판정, notification, bridge 후처리를 소유한다.
- apply 결과에는 ticket update, auto-approved/pending count, notification, bridge count가 그대로 보인다.
- handoff 실패나 blocked 상태는 ARLS apply 결과에서 그대로 보여주고 retry 가능 상태를 남긴다.

## Mapping Profile Attachment
- Pass 1에서 옮긴 mapping profile ownership은 유지된다.
- 기본 월간 근무표 업로드 전 readiness를 같은 Excel workflow 안에서 확인할 수 있다.
- 이번 패스에서는 support roster mode에 base mapping logic를 섞지 않았다.

## What Was Intentionally Not Changed
- Sentrix UI 자체는 수정하지 않았다.
- support ticket/state truth를 ARLS로 다시 옮기지 않았다.
- report tab를 다시 main workflow owner로 올리지 않았다.
- base monthly upload parser/apply business logic는 건드리지 않았다.
