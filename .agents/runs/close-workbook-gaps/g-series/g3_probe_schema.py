#!/usr/bin/env python3
"""Probe the access-log and lookup schemas (read-only) for G3 category anchoring."""
import sqlite3
import sys

ACCESS = "/var/tmp/mirothinker-canonical-v2-s12f/access-logs.sqlite3"
PACK = "/var/tmp/mirothinker-data-v2/serving-pack-run14/lookup.sqlite3"


def dump(path, label):
    print("=" * 72)
    print(f"[{label}] {path}")
    print("=" * 72)
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    cur = con.cursor()
    cur.execute("SELECT type, name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name")
    rows = cur.fetchall()
    for t, n in rows:
        print(f"-- {t}: {n}")
    print()
    for t, n in rows:
        if t != "table":
            continue
        cur.execute(f"PRAGMA table_info({n})")
        cols = cur.fetchall()
        print(f"### {n}")
        for c in cols:
            print("    ", c[1], c[2])
        try:
            cur.execute(f"SELECT COUNT(*) FROM {n}")
            print("     rows =", cur.fetchone()[0])
        except Exception as e:  # noqa: BLE001
            print("     rows = ?", e)
        print()
    con.close()


if __name__ == "__main__":
    dump(ACCESS, "ACCESS")
    if "--pack" in sys.argv:
        dump(PACK, "PACK")
