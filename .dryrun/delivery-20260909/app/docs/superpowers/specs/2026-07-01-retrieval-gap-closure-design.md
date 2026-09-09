# Retrieval Gap-Closure Design — 全 / 准 / 快 三轴收口

> Status: design (approved §1–§3) + Phase-1 measurement revision (2026-07-01).
> Phase 1 oracles built + run; measurement revised the §0 recall premise (74%→58%,
> Serper 403 → web-augment dead) and split web-augment to its own workstream (decision C).
> Owner: Claude (design/review). Implementation: Codex.
> Date: 2026-07-01.

## 0. Problem and first principles

The retrieval-augmented stack has implementation running ahead of its contracts. Measured
against repo artifacts (commits `1fb6449`, `0c85b04`, `06ae50b`, `0572d06`, `8da9053`,
`c4fa382`, `b1fc839`; OpenSpec change `fix-chat-retrieval-recall-gaps`): a commit claims
end-to-end recall 53%→74% and latency B~17s→~12s / D~13-45s→~15s, but the contracts, evidence,
and acceptance are stale or absent.

**Phase-1 measurement (this session, current HEAD, synthesis off) revised the recall premise:**
- End-to-end recall = **58% (11/19)**, NOT 74%. The 74% commit claim is **not reproducible** —
  it depended on Serper web-search augmentation, which now fails with `403 Unauthorized`
  (dead credential). With web dead, real recall is 58% (pure DB + SQL routing + RRF + lookup
  paths). Forced-domain no-web recall = 37% (7/19); the +21% to 58% is the chat path's
  SQL/lookup routes rescuing #1/#24/#40/#41 that pure vector misses.
- Latency (retrieval, synthesis off) = **p95 5.71s — SLO PASS** (≤6s). Measured without web
  (Serper fails fast); with a live Serper, D-path would be ~1.8s slower.
- Precision oracle built + run; surfaces the false-positive substrate (e.g. #4 returns 30
  candidates, only 普渡 is a required leader). `unsourced_web = 0` because web is dead (no web
  candidates to audit) — web-provenance auditing is blocked until Serper is fixed.

The retrieval requirement decomposes into three first-principle axes:

- **全 (recall)** — P(all relevant entities are retrieved) = data-coverage × routing-reaches ×
  candidate-window × dedup-does-not-collapse. Currently 58% (no web); web-augment is an
  intended-but-currently-broken recall lever, split to its own workstream (decision C).
- **准 (precision)** — P(returned entities are actually relevant) + identity not over-merged +
  evidence auditable/source-traceable (CLAUDE.md §5). Never measured before this round; the
  precision oracle now surfaces the false-positive substrate; web-provenance audit blocked
  until Serper fixed.
- **快 (latency)** — wall-clock to first byte / full answer, with an SLO and regression guard.
  Retrieval p95 5.71s (PASS); end-to-end (with synthesis) unmeasured this round but estimated
  ~14s (under the 15s e2e SLO).

Root structural finding (unchanged): **the spec describes reverted fixes, not the fixes that
actually work.** `fix-chat-retrieval-recall-gaps` codifies FM1b (candidate_limit, reverted) and
FM3 (routing, data-blocked not implemented), while omitting RRF that actually produced the
gain. Web-augment — the other shipped mechanism — is both un-specced AND currently broken
(Serper 403). So the contract is doubly disconnected from reality. Any closure that does not
first re-truth the spec will repeat the "write contracts from inference" failure mode.

## 1. Evidence foundation — making 全 / 准 / 快 measurable (§1, approved + built)

First principle: engineering decisions cannot be made where outcomes are unmeasured. Only 全
had a (weak) oracle; 准 was fully dark; 快 had no SLO. The closure builds measurement first.
**Phase 1 built all three oracles (TDD) and ran them; evidence persisted to
`.agents/runs/retrieval-generation-alignment/`.**

### 1.1 Oracle definitions (measured baselines)

| Oracle | Measures | RED (baseline, measured) | GREEN (target) | Persist |
|---|---|---|---|---|
| Recall (existing, +JSON persist) | required entity appears in /api/chat response (synthesis off) | **58% (11/19)** end-to-end no-web; forced-domain no-web 37% | acceptance = 58% current-HEAD (web split out); FM1a ingest is the recall ceiling | post-fix-recall.json |
| Precision (new, built) | returned candidates that are **actually relevant** + false-positive count; web-rescued entity correctness + source-auditability | first run done; false-positive substrate surfaced (e.g. #4: 30 cands, only 普渡 required); `unsourced_web=0` (Serper dead) | first-run baseline; GREEN p@k threshold set after labeling; 0 unsourced web (once Serper fixed); over-merge residue = 0 | precision-baseline.json |
| Latency (new, built) | /api/chat wall-clock, p50/p95/max; bucketed by A–G route | **retrieval p95 5.71s (PASS ≤6s)**, synthesis off, no web | retrieval p95 ≤ 6s (met); e2e p95 ≤ 15s (est. ~14s, unmeasured this round) | latency-baseline.json |

### 1.2 Precision oracle carrier (verified + fixed)

`Evidence` carries `object_type` / `source_url` / `score` / `snippet`; the chat response renders
candidates as `{id, label, type, url}` dicts. Phase 1 found and fixed a name-extraction bug
(`_display_name` now prefers `label`). Therefore we can judge:
- **In-DB candidate precision**: top-k false positives (e.g. non-leader robot firms returned for
  a 酒店送餐 query). Substrate now surfaced.
- **web-rescued entity provenance**: each web candidate must carry an auditable `source_url`
  (§5); unsourced entities count as 准 risk. **Blocked until Serper fixed** (0 web candidates now).
- **dedup over-merge residue**: whether #13 (deferred) and other uncorrected View-B over-merges
  still surface as collapsed entities. Substrate available; labeling pending.

Judgement: machine-check first (required-entity hit / false-positive keywords / unsourced web),
human/LLM-as-judge confirm on suspicious samples (precision needs a human anchor — §14.7).

### 1.3 Latency SLO (approved; retrieval SLO met)

SLO splits retrieval wall-clock (optimizable) from end-to-end (constrained by external API).
- Retrieval wall-clock p95 ≤ 6s (across A/B/D routes) — **MET (5.71s)**, synthesis off, no web.
- End-to-end p95 ≤ 15s, max ≤ 20s — estimated ~14s (synthesis ~8-9s + retrieval ~5.7s); not
  re-measured with synthesis on this round (needs DeepSeek key). With a live Serper, D-path
  adds ~1.8s.

## 2. Contract structure — behavior-preservation split + web split (§2, revised by decision C)

Per approach B (a change owns the mechanisms that achieve its goal) AND decision C (web-augment
split out because it is both broken AND a precision risk), closure lands in **four workstreams**:
three contracted this round (recall, synthesis-timeout, perf) + web-augment opened as a
skeleton follow-on (Serper fix + web contract + provenance audit).

### 2.1 Artifacts and ownership

| Artifact | Type | Scope | RED→GREEN |
|---|---|---|---|
| **`fix-chat-retrieval-recall-gaps` (rewritten) recall** | OpenSpec behavior-affecting | RRF + SQL routing + lookup paths = the mechanisms producing the **58%** recall (web-search REMOVED from this change — split to web-augment workstream); delete reverted candidate_limit requirement; mark FM3 data-blocked not-implemented; FM1a recorded as recall ceiling out-of-scope | recall 58% per-case JSON (persisted); precision oracle first-run baseline |
| **`add-synthesis-timeout`** | OpenSpec behavior-affecting (small) | synthesis timeout 3s→60s env — answers taking 4–59s previously failed, now succeed. User-visible behavior change vs current code (§8 → OpenSpec). | 60s default + env override; before/after evidence |
| **`perf-retrieval-keepalive-parallel`** | refactor-contract (behavior-preserving) | Milvus keepalive GOAWAY fix + D-path parallel = result set unchanged, only faster; **key concern: evidence-completion-order change** → golden-order proof | 0 GOAWAY; retrieval p95 ≤ 6s (MET 5.71s); golden: evidence set + order equivalent pre/post parallel |
| **`add-web-augment` (skeleton, follow-on)** | OpenSpec behavior-affecting (new, NOT implemented this round) | web-search augmentation as a recall lever + Serper 403 fix + web-evidence provenance contract + precision audit of web-rescued entities | opened as proposal/skeleton only; records the Serper 403 defect + the web-augment behavior + the provenance/precision obligations; implementation deferred |

### 2.2 recall change rewrite (spec re-truthing, web removed)

`fix-chat-retrieval-recall-gaps/specs/agentic-rag-retrieval/spec.md` rewritten to:
- **Delete** `Recall candidate window includes deep-but-relevant candidates` (reverted, not
  delivered).
- **Add** `Hybrid RRF rescues broad-profile entities` (the actual delivered recall mechanism,
  no web): vector ANN + lexical coverage + rerank three-way RRF fusion so deep-but-lexically-
  relevant entities (普渡) enter the candidate window via a second signal. (web-search
  augmentation is NOT in this requirement — it moved to `add-web-augment`.)
- **Fix** `Cross-filter professor queries reach recall`: add SHALL/MUST (fixes current
  `openspec validate --strict` error); acceptance notes "data-blocked (许晋诚/陈功 not
  ingested) → routing-reachable is enough; recall ceiling bound by ingest".
- **Add** `Retrieval evidence is auditable`: every candidate carries source/domain/label/url
  (provides carrier for precision oracle and guards §5).
- **Add** precision and latency UNCHANGED/baseline references (point to new oracles).

### 2.3 Incidental process gaps closed in flight

- `openspec validate --strict` error → fixed during spec rewrite (SHALL/MUST).
- Enter `change-ledger` → recall change marked `in-verification`; synthesis-timeout and
  perf-keepalive registered by type; web-augment registered as `proposed` (skeleton).
- `tasks.md` checkboxes → re-truthed to reality (candidate_limit struck, RRF checked, web
  split out).
- 21 chat tests + three oracles → Claude Accept/Revise/Reject, advancing slices from
  Candidate to Accepted.

### 2.4 Out of scope (honest boundary)

- **FM1a ingest of 6 absent entities**: recall hard ceiling (67% of misses), recorded as a
  separate ingest workstream — not implemented this round; captured as a decision gate in §3.
- **web-augment (Serper 403 + web contract + provenance audit)**: split to `add-web-augment`
  workstream (decision C); opened as a skeleton only this round, not implemented.
- **streaming / cache**: the next latency lever; this round only sets SLO + evidence.
- **profile-quality rework** (普渡/深南电路 broad summaries): mitigated via RRF, not redone.
- **dedup over-merge residue (#13 deferred)**: precision oracle exposes whether it still
  mis-answers; correction belongs to `correct-paper-tier2-overmerge-view-b` follow-on.

## 3. Ingest and follow-on workstream boundary — the honest ceiling's decision gate (§3, approved)

### 3.1 Why FM1a gets a decision gate this round, not silence

Diagnosis quantifies: 6/19 missed entities are simply absent from `company`, 67% of misses.
The real no-web recall ceiling without ingest is 58% (measured); even with a fixed Serper,
web can only rescue a subset of the 6 absent entities. First principle: **data coverage is a
multiplicative factor on recall, not salvageable by retrieval logic.** So this round does not
implement ingest, but must provide a decision gate.

### 3.2 This round delivers vs leaves a decision gate

| Item | This round (contract + evidence) | Decision gate only (later workstream) |
|---|---|---|
| FM1a ingest | recall change records out-of-scope + quantifies ceiling (58% measured, no-web) | ingest plan for 6 entities — new OpenSpec change; this round records title + reason |
| web-augment | `add-web-augment` skeleton opened (Serper 403 defect + web contract + provenance obligations recorded) | Serper key fix + web-augment implementation + precision audit of web-rescued entities — the full workstream |
| Precision | precision oracle (false-pos substrate + unsourced-web=0 baseline) + run dir | false-positive labeling → concrete fixes (web provenance hardening, #13 over-merge) — each a later change |
| Latency | latency oracle + SLO (retrieval p95≤6s MET 5.71s / e2e p95≤15s) + regression guard | streaming/cache; also e2e-with-synthesis re-measurement (needs DeepSeek key) |
| dedup over-merge #13 | precision oracle exposes whether it still mis-answers | correction is `correct-paper-tier2-overmerge-view-b` follow-on |

### 3.3 Ingest decision gate content (minimal, decidable)

This round fixes an "FM1a ingest decision record" (non-implementation) in the recall change:
- The 6 absent entities (quantified).
- Per-entity block reason (0 rows in `company`; 许晋诚/陈功 block FM3 routing verification).
- Expected recall ceiling after ingest (from 58% to a theoretical value needing re-measure
  post-ingest; web-augment, if fixed, adds on top).
- Ownership: data-pipeline workstream, decoupled from retrieval-logic.

### 3.4 End-state picture after closure

```
全(recall):  recall change rewritten → RRF/SQL/lookup contract (web OUT) + recall oracle (58% per-case)
             + FM1a ingest decision gate (67% miss = data, not retrieval)
             + add-web-augment skeleton (Serper 403 defect + web contract + provenance, follow-on)
准(precision): precision oracle built → false-positive substrate surfaced; web-provenance audit
             blocked until Serper fixed (add-web-augment); over-merge residue first-run
快(latency):  perf refactor-contract → SLO (retrieval p95 5.71s MET ≤6s) + latency evidence + golden-order guard
process:      4 workstreams into ledger + validate exits 0 + tasks re-truthed + Claude Accept
```

## 4. Decisions locked (this session)

1. Scope-drift closure = split by **behavior-preservation** (§8).
2. Spec re-truthing = **rewrite spec to delivered reality** (RRF as the recall mechanism), not
   retain the reverted candidate_limit spec.
3. Recall mechanism ownership = **B**: a change owns the mechanisms that achieve its goal, so
   RRF belongs to `fix-chat-retrieval-recall-gaps`. (Synthesis timeout and perf-keepalive each
   get their own contract.)
4. Latency SLO = **retrieval p95 ≤ 6s / end-to-end p95 ≤ 15s** (max ≤ 20s).
5. **(C, post-measurement)** Recall contract baseline = **58%** (current-HEAD, no-web, Serper
   dead). Web-augment is **split out** to `add-web-augment` (its own OpenSpec change: Serper 403
   fix + web behavior contract + provenance/precision audit), NOT lumped into the recall
   change. Rationale: web is both broken (Serper 403) and a precision risk — it deserves its
   own contract, and the recall contract must not be held hostage to a dead credential. The
   commit's 74% is recorded as a non-reproducible claim (depended on the now-dead Serper key).

## 5. Open risks (honest, post-measurement)

- Recall ceiling (58%) cannot be raised this round: FM1a ingest is out of scope, and
  web-augment (the other potential lever) is split out + blocked by Serper 403. Closure raises
  the contract/evidence/acceptance floor, not the recall number.
- **Serper 403 is a runtime credential defect** outside code/contract scope — recorded in
  `add-web-augment` as the first blocker; not fixable by this design (needs the user's key).
- Precision GREEN p@k threshold deferred to post-labeling (准 was dark; first run is substrate).
- End-to-end latency SLO (≤15s) not re-measured with synthesis on this round (needs DeepSeek
  key); retrieval SLO is met (5.71s).
- Golden-order equivalence for parallel D-path: if the order diff is not provably harmless,
  `perf-retrieval-keepalive-parallel` downgrades to behavior-affecting (OpenSpec). Named so it
  cannot silently fail.
