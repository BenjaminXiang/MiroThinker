from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest

from backend import main as backend_main


def _set_mtime(path: Path, mtime: float) -> None:
    os.utime(path, (mtime, mtime))


@pytest.fixture
def fake_frontend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    frontend = tmp_path / "frontend"
    (frontend / "src").mkdir(parents=True)
    (frontend / "dist").mkdir()
    monkeypatch.setattr(backend_main, "_FRONTEND_DIST", frontend / "dist")
    return frontend


def test_freshness_silent_when_dist_fresh(
    fake_frontend: Path, caplog: pytest.LogCaptureFixture
) -> None:
    dist_index = fake_frontend / "dist" / "index.html"
    dist_index.write_text("<html></html>")
    src_file = fake_frontend / "src" / "App.tsx"
    src_file.write_text("export {}")
    now = 1_700_000_000.0
    _set_mtime(src_file, now)
    _set_mtime(dist_index, now + 60)

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="backend.main"):
        backend_main._check_frontend_dist_freshness()
    assert "ADMIN_CONSOLE_FRONTEND" not in caplog.text


def test_freshness_warns_when_src_newer_than_dist(
    fake_frontend: Path, caplog: pytest.LogCaptureFixture
) -> None:
    dist_index = fake_frontend / "dist" / "index.html"
    dist_index.write_text("<html></html>")
    src_dir = fake_frontend / "src" / "pages"
    src_dir.mkdir(parents=True)
    src_file = src_dir / "Chat.tsx"
    src_file.write_text("export {}")
    now = 1_700_000_000.0
    _set_mtime(dist_index, now)
    _set_mtime(src_file, now + 3600)

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="backend.main"):
        backend_main._check_frontend_dist_freshness()
    assert "ADMIN_CONSOLE_FRONTEND_STALE" in caplog.text
    assert "Chat.tsx" in caplog.text
    assert "just frontend-fresh" in caplog.text


def test_freshness_warns_when_dist_missing(
    fake_frontend: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="backend.main"):
        backend_main._check_frontend_dist_freshness()
    assert "ADMIN_CONSOLE_FRONTEND_MISSING" in caplog.text
    assert "just frontend-fresh" in caplog.text


def test_freshness_within_grace_period_silent(
    fake_frontend: Path, caplog: pytest.LogCaptureFixture
) -> None:
    dist_index = fake_frontend / "dist" / "index.html"
    dist_index.write_text("<html></html>")
    src_file = fake_frontend / "src" / "App.tsx"
    src_file.write_text("export {}")
    now = 1_700_000_000.0
    _set_mtime(dist_index, now)
    _set_mtime(src_file, now + 2.0)

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="backend.main"):
        backend_main._check_frontend_dist_freshness()
    assert "ADMIN_CONSOLE_FRONTEND" not in caplog.text
