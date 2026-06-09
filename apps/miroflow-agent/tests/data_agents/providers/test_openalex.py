from __future__ import annotations

from src.data_agents.providers.openalex import (
    OPENALEX_RATE_LIMIT_CIRCUIT,
    openalex_rate_limit_cooldown_seconds,
    openalex_request_params,
)


def test_openalex_request_params_skips_without_api_key_by_default(monkeypatch):
    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    monkeypatch.delenv("OPENALEX_KEY", raising=False)
    monkeypatch.delenv("OPENALEX_SKIP_WITHOUT_API_KEY", raising=False)

    assert openalex_request_params({"search": "Wenbo Ding"}) is None


def test_openalex_request_params_can_allow_anonymous(monkeypatch):
    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    monkeypatch.delenv("OPENALEX_KEY", raising=False)
    monkeypatch.setenv("OPENALEX_SKIP_WITHOUT_API_KEY", "0")

    params = openalex_request_params({"search": "Wenbo Ding"})

    assert params == {"search": "Wenbo Ding"}


def test_openalex_request_params_adds_api_key_without_mutating_input(monkeypatch):
    monkeypatch.setenv("OPENALEX_API_KEY", "test key")
    base_params = {"search": "Wenbo Ding"}

    params = openalex_request_params(base_params)

    assert params == {"search": "Wenbo Ding", "api_key": "test key"}
    assert base_params == {"search": "Wenbo Ding"}


def test_openalex_rate_limit_cooldown_uses_response_headers():
    assert openalex_rate_limit_cooldown_seconds({"Retry-After": "42"}) == 42.0
    assert openalex_rate_limit_cooldown_seconds({"X-RateLimit-Reset": "120"}) == 120.0


def test_openalex_rate_limit_circuit_suppresses_after_threshold():
    OPENALEX_RATE_LIMIT_CIRCUIT.reset()
    try:
        assert OPENALEX_RATE_LIMIT_CIRCUIT.can_call() is True
        OPENALEX_RATE_LIMIT_CIRCUIT.record_rate_limit(cooldown_seconds=60.0)
        OPENALEX_RATE_LIMIT_CIRCUIT.record_rate_limit(cooldown_seconds=60.0)
        assert OPENALEX_RATE_LIMIT_CIRCUIT.can_call() is True
        OPENALEX_RATE_LIMIT_CIRCUIT.record_rate_limit(cooldown_seconds=60.0)
        assert OPENALEX_RATE_LIMIT_CIRCUIT.can_call() is False
    finally:
        OPENALEX_RATE_LIMIT_CIRCUIT.reset()
