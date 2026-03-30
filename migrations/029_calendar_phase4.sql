ALTER TABLE calendar_sync_connections
  ADD COLUMN IF NOT EXISTS default_container_id uuid NULL REFERENCES calendar_containers(id) ON DELETE SET NULL;

ALTER TABLE calendar_sync_connections
  ADD COLUMN IF NOT EXISTS selected_external_calendars_json jsonb NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE calendar_sync_connections
  ADD COLUMN IF NOT EXISTS last_sync_error text NULL;

CREATE INDEX IF NOT EXISTS idx_calendar_sync_connections_default_container_id
  ON calendar_sync_connections(default_container_id);
