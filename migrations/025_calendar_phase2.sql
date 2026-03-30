ALTER TABLE calendar_events
ADD COLUMN IF NOT EXISTS resource_id uuid REFERENCES calendar_resources(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_calendar_events_resource_window
ON calendar_events (resource_id, starts_at, ends_at)
WHERE resource_id IS NOT NULL;
