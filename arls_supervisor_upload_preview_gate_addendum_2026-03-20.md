## ARLS Supervisor Upload Preview Gate Addendum (2026-03-20)

Authenticated `Supervisor` runtime was re-captured on `2026-03-20` specifically to close the upload-preview boundary after the previously observed password-change gate. This pass remained evidence-only and did not execute preview/apply/upload mutation.

### Fresh-session gate result

- A fresh production `Supervisor` session still landed on `#/profile`.
- The initial authenticated shell explicitly displayed the password-change gate:
  - `초기 비밀번호 변경이 필요합니다.`
  - `계속하려면 비밀번호를 먼저 변경해 주세요.`
- The same gated shell still rendered visible field shortcuts/menu items for:
  - `근무표 업로드·자동등록`
  - `Finance용 스케쥴 제출`
  - `내 비밀번호 변경`
- Captured background authenticated requests succeeded normally during this gated shell:
  - `POST /api/v1/auth/refresh` -> `200`
  - `GET /api/v1/auth/me` -> `200`
  - additional attendance/profile bootstrap requests also returned `200`

### Upload workspace / preview impact

- Because the fresh `Supervisor` session remained inside the password-change gate, this pass did not proceed into upload workspace preview execution.
- The retained result is:
  - gate still blocking: **confirmed**
  - upload workspace shell opening after a clean fresh session: **not proven in this pass**
  - upload preview usability after gate clearance: **not proven in this pass**
  - upload mutation/apply behavior: **still unproven**
- This means the upload-preview boundary remains blocked by a real authenticated runtime prerequisite rather than by missing frontend evidence alone.

### Scope statement

- This addendum updates ARLS runtime evidence only.
- This addendum does not reopen the frozen Sentrix Phase 2A baseline.
- This addendum does not reopen the frozen Sentrix Phase 2B baseline.
- This addendum must not be read as upload workspace support, upload preview support, or a broader field permission expansion.
