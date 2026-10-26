"""Professor projection metrics surface: configured, missing, malformed."""

from __future__ import annotations

import json
from pathlib import Path

from tests.conftest import authorized_client

from backend.api.canonical_v2_professor_projection import METRICS_PATH_ENV

_PREFIX = "/api/canonical-v2/admin/professor-projection"


def _write(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "metrics.json"
    path.write_text(json.dumps(payload, ensure_ascii=False))
    return path


def test_returns_metrics_when_configured(tmp_path: Path, monkeypatch) -> None:
    path = _write(tmp_path, {"coherence": {"allowlist": 537}, "generated_at": "x"})
    monkeypatch.setenv(METRICS_PATH_ENV, str(path))

    response = authorized_client().get(_PREFIX)

    assert response.status_code == 200
    assert response.json()["coherence"]["allowlist"] == 537


def test_missing_file_is_404(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(METRICS_PATH_ENV, str(tmp_path / "absent.json"))

    response = authorized_client().get(_PREFIX)

    assert response.status_code == 404
    assert response.json()["detail"] == "professor_projection_metrics_missing"


def test_unconfigured_is_503(monkeypatch) -> None:
    monkeypatch.delenv(METRICS_PATH_ENV, raising=False)

    response = authorized_client().get(_PREFIX)

    assert response.status_code == 503
    assert response.json()["detail"] == "professor_projection_metrics_not_configured"


def test_malformed_file_is_500(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not json")
    monkeypatch.setenv(METRICS_PATH_ENV, str(path))

    response = authorized_client().get(_PREFIX)

    assert response.status_code == 500
    assert response.json()["detail"] == "professor_projection_metrics_unreadable"
