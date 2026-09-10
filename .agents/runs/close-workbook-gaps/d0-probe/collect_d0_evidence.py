"""D0 diagnostic-gate evidence collector (close-workbook-gaps B3+B2).

Builds the per-entity loss-attribution evidence for four acceptance turns
(g2-t1, g2-t2, g5-t1, g5-t2 of the workbook test set) WITHOUT any network:

  stage 0  data ceiling      run14 serving-pack lookup.sqlite3 (read-only)
  stage 1  retrieval recall  production turn-trace journal lane counts
                             + production web-lane cache (web_lane.sqlite3)
                             resolved via view_cache_key = sha256(view)
  stage 2  displayed set     production journal session_snapshot
                             (displayed_id_count, active_anchor) + the t2
                             web-probe views that enumerate the carried set
                             verbatim
  stage 3  answer containment runner `_hit` semantics on the archived
                             results-diff-run14-20260910.json answers
  stage 4  naming            alias-form comparison between carried legal
                             names and the answer wording

Blind cells (documented, not guessed): the vector lane's per-entity membership
(embedding service is remote) and the supplemental lane's item contents.
The manual-recall sidecar store (/var/tmp/mirothinker-data-v2/manual-recall-v1)
is EMPTY on disk, so manual recall contributed zero candidates in production.

Read-only against every artifact. Output: d0-evidence.json next to this file.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

WORKTREE = Path(__file__).resolve().parents[4]
MAIN_REPO = Path("/home/longxiang/MiroThinker")
JOURNAL_DIR = WORKTREE / "var" / "turn-trace"
WEB_CACHE_DB = JOURNAL_DIR / "web_lane.sqlite3"
PACK_LOOKUP_DB = Path("/var/tmp/mirothinker-data-v2/serving-pack-run14-sealed/lookup.sqlite3")
ARCHIVE_JSON = (
    MAIN_REPO / ".agents/runs/testset-baseline-20260909/results-diff-run14-20260910.json"
)
ANCHORS_DIR = MAIN_REPO / ".agents/runs/testset-baseline-20260909"

sys.path.insert(0, str(ANCHORS_DIR))
from anchors import ANCHORS  # noqa: E402  (harness of record for GT terms)

QUERIES = {
    "g2-t1": "中国有哪些成熟的酒店送餐机器人供应商",
    "g2-t2": "上述企业里总部在深圳的企业有哪些",
    "g5-t1": "我想找PCB打板， 有哪些推荐",
    "g5-t2": "上述企业有哪些是深圳的企业",
}

# GT terms come from ANCHORS (identical semantics to the runner's `_hit`).
# Aliases widen evidence search only; stage-3 hits use the GT term itself.
ALIASES = {
    "普渡": ("普渡", "Pudu", "普渡科技", "普渡机器人"),
    "开普勒": ("开普勒", "Kepler"),
    "云迹": ("云迹",),
    "九号": ("九号", "Ninebot", "Segway", "纳恩博"),
    "擎朗": ("擎朗", "Keenon"),
    "安赛步": ("安赛步",),
    "小村": ("小村",),
    "中科世界": ("中科世界",),
    "艾唯尔": ("艾唯尔",),
    "锐曼": ("锐曼",),
    "嘉立创": ("嘉立创",),
    "华秋": ("华秋",),
    "中信华": ("中信华",),
    "领智": ("领智",),
    "兴森": ("兴森",),
    "深南电路": ("深南电路",),
    "顺易捷": ("顺易捷",),
    "一博": ("一博",),
    "则成": ("则成",),
    "上达": ("上达",),
    "精诚达": ("精诚达",),
}

TURN_ENTITIES = {
    "g2-t1": list(ANCHORS["g2-t1"]["entities"]) + list(ANCHORS["g2-t1"]["key_points"]),
    "g2-t2": list(ANCHORS["g2-t2"]["entities_pool"]),
    "g5-t1": list(ANCHORS["g5-t1"]["entities"]),
    "g5-t2": [k for k in ANCHORS["g5-t2"]["key_points"] if k != "广州"],
}
for key, terms in TURN_ENTITIES.items():
    TURN_ENTITIES[key] = list(dict.fromkeys(terms))


def view_cache_key(view: str) -> str:
    return hashlib.sha256(view.encode("utf-8")).hexdigest()


def load_journal() -> dict[str, list[dict]]:
    sessions: dict[str, list[dict]] = {}
    for day_file in sorted(JOURNAL_DIR.glob("2026-09-*.jsonl")):
        for line in day_file.read_text(encoding="utf-8").splitlines():
            try:
                trace = json.loads(line)
            except json.JSONDecodeError:
                continue
            sessions.setdefault(trace.get("session_id", "?"), []).append(trace)
    for turns in sessions.values():
        turns.sort(key=lambda t: t.get("turn_ordinal", 0))
    return sessions


def carried_names_from_views(turn: dict) -> list[str]:
    """Extract the quoted legal names from the carried-set web-probe views."""
    names: list[str] = []
    for outcome in turn.get("web_outcomes", []):
        view = outcome.get("view", "")
        names.extend(re.findall(r'"([^"]{4,60})"', view))
    return list(dict.fromkeys(names))


def term_in_text(term: str, text: str) -> bool:
    return term.casefold() in text.casefold()


def entity_in_text(entity: str, text: str) -> bool:
    return any(term_in_text(term, text) for term in ALIASES.get(entity, (entity,)))


def main() -> None:
    sessions = load_journal()
    archive = json.loads(ARCHIVE_JSON.read_text(encoding="utf-8"))
    archived_answers = {
        f"g{grp['group']}-t{turn['turn']}": turn
        for grp in archive
        for turn in grp["turns"]
    }

    # The live cache is WAL-mode and may be held by the running service; copy
    # db+wal+shm to scratch so the WAL contents are included, never mutating
    # the original files.
    scratch = Path(tempfile.mkdtemp(prefix="d0-webcache-"))
    scratch_db = scratch / "web_lane.sqlite3"
    for suffix in ("", "-wal", "-shm"):
        source = Path(f"{WEB_CACHE_DB}{suffix}")
        if source.exists():
            shutil.copyfile(source, scratch / f"web_lane.sqlite3{suffix}")
    cache = sqlite3.connect(scratch_db)
    lookup = sqlite3.connect(f"file:{PACK_LOOKUP_DB}?mode=ro", uri=True)

    # ---- identify sessions per acceptance turn -----------------------------
    candidates: dict[str, list[dict]] = {key: [] for key in QUERIES}
    for session_id, turns in sessions.items():
        for trace in turns:
            for key, query in QUERIES.items():
                if trace.get("query_raw", "").strip().rstrip("？?") == query.rstrip("？?"):
                    candidates[key].append(
                        {"session_id": session_id, "trace": trace}
                    )

    # A run14 g2 session is the one whose t2 probe views enumerate the
    # 12-company carried set matching the archived t1 answer; g5 run14 has
    # the 4-company carried set matching the archived t2 answer. Report ALL
    # candidate sessions so the identification is auditable.
    session_report: dict[str, dict] = {}
    for key, hits in candidates.items():
        for hit in hits:
            sid = hit["session_id"]
            entry = session_report.setdefault(
                sid,
                {
                    "session_id": sid,
                    "turns": {},
                    "carried_set_at_t2": [],
                },
            )
            for trace in sessions[sid]:
                ordinal = trace.get("turn_ordinal")
                entry["turns"][f"t{ordinal}"] = {
                    "query_raw": trace.get("query_raw"),
                    "ts_start": trace.get("ts_start"),
                    "lanes": trace.get("lanes"),
                    "gate_drops": trace.get("gate_drops"),
                    "session_snapshot": trace.get("session_snapshot"),
                    "answer_subject": trace.get("answer_subject"),
                    "degradation": trace.get("degradation"),
                    "status": trace.get("status"),
                    "web_views": [
                        {
                            "provider": o.get("provider"),
                            "view": o.get("view"),
                            "cache_hit": o.get("cache_hit"),
                            "attempted": o.get("attempted"),
                            "timed_out": o.get("timed_out"),
                        }
                        for o in trace.get("web_outcomes", [])
                    ],
                }
                if ordinal == 2 and not entry["carried_set_at_t2"]:
                    entry["carried_set_at_t2"] = carried_names_from_views(trace)

    # ---- per-turn entity attribution ---------------------------------------
    out: dict[str, dict] = {}
    for key, query in QUERIES.items():
        turn_hits = candidates[key]
        entity_rows = []
        for entity in TURN_ENTITIES[key]:
            row: dict[str, object] = {"entity": entity, "aliases": ALIASES.get(entity)}
            # stage 0: pack data ceiling — distinguish the entity's OWN
            # identity documents (term in name/normalized_name/aliases) from
            # incidental mentions (term elsewhere in some other document).
            identity_docs = []
            mention_docs = []
            seen_ids: set[str] = set()
            for term in ALIASES.get(entity, (entity,)):
                for doc_id, proj, doc_json in lookup.execute(
                    "SELECT canonical_object_id, projection_id, document_json "
                    "FROM lookup_document WHERE document_json LIKE ? LIMIT 40",
                    (f"%{term}%",),
                ):
                    if doc_id in seen_ids:
                        continue
                    seen_ids.add(doc_id)
                    record = {
                        "canonical_object_id": doc_id,
                        "projection_id": proj,
                        "matched_term": term,
                    }
                    try:
                        content = json.loads(json.loads(doc_json)["lookup_content"])
                    except (json.JSONDecodeError, TypeError, KeyError):
                        content = {}
                    name_fields = (
                        str(content.get("name") or ""),
                        str(content.get("normalized_name") or ""),
                        *(str(a) for a in (content.get("aliases") or [])),
                    )
                    if any(
                        term_in_text(t, field)
                        for t in ALIASES.get(entity, (entity,))
                        for field in name_fields
                        if field
                    ):
                        record["name"] = content.get("name")
                        record["registered_address"] = content.get(
                            "registered_address"
                        )
                        identity_docs.append(record)
                    else:
                        mention_docs.append(record)
            row["stage0_identity_documents"] = identity_docs
            row["stage0_mention_documents"] = mention_docs[:6]
            row["stage0_mention_count"] = len(mention_docs)
            row["stage0_in_pack"] = bool(identity_docs)

            # stage 1: production web-lane payloads for this turn's views
            per_session = []
            for hit in turn_hits:
                trace = hit["trace"]
                views = [o.get("view", "") for o in trace.get("web_outcomes", [])]
                day = trace.get("ts_start", "")[:10]
                web_hit_views = []
                views_checked = 0
                payloads_found = 0
                for view in dict.fromkeys(views):
                    if not view:
                        continue
                    views_checked += 1
                    key_hash = view_cache_key(view)
                    for provider in ("bocha-v1", "serper-v1"):
                        found = cache.execute(
                            "SELECT payload_json FROM web_cache "
                            "WHERE provider = ? AND view_key = ? AND day = ?",
                            (provider, key_hash, day),
                        ).fetchone()
                        if found and entity_in_text(entity, found[0]):
                            payloads_found += 1
                            web_hit_views.append({"provider": provider, "view": view})
                per_session.append(
                    {
                        "session_id": hit["session_id"],
                        "lanes": trace.get("lanes"),
                        "gate_drops": trace.get("gate_drops"),
                        "web_views_checked": views_checked,
                        "web_payloads_naming_entity": payloads_found,
                        "web_hit_views": web_hit_views[:8],
                    }
                )
            row["stage1_production"] = per_session

            # stage 2: displayed/carried set membership (from t2 probe views
            # of the same session for t1; from the turn's own answer for t2)
            carried_membership = []
            for hit in turn_hits:
                sid = hit["session_id"]
                carried = session_report.get(sid, {}).get("carried_set_at_t2", [])
                carried_membership.append(
                    {
                        "session_id": sid,
                        "carried_set_size": len(carried),
                        "entity_in_carried_set": any(
                            entity_in_text(entity, name) for name in carried
                        ),
                    }
                )
            row["stage2_carried_set"] = carried_membership

            # stage 3: archived answer containment (runner `_hit` semantics)
            archived = archived_answers.get(key) or {}
            answer_text = archived.get("answer_text") or ""
            row["stage3_answer_hit"] = term_in_text(entity, answer_text)
            row["stage3_answer_hit_alias"] = entity_in_text(entity, answer_text)
            entity_rows.append(row)

        out[key] = {
            "query": query,
            "archived_scored": (archived_answers.get(key) or {}).get("scored"),
            "entities": entity_rows,
        }

    result = {
        "journal_dir": str(JOURNAL_DIR),
        "web_cache_db": str(WEB_CACHE_DB),
        "pack_lookup_db": str(PACK_LOOKUP_DB),
        "archive": str(ARCHIVE_JSON),
        "sessions": session_report,
        "turns": out,
    }
    out_path = Path(__file__).parent / "d0-evidence.json"
    out_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"evidence -> {out_path}")

    # ---- stdout summary -----------------------------------------------------
    print("\n=== candidate sessions ===")
    for sid, entry in sorted(
        session_report.items(), key=lambda kv: kv[1]["turns"].get("t1", {}).get("ts_start") or ""
    ):
        t1 = entry["turns"].get("t1", {})
        print(
            f"{sid[:44]:<46} t1={str(t1.get('query_raw'))[:24]:<26} "
            f"carried@t2={len(entry['carried_set_at_t2'])} "
            f"{entry['carried_set_at_t2'][:6]}"
        )
    print("\n=== per-turn entity table ===")
    for key, block in out.items():
        print(f"\n--- {key}: {block['query']}")
        for row in block["entities"]:
            s0_docs = row["stage0_identity_documents"]
            s0 = "pack✓" if row["stage0_in_pack"] else (
                "pack~mention" if row["stage0_mention_count"] else "pack✗"
            )
            s1 = []
            for ps in row["stage1_production"]:
                web = ps["web_payloads_naming_entity"]
                s1.append(f"web:{web}")
            s2 = [("carried✓" if c["entity_in_carried_set"] else "carried✗") for c in row["stage2_carried_set"]]
            s3 = "ans✓" if row["stage3_answer_hit"] else ("ans~alias" if row["stage3_answer_hit_alias"] else "ans✗")
            names = sorted({str(x.get("name")) for x in s0_docs if x.get("name")})
            print(f"  {row['entity']:<6} {s0:<7} {'/'.join(s1):<10} {'/'.join(s2):<18} {s3:<10} {names[:2]}")

    # ---- run14-pinned verdict table -----------------------------------------
    # Session pinning: archived elapsed g2-t1=41.9s matches JgjH... t1
    # (11:11:16.254 -> 11:11:58.168 = 41.91s); g5-t2=11.7s matches -YZX... t2
    # (11:14:26.253 -> 11:14:37.905 = 11.65s). The 12-company g2 carried set
    # and the 4-company g5 carried set match the archived answers verbatim.
    run14_sessions = {
        "g2": "session:chat:JgjH8u4MaHqeIQOTbZuUr4mY20cMC4nF",
        "g5": "session:chat:-YZXc4pO5OHEHdpQtuyKW7XEXtVHYiZc",
    }
    print("\n=== run14-pinned verdict (per entity, furthest stage) ===")
    for key, block in out.items():
        sid = run14_sessions[key[:2]]
        print(f"\n--- {key}: {block['query']}  [session {sid[-12:]}]")
        for row in block["entities"]:
            s1 = next(
                (p for p in row["stage1_production"] if p["session_id"] == sid),
                None,
            )
            s2 = next(
                (c for c in row["stage2_carried_set"] if c["session_id"] == sid),
                None,
            )
            in_pack = row["stage0_in_pack"]
            web_n = s1["web_payloads_naming_entity"] if s1 else 0
            carried = s2["entity_in_carried_set"] if s2 else None
            ans = row["stage3_answer_hit"]
            ans_alias = row["stage3_answer_hit_alias"]
            if not in_pack:
                verdict = (
                    "0-not-in-pack"
                    if not row["stage0_mention_count"]
                    else "0-not-in-pack (mention-only)"
                )
            elif web_n == 0 and not carried:
                verdict = "1-not-web-recalled (vector/supplemental blind)"
            elif not carried:
                verdict = "2-web-recalled, NOT in carried/displayed set"
            elif not ans and not ans_alias:
                verdict = "3-carried but NOT in answer"
            elif not ans and ans_alias:
                verdict = "4-answer mentions alias only (GT term miss)"
            else:
                verdict = "present-in-answer"
            print(
                f"  {row['entity']:<6} pack={'Y' if in_pack else 'N':<2} "
                f"web_payloads={web_n:<3} carried={carried!s:<6} "
                f"ans={row['stage3_answer_hit']!s:<6} -> {verdict}"
            )


if __name__ == "__main__":
    main()
