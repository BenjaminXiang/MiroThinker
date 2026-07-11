from __future__ import annotations

from importlib import import_module
from typing import Any

import pytest

from src.data_agents.canonical_v2.contracts import CandidateRelease as SharedCandidateRelease


RED_REASON = "Task 3.1 RED: Canonical V2 KnowledgeBuild interface is not implemented"


@pytest.mark.xfail(strict=True, raises=ModuleNotFoundError, reason=RED_REASON)
def test_knowledge_build_returns_isolated_candidate_with_versioned_manifest() -> None:
    module: Any = import_module("src.data_agents.canonical_v2.knowledge_build")
    assert module.CandidateRelease is SharedCandidateRelease
    request = module.BuildCandidateRequest(
        run_id="build-run-1",
        candidate_release_id="candidate-r1",
        source_batch_ids=("batch-1", "batch-2"),
        parser_versions={"historical_jsonl": "parser-v1"},
        policy_versions={"identity": "identity-v1", "eligibility": "eligibility-v1"},
        model_versions={"identity_judge": "recorded-fake-v1"},
    )

    class RecordingBuild(module.KnowledgeBuild):
        def build(self, value: Any) -> Any:
            assert value is request
            return module.CandidateRelease(
                release_id=value.candidate_release_id,
                run_id=value.run_id,
                state="candidate",
                source_batch_ids=value.source_batch_ids,
                parser_versions=value.parser_versions,
                policy_versions=value.policy_versions,
                model_versions=value.model_versions,
                manifest_sha256="a" * 64,
                object_counts={"professor": 2, "company": 1, "paper": 3, "patent": 1},
                relationship_count=4,
                active_release_changed=False,
            )

    candidate = RecordingBuild().build(request)

    assert isinstance(candidate, module.CandidateRelease)
    assert candidate.release_id == "candidate-r1"
    assert candidate.state == "candidate"
    assert candidate.source_batch_ids == request.source_batch_ids
    assert candidate.parser_versions == request.parser_versions
    assert candidate.policy_versions == request.policy_versions
    assert candidate.model_versions == request.model_versions
    assert candidate.manifest_sha256 == "a" * 64
    assert candidate.object_counts["paper"] == 3
    assert candidate.relationship_count == 4
    assert candidate.active_release_changed is False
