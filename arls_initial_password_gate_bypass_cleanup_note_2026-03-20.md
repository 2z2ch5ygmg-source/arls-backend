## ARLS Initial Password-Gate Runtime-Testing Bypass Cleanup Note (2026-03-20)

- Temporary ARLS initial password-change gate runtime-testing bypass reverted.
- Revert scope was limited to disabling the temporary bypass switch only.
- Original password-change gate logic, redirect/toast behavior, and role-based permission behavior remain in place.
- Upload, finance, apply, and other mutation permissions were not changed by this cleanup.
- This cleanup note is runtime/QA history only.
- Frozen Sentrix Phase 2A / Phase 2B native baselines remain unchanged.
