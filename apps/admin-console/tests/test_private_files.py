"""The private-file chmod helper must survive the CPython no-follow gap.

Regression: on CPython 3.12.13+ (the customer-site venv runs 3.12.14)
``os.chmod(..., follow_symlinks=False)`` raises ``NotImplementedError`` on Linux
instead of ignoring the flag, which used to disable the credential store and
the three SQLite sidecars at boot.
"""

from __future__ import annotations

import os

from backend.private_files import chmod_owner_only


def test_falls_back_when_platform_rejects_the_no_follow_flag(tmp_path, monkeypatch):
    target = tmp_path / "private.sqlite3"
    target.write_text("x", encoding="utf-8")
    calls: list[dict] = []
    real_chmod = os.chmod

    def fake_chmod(path, mode, **kwargs):
        calls.append({"mode": mode, **kwargs})
        if kwargs.get("follow_symlinks") is False:
            raise NotImplementedError(
                "chmod: follow_symlinks unavailable on this platform"
            )
        return real_chmod(path, mode)

    monkeypatch.setattr("backend.private_files.os.chmod", fake_chmod)

    chmod_owner_only(target)

    assert [call.get("follow_symlinks") for call in calls] == [False, None]
    assert (target.stat().st_mode & 0o777) == 0o600


def test_uses_the_no_follow_form_when_supported(tmp_path, monkeypatch):
    target = tmp_path / "private.sqlite3"
    target.write_text("x", encoding="utf-8")
    seen: list[dict] = []

    def fake_chmod(path, mode, **kwargs):
        seen.append({"mode": mode, **kwargs})

    monkeypatch.setattr("backend.private_files.os.chmod", fake_chmod)

    chmod_owner_only(target)

    assert seen == [{"mode": 0o600, "follow_symlinks": False}]
