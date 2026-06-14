from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent
    / "scripts"
    / "audit_professor_seed_adapter_coverage.py"
)


def _import_cli():
    spec = importlib.util.spec_from_file_location(
        "audit_professor_seed_adapter_coverage",
        _SCRIPT_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_missing_resolver_without_approved_blocked_issue_fails_guard() -> None:
    cli = _import_cli()
    row = cli.SeedCoverageRow(
        seed_id=24,
        school="深圳信息职业技术大学",
        department="教研教学",
        seed_url="https://zd.suit-sz.edu.cn/jyjx/jsfc.htm",
        last_run_status="adapter_missing",
    )

    results = cli.build_coverage_matrix(
        [row],
        adapter_resolver=lambda _seed: None,
        approved_blocked_by_seed_id={},
    )

    assert results == [
        cli.SeedCoverageResult(
            seed_id=24,
            school="深圳信息职业技术大学",
            department="教研教学",
            seed_url="https://zd.suit-sz.edu.cn/jyjx/jsfc.htm",
            last_run_status="adapter_missing",
            resolver_result=None,
            coverage_state="missing",
            diagnostic_status="adapter_missing",
            issue_id_or_reason="missing_resolver",
        )
    ]
    assert cli.guard_exit_code(results) == 1


def test_full_matrix_output_includes_covered_missing_and_approved_blocked_rows() -> None:
    cli = _import_cli()
    rows = [
        cli.SeedCoverageRow(
            seed_id=1,
            school="南方科技大学",
            department=None,
            seed_url="https://example.edu.cn/sustech",
            last_run_status="success",
        ),
        cli.SeedCoverageRow(
            seed_id=24,
            school="深圳信息职业技术大学",
            department="教研教学",
            seed_url="https://zd.suit-sz.edu.cn/jyjx/jsfc.htm",
            last_run_status="adapter_missing",
        ),
        cli.SeedCoverageRow(
            seed_id=25,
            school="电子科技大学（深圳）高等研究院",
            department="计算机科学与工程",
            seed_url="https://sias.uestc.edu.cn/rcpy/dsjs1/jsjkxygc.htm",
            last_run_status="failure",
        ),
    ]

    results = cli.build_coverage_matrix(
        rows,
        adapter_resolver=lambda seed: (
            "sustech-static-roster"
            if "sustech" in seed.roster_url
            else None
        ),
        approved_blocked_by_seed_id={
            25: cli.ApprovedBlockedIssue(
                issue_id="ISSUE-25",
                failure_class="fetch_blocked",
                stage="discovery",
                description="fetch_blocked: tokenized challenge page",
            )
        },
    )

    lines = cli.format_matrix(results)

    assert cli.guard_exit_code(results) == 1
    assert lines[0].split("\t") == [
        "seed_id",
        "school",
        "department",
        "seed_url",
        "last_run_status",
        "resolver_result",
        "coverage_state",
        "diagnostic_status",
        "issue_id_or_reason",
    ]
    assert len(lines) == 4
    assert "1\t南方科技大学\t\t" in lines[1]
    assert "\tresolver_covered\tadapter:sustech-static-roster\tresolver:sustech-static-roster" in lines[1]
    assert "24\t深圳信息职业技术大学\t教研教学\t" in lines[2]
    assert "\tmissing\tadapter_missing\tmissing_resolver" in lines[2]
    assert "25\t电子科技大学（深圳）高等研究院\t计算机科学与工程\t" in lines[3]
    assert "\tapproved_blocked\tfetch_blocked\tISSUE-25" in lines[3]
