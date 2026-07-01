# Retrieval Gap-Closure Design — 全 / 准 / 快 三轴收口

> Status: design (approved sections §1–§3). Next: writing-plans.
> Owner: Claude (design/review). Implementation: Codex.
> Date: 2026-07-01.

## 0. Problem and first principles

The retrieval-augmented stack has implementation running ahead of its contracts. Measured
against repo artifacts (commits `1fb6449`, `0c85b04`, `06ae50b`, `0572d06`, `8da9053`,
`c4fa382`, `b1fc839`; OpenSpec change `fix-chat-retrieval-recall-gaps`):
end-to-end entity recall rose 53%→74% (per commit), latency B~17s→~12s / D~13-45s→~15s (per
commit), but the contracts, evidence, and acceptance are stale or absent.

The retrieval requirement decomposes into three first-principle axes:

- **全 (recall)** — P(all relevant entities are retrieved) = data-coverage × routing-reaches ×
  candidate-window × dedup-does-not-collapse.
- **准 (precision)** — P(returned entities are actually relevant) + identity is not over-merged +
  evidence is auditable/source-traceable (CLAUDE.md §5 invariant).
- **快 (latency)** — wall-clock to first byte / full answer, with an SLO and a regression guard.

Current state per axis (verified this session, not from memory):

- **全**: commit claims 74% (14/19), but 6/19 required entities are absent from `company`
  (云迹/九号/擎朗/嘉立创/许晋诚/陈功); 3/19 are present-but-broad (普渡/深南电路/开普勒).
  The candidate_limit raise (30→64) was eval-NEUTRAL and reverted; the real lever that produced
  53→74 is RRF + web-search + multi-path fuse, which has NO spec. Post-fix per-case recall is
  NOT persisted as evidence (74% lives only in a commit message).
- **准**: NEVER measured. Both eval scripts (`eval_recall.py`, `eval_recall_chat.py`) check only
  required-entity recall. There is no precision@k, no false-positive count, no audit of
  web-rescued entities' correctness/source, no check that dedup over-merge residue (#13 deferred)
  still mis-answers.
- **快**: code-optimizable latency is largely done (Milvus keepalive GOAWAY fixed → 0 GOAWAY;
  D-path parallelized B~17→12s, D~13-45→~15s). But there is NO SLO/target, latency numbers exist
  only in a commit message (no persisted evidence, no regression guard), and parallelization
  changed evidence-completion order without proof the order change is harmless.

Root structural finding: **the spec describes reverted fixes, not the fixes that actually work.**
`fix-chat-retrieval-recall-gaps` codifies FM1b (candidate_limit, reverted) and FM3 (routing,
data-blocked not implemented), while omitting RRF/web-search/fuse that actually produced the
gain. So the contract is doubly disconnected from reality. Any closure that does not first
re-truth the spec will repeat the "write contracts from inference" failure mode.

## 1. Evidence foundation — making 全 / 准 / 快 measurable (§1, approved)

First principle: engineering decisions cannot be made where outcomes are unmeasured. Only 全
has a (weak) oracle today, and its 74% is not persisted; 准 is fully dark; 快 has no SLO and no
evidence. The closure must build measurement first, or contracts will again be written from
inference.

### 1.1 Oracle definitions

| Oracle | Measures | RED (baseline) | GREEN (target) | Persist |
|---|---|---|---|---|
| Recall (existing, complete) | required entity appears in /api/chat response (synthesis off) | 53% baseline → 74% claimed | acceptance original 63%; **real ceiling must be re-measured** because 6/19 uningested | per-case JSON into run dir |
| Precision (new) | share of returned candidates that are **actually relevant** + false-positive count; web-rescued entity **correctness + source-auditability** | never measured → first run is baseline | **first run establishes baseline; GREEN p@k threshold set after first measurement** (not pre-committed, since 准 is currently dark) + 0 unsourced web-rescued entities + over-merge residue = 0 | per-case false-pos / provenance JSON |
| Latency (new) | /api/chat wall-clock, p50/p95/max; bucketed by A–G route | B~12s / D~15s claimed | **SLO: retrieval wall-clock p95 ≤ 6s; end-to-end p95 ≤ 15s** | per-case latency JSON + regression guard |

### 1.2 Precision oracle carrier (verified feasible)

`Evidence` carries `object_type` / `source_url` / `score` / `snippet`; the chat response is
emitted in professor/paper/web blocks, the web block carries `source_type:"web"`. Therefore we
can judge:
- **In-DB candidate precision**: whether top-k contains irrelevant entities (false positives),
  especially web-search leaking out-of-DB entities into a query (e.g. unrelated PCB firms into a
  PCB query).
- **web-rescued entity provenance**: each web-rescued entity must carry an auditable
  `source_url` (§5 source-traceability invariant); unsourced entities count as 准 risk.
- **dedup over-merge residue**: whether #13 (deferred) and other uncorrected View-B over-merges
  still surface as collapsed entities in the response.

Judgement method: **machine-check first** (required-entity hit / false-positive keywords /
unsourced web), **human/LLM-as-judge confirm on suspicious samples** (precision inherently
needs a human anchor — same eval-first approach as §14.7).

### 1.3 Latency SLO (approved)

SLO splits **retrieval wall-clock** (the optimizable part) from **end-to-end wall-clock**
(constrained by external API). The commit honestly flags remaining ~12s as external
(DeepSeek ~8-9s + Serper 1.8s + SQL 0.9s), not code-optimizable.

- Retrieval wall-clock p95 ≤ 6s (across A/B/D routes).
- End-to-end p95 ≤ 15s, max ≤ 20s (includes external API variance).

## 2. Contract structure — three artifacts by behavior-preservation split (§2, approved)

Per the approved approach (B: a change owns the mechanisms that achieve its goal), closure
lands in three boundary-clean contracts:

### 2.1 Artifacts and ownership

| Artifact | Type | Scope | RED→GREEN |
|---|---|---|---|
| **`fix-chat-retrieval-recall-gaps` (rewritten) recall** | OpenSpec behavior-affecting | RRF + web-search augmentation + multi-path fuse = the mechanisms that actually produced 53→74; delete reverted candidate_limit requirement; mark FM3 data-blocked not-implemented; FM1a recorded as recall ceiling out-of-scope | recall 53→74 per-case JSON; precision oracle first-run baseline |
| **`add-synthesis-timeout`** | OpenSpec behavior-affecting (small) | synthesis timeout 3s→60s env — changes which answers succeed: answers taking 4–59s previously failed (timed out), now succeed. That is user-visible behavior change vs current code, so §8 classifies it behavior-affecting (OpenSpec), not a behavior-preserving refactor. Small because it is one knob with an env override. | 60s default + env override; before/after evidence: answers that took 4–59s now complete instead of erroring |
| **`perf-retrieval-keepalive-parallel`** | refactor-contract (behavior-preserving) | Milvus keepalive GOAWAY fix + D-path parallel = result set unchanged, only faster; **key concern: evidence-completion-order change** → golden-order proof | 0 GOAWAY; latency meets SLO; golden: evidence set + order equivalent pre/post parallel (or prove order diff harmless to answer) |

### 2.2 recall change rewrite (spec re-truthing)

`fix-chat-retrieval-recall-gaps/specs/agentic-rag-retrieval/spec.md` rewritten to:
- **Delete** `Recall candidate window includes deep-but-relevant candidates` (reverted, not
  delivered).
- **Add** `Hybrid RRF + web-search augmentation rescues broad-profile and absent entities` (the
  actual delivery): vector ANN + lexical coverage + rerank three-way RRF fusion; web-search as a
  recall supplement for out-of-DB / broad-profile entities; every web evidence source-traceable
  (§5).
- **Fix** `Cross-filter professor queries reach recall`: add SHALL/MUST (fixes current
  `openspec validate --strict` error), but acceptance notes "data-blocked (许晋诚/陈功 not
  ingested) → routing-reachable is enough; recall ceiling bound by ingest".
- **Add** `Retrieval evidence is auditable`: every candidate carries source/domain/score, web
  rescues carry source_url (provides carrier for precision oracle and guards §5).
- **Add** precision and latency UNCHANGED/baseline references (point to new oracles) so all
  three axes are acceptable under one capability.

### 2.3 Incidental process gaps closed in flight

- `openspec validate --strict` error → fixed during spec rewrite (SHALL/MUST).
- Enter `change-ledger` → recall change marked `in-verification`; the other two registered by
  type.
- `tasks.md` checkboxes → re-truthed to reality (candidate_limit struck, RRF checked).
- 21 chat tests + three oracles → Claude Accept/Revise/Reject, advancing the slice from
  Candidate to Accepted.

### 2.4 Out of scope (honest boundary)

- **FM1a ingest of 6 absent entities**: recall hard ceiling (67% of misses), recorded as a
  separate ingest workstream — **not implemented this round**, but captured as a decision gate
  in §3.
- **streaming / cache**: the next latency lever; this round only sets SLO + evidence, does not
  implement streaming/cache (new workstream).
- **profile-quality rework** (普渡/深南电路 broad summaries): diagnosis flags this as "a deeper
  layer"; this round mitigates via RRF/web-search, does not redo embedding/profile.
- **dedup over-merge residue (#13 deferred)**: precision oracle will expose whether it still
  mis-answers, but correction belongs to `correct-paper-tier2-overmerge-view-b` follow-on, not
  the recall change.

## 3. Ingest and follow-on workstream boundary — the honest ceiling's decision gate (§3, approved)

### 3.1 Why FM1a gets a decision gate this round, not silence

Diagnosis quantifies: 6/19 missed entities are simply absent from `company`, 67% of misses.
Whatever the recall/fuse/perf contracts achieve, the real ceiling without ingest is ≈13/19
(68%); commit's 74% can only come from web rescuing ~1 entity. First principle: **data coverage
is a multiplicative factor on recall, not salvageable by retrieval logic.** So this round does
not implement ingest, but must provide a decision gate, or the 全 axis stays stuck on an
unquantified, undecided gap forever.

### 3.2 This round delivers vs leaves a decision gate

| Item | This round (contract + evidence) | Decision gate only (later workstream) |
|---|---|---|
| FM1a ingest | recall change records out-of-scope + quantifies ceiling; acceptance lists "real ceiling ≈68%, web rescue ceiling ≈+1" | ingest plan for 6 entities (source / collection / dedup / load / Milvus rebackfill) — new OpenSpec change; this round only records title + reason |
| Precision | new precision oracle (false-pos / unsourced-web / over-merge first baseline) + write run dir | feed false-positive samples back to concrete fixes (web provenance hardening, #13 over-merge correction) — each a later change |
| Latency | new latency oracle + SLO (retrieval p95≤6s / e2e p95≤15s) + regression guard | streaming/cache (perceived-latency optimization) — new workstream; this round only registers it as "known next lever" |
| dedup over-merge #13 | precision oracle exposes whether it still mis-answers | correction is `correct-paper-tier2-overmerge-view-b` follow-on, not implemented this round |

### 3.3 Ingest decision gate content (minimal, decidable)

This round fixes an "FM1a ingest decision record" (non-implementation) in the recall change so
the later ingest workstream has a clear start:
- The 6 absent entities (quantified).
- Per-entity block reason (0 rows in `company`; 许晋诚/陈功 block FM3 routing verification).
- Expected recall ceiling after ingest (from ≈68% to a theoretical value that needs re-measure
  post-ingest).
- Ownership: data-pipeline workstream, decoupled from retrieval-logic — to avoid "the recall
  change carrying ingest responsibility".

### 3.4 End-state picture after three-axis closure

```
全(recall):  recall change rewritten → RRF/web/fuse contract + recall oracle persisted (53→74 per-case)
             + precision oracle first-run (exposes false-pos / unsourced web)
             + FM1a ingest decision gate (ceiling quantified, 67% miss attributed to data, not retrieval)
准(precision): precision oracle new → dark box opened; web rescue provenance audit; over-merge residue first-run
快(latency):  perf refactor-contract → SLO (retrieval≤6s / e2e≤15s p95) + latency evidence + golden-order guard
process:      3 artifacts into ledger + validate exits 0 + tasks re-truthed + Claude Accept
```

Each axis has a defined RED/GREEN, an owner, and an explicit out-of-scope — all landing on a
measurable oracle or a decidable decision gate. No room remains for "contracts written from
inference."

## 4. Decisions locked (this session)

1. Scope-drift closure = split by **behavior-preservation** (§8): behavior-preserving →
   refactor-contract; behavior-affecting → OpenSpec.
2. Spec re-truthing = **rewrite spec to delivered reality** (RRF/web/fuse as the recall
   mechanism), not retain the reverted candidate_limit spec.
3. Recall mechanism ownership = **B**: a change owns the mechanisms that achieve its goal, so
   RRF/web/fuse belong to `fix-chat-retrieval-recall-gaps`, not a separate change. (Synthesis
   timeout and perf-keepalive each get their own contract.)
4. Latency SLO = **retrieval p95 ≤ 6s / end-to-end p95 ≤ 15s** (max ≤ 20s).

## 5. Open risks (honest)

- The 74%→ceiling gap cannot be fully closed this round because FM1a (data ingest) is out of
  scope; closure raises the contract/evidence/acceptance floor, not the recall ceiling.
- Precision oracle's first baseline is unknown — GREEN target for p@k may need a second pass
  after the first measurement. This is acknowledged, not hidden.
- Golden-order equivalence for parallel D-path: if the order diff is not provably harmless,
  `perf-retrieval-keepalive-parallel` cannot reach Accept and must be downgraded to a
  behavior-affecting change (OpenSpec). This risk is named so it cannot silently fail.
- This design is built from artifacts and commit claims; the 74%/latency numbers were NOT
  re-run this session (localhost verification requires unsetting 6 proxy vars per memory
  `env_proxy_bypass`). Re-measurement is the first implementation task, not a deferred check.
