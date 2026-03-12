ARLS HQ Roster Ingress Contract

Site resolution rules
- Primary: exact sheet name -> selected workspace site
- Fallback: BC34 workbook text -> selected workspace site
- If neither resolves, the sheet is blocking and excluded.
- If a sheet resolves to an unselected site, it is explicitly excluded.

BC34 fallback rule
- BC34 text is read as workbook fallback identity text.
- Exact match is preferred.
- Contained-name match is allowed only when it resolves to a single unique workspace site.

Partial stale handling rule
- Stale is evaluated per selected site.
- Stale sites are excluded from apply.
- Valid sites continue through inspect/apply.
- Inspect result returns:
  - processed_site_count
  - stale_site_count
  - excluded_site_count
  - processed_sites
  - excluded_sites

Normalized support roster entry schema
- scope_key
- sheet_name
- site_id
- site_code
- site_name
- work_date
- shift_kind
- slot_index
- artifact_source_batch_id
- artifact_source_revision
- request_count
- raw_cell_text
- parsed_display_value
- source_row
- source_col
- source_cell_ref
- self_staff
- affiliation
- worker_name
- worker_type
- employee_id
- employee_code
- employee_name
- countable
- issue_code
- issue_message

Aggregated preview row schema
- 시트명
- 지점
- 날짜
- 구분
- 요청인원수
- 입력인원수
- 근무자명
- Ticket상태
- 사유

Apply result schema
- batch_id
- applied
- partial_success
- blocked
- blocked_reasons
- artifact_id
- retry_token
- handoff_status
- handoff_message
- handoff_success_count
- handoff_failed_count
- affected_scope_count
- excluded_scope_count
- processed_site_codes
- excluded_site_codes
- stale_site_codes
- affected_dates
- scope_results
