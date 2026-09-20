"""The console's single reader of the collection database DSN.

A leaf module on purpose. This function is needed by the app shell and by three
routers, and it used to live in ``backend/deps.py`` — whose module level imports the
pre-canonical retrieval stack (``RetrievalService``, the provider clients, the
professor vectorizer and, through it, ``pymilvus``). Every process that imported the
console therefore paid for ~60 legacy modules, the serving process included.

Keep this module free of project imports: that is the whole point of it existing
separately. Anything with a project import belongs in ``backend/deps.py``.
"""

from __future__ import annotations

from collections.abc import Mapping
import os


def resolve_console_dsn(environ: Mapping[str, str] | None = None) -> str | None:
    """Return the console/collection database DSN, or ``None`` when unconfigured.

    The single reader of `DATABASE_URL` (then `DATABASE_URL_TEST`, which lets
    pytest isolate from real data) for the console process. A blank or
    whitespace-only value counts as unset. `CANONICAL_V2_DATABASE_URL` is a
    different database — the serving target of the V2 operations surface — and
    is deliberately not accepted here.
    """

    values = os.environ if environ is None else environ
    for name in ("DATABASE_URL", "DATABASE_URL_TEST"):
        value = (values.get(name) or "").strip()
        if value:
            return value
    return None


__all__ = ["resolve_console_dsn"]
