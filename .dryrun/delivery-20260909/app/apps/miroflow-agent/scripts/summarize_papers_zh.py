"""LLM-summarize papers (needs_enrichment/partial) into Chinese `summary_zh`.

Generates a 3-5 sentence Chinese summary covering contribution / method / key
findings from each paper's `title_clean` + `abstract_clean` via the Anthropic SDK
through the zenmux proxy, then UPDATEs `paper.summary_zh` in Postgres.

Scope: ONLY writes `summary_zh`. Does NOT touch `quality_status` (a separate
`reassess_quality` step promotes to ready) and does NOT touch Milvus (a separate
embed step handles that, with backend coordination).

Env (set by the caller, e.g. by sourcing the running backend's /proc/<pid>/environ):
  DATABASE_URL              postgresql://miroflow:miroflow@localhost:15432/miroflow_real
  ANTHROPIC_BASE_URL        https://zenmux.ai/api/anthropic
  ANTHROPIC_AUTH_TOKEN      <token>

Proxy vars (http_proxy/https_proxy/...) MUST be unset by the caller or localhost
DB connections get hijacked.

Usage:
  # Real run (idempotent: skips papers that already have summary_zh)
  uv run python apps/miroflow-agent/scripts/summarize_papers_zh.py

  # Generate + print only, NO DB writes (proves the LLM pipeline)
  uv run python apps/miroflow-agent/scripts/summarize_papers_zh.py --dry-run

  # Regenerate even for papers that already have summary_zh
  uv run python apps/miroflow-agent/scripts/summarize_papers_zh.py --overwrite
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any

import psycopg
import anthropic
from psycopg.rows import dict_row

_REPO_ROOT = Path(__file__).resolve().parents[1]
try:
    from dotenv import load_dotenv

    load_dotenv(_REPO_ROOT / ".env")
except Exception:  # pragma: no cover - dotenv optional
    pass

DEFAULT_TOPIC_REGEX = "具身智能|灵巧手|embodied|dexterous|humanoid|具身|灵巧"
DEFAULT_STATUSES = ("needs_enrichment", "partial")
DEFAULT_MODEL = "claude-haiku-4-5"  # verified working on the zenmux proxy
PROMPT_TEMPLATE = (
    "用中文写3-5句论文摘要,覆盖贡献/方法/关键发现。只返回摘要正文,不要其他文字。\n\n"
    "标题: {title}\n摘要: {abstract}"
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    p.add_argument("--database-url", default=None, help="Postgres URL; defaults to $DATABASE_URL.")
    p.add_argument("--anthropic-base-url", default=None, help="Defaults to $ANTHROPIC_BASE_URL.")
    p.add_argument("--anthropic-auth-token", default=None, help="Defaults to $ANTHROPIC_AUTH_TOKEN.")
    p.add_argument("--model", default=DEFAULT_MODEL, help=f"LLM model id (default {DEFAULT_MODEL}).")
    p.add_argument("--topic-regex", default=DEFAULT_TOPIC_REGEX, help="title_clean regex filter.")
    p.add_argument(
        "--statuses",
        default=",".join(DEFAULT_STATUSES),
        help="Comma-separated paper.quality_status filter.",
    )
    p.add_argument("--dry-run", action="store_true", help="Generate + print, but do NOT write to DB.")
    p.add_argument("--overwrite", action="store_true", help="Regenerate even if summary_zh already exists.")
    p.add_argument("--sleep", type=float, default=0.2, help="Seconds between LLM calls (default 0.2).")
    p.add_argument("--max-consecutive-failures", type=int, default=3, help="Stop after N consecutive LLM failures.")
    p.add_argument("--batch-size", type=int, default=5, help="Commit every N writes (default 5).")
    p.add_argument("--max-tokens", type=int, default=300, help="LLM max_tokens (default 300).")
    p.add_argument("--timeout", type=float, default=30.0, help="LLM per-call timeout seconds (default 30).")
    return p.parse_args(argv)


def _require_env(name: str, value: str | None) -> str:
    if not value:
        env = os.environ.get(name)
        if not env:
            raise SystemExit(f"ERROR: {name} not set. Export it before running (see module docstring).")
        return env
    return value


def _query_papers(conn, *, topic_regex: str, statuses: tuple[str, ...]) -> list[dict[str, Any]]:
    sql = """
        SELECT p.paper_id, p.title_clean, p.abstract_clean, p.summary_zh, p.quality_status
        FROM paper p
        JOIN professor_paper_link ppl ON ppl.paper_id = p.paper_id
        JOIN professor pr ON pr.professor_id = ppl.professor_id
        WHERE p.title_clean ~* %s
          AND pr.identity_status = 'resolved' AND pr.lifecycle_state = 'active'
          AND p.identity_status != 'rejected'
          AND p.quality_status = ANY(%s)
        GROUP BY p.paper_id, p.title_clean, p.abstract_clean, p.summary_zh, p.quality_status
        ORDER BY p.paper_id
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, (topic_regex, list(statuses)))
        return list(cur.fetchall())


def _summarize(client: anthropic.Anthropic, *, title: str, abstract: str, model: str,
               max_tokens: int, timeout: float) -> str:
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        timeout=timeout,
        messages=[{"role": "user", "content": PROMPT_TEMPLATE.format(title=title, abstract=abstract)}],
    )
    return resp.content[0].text.strip()


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    database_url = args.database_url or os.environ.get("DATABASE_URL")
    base_url = _require_env("ANTHROPIC_BASE_URL", args.anthropic_base_url)
    auth_token = _require_env("ANTHROPIC_AUTH_TOKEN", args.anthropic_auth_token)
    statuses = tuple(s.strip() for s in args.statuses.split(",") if s.strip())

    client = anthropic.Anthropic(base_url=base_url, auth_token=auth_token)
    conn = psycopg.connect(database_url, row_factory=dict_row)
    pending_writes = 0  # uncommitted writes in the current batch

    stats = {
        "queried": 0,
        "written": 0,
        "skipped_no_abstract": 0,
        "skipped_has_summary": 0,
        "failed": 0,
    }
    skipped_no_abstract: list[str] = []
    skipped_has_summary: list[str] = []
    failures: list[dict[str, str]] = []
    sample: dict[str, str] | None = None
    consecutive_failures = 0
    aborted_consecutive = False

    try:
        rows = _query_papers(conn, topic_regex=args.topic_regex, statuses=statuses)
        stats["queried"] = len(rows)

        for row in rows:
            paper_id = row["paper_id"]
            title = row["title_clean"] or ""
            abstract = row["abstract_clean"] or ""
            existing_summary = row["summary_zh"] or ""

            if not abstract.strip():
                stats["skipped_no_abstract"] += 1
                skipped_no_abstract.append(paper_id)
                continue
            if existing_summary.strip() and not args.overwrite:
                stats["skipped_has_summary"] += 1
                skipped_has_summary.append(paper_id)
                continue

            try:
                summary_zh = _summarize(
                    client, title=title, abstract=abstract, model=args.model,
                    max_tokens=args.max_tokens, timeout=args.timeout,
                )
            except Exception as exc:  # noqa: BLE001 - log + continue per spec
                stats["failed"] += 1
                failures.append({"paper_id": paper_id, "error": f"{type(exc).__name__}: {exc}"})
                consecutive_failures += 1
                if consecutive_failures >= args.max_consecutive_failures:
                    aborted_consecutive = True
                    break
                continue

            consecutive_failures = 0
            print(f"[OK] {paper_id} :: {title[:70]}")
            print(f"     summary_zh: {summary_zh[:120]}{'...' if len(summary_zh) > 120 else ''}")
            if sample is None:
                sample = {"paper_id": paper_id, "title": title, "summary_zh": summary_zh}

            if args.dry_run:
                continue

            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE paper SET summary_zh = %s WHERE paper_id = %s",
                    (summary_zh, paper_id),
                )
            stats["written"] += 1
            pending_writes += 1
            if pending_writes >= args.batch_size:
                conn.commit()
                pending_writes = 0

            if args.sleep > 0:
                time.sleep(args.sleep)

        # commit any remaining writes
        if pending_writes > 0 and not args.dry_run:
            conn.commit()
            pending_writes = 0
    finally:
        try:
            conn.close()
        except Exception:
            pass

    print("\n" + "=" * 70)
    print("REPORT")
    print("=" * 70)
    print(f"model:                   {args.model}")
    print(f"dry_run:                 {args.dry_run}")
    print(f"overwrite:               {args.overwrite}")
    print(f"queried:                 {stats['queried']}")
    print(f"summarized + written:    {stats['written']}")
    print(f"skipped (no abstract):   {stats['skipped_no_abstract']}")
    print(f"skipped (has summary):   {stats['skipped_has_summary']}")
    print(f"failed (LLM):           {stats['failed']}")
    if aborted_consecutive:
        print(f"ABORTED: {args.max_consecutive_failures} consecutive LLM failures -> stop.")
    if skipped_no_abstract:
        print(f"\npaper_ids with NULL/empty abstract_clean ({len(skipped_no_abstract)}):")
        for pid in skipped_no_abstract:
            print(f"  {pid}")
    if skipped_has_summary:
        print(f"\npaper_ids that already had summary_zh ({len(skipped_has_summary)}):")
        for pid in skipped_has_summary:
            print(f"  {pid}")
    if failures:
        print(f"\nLLM failures ({len(failures)}):")
        for f in failures:
            print(f"  {f['paper_id']}: {f['error']}")
    if sample:
        print("\nSAMPLE (freshly generated):")
        print(f"  paper_id: {sample['paper_id']}")
        print(f"  title:    {sample['title']}")
        print(f"  summary_zh:")
        for line in sample["summary_zh"].splitlines():
            print(f"    {line}")
    return 0 if not aborted_consecutive else 2


if __name__ == "__main__":
    raise SystemExit(main())
