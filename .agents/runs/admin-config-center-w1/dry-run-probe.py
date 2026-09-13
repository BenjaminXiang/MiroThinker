"""W1 dry-run inventory probe (read-only).

Produces the machine-readable half of the config inventory: which config items
exist, where they come from, what actually resolves right now, and what is
missing. Never prints or persists credential material: key material is reduced
to a boolean plus length, and values are redacted for sensitive names.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys

REPO = Path("/home/longxiang/MiroThinker/.worktrees/admin-config-center")
SERVING_ROOT = Path("/var/tmp/mirothinker-canonical-v2-s12f")
PACK_DIR = Path("/var/tmp/mirothinker-data-v2/serving-pack-run14-sealed")
INDEX_ROOT = Path("/var/tmp/mirothinker-data-v2/index-v1")
LIVE_PID = 1992450  # canonical-v2-backend child of the systemd unit

SENSITIVE_RE = re.compile(
    r"(KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|DATABASE_URL|DSN|WEBHOOK)",
    re.IGNORECASE,
)

ENV_PROBES = [
    "DATABASE_URL",
    "DATABASE_URL_TEST",
    "CANONICAL_V2_DATABASE_URL",
    "CANONICAL_V2_EXPECTED_DATABASE",
    "CANONICAL_V2_TARGET_KIND",
    "CANONICAL_V2_BACKUP_GATE_ROOT",
    "CANONICAL_V2_ACCESS_LOG_DB",
    "CANONICAL_V2_CORRECTIONS_DB",
    "CANONICAL_V2_MANUAL_RECALL_DIR",
    "CANONICAL_V2_SERVING_PACK",
    "CANONICAL_V2_LEXICAL_INDEX",
    "CANONICAL_V2_LEXICAL_INDEX_ROOT",
    "CANONICAL_V2_RERANK_BASE_URL",
    "CANONICAL_V2_RERANK_MODEL",
    "CANONICAL_V2_RERANK_API_KEY",
    "CANONICAL_V2_RERANK_API_KEY_FILE",
    "CHAT_LLM_PROFILE",
    "CHAT_LLM_TIMEOUT_SECONDS",
    "CHAT_LLM_SYNTHESIS",
    "CHAT_AUGMENT_WEB",
    "CHAT_CONTEXTUAL_INTERPRETATION",
    "CHAT_E_WEB_FALLBACK_THRESHOLD",
    "CHAT_QUERY_CLASSIFIER",
    "CHAT_SYNTHESIS_TIMEOUT",
    "CHAT_MILVUS_URI",
    "MILVUS_URI",
    "TURN_TRACE_DIR",
    "CANONICAL_V2_TURN_DEBUG_DIR",
    "BOCHA_API_KEY",
    "SERPER_API_KEY",
    "OPENALEX_API_KEY",
    "SEMANTIC_SCHOLAR_API_KEY",
    "DEEPSEEK_API_KEY",
    "DASHSCOPE_API_KEY",
    "LOCAL_LLM_BASE_URL",
    "LOCAL_LLM_MODEL",
    "ONLINE_LLM_BASE_URL",
    "ONLINE_LLM_MODEL",
    "WEB_LANE_DAILY_QUOTA",
    "CANONICAL_V2_REVIEW_PROVIDER_PROFILE",
]

KEY_FILES = [
    ".bocha_api_key",
    ".serper_api_key",
    ".sglang_api_key",
    ".deepseek_api_key",
    ".dashscope_api_key",
    ".ark_api_key",
]

SQLITE_TARGETS = [
    ("access_log", SERVING_ROOT / "access-logs.sqlite3"),
    ("corrections", SERVING_ROOT / "corrections.sqlite3"),
    ("pack_lookup", PACK_DIR / "lookup.sqlite3"),
    ("live_index_lookup", INDEX_ROOT / "lookup.sqlite3"),
]

BIG_FILES = [
    ("pack_milvus", PACK_DIR / "milvus.db"),
    ("live_index_milvus", INDEX_ROOT / "milvus.db"),
    ("pack_lookup", PACK_DIR / "lookup.sqlite3"),
    ("pack_relationships", PACK_DIR / "relationships.json"),
    ("live_vector_matrix", INDEX_ROOT / "vector_matrix.npz"),
]

COLLECTION_SCRIPTS = [
    "run_company_news_ingest.py",
    "run_company_official_product_capture.py",
    "run_paper_search_backfill.py",
    "run_paper_summary_zh_backfill.py",
    "run_paper_doi_verify.py",
    "run_profile_bio_rescrape.py",
    "run_homepage_paper_ingest.py",
]


def redact(name: str, value: str | None) -> object:
    if value is None:
        return None
    if SENSITIVE_RE.search(name):
        return {"present": bool(value.strip()), "length": len(value)}
    return value


def live_env() -> dict[str, object]:
    path = Path(f"/proc/{LIVE_PID}/environ")
    result: dict[str, object] = {"probe": str(path), "readable": False, "values": {}}
    try:
        raw = path.read_bytes()
    except OSError as exc:
        result["error"] = type(exc).__name__
        return result
    result["readable"] = True
    seen = {}
    for chunk in raw.split(b"\0"):
        if b"=" not in chunk:
            continue
        name, _, value = chunk.decode("utf-8", "replace").partition("=")
        seen[name] = value
    result["values"] = {name: redact(name, seen.get(name)) for name in ENV_PROBES}
    result["value_count"] = len(seen)
    return result


def current_process_env() -> dict[str, object]:
    return {
        name: redact(name, os.environ.get(name)) for name in ENV_PROBES
    }


def key_files() -> list[dict[str, object]]:
    out = []
    for name in KEY_FILES:
        entry: dict[str, object] = {"name": name}
        for label, root in (("worktree_root", REPO), ("main_repo_root", REPO.parent.parent)):
            path = root / name
            info: dict[str, object] = {"path": str(path), "exists": path.is_file()}
            if path.is_file():
                stat = path.stat()
                info["readable"] = os.access(path, os.R_OK)
                info["bytes"] = stat.st_size
            entry[label] = info
        out.append(entry)
    return out


def sha256_file(path: Path, *, chunk: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(chunk)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def pack_manifest() -> dict[str, object]:
    manifest_path = PACK_DIR / "manifest.json"
    result: dict[str, object] = {"path": str(manifest_path)}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result
    result.update(
        {
            "schema_version": manifest.get("schema_version"),
            "pack_id": manifest.get("pack_id"),
            "release_id": manifest.get("release_id"),
            "generated_at": manifest.get("generated_at"),
            "generator_run_id": manifest.get("generator_run_id"),
            "index_marker_sha256": manifest.get("index_marker_sha256"),
            "index_root": manifest.get("index_root"),
            "embedding_model_id": manifest.get("embedding_model_id"),
            "manifest_version": manifest.get("build_manifest", {}).get(
                "manifest_version"
            ),
            "build_run_id": manifest.get("build_manifest", {}).get("build_run_id"),
            "build_created_at": manifest.get("build_manifest", {}).get("created_at"),
            "verified_at": manifest.get("release_verification", {}).get("verified_at"),
            "accepted": manifest.get("release_verification", {}).get("accepted"),
            "published_record_counts": {
                section.get("projection_id") or section.get("domain"): section["record_count"]
                for section in manifest.get("build_manifest", {}).get(
                    "published_projections", []
                )
            },
        }
    )
    # Real file-hash verification of the (huge) pack files is the expensive
    # half; do it for the small members only and report the registry verbatim.
    result["file_registry"] = dict(manifest.get("files", {}))
    result["file_registry_matches"] = {}
    for name, expected in manifest.get("files", {}).items():
        path = PACK_DIR / name
        if not path.is_file():
            result["file_registry_matches"][name] = "missing"
            continue
        if path.stat().st_size > 64 * 1024 * 1024:
            result["file_registry_matches"][name] = "skipped_large"
            continue
        result["file_registry_matches"][name] = sha256_file(path) == expected
    return result


def live_marker() -> dict[str, object]:
    marker = INDEX_ROOT / ".canonical-v2-isolated-index-target.json"
    result: dict[str, object] = {"path": str(marker), "exists": marker.is_file()}
    if not marker.is_file():
        return result
    payload = json.loads(marker.read_text(encoding="utf-8"))
    result["sha256"] = sha256_file(marker)
    result["target_kind"] = payload.get("target_kind")
    result["release_id"] = payload.get("release_id")
    result["root"] = payload.get("root")
    return result


def sqlite_probe(path: Path) -> dict[str, object]:
    result: dict[str, object] = {"path": str(path), "exists": path.is_file()}
    if not path.is_file():
        return result
    result["bytes"] = path.stat().st_size
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result
    try:
        with connection:
            integrity = connection.execute("PRAGMA quick_check").fetchone()
            result["quick_check"] = integrity[0] if integrity else None
            tables = [
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            ]
            counts = {}
            for table in tables:
                if table.startswith("sqlite_"):
                    continue
                try:
                    counts[table] = connection.execute(
                        f'SELECT COUNT(*) FROM "{table}"'
                    ).fetchone()[0]
                except sqlite3.Error as exc:
                    counts[table] = f"error:{type(exc).__name__}"
            result["tables"] = counts
            meta = {}
            if "workspace_meta" in tables:
                meta = dict(
                    connection.execute(
                        "SELECT key, value FROM workspace_meta"
                    ).fetchall()
                )
            result["workspace_meta"] = meta
    finally:
        connection.close()
    return result


def disk() -> list[dict[str, object]]:
    out = []
    for label, path in (
        ("root_fs", Path("/")),
        ("var_tmp", Path("/var/tmp")),
        ("md1", Path("/md1")),
    ):
        try:
            usage = os.statvfs(path)
        except OSError as exc:
            out.append({"label": label, "error": type(exc).__name__})
            continue
        total = usage.f_blocks * usage.f_frsize
        free = usage.f_bavail * usage.f_frsize
        out.append(
            {
                "label": label,
                "path": str(path),
                "total_bytes": total,
                "free_bytes": free,
                "used_percent": round(100 * (1 - free / total), 1) if total else None,
            }
        )
    return out


def manual_recall() -> dict[str, object]:
    directory = Path("/var/tmp/mirothinker-data-v2/manual-recall-v1")
    result: dict[str, object] = {"path": str(directory), "exists": directory.is_dir()}
    if not directory.is_dir():
        return result
    files = sorted(entry.name for entry in directory.iterdir())
    result["files"] = files
    result["entry_count"] = len(files)
    return result


def collection_scripts() -> list[dict[str, object]]:
    out = []
    for name in COLLECTION_SCRIPTS:
        path = REPO / "apps" / "miroflow-agent" / "scripts" / name
        out.append({"name": name, "exists": path.is_file()})
    return out


def crontab() -> dict[str, object]:
    completed = subprocess.run(
        ["crontab", "-l"], capture_output=True, text=True, check=False
    )
    lines = [
        line.strip()
        for line in completed.stdout.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    return {
        "returncode": completed.returncode,
        "lines": [
            SENSITIVE_RE.sub("<redacted>", line) for line in lines
        ],
    }


def main() -> int:
    payload = {
        "generated_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(),
        "repo": str(REPO),
        "live_process_env": live_env(),
        "probe_process_env": current_process_env(),
        "key_files": key_files(),
        "pack_manifest": pack_manifest(),
        "live_index_marker": live_marker(),
        "sqlite": {
            label: sqlite_probe(path) for label, path in SQLITE_TARGETS
        },
        "big_files": [
            {
                "label": label,
                "path": str(path),
                "exists": path.is_file(),
                "bytes": path.stat().st_size if path.is_file() else None,
            }
            for label, path in BIG_FILES
        ],
        "disk": disk(),
        "manual_recall": manual_recall(),
        "collection_scripts": collection_scripts(),
        "crontab": crontab(),
    }
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
