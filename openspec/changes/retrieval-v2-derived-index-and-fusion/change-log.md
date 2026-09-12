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
