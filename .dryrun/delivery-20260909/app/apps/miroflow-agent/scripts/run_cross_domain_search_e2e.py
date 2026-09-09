#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_agents.contracts import ReleasedObject
from src.data_agents.service.search_service import DataSearchService
from src.data_agents.storage.milvus_store import MilvusVectorStore
from src.data_agents.storage.sqlite_store import SqliteReleasedObjectStore


@dataclass(frozen=True, slots=True)
class CrossDomainSearchReport:
    company_released_count: int
    patent_released_count: int
    professor_released_count: int
    paper_released_count: int
    total_indexed_count: int
    professor_query: str
    professor_result_ids: list[str]
    company_query: str
    company_result_ids: list[str]
    patent_query: str
    patent_result_ids: list[str]
    paper_query: str
    paper_result_ids: list[str]
    cross_domain_query: str
    cross_domain_result_domains: list[str]
    cross_domain_result_ids: list[str]
    professor_relation_source_id: str
    professor_related_paper_ids: list[str]
    company_relation_source_id: str
    company_related_patent_ids: list[str]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _latest_output(prefix: str) -> Path:
    candidates = sorted((_repo_root() / "logs" / "debug").glob(f"{prefix}_*"))
    if not candidates:
        raise FileNotFoundError(f"no output directory found for prefix: {prefix}")
    return candidates[-1] / "released_objects.jsonl"


def _default_output_paths() -> tuple[Path, Path, Path]:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = _repo_root() / "logs" / "debug" / f"cross_domain_search_e2e_{timestamp}"
    return (
        output_dir / "released_objects.sqlite3",
        output_dir / "released_objects_milvus.db",
        output_dir / "report.json",
    )


def _load_released_objects(path: Path) -> list[ReleasedObject]:
    if not path.exists():
        raise FileNotFoundError(f"released object file not found: {path}")
    objects: list[ReleasedObject] = []
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            try:
                objects.append(ReleasedObject.model_validate_json(line))
            except Exception as error:
                raise ValueError(
                    f"invalid ReleasedObject JSONL entry in {path}:{line_number}: {error}"
                ) from error
    if not objects:
        raise ValueError(f"no released objects found in {path}")
    return objects


def _validate_search_hit(
    *,
    domain: str,
    expected_id: str,
    result_ids: list[str],
    query: str,
) -> None:
    if expected_id in result_ids:
        return
    raise RuntimeError(
        f"{domain} search did not return expected object {expected_id} for query={query!r}; "
        f"result_ids={result_ids}"
    )


def _select_company_with_patent_link(
    *,
    companies: list[ReleasedObject],
    patents: list[ReleasedObject],
) -> tuple[ReleasedObject, list[str]]:
    company_ids = {item.id for item in companies}
    for patent in patents:
        for company_id in patent.core_facts.get("company_ids") or []:
            if company_id in company_ids:
                return (
                    next(item for item in companies if item.id == company_id),
                    [patent.id],
                )
    raise RuntimeError("no patent with company_ids linked to loaded company objects")


def _select_professor_with_paper_link(
    *,
    professors: list[ReleasedObject],
    papers: list[ReleasedObject],
) -> tuple[ReleasedObject, list[str]]:
    professor_ids = {item.id for item in professors}
    for paper in papers:
        for professor_id in paper.core_facts.get("professor_ids") or []:
            if professor_id in professor_ids:
                return (
                    next(item for item in professors if item.id == professor_id),
                    [paper.id],
                )
    raise RuntimeError("no paper with professor_ids linked to loaded professor objects")


def run_cross_domain_search_e2e(
    *,
    company_released_path: Path,
    patent_released_path: Path,
    professor_released_path: Path,
    paper_released_path: Path,
    sqlite_db_path: Path,
    milvus_db_path: Path,
) -> CrossDomainSearchReport:
    company_objects = _load_released_objects(company_released_path)
    patent_objects = _load_released_objects(patent_released_path)
    professor_objects = _load_released_objects(professor_released_path)
    paper_objects = _load_released_objects(paper_released_path)
    all_objects = [
        *company_objects,
        *patent_objects,
        *professor_objects,
        *paper_objects,
    ]

    sql_store = SqliteReleasedObjectStore(sqlite_db_path)
    vector_store = MilvusVectorStore(
        uri=str(milvus_db_path),
        collection_name="released_objects",
    )
    sql_store.upsert_released_objects(all_objects)
    vector_store.upsert_released_objects(all_objects)
    service = DataSearchService(sql_store=sql_store, vector_store=vector_store)

    professor_probe = professor_objects[0]
    company_probe = company_objects[0]
    patent_probe = patent_objects[0]
    paper_probe = paper_objects[0]
    linked_professor, expected_paper_ids = _select_professor_with_paper_link(
        professors=professor_objects,
        papers=paper_objects,
    )
    linked_company, expected_patent_ids = _select_company_with_patent_link(
        companies=company_objects,
        patents=patent_objects,
    )

    professor_query = f"教授 {professor_probe.display_name}"
    company_query = f"公司 {company_probe.display_name}"
    patent_query = f"专利 {patent_probe.display_name}"
    paper_query = f"论文 {paper_probe.display_name}"
    cross_domain_query = f"教授 论文 {linked_professor.display_name}"

    professor_results = service.search(professor_query, limit=10)
    company_results = service.search(company_query, limit=10)
    patent_results = service.search(patent_query, limit=10)
    paper_results = service.search(paper_query, limit=10)
    cross_domain_results = service.search(cross_domain_query, limit=20)
    professor_related = service.get_related_objects(
        source_domain="professor",
        source_id=linked_professor.id,
        target_domain="paper",
        relation_type="professor_papers",
        limit=20,
    )
    company_related = service.get_related_objects(
        source_domain="company",
        source_id=linked_company.id,
        target_domain="patent",
        relation_type="company_patents",
        limit=20,
    )

    professor_result_ids = [item.id for item in professor_results.results]
    company_result_ids = [item.id for item in company_results.results]
    patent_result_ids = [item.id for item in patent_results.results]
    paper_result_ids = [item.id for item in paper_results.results]
    cross_domain_result_ids = [item.id for item in cross_domain_results.results]
    cross_domain_result_domains = [
        item.object_type for item in cross_domain_results.results
    ]
    professor_related_paper_ids = [item.id for item in professor_related]
    company_related_patent_ids = [item.id for item in company_related]

    _validate_search_hit(
        domain="professor",
        expected_id=professor_probe.id,
        result_ids=professor_result_ids,
        query=professor_query,
    )
    _validate_search_hit(
        domain="company",
        expected_id=company_probe.id,
        result_ids=company_result_ids,
        query=company_query,
    )
    _validate_search_hit(
        domain="patent",
        expected_id=patent_probe.id,
        result_ids=patent_result_ids,
        query=patent_query,
    )
    _validate_search_hit(
        domain="paper",
        expected_id=paper_probe.id,
        result_ids=paper_result_ids,
        query=paper_query,
    )

    if "professor" not in cross_domain_results.domains or "paper" not in (
        cross_domain_results.domains
    ):
        raise RuntimeError(
            "cross-domain query routing did not include professor and paper domains: "
            f"{cross_domain_results.domains}"
        )
    if "professor" not in cross_domain_result_domains:
        raise RuntimeError(
            "cross-domain query returned no professor objects: "
            f"{cross_domain_result_ids}"
        )
    if "paper" not in cross_domain_result_domains:
        raise RuntimeError(
            "cross-domain query returned no paper objects: "
            f"{cross_domain_result_ids}"
        )
    if not any(item in professor_related_paper_ids for item in expected_paper_ids):
        raise RuntimeError(
            "professor->paper relation lookup missed linked paper ids "
            f"{expected_paper_ids}; got {professor_related_paper_ids}"
        )
    if not any(item in company_related_patent_ids for item in expected_patent_ids):
        raise RuntimeError(
            "company->patent relation lookup missed linked patent ids "
            f"{expected_patent_ids}; got {company_related_patent_ids}"
        )

    return CrossDomainSearchReport(
        company_released_count=len(company_objects),
        patent_released_count=len(patent_objects),
        professor_released_count=len(professor_objects),
        paper_released_count=len(paper_objects),
        total_indexed_count=len(all_objects),
        professor_query=professor_query,
        professor_result_ids=professor_result_ids,
        company_query=company_query,
        company_result_ids=company_result_ids,
        patent_query=patent_query,
        patent_result_ids=patent_result_ids,
        paper_query=paper_query,
        paper_result_ids=paper_result_ids,
        cross_domain_query=cross_domain_query,
        cross_domain_result_domains=cross_domain_result_domains,
        cross_domain_result_ids=cross_domain_result_ids,
        professor_relation_source_id=linked_professor.id,
        professor_related_paper_ids=professor_related_paper_ids,
        company_relation_source_id=linked_company.id,
        company_related_patent_ids=company_related_patent_ids,
    )


def main() -> int:
    default_sqlite_db_path, default_milvus_db_path, default_report_output = (
        _default_output_paths()
    )
    parser = argparse.ArgumentParser(
        description=(
            "Run cross-domain publication + search e2e against real released "
            "objects from all data domains."
        )
    )
    parser.add_argument(
        "--company-released",
        type=Path,
        default=_latest_output("company_release_e2e"),
    )
    parser.add_argument(
        "--patent-released",
        type=Path,
        default=_latest_output("patent_release_e2e"),
    )
    parser.add_argument(
        "--professor-released",
        type=Path,
        default=_latest_output("professor_release_e2e"),
    )
    parser.add_argument(
        "--paper-released",
        type=Path,
        default=_latest_output("paper_release_e2e"),
    )
    parser.add_argument(
        "--sqlite-db",
        type=Path,
        default=default_sqlite_db_path,
    )
    parser.add_argument(
        "--milvus-db",
        type=Path,
        default=default_milvus_db_path,
    )
    parser.add_argument(
        "--report-output",
        type=Path,
        default=default_report_output,
        help="Output path for report JSON. Use '-' to print report JSON to stdout.",
    )
    args = parser.parse_args()

    report = run_cross_domain_search_e2e(
        company_released_path=args.company_released,
        patent_released_path=args.patent_released,
        professor_released_path=args.professor_released,
        paper_released_path=args.paper_released,
        sqlite_db_path=args.sqlite_db,
        milvus_db_path=args.milvus_db,
    )
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "inputs": {
            "company_released_jsonl": str(args.company_released),
            "patent_released_jsonl": str(args.patent_released),
            "professor_released_jsonl": str(args.professor_released),
            "paper_released_jsonl": str(args.paper_released),
        },
        "outputs": {
            "sqlite_db": str(args.sqlite_db),
            "milvus_db": str(args.milvus_db),
        },
        "search_summary": asdict(report),
    }

    if str(args.report_output) == "-":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    args.report_output.parent.mkdir(parents=True, exist_ok=True)
    args.report_output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(args.report_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
