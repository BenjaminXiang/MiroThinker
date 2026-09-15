"""Evidence-only pytest plugin: run the pinned-revision PG suites at head.

`tests/canonical_v2/test_canonical_decision_postgres.py` pins
`EXPECTED_REVISION = "C2_0008"`, so its reviewed-field fixtures never exercise
the C2_0014 guard. This plugin (loaded with `-p`, kept outside the test tree so
the repo's own suites are untouched) rewrites that pin to the migration head at
collection time, which is how the equivalence evidence in
`verification.md` was produced.

Usage:
    uv run pytest -p no:cacheprovider \
        -p bump_revision_plugin \
        tests/canonical_v2/test_canonical_decision_postgres.py
"""

from __future__ import annotations

import os

HEAD_REVISION = os.environ.get("EVIDENCE_HEAD_REVISION", "C2_0014")
TARGET_MODULES = (
    "test_canonical_decision_postgres",
)


def pytest_collection_modifyitems(session, config, items):  # noqa: ANN001
    import sys

    for name in TARGET_MODULES:
        module = sys.modules.get(name)
        if module is None:
            for item in items:
                if item.module.__name__.endswith(name):
                    module = item.module
                    break
        if module is not None and hasattr(module, "EXPECTED_REVISION"):
            module.EXPECTED_REVISION = HEAD_REVISION
