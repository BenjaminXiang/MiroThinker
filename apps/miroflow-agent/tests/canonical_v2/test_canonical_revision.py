from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Any

from alembic.config import Config
from alembic.script import ScriptDirectory
import pytest


APP_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = APP_ROOT / "canonical_v2_alembic.ini"
SCRIPT_LOCATION = APP_ROOT / "canonical_v2_alembic"
TARGET_MODULE = "src.data_agents.canonical_v2.canonical_revision"
MINIMUM_REVISION = "C2_0004"


def _module() -> Any:
    try:
        return import_module(TARGET_MODULE)
    except ModuleNotFoundError as exc:
        if exc.name != TARGET_MODULE:
            raise AssertionError(
                f"{TARGET_MODULE} has an unexpected missing dependency: {exc.name}"
            ) from exc
        raise


def _canonical_scripts() -> ScriptDirectory:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(SCRIPT_LOCATION))
    return ScriptDirectory.from_config(config)


def _write_revision(
    versions: Path,
    revision: str,
    down_revision: str | tuple[str, ...] | None,
    *,
    filename: str | None = None,
) -> None:
    (versions / (filename or f"{revision}.py")).write_text(
        "\n".join(
            (
                f'revision = "{revision}"',
                f"down_revision = {down_revision!r}",
                "branch_labels = None",
                "depends_on = None",
                "",
            )
        ),
        encoding="utf-8",
    )


def _synthetic_scripts(
    tmp_path: Path,
    revisions: tuple[tuple[str, str | tuple[str, ...] | None], ...],
) -> ScriptDirectory:
    script_location = tmp_path / "alembic"
    versions = script_location / "versions"
    versions.mkdir(parents=True)
    for revision, down_revision in revisions:
        _write_revision(versions, revision, down_revision)
    config = Config()
    config.set_main_option("script_location", str(script_location))
    return ScriptDirectory.from_config(config)


def test_minimum_revision_accepts_exact_and_known_linear_descendant(
    tmp_path: Path,
) -> None:
    module = _module()

    assert (
        module.require_minimum_canonical_revision(
            scripts=_canonical_scripts(),
            current_revision=MINIMUM_REVISION,
            minimum_revision=MINIMUM_REVISION,
        )
        is None
    )
    synthetic = _synthetic_scripts(
        tmp_path,
        (
            ("C2_0003", None),
            ("C2_0004", "C2_0003"),
            ("C2_0005", "C2_0004"),
        ),
    )
    assert (
        module.require_minimum_canonical_revision(
            scripts=synthetic,
            current_revision="C2_0005",
            minimum_revision=MINIMUM_REVISION,
        )
        is None
    )


@pytest.mark.parametrize("current_revision", ("C2_0003", "C2_DOES_NOT_EXIST"))
def test_minimum_revision_rejects_behind_or_unknown_current_revision(
    current_revision: str,
) -> None:
    module = _module()

    with pytest.raises(
        module.CanonicalRevisionError,
        match="minimum|behind|unknown|revision",
    ):
        module.require_minimum_canonical_revision(
            scripts=_canonical_scripts(),
            current_revision=current_revision,
            minimum_revision=MINIMUM_REVISION,
        )


def test_minimum_revision_rejects_an_unknown_minimum_revision() -> None:
    module = _module()

    with pytest.raises(module.CanonicalRevisionError, match="unknown|revision"):
        module.require_minimum_canonical_revision(
            scripts=_canonical_scripts(),
            current_revision=MINIMUM_REVISION,
            minimum_revision="C2_DOES_NOT_EXIST",
        )


def test_minimum_revision_rejects_duplicate_revision_files(tmp_path: Path) -> None:
    module = _module()
    script_location = tmp_path / "alembic"
    versions = script_location / "versions"
    versions.mkdir(parents=True)
    _write_revision(
        versions,
        "duplicate",
        None,
        filename="first_duplicate.py",
    )
    _write_revision(
        versions,
        "duplicate",
        None,
        filename="second_duplicate.py",
    )
    config = Config()
    config.set_main_option("script_location", str(script_location))
    scripts = ScriptDirectory.from_config(config)

    with pytest.raises(module.CanonicalRevisionError, match="duplicate|revision"):
        module.require_minimum_canonical_revision(
            scripts=scripts,
            current_revision="duplicate",
            minimum_revision="duplicate",
        )


def test_minimum_revision_rejects_a_synthetic_fork(tmp_path: Path) -> None:
    module = _module()
    scripts = _synthetic_scripts(
        tmp_path,
        (
            ("root", None),
            ("minimum", "root"),
            ("sibling", "root"),
        ),
    )

    with pytest.raises(
        module.CanonicalRevisionError,
        match="linear|fork|descendant|minimum",
    ):
        module.require_minimum_canonical_revision(
            scripts=scripts,
            current_revision="sibling",
            minimum_revision="minimum",
        )


def test_minimum_revision_rejects_a_synthetic_multi_parent_graph(
    tmp_path: Path,
) -> None:
    module = _module()
    scripts = _synthetic_scripts(
        tmp_path,
        (
            ("root", None),
            ("left", "root"),
            ("right", "root"),
            ("merge", ("left", "right")),
        ),
    )

    with pytest.raises(
        module.CanonicalRevisionError,
        match="linear|merge|multiple|parent",
    ):
        module.require_minimum_canonical_revision(
            scripts=scripts,
            current_revision="merge",
            minimum_revision="root",
        )
