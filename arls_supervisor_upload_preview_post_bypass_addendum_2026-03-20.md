## ARLS Supervisor Upload Preview Post-Bypass Addendum (2026-03-20)

Authenticated ARLS runtime was re-captured on `2026-03-20` after deployment of the temporary initial-password gate bypass for runtime verification. This addendum records runtime evidence only. It does not reopen the frozen Sentrix Phase 2A or Phase 2B baselines.

### Supervisor post-bypass shell

- A fresh `Supervisor` session authenticated successfully and no longer landed on the password-change gate by default.
- The initial authenticated shell opened on `#/home`.
- The initial shell did **not** display the prior gate texts:
  - `초기 비밀번호 변경이 필요합니다.`
  - `계속하려면 비밀번호를 먼저 변경해 주세요.`
- Visible navigation/menu state on the initial shell included:
  - `근무표 업로드·자동등록`
  - `Finance용 스케쥴 제출`
- `내 비밀번호 변경` was not rendered as a visible home/menu shortcut in the captured initial shell.

### Supervisor upload shell opening

- Direct hash navigation to `#/schedules/upload` now opened the upload workspace shell successfully:
  - final hash: `#/schedules/upload`
  - upload panel visible
  - no gate text shown
  - no read-only message shown
- A visible schedule-tab path also opened the upload workspace shell successfully:
  - starting point: `#/schedules/calendar`
  - action: click visible schedule tab `근무표 업로드·자동등록`
  - final hash: `#/schedules/upload`
  - upload panel visible
- The automated initial-shell menu/shortcut probes did **not** open the upload workspace in this capture:
  - final hash remained `#/home`
  - no upload requests fired
  - this capture therefore proves direct-hash and schedule-tab entry, but does not prove a stable home-shell menu/shortcut click path

### Supervisor file-stage and preview boundary

- From the opened upload workspace, the wizard advanced to file preparation without executing any mutation:
  - `STEP 3 파일 준비` visible
  - file input visible
  - `분석 시작` preview button visible
- Preview remained disabled in the captured file-stage state:
  - preview visible: `true`
  - preview enabled: `false`
  - file input visible: `true`
- No preview request was executed in this pass.
- The narrow proven statement is:
  - upload shell opening: confirmed
  - file-stage opening: confirmed
  - preview visibility: confirmed
  - preview requires file selection before any request: confirmed
  - preview execution with a real file: unproven
  - apply/upload/commit mutation: unproven

### Supervisor backend/runtime mismatch retained

- Even while the upload shell and file-stage opened in the browser, direct mapping-profile read access remained denied:
  - `GET /api/v1/schedules/import-mapping-profile?tenant_code=srs_korea` -> `403`
  - response envelope included `error.code="FORBIDDEN"` and `error.message="접근 권한이 없습니다."`
- This addendum records the mismatch exactly as observed. It does not normalize frontend shell availability and backend mapping-profile denial into a single simplified statement.

### Officer sanity check

- A fresh `Officer` session authenticated successfully.
- The initial authenticated shell also opened on `#/home` and did not show the gate texts immediately.
- However, `Officer` remained restricted on the upload route itself:
  - direct hash navigation to `#/schedules/upload` ended on `#/profile`
  - gate text reappeared on that route attempt:
    - `초기 비밀번호 변경이 필요합니다.`
    - `계속하려면 비밀번호를 먼저 변경해 주세요.`
  - upload shell did not open
  - `근무표 업로드·자동등록` remained hidden from the initial visible field shell
- Direct backend upload mapping-profile access also remained denied for `Officer`:
  - `GET /api/v1/schedules/import-mapping-profile?tenant_code=srs_korea` -> `403`
  - response envelope included `error.code="FORBIDDEN"` and `error.message="접근 권한이 없습니다."`

### Correction to the prior gate assumption

- The earlier assumption that `Officer` would be entirely unaffected by the temporary bypass is too broad.
- The narrower runtime-proven statement is:
  - `Supervisor` bypass succeeded for fresh-session entry into the upload shell boundary
  - `Officer` did not retain the old immediate-login `#/profile` gate landing in this capture
  - `Officer` still remained blocked from the upload route/shell and still re-entered the gate on direct upload-route access

### Scope statement

- This addendum updates ARLS runtime evidence only.
- This addendum does not reopen the frozen Sentrix Phase 2A baseline.
- This addendum does not reopen the frozen Sentrix Phase 2B baseline.
- This addendum must not be read as upload feature completion, preview execution proof, or broader field-permission expansion.

### Restoration reminder

- The temporary initial-password bypass must be removed after runtime verification is complete.
- In the current repo state, the retained bypass marker is implemented via `TEMP_RUNTIME_TEST_INITIAL_PASSWORD_GATE_BYPASS` in [frontend/js/app.js](/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js#L379) and consumed by [frontend/js/app.js](/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js#L46887).
- Restore normal gate behavior before treating future runtime captures as non-test operational evidence.
