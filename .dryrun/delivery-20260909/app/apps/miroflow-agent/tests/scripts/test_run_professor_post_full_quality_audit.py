from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path

from src.data_agents.professor.post_full_quality_audit import (
    FullRunEvidence,
    PostFullQualityMetrics,
)


_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent
    / "scripts"
    / "run_professor_post_full_quality_audit.py"
)


def _import_cli():
    spec = importlib.util.spec_from_file_location(
        "run_professor_post_full_quality_audit",
        _SCRIPT_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_cli_run_prints_deterministic_read_only_report(monkeypatch) -> None:
    cli = _import_cli()

    def fake_load_inputs(conn):
        assert conn == "CONN"
        return cli.PostFullAuditInputs(
            full_runs=[
                FullRunEvidence(
                    seed_id=7,
                    run_id="RUN-7",
                    status="succeeded",
                    trigger_mode="full",
                    failure_class="success",
                    items_processed=98,
                    items_failed=0,
                    written_profile_count=98,
                    diagnostic_profile_count=98,
                )
            ],
            metrics=PostFullQualityMetrics.empty(canonical_total=98),
            field_defects=[],
        )

    monkeypatch.setattr(cli, "load_post_full_audit_inputs", fake_load_inputs)
    output = io.StringIO()

    exit_code = cli.run(conn="CONN", output=output, selected_seed_ids=[7], blocked_seed_ids=[])

    assert exit_code == 0
    rendered = output.getvalue()
    assert '"p9_readiness": "ready"' in rendered
    assert '"canonical_total": 98' in rendered
