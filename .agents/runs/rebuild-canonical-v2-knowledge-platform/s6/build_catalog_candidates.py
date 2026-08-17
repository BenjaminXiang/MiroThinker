#!/usr/bin/env python3
"""Build the deterministic, preparation-only Canonical V2 PRD catalog candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "canonical-v2-prd-catalog-candidates-v1"
REQUIRED_DOMAINS = {"company", "paper", "patent", "professor"}
REQUIRED_RELATIONSHIP_FAMILIES = {
    "company_business_product_event",
    "evidence_lineage",
    "identity_lifecycle",
    "intellectual_property",
    "organization_role",
    "scholarly_output",
    "taxonomy_topic_geography",
}


class CatalogBuildError(ValueError):
    """The extraction seed or one of its cited sources is invalid."""


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CatalogBuildError(f"{path} must contain one JSON object")
    return value


def _source_path(repo_root: Path, relative_path: str) -> Path:
    candidate = (repo_root / relative_path).resolve()
    root = repo_root.resolve()
    if not candidate.is_relative_to(root):
        raise CatalogBuildError(f"citation escapes repository root: {relative_path}")
    if not candidate.is_file():
        raise CatalogBuildError(f"citation source does not exist: {relative_path}")
    return candidate


def _enrich_citation(
    *, repo_root: Path, citation_id: str, seed: dict[str, Any]
) -> dict[str, Any]:
    relative_path = seed.get("source")
    line_start = seed.get("line_start")
    line_end = seed.get("line_end")
    if not isinstance(relative_path, str) or not relative_path:
        raise CatalogBuildError(f"citation {citation_id!r} has no source")
    if (
        not isinstance(line_start, int)
        or not isinstance(line_end, int)
        or line_start <= 0
        or line_end < line_start
    ):
        raise CatalogBuildError(f"citation {citation_id!r} has an invalid line range")

    source_path = _source_path(repo_root, relative_path)
    source_bytes = source_path.read_bytes()
    try:
        source_text = source_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise CatalogBuildError(
            f"citation source is not strict UTF-8: {relative_path}"
        ) from exc
    lines = source_text.splitlines()
    if line_end > len(lines):
        raise CatalogBuildError(
            f"citation {citation_id!r} ends at {line_end}, source has {len(lines)} lines"
        )
    excerpt = "\n".join(lines[line_start - 1 : line_end]) + "\n"
    return {
        "citation_id": citation_id,
        "source": relative_path,
        "line_start": line_start,
        "line_end": line_end,
        "source_sha256": _sha256(source_bytes),
        "excerpt_sha256": _sha256(excerpt.encode("utf-8")),
        "excerpt": excerpt,
    }


def _candidate(
    seed: dict[str, Any], citations: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    candidate_id = seed.get("candidate_id")
    citation_refs = seed.get("citation_refs")
    source_terms = seed.get("source_terms")
    if not isinstance(candidate_id, str) or not candidate_id:
        raise CatalogBuildError("every candidate requires candidate_id")
    if not isinstance(citation_refs, list) or not citation_refs:
        raise CatalogBuildError(f"{candidate_id} requires citation_refs")
    if not isinstance(source_terms, list) or not source_terms:
        raise CatalogBuildError(f"{candidate_id} requires source_terms")
    if not all(isinstance(term, str) and term for term in source_terms):
        raise CatalogBuildError(f"{candidate_id} has an invalid source term")
    try:
        resolved_citations = [citations[ref] for ref in citation_refs]
    except KeyError as exc:
        raise CatalogBuildError(
            f"{candidate_id} references unknown citation {exc.args[0]!r}"
        ) from exc

    evidence_text = "\n".join(citation["excerpt"] for citation in resolved_citations)
    missing = [term for term in source_terms if term not in evidence_text]
    if missing:
        raise CatalogBuildError(
            f"{candidate_id} source terms are absent from cited excerpts: {missing}"
        )

    result = {key: value for key, value in seed.items() if key not in {"citation_refs"}}
    result["citations"] = sorted(
        resolved_citations,
        key=lambda item: (item["source"], item["line_start"], item["citation_id"]),
    )
    return result


def _domain(
    seed: dict[str, Any], citations: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    domain = seed.get("domain")
    if domain not in REQUIRED_DOMAINS:
        raise CatalogBuildError(f"unsupported or missing domain: {domain!r}")
    fields = [_candidate(item, citations) for item in seed.get("fields", [])]
    subobjects = [_candidate(item, citations) for item in seed.get("subobjects", [])]
    if not fields or not subobjects:
        raise CatalogBuildError(f"{domain} requires fields and subobjects")
    return {
        "domain": domain,
        "fields": sorted(fields, key=lambda item: item["candidate_id"]),
        "subobjects": sorted(subobjects, key=lambda item: item["candidate_id"]),
    }


def validate_catalog(catalog: dict[str, Any]) -> None:
    """Validate the generated preparation artifact without choosing deferred policy."""

    if catalog.get("schema_version") != SCHEMA_VERSION:
        raise CatalogBuildError("unexpected catalog schema_version")
    if catalog.get("status") != "preparation_only":
        raise CatalogBuildError("catalog must remain preparation_only")
    dependencies = catalog.get("dependencies")
    if not isinstance(dependencies, dict) or any(
        dependencies.get(task) != "not_accepted" for task in ("task_5_5", "task_5_6")
    ):
        raise CatalogBuildError("Task 5.5 and 5.6 must remain explicit dependencies")

    domains = catalog.get("domains")
    if (
        not isinstance(domains, list)
        or {item.get("domain") for item in domains if isinstance(item, dict)}
        != REQUIRED_DOMAINS
    ):
        raise CatalogBuildError("catalog must cover exactly the four PRD domains")
    shared_projection_fields = catalog.get("shared_projection_fields")
    if not isinstance(shared_projection_fields, list) or {
        item.get("field_name")
        for item in shared_projection_fields
        if isinstance(item, dict)
    } != {"core_facts", "display_name", "object_type", "summary_fields"}:
        raise CatalogBuildError("shared logical projection fields are incomplete")
    relationships = catalog.get("relationships")
    if (
        not isinstance(relationships, list)
        or {item.get("family") for item in relationships if isinstance(item, dict)}
        != REQUIRED_RELATIONSHIP_FAMILIES
    ):
        raise CatalogBuildError(
            "catalog does not cover every required relationship family"
        )

    all_items: list[dict[str, Any]] = list(shared_projection_fields)
    for domain in domains:
        all_items.extend(domain.get("fields", []))
        all_items.extend(domain.get("subobjects", []))
    all_items.extend(relationships)
    all_items.extend(catalog.get("unresolved_records", []))
    candidate_ids = [item.get("candidate_id") for item in all_items]
    if any(not isinstance(value, str) or not value for value in candidate_ids):
        raise CatalogBuildError("every catalog item requires candidate_id")
    if len(candidate_ids) != len(set(candidate_ids)):
        raise CatalogBuildError("catalog candidate IDs must be globally unique")

    for item in all_items:
        citations = item.get("citations")
        if not isinstance(citations, list) or not citations:
            raise CatalogBuildError(f"{item['candidate_id']} requires citations")
        for citation in citations:
            if (
                not isinstance(citation.get("line_start"), int)
                or not isinstance(citation.get("line_end"), int)
                or citation["line_start"] <= 0
                or citation["line_end"] < citation["line_start"]
                or len(citation.get("source_sha256", "")) != 64
                or len(citation.get("excerpt_sha256", "")) != 64
                or not citation.get("excerpt", "").strip()
            ):
                raise CatalogBuildError(
                    f"{item['candidate_id']} contains an invalid citation"
                )

    for relationship in relationships:
        if relationship.get("time_semantics") != "unresolved_task_5_5":
            raise CatalogBuildError(
                "relationship time semantics cannot be frozen before 5.5"
            )
        if relationship.get("allowed_state_policy") != "unresolved_task_6_5":
            raise CatalogBuildError("relationship states belong to Task 6.5")
        if relationship.get("direction") not in {"directed", "undirected"}:
            raise CatalogBuildError("relationship direction must be explicit")
        if not relationship.get("roles") or not relationship.get("evidence_obligation"):
            raise CatalogBuildError("relationship roles and evidence must be explicit")

    unresolved = catalog.get("unresolved_records")
    if not isinstance(unresolved, list) or not unresolved:
        raise CatalogBuildError("preparation artifact requires unresolved records")
    if any(item.get("resolution") != "deferred" for item in unresolved):
        raise CatalogBuildError("preparation cannot resolve ambiguous product policy")


def build_catalog(*, repo_root: Path, seed_path: Path) -> dict[str, Any]:
    seed = _load_json(seed_path)
    if seed.get("schema_version") != SCHEMA_VERSION:
        raise CatalogBuildError("seed uses an unsupported schema_version")
    citation_seeds = seed.get("citation_sources")
    if not isinstance(citation_seeds, dict) or not citation_seeds:
        raise CatalogBuildError("seed requires citation_sources")
    citations = {
        citation_id: _enrich_citation(
            repo_root=repo_root, citation_id=citation_id, seed=citation_seed
        )
        for citation_id, citation_seed in sorted(citation_seeds.items())
    }

    shared_projection_fields = [
        _candidate(item, citations) for item in seed.get("shared_projection_fields", [])
    ]
    domains = [_domain(item, citations) for item in seed.get("domains", [])]
    relationships = [
        _candidate(item, citations) for item in seed.get("relationships", [])
    ]
    unresolved = [
        _candidate(item, citations) for item in seed.get("unresolved_records", [])
    ]
    source_manifest = [
        {
            "source": source,
            "source_sha256": next(
                citation["source_sha256"]
                for citation in citations.values()
                if citation["source"] == source
            ),
        }
        for source in sorted({citation["source"] for citation in citations.values()})
    ]
    catalog = {
        "schema_version": SCHEMA_VERSION,
        "status": seed["status"],
        "purpose": seed["purpose"],
        "dependencies": seed["dependencies"],
        "source_precedence": seed["source_precedence"],
        "source_manifest": source_manifest,
        "shared_projection_fields": sorted(
            shared_projection_fields, key=lambda item: item["candidate_id"]
        ),
        "domains": sorted(domains, key=lambda item: item["domain"]),
        "relationships": sorted(relationships, key=lambda item: item["candidate_id"]),
        "unresolved_records": sorted(unresolved, key=lambda item: item["candidate_id"]),
    }
    validate_catalog(catalog)
    return catalog


def canonical_json_bytes(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--seed", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    s6_dir = Path(__file__).resolve().parent
    repo_root = args.repo_root or s6_dir.parents[3]
    seed_path = args.seed or s6_dir / "catalog-candidate-seeds.json"
    output_path = args.output or s6_dir / "catalog-candidates.json"
    generated = canonical_json_bytes(
        build_catalog(repo_root=repo_root, seed_path=seed_path)
    )
    if args.write:
        output_path.write_bytes(generated)
    if args.check:
        if not output_path.is_file() or output_path.read_bytes() != generated:
            raise SystemExit("catalog artifact is missing or stale")
    if not args.write and not args.check:
        print(generated.decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
