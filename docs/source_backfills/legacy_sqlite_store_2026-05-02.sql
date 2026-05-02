-- Legacy admin-console SQLite released object store schema.
-- Archived before retiring admin-console reads/writes of SqliteReleasedObjectStore
-- in W10-6 Batch D on 2026-05-02.

PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS released_objects (
  id TEXT PRIMARY KEY,
  object_type TEXT NOT NULL,
  display_name TEXT NOT NULL,
  payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_released_objects_object_type
ON released_objects(object_type);
