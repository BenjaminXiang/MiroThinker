#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import warnings
from dataclasses import asdict
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_agents.paper.milvus_backfill import backfill_paper_chunks  # noqa: E402
from src.data_agents.professor.vectorizer import EmbeddingClient  # noqa: E402
from src.data_agents.providers.local_api_key import load_local_api_key  # noqa: E402

logger = logging.getLogger(__name__)


def _open_database_connection(dsn: str) -> psycopg.Connection:
    return psycopg.connect(dsn, row_factory=dict_row)


def _open_milvus_client(uri: str):
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


def _load_resume_ids(path: Path | None) -> set[str]:
    if path is None or not path.exists():
        return set()

    resume_ids: set[str] = set()
    for line_number, raw_line in enumerate(path.read_text().splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            payload = json.loads(raw_line)
        except json.JSONDecodeError:
            logger.warning("Skipping corrupt resume line %d in %s", line_number, path)
            continue
        paper_id = payload.get("paper_id")
        if isinstance(paper_id, str) and paper_id:
            resume_ids.add(paper_id)
    return resume_ids


def _backfill_professor_domain(conn, milvus_client, embedding_client, **kwargs):
    raise NotImplementedError(
        "Professor Milvus backfill is not implemented here. Reuse "
        "src.data_agents.professor.vectorizer.ProfessorVectorizer instead."
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill Milvus collections.")
    parser.add_argument("--domain", choices=("paper", "professor"), required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--milvus-uri", default="./milvus.db")
    parser.add_argument("--resume", nargs="?")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    log_level = getattr(logging, str(args.log_level).upper(), logging.INFO)
    logging.basicConfig(level=log_level, format="%(levelname)s %(name)s: %(message)s")

    dsn = os.environ.get("DATABASE_URL")
    if dsn is None:
        sys.stderr.write("DATABASE_URL is required for Milvus backfill.\n")
        raise SystemExit(1)

    conn = None
    try:
        conn = _open_database_connection(dsn)
        milvus_client = _open_milvus_client(args.milvus_uri)
        embedding_client = _open_embedding_client()
        resume_ids = _load_resume_ids(Path(args.resume) if args.resume else None)

        if args.domain == "paper":
            report = backfill_paper_chunks(
                conn,
                milvus_client,
                embedding_client,
                limit=args.limit,
                batch_size=args.batch_size,
                resume_ids=resume_ids,
            )
        else:
            report = _backfill_professor_domain(
                conn,
                milvus_client,
                embedding_client,
                limit=args.limit,
                batch_size=args.batch_size,
                resume_ids=resume_ids,
            )

        print(json.dumps(asdict(report), ensure_ascii=False))
        return 0
    except Exception:
        logging.exception("Milvus backfill failed")
        return 1
    finally:
        if conn is not None:
            close = getattr(conn, "close", None)
            if callable(close):
                close()


if __name__ == "__main__":
    raise SystemExit(main())
