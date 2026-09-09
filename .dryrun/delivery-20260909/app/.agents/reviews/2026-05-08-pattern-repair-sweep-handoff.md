# Pattern-Repair Retroactive Sweep — Handoff (2026-05-08)

This handoff caps the 2026-05-08 session that shipped the `pattern-repair` skill
substrate and ran the sweep triage. Three deep slices are identified, scoped,
and ready for execution in separate sessions.

**Spec:** `docs/superpowers/specs/2026-05-08-pattern-repair-skill-design.md` (§10 sweep protocol).
**Plan:** `docs/superpowers/plans/2026-05-08-pattern-repair-skill.md` (T9 sweep slice loop).
**Triage report:** `.agents/reviews/2026-05-08-sweep-triage.md` (full classification of ~100 candidates).

---

## What was completed in 2026-05-08

| Step | Status |
|---|---|
| T1 Claude SKILL.md (~259 lines) | ✅ Created locally at `.claude/skills/pattern-repair/SKILL.md` (gitignored) |
| T2 Codex SKILL.md (~262 lines) | ✅ Created locally at `.agents/skills/pattern-repair/SKILL.md` (gitignored) |
| T3 mirror diff verification | ✅ Exactly 5 hunks per spec §7.3 |
| T4 AGENTS.md patches | ✅ §4.3 fallback compressed; §11 cross-link added |
| T5 CLAUDE.md patch | ✅ §8 Pattern-fix paragraph updated; `§4.3` ref → `§4 (Pattern-fix work subsection)` |
| T6 activation tests (manual) | ✅ Scenarios A (explicit trigger), B (auto-signal C multi-file), C (anti-trigger) all pass |
| T7 commit | ✅ `63679d5 feat(harness): add pattern-repair skill — substrate + spec/plan + cross-links` |
| T8 hotspot identification | ✅ Triage report written; 6 suspicious candidates surfaced |

---

## Sweep scope (locked by user 2026-05-08)

| Tier | Targets | Status |
|---|---|---|
| **T2 deep slices (this handoff)** | 3 high-priority suspicious candidates | Ready for separate sessions |
| T3 doc cleanup (32 done-undocumented specs) | Deferred to a future session using `ce-compound-refresh` / `ce-doc-review` |
| Unclear policy (4 specs) | Deferred to a future session pending closure-policy decision |
| 6 working-tree batches (Group A) | All `active` (in-flight W13-wave) — NOT touched by sweep |

The 3 remaining suspicious candidates that are NOT in the locked T2 set
(`w9-5-m2-4-dogfood`, `w13-14-paper-doi-verify`, `w13-15-test-fixture-pollution`)
are explicitly **out of scope** for this sweep cycle. If they need attention
they should be picked up as separate ad-hoc pattern-repair invocations or as
a future sweep batch.

---

## Slice 1 — `w12-4-m2-1-selector-expansion`

**Why suspicious:** Spec is design-only; no implementation commit found. This
selector gap is the root cause of "0 papers from any homepage paper-ingest
dry-run" failure mode noted in `docs/Paper-Data-Agent-PRD.md` and confirmed by
`docs/source_backfills/w13-14-doi-verify-dryrun-2026-05-03.txt`.

**Why high priority:** Blocks the entire paper data agent pipeline reaching
production. Multiple downstream specs (`w13-10` Milvus rebackfill, `w13-12`
identity status) implicitly depend on this being fixed first.

**Spec to read first:** `.agents/specs/2026-05-02-w12-4-m2-1-selector-expansion.md`

**How to start the slice (next session):**

1. Open a new Claude Code session at `/home/longxiang/MiroThinker`.
2. Verify the `pattern-repair` skill loads: `Are you aware of pattern-repair?`
3. Send: `Run pattern-repair on hotspot w12-4-m2-1-selector-expansion. Treat
   it as the reported symptom: homepage paper ingest returns 0 papers in any
   dry-run because the M2.1 selector expansion was specced but never
   implemented.`
4. Skill will activate; expect Phase 1 Diagnosis block.
5. Phase 2 sibling search: scope to **Lane 3 only** (per-domain paper). Lane 4
   (docs+migrations) optional if C2 stale-doc check seems relevant.
6. Likely defect class: **L1** (Local Branch Bug, single missing implementation)
   or **L4** (Schema/State Drift if data shape changed expectations) + **C2**
   (stale doc — w12-4 spec docs an unimplemented design).
7. Likely fix level: **Level 1** (local patch + regression test) if scope is
   just selectors, or **Level 6** (re-plan) if M2.1 design needs revision.
8. Hard cap: **1 day**. If selector work expands beyond that, escalate to a new
   `.agents/specs/2026-05-XX-w12-4-impl-escalated.md` per spec §10.3.

**Verification commands (when done):**
- `cd apps/miroflow-agent && uv run python scripts/run_homepage_paper_ingest.py --dry-run --limit 10` — confirm > 0 papers per profile
- `cd apps/miroflow-agent && uv run pytest tests/scripts/test_run_homepage_paper_ingest.py -v` — selector tests pass

**Mini-report path:** `.agents/reviews/2026-05-XX-sweep-w12-4-m2-1-selector.md` (use spec §6.4 template + outcome line).

---

## Slice 2 — `w13-10-paper-milvus-summary-zh-rebackfill`

**Why suspicious:** No implementation commit. `docs/index.md` Paper PRD row
explicitly states `summary_zh 未 rebackfill 到 Milvus`. Postgres has the data
(`3456/7297 = 47.4%` from `v1-paper-summary-zh-completed-2026-05-02`) but
Milvus `paper_chunks` collection doesn't have it, degrading paper retrieval
quality.

**Why high priority:** Direct quality impact on `/api/chat` paper queries
(rerank stage uses Milvus collections, not Postgres).

**Spec to read first:** `.agents/specs/2026-05-02-w13-10-paper-milvus-summary-zh-rebackfill.md`

**How to start the slice (next session):**

1. Send: `Run pattern-repair on hotspot w13-10-paper-milvus-summary-zh-rebackfill.
   Treat it as: paper summary_zh exists in Postgres for 3456/7297 papers but
   was never propagated to Milvus paper_chunks; paper retrieval rerank quality
   is degraded.`
2. Phase 2 sibling search: **Lane 2 (canonical/contracts)** + **Lane 3 (paper)**.
3. Likely defect class: **L4** (data sync drift) or **L6** (Evidence/Provenance
   if summary fields are part of evidence).
4. Likely fix level: **Level 1** (run a backfill script) or **Level 3**
   (write a generalized `summary_zh` backfiller covering paper + future fields).
5. Pre-flight check: `cd apps/miroflow-agent && uv run python scripts/run_milvus_backfill.py --domain paper --dry-run` — confirms what would change.
6. Hard cap: 0.5 day. Backfills are mostly mechanical.

**Verification commands:**
- `cd apps/miroflow-agent && uv run python -c "from src.data_agents.storage.milvus_collections import get_collection; c = get_collection('paper_chunks'); print(c.num_entities)"` — confirm count expectation
- One real `/api/chat` paper query before/after to spot retrieval quality delta

**Mini-report path:** `.agents/reviews/2026-05-XX-sweep-w13-10-paper-milvus.md`.

---

## Slice 3 — `w13-V3-intent-benchmark-archive`

**Why suspicious:** Benchmark ran but returned 0.000 accuracy (LLM was
unreachable in the sandbox where it ran). `docs/index.md` Agentic-RAG row
explicitly lists `host 复跑 100-case` as #1 next-priority. Production
classifier accuracy is currently **unknown**.

**Why high priority:** Without a real benchmark, we can't tell if classifier
A–G is regressing or improving. Blocks ADR-008 CI gate validation.

**Spec to read first:** `.agents/specs/2026-05-02-w13-V3-intent-benchmark-archive.md`
**Related:** `docs/architecture-decisions/ADR-008-intent-benchmark-ci-gate.md`

**How to start the slice (next session):**

1. **Pre-flight:** confirm LLM API access (Anthropic / Qwen / Dashscope env vars
   set) on whichever host the rerun targets. Without API access this slice will
   fail at the same point.
2. Send: `Run pattern-repair on hotspot w13-V3-intent-benchmark-archive. Treat
   it as: previous benchmark returned 0.000 accuracy because LLM was
   unreachable; production classifier accuracy is unknown; need a real host
   rerun.`
3. Phase 2 sibling search: **Lane 1 (admin-console)** + **Lane 2 (canonical)**
   to audit classifier prompts and routing.
4. Likely defect class: **L5** (Routing/Classification Drift — verifying A–G
   semantics still hold) + **C1** (Test-Matrix Gap — only one benchmark run
   means the matrix is thin).
5. Likely fix level: **Level 5** (parameterized matrix tests across A–G + per-domain).
6. Hard cap: 0.5 day for the rerun + analysis. If classifier shows regression,
   that's a separate fix that escalates.

**Verification commands:**
- `cd apps/miroflow-agent && uv run python -m src.core.pipeline agent=mirothinker_v1.5 llm=default benchmark=intent_classifier_100` (or equivalent — check `apps/miroflow-agent/conf/benchmark/`)
- Compare overall accuracy to the historical `0.690` from ADR-008
- Update `docs/architecture-decisions/ADR-008-intent-benchmark-ci-gate.md` with new run

**Mini-report path:** `.agents/reviews/2026-05-XX-sweep-w13-V3-benchmark.md`.

---

## Sequencing recommendation

Order: **Slice 1 → Slice 2 → Slice 3** (bottom-up).

- Slice 1 unblocks paper data agent end-to-end.
- Slice 2 makes paper retrieval use the freshest data.
- Slice 3 then validates that classifier behavior is healthy enough that the
  paper retrieval improvements actually surface to users.

If any slice escalates to Level 6 (re-plan), pause the sequence and create the
escalation spec before proceeding. Do not pile escalations.

---

## After all three slices complete

T10 (sweep summary + `docs/index.md` status update) per plan §"Task 10":

1. Aggregate `Sweep slice outcome:` lines from each `.agents/reviews/2026-05-XX-sweep-*.md`.
2. Write `.agents/reviews/2026-05-XX-pattern-repair-retroactive-sweep.md` summary.
3. Update `docs/index.md` 🟡 → ✅ where slice outcomes warrant.
4. User-approved commit per plan T10 Step 5.

---

## Open meta-issue (process gap, not a sweep slice)

The triage subagent flagged: **32 specs lack matching `.agents/reviews/` entries** —
this is a systematic process gap (Codex implements work; Claude reviews not consistently
written). The right fix is a hook or a slash-command ritual that prompts review
creation when a spec's last-touched commit hits main. **Track this as a separate
work item, not a sweep slice.** Suggested next step: open a new spec at
`.agents/specs/2026-05-XX-review-cycle-ritual.md` and brainstorm a lightweight
hook (e.g., `superpowers:writing-skills` to add a `review-on-merge` skill).

---

## Reset condition

If a future session discovers that the pattern-repair skill has broken (e.g.,
not triggering on Chinese keywords any more, or activating on anti-triggers),
do NOT amend the skill silently. Run the activation tests from plan T6 first;
if any fail, the skill itself is the bug — treat it as a Level 6 re-plan and
update the spec before fixing the skill.
