#!/usr/bin/env python3
"""Read-only acceptance smoke for professor/paper retrieval and optional chat.

The retrieval checks instantiate RetrievalService directly and only issue read
queries against Postgres/Milvus plus embedding/rerank providers. The optional
chat check posts to a running admin-console API and therefore creates/updates
chat session state; keep it opt-in via --chat-url.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_agents.professor.vectorizer import EmbeddingClient  # noqa: E402
from src.data_agents.providers.local_api_key import load_local_api_key  # noqa: E402
from src.data_agents.providers.rerank import RerankerClient  # noqa: E402
from src.data_agents.service.retrieval import Evidence, RetrievalService  # noqa: E402


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    ok: bool
    message: str
    evidence: dict[str, Any]


def _open_database_connection(dsn: str) -> psycopg.Connection:
    return psycopg.connect(dsn, row_factory=dict_row)


def _open_milvus_client(uri: str):
    if uri.strip() != ":memory:":
        os.environ.setdefault("MILVUS_USE_REAL_CLIENT", "1")
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="pkg_resources is deprecated as an API.*",
            category=UserWarning,
            module="milvus_lite",
        )
        from pymilvus import MilvusClient

    return MilvusClient(uri=uri)


def _open_embedding_client() -> EmbeddingClient:
    return EmbeddingClient(api_key=load_local_api_key())


def _open_reranker_client() -> RerankerClient:
    return RerankerClient(api_key=load_local_api_key())


def _make_retrieval_service(*, database_url: str, milvus_uri: str) -> RetrievalService:
    return RetrievalService(
        pg_conn_factory=lambda: _open_database_connection(database_url),
        milvus_client=_open_milvus_client(milvus_uri),
        embedding_client=_open_embedding_client(),
        reranker=_open_reranker_client(),
        cache=None,
    )


def _close_retrieval_service(service: RetrievalService) -> None:
    milvus_client = getattr(service, "_milvus_client", None)
    close = getattr(milvus_client, "close", None)
    if callable(close):
        close()


def _has_traceability(evidence: Evidence) -> bool:
    metadata = evidence.metadata or {}
    if evidence.source_url:
        return True
    trace_keys = {
        "chunk_id",
        "chunk_type",
        "collection_name",
        "professor_retrieval_index",
        "retrieval_source",
        "profile_url",
        "homepage_url",
        "doi",
        "title_clean",
        "snippet_source",
    }
    return any(metadata.get(key) for key in trace_keys)


def _evidence_summary(evidence: Evidence) -> dict[str, Any]:
    metadata = evidence.metadata or {}
    return {
        "object_type": evidence.object_type,
        "object_id": evidence.object_id,
        "score": evidence.score,
        "source_url": evidence.source_url,
        "snippet": evidence.snippet[:240],
        "metadata": {
            key: metadata.get(key)
            for key in (
                "name",
                "institution",
                "title_clean",
                "year",
                "venue",
                "chunk_id",
                "chunk_type",
                "collection_name",
                "professor_retrieval_index",
                "retrieval_source",
                "snippet_source",
                "quality_status",
            )
            if metadata.get(key) is not None
        },
    }


def _matches_professor(
    evidence: Evidence,
    *,
    expected_id: str | None,
    expected_name: str | None,
) -> bool:
    metadata = evidence.metadata or {}
    if evidence.object_type != "professor":
        return False
    if expected_id and evidence.object_id == expected_id:
        return True
    if expected_name:
        name_fields = [
            str(metadata.get("name") or ""),
            str(metadata.get("name_en") or ""),
            evidence.snippet,
        ]
        return any(expected_name in field for field in name_fields)
    return False


def _matches_paper(
    evidence: Evidence,
    *,
    expected_id: str | None,
    expected_title: str | None,
) -> bool:
    metadata = evidence.metadata or {}
    if evidence.object_type != "paper":
        return False
    if expected_id and evidence.object_id == expected_id:
        return True
    if expected_title:
        title_fields = [
            str(metadata.get("title_clean") or ""),
            str(metadata.get("title_raw") or ""),
            evidence.snippet,
        ]
        return any(expected_title in field for field in title_fields)
    return False


def assert_professor_retrieval(
    results: list[Evidence],
    *,
    expected_id: str | None,
    expected_name: str | None,
) -> CheckResult:
    for item in results:
        if _matches_professor(
            item,
            expected_id=expected_id,
            expected_name=expected_name,
        ):
            if not _has_traceability(item):
                return CheckResult(
                    name="professor_retrieval",
                    ok=False,
                    message="target professor found but traceability/source fields are missing",
                    evidence=_evidence_summary(item),
                )
            return CheckResult(
                name="professor_retrieval",
                ok=True,
                message="target professor found with traceability/source fields",
                evidence=_evidence_summary(item),
            )
    return CheckResult(
        name="professor_retrieval",
        ok=False,
        message="target professor was not found in retrieval results",
        evidence={"top_results": [_evidence_summary(item) for item in results[:5]]},
    )


def assert_paper_retrieval(
    results: list[Evidence],
    *,
    expected_id: str | None,
    expected_title: str | None,
) -> CheckResult:
    for item in results:
        if _matches_paper(
            item,
            expected_id=expected_id,
            expected_title=expected_title,
        ):
            if not _has_traceability(item):
                return CheckResult(
                    name="paper_retrieval",
                    ok=False,
                    message="target paper found but traceability/source fields are missing",
                    evidence=_evidence_summary(item),
                )
            return CheckResult(
                name="paper_retrieval",
                ok=True,
                message="target paper found with traceability/source fields",
                evidence=_evidence_summary(item),
            )
    return CheckResult(
        name="paper_retrieval",
        ok=False,
        message="target paper was not found in retrieval results",
        evidence={"top_results": [_evidence_summary(item) for item in results[:5]]},
    )


def _post_chat(chat_url: str, query: str, *, timeout_seconds: float) -> dict[str, Any]:
    url = chat_url.rstrip("/") + "/api/chat"
    body = json.dumps({"query": query}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"chat POST failed with HTTP {exc.code}: {detail}") from exc


def _chat_evidence_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    citations = payload.get("citations") or []
    structured_payload = payload.get("structured_payload") or {}
    retrieval_evidence = structured_payload.get("retrieval_evidence") or []
    return [
        item
        for item in [*citations, *retrieval_evidence]
        if isinstance(item, dict)
    ]


def _contains_text(value: Any, expected: str) -> bool:
    return expected.casefold() in str(value or "").casefold()


def _chat_item_summary(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item.get(key)
        for key in (
            "type",
            "id",
            "professor_id",
            "paper_id",
            "title",
            "canonical_name",
            "title_clean",
            "url",
            "source_url",
            "snippet",
            "score",
        )
        if item.get(key) is not None
    }


def _matches_chat_professor(
    item: dict[str, Any],
    *,
    expected_id: str | None,
    expected_name: str | None,
) -> bool:
    if item.get("type") != "professor":
        return False
    if expected_id:
        ids = [item.get("id"), item.get("professor_id")]
        if any(str(value or "") == expected_id for value in ids):
            return True
    if expected_name:
        return any(
            _contains_text(item.get(key), expected_name)
            for key in ("title", "canonical_name", "name", "snippet")
        )
    return False


def _matches_chat_paper(
    item: dict[str, Any],
    *,
    expected_id: str | None,
    expected_title: str | None,
) -> bool:
    if item.get("type") != "paper":
        return False
    if expected_id:
        ids = [item.get("id"), item.get("paper_id")]
        if any(str(value or "") == expected_id for value in ids):
            return True
    if expected_title:
        return any(
            _contains_text(item.get(key), expected_title)
            for key in ("title", "title_clean", "title_raw", "snippet")
        )
    return False


def _has_chat_traceability(item: dict[str, Any]) -> bool:
    has_stable_id = any(
        item.get(key)
        for key in ("id", "professor_id", "paper_id", "company_id", "patent_id")
    )
    has_user_audit_context = any(
        item.get(key)
        for key in (
            "url",
            "source_url",
            "snippet",
            "title",
            "canonical_name",
            "title_clean",
            "patent_number",
        )
    )
    return has_stable_id and has_user_audit_context


def _assert_expected_chat_target(
    items: list[dict[str, Any]],
    *,
    domain: str,
    expected_id: str | None,
    expected_text: str | None,
) -> CheckResult | None:
    if not (expected_id or expected_text):
        return CheckResult(
            name="chat_retrieval",
            ok=False,
            message=f"expected {domain} target is required for chat acceptance",
            evidence={
                "expected_domain": domain,
                "reason": "domain presence alone is not an acceptance signal",
                "top_items": [_chat_item_summary(item) for item in items[:8]],
            },
        )

    if domain == "professor":
        matches = [
            item
            for item in items
            if _matches_chat_professor(
                item,
                expected_id=expected_id,
                expected_name=expected_text,
            )
        ]
        expected = {"professor_id": expected_id, "professor_name": expected_text}
    elif domain == "paper":
        matches = [
            item
            for item in items
            if _matches_chat_paper(
                item,
                expected_id=expected_id,
                expected_title=expected_text,
            )
        ]
        expected = {"paper_id": expected_id, "paper_title": expected_text}
    else:
        return None

    if not matches:
        return CheckResult(
            name="chat_retrieval",
            ok=False,
            message=f"chat response missing expected {domain} target",
            evidence={
                "expected": {
                    key: value for key, value in expected.items() if value
                },
                "top_items": [_chat_item_summary(item) for item in items[:8]],
            },
        )

    for match in matches:
        if _has_chat_traceability(match):
            return None

    return CheckResult(
        name="chat_retrieval",
        ok=False,
        message=f"expected {domain} target found but traceability fields are missing",
        evidence={"match": _chat_item_summary(matches[0])},
    )


def assert_chat_response(
    payload: dict[str, Any],
    *,
    expected_domains: set[str],
    expected_professor_id: str | None = None,
    expected_professor_name: str | None = None,
    expected_paper_id: str | None = None,
    expected_paper_title: str | None = None,
) -> CheckResult:
    items = _chat_evidence_items(payload)
    domains = {
        str(item.get("type") or "")
        for item in items
    }
    missing = expected_domains - domains
    if missing:
        return CheckResult(
            name="chat_retrieval",
            ok=False,
            message=f"chat response missing expected domains: {sorted(missing)}",
            evidence={
                "query_type": payload.get("query_type"),
                "domains": sorted(domains),
                "item_count": len(items),
            },
        )
    if not items:
        return CheckResult(
            name="chat_retrieval",
            ok=False,
            message="chat response has no citations or retrieval_evidence",
            evidence={"query_type": payload.get("query_type")},
        )

    target_checks: list[CheckResult | None] = []
    if "professor" in expected_domains:
        target_checks.append(
            _assert_expected_chat_target(
                items,
                domain="professor",
                expected_id=expected_professor_id,
                expected_text=expected_professor_name,
            )
        )
    if "paper" in expected_domains:
        target_checks.append(
            _assert_expected_chat_target(
                items,
                domain="paper",
                expected_id=expected_paper_id,
                expected_text=expected_paper_title,
            )
        )

    for target_check in target_checks:
        if target_check is not None:
            return target_check

    return CheckResult(
        name="chat_retrieval",
        ok=True,
        message="chat response returned expected targets with citations/evidence",
        evidence={
            "query_type": payload.get("query_type"),
            "domains": sorted(domains),
            "item_count": len(items),
            "expected": {
                key: value
                for key, value in {
                    "professor_id": expected_professor_id,
                    "professor_name": expected_professor_name,
                    "paper_id": expected_paper_id,
                    "paper_title": expected_paper_title,
                }.items()
                if value
            },
            "side_effect": "POST /api/chat creates or updates chat session state",
        },
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate that ready professor and paper samples are retrievable from "
            "Milvus-backed RetrievalService, with optional live chat POST smoke."
        )
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URL_TEST"),
        help="Postgres DSN. Defaults to DATABASE_URL or DATABASE_URL_TEST.",
    )
    parser.add_argument(
        "--milvus-uri",
        default=os.environ.get("CHAT_MILVUS_URI") or os.environ.get("MILVUS_URI"),
        help="Milvus URI. Defaults to CHAT_MILVUS_URI or MILVUS_URI.",
    )
    parser.add_argument(
        "--professor-query",
        help="Query expected to retrieve the target professor.",
    )
    parser.add_argument("--professor-id", help="Expected professor_id.")
    parser.add_argument("--professor-name", help="Expected professor name substring.")
    parser.add_argument(
        "--paper-query",
        help="Query expected to retrieve the target paper.",
    )
    parser.add_argument("--paper-id", help="Expected paper_id.")
    parser.add_argument("--paper-title", help="Expected paper title substring.")
    parser.add_argument("--candidate-limit", type=int, default=30)
    parser.add_argument("--final-top-k", type=int, default=10)
    parser.add_argument(
        "--chat-url",
        help=(
            "Optional admin-console base URL. When set, the script POSTs to "
            "/api/chat and creates/updates chat session state."
        ),
    )
    parser.add_argument(
        "--chat-query",
        help="Optional query for the live chat POST. Defaults to professor-query.",
    )
    parser.add_argument(
        "--chat-expected-domain",
        action="append",
        choices=("professor", "paper", "company", "patent"),
        default=[],
        help="Expected domain in chat citations or structured retrieval_evidence.",
    )
    parser.add_argument("--chat-timeout-seconds", type=float, default=20.0)
    parser.add_argument(
        "--skip-retrieval-checks",
        action="store_true",
        help=(
            "Run only the live chat POST check. Use this when the chat backend "
            "uses the same local milvus_lite file as this script."
        ),
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    checks: list[CheckResult] = []

    if not args.skip_retrieval_checks:
        if not args.database_url:
            raise SystemExit("--database-url or DATABASE_URL is required")
        if not args.milvus_uri:
            raise SystemExit("--milvus-uri or CHAT_MILVUS_URI/MILVUS_URI is required")
        if not args.professor_query:
            raise SystemExit(
                "--professor-query is required unless --skip-retrieval-checks is set"
            )
        if not args.paper_query:
            raise SystemExit(
                "--paper-query is required unless --skip-retrieval-checks is set"
            )
        if not (args.professor_id or args.professor_name):
            raise SystemExit("--professor-id or --professor-name is required")
        if not (args.paper_id or args.paper_title):
            raise SystemExit("--paper-id or --paper-title is required")

        service = _make_retrieval_service(
            database_url=args.database_url,
            milvus_uri=args.milvus_uri,
        )
        try:
            professor_results = service.retrieve(
                args.professor_query,
                domains=("professor",),
                candidate_limit=args.candidate_limit,
                final_top_k=args.final_top_k,
            )
            paper_results = service.retrieve(
                args.paper_query,
                domains=("paper",),
                candidate_limit=args.candidate_limit,
                final_top_k=args.final_top_k,
            )
        finally:
            _close_retrieval_service(service)

        checks.extend(
            [
                assert_professor_retrieval(
                    professor_results,
                    expected_id=args.professor_id,
                    expected_name=args.professor_name,
                ),
                assert_paper_retrieval(
                    paper_results,
                    expected_id=args.paper_id,
                    expected_title=args.paper_title,
                ),
            ]
        )

    if args.chat_url:
        chat_query = args.chat_query or args.professor_query
        if not chat_query:
            raise SystemExit(
                "--chat-query is required when --skip-retrieval-checks is set"
            )
        chat_payload = _post_chat(
            args.chat_url,
            chat_query,
            timeout_seconds=args.chat_timeout_seconds,
        )
        expected_domains = set(args.chat_expected_domain or ["professor"])
        checks.append(
            assert_chat_response(
                chat_payload,
                expected_domains=expected_domains,
                expected_professor_id=args.professor_id,
                expected_professor_name=args.professor_name,
                expected_paper_id=args.paper_id,
                expected_paper_title=args.paper_title,
            )
        )
    elif args.skip_retrieval_checks:
        raise SystemExit("--chat-url is required when --skip-retrieval-checks is set")

    payload = {
        "status": "PASS" if all(check.ok for check in checks) else "FAIL",
        "checks": [asdict(check) for check in checks],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if all(check.ok for check in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
