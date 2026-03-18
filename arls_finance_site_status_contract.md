# ARLS Finance Site Status Contract

## 1. HQ Workspace Route
- Route: `GET /api/v1/schedules/finance-submission/hq-workspace`
- Allowed roles: `hq_admin`, `developer`
- Inputs: `tenant_code`, `month`
- Output: per-site publish status rows for the selected tenant+month.

## 2. Site Row Fields
- `site_code`
- `site_name`
- `month`
- `has_published_file`
- `status`
- `selectable`
- `latest_published_at`
- `latest_published_by`
- `latest_filename`
- `note`
- `latest_publish_version`
- `user_last_seen_version`
- `ui_summary`
- `technical_details`

## 3. Status Values
- `게시 완료`
  - A current publish exists for the site+month.
  - The actor does not have a stale seen/download gap for that site+month.
- `파일 없음`
  - No current publish exists for the site+month.
- `업데이트 필요`
  - A current publish exists.
  - The actor previously downloaded/acknowledged an older publish for that site+month.
  - The current publish marker is newer than the actor's last seen marker.

## 4. Selectable Rules
- `파일 없음` => `selectable=false`
- `게시 완료` => `selectable=true`
- `업데이트 필요` => `selectable=true`

## 5. Update-Needed Semantics
- Persistence table: `schedule_finance_download_acks`
- Acknowledgement key: `tenant_id + actor_id + site_id + month_key`
- Stored comparison markers:
  - `published_batch_id`
  - `published_version`
  - `seen_at`
- Write timing:
  - on successful single-site 2차 download
  - on successful multi-site 2차 download, once per included site
- Compare rule:
  - if no current publish => `파일 없음`
  - if no acknowledgement exists => `게시 완료`
  - if `current active_final_batch_id != ack.published_batch_id` => `업데이트 필요`
  - else => `게시 완료`

## 6. Latest Publish Fields
- `latest_published_at`: current publish timestamp from state row
- `latest_published_by`: actor username of current publish
- `latest_filename`: current published filename
- `latest_publish_version`: current publish marker, derived from current publish revision / batch id
- `user_last_seen_version`: actor-specific last acknowledged marker

## 7. UI Summary vs Technical Details
- `ui_summary`
  - operator-facing fields only: site, month, status, selectable, latest publish time/by/filename, note
- `technical_details`
  - hidden/advanced diagnostic fields only
  - may include current publish batch id, current publish version, last seen batch id, last seen version, last seen at
- Raw artifact ids are not required by the normal operator flow and are not top-level required contract fields.
