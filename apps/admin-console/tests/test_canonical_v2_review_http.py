from __future__ import annotations

import inspect
import json
from pathlib import Path
import shutil
from typing import Any

from fastapi.testclient import TestClient
import pytest

from backend.main import (
    _create_canonical_v2_route_shell,
    create_canonical_v2_candidate_app,
    create_canonical_v2_review_app,
)
from backend.services.canonical_v2_review import ReviewWorkspace, create_review_workspace


REPO_ROOT = Path(__file__).resolve().parents[3]
REVIEW_SOURCE = (
    REPO_ROOT
    / ".agents"
    / "runs"
    / "rebuild-canonical-v2-knowledge-platform"
    / "s2c"
    / "review"
)
ARTIFACT_NAMES = (
    "human-review-packet-v1.json",
    "human-review-workload-v2.json",
    "calibration-policy-v2.json",
    "calibration-observation-bank-v2.jsonl",
    "calibration-observation-bank-v2-provenance.json",
)
S2C_CONTEXT_PATHS = tuple(
    Path(".agents/runs/rebuild-canonical-v2-knowledge-platform/s2c") / name
    for name in (
        "claim-level-corpus-v1.jsonl",
        "case-accounting-v1.jsonl",
        "source-snapshots-v1.jsonl",
        "claim-level-corpus-manifest-v1.json",
    )
)
PUBLIC_ORIGIN = "http://127.0.0.1:18189"
COOKIE_NAME = "canonical_v2_review_session"


@pytest.fixture
def review_workspace(tmp_path: Path) -> ReviewWorkspace:
    review_dir = tmp_path / "review"
    review_dir.mkdir()
    for name in ARTIFACT_NAMES:
        shutil.copyfile(REVIEW_SOURCE / name, review_dir / name)

    workload = json.loads(
        (review_dir / "human-review-workload-v2.json").read_text(encoding="utf-8")
    )
    source_root = tmp_path / "source-root"
    source_paths = {
        Path(probe["source_identity"]["path"])
        for probe in workload["calibration_probes"]
    } | set(S2C_CONTEXT_PATHS)
    for relative in source_paths:
        destination = source_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / relative, destination)

    return create_review_workspace(
        packet_path=review_dir / "human-review-packet-v1.json",
        workload_path=review_dir / "human-review-workload-v2.json",
        source_root=source_root,
        state_dir=tmp_path / "state",
        export_dir=tmp_path / "exports",
    )


def _client(
    workspace: ReviewWorkspace | object,
    *,
    public_origin: str = PUBLIC_ORIGIN,
) -> TestClient:
    app = create_canonical_v2_review_app(
        review_workspace=workspace,  # type: ignore[arg-type]
        public_origin=public_origin,
    )
    return TestClient(app, base_url=public_origin)


def _register(client: TestClient) -> dict[str, Any]:
    response = client.post(
        "/api/review/sessions",
        headers={"Origin": str(client.base_url).rstrip("/")},
        json={"display_name": "Reviewer Li", "staff_id": "R-1042"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_review_factory_is_separate_and_routes_precede_reject_all(
    review_workspace: ReviewWorkspace,
) -> None:
    assert tuple(inspect.signature(_create_canonical_v2_route_shell).parameters) == ()
    assert tuple(inspect.signature(create_canonical_v2_candidate_app).parameters) == (
        "runtime",
    )
    runtime_parameter = inspect.signature(create_canonical_v2_candidate_app).parameters[
        "runtime"
    ]
    assert runtime_parameter.kind is inspect.Parameter.KEYWORD_ONLY

    predecessor = _create_canonical_v2_route_shell()
    predecessor_paths = [route.path for route in predecessor.routes]
    assert "/review" not in predecessor_paths
    assert not any(path.startswith("/api/review") for path in predecessor_paths)

    review_app = create_canonical_v2_review_app(
        review_workspace=review_workspace,
        public_origin=PUBLIC_ORIGIN,
    )
    paths = [route.path for route in review_app.routes]
    api_paths = {
        "/api/review/sessions",
        "/api/review/workspace",
        "/api/review/drafts/{task_id}",
        "/api/review/decisions",
        "/api/review/calibration/seal",
        "/api/review/exports",
        "/api/review/exports/{export_id}",
    }
    assert api_paths.issubset(paths)
    assert "/review" in paths
    catchall = paths.index("/api/{path:path}")
    assert all(paths.index(path) < catchall for path in api_paths)
    assert not any(
        middleware.cls.__name__ == "CORSMiddleware"
        for middleware in review_app.user_middleware
    )


def test_review_page_has_external_assets_and_strict_security_headers(
    review_workspace: ReviewWorkspace,
) -> None:
    client = _client(review_workspace)
    response = client.get("/review")

    assert response.status_code == 200
    assert response.headers["content-security-policy"].startswith("default-src 'none'")
    for directive in (
        "script-src 'self'",
        "style-src 'self'",
        "connect-src 'self'",
        "base-uri 'none'",
        "form-action 'self'",
        "frame-ancestors 'none'",
        "object-src 'none'",
        "img-src 'self' data:",
    ):
        assert directive in response.headers["content-security-policy"]
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert '<link rel="stylesheet" href="/static/review.css">' in response.text
    assert '<script src="/static/review_mutation_coordinator.js" defer></script>' in (
        response.text
    )
    assert '<script src="/static/review.js" defer></script>' in response.text

    predecessor = TestClient(_create_canonical_v2_route_shell())
    assert predecessor.get("/review").status_code == 404


@pytest.mark.parametrize(
    "alias",
    [
        "/static/review.html",
        "/static/./review.html",
        "/static/assets/../review.html",
        "/static/%72eview.html",
    ],
)
def test_review_html_static_aliases_are_denied_on_every_shell(
    review_workspace: ReviewWorkspace,
    alias: str,
) -> None:
    clients = (
        _client(review_workspace),
        TestClient(_create_canonical_v2_route_shell()),
    )

    for client in clients:
        response = client.get(alias, follow_redirects=False)
        assert response.status_code == 404
        assert "Canonical V2 人工评审台" not in response.text


def test_session_token_is_cookie_only_and_workspace_resumes(
    review_workspace: ReviewWorkspace,
) -> None:
    client = _client(review_workspace)
    opened = _register(client)
    set_cookie = client.post(
        "/api/review/sessions",
        headers={"Origin": PUBLIC_ORIGIN},
        json={"display_name": "Reviewer Li", "staff_id": "r-1042"},
    ).headers["set-cookie"]

    assert "session_token" not in opened
    assert opened["reviewer"]["reviewer_id"] == "human:r-1042"
    assert opened["artifact_identity"]["packet_raw_sha256"] == (
        "222777219026218d9a6308c62c0238613761ef83ae90497c3a0cfa785bce7d2e"
    )
    assert opened["judge_configured"] is False
    lowered_cookie = set_cookie.lower()
    assert COOKIE_NAME in set_cookie
    assert "httponly" in lowered_cookie
    assert "samesite=strict" in lowered_cookie
    assert "path=/api/review" in lowered_cookie
    assert "domain=" not in lowered_cookie
    assert "secure" not in lowered_cookie

    resumed = client.get("/api/review/workspace")
    assert resumed.status_code == 200
    assert resumed.headers["cache-control"] == "no-store"
    assert resumed.headers["x-content-type-options"] == "nosniff"
    assert resumed.json()["round_id"] == opened["round_id"]
    assert "session_token" not in resumed.json()
    assert COOKIE_NAME not in resumed.text


def test_calibration_http_payload_exposes_only_the_bound_blind_stimulus(
    review_workspace: ReviewWorkspace,
) -> None:
    client = _client(review_workspace)
    _register(client)
    probe = json.loads(
        (REVIEW_SOURCE / "human-review-workload-v2.json").read_text(encoding="utf-8")
    )["calibration_probes"][0]

    response = client.get(
        "/api/review/workspace",
        params={"task_id": f"calibration:{probe['sample_id']}"},
    )

    assert response.status_code == 200
    payload = response.json()["task"]["payload"]
    assert set(payload) == {
        "schema_version",
        "sample_id",
        "as_of",
        "requirement",
        "candidate_observation",
        "evidence_snapshots",
    }
    assert payload["schema_version"] == "canonical-v2-human-calibration-stimulus-v1"
    serialized = json.dumps(payload, ensure_ascii=False)
    for forbidden in (
        "source_identity",
        "fixture_locator",
        "critical_probe",
        "stratum",
        "test_name",
        "selectors",
        "apps/miroflow-agent/tests",
    ):
        assert forbidden not in serialized


def test_non_loopback_http_is_rejected_and_https_cookie_is_secure(
    review_workspace: ReviewWorkspace,
) -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        create_canonical_v2_review_app(
            review_workspace=review_workspace,
            public_origin="http://review.example",
        )

    origin = "https://review.example"
    client = _client(review_workspace, public_origin=origin)
    response = client.post(
        "/api/review/sessions",
        headers={"Origin": origin},
        json={"display_name": "Reviewer Secure", "staff_id": "secure-1"},
    )
    assert response.status_code == 200
    assert "secure" in response.headers["set-cookie"].lower()


@pytest.mark.parametrize(
    "headers",
    [
        [],
        [("Origin", "null")],
        [("Origin", "http://127.0.0.1:9999")],
        [("Origin", PUBLIC_ORIGIN), ("Origin", "https://wrong.example")],
    ],
)
def test_every_invalid_origin_is_rejected_before_workspace_access(
    review_workspace: ReviewWorkspace,
    monkeypatch: pytest.MonkeyPatch,
    headers: list[tuple[str, str]],
) -> None:
    calls = 0
    original = review_workspace.open

    def observed_open(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(review_workspace, "open", observed_open)
    client = _client(review_workspace)
    response = client.post(
        "/api/review/sessions",
        headers=headers,
        json={"display_name": "Reviewer Li", "staff_id": "r-1042"},
    )

    assert response.status_code == 403
    assert response.json() == {"code": "origin_rejected"}
    assert calls == 0
    assert "access-control-allow-origin" not in response.headers


def test_wrong_workspace_is_503_but_origin_check_still_runs_first() -> None:
    client = _client(object())
    wrong_origin = client.post(
        "/api/review/sessions",
        headers={"Origin": "https://wrong.example"},
        json={"display_name": "Reviewer Li", "staff_id": "r-1042"},
    )
    assert wrong_origin.status_code == 403

    unavailable = client.post(
        "/api/review/sessions",
        headers={"Origin": PUBLIC_ORIGIN},
        json={"display_name": "Reviewer Li", "staff_id": "r-1042"},
    )
    assert unavailable.status_code == 503
    assert unavailable.json() == {"code": "review_workspace_unavailable"}


def test_strict_validation_is_sanitized_and_never_echoes_input(
    review_workspace: ReviewWorkspace,
) -> None:
    client = _client(review_workspace)
    response = client.post(
        "/api/review/sessions",
        headers={"Origin": PUBLIC_ORIGIN},
        json={
            "display_name": "Reviewer Li",
            "staff_id": "r-1042",
            "api_key": "sk-must-not-be-echoed",
        },
    )
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.json() == {"code": "invalid_request"}
    assert "sk-must-not-be-echoed" not in response.text

    evidence_class_injection = client.post(
        "/api/review/sessions",
        headers={"Origin": PUBLIC_ORIGIN},
        json={
            "display_name": "Reviewer Li",
            "staff_id": "r-1042",
            "evidence_class": "real_human_round",
        },
    )
    assert evidence_class_injection.status_code == 422
    assert evidence_class_injection.json() == {"code": "invalid_request"}
    assert "real_human_round" not in evidence_class_injection.text


def test_draft_decision_stale_and_choice_errors_map_stably(
    review_workspace: ReviewWorkspace,
) -> None:
    client = _client(review_workspace)
    opened = _register(client)
    task = opened["task"]
    assert task["kind"] == "contract"

    draft = client.put(
        f"/api/review/drafts/{task['task_id']}",
        headers={"Origin": PUBLIC_ORIGIN},
        json={"decision": "approved", "rationale": "检查中"},
    )
    assert draft.status_code == 200
    assert draft.json()["task"]["draft"] == {
        "decision": "approved",
        "rationale": "检查中",
    }

    submitted = client.post(
        "/api/review/decisions",
        headers={"Origin": PUBLIC_ORIGIN},
        json={
            "task_id": task["task_id"],
            "task_kind": "contract",
            "decision": "approved",
            "rationale": None,
            "expected_revision": 0,
            "idempotency_key": "http-decision-1",
        },
    )
    assert submitted.status_code == 200
    assert submitted.json()["progress"]["submitted"] == 1

    stale = client.post(
        "/api/review/decisions",
        headers={"Origin": PUBLIC_ORIGIN},
        json={
            "task_id": task["task_id"],
            "task_kind": "contract",
            "decision": "approved",
            "rationale": "另一个标签页",
            "expected_revision": 0,
            "idempotency_key": "http-decision-stale",
        },
    )
    assert stale.status_code == 409
    assert stale.json() == {"code": "stale_revision", "current_revision": 1}

    current_task = submitted.json()["task"]
    invalid = client.post(
        "/api/review/decisions",
        headers={"Origin": PUBLIC_ORIGIN},
        json={
            "task_id": current_task["task_id"],
            "task_kind": current_task["kind"],
            "decision": "invented_choice",
            "rationale": "bad",
            "expected_revision": current_task["revision"],
            "idempotency_key": "http-invalid-choice",
        },
    )
    assert invalid.status_code == 422
    assert invalid.json() == {"code": "invalid_decision"}


def test_seal_and_review_evidence_export_routes_are_session_bound(
    review_workspace: ReviewWorkspace,
) -> None:
    client = _client(review_workspace)
    _register(client)

    seal = client.post(
        "/api/review/calibration/seal",
        headers={"Origin": PUBLIC_ORIGIN},
        json={"expected_revision": 60, "idempotency_key": "http-seal"},
    )
    assert seal.status_code == 409
    assert seal.json() == {"code": "calibration_not_sealed"}

    export = client.post(
        "/api/review/exports",
        headers={"Origin": PUBLIC_ORIGIN},
        json={"mode": "review_evidence", "idempotency_key": "http-export-1"},
    )
    assert export.status_code == 200
    receipt = export.json()
    assert receipt["mode"] == "review_evidence"
    assert receipt["acceptance_eligible"] is False

    download = client.get(f"/api/review/exports/{receipt['export_id']}")
    assert download.status_code == 200
    assert download.headers["cache-control"] == "no-store"
    assert download.headers["x-content-type-options"] == "nosniff"
    assert download.headers["content-disposition"] == (
        f'attachment; filename="{receipt["basename"]}"'
    )


def test_missing_cookie_and_cors_preflight_fail_without_cors_headers(
    review_workspace: ReviewWorkspace,
) -> None:
    client = _client(review_workspace)
    missing = client.get("/api/review/workspace")
    assert missing.status_code == 401
    assert missing.json() == {"code": "invalid_session"}

    preflight = client.options(
        "/api/review/sessions",
        headers={
            "Origin": "https://cross-origin.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert preflight.status_code == 404
    assert "access-control-allow-origin" not in preflight.headers
