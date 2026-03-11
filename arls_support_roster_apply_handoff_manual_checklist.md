# ARLS HQ Support Roster Apply -> Sentrix Handoff Manual Checklist

1. Open `ARLS > 스케쥴 > 근무일정 > Excel로 근무표 간편 제작 > HQ 지원근무자 반영 업로드`.
2. Choose a month/site scope with an existing support-demand artifact.
3. Upload an HQ-filled workbook and run `검토 시작`.
4. Confirm the review table still renders parsed worker rows and scope summaries.
5. Click `ARLS에서 적용`.
6. Verify one of these result modes is shown explicitly:
   - `적용 완료`
   - `부분 적용`
   - `적용 차단`
   - `전달 실패`
7. On full success, confirm the result area shows:
   - handoff scope count
   - updated ticket count
   - auto-approved count
   - pending count
8. On partial success, confirm the result area shows:
   - success count
   - failed count
   - retry token
9. Open Sentrix support worker status and verify confirmed workers/status changed for the affected scopes.
10. Re-run apply for the same failed/partial batch and confirm re-upload is not required.
11. Confirm blocked review states still prevent handoff.
12. Confirm per-scope apply detail rows show Sentrix handoff status and ticket id where available.
