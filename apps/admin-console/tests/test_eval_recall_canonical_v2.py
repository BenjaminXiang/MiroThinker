"""Recall-regression harness tests (embedding-model-switch gate).

Hermetic: SSE parsing, entity scoring, aggregation and every `--diff` verdict
class are exercised on constructed records — no network, no live instance.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from scripts import eval_recall_canonical_v2 as harness


def _record(
    case_id: str,
    *,
    suite: str = "testset",
    kind: str = "labeled",
    entities: dict | None = None,
    vector: int | None = 128,
    candidate_layer: bool = True,
    citations_local: int = 1,
    citations_web: int = 0,
) -> dict:
    entities = entities or {}
    lanes = {} if vector is None else {"vector": {"candidates": vector, "status": "ok"}}
    return {
        "case_id": case_id,
        "suite": suite,
        "group": case_id,
        "turn": 1,
        "kind": kind,
        "query": f"query-{case_id}",
        "session_id": f"session:chat:{case_id}",
        "status": "ok",
        "error": None,
        "seconds": 1.0,
        "sse_events": {},
        "answer": {
            "answer_style": "llm_synthesized",
            "text": "answer",
            "citations": [],
            "citation_nature": {"local": citations_local, "web": citations_web},
        },
        "lanes": lanes,
        "lanes_trace": {},
        "web": {
            "items": 0,
            "attempted": 0,
            "cache_hit": 0,
            "errored": 0,
            "timed_out": 0,
            "degradation": "none",
        },
        "candidate_layer": {
            "available": candidate_layer,
            "source": "turn-debug" if candidate_layer else None,
        },
        "hits": {
            "entities": entities,
            "forbidden_present": [],
            "answer_all_entities": bool(entities)
            and all(e["answer_or_citations"] for e in entities.values()),
            "candidate_all_entities": (
                None
                if not candidate_layer
                else (bool(entities) and all(e["candidate"] for e in entities.values()))
            ),
        },
        "note": "",
    }


def _entity(answer: bool, candidate: bool | None) -> dict:
    return {
        "label": "label",
        "answer": answer,
        "citations": answer,
        "answer_or_citations": answer,
        "candidate": candidate,
    }


def _payload(records: list[dict], *, label: str = "run") -> dict:
    return {
        "schema_version": harness.SCHEMA_VERSION,
        "label": label,
        "base_url": "http://127.0.0.1:18295",
        "cases_source": ["cases.json"],
        "candidate_layer_sources": {"turn_debug_dir": "/tmp", "turn_trace_dir": "/tmp"},
        "aggregate": harness._aggregate(records, 1.0),
        "cases": records,
    }


def _write(tmp_path: Path, name: str, payload: dict) -> Path:
    path = tmp_path / name
    path.write_text(harness.json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _diff(tmp_path: Path, before: dict, after: dict, *, lenient: bool = False) -> int:
    return harness._diff(
        argparse.Namespace(
            diff=[
                str(_write(tmp_path, "a.json", before)),
                str(_write(tmp_path, "b.json", after)),
            ],
            lenient_concepts=lenient,
        )
    )


# --- parsing / scoring -----------------------------------------------------

def test_parse_sse_returns_named_events_in_order() -> None:
    raw = (
        "event: stage\ndata: {\"name\":\"retrieval\"}\n\n"
        "event: retrieval_done\ndata: {\"lanes\":[{\"lane\":\"vector\",\"status\":\"ok\",\"candidates\":64}],\"web_items\":[]}\n\n"
        "event: answer\ndata: {\"answer_text\":\"你好\",\"citations\":[]}\n\n"
        "event: done\ndata: {}\n\n"
    )
    events = harness._parse_sse(raw)
    assert [name for name, _ in events] == ["stage", "retrieval_done", "answer", "done"]
    assert events[1][1]["lanes"][0]["candidates"] == 64


def test_score_turn_matches_aliases_and_reports_forbidden() -> None:
    case = {
        "case_id": "c",
        "expected_entities": [
            {"id": "pudu", "label": "普渡科技", "match": ["普渡", "Pudu"]},
            {"id": "jlc", "label": "嘉立创", "match": ["嘉立创"]},
        ],
        "forbidden_entities": [{"id": "bad", "label": "深圳智航无人机", "match": ["智航无人机"]}],
    }
    hits = harness._score_turn(
        case,
        answer_text="普渡 是送餐机器人厂商",
        citation_blobs=["嘉立创"],
        candidate_blobs=["深圳市普渡科技股份有限公司"],
    )
    assert hits["entities"]["pudu"]["answer_or_citations"] is True
    assert hits["entities"]["pudu"]["candidate"] is True
    assert hits["entities"]["jlc"]["answer"] is False
    assert hits["entities"]["jlc"]["citations"] is True
    assert hits["entities"]["jlc"]["candidate"] is False
    assert hits["answer_all_entities"] is True
    assert hits["candidate_all_entities"] is False

    forbidden = harness._score_turn(
        case,
        answer_text="这里说的是深圳智航无人机有限公司",
        citation_blobs=[],
        candidate_blobs=None,
    )
    assert forbidden["forbidden_present"] == ["bad"]
    assert forbidden["entities"]["pudu"]["candidate"] is None


def test_normalize_ignores_case_and_whitespace() -> None:
    entity = {"id": "x", "label": "pFedGPA", "match": ["pFedGPA"]}
    assert harness._entity_hit(entity, ["标题 pfedgpa：论文"]) is True
    assert harness._entity_hit(entity, ["pFed GPA 论文"]) is True
    assert harness._entity_hit(entity, ["无关"]) is False


def test_candidate_names_reads_handles_committed_slots_and_web_items() -> None:
    debug = {
        "recalled_handles": [
            {"kind": "canonical", "display_name": "深圳市普渡科技股份有限公司"},
            {"kind": "web", "display_name": "web 页面标题"},
        ],
        "committed_names": ["云迹科技"],
        "protected_slots": [{"value": "CN117873146A"}],
    }
    names = harness._candidate_names(debug, [{"title": "网页", "url": "https://example.com"}])
    assert "深圳市普渡科技股份有限公司" in names
    assert "云迹科技" in names
    assert "CN117873146A" in names
    assert "https://example.com" in names


def test_order_cases_keeps_group_order_and_turn_order() -> None:
    cases = [
        {"case_id": "b2", "group": "g2", "turn": 2},
        {"case_id": "a1", "group": "g1", "turn": 1},
        {"case_id": "b1", "group": "g2", "turn": 1},
    ]
    ordered = harness._order_cases(cases)
    assert [case["case_id"] for case in ordered] == ["b1", "b2", "a1"]


def test_group_slugs_share_one_session_per_turn_group() -> None:
    cases = [
        {"case_id": "q1t1", "group": "问题1", "turn": 1},
        {"case_id": "q1t2", "group": "问题1", "turn": 2},
        {"case_id": "q2t1", "group": "问题2", "turn": 1},
        {"case_id": "s01", "group": "s01", "turn": 1},
    ]
    slugs = harness._group_slugs(cases)
    sessions = {group: harness._session_id("866c", slug) for group, slug in slugs.items()}
    assert sessions["问题1"] == sessions["问题1"]
    assert len({harness._session_suffix(session) for session in sessions.values()}) == 3
    assert sessions["问题1"] == "session:chat:866c-q1t1"
    # the serving process names the debug dump after the last 12 characters
    assert all(
        len(harness._session_suffix(session)) <= 12 for session in sessions.values()
    )


def test_session_id_rejects_a_run_id_that_breaks_the_debug_file_name() -> None:
    try:
        harness._session_id("866c-too-long", "q1t1")
    except SystemExit as exc:
        assert "too long" in str(exc)
    else:  # pragma: no cover - the guard must fire
        raise AssertionError("expected SystemExit for an over-long run id")


# --- aggregates ------------------------------------------------------------

def test_aggregate_reports_vector_median_and_citation_mix() -> None:
    records = [
        _record("a", entities={"e1": _entity(True, True)}, vector=128, citations_web=2),
        _record("b", entities={"e1": _entity(False, True)}, vector=64),
        _record("c", entities={}, vector=None),
    ]
    aggregate = harness._aggregate(records, 12.5)
    assert aggregate["cases"] == 3
    assert aggregate["vector_candidates"] == {"n": 2, "median": 96.0, "min": 64, "max": 128}
    assert aggregate["entities_hit_in_answer_or_citations"] == 1
    assert aggregate["entities_hit_in_candidate_layer"] == 2
    assert aggregate["citation_nature_totals"] == {"local": 3, "web": 2}
    assert aggregate["turns_with_llm_synthesis"] == 3
    assert aggregate["cases_with_candidate_layer"] == 3


# --- diff verdicts ---------------------------------------------------------

def test_diff_passes_on_identical_runs(tmp_path: Path, capsys: object) -> None:
    payload = _payload([_record("q1", entities={"e1": _entity(True, True)})])
    assert _diff(tmp_path, payload, payload) == 0
    assert "VERDICT: PASS" in capsys.readouterr().out


def test_diff_flags_labeled_answer_regression_as_fail(tmp_path: Path, capsys: object) -> None:
    before = _payload([_record("q1", entities={"e1": _entity(True, True)})])
    after = _payload([_record("q1", entities={"e1": _entity(False, True)})])
    assert _diff(tmp_path, before, after) == 1
    out = capsys.readouterr().out
    assert "VERDICT: FAIL" in out
    assert "rule1(labeled) q1" in out


def test_diff_flags_labeled_candidate_regression_as_fail(tmp_path: Path) -> None:
    before = _payload([_record("q1", entities={"e1": _entity(True, True)})])
    after = _payload([_record("q1", entities={"e1": _entity(True, False)})])
    assert _diff(tmp_path, before, after) == 1


def test_diff_median_vector_drop_over_thirty_percent_is_fail(tmp_path: Path, capsys: object) -> None:
    before = _payload([_record(f"q{i}", entities={}, vector=128) for i in range(4)])
    after = _payload([_record(f"q{i}", entities={}, vector=80) for i in range(4)])
    assert _diff(tmp_path, before, after) == 1
    assert "rule3" in capsys.readouterr().out


def test_diff_probe_gt_loss_is_review_not_fail(tmp_path: Path, capsys: object) -> None:
    before = _payload(
        [_record("s1", suite="probes", kind="labeled", entities={"e1": _entity(True, True)})]
    )
    after = _payload(
        [_record("s1", suite="probes", kind="labeled", entities={"e1": _entity(True, False)})]
    )
    assert _diff(tmp_path, before, after) == 2
    assert "rule2(probe" in capsys.readouterr().out


def test_diff_probe_vector_drop_over_fifty_percent_is_review(tmp_path: Path) -> None:
    before = _payload(
        [_record(f"q{i}", entities={}, vector=128) for i in range(4)]
        + [_record("s1", suite="probes", kind="structural", entities={}, vector=128)]
    )
    after = _payload(
        [_record(f"q{i}", entities={}, vector=128) for i in range(4)]
        + [_record("s1", suite="probes", kind="structural", entities={}, vector=60)]
    )
    assert _diff(tmp_path, before, after) == 2


def test_diff_missing_candidate_layer_is_review(tmp_path: Path, capsys: object) -> None:
    before = _payload([_record("q1", entities={"e1": _entity(True, True)})])
    after = _payload(
        [_record("q1", entities={"e1": _entity(True, None)}, candidate_layer=False)]
    )
    assert _diff(tmp_path, before, after) == 2
    assert "candidate layer unavailable" in capsys.readouterr().out


def test_diff_concept_regression_is_fail_unless_lenient(tmp_path: Path) -> None:
    before = _payload(
        [_record("q11", kind="concept", entities={"c1": _entity(True, None)})]
    )
    after = _payload(
        [_record("q11", kind="concept", entities={"c1": _entity(False, None)})]
    )
    assert _diff(tmp_path, before, after) == 1
    assert _diff(tmp_path, before, after, lenient=True) == 2


def test_diff_unlabeled_case_regression_does_not_fail(tmp_path: Path, capsys: object) -> None:
    before = _payload([_record("q3", kind="unlabeled", entities={})])
    after = _payload([_record("q3", kind="unlabeled", entities={})])
    assert _diff(tmp_path, before, after) == 0
    assert "VERDICT: PASS" in capsys.readouterr().out


def test_diff_reports_case_set_mismatch_as_review(tmp_path: Path, capsys: object) -> None:
    before = _payload([_record("q1", entities={}), _record("q2", entities={})])
    after = _payload([_record("q1", entities={})])
    assert _diff(tmp_path, before, after) == 2
    assert "present in A only" in capsys.readouterr().out


# --- case files ------------------------------------------------------------

def test_committed_case_sets_are_wellformed() -> None:
    root = Path(__file__).resolve().parents[3] / ".agents" / "runs" / "embedding-model-switch"
    testset = harness.json.loads((root / "testset-cases.json").read_text(encoding="utf-8"))
    probes = harness.json.loads((root / "semantic-probes.json").read_text(encoding="utf-8"))

    testset_cases = testset["cases"]
    assert len(testset_cases) == 25
    assert len({case["group"] for case in testset_cases}) == 17
    assert sum(1 for case in testset_cases if case["kind"] == "labeled") >= 10
    assert sum(1 for case in testset_cases if case["kind"] == "unlabeled") >= 1

    probe_cases = probes["cases"]
    assert 10 <= len(probe_cases) <= 15
    assert probes["suite"] == "probes"
    for case in probe_cases:
        assert case["kind"] in {"labeled", "structural"}
        if case["kind"] == "labeled":
            assert case["expected_entities"]
        else:
            assert case["expected_entities"] == []

    ids = [case["case_id"] for case in testset_cases + probe_cases]
    assert len(ids) == len(set(ids))
