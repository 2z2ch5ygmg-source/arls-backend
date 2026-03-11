ALTER TABLE sentrix_support_roster_snapshot_entries
    ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT timezone('utc', now());
