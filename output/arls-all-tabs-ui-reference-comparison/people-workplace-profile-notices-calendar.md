# People / Workplace / Profile / Notices / Calendar UI reference comparison

Date: 2026-04-12  
Worker: worker-4  
Task: `People Workplace Profile Notices Calendar UI comparison`  
Scope: analysis only; no product source edits.

## Reference base

- ARLS catalog: `docs/design/arls-reference-action-layout-classification-20260412.md` images 6, 21-25, 38.
- Shiftee catalog: `docs/design/shiftee-reference-action-layout-classification-20260412.md` images 19, 21, 23, 26, 30, 33, 40, 45 and calendar-adjacent 13, 29.
- Shople captures: `output/shople-people-direct.png`, `output/shople-workplace-direct.png`, `output/shople-workplace-mgmt-direct.png`, `output/shople-company-settings-direct.png`, `output/playwright/arls-notices-list-reference.png`, `output/playwright/arls-notices-compose-after-reference.png`.
- Current ARLS evidence: `output/playwright/phase12-employee-management-hq-1366.png`, `phase12-site-management-1366.png`, `phase13-company-workspace-desktop-1920.png`, `batch2-profile-1366.png`, `settings-operations-after-prune-live.png`, `notices-list-live-polish-pass.png`, `notices-compose-live-polish-pass.png`, `remaining-calendar-live.png`, `phase5-schedule-calendar-deployed.png`.
- Binding rules: `docs/design/arls-global-design-law.md`, `shople-arls` skill core rules, and `ui-redesign-guardrails` pattern chooser / reference translation rules.

Note: the `shople-arls` skill points to `shople_dev_v1*.md` phase docs, but those files were not present in this checkout. I used the available Shople captures plus the binding global design law and UI guardrails instead.

## Cross-surface diagnosis

1. **ARLS is closer to its global design law than the older audit, but it is still not consistently reference-like.** The best current surfaces use one white primary sheet, dividers, compact tabs, and fewer inner panels. However, People/Workplace/Company still keep dashboard KPI blocks above the real work list, while Profile/Settings still splits into unrelated tool surfaces.
2. **Shiftee is table-first for admin and operations.** The relevant Shiftee employee/site/account screens use low-chrome rows, small search fields, left local category navigation, and restrained blue selection/action treatment. ARLS often adds more summary cards, bigger filters, and extra empty/detail panels before the user selects an object.
3. **Shople is visually lighter but more opinionated.** Shople People uses blue/orange chart accents and clear module identity; Shople Workplace and company/settings references use compact white sections, a dark top bar, sparse helper copy, and clear tab/accordion hierarchy. ARLS should translate this into ARLS orange/neutral accents without reintroducing card walls.
4. **Do not solve the remaining mismatch with more decoration.** The global law explicitly bans box-in-box, decorative title icons, oversized empty boxes, and redundant `보기/열기` style actions. The next pass should delete/demote redundant summaries first, then add accent only where it encodes selection, state, or the primary action.

## Priority issues and directions

### P0 — Settings/Profile: split default account settings from operations/admin tools

- **ARLS surface:** `#/profile`; current evidence `output/playwright/batch2-profile-1366.png` and `settings-operations-after-prune-live.png`.
- **Reference evidence:** Shiftee account/profile images 19, 21, 26, 33 show account/profile as a direct form with clear account/security sections; Shople company/settings uses tabbed accordion groups (`회사 정보`, `근무 정책`, `관리자`, `보안`, `연동`) and only expands the selected group.
- **Problem:** ARLS has improved from the older catch-all state, but the settings family is still split between a clean account/security page and an operations/profile generator page that looks like a narrow engineering control form. It mixes personal settings, operational rollout/profile generation, site/stream controls, and status feedback in one visual family.
- **Recommended direction:**
  - Make `내 설정` the default profile surface: account identity, password/security, notification preferences, and personal mode choices only.
  - Move tenant/operations tools into local subroutes or a left subsection nav: `연동`, `운영 플래그`, `프로필/시트 설정`, `관리 도구`.
  - Use Shople-style accordion/section rows for static settings; use compact field groups for real forms; avoid one tall column of boxed controls.
  - Keep one top summary chip only when a setting is blocked or needs action; do not keep an always-on right state rail.
- **Must not break:** logout, password change, notification prefs, role/mode visibility, Sheets/profile generator save behavior, groupware/video rollout tooling, any admin-only lock/log actions.
- **Avoid:** moving operational toggles into the personal default page, boxed checkbox rows for persistent settings, duplicated status text, and developer-facing internal labels in the first viewport.

### P0 — Employee management: remove dashboard-first composition and make list/detail the primary object model

- **ARLS surface:** `#/branch/employees`; current evidence `output/playwright/phase12-employee-management-hq-1366.png`, `phase7-org-employees-local.png`.
- **Reference evidence:** ARLS catalog images 6, 23, 24; Shiftee employee management images 40 and 45; Shople `output/shople-people-direct.png`.
- **Problem:** ARLS starts with four KPI cards, then a large filter block, then the employee list. Shiftee instead exposes a narrow local nav and a wide table-first work area. Shople uses summary charts, but the chart modules have clear visual identity and the table remains the operational anchor. ARLS's 0% circular KPI cards and disabled bulk-delete CTA read as decorative/admin noise before employee selection.
- **Recommended direction:**
  - Use a **directory-first 2-pane pattern**: compact list/table on the left, persistent selected employee summary/detail pane on the right.
  - Collapse KPI cards into a single slim strip (`전체`, `재직`, `계정 연결`, `역할 미구성`) or hide entirely when the values are all zero/empty.
  - Default visible filters to `검색`, `현장`, `재직 상태`; move `회사`, `역할`, inactive/deleted toggles, and dangerous bulk deletion into advanced/admin mode.
  - Row first line: name + role/status; second line: site + account connection + one key identifier. Open detail for phone, employee number, hire/retire dates, permissions, sync state, schedule linkage.
  - Use one accent color for primary add/import CTAs; destructive action stays in overflow/guarded footer.
- **Must not break:** employee registration, bulk import, search/filter/sort, role and SOC account state visibility, inactive/deleted inclusion, detail drawer actions, account/leave/schedule linkage from detail.
- **Avoid:** table rows as mini-cards inside another card, high-placed disabled destructive actions, repeating tenant/site context already known from the shell.

### P1 — Workplace/Site management: shift from infrastructure dump to setup/readiness browser

- **ARLS surface:** `#/branch/sites`; current evidence `output/playwright/phase12-site-management-1366.png`, `phase7-org-sites-local.png`.
- **Reference evidence:** ARLS catalog images 21, 22, 25; Shiftee workplace/location images 23 and 30; Shople `output/shople-workplace-direct.png`, `output/shople-workplace-mgmt-direct.png`.
- **Problem:** ARLS shows helpful right-side detail affordance, but the top still uses KPI cards and repeated readiness text. Rows expose address, coordinates, company code, employee count, and state before selection. Shiftee is more table-first and plain; Shople workplace management is lightweight, with local nav and compact section rows.
- **Recommended direction:**
  - Use a **site list + detail pane** with default row fields: site name/code, company, employee count, active state, readiness badge.
  - Move address, latitude/longitude, radius, Wi-Fi, and attendance criteria into detail sections (`기본 정보`, `출퇴근 기준`, `연동/검증`).
  - Replace four KPI cards with a segmented scope or tiny filter chips: `전체`, `운영중`, `설정 필요`, `Wi-Fi 미등록`.
  - Keep `지점 등록` in the header; `새로고침` can be a secondary icon/action in the filter row.
  - When no site is selected, keep the right pane as a slim instruction area, not a full framed empty card.
- **Must not break:** site registration/editing, active/inactive and deleted inclusion filters, geofence radius and Wi-Fi configuration, employee count, company/site scoping, attendance criteria semantics.
- **Avoid:** exposing coordinates as primary browsing text, repeated `준비 완료` copy per row, separate summary cards whose values duplicate filter chips.

### P1 — Notices: preserve the recent Shople-like shell but tighten list/detail/compose separation

- **ARLS surface:** `#/feature/notices`, `#/feature/notices?mode=new`; current evidence `output/playwright/notices-list-live-polish-pass.png`, `notices-compose-live-polish-pass.png`.
- **Reference evidence:** Shople-like notice references `output/playwright/arls-notices-list-reference.png`, `arls-notices-compose-after-reference.png`; Shiftee request-history empty states images 15, 18, 22 provide list/empty-state restraint rather than notice-specific behavior.
- **Problem:** The list and compose surfaces are now close to the Shople-like reference in spacing and same-plane grammar. Remaining mismatch is mostly state separation and density: empty list still centers a bordered CTA module, while compose exposes all insert tools in one horizontal strip and keeps a very large empty body.
- **Recommended direction:**
  - Keep the current top category tabs and header CTA; they match the reference better than the older card-wall version.
  - Make the empty list a same-plane empty state: icon + title + one CTA, no large framed mini-card unless there are pinned notices/details to group.
  - Introduce list/detail separation when data exists: pinned cluster (if any), compact rows (`title`, `category/date`, `pin/read`), then detail pane or route.
  - In compose, keep title/body dominant; move metadata (`카테고리`, `상단고정`, `발행`) into a right publish panel or compact top command block. Keep media/table/poll/link tools, but group them as secondary insert controls.
  - Preserve the reference's single white authoring sheet, but avoid making the editor a huge blank canvas when only metadata is active.
- **Must not break:** list first-entry route, compose route, detail route, permissions, CRUD, image/table/poll/link/block insertion, pinning, category filters, publish/return behavior.
- **Avoid:** reintroducing a card wall around every notice, duplicating category controls between list and compose, hiding authoring tools required for existing notice features.

### P1 — Calendar: keep calendar-first, but add Shiftee-style interpretation and inline detail

- **ARLS surface:** `#/calendar`; current evidence `output/playwright/remaining-calendar-live.png`, `phase5-schedule-calendar-deployed.png`; ARLS catalog image 38.
- **Reference evidence:** Shiftee schedule/calendar images 13 and 29; Shople schedule/calendar references in `output/shople-schedule-*` captures.
- **Problem:** ARLS calendar is clean and same-plane, but the sparse month view can feel like a blank grid with one selected day. Shiftee's schedule calendar pairs the grid with personal/team stats and event entries; older ARLS schedule calendar evidence already had a right detail panel for selected-day work. The current standalone calendar lacks a strong legend, selected-day interpretation, or quick jump to list/detail.
- **Recommended direction:**
  - Keep the calendar as a primary grid, but add a slim selected-day detail rail or bottom panel with event count, selected date, and quick actions.
  - Add compact legend/filter chips near the toolbar (`일정`, `외부`, `휴가`, `근무`) if those states exist in data; do not add decorative chips without data meaning.
  - Make `새 일정` a header-level primary action and keep view toggles (`일/주/월`) compact and aligned with filters.
  - For empty months, show a tiny same-plane empty note in the selected-day detail area instead of filling calendar cells with placeholder content.
  - If the page is intended as a personal calendar rather than schedule management, keep it visually lighter than `스케줄` and do not copy Shiftee's HR schedule edit modal behavior.
- **Must not break:** month/week/day toggles, today/prev/next navigation, filters/fullscreen, event create/edit flows, external calendar read-only rules, public booking links/sync states if routed through this family.
- **Avoid:** adding dashboard KPI cards above the calendar, pushing the grid below large summaries, or turning selected-day detail into an unrelated card stack.

### P2 — Company/Master tenant management: keep separate admin context and reduce placeholder noise

- **ARLS surface:** `#/master/tenants`, `#/master/tenants/<id>/overview`; current evidence `output/playwright/phase13-company-workspace-desktop-1920.png`.
- **Reference evidence:** ARLS People/workplace catalog adjacent images 21-25; Shople `output/shople-company-settings-direct.png`; Shiftee company selection image 17 only helps with context switching, not tenant admin details.
- **Problem:** ARLS's company page is more compact than earlier audit notes, but it still shows summary cards for `삭제됨`, `미조회`, and `null` connection state. This makes the page feel like a database admin console rather than a governance workspace. The normal ARLS shell also makes MASTER context feel too close to day-to-day operations.
- **Recommended direction:**
  - Keep company management as a distinct admin workspace with a clear `MASTER` banner/context indicator.
  - Replace placeholder-heavy KPI cards with one summary strip: `전체`, `활성`, `보완 필요`, `최근 변경`.
  - In list rows, show company, active state, completeness score/badge, sites, employees. Collapse stamp, connection, and missing fields into detail checklist.
  - In detail pane, group `기본 정보`, `운영 현황`, `보호 액션`; keep destructive actions in a guarded footer/modal.
- **Must not break:** tenant selection, tenant create/edit, activation/deactivation/delete protections, stamp/company info completeness, site/employee counts, MASTER-only permission checks.
- **Avoid:** `null`/`미조회` as first-view primary text, destructive actions adjacent to ordinary row details, duplicated active/state info in both table and pane.

## Recommended implementation order

1. **Settings/Profile IA split** — highest leverage; currently mixes personal, integration, and operations tools.
2. **Employee directory 2-pane restructure** — highest traffic People surface; removes KPI/filter/table overload.
3. **Notices list/detail/compose separation polish** — already close; smaller finishing pass with high visible payoff.
4. **Workplace site browser/detail restructure** — same pattern as employees, lower complexity.
5. **Calendar selected-day detail/legend pass** — preserve current clean grid while making it less empty.
6. **Company admin context cleanup** — important for MASTER, but less frequent and should follow shell/IA confirmation.

## Shared must-not-break constraints

- Preserve ARLS routes, deep links, role permissions, tenant/site scoping, and existing business outcomes.
- Do not copy Shiftee or Shople features that ARLS does not have; use them only for hierarchy, density, spacing, and interaction model.
- Stay within ARLS global design law: one outer plane, one white primary sheet, same-plane subdivision, divider rhythm, no default box-in-box.
- Keep icons semantic. Do not add decorative title-left icons just to look closer to Shople.
- Keep primary actions in the header row or local command row; move destructive actions into guarded flows.
- Prefer lists/tables for comparison and operational management; use detail panes for metadata and advanced fields.
- Preserve notice rich-compose capabilities, calendar external/read-only behavior, employee/site CRUD, and profile/admin operational tooling.
