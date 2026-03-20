# Sentrix Native Foundation (Phase 1 + Phase 2A)

This package keeps the original Phase 1 native foundation and adds the HQ-safe authenticated Phase 2A slice for Sentrix.

What is intentionally implemented:
- public bootstrap using:
  - `/health`
  - `/api/app-config`
  - `/api/build-info`
- stored-session continuation using:
  - `soc_token`
  - `soc_user`
- HQ authenticated bootstrap using `/api/bootstrap-config`
- HQ SSE realtime transport using `/api/notifications/stream?token=...`
- HQ Apple Weekly read/readiness/conflict/dry-run workspace
- support-submission handoff-only workspace
- server-side push diagnostics result model
- login shell container for blocked fresh sign-in
- session/unauthorized/session-expired structure
- diagnostics/build provenance screen
- read-only and master-data-read-only notice structure
- adapter boundaries and stubs for runtime-blocked integrations

What is intentionally not finalized:
- production auth branch orchestration
- field, disabled, or HR-linked account behavior
- universal authenticated `/api/bootstrap-config` behavior
- realtime ordering guarantees and non-HQ transport variants
- Apple Weekly mutation, rollout, conflict-resolution, and live write
- Google Sheets write flows
- native APNs registration and device receipt
- startup recovery and degraded read-only operational behavior

Module layout:
- `SentrixCore`
  - domain models
  - public runtime contracts
  - adapter protocols
  - use cases
- `SentrixAPI`
  - public bootstrap DTOs
  - network client
  - DTO-to-domain mappers
  - live public bootstrap repository
  - blocked integration stubs
- `SentrixDesignSystem`
  - theme tokens
  - common state components
- `SentrixFeatures`
  - bootstrap/session containers
  - diagnostics screen
  - blocked-module placeholders
  - root navigation shell
- `SentrixPhase1App`
  - SwiftUI app entry point
  - concrete composition root for public bootstrap, HQ-safe authenticated repositories, and remaining blocked adapters

Hardening notes:
- `SentrixFeatures` depends on `SentrixCore` contracts and shared UI only; concrete API wiring lives in `SentrixPhase1App`.
- blocked adapters are marked with `BLOCKED-BY-RUNTIME[...]` comments and must not be replaced before authenticated runtime capture exists for the unresolved role or behavior.
- public bootstrap decoding is tolerant of missing fields and minor schema drift, but incompatible contract changes still fail loudly.
- HQ-authenticated repositories are wired only for runtime-proven HQ slices. Field or universal behavior must remain blocked until dedicated runtime evidence exists.

Source-of-truth references for blocked modules:
- `sentrix_reverse_engineering_audit_2026-03-19.md`
- `sentrix_reverse_engineering_audit_closure_pass_1_2026-03-19.md`
- `sentrix_reverse_engineering_audit_public_runtime_addendum_2026-03-19.md`
- `sentrix_runtime_recon_pass_b_2026-03-19.md`
- `sentrix_authenticated_runtime_addendum_2026-03-19.md`
- `sentrix_phase_2a_scope_2026-03-19.md`
- `sentrix_field_runtime_closure_pass_2026-03-19.md`
- `sentrix_staged_native_implementation_design_2026-03-19.md`
