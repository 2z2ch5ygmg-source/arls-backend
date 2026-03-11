ALTER TABLE IF EXISTS schedule_support_roundtrip_rows
ADD COLUMN IF NOT EXISTS payload_json jsonb NOT NULL DEFAULT '{}'::jsonb;
