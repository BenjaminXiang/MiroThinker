"""Projection refresh wrapper: path resolution and command construction."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_projection_refresh.py"
_spec = importlib.util.spec_from_file_location("run_projection_refresh", _SCRIPT)
assert _spec and _spec.loader
wrapper = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = wrapper
_spec.loader.exec_module(wrapper)


def test_defaults_match_the_customer_layout() -> None:
    pack, out_dir, metrics = wrapper.resolve_paths({})

    assert str(pack) == wrapper.DEFAULT_PACK
    assert str(out_dir) == wrapper.DEFAULT_OUT_DIR
    assert str(metrics) == wrapper.DEFAULT_METRICS


def test_environment_overrides_every_path() -> None:
    pack, out_dir, metrics = wrapper.resolve_paths(
        {
            "CANONICAL_V2_SERVING_PACK": "/p",
            "CANONICAL_V2_PROFESSOR_PROJECTION_DIR": "/o",
            "CANONICAL_V2_PROFESSOR_PROJECTION_METRICS": "/m.json",
        }
    )

    assert (str(pack), str(out_dir), str(metrics)) == ("/p", "/o", "/m.json")


def test_command_carries_threshold_and_skip_flag() -> None:
    command = wrapper.build_command(
        python="/py",
        pack=Path("/p"),
        out_dir=Path("/o"),
        threshold=0.4,
        skip_coherence=True,
    )

    assert command[0] == "/py"
    assert "--threshold" in command and "0.4" in command
    assert "--skip-coherence" in command
    assert str(wrapper.REFRESH_SCRIPT) in command


def test_missing_pack_fails_before_running(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("CANONICAL_V2_SERVING_PACK", str(tmp_path / "nope"))
    monkeypatch.setenv("CANONICAL_V2_EMBEDDING_API_KEY", "k")

    assert wrapper.main([]) == 2
    assert "serving pack missing" in capsys.readouterr().err


def test_missing_key_fails_before_running(tmp_path: Path, monkeypatch) -> None:
    pack = tmp_path / "pack"
    pack.mkdir()
    monkeypatch.setenv("CANONICAL_V2_SERVING_PACK", str(pack))
    monkeypatch.delenv("CANONICAL_V2_EMBEDDING_API_KEY", raising=False)

    assert wrapper.main([]) == 2


def test_dry_run_prints_the_command(tmp_path: Path, monkeypatch, capsys) -> None:
    pack = tmp_path / "pack"
    pack.mkdir()
    monkeypatch.setenv("CANONICAL_V2_SERVING_PACK", str(pack))
    monkeypatch.setenv("CANONICAL_V2_EMBEDDING_API_KEY", "k")

    assert wrapper.main(["--dry-run"]) == 0
    assert "--threshold 0.33" in capsys.readouterr().out


def test_publish_file_is_atomic(tmp_path: Path) -> None:
    source = tmp_path / "src.json"
    source.write_text('{"a": 1}')
    target = tmp_path / "out" / "target.json"

    wrapper.publish_file(source, target)

    assert target.read_text() == '{"a": 1}'
    assert not (target.parent / "target.json.tmp").exists()


def test_allowlist_target_prefers_the_overlay_variable() -> None:
    assert str(
        wrapper.resolve_allowlist_target({"CANONICAL_V2_PROFESSOR_PROJECTION": "/x.json"})
    ) == "/x.json"
    assert str(wrapper.resolve_allowlist_target({})) == wrapper.DEFAULT_ALLOWLIST


def test_guard_rejects_a_tiny_allowlist() -> None:
    assert wrapper.allowlist_guard_reason(120, 536) == "too_small (120 < 300)"


def test_guard_rejects_a_large_shrink() -> None:
    assert wrapper.allowlist_guard_reason(400, 536) == "shrink (536 -> 400)"
    assert wrapper.allowlist_guard_reason(500, 536) is None


def test_guard_allows_growth_and_missing_current() -> None:
    assert wrapper.allowlist_guard_reason(600, 536) is None
    assert wrapper.allowlist_guard_reason(536, None) is None


def test_record_count_reads_json_and_tolerates_missing(tmp_path: Path) -> None:
    path = tmp_path / "a.json"
    path.write_text('{"a": 1, "b": 2}')
    assert wrapper._record_count(path) == 2
    assert wrapper._record_count(tmp_path / "absent.json") is None


def test_publish_keeps_the_previous_generation(tmp_path: Path) -> None:
    current = tmp_path / "allowlist.json"
    current.write_text('{"old": 1}')
    source = tmp_path / "new.json"
    source.write_text('{"new": 2}')

    if current.is_file():
        wrapper.publish_file(current, current.with_name(current.name + ".prev"))
    wrapper.publish_file(source, current)

    assert current.read_text() == '{"new": 2}'
    assert (tmp_path / "allowlist.json.prev").read_text() == '{"old": 1}'
