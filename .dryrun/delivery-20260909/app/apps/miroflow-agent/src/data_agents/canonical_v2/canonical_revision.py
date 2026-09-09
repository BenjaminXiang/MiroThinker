"""Fail-closed Canonical V2 Alembic revision capability checks."""

from __future__ import annotations

from importlib.resources import files
import warnings

from alembic.script import ScriptDirectory
from alembic.script.revision import Revision


class CanonicalRevisionError(RuntimeError):
    """The loaded Canonical V2 history cannot prove a required capability."""


def load_canonical_v2_script_directory() -> ScriptDirectory:
    """Load the repository-owned Canonical V2 history without ambient config."""
    try:
        script_location = files("canonical_v2_alembic")
        if not script_location.is_dir():
            raise CanonicalRevisionError(
                "Canonical V2 Alembic revision history package is unavailable"
            )
        return ScriptDirectory(dir=str(script_location))
    except CanonicalRevisionError:
        raise
    except Exception as exc:
        raise CanonicalRevisionError(
            "Canonical V2 Alembic revision history package could not be loaded"
        ) from exc


def _known_linear_history(scripts: ScriptDirectory) -> dict[str, Revision]:
    try:
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "error",
                message=r"^Revision .+ is present more than once$",
                category=UserWarning,
                module=r"^alembic\.script\.revision$",
            )
            revisions = tuple(scripts.walk_revisions())
    except UserWarning as exc:
        raise CanonicalRevisionError(
            "Canonical V2 revision history contains duplicate revision identifiers"
        ) from exc
    except Exception as exc:
        raise CanonicalRevisionError(
            "Canonical V2 revision history is malformed or cyclic"
        ) from exc

    if not revisions:
        raise CanonicalRevisionError("Canonical V2 revision history is empty")

    known: dict[str, Revision] = {}
    parents: dict[str, str | None] = {}
    for revision in revisions:
        revision_id = revision.revision
        if not isinstance(revision_id, str) or not revision_id:
            raise CanonicalRevisionError(
                "Canonical V2 revision history contains an invalid revision identifier"
            )
        if revision_id in known:
            raise CanonicalRevisionError(
                "Canonical V2 revision history contains duplicate revision identifiers"
            )
        if revision.dependencies:
            raise CanonicalRevisionError(
                "Canonical V2 revision history is not linear: "
                f"revision {revision_id!r} declares dependency parents"
            )

        down_revision = revision.down_revision
        if down_revision is not None and not isinstance(down_revision, str):
            raise CanonicalRevisionError(
                "Canonical V2 revision history is not single-parent linear: "
                f"merge revision {revision_id!r} has multiple parents"
            )
        known[revision_id] = revision
        parents[revision_id] = down_revision

    children: dict[str, list[str]] = {revision_id: [] for revision_id in known}
    roots: list[str] = []
    for revision_id, parent_id in parents.items():
        if parent_id is None:
            roots.append(revision_id)
            continue
        if parent_id not in known:
            raise CanonicalRevisionError(
                "Canonical V2 revision history is malformed: "
                f"revision {revision_id!r} has unknown parent {parent_id!r}"
            )
        children[parent_id].append(revision_id)

    if len(roots) != 1:
        raise CanonicalRevisionError(
            "Canonical V2 revision history is not linear: "
            f"expected one root, found {len(roots)}"
        )
    for revision_id in sorted(children):
        child_ids = children[revision_id]
        if len(child_ids) > 1:
            raise CanonicalRevisionError(
                "Canonical V2 revision history is not linear: "
                f"fork detected at revision {revision_id!r}"
            )

    root_id = roots[0]
    for revision_id in sorted(known):
        seen: set[str] = set()
        cursor: str | None = revision_id
        while cursor is not None:
            if cursor in seen:
                raise CanonicalRevisionError(
                    "Canonical V2 revision history is malformed or cyclic"
                )
            seen.add(cursor)
            cursor = parents[cursor]
        if root_id not in seen:
            raise CanonicalRevisionError(
                "Canonical V2 revision history contains disconnected lineages"
            )

    return known


def require_minimum_canonical_revision(
    *,
    scripts: ScriptDirectory,
    current_revision: str,
    minimum_revision: str,
) -> None:
    """Require ``current_revision`` to be on/after a known linear minimum."""
    known = _known_linear_history(scripts)

    if minimum_revision not in known:
        raise CanonicalRevisionError(
            "Canonical V2 minimum revision "
            f"{minimum_revision!r} is unknown in the loaded history"
        )
    if current_revision not in known:
        raise CanonicalRevisionError(
            "Canonical V2 current revision "
            f"{current_revision!r} is unknown; required minimum is "
            f"{minimum_revision!r}"
        )

    cursor: Revision | None = known[current_revision]
    while cursor is not None:
        if cursor.revision == minimum_revision:
            return
        parent_id = cursor.down_revision
        cursor = known[parent_id] if isinstance(parent_id, str) else None

    raise CanonicalRevisionError(
        "Canonical V2 current revision "
        f"{current_revision!r} is behind or not a descendant of required minimum "
        f"revision {minimum_revision!r}"
    )


__all__ = ["CanonicalRevisionError", "require_minimum_canonical_revision"]
