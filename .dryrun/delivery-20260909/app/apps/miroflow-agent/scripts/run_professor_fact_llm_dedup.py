#!/usr/bin/env python
"""LLM-assisted semantic dedup for professors with anomalous fact counts.

Targets professors with >= N active education facts (default 6) — the residual
that rule-based dedup could not safely resolve (prose<->structured, year-range
vs completion-year, romanization variants, bilingual flips the rules missed).
For each professor and each structured fact_type, asks the LLM to group facts
that describe the SAME logical entry and pick the most complete to keep; the
rest are superseded.

Conservative by design:
  - dry-run default; --apply writes.
  - the LLM is instructed to ONLY merge CLEARLY-same entries (same school/org,
    same degree/role level, same field, same/overlapping period) and to NEVER
    merge different periods or fields.
  - every supersede is archived to JSONL (reversible).
  - garbage (mis-categorized) facts are REPORTED only, never auto-removed.

Env: SUSTech gemma4 endpoint is reached directly; localhost DB is TCP. Unset
the 6 proxy env vars before running.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

import psycopg
from openai import OpenAI

from src.data_agents.professor.llm_profiles import resolve_professor_llm_settings
from src.data_agents.professor.fact_dedup_key import llm_merge_is_safe

STRUCTURED_TYPES = ("education", "work_experience")

_PROMPT = """你是数据清洗助手。下面是某教授的{fact_type_zh}事实列表(从主页抽取,格式不一:可能是 "学校 | 学位 | 领域 | 年份" 管道式、JSON、双语散文、中文散文)。

其中有些是【重复】:同一条经历以不同形式出现(如管道式与JSON、中文与双语、年份范围与结业年)。有些可能是【噪声】(不是真实的{fact_type_zh},例如把导师/学生记录、论文标题、获奖误当{fact_type_zh})。

请把描述【同一条】{fact_type_zh}的事实归为一组,并选出最完整的一条保留(优先级:带年份的管道式 > JSON > 双语散文 > 中文散文)。

【严格规则】:
- 只把"明显是同一条"的归组:同一学校/机构 + 同一学位/职位级别 + 同一领域 + 相同或可重合的时段。
- 时段不同(如 2018-2019 与 2019-2020)绝不归组,除非其中一方没有年份。
- 领域不同(如 经济学 与 环境工程)绝不归组。
- 不确定时,保持独立,不要归组。
- 学位同义词视为同一级别:Ph.D./Doctor/博士、Master/硕士、Bachelor/学士、Postdoc/博士后。
- 噪声事实不要归组,放到 "garbage" 里(仅标注,不删除)。

只输出 JSON,不要解释:
{{"groups":[{{"keep":<保留的编号>,"supersede":[<要下线的编号>,...],"reason":"<为何是同一条,简短>"}}],"garbage":[{{"id":<编号>,"reason":"<为何是噪声>"}}]}}

{fact_type_zh}事实:
{facts_block}
"""

_FACT_TYPE_ZH = {"education": "教育经历", "work_experience": "工作经历"}


def _gather_target_professors(cur, min_facts: int, limit: int | None) -> list[str]:
    cur.execute(
        """
        SELECT professor_id FROM (
            SELECT professor_id, count(*) c
            FROM professor_fact
            WHERE fact_type = 'education' AND status = 'active'
            GROUP BY professor_id HAVING count(*) >= %s
        ) t ORDER BY c DESC
        """,
        (min_facts,),
    )
    pids = [r[0] for r in cur.fetchall()]
    if limit:
        pids = pids[:limit]
    return pids


def _load_active_facts(cur, professor_id: str, fact_type: str) -> list[tuple[str, str]]:
    cur.execute(
        "SELECT fact_id, value_raw FROM professor_fact "
        "WHERE professor_id=%s AND fact_type=%s AND status='active' "
        "ORDER BY length(value_raw) DESC",
        (professor_id, fact_type),
    )
    return [(str(r[0]), str(r[1] or "")) for r in cur.fetchall()]


def _ask_llm(client: OpenAI, model: str, fact_type: str, facts: list[tuple[str, str]]) -> dict | None:
    zh = _FACT_TYPE_ZH.get(fact_type, fact_type)
    block = "\n".join(f"[{i}] {v[:300]}" for i, (_, v) in enumerate(facts))
    prompt = _PROMPT.format(fact_type_zh=zh, facts_block=block)
    for attempt in range(3):
        try:
            r = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000,
                temperature=0.1,
            )
            content = (r.choices[0].message.content or "").strip()
            content = content[content.find("{"): content.rfind("}") + 1]
            return json.loads(content)
        except Exception as exc:  # noqa: BLE001
            if attempt == 2:
                print(f"    LLM parse failed ({fact_type}): {exc}", file=sys.stderr)
                return None
            time.sleep(1.0)
    return None


def _process_professor(conn, client, model, professor_id: str, apply: bool, archive) -> dict:
    stats = {"groups": 0, "supersede": 0, "rejected": 0, "garbage": 0, "skipped_types": 0}
    with conn.cursor() as cur:
        for fact_type in STRUCTURED_TYPES:
            facts = _load_active_facts(cur, professor_id, fact_type)
            if len(facts) < 2:
                stats["skipped_types"] += 1
                continue
            result = _ask_llm(client, model, fact_type, facts)
            if not result:
                continue
            id_by_idx = {i: fid for i, (fid, _) in enumerate(facts)}
            val_by_id = {fid: v for fid, v in facts}
            groups = result.get("groups") or []
            garbage = result.get("garbage") or []
            for g in groups:
                sup_ids = g.get("supersede") or []
                if not sup_ids:
                    continue
                keep_idx = g.get("keep")
                keep_id = id_by_idx.get(keep_idx) if keep_idx is not None else None
                keep_val = val_by_id.get(keep_id or "")
                sup_fids = [id_by_idx[i] for i in sup_ids if i in id_by_idx and id_by_idx[i] != keep_id]
                if not sup_fids:
                    continue
                stats["groups"] += 1
                for fid in sup_fids:
                    sup_val = val_by_id.get(fid, "")
                    # Safety filter: only apply merges the conservative key
                    # confirms (same degree/role level when both present, same
                    # period, shared org token). Rejects LLM false-positives
                    # (PhD vs Master, different periods, different schools).
                    safe = bool(keep_val) and llm_merge_is_safe(fact_type, keep_val, sup_val)
                    archive.write(json.dumps({
                        "professor_id": professor_id, "fact_type": fact_type,
                        "reason": "llm_semantic_dedup_confirmed" if safe else "llm_merge_rejected",
                        "group_reason": g.get("reason", ""),
                        "fact_id_superseded": fid, "value_raw_superseded": sup_val,
                        "fact_id_kept": keep_id, "value_raw_kept": keep_val,
                    }, ensure_ascii=False) + "\n")
                    if safe:
                        stats["supersede"] += 1
                        if apply:
                            cur.execute(
                                "UPDATE professor_fact SET status='superseded', updated_at=now() "
                                "WHERE fact_id=%s::uuid AND status='active'",
                                (fid,),
                            )
                    else:
                        stats["rejected"] += 1
            stats["garbage"] += len(garbage)
            if garbage:
                archive.write(json.dumps({
                    "professor_id": professor_id, "fact_type": fact_type,
                    "reason": "llm_garbage_flag", "garbage": [
                        {"fact_id": id_by_idx.get(g2.get("id")), "value_raw": val_by_id.get(id_by_idx.get(g2.get("id")), ""), "why": g2.get("reason", "")}
                        for g2 in garbage if g2.get("id") in id_by_idx
                    ],
                }, ensure_ascii=False) + "\n")
        if apply:
            conn.commit()
    return stats


def main() -> int:
    p = argparse.ArgumentParser(description="LLM-assisted professor_fact semantic dedup.")
    p.add_argument("--dsn", default=os.environ.get("DATABASE_URL"))
    p.add_argument("--llm-profile", default="gemma4")
    p.add_argument("--min-facts", type=int, default=6)
    p.add_argument("--limit", type=int, default=None, help="cap professors (default all).")
    p.add_argument("--apply", action="store_true", help="write (default: dry-run).")
    p.add_argument("--sleep", type=float, default=1.5)
    args = p.parse_args()
    if not args.dsn:
        raise SystemExit("DATABASE_URL or --dsn required")
    if "+psycopg" in args.dsn:
        args.dsn = args.dsn.replace("postgresql+psycopg://", "postgresql://")

    settings = resolve_professor_llm_settings(args.llm_profile)
    client = OpenAI(
        base_url=settings["local_llm_base_url"],
        api_key=settings.get("local_llm_api_key") or "EMPTY",
        timeout=90.0,
    )
    model = settings["local_llm_model"]

    conn = psycopg.connect(args.dsn)
    with conn.cursor() as cur:
        pids = _gather_target_professors(cur, args.min_facts, args.limit)
    mode = "APPLY" if args.apply else "DRY-RUN"
    archive_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "..", ".agents", "runs", "professor-fact-llm-dedup",
        f"{'apply' if args.apply else 'dryrun'}-2026-06-23.jsonl",
    )
    os.makedirs(os.path.dirname(archive_path), exist_ok=True)
    print(f"{mode} | {len(pids)} professors | model={model} | archive={archive_path}")

    totals = {"groups": 0, "supersede": 0, "rejected": 0, "garbage": 0}
    with open(archive_path, "w", encoding="utf-8") as archive:
        for n, pid in enumerate(pids, 1):
            try:
                s = _process_professor(conn, client, model, pid, args.apply, archive)
            except Exception as exc:  # noqa: BLE001
                print(f"[{n}/{len(pids)}] {pid} ERROR: {exc}", file=sys.stderr)
                conn.rollback()
                continue
            for k in totals:
                totals[k] += s[k]
            if s["supersede"] or s["rejected"] or s["garbage"]:
                print(f"[{n}/{len(pids)}] {pid}: {s['supersede']} supersede, {s['rejected']} rejected, {s['garbage']} garbage, {s['groups']} groups")
            time.sleep(args.sleep)
    print(f"\n{mode} done. totals: {totals}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
