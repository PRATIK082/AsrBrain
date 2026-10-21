-- The retrieval unit (a chunk) is the precise anchor of a source location.
-- Keeping it on the location lets a citation be bound to a passage exactly,
-- instead of being resolved by a fragile text match.
ALTER TABLE source_locations ADD COLUMN chunk_id TEXT;

CREATE INDEX IF NOT EXISTS idx_source_locations_chunk ON source_locations(chunk_id);
