from __future__ import annotations

from pathlib import Path

from src.data_agents.professor import llm_profiles


def test_candidate_key_roots_walk_ancestors_above_the_checkout(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fake_module = (
        tmp_path
        / "main-checkout"
        / ".worktrees"
        / "wt"
        / "apps"
        / "miroflow-agent"
        / "src"
        / "data_agents"
        / "professor"
        / "llm_profiles.py"
    )
    fake_module.parent.mkdir(parents=True)
    fake_module.write_text("", encoding="utf-8")
    key_path = tmp_path / "main-checkout" / ".sglang_api_key"
    key_path.write_text("ancestor-key\n", encoding="utf-8")
    monkeypatch.setattr(llm_profiles, "__file__", str(fake_module))

    roots = llm_profiles._candidate_key_roots()

    assert roots[0] == fake_module.parents[5]
    assert roots[1] == fake_module.parents[3]
    assert tmp_path / "main-checkout" in roots
    assert llm_profiles._read_key_file(".sglang_api_key") == "ancestor-key"


def test_candidate_key_roots_preserve_repo_then_app_precedence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fake_module = (
        tmp_path
        / "repo"
        / "apps"
        / "miroflow-agent"
        / "src"
        / "data_agents"
        / "professor"
        / "llm_profiles.py"
    )
    fake_module.parent.mkdir(parents=True)
    fake_module.write_text("", encoding="utf-8")
    (tmp_path / "repo" / ".sglang_api_key").write_text("repo-key\n", encoding="utf-8")
    (tmp_path / "repo" / "apps" / "miroflow-agent" / ".sglang_api_key").write_text(
        "app-key\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(llm_profiles, "__file__", str(fake_module))

    roots = llm_profiles._candidate_key_roots()

    assert roots[0] == tmp_path / "repo"
    assert roots[1] == tmp_path / "repo" / "apps" / "miroflow-agent"
    assert llm_profiles._read_key_file(".sglang_api_key") == "repo-key"
