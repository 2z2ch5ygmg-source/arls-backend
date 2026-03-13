# Sentrix Final QA Matrix

| scenario | role/account | site | date | shift | old state | new state | confirmed workers | notification result | outbox result | PASS/FAIL |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Visible ownership cleanup | deployed asset inspection | R692 context preserved when present | n/a | n/a | legacy workbook surface existed historically | legacy route redirects to ARLS, submission workspace root removed | n/a | n/a | n/a | PASS |
| Support status UI structure | code / DOM inspection | ALL / selected site | current month | day + night | support screen at risk of workbook contamination | site filter, calendar/list/detail views intact | pending display path retained | n/a | n/a | PASS |
| Missing scope create | HQ roster ingest harness | R692 | 2026-03-15 | day | missing scope | approved | `자체 지원테스터`, `협력 외부A` | fired | side-effect band invoked; approved path covered | PASS |
| Existing scope update in place | HQ roster ingest harness | R692 | 2026-03-16 | day | approved | pending | `자체 지원테스터` retained | covered via side-effect band | same logical ticket reused; reversal bridge path covered separately | PASS |
| New pending scope with workers | HQ roster side-effect harness | R692 | 2026-03-15 | day | pending / empty workers | pending | `자체 홍길동` visible | fired | none | PASS |
| Existing pending scope with roster change | HQ roster side-effect harness | R692 | 2026-03-15 | day | pending | pending | `자체 홍길동`, `협력 외부A` visible | fired | none | PASS |
| Identical repeated pending upload | HQ roster side-effect harness | R692 | 2026-03-15 | day | pending | pending | unchanged | suppressed | none | PASS |
| Approved scope notification body generation | HQ roster side-effect harness | R692 | 2026-03-15 | day | pending | approved | label includes approved body path | fired | UPSERT emitted | PASS |
| External worker only | HQ roster side-effect harness | R692 | 2026-03-15 | day | pending | approved | `협력 외부A`, `협력 외부B` visible | fired | no bridge | PASS |
| Mixed external + self-staff | HQ roster side-effect harness | R692 | 2026-03-15 | day | pending | approved | `자체 홍길동`, `협력 외부A` visible | fired | UPSERT for self-staff subset only | PASS |
| Approved -> pending reversal | HQ roster side-effect harness | R692 | 2026-03-15 | day | approved | pending | latest confirmed-worker snapshot retained | fired | RETRACT emitted | PASS |
| Day reason enforcement | HQ roster core harness | R692 | 2026-03-17 | day | n/a | rejected at consume stage | none written | n/a | n/a | PASS |
| Night purpose preservation | HQ roster core harness | R692 | 2026-03-18 | night | missing scope | approved | `자체 지원테스터` visible | eligible on approval path | eligible on approval path | PASS |
