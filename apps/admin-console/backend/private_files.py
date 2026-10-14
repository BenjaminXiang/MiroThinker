"""Permissions for the console's private files.

Every caller vets its target first (regular file, not a symlink, single hard
link) and then wants mode 0600. ``os.chmod(..., follow_symlinks=False)`` is the
strict form, but CPython 3.12.13+ *raises* ``NotImplementedError`` on platforms
whose chmod cannot honour the flag (Linux without ``fchmodat2``) where older
patch releases silently ignored it. That turned a hardening call into a boot
failure for the credential store and the three SQLite sidecars (first seen on
the customer site, Python 3.12.14). The fallback is the same chmod minus the
flag; the vetting above already pins the target.
"""

from __future__ import annotations

import os

__all__ = ["chmod_owner_only"]


def chmod_owner_only(path: os.PathLike[str] | str, mode: int = 0o600) -> None:
    """Chmod one already-vetted private path, tolerating the no-follow gap."""

    try:
        os.chmod(path, mode, follow_symlinks=False)
    except NotImplementedError:
        os.chmod(path, mode)
