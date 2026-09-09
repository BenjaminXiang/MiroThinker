# Slice — Professor Layer C: topic-paper-count fusion

- **State:** Accepted (2026-07-08) — Codex implemented → Claude live-E2E found a wiring bug
  (re-rank was before the paper-rescue, so rescued profs like 潘挺睿 were missed) → Claude moved
  the re-rank to AFTER the rescue → live-E2E GREEN. Doc-as-contract (OpenSpec absent on this
  branch); ADR-010 + this slice + verification-contract = the contract.
- **Decision record:** `docs/architecture-decisions/ADR-010-professor-layer-c-topic-paper-count-fusion.md`
- **Scope:** all professor-topic queries (`_lookup_professors_by_topic`, B-type professor topic).
  视触觉 is the validating case; generalizes to 灵巧手 / 具身智能 / etc. — consistent with the
  company slice (ADR-009).
- **Non-goals:** company topic (done, ADR-009), patent path, Milvus re-index, synthesis/kill-dump
  changes (stays as backstop), `professor_fact.research_topic` backfill.
- **Owner:** Codex implements; Claude reviews.

## Problem (one line)

Professor topic retrieval buries the gold (潘挺睿 #7) behind false positives (0 topic papers) because
the one clean precision signal — topic-paper-count — is structurally suppressed
(`len(rows) < limit` gate at chat.py:2258; 清华深研院 recall is always thick).

## Changes (all in `apps/admin-console/backend/api/chat.py` unless noted)

### 1. Topic-term extraction for paper-title match (NEW helper)
Build the topic-terms used for the paper-title ILIKE: the core topic term(s) from the query
(stripped of stopwords: 做/的/教授/有哪些/清华/深圳/大学/学院/…) PLUS English equivalents.
Provide a small map: 视触觉→[触觉,视触,haptic,tactile,visuotactile]; 灵巧手→[灵巧手,dexterous];
具身智能→[具身智能,embodied]; 机器人→[robot,robotic]; etc. Fall back to the raw topic token if no
map entry. Reuse existing term-extraction patterns where possible (do NOT reuse the company
`_company_topic_term_groups` generic-AI expansion — that was the company bug).

### 2. Per-prof topic-paper-count (NEW helper)
`_professor_topic_paper_counts(conn, professor_ids: list[str], topic_terms: list[str]) -> dict[str,int]`:
one SQL query —
`SELECT pl.professor_id, count(*) FROM professor_paper_link pl JOIN paper p ON p.paper_id=pl.paper_id
 WHERE pl.professor_id = ANY(%s) AND pl.link_status='verified'
   AND (p.title_clean ILIKE ANY(%s) OR p.title_raw ILIKE ANY(%s))
 GROUP BY pl.professor_id`.
Return {professor_id: count} (0 for profs with no match). Note: link_status is `'verified'`
(NOT 'active' — that was a stale assumption; the table has verified/rejected only).

### 3. Re-rank in `_lookup_professors_by_topic` — AFTER the paper-rescue (critical wiring)
Compute topic-paper-counts and **re-rank by `(topic_paper_count DESC, original_vector_rank ASC)`**,
demote-not-drop 0-count profs. **The re-rank MUST run AFTER the paper-rescue block**, not before
it. Reason (found in live E2E): for thin-recall topics (e.g. 视触觉 at 清华深研院 — vector returns
only ~6 profs, all false-positives with 0 topic papers), the gold (潘挺睿, 4 视触觉 papers) enters
via the paper→professor rescue, which appends rescued profs to `rows`. A re-rank wired BEFORE the
rescue never sees 潘挺睿 → he stays at #7. Wired AFTER the rescue, the re-rank covers the full set
(vector + rescued) and lifts 潘挺睿 to #1. Audit-logged at INFO (`professor_topic_rerank`).

## Verification contract (behavior-affecting → eval-first, not unit-only)

- **RED (today, confirmed):** live POST "清华做视触觉的教授有哪些" → `matched_professors` has
  潘挺睿 at rank 7, false positives (黎维彬/Tsuboi/訾牧聪) at ranks 1-3.
- **GREEN (Claude live):**
  1. 视触觉 POST → 潘挺睿 **#1** in `matched_professors`; 黎维彬/Tsuboi/訾牧聪 demoted to the tail.
  2. 灵巧手 POST + 具身智能教授 POST → non-regression (count-primary sort doesn't break them;
     gold/legit profs surface, no crash).
  3. Synthesis answer still features the gold (backstop intact).
- **Codex (unit, no network):** unit-test the topic-term extraction (视触觉→terms incl. haptic/tactile;
  stopword stripping) and the re-rank (a 3-prof list where the gold has fewer vector-points but
  more topic-papers → gold surfaces #1; 0-count profs demoted not dropped; empty topic-terms →
  no re-rank / graceful). ruff + pyright on touched code.

## Notes for Codex

- `professor_paper_link.link_status` values are `verified` / `rejected` — use `'verified'`.
- Reuse the existing DB connection (`conn`) — this is SQL, no Milvus, no new service.
- Do NOT touch company retrieval, the patent path, Milvus, schemas, migrations, or synthesis.
- `profile_summary` / `profile_raw_text` are NOT needed for this slice (paper titles suffice).
- The `[:100]` synthesis truncation hardening is a SEPARATE follow-up — out of scope here.
- For localhost commands, unset the 6 proxy vars first or loopback is hijacked.

## Verification outcome (2026-07-08) — GREEN (Accepted, after Claude wiring fix)

Live E2E: `POST /api/chat {"query":"清华做视触觉的教授有哪些"}` against a backend restarted with
the new code. `matched_professors` order:
1. 潘挺睿 (4 视触觉 papers) — **was #7, now #1**
2. 王晓浩 · 3. 张盛 · 4. 聂晓梅 · 5. 丁文伯
6. 黎维彬 · 7. Tsuboi · 8. 訾牧聪 (0 papers — demoted to the tail)

Answer features 潘挺睿 first [1]; false positives absent from the answer. Non-清华 high-count
profs (邵奕天 7, 张明明 8 — legit 触觉传感 profs at other institutions) correctly excluded by the
institution filter for this 清华-scoped query.

Audit log confirms: `professor_topic_rerank topic='视触觉' rows=19 nonzero={潘挺睿:4, ...}` —
the re-rank now sees the full set (vector + rescued) and lifts the gold.

灵巧手 / 具身智能 professor-topic: non-regression (10 profs each, no crash; count-primary sort
generalizes). Unit: `test_chat_professor_topic_layer_c.py` 3 pass; ruff clean; pyright clean on
the slice. (2 pre-existing `test_chat_retrieval.py` failures at HEAD — unrelated, fail at
1207cf3 too.)
