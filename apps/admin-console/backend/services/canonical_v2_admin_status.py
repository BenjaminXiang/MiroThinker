"""Read-only system-status and provider-health collection for the admin surface.

Every block degrades independently: an unreadable store, an absent build-time
database, or a missing marker all become ``state: "unavailable"`` with a reason
instead of an exception. No block fabricates a value for a source it could not
read, and no block ever returns credential material.

The live 18188 service is never started, restarted, or reconfigured here — the
module only reads files, SQLite databases, and process-independent manifests.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
from typing import Any
from urllib.parse import urlsplit

from backend.deps import resolve_console_dsn
from src.data_agents.canonical_v2.managed_config import (
    PUBLIC_DOMAINS,
    ManagedSettingsStore,
)


INDEX_MARKER_FILENAME = ".canonical-v2-isolated-index-target.json"
_HASH_CHUNK = 8 * 1024 * 1024

_SQLITE_PATHS: tuple[tuple[str, str], ...] = (
    ("access_log", "CANONICAL_V2_ACCESS_LOG_DB"),
    ("corrections", "CANONICAL_V2_CORRECTIONS_DB"),
    ("lookup", "CANONICAL_V2_LOOKUP_DB"),
)
_MANUAL_RECALL_ENV = "CANONICAL_V2_MANUAL_RECALL_DIR"
_SERVING_PACK_ENV = "CANONICAL_V2_SERVING_PACK"
_INDEX_ROOT_ENV = "CANONICAL_V2_INDEX_ROOT"
_INDEX_MARKER_SHA256_ENV = "CANONICAL_V2_INDEX_MARKER_SHA256"
_DISK_PATHS: tuple[tuple[str, str], ...] = (
    ("data_root", "/var/tmp"),
    ("system_root", "/"),
    ("bulk_storage", "/md1"),
)


class ProviderSpec:
    """One provider's credential resolution order (env names, then key files)."""

    __slots__ = ("key", "label", "env_names", "key_files", "probe_url")

    def __init__(
        self,
        *,
        key: str,
        label: str,
        env_names: tuple[str, ...],
        key_files: tuple[str, ...],
        probe_url: str | None,
    ) -> None:
        self.key = key
        self.label = label
        self.env_names = env_names
        self.key_files = key_files
        self.probe_url = probe_url


# Resolution mirrors the providers themselves (env first, then the approved
# repository-root key file). Read-only: the health check never writes anything.
PROVIDERS: tuple[ProviderSpec, ...] = (
    ProviderSpec(
        key="bocha",
        label="Bocha 博查 Web 搜索",
        env_names=("BOCHA_API_KEY",),
        key_files=(".bocha_api_key",),
        probe_url="https://api.bochaai.com/v1/web-search",
    ),
    ProviderSpec(
        key="serper",
        label="Serper Web 搜索",
        env_names=("SERPER_API_KEY",),
        key_files=(".serper_api_key",),
        probe_url="https://google.serper.dev/search",
    ),
    ProviderSpec(
        key="deepseek",
        label="DeepSeek LLM (active chat profile)",
        env_names=("DEEPSEEK_API_KEY",),
        key_files=(".deepseek_api_key",),
        probe_url="https://api.deepseek.com/v1/models",
    ),
    ProviderSpec(
        key="dashscope",
        label="DashScope 在线模型档",
        env_names=("DASHSCOPE_API_KEY",),
        key_files=(".dashscope_api_key",),
        probe_url="https://dashscope.aliyuncs.com/compatible-mode/v1/models",
    ),
    ProviderSpec(
        key="local_llm",
        label="本地/校内 LLM (SGLang)",
        env_names=("API_KEY", "LOCAL_LLM_API_KEY"),
        key_files=(".sglang_api_key",),
        probe_url=None,
    ),
    ProviderSpec(
        key="openalex",
        label="OpenAlex",
        env_names=("OPENALEX_API_KEY", "OPENALEX_KEY"),
        key_files=(),
        probe_url="https://api.openalex.org/works?per-page=1",
    ),
    ProviderSpec(
        key="semantic_scholar",
        label="Semantic Scholar",
        env_names=("SEMANTIC_SCHOLAR_API_KEY", "S2_API_KEY"),
        key_files=(),
        probe_url="https://api.semanticscholar.org/graph/v1/paper/search?query=test&limit=1",
    ),
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.astimezone(timezone.utc).isoformat()


def _seconds_since(value: datetime | None, *, now: datetime) -> int | None:
    if value is None:
        return None
    return max(0, int((now - value.astimezone(timezone.utc)).total_seconds()))


def ok(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {"state": "ok", **payload}


def unavailable(reason: str, **extra: Any) -> dict[str, Any]:
    return {"state": "unavailable", "reason": reason, **extra}


def sha256_file(path: Path, *, chunk: int = _HASH_CHUNK) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(chunk)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


# -- pack / index ------------------------------------------------------------


def _pack_dir(environ: Mapping[str, str]) -> Path | None:
    raw = environ.get(_SERVING_PACK_ENV, "").strip()
    return Path(raw) if raw else None


def collect_pack(
    *,
    environ: Mapping[str, str],
    manifest: Any | None = None,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    """Report pack identity. The runtime manifest (when installed) is authoritative."""

    pack_dir = _pack_dir(environ)
    block: dict[str, Any] = {
        "pack_dir": None if pack_dir is None else str(pack_dir),
        "release_id": None,
        "pack_id": None,
        "schema_version": None,
        "generated_at": None,
        "build_created_at": None,
        "manifest_version": None,
        "build_run_id": None,
        "manifest_sha256": None,
        "embedding_model_id": None,
        "record_counts": {},
        "as_of": _iso(as_of),
    }
    if manifest is not None:
        record_counts = {
            _projection_key(projection): projection.record_count
            for projection in getattr(manifest, "published_projections", ())
        }
        block.update(
            {
                "state": "ok",
                "release_id": getattr(manifest, "release_id", None),
                "manifest_version": getattr(manifest, "manifest_version", None),
                "build_run_id": getattr(manifest, "build_run_id", None),
                "build_created_at": _iso(getattr(manifest, "created_at", None)),
                "manifest_sha256": getattr(manifest, "manifest_sha256", None),
                "record_counts": record_counts,
                "source": "runtime_manifest",
            }
        )
        return block
    if pack_dir is None:
        return unavailable(
            f"{_SERVING_PACK_ENV} is not set and no runtime manifest is installed",
            **block,
        )
    manifest_path = pack_dir / "manifest.json"
    try:
        payload = _read_json(manifest_path)
    except (OSError, ValueError) as exc:
        return unavailable(
            f"pack manifest is unreadable ({type(exc).__name__})", **block
        )
    build = payload.get("build_manifest") or {}
    block.update(
        {
            "state": "ok",
            "release_id": payload.get("release_id"),
            "pack_id": payload.get("pack_id"),
            "schema_version": payload.get("schema_version"),
            "generated_at": payload.get("generated_at"),
            "embedding_model_id": payload.get("embedding_model_id"),
            "manifest_version": build.get("manifest_version"),
            "build_run_id": build.get("build_run_id"),
            "build_created_at": build.get("created_at"),
            "manifest_sha256": (payload.get("release_verification") or {}).get(
                "manifest_sha256"
            ),
            "record_counts": {
                projection.get("projection_id") or projection.get("domain"): projection.get(
                    "record_count"
                )
                for projection in build.get("published_projections", [])
            },
            "source": "pack_manifest",
        }
    )
    return block


def _projection_key(projection: Any) -> str:
    for attribute in ("projection_id", "domain", "entity_type"):
        value = getattr(projection, attribute, None)
        if value:
            return str(value)
    return "unknown"


def collect_index_marker(
    *, environ: Mapping[str, str], expected_marker_sha256: str | None = None
) -> dict[str, Any]:
    """Compare the live index marker against the value the release binds.

    The expected value comes from the release-binding pack manifest (the same
    value the serving loader verifies at startup) or from
    ``CANONICAL_V2_INDEX_MARKER_SHA256``; a caller-supplied value wins.
    """

    roots: list[Path] = []
    raw_root = environ.get(_INDEX_ROOT_ENV, "").strip()
    if raw_root:
        roots.append(Path(raw_root))
    pack_dir = _pack_dir(environ)
    pack_manifest: Mapping[str, Any] = {}
    if pack_dir is not None:
        try:
            pack_manifest = _read_json(pack_dir / "manifest.json")
        except (OSError, ValueError):
            pack_manifest = {}
        declared = pack_manifest.get("index_root")
        if isinstance(declared, str) and declared.strip():
            roots.append(Path(declared))
    if expected_marker_sha256 is None:
        for candidate in (
            pack_manifest.get("index_marker_sha256"),
            environ.get(_INDEX_MARKER_SHA256_ENV, "").strip(),
        ):
            if isinstance(candidate, str) and candidate.strip():
                expected_marker_sha256 = candidate.strip()
                break
    if not roots:
        return unavailable(
            f"neither {_INDEX_ROOT_ENV} nor a serving pack manifest names the index root"
        )
    root = roots[0]
    marker = root / INDEX_MARKER_FILENAME
    if not marker.is_file():
        return unavailable(f"index marker is missing at {marker}", index_root=str(root))
    try:
        observed = sha256_file(marker)
        payload = _read_json(marker)
    except (OSError, ValueError) as exc:
        return unavailable(
            f"index marker is unreadable ({type(exc).__name__})", index_root=str(root)
        )
    block: dict[str, Any] = {
        "index_root": str(root),
        "marker_path": str(marker),
        "observed_sha256": observed,
        "target_kind": payload.get("target_kind"),
        "release_id": payload.get("release_id"),
    }
    if expected_marker_sha256:
        block["expected_sha256"] = expected_marker_sha256
        block["source"] = "release_binding"
        if observed != expected_marker_sha256:
            return unavailable(
                "live index marker differs from the release-bound value", **block
            )
    else:
        block["expected_sha256"] = None
        block["source"] = "disk_only"
    return ok(block)


# -- freshness ---------------------------------------------------------------


def _sqlite_path(environ: Mapping[str, str], env_name: str) -> Path | None:
    raw = environ.get(env_name, "").strip()
    return Path(raw) if raw else None


_LOOKUP_FILENAMES = ("lookup.sqlite3",)


def _default_lookup_path(environ: Mapping[str, str]) -> Path | None:
    """Resolve the live lookup database without a dedicated env variable.

    The serving process receives its index root as a CLI pin, so the panel
    falls back to the index root named by ``CANONICAL_V2_INDEX_ROOT``, the
    serving pack manifest, or the servicing-pack directory itself.
    """

    candidates: list[Path] = []
    raw_root = environ.get(_INDEX_ROOT_ENV, "").strip()
    if raw_root:
        candidates.append(Path(raw_root))
    pack_dir = _pack_dir(environ)
    if pack_dir is not None:
        candidates.append(pack_dir)
        try:
            declared = _read_json(pack_dir / "manifest.json").get("index_root")
        except (OSError, ValueError):
            declared = None
        if isinstance(declared, str) and declared.strip():
            candidates.append(Path(declared))
    for root in candidates:
        for filename in _LOOKUP_FILENAMES:
            candidate = root / filename
            if candidate.is_file():
                return candidate
    return None


def _query(sqlite_path: Path, sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    connection = sqlite3.connect(
        f"file:{sqlite_path}?mode=ro", uri=True, timeout=5
    )
    try:
        return list(connection.execute(sql, params).fetchall())
    finally:
        connection.close()


def collect_corrections(environ: Mapping[str, str]) -> dict[str, Any]:
    path = _sqlite_path(environ, "CANONICAL_V2_CORRECTIONS_DB")
    if path is None:
        return unavailable("CANONICAL_V2_CORRECTIONS_DB is not set")
    if not path.is_file():
        return unavailable(f"corrections database is missing at {path}")
    try:
        rows = _query(
            path,
            "SELECT domain, status, COUNT(*), MAX(created_at) "
            "FROM field_corrections GROUP BY domain, status",
        )
        by_domain: dict[str, dict[str, Any]] = {}
        active = reverted = 0
        latest: str | None = None
        for domain, status, count, max_created in rows:
            bucket = by_domain.setdefault(
                str(domain), {"active": 0, "reverted": 0, "latest_at": None}
            )
            bucket[str(status)] = int(count)
            if max_created and (bucket["latest_at"] is None or max_created > bucket["latest_at"]):
                bucket["latest_at"] = max_created
            if str(status) == "active":
                active += int(count)
            else:
                reverted += int(count)
            if max_created and (latest is None or max_created > latest):
                latest = max_created
        added = _query(
            path,
            "SELECT domain, status, COUNT(*) FROM added_records GROUP BY domain, status",
        )
        added_total = sum(int(row[2]) for row in added)
    except sqlite3.Error as exc:
        return unavailable(f"corrections query failed ({type(exc).__name__})")
    return ok(
        {
            "path": str(path),
            "active": active,
            "reverted": reverted,
            "added_records": added_total,
            "latest_at": latest,
            "by_domain": by_domain,
        }
    )


def collect_manual_recall(environ: Mapping[str, str]) -> dict[str, Any]:
    raw = environ.get(_MANUAL_RECALL_ENV, "").strip()
    if not raw:
        return unavailable(f"{_MANUAL_RECALL_ENV} is not set")
    directory = Path(raw)
    if not directory.is_dir():
        return unavailable(f"manual-recall directory is missing at {directory}")
    try:
        entries = sorted(item.name for item in directory.iterdir())
    except OSError as exc:
        return unavailable(f"manual-recall directory is unreadable ({type(exc).__name__})")
    payload: dict[str, Any] = {
        "path": str(directory),
        "entry_count": len(entries),
        "entries": entries[:20],
    }
    sidecar = directory / "manual-recall.json"
    if sidecar.is_file():
        try:
            document = _read_json(sidecar)
            points = document.get("points") if isinstance(document, Mapping) else None
            if isinstance(points, Mapping):
                active = [p for p in points.values() if p.get("status") == "active"]
                payload["active_points"] = len(active)
        except (OSError, ValueError):
            payload["active_points"] = None
    return ok(payload)


def collect_access_log(environ: Mapping[str, str]) -> dict[str, Any]:
    path = _sqlite_path(environ, "CANONICAL_V2_ACCESS_LOG_DB")
    if path is None:
        return unavailable("CANONICAL_V2_ACCESS_LOG_DB is not set")
    if not path.is_file():
        return unavailable(f"access-log database is missing at {path}")
    try:
        sessions = _query(path, "SELECT COUNT(*) FROM sessions")[0][0]
        turns = _query(path, "SELECT COUNT(*) FROM turns")[0][0]
        latest = _query(path, "SELECT MAX(last_active_at) FROM sessions")[0][0]
        earliest = _query(path, "SELECT MIN(started_at) FROM sessions")[0][0]
    except sqlite3.Error as exc:
        return unavailable(f"access-log query failed ({type(exc).__name__})")
    return ok(
        {
            "path": str(path),
            "sessions": int(sessions),
            "turns": int(turns),
            "latest_at": latest,
            "earliest_at": earliest,
        }
    )


def collect_freshness(
    *,
    environ: Mapping[str, str],
    record_counts: Mapping[str, Any],
    as_of: datetime | None,
    build_created_at: str | None,
    now: datetime,
) -> dict[str, Any]:
    """Artifact-derived per-domain freshness plus the build-time view.

    The serving host has no build-time ``pipeline_run`` source (design §2.6), so
    the collection-history block reports ``unavailable`` with that reason rather
    than inventing a timestamp.
    """

    as_of_dt = as_of.astimezone(timezone.utc) if as_of is not None else None
    build_dt: datetime | None = None
    if build_created_at:
        try:
            build_dt = datetime.fromisoformat(build_created_at.replace("Z", "+00:00"))
        except ValueError:
            build_dt = None
    per_domain = {
        domain: {
            "record_count": record_counts.get(f"published:{domain}"),
            "pack_build_at": _iso(build_dt),
            "pack_build_age_seconds": _seconds_since(build_dt, now=now),
            "projection_as_of": _iso(as_of_dt),
            "projection_age_seconds": _seconds_since(as_of_dt, now=now),
        }
        for domain in PUBLIC_DOMAINS
    }
    database_url = resolve_console_dsn(environ)
    if database_url:
        collection_history: dict[str, Any] = unavailable(
            "build-time pipeline_run history is not readable from this process",
        )
    else:
        collection_history = unavailable(
            "DATABASE_URL is not set: the build-time pipeline_run "
            "history lives in the build/release database, not on the serving host",
        )
    return ok(
        {
            "pack_build_at": _iso(build_dt),
            "pack_build_age_seconds": _seconds_since(build_dt, now=now),
            "projection_as_of": _iso(as_of_dt),
            "projection_age_seconds": _seconds_since(as_of_dt, now=now),
            "per_domain": per_domain,
            "collection_history": collection_history,
        }
    )


# -- storage / disk ----------------------------------------------------------


def _sqlite_health(path: Path) -> dict[str, Any]:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    try:
        with connection:
            integrity = connection.execute("PRAGMA quick_check").fetchone()
            tables = [
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                ).fetchall()
            ]
            counts: dict[str, Any] = {}
            for table in tables:
                if table.startswith("sqlite_"):
                    continue
                try:
                    counts[table] = int(
                        connection.execute(
                            f'SELECT COUNT(*) FROM "{table}"'
                        ).fetchone()[0]
                    )
                except sqlite3.Error as exc:
                    counts[table] = f"error:{type(exc).__name__}"
            meta: dict[str, Any] = {}
            if "workspace_meta" in tables:
                meta = {
                    str(key): value
                    for key, value in connection.execute(
                        "SELECT key, value FROM workspace_meta"
                    ).fetchall()
                }
    finally:
        connection.close()
    return {
        "quick_check": integrity[0] if integrity else None,
        "tables": counts,
        "workspace_meta": meta,
    }


def collect_storage(environ: Mapping[str, str]) -> dict[str, Any]:
    sources: dict[str, Any] = {}
    for label, env_name in _SQLITE_PATHS:
        path = _sqlite_path(environ, env_name)
        if path is None and label == "lookup":
            path = _default_lookup_path(environ)
        if path is None:
            sources[label] = unavailable(
                f"{env_name} is not set and no index root declares a lookup database"
            )
            continue
        if not path.is_file():
            sources[label] = unavailable(f"database is missing at {path}", path=str(path))
            continue
        try:
            health = _sqlite_health(path)
        except sqlite3.Error as exc:
            sources[label] = unavailable(
                f"SQLite open failed ({type(exc).__name__})", path=str(path)
            )
            continue
        sources[label] = ok(
            {
                "path": str(path),
                "bytes": path.stat().st_size,
                "env_var": env_name,
                **health,
            }
        )
    pack_dir = _pack_dir(environ)
    if pack_dir is None:
        sources["pack"] = unavailable(f"{_SERVING_PACK_ENV} is not set")
    elif not pack_dir.is_dir():
        sources["pack"] = unavailable(f"serving pack directory is missing at {pack_dir}")
    else:
        members = {}
        try:
            for member in sorted(pack_dir.iterdir()):
                try:
                    if member.is_file():
                        members[member.name] = member.stat().st_size
                except OSError:
                    continue
        except OSError as exc:
            sources["pack"] = unavailable(
                f"serving pack directory is unreadable ({type(exc).__name__})",
                path=str(pack_dir),
            )
        else:
            sources["pack"] = ok({"path": str(pack_dir), "members": members})
    marker_root = collect_index_marker(environ=environ)
    if marker_root.get("state") == "ok":
        index_root = Path(str(marker_root["index_root"]))
        members = {}
        try:
            for member in sorted(index_root.iterdir()):
                try:
                    if member.is_file():
                        members[member.name] = member.stat().st_size
                except OSError:
                    continue
        except OSError as exc:
            sources["index_root"] = unavailable(
                f"index root is unreadable ({type(exc).__name__})", path=str(index_root)
            )
        else:
            sources["index_root"] = ok(
                {
                    "path": str(index_root),
                    "members": members,
                    "milvus_db": _milvus_health(index_root / "milvus.db"),
                }
            )
    else:
        sources["index_root"] = unavailable(
            "index root could not be resolved", reason_detail=marker_root.get("reason")
        )
    return {"state": "ok", "sources": sources}


def _milvus_health(path: Path) -> dict[str, Any]:
    """Presence and size only: the file is held open by the live server."""

    if not path.is_file():
        return {"state": "unavailable", "reason": "milvus.db is missing"}
    try:
        stat = path.stat()
    except OSError as exc:
        return {"state": "unavailable", "reason": type(exc).__name__}
    lock = path.with_name(".milvus.db.lock")
    try:
        modified_at = _iso(datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc))
    except (OSError, OverflowError, ValueError):
        modified_at = None
    return {
        "state": "ok",
        "path": str(path),
        "bytes": stat.st_size,
        "modified_at": modified_at,
        "lock_present": lock.exists(),
    }


def collect_disk() -> dict[str, Any]:
    volumes = []
    for label, raw in _DISK_PATHS:
        path = Path(raw)
        if not path.exists():
            volumes.append({"label": label, "path": raw, "state": "unavailable"})
            continue
        try:
            usage = shutil.disk_usage(path)
        except OSError as exc:
            volumes.append(
                {
                    "label": label,
                    "path": raw,
                    "state": "unavailable",
                    "reason": type(exc).__name__,
                }
            )
            continue
        volumes.append(
            {
                "label": label,
                "path": raw,
                "state": "ok",
                "total_bytes": usage.total,
                "free_bytes": usage.free,
                "used_percent": round(100 * (usage.total - usage.free) / usage.total, 1)
                if usage.total
                else None,
            }
        )
    readable = [volume for volume in volumes if volume["state"] == "ok"]
    if not readable:
        return unavailable("no configured volume is readable", volumes=volumes)
    return ok({"volumes": volumes})


def collect_system_status(
    *,
    store: ManagedSettingsStore,
    environ: Mapping[str, str],
    manifest: Any | None = None,
    as_of: datetime | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Assemble the full panel. Never raises for a single unreadable source."""

    moment = now or _now()
    pack = collect_pack(environ=environ, manifest=manifest, as_of=as_of)
    marker = collect_index_marker(environ=environ)
    try:
        effective, fields = store.effective()
        config_block: dict[str, Any] = ok(
            {
                "path": str(store.path),
                "exists": store.exists(),
                "schema_version": effective.schema_version,
                "fields": [field.as_dict() for field in fields],
            }
        )
    except Exception as exc:  # noqa: BLE001 - a broken config file must not 5xx
        config_block = unavailable(
            f"managed configuration is unreadable ({type(exc).__name__})",
            path=str(store.path),
        )
    collection = effective.collection if config_block["state"] == "ok" else None
    retention = effective.paths.access_log_retention_days if collection else None
    return {
        "state": "ok",
        "generated_at": _iso(moment),
        "pack": pack,
        "index_marker": marker,
        "freshness": collect_freshness(
            environ=environ,
            record_counts=pack.get("record_counts") or {},
            as_of=as_of,
            build_created_at=pack.get("build_created_at"),
            now=moment,
        ),
        "operations": {
            "state": "ok",
            "corrections": collect_corrections(environ),
            "manual_recall": collect_manual_recall(environ),
            "access_log": collect_access_log(environ),
            "access_log_retention_days": retention,
        },
        "storage": collect_storage(environ),
        "disk": collect_disk(),
        "config": config_block,
        "collection": (
            collection.model_dump(mode="json") if collection is not None else None
        ),
    }


def _bound_marker_sha256(environ: Mapping[str, str]) -> str | None:
    raw = environ.get(_INDEX_MARKER_SHA256_ENV, "").strip()
    return raw or None


# -- providers ---------------------------------------------------------------


def _key_file_roots(environ: Mapping[str, str]) -> tuple[Path, ...]:
    roots: list[Path] = []
    for env_name in ("CANONICAL_V2_KEY_ROOTS", "CANONICAL_V2_KEY_ROOT"):
        raw = environ.get(env_name, "").strip()
        if raw:
            roots.extend(Path(part) for part in raw.split(os.pathsep) if part)
    here = Path(__file__).resolve()
    # Walk every ancestor so a key file placed above the checkout root (for
    # example the main checkout while serving from a git worktree) still
    # resolves — the same convention `professor/llm_profiles.py` uses.
    roots.extend(here.parents)
    roots.append(Path.cwd())
    roots.extend(Path.cwd().parents)
    seen: list[Path] = []
    for root in roots:
        if root not in seen:
            seen.append(root)
    return tuple(seen)


def resolve_provider_key(
    spec: ProviderSpec, *, environ: Mapping[str, str]
) -> tuple[str, str | None]:
    """Return ``(material, origin)`` without ever logging or returning it."""

    for env_name in spec.env_names:
        value = environ.get(env_name, "").strip()
        if value:
            return value, f"env:{env_name}"
    for root in _key_file_roots(environ):
        for filename in spec.key_files:
            candidate = root / filename
            try:
                if not candidate.is_file():
                    continue
                value = candidate.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if value:
                return value, f"file:{filename}"
    return "", None


def provider_status(
    *,
    environ: Mapping[str, str],
    probe: Callable[[str, str], tuple[bool, str]] | None = None,
) -> list[dict[str, Any]]:
    results = []
    for spec in PROVIDERS:
        material, origin = resolve_provider_key(spec, environ=environ)
        entry: dict[str, Any] = {
            "key": spec.key,
            "label": spec.label,
            "configured": bool(material),
            "suffix4": material[-4:] if material else None,
            "origin": origin,
            "reachable": None,
            "detail": None,
        }
        if not material:
            entry["detail"] = "未配置（env 与 key 文件均缺失）"
        elif probe is not None and spec.probe_url:
            try:
                reachable, detail = probe(spec.probe_url, material)
            except Exception as exc:  # noqa: BLE001 - a probe failure is a result
                reachable, detail = False, f"probe failed ({type(exc).__name__})"
            entry["reachable"] = reachable
            entry["detail"] = detail
        results.append(entry)
    return results


def probe_http(url: str, api_key: str, *, timeout: float = 5.0) -> tuple[bool, str]:
    """One bounded, credential-safe reachability probe.

    Only the HTTP status (or transport error class) is reported; the body is
    discarded so nothing credential-bearing can leak into a response.
    """

    import urllib.error
    import urllib.request

    host = urlsplit(url).netloc
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return True, f"{host} → HTTP {response.status}"
    except urllib.error.HTTPError as exc:
        # 401/403 still proves the endpoint is reachable and the key was sent.
        verdict = exc.code not in {401, 403}
        return verdict, f"{host} → HTTP {exc.code}"
    except urllib.error.URLError as exc:
        return False, f"{host} → {type(exc.reason).__name__}"
    except OSError as exc:
        return False, f"{host} → {type(exc).__name__}"


__all__ = [
    "PROVIDERS",
    "ProviderSpec",
    "collect_access_log",
    "collect_corrections",
    "collect_disk",
    "collect_freshness",
    "collect_index_marker",
    "collect_manual_recall",
    "collect_pack",
    "collect_storage",
    "collect_system_status",
    "ok",
    "probe_http",
    "provider_status",
    "resolve_provider_key",
    "sha256_file",
    "unavailable",
]
