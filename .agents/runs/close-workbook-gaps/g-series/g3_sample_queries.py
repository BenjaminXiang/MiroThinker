#!/usr/bin/env python3
"""Sample access-log queries (read-only)."""
import sqlite3

ACCESS = "/var/tmp/mirothinker-canonical-v2-s12f/access-logs.sqlite3"

con = sqlite3.connect(f"file:{ACCESS}?mode=ro", uri=True)
cur = con.cursor()
cur.execute("SELECT key, value FROM workspace_meta")
print("workspace_meta:", cur.fetchall())
cur.execute("SELECT query_type, COUNT(*) FROM turns GROUP BY query_type ORDER BY 2 DESC")
print("query_type:", cur.fetchall())
cur.execute("SELECT status, COUNT(*) FROM turns GROUP BY status")
print("status:", cur.fetchall())
cur.execute("SELECT MIN(started_at), MAX(started_at) FROM turns")
print("window:", cur.fetchone())
print()
cur.execute("SELECT turn_id, session_id, turn_count, query FROM turns ORDER BY started_at LIMIT 40")
for r in cur.fetchall():
    print(r[0], "|", r[2], "|", (r[3] or "")[:160].replace("\n", " "))
con.close()
