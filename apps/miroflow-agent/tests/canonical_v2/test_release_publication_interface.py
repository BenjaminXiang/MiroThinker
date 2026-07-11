from __future__ import annotations

from importlib import import_module
from typing import Any

import pytest


RED_REASON = "Task 3.1 RED: Canonical V2 ReleasePublication interface is not implemented"


@pytest.mark.xfail(strict=True, raises=ModuleNotFoundError, reason=RED_REASON)
def test_release_publication_verifies_exact_parity_then_promotes_and_rolls_back_one_release() -> None:
    module: Any = import_module("src.data_agents.canonical_v2.release_publication")

    class RecordingPublication(module.ReleasePublication):
        def __init__(self) -> None:
            self.active_release_id = "release-r0"
            self.accepted: set[str] = set()

        def verify(self, candidate_release_id: str) -> Any:
            verification = module.ReleaseVerification(
                candidate_release_id=candidate_release_id,
                accepted=True,
                canonical_index_parity=True,
                missing_points=0,
                extra_points=0,
                stale_points=0,
                cross_release_points=0,
                evidence_ids=("verification-e1",),
            )
            self.accepted.add(candidate_release_id)
            return verification

        def promote(self, accepted_release_id: str) -> Any:
            if accepted_release_id not in self.accepted:
                raise ValueError("release is not accepted")
            previous = self.active_release_id
            self.active_release_id = accepted_release_id
            return module.PublishedRelease(
                release_id=accepted_release_id,
                previous_release_id=previous,
                canonical_release_id=accepted_release_id,
                published_projection_release_id=accepted_release_id,
                index_release_id=accepted_release_id,
                state="active",
            )

        def rollback(self, published_release_id: str) -> Any:
            assert published_release_id == self.active_release_id
            previous = "release-r0"
            self.active_release_id = previous
            return module.PublishedRelease(
                release_id=previous,
                previous_release_id=published_release_id,
                canonical_release_id=previous,
                published_projection_release_id=previous,
                index_release_id=previous,
                state="active",
            )

    publication = RecordingPublication()
    with pytest.raises(ValueError, match="not accepted"):
        publication.promote("candidate-r1")

    verification = publication.verify("candidate-r1")
    promoted = publication.promote("candidate-r1")
    rolled_back = publication.rollback(promoted.release_id)

    assert isinstance(verification, module.ReleaseVerification)
    assert verification.accepted is True
    assert verification.canonical_index_parity is True
    assert (
        verification.missing_points,
        verification.extra_points,
        verification.stale_points,
        verification.cross_release_points,
    ) == (0, 0, 0, 0)
    assert promoted.previous_release_id == "release-r0"
    assert {
        promoted.canonical_release_id,
        promoted.published_projection_release_id,
        promoted.index_release_id,
    } == {promoted.release_id}
    assert rolled_back.release_id == "release-r0"
    assert rolled_back.previous_release_id == "candidate-r1"
    assert publication.active_release_id == "release-r0"
