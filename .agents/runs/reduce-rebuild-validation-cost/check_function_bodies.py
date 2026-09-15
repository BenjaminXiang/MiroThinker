"""Verify the installed validator bodies equal C2_0007 (baseline) or C2_0014 (guarded).

Usage:
    uv run python check_function_bodies.py <dbname> <expected: baseline|guarded>
"""

from __future__ import annotations

import ast
import re
import sys

import psycopg

DB, EXPECTED = sys.argv[1], sys.argv[2]
PORT = sys.argv[3] if len(sys.argv) > 3 else "55458"
VERSIONS = "canonical_v2_alembic/versions"
FUNCTIONS = (
    "knowledge.validate_field_human_review_binding",
    "knowledge.validate_relationship_human_review_binding",
    "knowledge.validate_identity_human_review_binding",
)
FILES = {
    "baseline": f"{VERSIONS}/C2_0007_bind_human_review_provenance.py",
    "guarded": f"{VERSIONS}/C2_0014_guard_review_binding_scans.py",
}


def body_of(path: str, function: str) -> str:
    """Return the PL/pgSQL body text of `knowledge.<function>` from a migration."""
    tree = ast.parse(open(path).read())
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "execute"):
            continue
        arg = node.args[0]
        if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
            continue
        text = arg.value
        if f"FUNCTION {function}()" not in text:
            continue
        start = text.index("BEGIN")
        end = text.index("END;", start)
        # PostgreSQL stores the body verbatim; migration files indent the string
        # literal differently, so compare token-wise (whitespace collapsed).
        return re.sub(r"\s+", " ", text[start : end + 4]).strip()
    raise SystemExit(f"{function}: body not found in {path}")


failures = 0
with psycopg.connect(f"postgresql://miroflow@127.0.0.1:{PORT}/{DB}") as conn:
    for function in FUNCTIONS:
        installed = conn.execute(
            "SELECT prosrc FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'knowledge' AND p.proname = %s",
            (function.split(".", 1)[1],),
        ).fetchone()[0]
        start = installed.index("BEGIN")
        end = installed.index("END;", start)
        normalized = re.sub(r"\s+", " ", installed[start : end + 4]).strip()
        matches = {
            label: normalized == body_of(path, function)
            for label, path in FILES.items()
        }
        failures += 0 if matches[EXPECTED] else 1
        print(f"{function:52s} expected={EXPECTED:8s} ok={matches[EXPECTED]} all={matches}")
print("PASS" if failures == 0 else f"FAIL ({failures})")
raise SystemExit(0 if failures == 0 else 1)
