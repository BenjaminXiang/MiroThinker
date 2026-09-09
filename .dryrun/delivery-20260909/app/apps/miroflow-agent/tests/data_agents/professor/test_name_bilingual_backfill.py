# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace


def _load_module_from_path(module_name: str, module_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Unable to load module spec for {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_script_module():
    return _load_module_from_path(
        "run_name_bilingual_backfill",
        Path(__file__).resolve().parents[3]
        / "scripts"
        / "run_name_bilingual_backfill.py",
    )


class _FakeCursor:
    def __init__(self, rowcount: int = 1):
        self.rowcount = rowcount


class _FakeConn:
    def __init__(self):
        self.calls: list[tuple[str, tuple | None]] = []

    def execute(self, sql: str, params=None):
        normalized = " ".join(sql.split())
        recorded = tuple(params) if params is not None else None
        self.calls.append((normalized, recorded))
        return _FakeCursor(1)


def test_classify_name_shape_detects_cjk_latin_mixed_and_filled():
    module = _load_script_module()

    assert module.classify_name_shape(
        canonical_name="黄建伟",
        canonical_name_en=None,
        canonical_name_zh=None,
    ) == "cjk_only"
    assert module.classify_name_shape(
        canonical_name="Jianwei Huang",
        canonical_name_en=None,
        canonical_name_zh=None,
    ) == "latin_only"
    assert module.classify_name_shape(
        canonical_name="黄建伟 Jianwei Huang",
        canonical_name_en=None,
        canonical_name_zh=None,
    ) == "mixed_or_other"
    assert module.classify_name_shape(
        canonical_name="黄建伟",
        canonical_name_en="Jianwei Huang",
        canonical_name_zh="黄建伟",
    ) == "already_filled"


def test_process_rows_cjk_only_uses_llm_and_gate_then_updates_anchor_and_en():
    module = _load_script_module()
    conn = _FakeConn()
    llm_calls: list[tuple[str, str]] = []
    gate_calls: list[tuple[str, str]] = []

    def propose(row, classification, *, llm_client, llm_model):
        llm_calls.append((row.professor_id, classification))
        assert llm_model == "gemma4-test"
        return module.NameProposal(
            candidate_name="Jianwei Huang",
            confidence=0.93,
            reasoning="official pinyin",
        )

    def verify(candidate, *, llm_client, llm_model):
        gate_calls.append((candidate.canonical_name, candidate.candidate_name_en))
        assert llm_model == "gemma4-test"
        return SimpleNamespace(
            accepted=True,
            confidence=0.95,
            reasoning="same person",
            error=None,
        )

    row = module.NameBackfillRow(
        professor_id="PROF-1",
        canonical_name="黄建伟",
        canonical_name_en=None,
        canonical_name_zh=None,
        institution="香港中文大学（深圳）",
        source_url="https://sse.cuhk.edu.cn/faculty/jianwei-huang",
    )

    stats = module.process_rows(
        conn,
        [row],
        apply=True,
        llm_client=object(),
        llm_model="gemma4-test",
        propose_name_fn=propose,
        verify_name_identity_fn=verify,
    )

    assert stats.examined == 1
    assert stats.updated == 1
    assert stats.issues_inserted == 0
    assert stats.llm_attempted == 1
    assert llm_calls == [("PROF-1", "cjk_only")]
    assert gate_calls == [("黄建伟", "Jianwei Huang")]

    update_calls = [call for call in conn.calls if "UPDATE professor" in call[0]]
    assert len(update_calls) == 1
    _, params = update_calls[0]
    assert params is not None
    assert "PROF-1" in params
    assert "黄建伟" in params
    assert "Jianwei Huang" in params


def test_process_rows_cjk_only_with_existing_english_copies_missing_zh_without_llm():
    module = _load_script_module()
    conn = _FakeConn()

    def should_not_propose(*args, **kwargs):  # pragma: no cover - defensive
        raise AssertionError("LLM should not run when only the zh anchor copy is missing")

    def should_not_verify(*args, **kwargs):  # pragma: no cover - defensive
        raise AssertionError("gate should not run when no cross-language proposal is needed")

    row = module.NameBackfillRow(
        professor_id="PROF-2",
        canonical_name="黄建伟",
        canonical_name_en="Jianwei Huang",
        canonical_name_zh=None,
        institution="香港中文大学（深圳）",
        source_url="https://sse.cuhk.edu.cn/faculty/jianwei-huang",
    )

    stats = module.process_rows(
        conn,
        [row],
        apply=True,
        llm_client=object(),
        llm_model="gemma4-test",
        propose_name_fn=should_not_propose,
        verify_name_identity_fn=should_not_verify,
    )

    assert stats.examined == 1
    assert stats.updated == 1
    assert stats.issues_inserted == 0
    assert stats.llm_attempted == 0

    update_calls = [call for call in conn.calls if "UPDATE professor" in call[0]]
    assert len(update_calls) == 1
    _, params = update_calls[0]
    assert params == ("黄建伟", "PROF-2")


def test_process_rows_latin_only_rejection_files_issue_without_update():
    module = _load_script_module()
    conn = _FakeConn()
    llm_calls: list[tuple[str, str]] = []
    gate_calls: list[tuple[str, str]] = []

    def propose(row, classification, *, llm_client, llm_model):
        llm_calls.append((row.professor_id, classification))
        return module.NameProposal(
            candidate_name="黄建伟",
            confidence=0.91,
            reasoning="candidate found from official domain context",
        )

    def verify(candidate, *, llm_client, llm_model):
        gate_calls.append((candidate.canonical_name, candidate.candidate_name_en))
        return SimpleNamespace(
            accepted=False,
            confidence=0.41,
            reasoning="insufficient certainty",
            error=None,
        )

    row = module.NameBackfillRow(
        professor_id="PROF-3",
        canonical_name="Jianwei Huang",
        canonical_name_en=None,
        canonical_name_zh=None,
        institution="香港中文大学（深圳）",
        source_url="https://sse.cuhk.edu.cn/faculty/jianwei-huang",
    )

    stats = module.process_rows(
        conn,
        [row],
        apply=True,
        llm_client=object(),
        llm_model="gemma4-test",
        propose_name_fn=propose,
        verify_name_identity_fn=verify,
    )

    assert stats.examined == 1
    assert stats.updated == 0
    assert stats.issues_inserted == 1
    assert stats.llm_attempted == 1
    assert llm_calls == [("PROF-3", "latin_only")]
    assert gate_calls == [("黄建伟", "Jianwei Huang")]

    update_calls = [call for call in conn.calls if "UPDATE professor" in call[0]]
    issue_calls = [call for call in conn.calls if "INSERT INTO pipeline_issue" in call[0]]
    assert update_calls == []
    assert len(issue_calls) == 1
    _, params = issue_calls[0]
    assert params is not None
    assert params[0] == "PROF-3"
    assert params[2] == "medium"
    assert params[-1] == "round_7_19a_name_bilingual"
