ALTER TABLE notices
  ADD COLUMN IF NOT EXISTS body_model text NOT NULL DEFAULT 'legacy_block_flow',
  ADD COLUMN IF NOT EXISTS body_document jsonb,
  ADD COLUMN IF NOT EXISTS target_mode text NOT NULL DEFAULT 'all',
  ADD COLUMN IF NOT EXISTS target_usernames jsonb NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS is_important boolean NOT NULL DEFAULT false;

UPDATE notices
SET body_model = 'legacy_block_flow'
WHERE COALESCE(NULLIF(trim(body_model), ''), '') = '';

UPDATE notices
SET target_mode = 'all'
WHERE COALESCE(NULLIF(trim(target_mode), ''), '') = '';

UPDATE notices
SET target_usernames = '[]'::jsonb
WHERE target_usernames IS NULL
   OR jsonb_typeof(target_usernames) <> 'array';

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'chk_notices_body_model'
      AND conrelid = 'notices'::regclass
  ) THEN
    ALTER TABLE notices
      ADD CONSTRAINT chk_notices_body_model
      CHECK (body_model IN ('legacy_block_flow', 'floating_scene_v1', 'flow_lane_v1'));
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'chk_notices_target_mode'
      AND conrelid = 'notices'::regclass
  ) THEN
    ALTER TABLE notices
      ADD CONSTRAINT chk_notices_target_mode
      CHECK (target_mode IN ('all', 'selected'));
  END IF;
END $$;

ALTER TABLE notice_polls
  ADD COLUMN IF NOT EXISTS client_key text;

UPDATE notice_polls
SET client_key = id::text
WHERE COALESCE(NULLIF(trim(client_key), ''), '') = '';

ALTER TABLE notice_poll_options
  ADD COLUMN IF NOT EXISTS client_key text;

UPDATE notice_poll_options
SET client_key = id::text
WHERE COALESCE(NULLIF(trim(client_key), ''), '') = '';

CREATE UNIQUE INDEX IF NOT EXISTS uq_notice_polls_tenant_notice_client_key
  ON notice_polls (tenant_id, notice_id, client_key)
  WHERE client_key IS NOT NULL AND btrim(client_key) <> '';

CREATE UNIQUE INDEX IF NOT EXISTS uq_notice_poll_options_tenant_poll_client_key
  ON notice_poll_options (tenant_id, poll_id, client_key)
  WHERE client_key IS NOT NULL AND btrim(client_key) <> '';

CREATE INDEX IF NOT EXISTS idx_notices_tenant_body_model
  ON notices (tenant_id, body_model, updated_at DESC);
