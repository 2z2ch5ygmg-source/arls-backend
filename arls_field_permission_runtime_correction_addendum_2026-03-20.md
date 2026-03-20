## ARLS Field-Permission Runtime Correction Addendum (2026-03-20)

Authenticated ARLS runtime was captured on `2026-03-20` with fresh production `Supervisor` and `Officer` sessions. This addendum records post-change field-permission evidence for the ARLS schedule workspaces only. It does not reopen the frozen Sentrix Phase 2A or Phase 2B baselines.

### Supervisor

- Initial authenticated shell exposed `근무표 업로드·자동등록` and `Finance용 스케쥴 제출` in visible navigation/menu text.
- Direct navigation to `#/schedules/upload` succeeded:
  - final hash remained `#/schedules/upload`
  - upload workspace shell opened
  - related data requests succeeded:
    - `GET /api/v1/schedules/import-mapping-profile?tenant_code=srs_korea` -> `200`
    - `GET /api/v1/sites?page=1&page_size=500` -> `200`
    - `GET /api/v1/sites?limit=500&offset=0` -> `200`
- Upload click-path access also succeeded:
  - upload tab button was visible/clickable
  - final hash remained `#/schedules/upload`
  - workspace shell stayed open
  - related read-side requests succeeded:
    - `GET /api/v1/schedules/monthly-board-lite?...` -> `200`
    - `GET /api/v1/leaves?...employee_code=R738-1` -> `200`
- The captured Supervisor upload path proves shell access plus read-side data access. It does not prove upload preview/apply mutation success.
- Direct navigation to `#/schedules/reports` did not open a finance workspace shell:
  - final hash remained `#/schedules/reports`
  - finance panel stayed closed
  - the captured UI remained on the upload workspace shell
  - no finance-specific network requests fired from that direct route attempt
- The finance tab button was still hidden in the captured schedule tab strip, and click-based entry into the finance workspace was not available from the visible UI.
- Despite that shell mismatch, a direct backend finance probe succeeded for Supervisor:
  - `GET /api/v1/schedules/finance-submission/status?month=2026-03&site_code=R738&tenant_code=srs_korea` -> `200`
  - response envelope returned `success=true` with finance state/readiness fields including `state`, `current_revision`, `review_download_ready`, `final_download_enabled`, `final_upload_stale`, and `blocked_reasons`
- This means Supervisor finance behavior is not “fully blocked”; the narrower proven statement is:
  - shell/menu exposure changed enough that finance text is visible in the wider navigation
  - backend finance read/status access is reachable
  - finance workspace shell opening was not proven in this capture
  - finance submit/upload mutation actions were not exercised

### Officer

- Initial authenticated shell did not expose `근무표 업로드·자동등록` or `Finance용 스케쥴 제출` in visible navigation/menu text.
- Schedule workspace showed the read-only message:
  - `읽기 전용: 스케줄 조회/내보내기만 가능합니다.`
- Direct navigation to `#/schedules/upload` did not open the upload workspace:
  - final hash resolved to `#/schedules/calendar`
  - upload panel stayed closed
  - only calendar/read-side requests were observed
- Upload tab button was not visible/clickable.
- Direct backend upload probe was denied:
  - `GET /api/v1/schedules/import-mapping-profile?tenant_code=srs_korea` -> `403`
  - response envelope: `success=false`, `error.code="FORBIDDEN"`, `error.message="접근 권한이 없습니다."`
- Direct navigation to `#/schedules/reports` did not open a finance workspace shell:
  - final hash remained `#/schedules/reports`
  - UI stayed on the read-only calendar shell
  - finance panel stayed closed
  - only calendar/read-side requests were observed
- Finance tab button was not visible/clickable.
- Direct backend finance probe was denied:
  - `GET /api/v1/schedules/finance-submission/status?month=2026-03&site_code=R738&tenant_code=srs_korea` -> `403`
  - response envelope: `success=false`, `error.code="FORBIDDEN"`, `error.message="접근 권한이 없습니다."`

### Correction To Previously Retained Assumptions

- The previously retained assumption that both field roles were uniformly restricted on these ARLS tabs is stale.
- The previously retained assumption that `Supervisor` could not access the upload/auto-registration workspace is stale.
- The previously retained assumption that `Supervisor` finance submission was simply blocked is too broad. The corrected statement is:
  - Supervisor finance backend read/status access is proven
  - Supervisor finance workspace shell opening is not proven by this capture
  - Supervisor finance submit/upload mutation behavior remains unverified
- The retained restriction for `Officer` remains supported by runtime evidence for both captured surfaces.

### Scope Statement

- This addendum is runtime correction evidence for ARLS field permissions only.
- This addendum does not reopen the frozen Sentrix Phase 2A baseline.
- This addendum does not reopen the frozen Sentrix Phase 2B baseline.
- This addendum must not be read as broad field feature support or as a universal ARLS permission matrix.
