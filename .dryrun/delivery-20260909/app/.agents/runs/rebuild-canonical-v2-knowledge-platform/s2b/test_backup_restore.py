from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
from types import ModuleType
import unittest


MODULE_PATH = Path(__file__).with_name("backup_restore.py")
INVENTORY_PATH = MODULE_PATH.parents[1] / "s2" / "source-inventory.json"


class BackupRestoreTests(unittest.TestCase):
    def load_module(self) -> ModuleType:
        self.assertTrue(MODULE_PATH.is_file(), "backup_restore.py is not implemented")
        spec = importlib.util.spec_from_file_location("s2b_backup_restore", MODULE_PATH)
        self.assertIsNotNone(spec)
        assert spec is not None
        self.assertIsNotNone(spec.loader)
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_target_roots_reject_source_nesting_and_backup_restore_aliasing(self) -> None:
        module = self.load_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            outside = root / "outside"

            with self.assertRaisesRegex(module.BackupGateError, "inside source"):
                module.validate_target_roots(
                    source_roots=[source],
                    backup_root=source / "backup",
                    restore_root=outside,
                )
            with self.assertRaisesRegex(module.BackupGateError, "must be distinct"):
                module.validate_target_roots(
                    source_roots=[source],
                    backup_root=outside,
                    restore_root=outside,
                )

    def test_cas_copy_and_restore_are_byte_identical_independent_files(self) -> None:
        module = self.load_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.bin"
            source.write_bytes(b"canonical-v2-backup-fixture\x00\xff")
            backup_root = root / "backup"
            restore_root = root / "restore"

            copy = module.copy_file_to_cas(source, backup_root)
            restored = module.materialize_cas_object(
                copy,
                backup_root=backup_root,
                restore_root=restore_root,
                relative_path=Path("fixtures/source.bin"),
            )

            backup_path = backup_root / copy["object_path"]
            restore_path = restore_root / restored["restore_path"]
            self.assertEqual(source.read_bytes(), backup_path.read_bytes())
            self.assertEqual(source.read_bytes(), restore_path.read_bytes())
            self.assertEqual(copy["source_sha256"], copy["backup_sha256"])
            self.assertEqual(copy["source_sha256"], restored["restore_sha256"])
            self.assertTrue(copy["copy_independent"])
            self.assertTrue(restored["copy_independent"])
            self.assertNotEqual(os.stat(source).st_ino, os.stat(backup_path).st_ino)
            self.assertNotEqual(os.stat(backup_path).st_ino, os.stat(restore_path).st_ino)

            escaped = dict(copy)
            escaped["object_path"] = "../source.bin"
            with self.assertRaisesRegex(module.BackupGateError, "unsafe backup object"):
                module.materialize_cas_object(
                    escaped,
                    backup_root=backup_root,
                    restore_root=restore_root,
                    relative_path=Path("fixtures/escaped.bin"),
                )

    def test_member_manifest_matches_frozen_family_hash_contract(self) -> None:
        module = self.load_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "b.json").write_text('{"b": 2}\n', encoding="utf-8")
            (root / "a.json").write_text('{"a": 1}\n', encoding="utf-8")

            summary, rows = module.build_member_manifest(
                [root / "b.json", root / "a.json"], root
            )

            expected_rows = [
                {
                    "relative_path": "a.json",
                    "bytes": 9,
                    "sha256": module.sha256_file(root / "a.json"),
                },
                {
                    "relative_path": "b.json",
                    "bytes": 9,
                    "sha256": module.sha256_file(root / "b.json"),
                },
            ]
            expected_legacy = "".join(
                f"{row['relative_path']}|{row['bytes']}|{row['sha256']}\n"
                for row in expected_rows
            )
            self.assertEqual(rows, expected_rows)
            self.assertEqual(summary["files"], 2)
            self.assertEqual(summary["bytes"], 18)
            self.assertEqual(
                summary["legacy_manifest_sha256"],
                module.sha256_bytes(expected_legacy.encode()),
            )

    def test_frozen_family_patterns_and_required_extras_are_complete(self) -> None:
        module = self.load_module()
        inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
        frozen_family_kinds = {
            source["kind"] for source in inventory["sources"] if "root" in source
        }
        self.assertEqual(frozen_family_kinds, set(module.FAMILY_PATTERNS))
        self.assertEqual(
            module.REQUIRED_EXTRA_SOURCE_IDS,
            {"original_postgresql_volume", "forensic_recovery_tree"},
        )
        self.assertEqual(
            module.RECOVERY_TREE_EXCLUDES,
            {"lab-01/cluster-current"},
        )

    def test_gate_rejects_missing_mismatch_hardlink_and_unrestored_sources(self) -> None:
        module = self.load_module()
        inventory = {
            "sources": [
                {"kind": "alpha", "path": "a.json", "sha256": "a" * 64},
                {"kind": "beta", "path": "b.json", "sha256": "b" * 64},
            ]
        }
        source_ids = module.expected_source_ids(inventory)
        all_ids = sorted(source_ids | module.REQUIRED_EXTRA_SOURCE_IDS)
        backup = self.make_backup_manifest(module, all_ids)
        restore = self.make_restore_verification(all_ids)
        restore["backup_manifest_sha256"] = module.document_sha256(backup)
        acceptance = self.make_acceptance_record(module, backup, restore)

        for mutation, message in (
            (lambda value: value["sources"].pop(), "missing backup source"),
            (
                lambda value: value["sources"][0].update(copy_independent=False),
                "copy independence",
            ),
            (
                lambda value: value["sources"][0].update(hash_verified=False),
                "backup hash",
            ),
        ):
            changed = json.loads(json.dumps(backup))
            mutation(changed)
            with self.assertRaisesRegex(module.BackupGateError, message):
                module.require_accepted_backup_gate(
                    inventory=inventory,
                    backup_manifest=changed,
                    restore_verification=restore,
                    acceptance_record=acceptance,
                )

        failed_restore = json.loads(json.dumps(restore))
        failed_restore["sources"][0]["status"] = "failed"
        with self.assertRaisesRegex(module.BackupGateError, "restore verification"):
            module.require_accepted_backup_gate(
                inventory=inventory,
                backup_manifest=backup,
                restore_verification=failed_restore,
                acceptance_record=acceptance,
            )

        missing_probe = json.loads(json.dumps(restore))
        del missing_probe["required_probes"]["milvus"]
        with self.assertRaisesRegex(module.BackupGateError, "required restore probes"):
            module.require_accepted_backup_gate(
                inventory=inventory,
                backup_manifest=backup,
                restore_verification=missing_probe,
                acceptance_record=acceptance,
            )

        wrong_backup_reference = json.loads(json.dumps(restore))
        wrong_backup_reference["backup_manifest_sha256"] = "0" * 64
        rebound_acceptance = self.make_acceptance_record(
            module, backup, wrong_backup_reference
        )
        with self.assertRaisesRegex(
            module.BackupGateError, "restore verification.*backup manifest"
        ):
            module.require_accepted_backup_gate(
                inventory=inventory,
                backup_manifest=backup,
                restore_verification=wrong_backup_reference,
                acceptance_record=rebound_acceptance,
            )

    def test_gate_acceptance_is_bound_to_exact_manifests(self) -> None:
        module = self.load_module()
        inventory = {
            "sources": [
                {"kind": "alpha", "path": "a.json", "sha256": "a" * 64}
            ]
        }
        all_ids = sorted(
            module.expected_source_ids(inventory) | module.REQUIRED_EXTRA_SOURCE_IDS
        )
        backup = self.make_backup_manifest(module, all_ids)
        restore = self.make_restore_verification(all_ids)
        restore["backup_manifest_sha256"] = module.document_sha256(backup)
        acceptance = self.make_acceptance_record(module, backup, restore)

        result = module.require_accepted_backup_gate(
            inventory=inventory,
            backup_manifest=backup,
            restore_verification=restore,
            acceptance_record=acceptance,
        )
        self.assertEqual(result["state"], "accepted")
        self.assertEqual(result["source_count"], len(all_ids))

        acceptance["backup_manifest_sha256"] = "0" * 64
        with self.assertRaisesRegex(module.BackupGateError, "acceptance.*backup manifest"):
            module.require_accepted_backup_gate(
                inventory=inventory,
                backup_manifest=backup,
                restore_verification=restore,
                acceptance_record=acceptance,
            )

    def test_bounded_format_probes_distinguish_readable_and_corrupt_files(self) -> None:
        module = self.load_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            valid_jsonl = root / "valid.jsonl"
            valid_jsonl.write_text('{"ok": true}\n', encoding="utf-8")
            corrupt_jsonl = root / "corrupt.jsonl"
            corrupt_jsonl.write_text("not-json\n", encoding="utf-8")
            database = root / "valid.db"
            with sqlite3.connect(database) as connection:
                connection.execute("CREATE TABLE evidence (id INTEGER PRIMARY KEY)")

            self.assertEqual(
                module.probe_materialized_file(valid_jsonl)["status"], "passed"
            )
            self.assertEqual(
                module.probe_materialized_file(corrupt_jsonl)["status"], "failed"
            )
            sqlite_probe = module.probe_materialized_file(database)
            self.assertEqual(sqlite_probe["status"], "passed")
            self.assertEqual(sqlite_probe["probe"], "sqlite_quick_check")

    def test_inventory_backup_and_restore_cover_individual_family_and_recovery(self) -> None:
        module = self.load_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "evidence"
            recovery = root / "recovery"
            backup = root / "backup"
            restore = root / "restore"
            (evidence / "logs/debug/professor_fetch_cache").mkdir(parents=True)
            recovery.mkdir()
            individual = evidence / "individual.jsonl"
            individual.write_text('{"id": 1}\n', encoding="utf-8")
            family_paths = []
            for name in ("b.json", "a.json"):
                path = evidence / "logs/debug/professor_fetch_cache" / name
                path.write_text(json.dumps({"name": name}) + "\n", encoding="utf-8")
                family_paths.append(path)
            recovered = recovery / "salvage.dump"
            recovered.write_bytes(b"PGDMP-fixture")
            family_summary, _ = module.build_member_manifest(family_paths, evidence)
            inventory = {
                "sources": [
                    {
                        "kind": "fixture_jsonl",
                        "authority": "historical_local_evidence",
                        "path": "individual.jsonl",
                        "bytes": individual.stat().st_size,
                        "sha256": module.sha256_file(individual),
                    },
                    {
                        "kind": "professor_fetch_cache_family",
                        "authority": "historical_family_manifest",
                        "root": str(evidence),
                        "files": family_summary["files"],
                        "bytes": family_summary["bytes"],
                        "manifest_sha256": family_summary["legacy_manifest_sha256"],
                    },
                    {
                        "kind": "fixture_salvage",
                        "authority": "forensic_recovery_evidence",
                        "path": "salvage.dump",
                        "bytes": recovered.stat().st_size,
                        "sha256": module.sha256_file(recovered),
                    },
                ]
            }

            manifest = module.backup_inventory_sources(
                inventory=inventory,
                evidence_root=evidence,
                recovery_root=recovery,
                backup_root=backup,
                restore_root=restore,
                run_id="fixture-run",
                copied_at="2026-07-11T00:00:00Z",
            )
            self.assertEqual(len(manifest["sources"]), 3)
            self.assertTrue(all(item["hash_verified"] for item in manifest["sources"]))
            self.assertTrue(
                all(item["copy_independent"] for item in manifest["sources"])
            )

            verification = module.restore_inventory_sources(
                backup_manifest=manifest,
                backup_root=backup,
                restore_root=restore,
                verified_at="2026-07-11T00:01:00Z",
            )
            self.assertEqual(len(verification["sources"]), 3)
            self.assertTrue(
                all(item["status"] == "passed" for item in verification["sources"])
            )
            self.assertEqual(
                (restore / "workspace/individual.jsonl").read_bytes(),
                individual.read_bytes(),
            )
            self.assertEqual(
                (restore / "recovery/salvage.dump").read_bytes(),
                recovered.read_bytes(),
            )

    def test_cli_exposes_backup_restore_assembly_acceptance_and_gate_commands(self) -> None:
        result = subprocess.run(
            [sys.executable, str(MODULE_PATH), "--help"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for command in (
            "backup-inventory",
            "restore-inventory",
            "register-archive",
            "probe-milvus",
            "assemble",
            "create-acceptance",
            "verify-gate",
        ):
            self.assertIn(command, result.stdout)

    def test_archive_registration_content_addresses_archive_and_tree_manifest(self) -> None:
        module = self.load_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "source.tar"
            archive.write_bytes(b"archive bytes")
            tree_manifest = root / "source-tree.txt"
            tree_manifest.write_text(
                "f|./one|5|" + "a" * 64 + "\n",
                encoding="utf-8",
            )
            backup = root / "backup"

            record = module.register_archive_backup(
                source_id="fixture_tree",
                kind="fixture_tree",
                source_identity="fixture-source",
                source_root="/source",
                archive=archive,
                source_tree_manifest=tree_manifest,
                backup_root=backup,
                details={"mount_rw": False},
            )

            self.assertEqual(record["source_id"], "fixture_tree")
            self.assertTrue(record["copy_independent"])
            self.assertTrue(record["hash_verified"])
            self.assertEqual(record["source_tree_entries"], 1)
            self.assertEqual(
                module.sha256_file(backup / record["backup_archive_object_path"]),
                record["backup_archive_sha256"],
            )
            self.assertEqual(
                module.sha256_file(
                    backup / record["backup_tree_manifest_object_path"]
                ),
                record["source_tree_manifest_sha256"],
            )

    def test_container_mount_policy_rejects_implicit_volume_and_accepts_tmpfs_override(self) -> None:
        module = self.load_module()
        implicit_volume = {
            "Mounts": [
                {"Type": "bind", "Destination": "/archive", "RW": False},
                {"Type": "bind", "Destination": "/restore", "RW": True},
                {
                    "Type": "volume",
                    "Destination": "/var/lib/postgresql/data",
                    "RW": True,
                },
            ],
            "HostConfig": {"Tmpfs": None},
        }
        with self.assertRaisesRegex(module.BackupGateError, "unexpected persistent mount"):
            module.validate_container_mount_policy(
                implicit_volume,
                readonly_destinations={"/archive"},
                writable_destinations={"/restore"},
                tmpfs_destinations={"/var/lib/postgresql/data"},
            )

        explicit_tmpfs = {
            "Mounts": [
                {"Type": "bind", "Destination": "/archive", "RW": False},
                {"Type": "bind", "Destination": "/restore", "RW": True},
            ],
            "HostConfig": {
                "Tmpfs": {
                    "/var/lib/postgresql/data": "rw,noexec,nosuid,size=1048576"
                }
            },
        }
        result = module.validate_container_mount_policy(
            explicit_tmpfs,
            readonly_destinations={"/archive"},
            writable_destinations={"/restore"},
            tmpfs_destinations={"/var/lib/postgresql/data"},
        )
        self.assertEqual(result["persistent_mounts"], 2)
        self.assertEqual(result["tmpfs_mounts"], 1)

    def test_milvus_probe_rejects_original_and_inspects_only_verified_copy(self) -> None:
        module = self.load_module()

        class FakeMilvusClient:
            def __init__(self, uri: str) -> None:
                self.uri = uri
                self.closed = False

            def list_collections(self) -> list[str]:
                return ["papers", "professors"]

            def describe_collection(self, collection_name: str) -> dict[str, object]:
                return {
                    "collection_name": collection_name,
                    "fields": [
                        {"name": "id", "type": "INT64", "is_primary": True},
                        {
                            "name": "embedding",
                            "type": "FLOAT_VECTOR",
                            "params": {"dim": 4},
                        },
                    ],
                }

            def get_collection_stats(self, collection_name: str) -> dict[str, str]:
                return {"row_count": "2" if collection_name == "papers" else "1"}

            def close(self) -> None:
                self.closed = True

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "original.db"
            original.write_bytes(b"milvus-fixture")
            copy = root / "probe.db"
            copy.write_bytes(original.read_bytes())
            opened: list[FakeMilvusClient] = []

            def factory(uri: str) -> FakeMilvusClient:
                client = FakeMilvusClient(uri)
                opened.append(client)
                return client

            with self.assertRaisesRegex(module.BackupGateError, "forbidden Milvus"):
                module.probe_milvus_copy(
                    original,
                    forbidden_paths={original},
                    expected_sha256=module.sha256_file(original),
                    client_factory=factory,
                )
            self.assertEqual(opened, [])

            result = module.probe_milvus_copy(
                copy,
                forbidden_paths={original},
                expected_sha256=module.sha256_file(original),
                client_factory=factory,
            )
            self.assertEqual(result["collection_count"], 2)
            self.assertEqual(result["total_rows"], 3)
            self.assertEqual(result["collections"][0]["name"], "papers")
            self.assertTrue(opened[0].closed)

    @staticmethod
    def make_backup_manifest(module: ModuleType, source_ids: list[str]) -> dict[str, object]:
        return {
            "schema_version": "test-backup-v1",
            "source_inventory_sha256": "inventory-hash",
            "backup_root": "/backup",
            "restore_root": "/restore",
            "sources": [
                {
                    "source_id": source_id,
                    "copy_independent": True,
                    "hash_verified": True,
                }
                for source_id in source_ids
            ],
        }

    @staticmethod
    def make_restore_verification(source_ids: list[str]) -> dict[str, object]:
        return {
            "schema_version": "test-restore-v1",
            "backup_root": "/backup",
            "restore_root": "/restore",
            "required_probes": {
                "forensic": {"status": "passed"},
                "milvus": {"status": "passed"},
                "postgresql": {"status": "passed"},
            },
            "sources": [
                {"source_id": source_id, "status": "passed"}
                for source_id in source_ids
            ],
        }

    @staticmethod
    def make_acceptance_record(
        module: ModuleType,
        backup: dict[str, object],
        restore: dict[str, object],
    ) -> dict[str, object]:
        return {
            "state": "accepted",
            "backup_manifest_sha256": module.document_sha256(backup),
            "restore_verification_sha256": module.document_sha256(restore),
        }


if __name__ == "__main__":
    unittest.main()
