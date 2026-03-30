ALTER TABLE calendar_booking_links
ADD COLUMN IF NOT EXISTS duration_minutes integer NOT NULL DEFAULT 30;

ALTER TABLE calendar_booking_links
ADD COLUMN IF NOT EXISTS availability_start_time time without time zone NOT NULL DEFAULT '09:00';

ALTER TABLE calendar_booking_links
ADD COLUMN IF NOT EXISTS availability_end_time time without time zone NOT NULL DEFAULT '18:00';

CREATE INDEX IF NOT EXISTS idx_calendar_booking_links_public_window
ON calendar_booking_links (is_public, expires_at, created_at DESC);
