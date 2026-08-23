"""Lightweight full-column lane: load the six extracted P4 JSONL batches.

Boring by design: hot queryable columns + full raw JSONB per row, trigram
indexes for keyword search, no adjudication machinery. Idempotent: truncates
and reloads. Target database carries its own disposable marker and nothing
else shares it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import psycopg

SOURCES_ROOT = Path(
    "/var/tmp/mirothinker-restores/canonical-v2-s2b-20260711T152222Z"
    "/workspace/docs/source_backfills"
)
DATABASE = "miroflow_light_lane_r1"

DDL = """
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS vector;

DROP TABLE IF EXISTS company CASCADE;
CREATE TABLE company (
    company_name text PRIMARY KEY,
    industry text, business text, geography text, founded_date text,
    legal_representative text, registered_address text, website text,
    email text, phone text, company_type text, team text,
    product_summary text, product_features text,
    application_scenarios text,
    raw jsonb NOT NULL
);
CREATE INDEX company_name_trgm ON company USING gin (company_name gin_trgm_ops);
CREATE INDEX company_industry_trgm ON company USING gin (industry gin_trgm_ops);

DROP TABLE IF EXISTS patent CASCADE;
CREATE TABLE patent (
    patent_id text PRIMARY KEY,
    patent_number text, title text, patent_type text, abstract text,
    technology_effect text, grant_date text, ipc_codes jsonb,
    applicants jsonb NOT NULL, raw jsonb NOT NULL
);
CREATE INDEX patent_title_trgm ON patent USING gin (title gin_trgm_ops);
CREATE INDEX patent_number_idx ON patent (patent_number);
CREATE INDEX patent_applicants_gin ON patent USING gin (applicants jsonb_path_ops);

DROP TABLE IF EXISTS paper CASCADE;
CREATE TABLE paper (
    paper_id text PRIMARY KEY,
    title text, abstract text, summary_zh text, doi text, arxiv_id text,
    openalex_id text, year int, venue text, citation_count int,
    authors jsonb NOT NULL, raw jsonb NOT NULL
);
CREATE INDEX paper_title_trgm ON paper USING gin (title gin_trgm_ops);
CREATE INDEX paper_doi_idx ON paper (doi);

DROP TABLE IF EXISTS professor CASCADE;
CREATE TABLE professor (
    professor_id text PRIMARY KEY,
    name text NOT NULL, name_en text, institution text, department text,
    title text, research_directions jsonb, raw jsonb NOT NULL
);
CREATE INDEX professor_name_trgm ON professor USING gin (name gin_trgm_ops);
CREATE INDEX professor_institution_trgm ON professor
    USING gin (institution gin_trgm_ops);

DROP TABLE IF EXISTS prof_paper_link CASCADE;
CREATE TABLE prof_paper_link (
    professor_id text NOT NULL,
    paper_id text NOT NULL,
    link_status text NOT NULL,
    match_reason text,
    professor_name text,
    PRIMARY KEY (professor_id, paper_id)
);
CREATE INDEX link_paper_idx ON prof_paper_link (paper_id);

DROP TABLE IF EXISTS applicant_binding CASCADE;
CREATE TABLE applicant_binding (
    applicant_name text PRIMARY KEY,
    status text NOT NULL,
    resolved_company text,
    aliases jsonb NOT NULL DEFAULT '[]',
    evidence_urls jsonb NOT NULL DEFAULT '[]',
    confidence text,
    patent_count int,
    note text,
    raw jsonb NOT NULL
);
CREATE INDEX applicant_name_trgm ON applicant_binding
    USING gin (applicant_name gin_trgm_ops);
CREATE INDEX resolved_company_idx ON applicant_binding (resolved_company);
"""

# Embeddings are derived data rebuilt by embed_light_lane.py; a table reload
# must never drop them.
EMBEDDING_DDL = """
CREATE TABLE IF NOT EXISTS embedding (
    vec_id text PRIMARY KEY,
    entity_type text NOT NULL,
    entity_id text NOT NULL,
    content_sha256 text NOT NULL,
    dim int NOT NULL,
    vec vector(4096) NOT NULL
);
CREATE INDEX IF NOT EXISTS embedding_entity_idx ON embedding (entity_type, entity_id);
"""

COMPANY_HOT = (
    "company_name", "industry", "business", "geography", "founded_date",
    "legal_representative", "registered_address", "website", "email", "phone",
    "company_type", "team", "product_summary",
    "product_features", "application_scenarios",
)
PATENT_HOT = (
    "patent_id", "patent_number", "title", "patent_type", "abstract",
    "technology_effect", "grant_date", "ipc_codes", "applicants",
)
PAPER_HOT = (
    "paper_id", "title", "abstract", "summary_zh", "doi", "arxiv_id",
    "openalex_id", "year", "venue", "citation_count", "authors",
)
PROFESSOR_HOT = (
    "professor_id", "name", "name_en", "institution", "department", "title",
    "research_directions",
)


INVISIBLE = "\u200b\u200c\u200d\ufeff\u00a0"


def _clean_text(value):
    if not isinstance(value, str):
        return value
    return value.translate({ord(ch): None for ch in INVISIBLE}).strip()


def _hot(record: dict, fields: tuple[str, ...]) -> list:
    values = []
    for field in fields:
        value = record.get(field)
        if isinstance(value, str):
            value = _clean_text(value)
        values.append(json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value)
    return values


def load_jsonl(name: str):
    path = SOURCES_ROOT / name
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def load_table(connection, source_name: str, table: str, hot: tuple[str, ...], columns: tuple[str, ...]):
    placeholders = ", ".join(["%s"] * len(columns))
    statement = (
        f"INSERT INTO {table} ({', '.join(columns)}) "
        f"VALUES ({placeholders}) ON CONFLICT DO NOTHING"
    )
    count = 0
    for record in load_jsonl(source_name):
        connection.cursor().execute(
            statement, [*_hot(record, hot), psycopg.types.json.Jsonb(record)]
        )
        count += 1
    return count


def main() -> None:
    connection = psycopg.connect(
        f"postgresql://miroflow@127.0.0.1:55458/{DATABASE}", autocommit=False
    )
    with connection:
        with connection.cursor() as cursor:
            cursor.execute(DDL)
            cursor.execute(EMBEDDING_DDL)
        counts = {}
        counts["company"] = load_table(
            connection, "p4-company-full-v1.jsonl", "company",
            COMPANY_HOT, (*COMPANY_HOT, "raw"),
        )
        counts["patent"] = load_table(
            connection, "p4-patent-full-v1.jsonl", "patent",
            PATENT_HOT, (*PATENT_HOT, "raw"),
        )
        counts["paper"] = load_table(
            connection, "p4-paper-salvage-v1.jsonl", "paper",
            PAPER_HOT, (*PAPER_HOT, "raw"),
        )
        counts["professor"] = load_table(
            connection, "p4-professor-full-v1.jsonl", "professor",
            PROFESSOR_HOT, (*PROFESSOR_HOT, "raw"),
        )
        cursor = connection.cursor()
        for record in load_jsonl("p4-professor-paper-links-v1.jsonl"):
            cursor.execute(
                "INSERT INTO prof_paper_link (professor_id, paper_id, "
                "link_status, match_reason, professor_name) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                (
                    record["professor_id"], record["paper_id"],
                    record.get("link_status"), record.get("match_reason"),
                    record.get("professor_name"),
                ),
            )
            counts["link"] = counts.get("link", 0) + 1
        for record in load_jsonl("p4-applicant-binding-full-v1.jsonl"):
            status = record.get("status") or "unknown"
            applicant = record.get("applicant_name") or f"unkeyed:{counts.get('applicant', 0)}"
            cursor.execute(
                "INSERT INTO applicant_binding (applicant_name, status, "
                "resolved_company, aliases, evidence_urls, confidence, "
                "patent_count, note, raw) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT DO NOTHING",
                (
                    applicant, status,
                    record.get("resolved_company") or None,
                    psycopg.types.json.Jsonb(record.get("aliases") or []),
                    psycopg.types.json.Jsonb(record.get("evidence_urls") or []),
                    record.get("confidence") or None,
                    record.get("patent_count"),
                    record.get("note"),
                    psycopg.types.json.Jsonb(record),
                ),
            )
            counts["applicant"] = counts.get("applicant", 0) + 1
    print(json.dumps(counts, ensure_ascii=False))
    for key in counts:
        actual = connection.execute(
            f"SELECT count(*) FROM {key if key != 'link' else 'prof_paper_link'}"
            if key != "applicant" else
            "SELECT count(*) FROM applicant_binding"
        ).fetchone()[0]
        print(f"table {key}: loaded={counts[key]} durable={actual}")
    connection.close()


if __name__ == "__main__":
    sys.exit(main())
