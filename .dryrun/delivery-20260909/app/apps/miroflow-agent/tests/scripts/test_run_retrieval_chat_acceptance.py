from __future__ import annotations

import sys
from pathlib import Path

import pytest

from src.data_agents.service.retrieval import Evidence

_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent
    / "scripts"
    / "run_retrieval_chat_acceptance.py"
)


def _import_cli_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "run_retrieval_chat_acceptance",
        _SCRIPT_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _professor_evidence(**metadata):
    return Evidence(
        object_type="professor",
        object_id="PROF-SUSTECH-1",
        score=0.91,
        snippet="张三 南方科技大学 计算机科学与工程系 教授",
        source_url="https://www.sustech.edu.cn/faculties/zhangsan.html",
        metadata={
            "name": "张三",
            "institution": "南方科技大学",
            "professor_retrieval_index": "identity",
            **metadata,
        },
    )


def _paper_evidence(**metadata):
    return Evidence(
        object_type="paper",
        object_id="PAPER-SUSTECH-1",
        score=0.88,
        snippet="Target paper abstract.",
        source_url=None,
        metadata={
            "title_clean": "Force Control for Legged Robots",
            "chunk_id": "PAPER-SUSTECH-1:abstract:0",
            "chunk_type": "abstract",
            **metadata,
        },
    )


def test_cli_help_exits_zero(capsys, monkeypatch):
    cli = _import_cli_module()
    monkeypatch.setattr(sys, "argv", ["run_retrieval_chat_acceptance.py", "--help"])

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "--professor-query" in captured.out
    assert "--paper-query" in captured.out
    assert "--chat-url" in captured.out


def test_professor_assertion_requires_target_and_traceability():
    cli = _import_cli_module()

    result = cli.assert_professor_retrieval(
        [_professor_evidence()],
        expected_id=None,
        expected_name="张三",
    )

    assert result.ok is True
    assert result.evidence["object_id"] == "PROF-SUSTECH-1"


def test_professor_assertion_fails_when_traceability_missing():
    cli = _import_cli_module()
    evidence = Evidence(
        object_type="professor",
        object_id="PROF-SUSTECH-1",
        score=0.91,
        snippet="张三 南方科技大学",
        source_url=None,
        metadata={"name": "张三"},
    )

    result = cli.assert_professor_retrieval(
        [evidence],
        expected_id="PROF-SUSTECH-1",
        expected_name=None,
    )

    assert result.ok is False
    assert "traceability" in result.message


def test_paper_assertion_accepts_title_match_with_chunk_traceability():
    cli = _import_cli_module()

    result = cli.assert_paper_retrieval(
        [_paper_evidence()],
        expected_id=None,
        expected_title="Force Control for Legged Robots",
    )

    assert result.ok is True
    assert result.evidence["metadata"]["chunk_id"] == "PAPER-SUSTECH-1:abstract:0"


def test_paper_assertion_reports_top_results_when_target_missing():
    cli = _import_cli_module()

    result = cli.assert_paper_retrieval(
        [_paper_evidence(title_clean="Different Paper")],
        expected_id=None,
        expected_title="Force Control for Legged Robots",
    )

    assert result.ok is False
    assert "top_results" in result.evidence


def test_chat_assertion_requires_expected_domains_and_evidence():
    cli = _import_cli_module()
    payload = {
        "query_type": "D_cross_domain_topic",
        "citations": [{"type": "professor", "id": "PROF-1", "title": "张三"}],
        "structured_payload": {
            "retrieval_evidence": [
                {"type": "paper", "id": "PAPER-1", "title": "Target paper"}
            ]
        },
    }

    result = cli.assert_chat_response(
        payload,
        expected_domains={"professor", "paper"},
        expected_professor_id="PROF-1",
        expected_paper_id="PAPER-1",
    )

    assert result.ok is True
    assert result.evidence["side_effect"] == (
        "POST /api/chat creates or updates chat session state"
    )


def test_chat_assertion_fails_when_expected_professor_target_missing():
    cli = _import_cli_module()
    payload = {
        "query_type": "D_cross_domain_topic",
        "citations": [
            {
                "type": "professor",
                "id": "PROF-WRONG",
                "title": "Other Professor",
                "snippet": "Wrong professor.",
            }
        ],
        "structured_payload": {
            "retrieval_evidence": [
                {
                    "type": "paper",
                    "id": "PAPER-1",
                    "title": "Relevant paper",
                    "snippet": "Paper evidence.",
                }
            ]
        },
    }

    result = cli.assert_chat_response(
        payload,
        expected_domains={"professor", "paper"},
        expected_professor_id="PROF-EXPECTED",
    )

    assert result.ok is False
    assert "expected professor target" in result.message
    assert result.evidence["expected"]["professor_id"] == "PROF-EXPECTED"


def test_chat_assertion_fails_when_expected_target_lacks_traceability():
    cli = _import_cli_module()
    payload = {
        "query_type": "D_cross_domain_topic",
        "citations": [{"type": "paper", "id": "PAPER-EXPECTED"}],
        "structured_payload": {"retrieval_evidence": []},
    }

    result = cli.assert_chat_response(
        payload,
        expected_domains={"paper"},
        expected_paper_id="PAPER-EXPECTED",
    )

    assert result.ok is False
    assert "traceability" in result.message
    assert result.evidence["match"]["id"] == "PAPER-EXPECTED"


def test_chat_assertion_only_checks_targets_for_expected_domains():
    cli = _import_cli_module()
    payload = {
        "query_type": "C_cross_domain_related",
        "citations": [
            {
                "type": "professor",
                "id": "PROF-EXPECTED",
                "title": "Expected Professor",
                "snippet": "Related professor evidence.",
            }
        ],
        "structured_payload": {"retrieval_evidence": []},
    }

    result = cli.assert_chat_response(
        payload,
        expected_domains={"professor"},
        expected_professor_id="PROF-EXPECTED",
        expected_paper_id="PAPER-USED-FOR-DIRECT-RETRIEVAL-ONLY",
    )

    assert result.ok is True


def test_cli_closes_local_milvus_before_live_chat_post(monkeypatch):
    cli = _import_cli_module()

    class _FakeMilvusClient:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

    class _FakeService:
        def __init__(self) -> None:
            self._milvus_client = _FakeMilvusClient()

        def retrieve(self, query, *, domains, **_kwargs):
            if domains == ("professor",):
                return [_professor_evidence()]
            if domains == ("paper",):
                return [_paper_evidence()]
            return []

    service = _FakeService()
    monkeypatch.setattr(cli, "_make_retrieval_service", lambda **_kwargs: service)

    def _fake_post_chat(*_args, **_kwargs):
        assert service._milvus_client.closed is True
        return {
            "query_type": "D_cross_domain_topic",
            "citations": [
                {
                    "type": "professor",
                    "id": "PROF-SUSTECH-1",
                    "title": "张三",
                    "snippet": "张三 南方科技大学 计算机科学与工程系 教授",
                }
            ],
            "structured_payload": {
                "retrieval_evidence": [
                    {
                        "type": "paper",
                        "id": "PAPER-SUSTECH-1",
                        "title": "Force Control for Legged Robots",
                        "snippet": "Target paper abstract.",
                    }
                ]
            },
        }

    monkeypatch.setattr(cli, "_post_chat", _fake_post_chat)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_retrieval_chat_acceptance.py",
            "--database-url",
            "postgresql://example/test",
            "--milvus-uri",
            "/tmp/test-milvus.db",
            "--professor-query",
            "南方科技大学 张三",
            "--professor-id",
            "PROF-SUSTECH-1",
            "--paper-query",
            "Force Control for Legged Robots",
            "--paper-id",
            "PAPER-SUSTECH-1",
            "--chat-url",
            "http://127.0.0.1:18188",
            "--chat-expected-domain",
            "professor",
            "--chat-expected-domain",
            "paper",
        ],
    )

    assert cli.main() == 0


def test_cli_chat_only_mode_does_not_open_local_retrieval(monkeypatch):
    cli = _import_cli_module()

    def _fail_make_service(**_kwargs):
        raise AssertionError("chat-only mode must not open local retrieval service")

    monkeypatch.setattr(cli, "_make_retrieval_service", _fail_make_service)
    monkeypatch.setattr(
        cli,
        "_post_chat",
        lambda *_args, **_kwargs: {
            "query_type": "D_cross_domain_topic",
            "citations": [
                {"type": "professor", "id": "PROF-1", "title": "陈晓非"}
            ],
            "structured_payload": {
                "retrieval_evidence": [
                    {"type": "paper", "id": "PAPER-1", "title": "Target paper"}
                ]
            },
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_retrieval_chat_acceptance.py",
            "--skip-retrieval-checks",
            "--chat-url",
            "http://127.0.0.1:18188",
            "--chat-query",
            "南方科技大学陈晓非教授的研究方向和论文情况",
            "--chat-expected-domain",
            "professor",
            "--chat-expected-domain",
            "paper",
            "--professor-id",
            "PROF-1",
            "--paper-id",
            "PAPER-1",
        ],
    )

    assert cli.main() == 0


def test_chat_assertion_fails_when_expected_target_is_not_provided():
    cli = _import_cli_module()
    payload = {
        "query_type": "D_cross_domain_topic",
        "citations": [{"type": "professor", "id": "PROF-1", "title": "陈晓非"}],
        "structured_payload": {
            "retrieval_evidence": [
                {"type": "paper", "id": "PAPER-1", "title": "Target paper"}
            ]
        },
    }

    result = cli.assert_chat_response(
        payload,
        expected_domains={"professor", "paper"},
    )

    assert result.ok is False
    assert "expected professor target is required" in result.message


def test_cli_chat_only_mode_requires_targets_for_expected_domains(monkeypatch):
    cli = _import_cli_module()
    monkeypatch.setattr(
        cli,
        "_post_chat",
        lambda *_args, **_kwargs: {
            "query_type": "D_cross_domain_topic",
            "citations": [{"type": "professor", "id": "PROF-1", "title": "陈晓非"}],
            "structured_payload": {
                "retrieval_evidence": [
                    {"type": "paper", "id": "PAPER-1", "title": "Target paper"}
                ]
            },
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_retrieval_chat_acceptance.py",
            "--skip-retrieval-checks",
            "--chat-url",
            "http://127.0.0.1:18188",
            "--chat-query",
            "南方科技大学陈晓非教授的研究方向和论文情况",
            "--chat-expected-domain",
            "professor",
            "--chat-expected-domain",
            "paper",
        ],
    )

    assert cli.main() == 1
