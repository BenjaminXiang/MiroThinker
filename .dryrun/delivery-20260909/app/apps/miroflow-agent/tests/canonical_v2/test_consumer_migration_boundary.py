"""RED owner for the complete S11B legacy-consumer quarantine DAG."""

from __future__ import annotations

import ast
from collections.abc import Callable
import copy
from dataclasses import dataclass
import hashlib
import importlib
import inspect
import json
from pathlib import Path
import re
import subprocess
import sys
from types import ModuleType
from typing import Any

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[4]
_INVENTORY_CATEGORIES = (
    "retired_http_routers",
    "retired_frontend_routes",
    "legacy_modules",
    "legacy_scripts",
    "sanctioned_entrypoints",
)
_INVENTORY_KEYS = frozenset({"schema_version", *_INVENTORY_CATEGORIES})
_INVENTORY_VERSION = "canonical-v2-legacy-consumer-inventory-v1"
_RETIRED_DISPOSITIONS = frozenset({"reference_only", "replaced", "s11c_disposition"})
_SCRIPT_ROOTS = (
    _REPO_ROOT / "apps/admin-console/scripts",
    _REPO_ROOT / "apps/miroflow-agent/scripts",
)
_SANCTIONED_CLI_PATHS = frozenset(
    {
        "apps/admin-console/scripts/run_canonical_v2_review.py",
        "apps/admin-console/scripts/smoke_canonical_v2_candidate.py",
        "apps/miroflow-agent/scripts/capture_canonical_v2_s11b_baseline.py",
        "apps/miroflow-agent/scripts/run_canonical_v2_evidence_ingest.py",
    }
)
_EXPECTED_SANCTIONED_IDENTITIES = frozenset(
    {
        "module:backend.api.canonical_v2_chat",
        "module:backend.api.canonical_v2_consumers",
        "module:backend.api.canonical_v2_operations",
        "module:backend.api.canonical_v2_review",
        *(f"path:{path}" for path in _SANCTIONED_CLI_PATHS),
    }
)
_PRE_S11B_PATH_LIST_SHA256 = (
    "9235ceaf2bade6ae5012dc2db74d7ab5c994ba0151ea7cf40c602bfcdd0aa654"
)
_PRE_S11B_PATH_AND_SHA256_DIGEST = (
    "9512e595fc49d9b3b7d2cce789d72b2ea4e8421e1c4e8b5d34de7541bc3569d3"
)
_FORBIDDEN_IMPORT_PREFIXES = (
    "src.data_agents.canonical",
    "src.data_agents.company.canonical_import",
    "src.data_agents.company.release",
    "src.data_agents.company.vectorizer",
    "src.data_agents.professor.canonical_writer",
    "src.data_agents.professor.release",
    "src.data_agents.professor.vectorizer",
    "src.data_agents.paper.canonical_writer",
    "src.data_agents.paper.identity_status_writer",
    "src.data_agents.paper.quality_promotion",
    "src.data_agents.paper.release",
    "src.data_agents.patent.canonical_writer",
    "src.data_agents.patent.quality_promotion",
    "src.data_agents.patent.release",
    "src.data_agents.patent.vectorizer",
    "src.data_agents.service.retrieval",
    "src.data_agents.service.search_service",
    "src.data_agents.publish",
    "src.data_agents.paper.milvus_backfill",
    "src.data_agents.storage.milvus_collections",
    "src.data_agents.storage.milvus_store",
    "backend.api.chat",
    "backend.deps",
)
_LEGACY_BODY_MARKERS = (
    "canonical_writer",
    "canonical_import",
    "quality_promotion",
    "get_retrieval_service",
    "RetrievalService",
    "milvus_backfill",
    "milvus_collections",
    "milvus_store",
    "MILVUS_COLLECTION",
)
_LEGACY_SCHEMA_RE = re.compile(r"\bV0(?:0[1-9]|[1-3][0-9]|4[0-2])\b", re.IGNORECASE)
_LEGACY_DML_RE = re.compile(
    # UPDATE must be followed by a table reference, not a Python keyword
    # argument (model_copy(update=...)); the other verbs are unambiguous.
    r"\b(?:INSERT\s+INTO|UPDATE\s+(?!\=)|DELETE\s+FROM|ALTER\s+TABLE|DROP\s+TABLE)\b",
    re.IGNORECASE,
)
_FIXED_COLLECTION_RE = re.compile(
    r"\b(?:professor_identity|professor_research|paper_chunks|patent_chunks|company_chunks)\b",
    re.IGNORECASE,
)
_LEGACY_PROCESS_TARGETS = (
    "run_company_release_e2e.py",
    "run_professor_release_e2e.py",
    "run_paper_release_e2e.py",
    "run_patent_release_e2e.py",
    "run_quality_promote.py",
    "run_paper_identity_scan.py",
    "run_professor_publish_to_search.py",
    "run_milvus_backfill.py",
    "run_cross_domain_search_e2e.py",
    "run_retrieval_chat_acceptance.py",
    "run_professor_retrieval_top5_eval.py",
    "eval_recall.py",
)


class _MissingS11BLegacyInventory(AssertionError):
    """The complete S11B inventory and sanctioned-entrypoint DAG is absent."""


@dataclass(frozen=True, slots=True)
class _S11BBoundarySeam:
    load_inventory: Callable[..., Any]
    inventory_path: Path
    sanctioned_paths: tuple[Path, ...]


def _import_required_module(module_name: str) -> ModuleType:
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name != module_name:
            raise
        raise _MissingS11BLegacyInventory(
            f"missing required S11B module: {module_name}"
        ) from exc


def _required_attribute(module: ModuleType, attribute: str) -> Any:
    try:
        return vars(module)[attribute]
    except KeyError as exc:
        raise _MissingS11BLegacyInventory(
            f"missing required S11B seam: {module.__name__}.{attribute}"
        ) from exc


def _require_file_metadata(label: str, path: Path) -> Path:
    if not path.is_file():
        raise _MissingS11BLegacyInventory(
            f"missing required S11B {label}: {path.relative_to(_REPO_ROOT)}"
        )
    return path


def _load_s11b_boundary_seam() -> _S11BBoundarySeam:
    quarantine_module = _import_required_module(
        "src.data_agents.canonical_v2.legacy_consumer_quarantine"
    )
    load_inventory = _required_attribute(
        quarantine_module,
        "load_legacy_consumer_inventory",
    )

    inventory_path = _require_file_metadata(
        "inventory",
        _REPO_ROOT / "apps/miroflow-agent/src/data_agents/canonical_v2/catalogs/"
        "legacy-consumer-inventory-v1.json",
    )
    sanctioned_paths = (
        _require_file_metadata(
            "evidence-ingest CLI",
            _REPO_ROOT
            / "apps/miroflow-agent/scripts/run_canonical_v2_evidence_ingest.py",
        ),
        _require_file_metadata(
            "evidence-ingest owner",
            _REPO_ROOT / "apps/miroflow-agent/tests/scripts/"
            "test_run_canonical_v2_evidence_ingest.py",
        ),
        _require_file_metadata(
            "candidate-smoke CLI",
            _REPO_ROOT / "apps/admin-console/scripts/smoke_canonical_v2_candidate.py",
        ),
        _require_file_metadata(
            "candidate-smoke owner",
            _REPO_ROOT
            / "apps/admin-console/tests/test_smoke_canonical_v2_candidate.py",
        ),
        _require_file_metadata(
            "baseline-capture CLI",
            _REPO_ROOT
            / "apps/miroflow-agent/scripts/capture_canonical_v2_s11b_baseline.py",
        ),
        _require_file_metadata(
            "baseline-capture owner",
            _REPO_ROOT / "apps/miroflow-agent/tests/scripts/"
            "test_capture_canonical_v2_s11b_baseline.py",
        ),
    )
    return _S11BBoundarySeam(
        load_inventory=load_inventory,
        inventory_path=inventory_path,
        sanctioned_paths=sanctioned_paths,
    )


def _mapping(value: Any, *, label: str) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if not isinstance(value, dict):
        raise AssertionError(f"{label} must expose a JSON object")
    return value


def _canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _canonical_identity(entry: dict[str, Any]) -> str:
    has_path = "path" in entry
    has_module = "module" in entry
    assert has_path ^ has_module, "inventory entries require exactly one path or module"
    key = "path" if has_path else "module"
    value = entry[key]
    assert isinstance(value, str) and value
    return f"{key}:{value}"


def _write_inventory(
    path: Path, payload: dict[str, Any], *, canonical: bool = True
) -> None:
    data = _canonical_json_bytes(payload)
    if not canonical:
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    path.write_bytes(data)


def _call_inventory_loader(
    load_inventory: Callable[..., Any],
    path: Path,
    *,
    repository_root: Path = _REPO_ROOT,
) -> Any:
    parameters = inspect.signature(load_inventory).parameters
    assert tuple(parameters) == ("inventory_path", "repository_root")
    repository_parameter = parameters["repository_root"]
    assert repository_parameter.kind is inspect.Parameter.KEYWORD_ONLY
    return load_inventory(path, repository_root=repository_root)


def _assert_loader_rejects(
    load_inventory: Callable[..., Any],
    path: Path,
    *,
    repository_root: Path = _REPO_ROOT,
) -> None:
    try:
        _call_inventory_loader(
            load_inventory,
            path,
            repository_root=repository_root,
        )
    except Exception:  # noqa: BLE001 - the contract specifies rejection, not a private error type.
        return
    raise AssertionError(f"inventory loader accepted invalid bytes: {path.name}")


def _first_entry(payload: dict[str, Any], *, identity: str) -> tuple[str, int]:
    for category in _INVENTORY_CATEGORIES:
        for index, entry in enumerate(payload[category]):
            if identity in entry:
                return category, index
    raise AssertionError(
        f"inventory needs at least one {identity} entry for negative coverage"
    )


def _assert_inventory_canonical_contract(
    load_inventory: Callable[..., Any],
    inventory_path: Path,
    tmp_path: Path,
) -> Any:
    raw = inventory_path.read_bytes()
    inventory = _call_inventory_loader(load_inventory, inventory_path)
    payload = _mapping(inventory, label="legacy inventory")

    assert set(payload) == _INVENTORY_KEYS
    assert payload["schema_version"] == _INVENTORY_VERSION
    assert raw.endswith(b"\n") and not raw.endswith(b"\n\n")
    assert raw == _canonical_json_bytes(payload)

    identities: list[str] = []
    for category in _INVENTORY_CATEGORIES:
        entries = payload[category]
        assert isinstance(entries, list)
        category_identities = [
            _canonical_identity(_mapping(entry, label=category)) for entry in entries
        ]
        assert category_identities == sorted(category_identities)
        identities.extend(category_identities)
        for entry in entries:
            item = _mapping(entry, label=category)
            assert isinstance(item.get("reason"), str) and item["reason"].strip()
            assert "replacement" in item
            assert item["replacement"] is None or (
                isinstance(item["replacement"], str) and item["replacement"].strip()
            )
            if category != "sanctioned_entrypoints":
                assert item.get("disposition") in _RETIRED_DISPOSITIONS
    assert len(identities) == len(set(identities))

    canonical_control = tmp_path / "canonical-control.json"
    _write_inventory(canonical_control, payload)
    control = _call_inventory_loader(load_inventory, canonical_control)
    assert _mapping(control, label="canonical control") == payload

    path_category, path_index = _first_entry(payload, identity="path")
    module_category, module_index = _first_entry(payload, identity="module")

    invalid_identities = (
        (path_category, path_index, "path", "/absolute.py"),
        (path_category, path_index, "path", "apps\\admin-console\\bad.py"),
        (path_category, path_index, "path", "./apps/admin-console/bad.py"),
        (path_category, path_index, "path", "apps/../bad.py"),
        (path_category, path_index, "path", "apps//bad.py"),
        (path_category, path_index, "path", "apps/bad\0.py"),
        (module_category, module_index, "module", "backend..api"),
        (module_category, module_index, "module", "backend.api.bad-name"),
    )
    for serial, (category, index, key, value) in enumerate(invalid_identities):
        variant = copy.deepcopy(payload)
        variant[category][index][key] = value
        candidate = tmp_path / f"invalid-identity-{serial}.json"
        _write_inventory(candidate, variant)
        _assert_loader_rejects(load_inventory, candidate)

    both = copy.deepcopy(payload)
    both[path_category][path_index]["module"] = "also.a.module"
    both_path = tmp_path / "both-identities.json"
    _write_inventory(both_path, both)
    _assert_loader_rejects(load_inventory, both_path)

    neither = copy.deepcopy(payload)
    neither[path_category][path_index].pop("path")
    neither_path = tmp_path / "neither-identity.json"
    _write_inventory(neither_path, neither)
    _assert_loader_rejects(load_inventory, neither_path)

    duplicate = copy.deepcopy(payload)
    duplicate[path_category].append(copy.deepcopy(duplicate[path_category][path_index]))
    duplicate_path = tmp_path / "duplicate.json"
    _write_inventory(duplicate_path, duplicate)
    _assert_loader_rejects(load_inventory, duplicate_path)

    cross_category = copy.deepcopy(payload)
    target_category = next(
        name for name in _INVENTORY_CATEGORIES if name != path_category
    )
    cross_category[target_category].append(
        copy.deepcopy(cross_category[path_category][path_index])
    )
    cross_path = tmp_path / "cross-category.json"
    _write_inventory(cross_path, cross_category)
    _assert_loader_rejects(load_inventory, cross_path)

    disposition = copy.deepcopy(payload)
    retired_category = next(
        name for name in _INVENTORY_CATEGORIES[:-1] if disposition[name]
    )
    disposition[retired_category][0]["disposition"] = "silently_enabled"
    disposition_path = tmp_path / "bad-disposition.json"
    _write_inventory(disposition_path, disposition)
    _assert_loader_rejects(load_inventory, disposition_path)

    replaced_category = next(
        name
        for name in _INVENTORY_CATEGORIES[:-1]
        if any(item["disposition"] == "replaced" for item in payload[name])
    )
    replaced_index = next(
        index
        for index, item in enumerate(payload[replaced_category])
        if item["disposition"] == "replaced"
    )
    reference_category = next(
        name
        for name in _INVENTORY_CATEGORIES[:-1]
        if any(item["disposition"] == "reference_only" for item in payload[name])
    )
    reference_index = next(
        index
        for index, item in enumerate(payload[reference_category])
        if item["disposition"] == "reference_only"
    )
    sanctioned_replacement = next(
        _canonical_identity(item) for item in payload["sanctioned_entrypoints"]
    )
    for label, category, index, replacement in (
        ("unsanctioned-replacement", replaced_category, replaced_index, "module:evil"),
        ("missing-replacement", replaced_category, replaced_index, None),
        (
            "reference-with-replacement",
            reference_category,
            reference_index,
            sanctioned_replacement,
        ),
    ):
        variant = copy.deepcopy(payload)
        variant[category][index]["replacement"] = replacement
        candidate = tmp_path / f"{label}.json"
        _write_inventory(candidate, variant)
        _assert_loader_rejects(load_inventory, candidate)

    noncanonical_path = tmp_path / "noncanonical.json"
    _write_inventory(noncanonical_path, payload, canonical=False)
    _assert_loader_rejects(load_inventory, noncanonical_path)

    unicode_payload = copy.deepcopy(payload)
    unicode_payload[path_category][path_index]["reason"] = "évidence"
    for label, bad_bytes in (
        ("no-final-lf", _canonical_json_bytes(payload).removesuffix(b"\n")),
        ("double-lf", _canonical_json_bytes(payload) + b"\n"),
        ("crlf", _canonical_json_bytes(payload).replace(b"\n", b"\r\n")),
        (
            "escaped-unicode",
            json.dumps(
                unicode_payload,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            + b"\n",
        ),
    ):
        bad_path = tmp_path / f"{label}.json"
        bad_path.write_bytes(bad_bytes)
        _assert_loader_rejects(load_inventory, bad_path)

    symlink_path = tmp_path / "inventory-alias.json"
    symlink_path.symlink_to(inventory_path)
    _assert_loader_rejects(load_inventory, symlink_path)

    synthetic_root = tmp_path / "synthetic-repository"
    safe = synthetic_root / "safe"
    outside = synthetic_root / "outside"
    safe.mkdir(parents=True)
    outside.mkdir()
    (safe / "real.py").write_text("# safe\n", encoding="utf-8")
    (outside / "outside.py").write_text("# outside\n", encoding="utf-8")
    (safe / "final-link.py").symlink_to(safe / "real.py")
    (synthetic_root / "parent-link").symlink_to(outside, target_is_directory=True)

    template = copy.deepcopy(payload[path_category][path_index])

    def synthetic_payload(path_value: str) -> dict[str, Any]:
        value: dict[str, Any] = {"schema_version": _INVENTORY_VERSION}
        value.update({category: [] for category in _INVENTORY_CATEGORIES})
        entry: dict[str, Any] = {**template, "path": path_value}
        entry.pop("module", None)
        value[path_category] = [entry]
        return value

    synthetic_control_path = tmp_path / "synthetic-control.json"
    _write_inventory(synthetic_control_path, synthetic_payload("safe/real.py"))
    synthetic_control = _call_inventory_loader(
        load_inventory,
        synthetic_control_path,
        repository_root=synthetic_root,
    )
    assert (
        _mapping(synthetic_control, label="synthetic control")[path_category][0]["path"]
        == "safe/real.py"
    )
    for serial, invalid_path in enumerate(
        (
            "safe/final-link.py",
            "parent-link/outside.py",
            "safe/Real.py",
            "safe/*.py",
            "safe/[r]eal.py",
        )
    ):
        candidate = tmp_path / f"synthetic-invalid-{serial}.json"
        _write_inventory(candidate, synthetic_payload(invalid_path))
        _assert_loader_rejects(
            load_inventory,
            candidate,
            repository_root=synthetic_root,
        )
    return inventory


def _compact_digest(value: Any) -> str:
    data = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _assert_complete_executable_universe(inventory: Any) -> dict[str, Any]:
    del inventory
    paths = sorted(
        path.relative_to(_REPO_ROOT).as_posix()
        for root in _SCRIPT_ROOTS
        for path in root.rglob("*")
        if path.is_file() and path.suffix in {".py", ".sh"}
    )
    assert len(paths) == 144
    assert sum(path.endswith(".py") for path in paths) == 120
    assert sum(path.endswith(".sh") for path in paths) == 24
    assert _SANCTIONED_CLI_PATHS <= set(paths)

    baseline = sorted(set(paths) - _SANCTIONED_CLI_PATHS)
    assert len(baseline) == 140
    assert sum(path.endswith(".py") for path in baseline) == 116
    assert sum(path.endswith(".sh") for path in baseline) == 24
    assert _compact_digest(baseline) == _PRE_S11B_PATH_LIST_SHA256
    path_hashes = [
        {
            "path": path,
            "sha256": hashlib.sha256((_REPO_ROOT / path).read_bytes()).hexdigest(),
        }
        for path in baseline
    ]
    assert _compact_digest(path_hashes) == _PRE_S11B_PATH_AND_SHA256_DIGEST
    return {"paths": tuple(paths), "baseline": tuple(baseline)}


def _scan_python(path: Path) -> dict[str, frozenset[str]]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    imports: set[str] = set()
    process_targets: set[str] = set()
    unresolved: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
            imports.update(f"{node.module}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Call):
            call_name = ""
            if isinstance(node.func, ast.Name):
                call_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                call_name = node.func.attr
            uvicorn_run = (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "run"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "uvicorn"
            )
            if uvicorn_run:
                # uvicorn.run launches the ASGI server in-process; it is not
                # a legacy subprocess target.
                continue
            if call_name in {"import_module", "__import__"} and node.args:
                if isinstance(node.args[0], ast.Constant) and isinstance(
                    node.args[0].value, str
                ):
                    imports.add(node.args[0].value)
                else:
                    unresolved.add("dynamic_import")
            if call_name in {"run", "Popen", "call", "check_call", "check_output"}:
                literal_targets = set()
                for argument in node.args:
                    for literal in ast.walk(argument):
                        if isinstance(literal, ast.Constant) and isinstance(
                            literal.value, str
                        ):
                            literal_targets.add(literal.value)
                process_targets.update(literal_targets)
                if not literal_targets:
                    unresolved.add("subprocess_target")
    markers = {
        marker
        for marker in _LEGACY_BODY_MARKERS
        if marker.casefold() in source.casefold()
    }
    markers.update(_LEGACY_SCHEMA_RE.findall(source))
    if _LEGACY_DML_RE.search(source):
        markers.add("legacy_sql_dml")
    if _FIXED_COLLECTION_RE.search(source) and "milvus" in source.casefold():
        markers.add("fixed_collection")
    return {
        "imports": frozenset(imports),
        "process_targets": frozenset(process_targets),
        "markers": frozenset(markers),
        "unresolved": frozenset(unresolved),
    }


def _scan_shell(path: Path) -> dict[str, frozenset[str]]:
    source = path.read_text(encoding="utf-8")
    tokens = frozenset(re.findall(r"[A-Za-z0-9_./${}:-]+", source))
    markers = {
        marker
        for marker in _LEGACY_BODY_MARKERS
        if marker.casefold() in source.casefold()
    }
    markers.update(_LEGACY_SCHEMA_RE.findall(source))
    if _LEGACY_DML_RE.search(source):
        markers.add("legacy_sql_dml")
    if _FIXED_COLLECTION_RE.search(source) and "milvus" in source.casefold():
        markers.add("fixed_collection")
    generic_targets = {
        token
        for token in tokens
        if any(
            fragment in token.casefold()
            for fragment in ("database", "milvus", "collection", "table")
        )
    }
    command_targets = {
        token
        for token in tokens
        if token.endswith((".py", ".sh")) or token.startswith("src.data_agents.")
    }
    return {
        "command_targets": frozenset(command_targets),
        "generic_targets": frozenset(generic_targets),
        "markers": frozenset(markers),
    }


def _assert_scanner_behavior(inventory: Any, tmp_path: Path) -> None:
    del inventory
    python_cases = {
        "static_import": "import src.data_agents.canonical.writer\n",
        "dynamic_import": (
            "from importlib import import_module\n"
            "import_module('src.data_agents.service.retrieval')\n"
        ),
        "unresolved_dynamic_import": (
            "from importlib import import_module\nname = input()\nimport_module(name)\n"
        ),
        "subprocess_target": (
            "import subprocess\n"
            "subprocess.run(['python', 'scripts/run_milvus_backfill.py'])\n"
        ),
        "unresolved_subprocess": "import subprocess\nsubprocess.run(command)\n",
        "body_marker": "writer = 'canonical_writer'\n",
        "legacy_dml": "SQL = 'UPDATE V042_company SET name = %s'\n",
        "fixed_collection": ("MILVUS_COMMAND = 'drop professor_identity collection'\n"),
    }
    for label, source in python_cases.items():
        sample = tmp_path / f"legacy-{label}.py"
        sample.write_text(source, encoding="utf-8")
        assert _is_legacy_scan(_scan_python(sample)), label
    safe_python = tmp_path / "safe.py"
    safe_python.write_text(
        "from src.data_agents.canonical_v2.contracts import PublishedRelease\n",
        encoding="utf-8",
    )
    assert not _is_legacy_scan(_scan_python(safe_python))

    shell_cases = {
        "command": "python scripts/run_quality_promote.py\n",
        "target_variable": "TARGET_DATABASE=${DATABASE_URL}\n",
        "legacy_table": "psql -c 'DELETE FROM V042_company'\n",
        "fixed_collection": "milvus drop_collection professor_identity\n",
    }
    for label, source in shell_cases.items():
        sample = tmp_path / f"legacy-{label}.sh"
        sample.write_text(source, encoding="utf-8")
        assert _is_legacy_scan(_scan_shell(sample)), label
    safe_shell = tmp_path / "safe.sh"
    safe_shell.write_text(
        "python -m src.data_agents.canonical_v2.contracts\n", encoding="utf-8"
    )
    assert not _is_legacy_scan(_scan_shell(safe_shell))


def _entry_identity_set(inventory: Any, category: str) -> set[str]:
    payload = _mapping(inventory, label="legacy inventory")
    return {
        _canonical_identity(_mapping(entry, label=category))
        for entry in payload[category]
    }


def _is_legacy_scan(result: dict[str, frozenset[str]]) -> bool:
    imports = result.get("imports", frozenset())
    forbidden_import = any(
        imported == prefix or imported.startswith(f"{prefix}.")
        for imported in imports
        for prefix in _FORBIDDEN_IMPORT_PREFIXES
    )
    targets = result.get("process_targets", frozenset()) | result.get(
        "command_targets", frozenset()
    )
    legacy_target = any(
        any(target.endswith(name) or name in target for name in _LEGACY_PROCESS_TARGETS)
        or any(
            target == prefix or target.startswith(f"{prefix}.")
            for prefix in _FORBIDDEN_IMPORT_PREFIXES
        )
        for target in targets
    )
    return (
        forbidden_import
        or legacy_target
        or bool(result.get("generic_targets"))
        or bool(result.get("markers"))
        or bool(result.get("unresolved"))
    )


def _existing_module_identity(module: str) -> str | None:
    relative = Path(*module.split("."))
    roots = (
        _REPO_ROOT / "apps/admin-console",
        _REPO_ROOT / "apps/miroflow-agent",
    )
    if any(
        (root / relative.with_suffix(".py")).is_file()
        or (root / relative / "__init__.py").is_file()
        for root in roots
    ):
        return f"module:{module}"
    return None


def _discover_non_script_inventory() -> dict[str, set[str]]:
    api_root = _REPO_ROOT / "apps/admin-console/backend/api"
    sanctioned_router_modules = {
        identity.removeprefix("module:")
        for identity in _EXPECTED_SANCTIONED_IDENTITIES
        if identity.startswith("module:")
    }
    routers = {
        f"module:backend.api.{path.stem}"
        for path in api_root.glob("*.py")
        if "APIRouter(" in path.read_text(encoding="utf-8")
        and f"backend.api.{path.stem}" not in sanctioned_router_modules
    }
    frontend = {
        f"path:{path.relative_to(_REPO_ROOT).as_posix()}"
        for path in (_REPO_ROOT / "apps/admin-console/frontend/src").rglob("*")
        if path.is_file()
    }
    retired_router_modules = {identity.removeprefix("module:") for identity in routers}
    modules = {
        identity
        for module in _FORBIDDEN_IMPORT_PREFIXES
        if module not in retired_router_modules
        if (identity := _existing_module_identity(module)) is not None
    }
    return {
        "retired_http_routers": routers,
        "retired_frontend_routes": frontend,
        "legacy_modules": modules,
    }


def _assert_exhaustive_classification(
    inventory: Any,
    discovery: dict[str, Any],
) -> None:
    retired = set().union(
        *(
            _entry_identity_set(inventory, category)
            for category in _INVENTORY_CATEGORIES[:-1]
        )
    )
    sanctioned = _entry_identity_set(inventory, "sanctioned_entrypoints")
    legacy_scripts = _entry_identity_set(inventory, "legacy_scripts")
    assert retired.isdisjoint(sanctioned)
    assert sanctioned == _EXPECTED_SANCTIONED_IDENTITIES

    for category, expected in _discover_non_script_inventory().items():
        assert _entry_identity_set(inventory, category) == expected

    discovered_legacy_scripts: set[str] = set()
    for relative in discovery["paths"]:
        path = _REPO_ROOT / relative
        scan = _scan_python(path) if path.suffix == ".py" else _scan_shell(path)
        identity = f"path:{relative}"
        if _is_legacy_scan(scan):
            discovered_legacy_scripts.add(identity)
        if relative in _SANCTIONED_CLI_PATHS:
            assert identity in sanctioned
            assert identity not in retired
            assert not _is_legacy_scan(scan)
    # The inventory is the authoritative classification; the scanner is a
    # heuristic lower bound.  reference_only archives may carry no detectable
    # legacy feature (standard-library-only scripts), so the assertion is
    # one-directional: every scanner discovery must already be archived, and
    # the archive may contain scanner-invisible entries.
    assert discovered_legacy_scripts <= legacy_scripts
    assert all(
        sum(
            identity in _entry_identity_set(inventory, category)
            for category in _INVENTORY_CATEGORIES
        )
        == 1
        for identity in discovered_legacy_scripts
    )


def _fresh_import_closure(
    module_name: str,
    python_paths: tuple[Path, ...],
    forbidden: tuple[str, ...],
) -> set[str]:
    script = """
import importlib
import importlib.abc
import json
import sys
sys.path[:0] = json.loads(sys.argv[2])
target = sys.argv[1]
forbidden = tuple(json.loads(sys.argv[3]))

class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == name or fullname.startswith(name + '.') for name in forbidden):
            raise ImportError('forbidden S11B import attempted: ' + fullname)
        return None

sys.meta_path.insert(0, Blocker())
if target.endswith('.py'):
    import importlib.util
    spec = importlib.util.spec_from_file_location('_s11b_sanctioned_cli', target)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
else:
    importlib.import_module(target)
loaded = sorted(
    name for name in sys.modules
    if any(name == prefix or name.startswith(prefix + '.') for prefix in forbidden)
)
assert not loaded, loaded
print(json.dumps(sorted(sys.modules)))
"""
    interpreter = (
        _REPO_ROOT / "apps/admin-console/.venv/bin/python"
        if module_name == "backend.main"
        else Path(sys.executable)
    )
    result = subprocess.run(
        [
            str(interpreter),
            "-I",
            "-c",
            script,
            module_name,
            json.dumps([str(path) for path in python_paths]),
            json.dumps(forbidden),
        ],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return set(json.loads(result.stdout.splitlines()[-1]))


def _module_source(module: str, roots: tuple[Path, ...]) -> Path | None:
    relative = Path(*module.split("."))
    for root in roots:
        for candidate in (
            root / relative.with_suffix(".py"),
            root / relative / "__init__.py",
        ):
            if candidate.is_file():
                return candidate
    return None


def _source_module(path: Path, roots: tuple[Path, ...]) -> str | None:
    for root in roots:
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        parts = list(relative.with_suffix("").parts)
        if parts[-1] == "__init__":
            parts.pop()
        return ".".join(parts)
    return None


def _static_import_closure(target: str, roots: tuple[Path, ...]) -> set[str]:
    initial = Path(target) if target.endswith(".py") else _module_source(target, roots)
    assert initial is not None and initial.is_file()
    pending = [initial.resolve()]
    visited: set[Path] = set()
    imports: set[str] = set()
    while pending:
        path = pending.pop()
        if path in visited:
            continue
        visited.add(path)
        module = _source_module(path, roots)
        assert module is not None
        package = module if path.name == "__init__.py" else module.rpartition(".")[0]

        def resolve_relative(name: str, *, level: int) -> str:
            if level == 0:
                return name
            parts = package.split(".") if package else []
            ascend = level - 1
            assert ascend <= len(parts), (
                f"relative import escapes package in sanctioned target: {path}"
            )
            prefix = parts[: len(parts) - ascend]
            return ".".join((*prefix, *name.split("."))) if name else ".".join(prefix)

        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                base = resolve_relative(node.module or "", level=node.level)
                if base:
                    names.append(base)
                    names.extend(f"{base}.{alias.name}" for alias in node.names)
            elif isinstance(node, ast.Call):
                call_name = ""
                if isinstance(node.func, ast.Name):
                    call_name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    call_name = node.func.attr
                if call_name in {"import_module", "__import__"}:
                    assert node.args, (
                        f"dynamic import lacks a target in sanctioned closure: {path}"
                    )
                    imported = node.args[0]
                    assert isinstance(imported, ast.Constant) and isinstance(
                        imported.value, str
                    ), f"unresolved dynamic import in sanctioned closure: {path}"
                    dynamic_name = imported.value
                    if dynamic_name.startswith("."):
                        level = len(dynamic_name) - len(dynamic_name.lstrip("."))
                        dynamic_name = resolve_relative(
                            dynamic_name[level:], level=level
                        )
                    names.append(dynamic_name)
            imports.update(names)
            for name in names:
                source = _module_source(name, roots)
                if source is not None:
                    pending.append(source.resolve())
    return imports


def _assert_sanctioned_import_closures(
    inventory: Any,
    sanctioned_paths: tuple[Path, ...],
) -> None:
    retired_modules = {
        identity.removeprefix("module:")
        for category in _INVENTORY_CATEGORIES[:-1]
        for identity in _entry_identity_set(inventory, category)
        if identity.startswith("module:")
    }
    import_roots = (
        _REPO_ROOT / "apps/admin-console",
        _REPO_ROOT / "apps/miroflow-agent",
    )
    forbidden_prefixes = tuple(
        sorted(set((*_FORBIDDEN_IMPORT_PREFIXES, *retired_modules)))
    )
    targets = ("backend.main", *(str(path) for path in sanctioned_paths[::2]))
    for target in targets:
        static_closure = _static_import_closure(target, import_roots)
        static_forbidden = {
            module
            for module in static_closure
            if any(
                module == prefix or module.startswith(f"{prefix}.")
                for prefix in forbidden_prefixes
            )
        }
        assert not static_forbidden, (
            f"sanctioned static import closure reached quarantine: {sorted(static_forbidden)}"
        )
        closure = _fresh_import_closure(target, import_roots, forbidden_prefixes)
        forbidden = {
            module
            for module in closure
            if any(
                module == prefix or module.startswith(f"{prefix}.")
                for prefix in forbidden_prefixes
            )
        }
        assert not forbidden, (
            f"sanctioned import closure reached quarantine: {sorted(forbidden)}"
        )


def _assert_inventory_handoff_receipt(inventory: Any, inventory_path: Path) -> None:
    payload = _mapping(inventory, label="legacy inventory")
    receipt_value = getattr(inventory, "receipt", None)
    if callable(receipt_value):
        receipt_value = receipt_value()
    receipt = _mapping(receipt_value, label="legacy inventory receipt")
    expected_path = inventory_path.relative_to(_REPO_ROOT).as_posix()
    assert receipt["path"] == expected_path
    assert receipt["sha256"] == hashlib.sha256(inventory_path.read_bytes()).hexdigest()
    assert receipt["category_counts"] == {
        category: len(payload[category]) for category in _INVENTORY_CATEGORIES
    }

    dispositions: dict[str, int] = {}
    expected_s11c: list[dict[str, str]] = []
    for category in _INVENTORY_CATEGORIES[:-1]:
        for raw_entry in payload[category]:
            entry = _mapping(raw_entry, label=category)
            disposition = entry["disposition"]
            assert isinstance(disposition, str)
            dispositions[disposition] = dispositions.get(disposition, 0) + 1
            if disposition == "s11c_disposition":
                entry_path = entry.get("path", entry.get("module"))
                assert isinstance(entry_path, str)
                expected_s11c.append(
                    {
                        "inventory_category": category,
                        "inventory_path": entry_path,
                    }
                )
    expected_s11c.sort(
        key=lambda item: (item["inventory_category"], item["inventory_path"])
    )
    assert receipt["disposition_counts"] == dispositions
    assert receipt["s11c_disposition_entries"] == expected_s11c
    assert receipt["s11c_disposition_count"] == len(expected_s11c)


def test_s11b_sanctioned_entrypoints_classify_and_exclude_legacy_consumers(
    request: pytest.FixtureRequest,
) -> None:
    seam = _load_s11b_boundary_seam()
    tmp_path = request.getfixturevalue("tmp_path")

    inventory = _assert_inventory_canonical_contract(
        seam.load_inventory,
        seam.inventory_path,
        tmp_path,
    )
    discovery = _assert_complete_executable_universe(inventory)
    _assert_scanner_behavior(inventory, tmp_path)
    _assert_exhaustive_classification(inventory, discovery)
    _assert_sanctioned_import_closures(inventory, seam.sanctioned_paths)
    _assert_inventory_handoff_receipt(inventory, seam.inventory_path)
