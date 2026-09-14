"""Compute the W5 scratch-smoke assertions from the raw 18289 HTTP evidence."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import re

E = Path(__file__).resolve().parent
DB = Path("/tmp/w5-scratch/data/access-logs-copy.sqlite3")
PURGE_DB = Path("/tmp/w5-scratch/data/purge-copy.sqlite3")
SETTINGS = Path("/tmp/w5-scratch/managed/settings.json")
SCRIPT = E.parents[2] / "deploy" / "purge-access-logs.sh"

results: dict[str, object] = {}


def load(name: str):
    return json.loads((E / name).read_text(encoding="utf-8"))


def raw(name: str) -> str:
    return (E / name).read_text(encoding="utf-8")


def sql(query: str, params: tuple = ()) -> list[tuple]:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        return con.execute(query, params).fetchall()
    finally:
        con.close()


# 1) identity capture over real HTTP -----------------------------------------
write_turn = load("scratch-18289-write-turn.json")
sessions_identity = load("scratch-18289-sessions-identity.json")
detail = load("scratch-18289-session-detail.json")
detail_anon = load("scratch-18289-session-detail-anon.json")
stored_identity = sql(
    "SELECT user_identity FROM turns WHERE session_id = 'session:chat:smoke'"
)
results["identity"] = {
    "write_response": write_turn,
    "identity_sessions": [s["session_id"] for s in sessions_identity["sessions"]],
    "list_identities": [
        s["identities"] for s in sessions_identity["sessions"]
    ],
    "detail_turn_identity": [t["user_identity"] for t in detail["turns"]],
    "stored_value": [row[0] for row in stored_identity],
    "no_header_detail_identity": [t["user_identity"] for t in detail_anon["turns"]],
    "pass": (
        write_turn["recorded"] is True
        and [s["session_id"] for s in sessions_identity["sessions"]]
        == ["session:chat:smoke"]
        and [t["user_identity"] for t in detail["turns"]] == ["smoke-auditor"]
        and [row[0] for row in stored_identity] == ["smoke-auditor"]
        and [t["user_identity"] for t in detail_anon["turns"]] == ["anonymous"]
    ),
}

# 2) combined filters vs direct SQL ------------------------------------------
combined = load("scratch-18289-filtered-combined.json")
empty_bucket = load("scratch-18289-filtered-empty-bucket.json")
sql_combined = sql(
    """
    SELECT COUNT(*) FROM sessions s WHERE
      EXISTS (SELECT 1 FROM turns t WHERE t.session_id = s.session_id
              AND t.status = 'completed')
      AND EXISTS (SELECT 1 FROM turns t WHERE t.session_id = s.session_id
              AND t.query_type = 'canonical_v2:A:answer')
      AND EXISTS (SELECT 1 FROM turns t WHERE t.session_id = s.session_id
              AND COALESCE(NULLIF(t.user_identity, ''), 'anonymous') = 'anonymous')
      AND EXISTS (SELECT 1 FROM turns t WHERE t.session_id = s.session_id
              AND t.started_at >= '2026-08-10T00:00:00.000000+00:00'
              AND t.started_at <= '2026-08-13T23:59:59.999999+00:00')
    """
)[0][0]
sql_empty_bucket = sql("SELECT COUNT(DISTINCT session_id) FROM turns WHERE query_type = ''")[0][0]
results["combined_filters"] = {
    "http_total": combined["total"],
    "sql_total": sql_combined,
    "http_sessions_sample": [s["session_id"] for s in combined["sessions"][:3]],
    "empty_query_type_bucket_http": empty_bucket["total"],
    "empty_query_type_bucket_sql": sql_empty_bucket,
    "invalid_naive_datetime_status": raw("scratch-18289-filtered-invalid.json"),
    "invalid_order_status": raw("scratch-18289-filtered-invalid-order.json"),
    "pass": (
        combined["total"] == sql_combined > 0
        and empty_bucket["total"] == sql_empty_bucket
    ),
}

# 3) export equals what the page shows ---------------------------------------
csv_rows = list(csv.DictReader(io.StringIO(raw("scratch-18289-export.csv"))))
jsonl_rows = [json.loads(line) for line in raw("scratch-18289-export.jsonl").splitlines() if line.strip()]
from collections import Counter
turn_counts = Counter(row["session_id"] for row in csv_rows)
busiest = [sid for sid, _ in turn_counts.most_common(3)]
sampled = list(dict.fromkeys(busiest + ["session:chat:smoke", "session:chat:smoke-anon"]))
compared_turns = 0
mismatches: list[str] = []
for session_id in sampled:
    detail_json = json.loads(
        subprocess.run(
            [
                "curl", "-sS",
                f"http://127.0.0.1:18289/api/canonical-v2/admin/access-logs/sessions/{session_id}",
            ],
            capture_output=True, text=True, check=True,
        ).stdout
    )
    visible = {t["turn_id"]: t for t in detail_json["turns"]}
    for turn_id, turn in visible.items():
        compared_turns += 1
        row = next(r for r in csv_rows if r["turn_id"] == turn_id)
        line = next(r for r in jsonl_rows if r["turn_id"] == turn_id)
        checks = {
            "user_identity": (row["user_identity"], turn["user_identity"]),
            "query": (row["query"], turn["query"]),
            "answer_text": (row["answer_text"], turn["answer_text"]),
            "status": (row["status"], turn["status"]),
            "error_detail": (row["error_detail"], turn["error_detail"] or ""),
            "latency_ms": (row["latency_ms"], str(turn["latency_ms"])),
            "started_at": (row["started_at"], turn["started_at"]),
            "citations": (json.loads(row["citations"]), turn["citations"]),
            "suggested_followups": (
                json.loads(row["suggested_followups"]),
                turn["suggested_followups"],
            ),
        }
        for field, (exported, page) in checks.items():
            if exported != page:
                mismatches.append(f"{session_id}/{turn_id}/{field}: {exported!r} != {page!r}")
        if line["query"] != row["query"] or line["citations"] != json.loads(row["citations"]):
            mismatches.append(f"{session_id}/{turn_id}/jsonl-diverges")
results["export_equals_page"] = {
    "csv_rows": len(csv_rows),
    "jsonl_rows": len(jsonl_rows),
    "sampled_sessions": sampled,
    "compared_turns": compared_turns,
    "mismatches": mismatches,
    "bad_format_response": raw("scratch-18289-export-bad-format.json"),
    "pass": not mismatches and len(csv_rows) == len(jsonl_rows) and len(csv_rows) > 0,
}

# 4) statistics reconciled with SQL over the turns table ----------------------
stats = load("scratch-18289-stats.json")
window = (stats["window"]["since"], stats["window"]["until"])
where = "WHERE t.started_at >= ? AND t.started_at <= ?"
totals_sql = sql(
    f"SELECT COUNT(*), COUNT(DISTINCT t.session_id),"
    f" COALESCE(SUM(t.status='error'),0), COALESCE(SUM(t.status='interrupted'),0)"
    f" FROM turns t {where}",
    window,
)[0]
daily_sql = sql(
    f"SELECT substr(t.started_at,1,10), COUNT(*), COUNT(DISTINCT t.session_id)"
    f" FROM turns t {where} GROUP BY 1 ORDER BY 1",
    window,
)
types_sql = sql(
    f"SELECT t.query_type, COUNT(*) FROM turns t {where}"
    f" GROUP BY 1 ORDER BY 2 DESC, 1 ASC",
    window,
)
identities_sql = sql(
    f"SELECT COALESCE(NULLIF(t.user_identity,''),'anonymous'), COUNT(*) FROM turns t {where}"
    f" GROUP BY 1 ORDER BY 2 DESC, 1 ASC",
    window,
)
top_sql = sql(
    f"SELECT TRIM(t.query), COUNT(*) FROM turns t {where}"
    f" GROUP BY 1 ORDER BY 2 DESC, 1 ASC LIMIT 10",
    window,
)
stats_match = {
    "totals": (
        stats["totals"]["turns"], stats["totals"]["sessions"],
        stats["totals"]["errors"], stats["totals"]["interrupted"],
    ) == totals_sql,
    "error_rate": stats["totals"]["error_rate"] == round(totals_sql[2] / totals_sql[0], 4),
    "daily": [(d["day"], d["turns"], d["sessions"]) for d in stats["daily"]] == daily_sql,
    "query_types": [(q["query_type"], q["turns"]) for q in stats["query_types"]] == types_sql,
    "identities": [(i["identity"], i["turns"]) for i in stats["identities"]] == identities_sql,
    "top_queries": [(q["query"], q["turns"]) for q in stats["top_queries"]] == top_sql,
}
default_stats = load("scratch-18289-stats-default.json")
empty_stats = load("scratch-18289-stats-empty.json")
from datetime import datetime
since = datetime.fromisoformat(default_stats["window"]["since"])
until = datetime.fromisoformat(default_stats["window"]["until"])
results["statistics_reconcile"] = {
    "sql_totals": totals_sql,
    "http_totals": stats["totals"],
    "sql_window_turns": totals_sql[0],
    "checks": stats_match,
    "default_window_days": (until - since).days,
    "default_window_defaulted": default_stats["window"]["since_defaulted"],
    "empty_window": empty_stats["totals"],
    "pass": all(stats_match.values())
    and default_stats["window"]["since_defaulted"] is True
    and (until - since).days == 30
    and empty_stats["totals"]["turns"] == 0
    and empty_stats["totals"]["error_rate"] == 0.0,
}

# 5) retention: page reads the managed settings file -------------------------
config = load("scratch-18289-admin-config.json")
retention_field = next(
    f for f in config["fields"] if f["path"] == "paths.access_log_retention_days"
)
purge_file = subprocess.run(
    ["bash", str(SCRIPT)], capture_output=True, text=True,
    env={
        "PATH": "/usr/bin:/bin",
        "CANONICAL_V2_ACCESS_LOG_DB": str(PURGE_DB),
        "CANONICAL_V2_MANAGED_SETTINGS": str(SETTINGS),
    }, check=False,
)
purge_default = subprocess.run(
    ["bash", str(SCRIPT)], capture_output=True, text=True,
    env={
        "PATH": "/usr/bin:/bin",
        "CANONICAL_V2_ACCESS_LOG_DB": str(PURGE_DB),
    }, check=False,
)
survivors = sqlite3.connect(PURGE_DB).execute("SELECT COUNT(*) FROM turns").fetchone()[0]
results["retention"] = {
    "config_field": retention_field,
    "purge_with_scratch_settings": purge_file.stdout.strip(),
    "purge_without_settings": purge_default.stdout.strip(),
    "turns_after_purge": survivors,
    "settings_file": json.loads(SETTINGS.read_text(encoding="utf-8")),
    "pass": (
        retention_field["value"] == 45
        and retention_field["source"] == "file"
        and "retention_days=45" in purge_file.stdout
        and "source=file" in purge_file.stdout
        and "retention_days=90" in purge_default.stdout
        and "source=default" in purge_default.stdout
    ),
}

# 6) privacy: no network identifier is recorded or exposed -------------------
columns = [row[1] for row in sql("PRAGMA table_info(turns)")]
ip_pattern = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
exposed_texts = {
    "detail": raw("scratch-18289-session-detail.json"),
    "list": raw("scratch-18289-sessions-before.json"),
    "export.csv": raw("scratch-18289-export.csv"),
    "export.jsonl": raw("scratch-18289-export.jsonl"),
    "config": raw("scratch-18289-admin-config.json"),
}
row_payload = json.dumps(
    sql("SELECT * FROM turns ORDER BY started_at DESC LIMIT 200"), ensure_ascii=False
)
results["no_ip_recorded"] = {
    "turn_columns": columns,
    "column_hits": [c for c in columns if "ip" in c.lower() or "addr" in c.lower() or "agent" in c.lower() or "cookie" in c.lower()],
    "ip_pattern_in_exposed_responses": {k: ip_pattern.findall(v) for k, v in exposed_texts.items()},
    "ip_pattern_in_stored_rows": ip_pattern.findall(row_payload),
    "pass": (
        not [c for c in columns if "ip" in c.lower() or "addr" in c.lower()]
        and not any(ip_pattern.findall(v) for v in exposed_texts.values())
        and not ip_pattern.findall(row_payload)
    ),
}

(E / "scratch-18289-checks.json").write_text(
    json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
)
for name, value in results.items():
    print(f"{name}: {'PASS' if value['pass'] else 'FAIL'}")
