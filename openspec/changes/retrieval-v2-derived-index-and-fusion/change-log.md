# Change log: retrieval-v2-derived-index-and-fusion

## 2026-09-12/13 — Step 0 + Step 1 landed, then the lane was switched off (evidence-driven)

### Step 0 (contract + baseline)

- `verification-contract.md` written before production edits: four oracle
  classes (replay gate, generalization P2, workbook testset, offline harness),
  frozen baselines (TTFT r4, lane walls, P2 counts, testset g2/g5, replay
  `replay-post-lat3`), RED→GREEN per step. Ledger entry added.

### Step 1 (derived lexical index)

Landed commits (serving worktree `codex/canonical-v2-s12a-ready`):
`5046642f` module + build script, `0a651254` pack adapter wiring, `e36cc47d`
single selection + retryable open cache + lockfile entry, `876662cd`
content-residue index query + wide/narrow fill policy + boot warm, `6bf65741`
warm moved to the pack path.

Artifact: `/var/tmp/mirothinker-data-v2/derived/lexical/candidate-v2-20260819-r1/`
(47,071 documents, 94.2 MB, build 70s), manifest bound to the serving pack's
`lookup.sqlite3` sha256 + size + mtime. Built against `index-v1` — the first
artifact was built from the sealed pack directory and silently fell back at
load (stat mismatch); see `step1-measurements.md` "Correction".

Speed (measured, real artifact): lane-internal select+build 0.056 / 0.607 /
0.710 s for lidar / g2 / pcb-1 in the harness (substring lane same turns:
1.13 / 2.46 / 3.71 s). Zero lane fallbacks. One-time open 5.7 s, now warmed
off the request path.

### Why the lane is OFF by default (deviation from the original Step 1 exit)

With the lane serving, the strongest oracle failed:

- **Replay gate 3 failures** (baseline ALL PASS): `G3_person_pronoun` T2
  (他有哪些论文 — the lane filled the window with 128 unrelated papers where
  the substring lane returned 0, and the answer lost its person scope) and
  `G7_enumeration` 2 of 3 repeats (深圳有哪些做具身智能的公司 — the required
  company 优必选 missing; the F1 path matches it through the 智能 bigram, an
  exact-token index pass does not).
- **Testset g2 2/3** (`entity` layer missing 开普勒/九号 — exactly the ids
  that dropped out of the index window in the harness id-level diff) and
  **g5 1/2** (completeness 4/12).
- Attribution chain closed: the harness window diff (substring vs index) and
  the live answer's off-category company names match one-for-one
  (心鉴智控/超联讯/骏之源/兰星/门庭/德龙艺彩).

Root cause (structural, recorded in design.md): the F1 category recall is a
tuned semantic (bigram term matching, field tiers 8/4/2/1, min-score gate,
displayed-entity constraints). Replacing it with tokenisation + BM25 +
a 128 window substitutes a different semantic — narrower in one direction
(exact tokens miss 智能-only documents), wider in the other (generic terms
flood the window), and BM25 truncation drops tier-tagged companies. The index
must be a *candidate generator for a relevance reranker*, not a recall
substitute.

TTFT did not move (23.6/14.1/20.8/16.8/16.4/14.3/9.8 vs baseline
24.4/14.6/19.8/15.6/17.5/15.4/11.1 s): the lane is not on the critical path —
web (6.9-11.2 s) and vector (3.2-5.4 s) are.

Action taken: the deployed unit pins `CANONICAL_V2_LEXICAL_INDEX=0` (systemd
drop-in `lexical-index.conf`), restoring baseline behaviour byte-for-byte;
the artifact and the switch stay in place for Step 1b.

### Verification performed this slice

- Unit/contract: `test_lexical_index.py` 16 green (segmentation matrix, field
  weights, phrase-vs-OR correction, manifest/pack refusal, open-cache
  semantics, residue stripping, wide/narrow policy); `test_serving_pack_loader`
  + `test_fast_boot` 36 green; `test_knowledge_read_isolated` 48 green.
- Offline harness rounds on the real pack: `harness-lexical-v2` (substring
  baseline), `v2c` (fallback), `v2e` (raw-question fill — the regression),
  `v2f` (content residue — lane cost + window composition).
- Live: generalization probe (raw fill 15 off-category lidar → residue 10,
  storage 0), testset g2/g5 (failing with the lane on), replay gate (failing),
  TTFT probe (unchanged). All artifacts under
  `.agents/runs/retrieval-v2-derived-index-and-fusion/`.

### Owner-decided refinements to the plan (2026-09-13)

The user's directive: zvec-grep's mechanisms stay in scope, but every step
must prove quality non-regression, and the rerank model must be used properly.
Step 1b therefore is: index generates a wide candidate pool (2-4x the window,
cap ~512) → embedding-model rerank (Qwen3-Embedding-8B, the vector lane's
model; reuse the pack's persisted vectors where the document→point mapping
allows it) → window. The current `_serving_reranker` is a deterministic
bucket-sort (all local candidates carry `raw_score=1.0`) and is the object to
replace. A category query's index window must be a *superset* of the substring
lane's recall (offline id-level proof) or the query falls through. Default-on
requires all four oracles (replay, testset, P2, harness cost/superset) to pass.

## 2026-09-13 — Step 1b(a) live differential: replay clean, quality gate REJECTED, lane stays OFF

### What was switched on (verified, not asserted)

`switch_rerank.sh on` → 01:38:51 restart, READY 01:50:51. Live env: base URL
`http://100.64.0.27:18006`, model `qwen3-reranker-8b`, credential only via the
0600 key file, timeout 3 s, document cap 128, debug on.
`CANONICAL_V2_LEXICAL_INDEX=0` for the whole batch, so this differential
isolates the rerank change (the index lane stays off).

ON is not a phantom switch: the endpoint's own vLLM request counter advanced by
exactly the cap per live turn — 2129516 → 2129644 after the 具身智能 turn →
2129772 after the PCB turn (128 each). The model really received the
candidates.

### Replay gate — no new signatures (3 runs, same pack, same day)

| run | rerank | failing sessions |
|---|---|---|
| `replay-off-20260913` | OFF | `G3_person_pronoun`, `G4_patents` |
| `replay-off-20260913-r2` | OFF | `G3_person_pronoun`, `G7_enumeration` |
| `replay-on-20260913` | ON | `G3_person_pronoun` |

ON is the best of the three runs and adds no signature. `G4_patents` (OFF r1,
forbidden substring `国家知识产权局`) and `G7_enumeration` (OFF r2, missing
`优必选` — the known recall defect) did not reproduce under ON, matching their
known non-determinism (Web lane + LLM synthesis). The historical all-green
`replay-post-lat3` therefore cannot be used as today's baseline; the same-day
OFF runs are the baseline, and against them ON is clean.

### G3 root cause — a deterministic defect, mis-read as flakiness

`他有哪些论文` (pronoun after an institution turn) fails in **all three** runs
with the identical assertion and the identical `query_type`
(`canonical_v2:A:answer`, never `clarification_only`). Not random, not
rerank-caused. Two independent defects sit behind one assertion:

1. **Behaviour**: the turn is never routed to clarification/pronoun resolution —
   the planner answers a paper-shaped query about the pronoun itself. Under ON
   the answer was actually the *better* behaviour ("“他”具体指哪位作者，目前无法
   从问题中确定 … 如果你能补充作者姓名 …"), i.e. a clarification phrased as prose;
   under OFF r1 it answered about the paper the pronoun was wrongly bound to.
2. **Oracle brittleness**: `must_clarify_or_person_scoped` accepts only a
   `clarification_only` query_type or the literal substrings 教授/老师/学者/
   **论文作者**. The ON answer asks who the person is but says 作者, not
   论文作者, so a semantically correct clarification is scored as a failure.

Recorded as its own defect: pronoun→person after an institution turn must
route to clarification, and the replay assertion must measure the behaviour,
not a literal proxy.

### Testset (workbook g2/g5) — ON 1/5 vs OFF 4/5

| case | OFF | ON |
|---|---|---|
| g2-t1 | PASS | FAIL — missing 九号, coverage 7/10 < 0.8 |
| g2-t2 | PASS | FAIL — pool 4 < 5, coverage 4/6 < 0.8 |
| g2-t3 | PASS | FAIL — stance check |
| g5-t1 | PASS | PASS |
| g5-t2 | FAIL (coverage 8/12) | FAIL (coverage 7/12) |

### Generalization P2 (on-category / off-category / off-domain / miss)

| probe | OFF | ON |
|---|---|---|
| drone#1 | 46/46/0/0 | 30/29/1/0 |
| drone#2 | 64/63/0/1 | 59/58/1/0 |
| drone#3 | 35/35/0/0 | 33/32/1/0 |
| storage#1 | 55/47/8/0 | 55/50/5/0 |
| lidar#1 | 64/38/25/1 | 64/43/20/1 |
| lidar#2 | 63/40/23/0 | 60/41/19/0 |
| medical#1 | 47/47/0/0 | 39/39/0/0 |

ON trades recall for precision: it improves off-category numbers on
lidar/storage but *drops* on-category coverage on drone and medical, which is
the axis the customer actually asked for.

### TTFT (ON) — within budget

23.75 / 11.61 / 21.27 / 16.08 / 19.47 / 18.05 / 13.85 s (大疆 / 教授 / 激光雷达 /
储能 / g2 / PCB#1 / PCB#2). All below the 30 s ceiling; the cross-encoder's own
cost is 208 ms at the 128-document cap, so it is not a latency risk.

### Why ON regresses a struct-field query (leading hypothesis, instrument first)

The cross-encoder sees text only: `_serving_rerank_document()` renders
`display_name（domain）` plus up to N evidence snippets. An entity whose match
is a *typed field* with a thin profile (九号: `industry=机器人`, nearly all other
fields empty) presents a near-empty document, so the model cannot see the
evidence that the deterministic tier score encodes (industry ×8 / tags ×4 /
product ×2 / text ×1). The measured symptom — 九号 and the drone-class
companies leaving the committed window under ON — matches that mechanism, but it
is not yet proven: the decisive check is to record, per turn, the pre-rerank
position, post-rerank position and rendered document length for the
struct-field-matched entities. Until that evidence exists this is a hypothesis,
not a finding.

Design consequence to carry into 1b.2/1b.3: the model must **augment** the
structural prior (blend or quota inside the commit window), and the superset
guard must cover the *commit* axis (every entity the legacy path committed
stays committed), not only recall generation.

### Verdict

Step 1b(a) is implemented and fail-safe, but **fails the quality gate** and is
not default-on. Replay is clean; testset g2 collapses 3/3 → 0/3, generalization
loses on-category coverage, so the lane returns to OFF (`rerank.conf.parked`).
The next step is not more reranker tuning — it is candidate generation
(1b.1 wide pool + bigram residue recall) and the commit-superset guard (1b.3),
with 1b.0b's live fault injection proving the fail-safe path before any
default-on decision.

## 2026-09-13 — Step 1b.0b fault injection closed (live, serial 18188)

Two real `/api/chat/stream` turns on the same instance, query
`深圳有哪些做激光雷达的公司`, endpoint pointed at a local stub
(`fault_stub_rerank.py`, `:18099`):

| mode | stub state | bytes | error events | done | answer len | journal fallback line |
|---|---|---|---|---|---|---|
| malformed | answering, adapter must reject the payload | 82,954 | 0 | 1 | 4,607 | `rerank result lacks a numeric score` |
| refused | process stopped, port closed | 89,944 | 0 | 1 | 4,781 | `rerank request failed: URLError` |

Both turns produced complete, category-consistent answers (速腾聚创 / 镭神智能 /
览沃 …) with no error event on the stream. Journal scan over the 23,713 lines of
the fault window: `Bearer` 0, `authorization` 0, credential content 0, query
text 0; the only rerank lines are the two normalized fallback lines above.
Scope note: the served journal is clean on all four counts; query text exists
only under `CANONICAL_V2_TURN_DEBUG_DIR` (the turn-debug artifact directory —
test instrumentation, not a served log).

Restore verified twice (script end, then re-checked): drop-ins back to
`lexical-index.conf` + `turn-debug.conf` (both `.pending` files inert),
`CANONICAL_V2_LEXICAL_INDEX=0`, no `CANONICAL_V2_RERANK_*` in the process
environment, `/api/health` ok. Original ON/stub drop-ins preserved by SHA256 in
`dropin-backup-20260913/`.

Verdict: the fail-safe path is proven on real turns. Step 1b.0b closes as
*measured* — quality gate failed (lane OFF), fallback verified, logs clean.
Default-on stays gated behind 1b.1/1b.3 + the four oracles.

## 2026-09-13 — 1b.0c routing half closed (G3 pronoun → clarification)

**What.** The replay-gate G3 defect (「他有哪些论文」 after an institution
turn free-retrieving junk papers) is fixed on the serving line: the
personal-pronoun × anchor-type guard from `513858e0` (branch
`data/p4-serving-pack-rebuild`, never merged into this line) is ported into
`canonical_v2_chat.py` + `followup_referents.py`, and interpreter check ③
is aligned with its documented symmetric rejection (typed referent ×
anchor-domain mismatch). Root cause for the residual: this line's 3.2.1
only fires clarification when **no** anchor exists; under the current pack
T1 anchors a canonical company, so the type-mismatched anchor slid through
to unbound retrieval, and the ON interpreter could also hand the org
subject back in place of the person pronoun.

**Evidence.** Unit: new guard suite 9 tests + 3 interpreter mismatch tests,
RED 5 failing → focused suites 42/188 green; adapter matrix row
`(他有哪些代表性研究成果, True, True, False)` → `True` (untyped anchor no
longer satisfies a personal pronoun, matching `_planning_displayed_ids`).
Endpoint (18188 restarted with this code): G3-only replay PASS (T2
`canonical_v2:G:clarification_only`, 1.0 s); full gate `replay-full-
20260913/` = **6/7 sessions, 1 failing turn** — G1/G2/G3/G4/G5/G6 PASS,
G7 `优必选` missing in repeat 2/3 only. Previous gate was 5/7 / 3 failures.

**G7 note (unchanged scope).** `diagnose_g7_recall.py` over 23 archived
具身智能 turns: local recall 6/23 (rank ~37/128), commit **0/23** — so
neither more reranker tuning nor web luck can close it; 1b.1 (wide pool +
bigram residue recall) and 1b.3 (commit-axis superset guard) own it.

**Artifacts.** Serving worktree: `replay-g3-fix-20260913/`,
`replay-full-20260913/`, `.agents/runs/harden-deterministic-subject-layer/
verification-3.2.2.md`; code uncommitted on `codex/canonical-v2-s12a-ready`.

## 2026-09-13 — G7 diagnosis closed to three mechanism causes; slice split (1b.1a/1b.1b)

**Diagnosis (26 archived enumeration turns + today's 3 runs).** 优必选 was
in the cut window only 6/26 (rank ~37/128 when present) and reached the
commit universe 0/26; today's three replay turns have it out of window
entirely, and the two passing runs came from web-prose mentions with zero
优必选 citations. Mechanism, all located in code:

1. F1 category scoring sorts ties by `canonical_object_id` (hash):
   「具身智能」 decomposes to bigrams {具身,身智,智能}; 智能 hits
   industry=人工智能 for a thousand-strong tie mass at ×8 — 优必选 ties at
   exactly 8 and the bucket cut (64 on the enumeration branch) is decided
   by hash order.
2. "A term counts once at its highest tier" swallows the differentiating
   evidence: 优必选's tech_tag 人形智能机器人研发商 contains 智能机器人/
   机器人/人形, but those are not query terms, and 智能 already scored at
   the industry tier.
3. The enumeration commit joins handles by
   `_prose_mention_name_forms(display_name)` over the answer text, while
   the AQ-S2c coverage sentence skips already-mentioned members — an
   in-window local handle can lose its join even when the answer text is
   not backed by any local selection.

**Plan adjustment.** 1b.1's wide pool is not the primary fix; the change
splits into 1b.1a (recall determinism: evidence-richness tie-break +
具身智能 `expands` family + optional struct-anchor quota) and 1b.1b
(commit-channel decoupling + local-proof acceptance), both verifiable on
the current pack without a rebuild. The wide pool stays, sequenced behind
these. Human plan + 8 program adjustments:
`docs/plans/2026-09-13-g7-closure-plan.md`; RED/GREEN contract appended to
this change's verification-contract.

## 2026-09-13 — G7 closed: replay gate 7/7; recall determinism + fallback coverage delivered (1b.1a/1b.1b)

**Outcome.** The seven-session replay gate is green for the first time with
both known reds closed: `replay-full-g7fix-r2-20260913/` = **7/7 ALL PASS**
(G1–G7). G7 深圳有哪些做具身智能的公司 repeats 3/3 with 优必选 locally
backed: turn-debug recall @12, commit @5 in every run, and an
official-source citation (ubtrobot.com) bound to the company; diagnose
totals moved recall 6/26→15/35 and commit 0/26→9/35 (all nine post-fix
turns).

**What landed (serving worktree, uncommitted).**

1. Declared-category-term trigger extension in `_category_query_terms`:
   planner view variants without 哪些/厂商 markers ("深圳 人形机器人 企业",
   "深圳 具身智能 公司") were inert (0 candidates measured) — a declared
   term now opens the F1 fallback.
2. Anchoring declaration family under the extracted bigram head 具身
   (members 智能机器人:2 / 人形机器人:2 / 人形:1; the 4-char head 具身智能
   never survives bigram extraction, which is why the family hangs off
   具身). Offline rank of 优必选 on the primary view 926 → 15; 乐聚 264 → 3;
   the 人形机器人 view unchanged (family correctly inert).
3. `_degraded_fallback_text(result, request=...)`: the deterministic
   fallback (all four call sites) appends the AQ-S2c member coverage
   sentence. The original 1b.1b join-leak hypothesis was **not
   reproducible** on current code — the failing live turn was
   `render_mode=deterministic_fallback` dropping the coverage sentence
   while 优必选 sat committed@15; the fallback path, not the join, was the
   gap.

**Verification.** Offline rank tables (baseline → after) in the runs dir;
3 new tests in `test_knowledge_read_isolated.py` (file 38/38; the PCB
declaration test scoped to `expands == "PCB"` now that a second family
exists) + 1 new test in `test_coverage_presentation.py` (5/5) + answer
suites 87/87; live G7-only 3/3 after fix 1+2, full gate 6/7 (fallback turn
failed → fix 3), full gate **7/7** after fix 3. Ruff clean on changed files
(knowledge_answer.py keeps its 4 pre-existing E402s). Full note:
`.agents/runs/retrieval-v2-derived-index-and-fusion/verification-1b1.md`.

**Backlog carried.** Wide pool (1b.1 remainder), tie-break richness +
whole-term extraction (not needed for this acceptance), 越疆-class
tag-vocabulary case (`智能机械臂解决方案提供商`) with the C1 rebuild
decision, lexical/rerank default-on still behind 1b.3/1b.4.

**Human docs.** Plan `docs/plans/2026-09-13-g7-closure-plan.md`; system
log entry 39.
