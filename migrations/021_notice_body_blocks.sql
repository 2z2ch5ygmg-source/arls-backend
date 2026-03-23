ALTER TABLE notices
  ADD COLUMN IF NOT EXISTS body_blocks jsonb NOT NULL DEFAULT '[]'::jsonb;

UPDATE notices
SET body_blocks = jsonb_build_array(
  jsonb_build_object(
    'kind', 'paragraph',
    'variant', 'body',
    'text', body_text
  )
)
WHERE (body_blocks IS NULL OR body_blocks = '[]'::jsonb)
  AND COALESCE(btrim(body_text), '') <> '';
