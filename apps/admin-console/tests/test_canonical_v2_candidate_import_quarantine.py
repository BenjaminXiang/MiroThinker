"""The candidate app must not be able to reach the legacy line.

This guard used to live inside
``test_canonical_v2_consumer_migration._assert_static_and_import_quarantine``, in a
test that has not run for several releases: it sits behind a factory-arity assertion
that stopped matching when the factory gained an optional keyword-only parameter, and
its own premise — a read-only candidate app — was overtaken when the console grew its
own write surfaces (``/upload``, ``/seeds``, ``/jobs``, ``/config``). The quarantine
itself is still true and still worth enforcing, so it lives on its own here, where it
actually runs.

The check runs in a subprocess with a meta-path blocker installed before the app is
imported: if building the candidate app ever pulls in a legacy module — the pre-V2
data/pipeline/review APIs, the Milvus stack, the domain writers — the blocker raises
and the subprocess fails. The subprocess also asserts the factory refuses anything
that is not the one accepted aggregate, and prints the route table it built.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

_REPO_ROOT = Path(__file__).resolve().parents[3]

_LEGACY_IMPORT_QUARANTINE = r"""
import importlib.abc
import json
import sys

forbidden = (
    "backend.api.chat",
    "backend.deps",
    "backend.api.admin_professor",
    "backend.api.batch",
    "backend.api.data",
    "backend.api.domains",
    "backend.api.pipeline",
    "backend.api.review",
    "backend.api.seeds",
    "backend.api.upload",
    "src.data_agents.canonical",
    "src.data_agents.company.canonical_import",
    "src.data_agents.company.release",
    "src.data_agents.company.vectorizer",
    "src.data_agents.professor.canonical_writer",
    "src.data_agents.professor.release",
    "src.data_agents.professor.vectorizer",
    "src.data_agents.paper.canonical_writer",
    "src.data_agents.paper.identity_status_writer",
    "src.data_agents.paper.quality_promotion",
    "src.data_agents.paper.release",
    "src.data_agents.patent.canonical_writer",
    "src.data_agents.patent.quality_promotion",
    "src.data_agents.patent.release",
    "src.data_agents.patent.vectorizer",
    "src.data_agents.service.retrieval",
    "src.data_agents.service.search_service",
    "src.data_agents.publish",
    "src.data_agents.paper.milvus_backfill",
    "src.data_agents.storage.milvus_collections",
    "src.data_agents.storage.milvus_store",
    "pymilvus",
)

class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == name or fullname.startswith(name + ".") for name in forbidden):
            raise ImportError("forbidden S11B import attempted: " + fullname)
        return None

sys.meta_path.insert(0, Blocker())
import backend.main
shell = backend.main._create_canonical_v2_route_shell()
assert not hasattr(shell.state, "canonical_v2_consumer_runtime")
try:
    backend.main.create_canonical_v2_candidate_app(runtime=object())
except (TypeError, ValueError):
    pass
else:
    raise AssertionError("candidate factory accepted a wrong runtime")
loaded = sorted(
    name for name in sys.modules
    if any(name == prefix or name.startswith(prefix + ".") for prefix in forbidden)
)
assert not loaded, loaded
print(json.dumps(sorted((method, route.path) for route in shell.routes for method in (getattr(route, "methods", None) or {"MOUNT"}))))
"""


def test_the_candidate_app_cannot_import_the_legacy_line() -> None:
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(
            (
                str(_REPO_ROOT / "apps/admin-console"),
                str(_REPO_ROOT / "apps/miroflow-agent"),
            )
        ),
    }
    completed = subprocess.run(
        [sys.executable, "-c", _LEGACY_IMPORT_QUARANTINE],
        cwd=_REPO_ROOT / "apps/admin-console",
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr

    # The subprocess prints a startup info line before its JSON; take the JSON line.
    payload = [line for line in completed.stdout.splitlines() if line.startswith("[")]
    assert payload, completed.stdout
    rows = {(method, path) for method, path in json.loads(payload[-1])}
    # Every reject method is answered by the one catch-all that refuses them, and it
    # is the only catch-all: no "/{path:path}", no "/assets" mount.
    for method in ("GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"):
        assert (method, "/api/{path:path}") in rows, method
    for forbidden in ("/{path:path}", "/assets", "/docs", "/openapi.json", "/redoc"):
        assert not any(path == forbidden for _, path in rows), (forbidden, sorted(rows))
