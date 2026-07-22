"""Run the frozen S11C pytest partitions through the Accepted S11B producer."""

from __future__ import annotations

from collections.abc import Callable
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
from types import ModuleType
from typing import Any, Literal, NamedTuple
import uuid


_ACCEPTED_RECEIPT_PATH = Path(
    ".agents/runs/rebuild-canonical-v2-knowledge-platform/"
    "s11b/verification-receipt.json"
)
_ACCEPTED_RECEIPT_SHA256 = (
    "cee1beebe2bdb1eba3f09b06e4e3c819167bbba14d5b6d6072f1f4cbafb0a945"
)
_ACCEPTED_PRODUCER_PATH = Path(
    "apps/miroflow-agent/scripts/capture_canonical_v2_s11b_baseline.py"
)
_ACCEPTED_PRODUCER_SHA256 = (
    "75fd8ea49cf6cab552c0eec1d196c9a41430543e10beb361bde14dd5e4638efa"
)
_ACCEPTED_OWNER_PATH = Path(
    "apps/miroflow-agent/tests/scripts/test_capture_canonical_v2_s11b_baseline.py"
)
_ACCEPTED_OWNER_SHA256 = (
    "47c060bb589bac6ae5c593eea2dfebf3272dd23b12e690662cd3e7322f95e1b3"
)
_S11C_EVIDENCE_ROOT = Path(".agents/runs/rebuild-canonical-v2-knowledge-platform/s11c")
_SIGNATURE_SCHEMA_VERSION = "canonical-v2-s11b-baseline-signature-v3"
_ADMIN_MARKER = "not requires_classifier_llm"
_ADMIN_DESELECTED = ("tests/test_classifier_benchmark.py::test_classifier_benchmark",)
_RECEIPT_NAME = "guarded-partitions-receipt.json"


class GuardedPartitionCaptureError(RuntimeError):
    """Accepted authority, partition, guard, or artifact validation failed."""


class _PartitionSpec(NamedTuple):
    run_id: str
    cwd: str
    pytest_args: tuple[str, ...]


_TASK5_PARTITIONS = (
    _PartitionSpec(
        "admin-no-external",
        "apps/admin-console",
        ("-m", _ADMIN_MARKER, "tests"),
    ),
    _PartitionSpec(
        "canonical-v2-predecessors",
        "apps/miroflow-agent",
        (
            "tests/canonical_v2",
            "--ignore=tests/canonical_v2/test_consumer_acceptance_contract.py",
        ),
    ),
)


class AcceptedS11BAuthority(NamedTuple):
    receipt_sha256: str
    producer_sha256: str
    owner_sha256: str
    producer: ModuleType


class GuardedPartitionCaptureResult(NamedTuple):
    capture_mode: str
    receipt: dict[str, Any]
    receipt_bytes: bytes
    receipt_sha256: str


class _OwnedLink(NamedTuple):
    path: Path
    st_dev: int
    st_ino: int


Runner = Callable[..., Any]
CaptureMode = Literal["real_subprocess", "synthetic_test_only"]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_exact_producer(
    source_bytes: bytes,
    *,
    path: Path,
    repository_root: Path,
) -> ModuleType:
    agent_root = str(repository_root / "apps/miroflow-agent")
    original_sys_path = list(sys.path)
    if agent_root not in sys.path:
        sys.path.insert(0, agent_root)
    module_name = "_s11c_exact_accepted_s11b_guard"
    spec = importlib.util.spec_from_loader(module_name, loader=None, origin=str(path))
    if spec is None:
        raise GuardedPartitionCaptureError("Accepted S11B producer cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(path)
    prior = sys.modules.get(module_name)
    sys.modules[module_name] = module
    try:
        code = compile(source_bytes, str(path), "exec", dont_inherit=True)
        exec(code, module.__dict__)
    finally:
        if prior is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = prior
        sys.path[:] = original_sys_path
    return module


def verify_accepted_s11b_authority(
    repository_root: Path,
) -> AcceptedS11BAuthority:
    """Verify all raw hashes before importing the Accepted guard producer."""

    repository_root = repository_root.resolve(strict=True)
    receipt_path = repository_root / _ACCEPTED_RECEIPT_PATH
    producer_path = repository_root / _ACCEPTED_PRODUCER_PATH
    owner_path = repository_root / _ACCEPTED_OWNER_PATH
    for label, path in (
        ("receipt", receipt_path),
        ("producer", producer_path),
        ("producer owner", owner_path),
    ):
        if not path.is_file():
            raise GuardedPartitionCaptureError(f"Accepted S11B {label} is absent")

    receipt_bytes = receipt_path.read_bytes()
    producer_bytes = producer_path.read_bytes()
    owner_bytes = owner_path.read_bytes()
    receipt_sha256 = hashlib.sha256(receipt_bytes).hexdigest()
    producer_sha256 = hashlib.sha256(producer_bytes).hexdigest()
    owner_sha256 = hashlib.sha256(owner_bytes).hexdigest()
    if receipt_sha256 != _ACCEPTED_RECEIPT_SHA256:
        raise GuardedPartitionCaptureError("Accepted S11B receipt hash drifted")
    if producer_sha256 != _ACCEPTED_PRODUCER_SHA256:
        raise GuardedPartitionCaptureError("Accepted S11B producer hash drifted")
    if owner_sha256 != _ACCEPTED_OWNER_SHA256:
        raise GuardedPartitionCaptureError("Accepted S11B producer owner hash drifted")

    try:
        receipt = json.loads(receipt_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GuardedPartitionCaptureError("Accepted S11B receipt is invalid") from exc
    artifacts = (
        receipt.get("implementation_artifacts") if isinstance(receipt, dict) else None
    )
    if (
        not isinstance(receipt, dict)
        or receipt.get("status") != "Accepted"
        or receipt.get("slice_id") != "S11B"
        or not isinstance(artifacts, dict)
        or artifacts.get(_ACCEPTED_PRODUCER_PATH.as_posix())
        != _ACCEPTED_PRODUCER_SHA256
        or artifacts.get(_ACCEPTED_OWNER_PATH.as_posix()) != _ACCEPTED_OWNER_SHA256
    ):
        raise GuardedPartitionCaptureError(
            "Accepted S11B receipt does not bind the producer and owner"
        )

    producer = _load_exact_producer(
        producer_bytes,
        path=producer_path,
        repository_root=repository_root,
    )
    if (
        type(producer.SENSITIVE_ENV_NAMES) is not tuple
        or len(producer.SENSITIVE_ENV_NAMES) != 49
        or tuple(sorted(producer.SENSITIVE_ENV_NAMES)) != producer.SENSITIVE_ENV_NAMES
        or producer._SIGNATURE_VERSION != _SIGNATURE_SCHEMA_VERSION
        or producer._ADMIN_MARKER != _ADMIN_MARKER
        or producer._ADMIN_DESELECTED != _ADMIN_DESELECTED
    ):
        raise GuardedPartitionCaptureError("Accepted S11B guard invariants drifted")
    return AcceptedS11BAuthority(
        receipt_sha256,
        producer_sha256,
        owner_sha256,
        producer,
    )


def _relative(path: Path, *, cwd: Path) -> str:
    return Path(os.path.relpath(path, start=cwd)).as_posix()


def _display(path: Path, *, repository_root: Path) -> str:
    resolved = path.resolve(strict=False)
    try:
        return resolved.relative_to(repository_root).as_posix()
    except ValueError:
        return resolved.as_posix()


def _producer_specs(
    producer: ModuleType,
    *,
    repository_root: Path,
    evidence_root: Path,
) -> tuple[Any, ...]:
    prefix = (
        "uv",
        "run",
        "pytest",
        "-o",
        "addopts=",
        "-p",
        "no:cacheprovider",
    )
    configured = []
    for spec in _TASK5_PARTITIONS:
        cwd = repository_root / spec.cwd
        collect_root = evidence_root / "tmp" / spec.run_id / "collect" / "pytest"
        run_root = evidence_root / "tmp" / spec.run_id / "pytest"
        junit = evidence_root / "junit" / f"{spec.run_id}.xml"
        configured.append(
            producer.RunSpec(
                run_id=spec.run_id,
                cwd=spec.cwd,
                collection_argv=(
                    *prefix,
                    *spec.pytest_args,
                    f"--basetemp={_relative(collect_root, cwd=cwd)}",
                    "--collect-only",
                    "-q",
                ),
                argv=(
                    *prefix,
                    *spec.pytest_args,
                    f"--basetemp={_relative(run_root, cwd=cwd)}",
                    f"--junitxml={_relative(junit, cwd=cwd)}",
                    "-q",
                ),
            )
        )
    return tuple(configured)


def _final_artifact_paths(output_root: Path) -> tuple[Path, ...]:
    paths = [output_root / "baseline-row.json", output_root / _RECEIPT_NAME]
    for spec in _TASK5_PARTITIONS:
        paths.extend(
            (
                output_root / "collected" / f"{spec.run_id}.txt",
                output_root / "junit" / f"{spec.run_id}.xml",
            )
        )
    return tuple(paths)


def _validate_producer_receipt(
    baseline_receipt: object,
    *,
    authority: AcceptedS11BAuthority,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    baseline = (
        baseline_receipt.get("broad_test_baseline")
        if isinstance(baseline_receipt, dict)
        else None
    )
    if not isinstance(baseline, dict):
        raise GuardedPartitionCaptureError("Accepted producer receipt is absent")
    guard = baseline.get("guard_preflight")
    runs = baseline.get("runs")
    if not isinstance(guard, dict) or not isinstance(runs, list):
        raise GuardedPartitionCaptureError(
            "Accepted producer guard or run receipt is absent"
        )
    child_receipts = guard.get("child_receipts")
    if (
        baseline.get("signature_schema_version") != _SIGNATURE_SCHEMA_VERSION
        or baseline.get("producer_path") != _ACCEPTED_PRODUCER_PATH.as_posix()
        or baseline.get("producer_sha256") != authority.producer_sha256
        or [row.get("run_id") for row in runs]
        != [spec.run_id for spec in _TASK5_PARTITIONS]
        or not isinstance(child_receipts, list)
        or len(child_receipts) != len(_TASK5_PARTITIONS) * 2
        or any(
            not isinstance(receipt, dict)
            or receipt.get("session_finished") is not True
            or receipt.get("unconfigured") is not True
            for receipt in child_receipts
        )
        or guard.get("cleanup") is not True
        or guard.get("admin_marker_expression") != _ADMIN_MARKER
        or guard.get("admin_deselected_nodeids") != list(_ADMIN_DESELECTED)
    ):
        raise GuardedPartitionCaptureError(
            "Accepted producer emitted an invalid terminal receipt"
        )
    return guard, runs


def _link_without_overwrite(source: Path, destination: Path) -> _OwnedLink:
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_identity = source.stat()
    try:
        os.link(source, destination)
    except FileExistsError as exc:
        raise GuardedPartitionCaptureError(
            "artifact appeared during promotion"
        ) from exc
    destination_identity = destination.lstat()
    if (
        destination_identity.st_dev != source_identity.st_dev
        or destination_identity.st_ino != source_identity.st_ino
    ):
        raise GuardedPartitionCaptureError("promoted artifact identity changed")
    return _OwnedLink(
        destination,
        destination_identity.st_dev,
        destination_identity.st_ino,
    )


def _unlink_if_owned(owned: _OwnedLink) -> None:
    try:
        current = owned.path.lstat()
    except FileNotFoundError:
        return
    if current.st_dev == owned.st_dev and current.st_ino == owned.st_ino:
        owned.path.unlink()


def _capture_guarded_partitions(
    *,
    repository_root: Path,
    output_root: Path,
    runner: Runner | None,
    capture_mode: CaptureMode,
) -> GuardedPartitionCaptureResult:
    repository_root = repository_root.resolve(strict=True)
    output_root = output_root.resolve(strict=False)
    exact_root = (repository_root / _S11C_EVIDENCE_ROOT).resolve(strict=False)
    if capture_mode == "real_subprocess" and output_root != exact_root:
        raise GuardedPartitionCaptureError(
            "real capture requires the exact S11C evidence root"
        )
    if capture_mode == "real_subprocess" and runner is not None:
        raise GuardedPartitionCaptureError(
            "real capture requires the Accepted default subprocess runner"
        )
    if capture_mode == "synthetic_test_only" and runner is None:
        raise GuardedPartitionCaptureError("synthetic capture requires a test runner")

    output_root.mkdir(parents=True, exist_ok=True)
    if any(path.exists() for path in _final_artifact_paths(output_root)) or list(
        output_root.glob(".guarded-receipt-*")
    ):
        raise GuardedPartitionCaptureError("guarded partition target already exists")

    authority = verify_accepted_s11b_authority(repository_root)
    producer = authority.producer
    active_runner = producer._default_runner if runner is None else runner
    setattr(
        producer,
        "RUN_SPECS",
        _producer_specs(
            producer,
            repository_root=repository_root,
            evidence_root=output_root,
        ),
    )
    stage = output_root / f".guarded-receipt-{uuid.uuid4().hex}"
    stage.mkdir(mode=0o700)
    owned_outputs: list[_OwnedLink] = []
    try:
        baseline_receipt = producer.capture_baseline(
            repository_root=repository_root,
            output_root=stage,
            runner=active_runner,
        )
        guard, producer_runs = _validate_producer_receipt(
            baseline_receipt,
            authority=authority,
        )
        runs: list[dict[str, Any]] = []
        promotion_pairs: list[tuple[Path, Path]] = []
        for spec, producer_row in zip(
            _TASK5_PARTITIONS,
            producer_runs,
            strict=True,
        ):
            row = dict(producer_row)
            source_nodeids = stage / "collected" / f"{spec.run_id}.txt"
            source_junit = stage / "junit" / f"{spec.run_id}.xml"
            final_nodeids = output_root / "collected" / f"{spec.run_id}.txt"
            final_junit = output_root / "junit" / f"{spec.run_id}.xml"
            if _sha256(source_nodeids) != row.get(
                "collected_nodeids_sha256"
            ) or _sha256(source_junit) != row.get("junit_xml_sha256"):
                raise GuardedPartitionCaptureError(
                    "producer artifact hash differs before promotion"
                )
            row["collected_nodeids_path"] = _display(
                final_nodeids,
                repository_root=repository_root,
            )
            row["junit_xml_path"] = _display(
                final_junit,
                repository_root=repository_root,
            )
            runs.append(row)
            promotion_pairs.extend(
                ((source_nodeids, final_nodeids), (source_junit, final_junit))
            )

        guard["terminal_receipts_captured_after_process_exit"] = (
            capture_mode == "real_subprocess"
        )
        guard["wrapper_stage_cleanup"] = True
        receipt = {
            "schema_version": ("canonical-v2-s11c-guarded-partitions-receipt-v1"),
            "capture_mode": capture_mode,
            "accepted_s11b": {
                "receipt_path": _ACCEPTED_RECEIPT_PATH.as_posix(),
                "receipt_sha256": authority.receipt_sha256,
                "producer_path": _ACCEPTED_PRODUCER_PATH.as_posix(),
                "producer_sha256": authority.producer_sha256,
                "owner_path": _ACCEPTED_OWNER_PATH.as_posix(),
                "owner_sha256": authority.owner_sha256,
            },
            "signature_schema_version": _SIGNATURE_SCHEMA_VERSION,
            "guard_preflight": guard,
            "runs": runs,
        }
        receipt_bytes = producer._canonical_bytes(receipt)
        receipt_sha256 = hashlib.sha256(receipt_bytes).hexdigest()
        for source, destination in promotion_pairs:
            owned_outputs.append(_link_without_overwrite(source, destination))
        if capture_mode == "real_subprocess":
            stage_receipt = stage / "wrapper-receipt.json"
            stage_receipt.write_bytes(receipt_bytes)
            final_receipt = output_root / _RECEIPT_NAME
            owned_outputs.append(_link_without_overwrite(stage_receipt, final_receipt))
        shutil.rmtree(stage)
        if stage.exists():
            raise GuardedPartitionCaptureError("wrapper stage cleanup failed")
        return GuardedPartitionCaptureResult(
            capture_mode,
            receipt,
            receipt_bytes,
            receipt_sha256,
        )
    except BaseException as exc:
        for owned in reversed(owned_outputs):
            _unlink_if_owned(owned)
        shutil.rmtree(stage, ignore_errors=True)
        if isinstance(exc, producer.BaselineCaptureError):
            raise GuardedPartitionCaptureError(str(exc)) from exc
        raise


def _capture_guarded_partitions_for_test(
    *,
    repository_root: Path,
    output_root: Path,
    runner: Runner,
) -> GuardedPartitionCaptureResult:
    """Exercise the exact partitions without minting a real acceptance receipt."""

    return _capture_guarded_partitions(
        repository_root=repository_root,
        output_root=output_root,
        runner=runner,
        capture_mode="synthetic_test_only",
    )


def capture_guarded_partitions(
    *,
    repository_root: Path,
) -> GuardedPartitionCaptureResult:
    """Run only the frozen Task 5 partitions with the real subprocess runner."""

    return _capture_guarded_partitions(
        repository_root=repository_root,
        output_root=repository_root / _S11C_EVIDENCE_ROOT,
        runner=None,
        capture_mode="real_subprocess",
    )
