"""RED-phase tests for M0.2 load_local_api_key helper.

Source of truth: docs/plans/2026-04-20-004-m0.1-reranker-client.md Unit 1.
Requirements: R6 (env priority, file fallback, empty-string never-raise).
"""
from __future__ import annotations

from src.data_agents.providers.local_api_key import load_local_api_key


def test_api_key_env_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("API_KEY", "abc")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("SGLANG_API_KEY", raising=False)
    assert load_local_api_key(repo_root=tmp_path) == "abc"


def test_file_fallback_when_no_env(monkeypatch, tmp_path):
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("SGLANG_API_KEY", raising=False)
    (tmp_path / ".sglang_api_key").write_text("xyz\n", encoding="utf-8")
    assert load_local_api_key(repo_root=tmp_path) == "xyz"


def test_empty_env_skips_to_next_priority(monkeypatch, tmp_path):
    monkeypatch.setenv("API_KEY", "   ")
    monkeypatch.setenv("OPENAI_API_KEY", "real")
    monkeypatch.delenv("SGLANG_API_KEY", raising=False)
    assert load_local_api_key(repo_root=tmp_path) == "real"


def test_no_env_no_file_returns_empty(monkeypatch, tmp_path):
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("SGLANG_API_KEY", raising=False)
    assert load_local_api_key(repo_root=tmp_path) == ""


def test_env_priority_order_api_key_first(monkeypatch, tmp_path):
    monkeypatch.setenv("API_KEY", "key-a")
    monkeypatch.setenv("OPENAI_API_KEY", "key-o")
    monkeypatch.setenv("SGLANG_API_KEY", "key-s")
    assert load_local_api_key(repo_root=tmp_path) == "key-a"
