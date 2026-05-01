from __future__ import annotations

import requests

from src.data_agents.professor import openalex_metrics
from src.data_agents.professor.openalex_metrics import fetch_metrics


class FakeResponse:
    def __init__(self, status_code: int, payload: object | None = None) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> object:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeClient:
    def __init__(self, responses: list[object]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def get(self, url: str, *, params: dict[str, object], timeout: float) -> object:
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_fetch_metrics_happy_path_from_author_id() -> None:
    client = FakeClient(
        [
            FakeResponse(
                200,
                {
                    "id": "https://openalex.org/A123",
                    "summary_stats": {"h_index": 37},
                    "cited_by_count": 5_000_000_000,
                    "works_count": 88,
                },
            )
        ]
    )

    metrics = fetch_metrics(
        openalex_author_id="https://openalex.org/A123",
        http_client=client,
        timeout=3.0,
    )

    assert metrics.source == "openalex"
    assert metrics.h_index == 37
    assert metrics.citation_count == 5_000_000_000
    assert metrics.works_count_openalex == 88
    assert client.calls[0]["url"] == "https://api.openalex.org/authors/A123"


def test_fetch_metrics_uses_orcid_when_author_id_absent() -> None:
    client = FakeClient(
        [
            FakeResponse(
                200,
                {
                    "results": [
                        {
                            "id": "https://openalex.org/A9",
                            "summary_stats": {"h_index": 0},
                            "cited_by_count": 0,
                            "works_count": 0,
                        }
                    ]
                },
            )
        ]
    )

    metrics = fetch_metrics(
        orcid="https://orcid.org/0000-0002-1825-009X",
        http_client=client,
    )

    assert metrics.source == "openalex"
    assert metrics.h_index == 0
    assert metrics.citation_count == 0
    assert metrics.works_count_openalex == 0
    assert client.calls[0]["params"]["filter"] == "orcid:0000-0002-1825-009X"


def test_fetch_metrics_timeout_returns_unmatched(monkeypatch) -> None:
    monkeypatch.setattr(openalex_metrics.time, "sleep", lambda _: None)
    client = FakeClient(
        [
            requests.Timeout("slow"),
            requests.Timeout("still slow"),
            requests.Timeout("done"),
        ]
    )

    metrics = fetch_metrics(openalex_author_id="A1", http_client=client)

    assert metrics.source == "openalex_unmatched"
    assert metrics.h_index is None
    assert metrics.citation_count is None
    assert metrics.works_count_openalex is None
    assert len(client.calls) == 3


def test_fetch_metrics_5xx_exhausts_retries(monkeypatch) -> None:
    monkeypatch.setattr(openalex_metrics.time, "sleep", lambda _: None)
    client = FakeClient(
        [
            FakeResponse(500, {}),
            FakeResponse(502, {}),
            FakeResponse(503, {}),
        ]
    )

    metrics = fetch_metrics(openalex_author_id="A1", http_client=client)

    assert metrics.source == "openalex_unmatched"
    assert len(client.calls) == 3


def test_fetch_metrics_404_returns_unmatched_without_retry() -> None:
    client = FakeClient([FakeResponse(404, {})])

    metrics = fetch_metrics(openalex_author_id="A404", http_client=client)

    assert metrics.source == "openalex_unmatched"
    assert len(client.calls) == 1


def test_fetch_metrics_429_retries_then_succeeds(monkeypatch) -> None:
    monkeypatch.setattr(openalex_metrics.time, "sleep", lambda _: None)
    client = FakeClient(
        [
            FakeResponse(429, {}),
            FakeResponse(
                200,
                {
                    "id": "https://openalex.org/A7",
                    "summary_stats": {"h_index": 12},
                    "cited_by_count": 345,
                    "works_count": 67,
                },
            ),
        ]
    )

    metrics = fetch_metrics(openalex_author_id="A7", http_client=client)

    assert metrics.source == "openalex"
    assert metrics.h_index == 12
    assert metrics.citation_count == 345
    assert metrics.works_count_openalex == 67
    assert len(client.calls) == 2


def test_fetch_metrics_without_identifiers_does_not_call_http() -> None:
    client = FakeClient([])

    metrics = fetch_metrics(http_client=client)

    assert metrics.source == "openalex_unmatched"
    assert client.calls == []
