from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest


MODULE_PATH = Path(__file__).with_name("build_source_inventory.py")


def _load_builder():
    if not MODULE_PATH.exists():
        raise AssertionError("build_source_inventory.py is not implemented")
    spec = importlib.util.spec_from_file_location("s2_inventory_builder", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SourceInventoryBuilderTests(unittest.TestCase):
    def test_sha256_file_hashes_bytes_without_modifying_source(self) -> None:
        builder = _load_builder()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evidence.bin"
            path.write_bytes(b"canonical-v2-evidence")
            before = path.stat()

            actual = builder.sha256_file(path)

            after = path.stat()
            self.assertEqual(actual, hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(after.st_size, before.st_size)
            self.assertEqual(after.st_mtime_ns, before.st_mtime_ns)

    def test_inspect_sqlite_uses_immutable_read_only_mode(self) -> None:
        builder = _load_builder()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "released_objects.db"
            with sqlite3.connect(path) as conn:
                conn.execute(
                    "CREATE TABLE released_objects (id TEXT, object_type TEXT)"
                )
                conn.executemany(
                    "INSERT INTO released_objects VALUES (?, ?)",
                    [("p1", "paper"), ("p2", "paper"), ("c1", "company")],
                )
            before = path.stat()

            entry = builder.inspect_sqlite(path, root)

            after = path.stat()
            self.assertEqual(entry["access_mode"], "sqlite_uri_mode_ro_immutable")
            self.assertEqual(entry["table_counts"], {"released_objects": 3})
            self.assertEqual(
                entry["object_type_counts"], {"company": 1, "paper": 2}
            )
            self.assertEqual(after.st_mtime_ns, before.st_mtime_ns)
            self.assertFalse(path.with_name(path.name + "-wal").exists())
            self.assertFalse(path.with_name(path.name + "-shm").exists())

    def test_milvus_like_file_is_hashed_without_opening_client_or_sqlite(self) -> None:
        builder = _load_builder()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "milvus.db"
            path.write_bytes(b"not-a-database-but-valid-hash-evidence")

            entry = builder.hash_only_file(
                path,
                root,
                kind="milvus_lite_original",
            )

            self.assertEqual(entry["access_mode"], "hash_only_never_opened")
            self.assertEqual(entry["kind"], "milvus_lite_original")
            self.assertEqual(entry["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())

    def test_aggregate_manifest_is_content_addressed_and_order_independent(self) -> None:
        builder = _load_builder()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "family" / "a.json"
            second = root / "family" / "b.json"
            first.parent.mkdir()
            first.write_text('{"id": 1}\n', encoding="utf-8")
            second.write_text('{"id": 2}\n', encoding="utf-8")

            forward = builder.aggregate_files(
                [first, second], root, kind="recorded_cache_family"
            )
            reverse = builder.aggregate_files(
                [second, first], root, kind="recorded_cache_family"
            )

            self.assertEqual(forward, reverse)
            self.assertEqual(forward["files"], 2)
            self.assertEqual(forward["bytes"], first.stat().st_size + second.stat().st_size)
            self.assertRegex(forward["manifest_sha256"], r"^[0-9a-f]{64}$")

    def test_build_inventory_merges_committed_ignored_recovery_and_db_sources(self) -> None:
        builder = _load_builder()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            evidence = root / "evidence"
            recovery = root / "recovery"
            (workspace / "docs").mkdir(parents=True)
            (workspace / "docs" / "Data-Agent-Shared-Spec.md").write_text(
                "shared contract", encoding="utf-8"
            )
            (evidence / "apps" / "miroflow-agent").mkdir(parents=True)
            (evidence / "apps" / "miroflow-agent" / "milvus.db").write_bytes(
                b"hash-only-milvus"
            )
            (evidence / "logs" / "debug" / "professor_fetch_cache").mkdir(
                parents=True
            )
            (evidence / "logs" / "debug" / "professor_fetch_cache" / "a.json").write_text(
                '{"url": "https://example.test"}\n', encoding="utf-8"
            )
            recovery.mkdir()
            (recovery / "FORENSIC-CHECKPOINT.md").write_text(
                "checkpoint", encoding="utf-8"
            )
            snapshot = {
                "databases": [
                    {
                        "name": "miroflow_recovery_candidate_verify",
                        "transaction_read_only": True,
                    }
                ]
            }

            inventory = builder.build_inventory(
                workspace=workspace,
                evidence_root=evidence,
                recovery_root=recovery,
                recovery_snapshot=snapshot,
                git_commit="abc123",
                captured_at="2026-07-11T00:00:00Z",
            )

            self.assertEqual(inventory["git_commit"], "abc123")
            self.assertEqual(
                inventory["builder_version"],
                "canonical-v2-s2-source-inventory-builder-v1",
            )
            self.assertEqual(inventory["recovery_database_snapshot"], snapshot)
            kinds = {entry["kind"] for entry in inventory["sources"]}
            self.assertIn("authoritative_prd", kinds)
            self.assertIn("milvus_lite_original", kinds)
            self.assertIn("forensic_checkpoint_document", kinds)
            self.assertIn("professor_fetch_cache_family", kinds)


if __name__ == "__main__":
    unittest.main()
