ALTER TABLE sentrix_support_hq_roster_batches
  DROP CONSTRAINT IF EXISTS chk_sentrix_support_hq_roster_batches_scope;

ALTER TABLE sentrix_support_hq_roster_batches
  ADD CONSTRAINT chk_sentrix_support_hq_roster_batches_scope
  CHECK (download_scope IN ('all', 'site', 'selected'));
