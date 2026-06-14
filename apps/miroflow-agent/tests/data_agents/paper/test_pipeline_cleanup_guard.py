from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]

FORBIDDEN_DISCOVERY_SYMBOLS = {
    "_discover_best_hybrid_result",
    "discover_professor_paper_candidates",
    "discover_professor_paper_candidates_from_crossref",
    "discover_professor_paper_candidates_from_cv_pdf",
    "discover_professor_paper_candidates_from_google_scholar_profile",
    "discover_professor_paper_candidates_from_hybrid_sources",
    "discover_professor_paper_candidates_from_openalex",
    "discover_professor_paper_candidates_from_orcid",
    "run_paper_pipeline",
}

ALLOWED_COMPATIBILITY_MODULES = {
    Path("src/data_agents/paper/crossref.py"),
    Path("src/data_agents/paper/cv_pdf.py"),
    Path("src/data_agents/paper/google_scholar_profile.py"),
    Path("src/data_agents/paper/hybrid.py"),
    Path("src/data_agents/paper/openalex.py"),
    Path("src/data_agents/paper/orcid.py"),
    Path("src/data_agents/paper/pipeline.py"),
    Path("src/data_agents/paper/semantic_scholar.py"),
}


def _production_python_files(root: Path) -> list[Path]:
    source_roots = [root / "src" / "data_agents", root / "scripts"]
    files: list[Path] = []
    for source_root in source_roots:
        if not source_root.exists():
            continue
        files.extend(path for path in source_root.rglob("*.py") if path.is_file())
    return sorted(files)


def _symbol_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _forbidden_discovery_references(root: Path) -> list[str]:
    violations: list[str] = []
    for path in _production_python_files(root):
        relative = path.relative_to(root)
        if relative in ALLOWED_COMPATIBILITY_MODULES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name in FORBIDDEN_DISCOVERY_SYMBOLS:
                        violations.append(f"{relative}:{node.lineno}: import {alias.name}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imported_name = alias.name.rsplit(".", maxsplit=1)[-1]
                    if imported_name in FORBIDDEN_DISCOVERY_SYMBOLS:
                        violations.append(
                            f"{relative}:{node.lineno}: import {alias.name}"
                        )
            elif isinstance(node, ast.Call):
                symbol = _symbol_name(node.func)
                if symbol in FORBIDDEN_DISCOVERY_SYMBOLS:
                    violations.append(f"{relative}:{node.lineno}: call {symbol}")
    return violations


def test_guard_detects_injected_forbidden_discovery_import(tmp_path: Path) -> None:
    module = tmp_path / "src" / "data_agents" / "example.py"
    module.parent.mkdir(parents=True)
    module.write_text(
        "from src.data_agents.paper.hybrid import "
        "discover_professor_paper_candidates_from_hybrid_sources\n",
        encoding="utf-8",
    )

    violations = _forbidden_discovery_references(tmp_path)

    assert violations == [
        "src/data_agents/example.py:1: import "
        "discover_professor_paper_candidates_from_hybrid_sources"
    ]


def test_production_source_has_no_retired_paper_discovery_callers() -> None:
    violations = _forbidden_discovery_references(REPO_ROOT)

    assert violations == []
