"""The v2 (no-Milvus) serving pack contract, and the v1 compatibility lock.

Layer ① of the verification contract:
``.agents/runs/drop-milvus-from-serving-pack/verification-contract.md``.

The fixture reuses the real contract fixture from ``test_serving_pack_loader``
(build authority → isolated index → sealed v1 pack), then produces the v2
world from it with the real migration and the real sealer. Nothing here is a
hand-written stand-in for the pack format.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.abc
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace
from typing import Any

import pytest

from src.data_agents.canonical_v2 import index_projection_isolated as iso
from src.data_agents.canonical_v2 import knowledge_build_isolated as build_module
from src.data_agents.canonical_v2 import serving_pack_loader as pack_loader
from src.data_agents.canonical_v2 import placeholder_scrub
from src.data_agents.canonical_v2.index_projection import (
    IndexProjectionIntegrityError,
)


_REPO_ROOT = Path(__file__).resolve().parents[4]
_PACK_TEST_PATH = Path(__file__).with_name("test_serving_pack_loader.py")
CANDIDATE_EMBEDDING_BUNDLE_PATH = (
    _REPO_ROOT
    / ".agents/runs/embedding-model-switch-v2"
    / "qwen3.7-text-embedding-flash-embedding-bundle-v1.json"
)


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(spec.name, None)
        raise
    return module


class _BlockPymilvus(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname: str, path: Any = None, target: Any = None) -> None:
        if fullname.split(".")[0] == "pymilvus":
            raise ImportError("pymilvus is forbidden on this code path")
        return None


class forbid_pymilvus:
    """Poison every pymilvus import, including already-imported modules."""

    def __enter__(self) -> forbid_pymilvus:
        self._saved = {
            name: module
            for name, module in list(sys.modules.items())
            if name.split(".")[0] == "pymilvus"
        }
        for name in self._saved:
            del sys.modules[name]
        importlib.invalidate_caches()
        self._finder = _BlockPymilvus()
        sys.meta_path.insert(0, self._finder)
        return self

    def __exit__(self, *exc: Any) -> bool:
        sys.meta_path.remove(self._finder)
        sys.modules.update(self._saved)
        return False


class _Fixture(SimpleNamespace):
    root: Path
    v1_index: Path
    v1_pack: Path
    v2_index: Path
    v2_pack: Path
    points: tuple[Any, ...]
    adapter: Any
    generator: Any
    target: Any
    conversion: Any
    bundle: Any
    index_request: Any
    catalog: Any
    verification: Any
    release_id: str


@pytest.fixture(scope="module")
def worlds(tmp_path_factory: pytest.TempPathFactory) -> _Fixture:
    pack_tests = _load_module(
        "canonical_v2_pack_loader_tests", _PACK_TEST_PATH
    )
    tmp = tmp_path_factory.mktemp("no-milvus")
    (tmp / "v1").mkdir()
    v1 = pack_tests._build_fixture_once(tmp / "v1")

    points = tuple(v1.bundle.index_result.points)
    iso.write_persisted_vector_matrix(
        v1.index_root,
        points=points,
        vectors=v1.adapter.embed_batch(
            tuple(point.embedded_content for point in points)
        ),
        embedding_model_id=v1.adapter.model_id,
    )
    v2_index = tmp / "v2-index"
    conversion = iso.convert_isolated_index_to_v2(
        source_root=v1.index_root,
        dest_root=v2_index,
    )
    v2_pack = tmp / "pack-v2"
    v1.generator.build_serving_pack_from_authority(
        release_bundle=v1.bundle,
        index_projection_request=v1.index_request,
        institution_catalog=v1.catalog,
        release_verification=v1.verification,
        index_root=v2_index,
        pack_dir=v2_pack,
        expected_release_id=pack_tests.RELEASE_ID,
        generator_run_id="serving-pack-v2-test-run",
        pack_schema_version=pack_loader.PACK_SCHEMA_VERSION_V2,
    )
    return _Fixture(
        root=tmp,
        v1_index=v1.index_root,
        v1_pack=v1.pack_dir,
        v2_index=v2_index,
        v2_pack=v2_pack,
        points=points,
        adapter=v1.adapter,
        generator=v1.generator,
        target=v1.target,
        conversion=conversion,
        bundle=v1.bundle,
        index_request=v1.index_request,
        catalog=v1.catalog,
        verification=v1.verification,
        release_id=v1.bundle.release_id,
    )


def _open(fixture: _Fixture, pack_dir: Path) -> Any:
    return pack_loader.open_serving_pack_authority(
        pack_dir=pack_dir,
        expected_release_id=json.loads(
            (pack_dir / "manifest.json").read_bytes()
        )["release_id"],
        expected_index_marker_sha256=json.loads(
            (pack_dir / "manifest.json").read_bytes()
        )["index_marker_sha256"],
        expected_forbidden_milvus_path=fixture.target.forbidden_milvus_paths[0],
    )


def _reforge_pack(*, source_pack: Path, index_root: Path, dest_pack: Path) -> None:
    """Point a copy of one pack at another index root (marker + hashes rebound)."""

    shutil.copytree(source_pack, dest_pack)
    manifest_path = dest_pack / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    marker_bytes = (
        iso._canonical_json_bytes(
            iso._marker_document(
                root=index_root,
                target_id=manifest["index_target_id"],
                release_id=manifest["release_id"],
                forbidden_milvus_paths=tuple(
                    Path(value) for value in manifest["index_forbidden_milvus_paths"]
                ),
            )
        )
        + b"\n"
    )
    (index_root / iso._MARKER_NAME).write_bytes(marker_bytes)
    (dest_pack / iso._MARKER_NAME).write_bytes(marker_bytes)
    manifest["index_root"] = str(index_root)
    manifest["index_marker_sha256"] = hashlib.sha256(marker_bytes).hexdigest()
    manifest["files"] = {
        name: hashlib.sha256((dest_pack / name).read_bytes()).hexdigest()
        for name in manifest["files"]
    }
    manifest_path.write_bytes(
        (json.dumps(manifest, ensure_ascii=False, separators=(",", ":")) + "\n").encode(
            "utf-8"
        )
    )


# --- R1/R2: the v2 boot path -------------------------------------------------


def test_v2_boot_opens_without_touching_milvus(
    worlds: _Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(path: Path) -> Any:
        raise AssertionError(f"the v2 boot path opened Milvus: {path}")

    monkeypatch.setattr(iso, "_open_milvus_client", refuse)
    with forbid_pymilvus():
        authority = _open(worlds, worlds.v2_pack)
    assert tuple(authority.index_snapshot.points) == worlds.points
    assert authority.manifest.schema_version == pack_loader.PACK_SCHEMA_VERSION_V2


def test_v1_boot_would_fail_without_pymilvus(worlds: _Fixture) -> None:
    """The v1 path is unchanged: it still needs the Milvus store."""

    with forbid_pymilvus(), pytest.raises(Exception):  # noqa: B017
        _open(worlds, worlds.v1_pack)


def test_v2_points_come_from_the_lookup_point_table(worlds: _Fixture) -> None:
    import sqlite3

    lookup_path = worlds.v2_index / "lookup.sqlite3"
    assert iso.has_lookup_index_points(lookup_path)
    with sqlite3.connect(f"file:{lookup_path}?mode=ro&immutable=1", uri=True) as con:
        rows = con.execute("SELECT point_id, point_json FROM index_point").fetchall()
    assert len(rows) == len(worlds.points)
    stored = {
        row[0]: iso.IndexProjectionPoint.model_validate_json(row[1]) for row in rows
    }
    assert tuple(sorted(stored)) == tuple(
        sorted(point.point_id for point in worlds.points)
    )
    assert tuple(stored[point.point_id] for point in worlds.points) == worlds.points
    snapshot = _open(worlds, worlds.v2_pack).index_snapshot
    assert tuple(snapshot.points) == worlds.points


# --- R3/R4: fail closed ------------------------------------------------------


def test_v2_pack_without_point_store_is_refused(worlds: _Fixture) -> None:
    import sqlite3

    broken_index = worlds.root / "broken-index-no-points"
    shutil.copytree(worlds.v2_index, broken_index)
    with sqlite3.connect(broken_index / "lookup.sqlite3") as con:
        con.execute("DROP TABLE index_point")
    broken_pack = worlds.root / "broken-pack-no-points"
    _reforge_pack(
        source_pack=worlds.v2_pack, index_root=broken_index, dest_pack=broken_pack
    )
    with pytest.raises(IndexProjectionIntegrityError):
        _open(worlds, broken_pack)


def test_v2_pack_with_milvus_copy_is_refused(worlds: _Fixture) -> None:
    broken_index = worlds.root / "broken-index-milvus"
    shutil.copytree(worlds.v2_index, broken_index)
    (broken_index / "milvus.db").write_bytes(b"not a milvus store\n")
    broken_pack = worlds.root / "broken-pack-milvus"
    _reforge_pack(
        source_pack=worlds.v2_pack, index_root=broken_index, dest_pack=broken_pack
    )
    with pytest.raises(IndexProjectionIntegrityError):
        _open(worlds, broken_pack)


def test_v2_point_store_drift_is_refused(worlds: _Fixture) -> None:
    """A store whose inventory differs from the receipt refuses the boot."""

    import sqlite3

    broken_index = worlds.root / "broken-index-short"
    shutil.copytree(worlds.v2_index, broken_index)
    with sqlite3.connect(broken_index / "lookup.sqlite3") as con:
        con.execute(
            "DELETE FROM index_point WHERE point_id = ?",
            (worlds.points[0].point_id,),
        )
    broken_pack = worlds.root / "broken-pack-short"
    _reforge_pack(
        source_pack=worlds.v2_pack, index_root=broken_index, dest_pack=broken_pack
    )
    with pytest.raises(IndexProjectionIntegrityError):
        _open(worlds, broken_pack)


# --- R5/R9: v1 compatibility and equivalence ---------------------------------


def test_v1_pack_still_boots_through_milvus(worlds: _Fixture) -> None:
    authority = _open(worlds, worlds.v1_pack)
    assert authority.manifest.schema_version == pack_loader.PACK_SCHEMA_VERSION
    assert tuple(authority.index_snapshot.points) == worlds.points
    assert set(authority.manifest.files) == {
        "lookup.sqlite3",
        "milvus.db",
        ".canonical-v2-isolated-index-target.json",
        "relationships.json",
        "institution_catalog.json",
    }


def test_v1_and_v2_read_the_same_index_to_the_same_points(worlds: _Fixture) -> None:
    v1_snapshot = _open(worlds, worlds.v1_pack).index_snapshot
    with forbid_pymilvus():
        v2_snapshot = _open(worlds, worlds.v2_pack).index_snapshot
    assert tuple(v1_snapshot.points) == tuple(v2_snapshot.points)
    assert v1_snapshot.receipt == v2_snapshot.receipt
    assert v1_snapshot.lookup_documents == v2_snapshot.lookup_documents


# --- R6: the npz anchor ------------------------------------------------------


def _rewrite_matrix(source: Path, dest: Path, *, drop: bool) -> None:
    import numpy as np

    with np.load(source, allow_pickle=True) as data:
        meta = json.loads(str(data["meta"].item()))
        point_ids = [str(value) for value in data["point_ids"].tolist()]
        matrix = np.asarray(data["matrix"], dtype=np.float64)
        norms = np.asarray(data["norms"], dtype=np.float64)
    if drop:
        point_ids = point_ids[:-1]
        matrix = matrix[:-1]
        norms = norms[:-1]
    else:
        point_ids = [*point_ids, "point:not-in-the-store"]
        matrix = np.vstack([matrix, matrix[0]])
        norms = np.append(norms, norms[0])
    meta["point_count"] = len(point_ids)
    np.savez(
        dest,
        point_ids=np.asarray(tuple(point_ids), dtype=object),
        matrix=matrix,
        norms=norms,
        meta=np.asarray(json.dumps(meta, ensure_ascii=False, sort_keys=True), dtype=object),
    )


def test_v2_npz_anchor_rejects_extra_and_missing_points(worlds: _Fixture) -> None:
    snapshot = _open(worlds, worlds.v2_pack).index_snapshot
    source = worlds.v2_index / "vector_matrix.npz"
    healthy = iso.load_persisted_vector_matrix(
        source,
        points=snapshot.points,
        expected_embedding_model_id=worlds.adapter.model_id,
        dimension=worlds.adapter.dimension,
    )
    assert healthy is not None
    extra = worlds.root / "matrix-extra.npz"
    _rewrite_matrix(source, extra, drop=False)
    with pytest.raises(IndexProjectionIntegrityError):
        iso.load_persisted_vector_matrix(
            extra,
            points=snapshot.points,
            expected_embedding_model_id=worlds.adapter.model_id,
            dimension=worlds.adapter.dimension,
        )
    missing = worlds.root / "matrix-missing.npz"
    _rewrite_matrix(source, missing, drop=True)
    with pytest.raises(IndexProjectionIntegrityError):
        iso.load_persisted_vector_matrix(
            missing,
            points=snapshot.points,
            expected_embedding_model_id=worlds.adapter.model_id,
            dimension=worlds.adapter.dimension,
        )


# --- the embedding identity pair ---------------------------------------------


def test_v2_index_refuses_the_candidate_embedding_identity(worlds: _Fixture) -> None:
    """A bundle's (model, dimension) pair must match the index that ships with it.

    The v2 candidate (``qwen3.7-text-embedding-flash``, 1024 dimensions) is a
    different vector space from the released one, so binding its adapter to this
    index has to fail closed at both layers: the pack binding refuses the
    adapter, and the persisted matrix refuses an identity it was not written
    with — including a matching model with the wrong dimension, which is exactly
    the shape a "new bundle, old index" mistake takes.
    """

    snapshot = _open(worlds, worlds.v2_pack).index_snapshot
    candidate = build_module.load_content_addressed_embedding_adapter(
        CANDIDATE_EMBEDDING_BUNDLE_PATH
    )
    assert candidate.model_id != worlds.adapter.model_id
    assert candidate.dimension != worlds.adapter.dimension
    marker_sha256 = json.loads((worlds.v2_pack / "manifest.json").read_bytes())[
        "index_marker_sha256"
    ]

    with pytest.raises(
        pack_loader.ServingPackIntegrityError,
        match="embedding model differs",
    ):
        pack_loader.open_serving_pack_authority(
            pack_dir=worlds.v2_pack,
            expected_release_id=worlds.release_id,
            expected_index_marker_sha256=marker_sha256,
            expected_forbidden_milvus_path=worlds.target.forbidden_milvus_paths[0],
            embedding_adapter=candidate,
        )

    source = worlds.v2_index / "vector_matrix.npz"
    with pytest.raises(IndexProjectionIntegrityError):
        iso.load_persisted_vector_matrix(
            source,
            points=snapshot.points,
            expected_embedding_model_id=candidate.model_id,
            dimension=candidate.dimension,
        )
    with pytest.raises(IndexProjectionIntegrityError):
        iso.load_persisted_vector_matrix(
            source,
            points=snapshot.points,
            expected_embedding_model_id=worlds.adapter.model_id,
            dimension=candidate.dimension,
        )


# --- R7: mount receipt -------------------------------------------------------


def test_v2_mount_receipt_registers_only_v2_files(worlds: _Fixture) -> None:
    receipt_path = worlds.v2_pack.parent / f"{worlds.v2_pack.name}.mount-receipt.json"
    if receipt_path.exists():
        receipt_path.unlink()
    _open(worlds, worlds.v2_pack)
    first = json.loads(receipt_path.read_bytes())
    assert first["verification"] == "full"
    assert set(first["files"]) == {
        "lookup.sqlite3",
        pack_loader.PACK_MARKER_FILENAME,
    }
    assert "milvus.db" not in first["file_sha256"]
    _open(worlds, worlds.v2_pack)
    second = json.loads(receipt_path.read_bytes())
    assert second["verification"] == "receipt"
    assert set(second["files"]) == set(first["files"])


# --- R8/R10/R11: sealer, migration, deletion ---------------------------------


def test_sealer_v2_pack_carries_no_milvus_file(worlds: _Fixture) -> None:
    files = {path.name for path in worlds.v2_pack.iterdir()}
    assert "milvus.db" not in files
    manifest = json.loads((worlds.v2_pack / "manifest.json").read_bytes())
    assert manifest["schema_version"] == pack_loader.PACK_SCHEMA_VERSION_V2
    assert set(manifest["files"]) == {
        "lookup.sqlite3",
        ".canonical-v2-isolated-index-target.json",
        "relationships.json",
        "institution_catalog.json",
    }
    assert pack_loader.pack_index_filenames(pack_loader.PACK_SCHEMA_VERSION_V2) == (
        "lookup.sqlite3",
    )
    assert pack_loader.pack_point_store(pack_loader.PACK_SCHEMA_VERSION_V2) == (
        iso.POINT_STORE_LOOKUP
    )
    assert pack_loader.pack_point_store(pack_loader.PACK_SCHEMA_VERSION) == (
        iso.POINT_STORE_MILVUS
    )
    with pytest.raises(pack_loader.ServingPackIntegrityError):
        pack_loader.pack_index_filenames("canonical-v2-serving-pack-v3")


def test_sealer_refuses_a_v2_seal_over_a_v1_index_root(worlds: _Fixture) -> None:
    with pytest.raises(Exception) as error:  # noqa: B017
        worlds.generator.build_serving_pack_from_authority(
            release_bundle=worlds.bundle,
            index_projection_request=worlds.index_request,
            institution_catalog=worlds.catalog,
            release_verification=worlds.verification,
            index_root=worlds.v1_index,
            pack_dir=worlds.root / "refused-pack",
            expected_release_id=worlds.release_id,
            generator_run_id="refused",
            pack_schema_version=pack_loader.PACK_SCHEMA_VERSION_V2,
        )
    assert "v2 seal requires" in str(error.value)


def test_index_point_migration_preserves_points_and_drops_milvus(
    worlds: _Fixture,
) -> None:
    dest = worlds.root / "migration-dest"
    report = iso.convert_isolated_index_to_v2(
        source_root=worlds.v1_index,
        dest_root=dest,
    )
    assert report.point_count == len(worlds.points)
    assert report.removed_milvus_bytes > 0
    assert not (dest / "milvus.db").exists()
    assert (dest / "vector_matrix.npz").is_file()
    assert iso.has_lookup_index_points(dest / "lookup.sqlite3")
    marker = json.loads((dest / iso._MARKER_NAME).read_bytes())
    assert marker["root"] == str(dest)
    assert marker["release_id"] == report.release_id
    read_back = iso._read_index_points_from_path(
        dest / "lookup.sqlite3",
        expected_release_id=report.release_id,
    )
    assert read_back == worlds.points


def test_placeholder_census_is_deleted_but_matcher_survives() -> None:
    assert not hasattr(placeholder_scrub, "scan_lookup_index")
    assert not hasattr(placeholder_scrub, "classify_field_value")
    assert not hasattr(placeholder_scrub, "SCAN_FIELD_LISTS")
    assert placeholder_scrub.scrub_placeholder_value("未找到") == ""
    assert placeholder_scrub.is_placeholder_value("Not supplied by the source system")
    sealer_source = (
        _REPO_ROOT
        / ".agents/runs/rebuild-canonical-v2-knowledge-platform/s12c/build_serving_pack.py"
    ).read_text()
    assert "placeholder" not in sealer_source
