# Pattern-Repair Skill — Design Spec

**Date:** 2026-05-08
**Status:** Approved for implementation
**Owner:** longxiang
**Source brainstorming:** in-session, this date

---

## 1. Problem and goal

### 1.1 Symptom

In MiroThinker vibe coding, when a user reports a concrete bug to Codex CLI or Claude
Code, both tools default to a single-point patch on the reported case. When the user
reports a similar bug afterward, both again apply a single-point patch. The user's
prompt-level instruction to "do this systematically" does not change this behavior.

### 1.2 Diagnosed root cause

`CLAUDE.md §8` and `AGENTS.md §0/§4` classify "obvious local bug, reversible one- or
two-file edit" as **tiny fix**, with the explicit workflow `inspect → smallest fix →
narrow check → diff review → report`. The model treats a concrete bug report as a tiny
fix by hard rule and never reaches the systemic-fix workflow even when the user uses
trigger words. The instruction-priority hierarchy of `superpowers` makes skills the
only mechanism that legitimately overrides this default: prose pleas in instructions
do not.

### 1.3 Goal

Ship a `pattern-repair` skill that, when triggered:

1. Blocks direct edit on the reported case until a structured Diagnosis block is
   produced.
2. Forces classification into a defect class.
3. Forces a sibling-search step before deciding on fix level.
4. Requires regression coverage tied to the *invariant*, not the example.
5. Produces a final report aligned with `AGENTS.md §11` Pattern-fix template.

The skill must be cheap enough (in context tokens) and unambiguous enough (in
triggering rules) that the model actually invokes it instead of falling through to
tiny-fix.

### 1.4 Non-goals

- Not building a generic "half-baked scaffolding consolidator" meta-skill (YAGNI; only
  one occurrence of the pattern; existing `ce-doc-review` / `ce-compound-refresh` /
  `writing-skills` already cover related concerns).
- Not refactoring `AGENTS.md` or `CLAUDE.md` structure. Only minimal cross-link
  patches.
- Not replacing `superpowers:systematic-debugging` or `compound-engineering:ce-debug`.
  Pattern-repair is orthogonal to them.

---

## 2. Architecture decisions (all locked)

| Decision | Choice | Rationale |
|---|---|---|
| **D1. Skill thinness** | Thin layer activator, ~250 lines per file | Repo already has scaffolding in `AGENTS.md §0/§4.3/§5/§6/§7/§11`; skill is the missing enforcement container, not a duplicate. Lower context cost → higher trigger probability. |
| **D2. Source-of-truth strategy** | Skill body is the protocol owner; `AGENTS.md` and `CLAUDE.md` get minimal cross-link patches (option D from brainstorming) | Avoids `AGENTS.md` restructure (high blast radius). Keeps existing fragments where they have local utility. |
| **D3. Triple-skill handoff** | Orthogonal with explicit routing (option δ) | Pattern-repair triggers on systemic signals → skip reproduction; ambiguous bug → `systematic-debugging` first, then transition to pattern-repair if needed. `ce-debug` deprioritized when pattern-repair applies. |
| **D4. Sibling-search dispatch** | Default parallel `Explore` agents, partitioned by domain (4 lanes) | Leverages Claude's native edge over Codex. Domain boundaries match MiroThinker data layout. |
| **D5. Auto-detection signals** | Enable A/B/C/D (in-session repeat / recent-commit hint / multi-file pattern / cross-domain hint) | All four have low false-positive risk. Coverage > selectivity here. |
| **D6. Anti-triggers** | Strict list + `skip-but-note` epilogue | "Just fix this one case" disables the skill but emits a one-line sibling-risk note in the final report. Honors user intent without losing institutional memory. |
| **D7. Defect taxonomy** | 7 primary (L1–L7) + 2 cross-cutting (C1, C2) | Compressed from Codex draft's 10 classes (A–J). MiroThinker-tuned naming and examples. |
| **D8. DRY across 2 files** | Full mirror, manual sync, called out at top of each SKILL.md | Two files × ~250 lines, ~150 lines shared body. Manual sync risk is acceptable for a low-change-rate skill. Eliminates inter-CLI coupling. |
| **D9. Report alignment** | Skill final report extends `AGENTS.md §11` Pattern-fix template, not replaces it | Already in repo; reuse > re-invent. Skill adds the `Sibling search` section. |
| **D10. Length budget enforcement** | Hard cap 280 lines per SKILL.md | If reviewers / future edits push past 280 lines, must refactor (push content into AGENTS.md cross-refs) before merging. |

---

## 3. Trigger model

### 3.1 Explicit trigger words (skill-creator: put in `description` frontmatter)

```
Chinese: 系统性、同类问题、类似问题、不要打补丁、不要单点修复、根因、
         反复出现、全面检查、跨领域同样问题、第二次出现
English: patch-only, systemic, recurring, regression, escaped defect,
         sibling pattern, root cause, defect class, system-wide, second time,
         not-just-this-case
```

### 3.2 Auto-detection signals (skill self-checks before activating)

| Signal | Detection | Confidence |
|---|---|---|
| **A. In-session repeat** | Same file path or function name appeared in a previous user turn within current session | High |
| **B. Recent-commit hint** | `git log --oneline -10` shows `fix(...)` / `revert(...)` touching the same file as current bug; current report on same area | Medium (may false-positive in active dev periods; skill should add a one-line "I notice we recently fixed Y in this area — is this systemic?" check before fully activating) |
| **C. Multi-file pattern** | User explicitly mentions multiple sites, nodes, or domains | Very high |
| **D. Cross-domain shared-surface** | Bug touches `_VALID_DOMAINS` / `evidence` / `run_id` / `canonical/` / `contracts.py` / four-domain shared invariants | Medium-high |

### 3.3 Anti-triggers (skill MUST NOT activate)

| Signal | Action |
|---|---|
| User explicitly says "只修这一处" / "narrow patch" / "don't broaden" / "minimal change" | Do not activate. Run tiny-fix. **Append a one-liner to final report:** `Sibling risk: <where to look> — not investigated per user request.` |
| Change is typo / docs / comments / format-only / rename | Do not activate. |
| User pasted a complete diff / patch | Do not activate. User has decided. |
| `.agents/specs/` or `.agents/handoffs/` text-only edit | Do not activate. |

### 3.4 Triple-skill routing (handoff with `systematic-debugging` / `ce-debug`)

```
Bug report received
  │
  ├─ Trigger word OR auto-signal C (multi-file)?  → pattern-repair (no reproduce phase)
  ├─ Auto-signal A or B fired?                    → pattern-repair, ask one clarifying Q first
  ├─ Auto-signal D fired AND no other signals?    → pattern-repair, optional reproduce
  ├─ Bug not understood / not reproducible?       → systematic-debugging first
  │                                                  THEN evaluate pattern-repair triggers
  │                                                  with the new understanding
  └─ Anti-trigger fired?                          → tiny-fix; emit skip-but-note epilogue
```

`ce-debug` is intentionally deprioritized when pattern-repair triggers fire, to avoid
three-skill confusion. `ce-debug` remains useful for bugs that need root-cause
analysis but no sibling search.

---

## 4. Defect-class taxonomy (MiroThinker-tuned)

### 4.1 Primary classes (cause of the defect — pick one)

| ID | Class | Typical clue | Preferred fix level (see §5) |
|---|---|---|---|
| **L1** | Local Branch Bug | Only one branch, one node, one route, one component violates the invariant | Level 1 (local patch + regression test) |
| **L2** | Duplicated Logic | Same decision logic copied across files (e.g., evidence check repeated in each domain enricher) | Level 2–3 (consolidate to helper) |
| **L3** | Missing Shared Helper / Boundary Guard | Multiple call sites independently re-implement normalization, validation, routing, or formatting | Level 3 (helper) or Level 4 (boundary guard) |
| **L4** | Schema / State Contract Drift | V001–V018 + DDL + Pydantic + storage code + tests not synchronized; or state enters illegal form | Level 4 (boundary) + parameterized tests |
| **L5** | Routing / Classification Drift | Classifier A–G semantics violated; `_VALID_DOMAINS` filter inconsistent; fusion/rerank ordering wrong; SessionContext entity stack inconsistent | Level 4 (boundary) + Level 5 (matrix tests across A–G) |
| **L6** | Evidence / Provenance Violation | `run_id` / `source_url` / `fetched_at` / `confidence` weakened or missing; structured evidence shape compromised | Level 4 (Pydantic boundary guard) + parameterized tests across all four domains |
| **L7** | Provider / Integration Boundary Failure | Anthropic / Qwen / Dashscope / Milvus / Postgres failure leaking raw exception; missing fallback; client misconfigured | Level 3–4 (client wrapper) + failure-path tests |

### 4.2 Cross-cutting checks (always evaluate alongside primary class)

| ID | Class | Action |
|---|---|---|
| **C1** | Test-Matrix Gap | If only single-case test exists, add parameterized matrix across nodes / classes / domains / providers as relevant. |
| **C2** | Stale-Doc Revival | If code is following a doc marked legacy/partial in `docs/index.md`, follow current source-of-truth instead. Note doc drift in final report. |

### 4.3 Examples mapped to MiroThinker areas (for skill body, abbreviated)

```text
"chat router returns wrong domain in turn 2" → L5 + C1
"evidence missing fetched_at in patent only" → L6 (cross-domain audit needed)
"V016 added column but Pydantic model didn't update" → L4 + C2 likely
"Anthropic 5xx surfaces stack trace to /api/chat caller" → L7
"professor enricher and company enricher do same regex differently" → L2 / L3
```

---

## 5. Fix-level ladder

```
Level 0: No code change
  Reported behavior is expected, stale, or setup-caused. Provide evidence.

Level 1: Local patch + regression test
  Sibling search confirmed only-one-occurrence. Add a regression test for the
  invariant on the local case.

Level 2: Local helper / table-driven local logic
  Multiple branches in one file share logic. Consolidate within the file.

Level 3: Shared domain helper
  Multiple files in same domain share invariant. Helper near the domain owner +
  helper tests + at least one call-site test.

Level 4: Boundary guard / contract enforcement
  Many call sites can violate. Enforce at boundary: route, service, state update,
  Pydantic validator, repository layer, or `_VALID_DOMAINS` filter.

Level 5: Parameterized invariant test matrix
  Class spans nodes / domains / providers. Add parameterized tests; lower-level
  fix may already exist.

Level 6: Re-plan
  Defect reveals architectural contradiction. Stop. Write a plan in
  `.agents/specs/`. Do not broad-rewrite.
```

**Default preference for MiroThinker, when user uses systemic trigger words:**
**Level 3 or Level 4.** Drop to Level 1 only if sibling search proves no class.

---

## 6. Skill workflow (the body that goes into both SKILL.md files)

### 6.1 Phases

```
Phase 0 — Trigger / anti-trigger gate
  Check explicit triggers + auto-signals + anti-triggers. Decide: activate /
  skip-but-note / pass to systematic-debugging.

Phase 1 — Diagnosis block (REQUIRED before any edit)
  Emit:
    Reported symptom:
    Expected invariant:
    Likely defect class (L1–L7, optionally + C1/C2):
    Why this may be systemic:
    Search plan:
    Files / areas to inspect:
    Proposed fix level (Level 0–6):
    Regression test plan:
    Out of scope:

Phase 2 — Sibling search (parallel by default)
  Dispatch 3–5 Explore agents partitioned by 4-domain layout (see §6.3).
  Aggregate findings in main thread.

Phase 3 — Decide invariant (one-sentence)
  Lock the invariant before editing.

Phase 4 — Implementation plan (compact, in-message; not a separate file unless
  Level 6)
  Slices / tests / verification commands / rollback.

Phase 5 — Implement
  Smallest coherent shared fix. No drive-by refactor. Preserve public APIs,
  schemas, prompt contracts, evidence shape, classifier A–G semantics, and
  `_VALID_DOMAINS`.

Phase 6 — Regression tests
  Tied to invariant. Parameterized when class spans multiple sites.

Phase 7 — Verification
  Narrowest relevant first. Use AGENTS.md §10 command palette. Never claim
  pass without actual run in current session.

Phase 8 — Post-fix sibling re-check
  Rerun the most important sibling search; report remaining matches and why
  they are safe / out of scope.

Phase 9 — Self-review + final report (matches AGENTS.md §11 Pattern-fix template)
```

### 6.2 Diagnosis block template

(Copy-paste-ready in skill body. Aligned with `AGENTS.md §4.3` 7-line template
but extended to 9 lines for taxonomy fields.)

```text
Reported symptom:
Expected invariant:
Likely defect class (L1–L7, optionally + C1/C2):
Why this may be systemic:
Search plan:
Files / areas to inspect:
Proposed fix level (Level 0–6):
Regression test plan:
Out of scope:
```

### 6.3 Sibling-search dispatch (Claude Code version only)

**Default lanes (parallel `Explore` agents):**

```
Lane 1 — admin-console
  Roots: apps/admin-console/backend/api/, apps/admin-console/backend/services/,
         apps/admin-console/backend/storage/, apps/admin-console/tests/
  Brief: <invariant>; find sites that violate or might violate it.

Lane 2 — data-agents canonical / contracts
  Roots: apps/miroflow-agent/src/data_agents/canonical/,
         apps/miroflow-agent/src/data_agents/contracts.py,
         apps/miroflow-agent/src/data_agents/evidence.py,
         apps/miroflow-agent/src/data_agents/{linking,normalization,publish}.py
  Brief: <invariant>; check shared layer.

Lane 3 — data-agents per-domain
  Roots: apps/miroflow-agent/src/data_agents/{company,professor,paper,patent}/,
         apps/miroflow-agent/tests/
  Brief: <invariant>; audit each of the four domains independently.

Lane 4 — docs + migrations + scripts
  Roots: docs/, apps/miroflow-agent/alembic/versions/,
         apps/miroflow-agent/scripts/run_*
  Brief: <invariant>; find stale docs (C2) and migration drift (L4).
```

**Codex version:** sequential `rg` commands using `AGENTS.md §6` recipes; same
content but no parallelism. Skill body in Codex file documents the same lanes
as `rg` invocations.

### 6.4 Final report template (extends AGENTS.md §11)

```md
## Pattern-fix report
- Reported case fixed: <yes/no>
- Defect class: <L?, optionally + C1/C2>
- Invariant enforced: <one sentence>
- Fix level applied: <Level 0–6, with reason>

## Sibling search
- Lane 1 (admin-console):  <findings or "clean">
- Lane 2 (canonical):      <findings or "clean">
- Lane 3 (per-domain):     <findings or "clean">
- Lane 4 (docs+migrations): <findings or "clean">

## Sibling resolution
- Fixed: <list>
- Ruled out (with reason): <list>
- Out of scope (with reason): <list>

## Regression coverage
- <test path> — <invariant covered>

## Verification
- <command> — <result>
- <command not run> — <why>

## Self-review (extends AGENTS.md §11 Self-review)
- Scope control:
- Invariants preserved (data-agent contract, A–G semantics, _VALID_DOMAINS,
  evidence shape, V001–V018 history, secrets boundary):
- Patch-only risk:
- Rollback / checkpoint:

## Skip-but-note epilogue (only if anti-trigger fired)
- Sibling risk: <where to look> — not investigated per user request.
```

---

## 7. File layout and DRY strategy

### 7.1 Files created by implementation

```
.agents/skills/pattern-repair/SKILL.md          (Codex; ~250 lines)
.claude/skills/pattern-repair/SKILL.md          (Claude Code; ~250 lines)
docs/superpowers/specs/2026-05-08-pattern-repair-skill-design.md  (this file)
```

**Distribution model (per repo `.gitignore`):** `.agents/skills/` and `.claude/`
are excluded from version control by intentional convention. The two SKILL.md
files are therefore **local per developer**. Each developer recreates them by
following this spec + the implementation plan. The spec and plan ARE tracked,
so the recreation recipe propagates with the repo. `AGENTS.md §0` explicitly
labels the skill as "Recommended" and `AGENTS.md §4` (Pattern-fix work) provides
a plain-workflow fallback for sessions where the skill file is absent.

### 7.2 Mirror invariant (top of each SKILL.md)

Both SKILL.md files **must** open with:

```text
> This skill is mirrored at the other CLI's path. If you change one, change the
> other. Differences are limited to the platform-adaptation block (§<n>): tool
> names (Skill vs $skill-name), parallel agent dispatch (Claude only), and
> trigger announcement style.
```

### 7.3 Allowed differences between the two files

| Concern | Codex SKILL.md | Claude SKILL.md |
|---|---|---|
| Trigger announcement | "I am entering pattern-repair." | `Skill` tool invocation; Claude's announce-skill style |
| Sibling search | Sequential `rg` commands (per AGENTS.md §6) | Parallel `Explore` agents (lanes per §6.3) |
| TodoWrite | Not used | Use TaskCreate per phase, completed-as-done |
| Subagent reference | None | May suggest `general-purpose` or `Explore` for big lanes |
| Final report | AGENTS.md §11 alignment | Same template, identical text |

Everything else (taxonomy, fix-level ladder, diagnosis block, anti-triggers,
skip-but-note epilogue, examples) is **identical text**.

### 7.4 Sync ritual

When editing one file, run `diff` against the other. The design doc requires the
opener of the PR to confirm both files moved together. No automation enforces
this — it is a manual discipline backed by the mirror banner.

---

## 8. Minimal patches to AGENTS.md and CLAUDE.md

### 8.1 AGENTS.md (5 small touches, all in-place)

| Section | Change |
|---|---|
| §0 (line 32–41) | No change — table already includes pattern-fix row. |
| §4.3 (line 199–213) | Compress the 7-line inline fallback template; replace with: "Invoke `pattern-repair`. If skill is unavailable, fall back to the 9-line Diagnosis block in `.agents/skills/pattern-repair/SKILL.md` Phase 1 and the Pattern-fix report in §11." |
| §5 (line 240) | No change — row already exists. |
| §6 (line 263–273) | No change — searches still useful for non-pattern-fix work. |
| §7 | No change — invariants are still authoritative. |
| §11 (line 467–475) | Add one cross-reference line: "See `.agents/skills/pattern-repair/SKILL.md` for full sibling-search discipline." |

### 8.2 CLAUDE.md (1 small touch)

| Section | Change |
|---|---|
| §8 Pattern-fix paragraph (line 194) | Update path reference: `invoke the pattern-repair skill (Claude Code: .claude/skills/pattern-repair/SKILL.md; Codex: .agents/skills/pattern-repair/SKILL.md) when the user says ...`. The rest unchanged. |

Both patch sets are pure additive cross-links + one fallback compression. No
section restructure. No invariant change.

---

## 9. Testing the skill itself

This is a *behavioral* skill — its correctness is not unit-testable. We verify it
through:

### 9.1 Activation tests (manual)

Create three short scenarios in a scratch session and confirm the skill activates:

- **A. Explicit trigger:** "我发现 paper 的 evidence 缺 fetched_at, 这个不要打补丁，看看其他领域是不是也有同样问题。" → must activate Claude version.
- **B. Auto-signal C:** "professor enricher 和 company enricher 都返回了同样的错。" → must activate.
- **C. Anti-trigger:** "professor 这一处 enricher 写错了, 只修这一处." → must NOT activate; final report includes skip-but-note line.

### 9.2 Output-shape tests

Confirm the Diagnosis block, sibling-search lanes, and Pattern-fix report all match
the templates in §6.2 / §6.3 / §6.4.

### 9.3 Length budget check

`wc -l` on each SKILL.md must be ≤ 280 lines.

### 9.4 Mirror-diff check

`diff .agents/skills/pattern-repair/SKILL.md .claude/skills/pattern-repair/SKILL.md`
should show only the differences enumerated in §7.3.

---

## 10. Retroactive sweep (one-time, addresses pre-existing half-baked artifacts)

Pattern-repair as designed is **forward-looking**: it triggers when the user reports
a new bug, and only sweeps the area that bug touches. It does **not** proactively
scan dormant areas of the repo.

The user has accumulated half-baked artifacts from prior single-point fixes (visible
in current `git status` showing 60+ modified files, in `docs/index.md` rows marked
🟡 / 🚧 / 📝, and in implicit "we fixed X but never finished Y" debt). These need a
one-time sweep, gated by the same pattern-repair discipline.

### 10.1 Hotspot identification (inputs to the sweep)

Sources from which sweep targets are identified:

```text
1. Current working-tree drift:    `git status` modified files not part of an active task
2. Doc-status matrix:              `docs/index.md` rows marked 🟡 / 🚧 / 📝
3. Recent revert/rollback hints:   `git log --oneline -50 | rg "revert|partial|TODO|WIP"`
4. Open spec/handoff with no review: files in `.agents/specs/` or `.agents/handoffs/`
                                   that have no matching `.agents/reviews/` entry
5. User-named hotspots:            user can name areas they know are messy
```

Each identified hotspot becomes **one sweep slice**.

### 10.2 Sweep-slice protocol (each hotspot is a mini pattern-repair invocation)

Each slice runs the full pattern-repair flow but scoped to the hotspot:

```text
1. Diagnosis block (Phase 1)        what invariant is violated; defect class L1–L7 + C1/C2
2. Targeted sibling search          scoped to the hotspot's natural lanes (often 1–2 lanes,
                                    not full 4-lane fan-out)
3. Outcome decision (one of):
   3a. Real defect → apply pattern-repair fix at appropriate level (1–4)
   3b. Doc-only drift → invoke `compound-engineering:ce-compound-refresh` for
                        `docs/solutions/` items, or `ce-doc-review` for other docs
   3c. Genuinely abandoned/superseded → delete or mark deprecated with explicit reason
   3d. Out of scope (no current capacity) → file `.agents/reviews/<date>-sweep-<slug>.md`
                                            with what was found and parking lot rationale
4. Mini-report                      same shape as §6.4 final report, archived in
                                    `.agents/reviews/<date>-sweep-<slug>.md`
```

### 10.3 Hard limits on the sweep

| Limit | Reason |
|---|---|
| Each sweep slice ≤ 1 day of effort. Larger → escalate to a separate `.agents/specs/` plan, do not silently expand. | Avoid scope explosion; preserve user control. |
| No sweep modifies V001–V018 migration history. | Repo invariant from `CLAUDE.md §7`. |
| No sweep silently changes public APIs, serialized formats, benchmark output formats, or data contracts. | Repo invariant from `AGENTS.md §0`. |
| Each slice produces an `.agents/reviews/` entry, even for "ruled out" outcomes. | Future-proofs against re-discovering the same hotspot. |
| Sweep does not commit anything without explicit user approval per slice. | `CLAUDE.md` global rule: never commit unless asked. |

### 10.4 Sweep completion criteria

The retroactive sweep is "done" when:

- All hotspots from §10.1 have a slice outcome (fixed / doc-only-refreshed / abandoned / parked).
- A summary report at `.agents/reviews/<date>-pattern-repair-retroactive-sweep.md` enumerates all slices and outcomes.
- `docs/index.md` status matrix is updated to reflect post-sweep reality (reduced 🟡 / 🚧 entries; new ✅ where applicable).

### 10.5 The sweep is bounded, not recurring

This is a **one-time** operation triggered when the skill ships. After the sweep,
incremental pattern-repair invocations (driven by new bug reports) catch new
regressions. There is **no periodic re-sweep ritual**. If half-baked debt
accumulates again later, that is itself a pattern-repair-class signal indicating
the skill is being skipped — the right response is to fix the *process*, not
schedule recurring sweeps.

### 10.6 Sweep precedence relative to skill-shipping

Recommended ordering (writing-plans should respect this):

```text
[Slices 1–4: build & patch]   →  ship pattern-repair, no behavior change yet
[Slice 5: activation tests]   →  verify skill triggers correctly in scratch session
[Slice 6: doc commit]         →  spec + skill files committed
[Slice 7: retroactive sweep]  →  apply skill protocol to identified hotspots
                                 (this is when the existing mess actually gets cleaned)
```

The sweep is **last** because: (a) it depends on the skill being shipped to use as
its protocol; (b) putting it first risks landing the cleanup in a half-baked state
and undermining the skill's credibility on day one.

---

## 11. Implementation plan handoff

The next step is to invoke `superpowers:writing-plans` to break this design into
implementation slices. Expected slices:

1. Write `.claude/skills/pattern-repair/SKILL.md` from §3 / §4 / §5 / §6 / §7.
2. Write `.agents/skills/pattern-repair/SKILL.md` mirror per §7.
3. Patch `AGENTS.md` per §8.1.
4. Patch `CLAUDE.md` per §8.2.
5. Run §9.1 activation tests in a scratch conversation.
6. Commit design doc + skill files + patches together (user-approved).
7. Run retroactive sweep per §10 (bounded, one-time, hotspot-driven).

---

## 12. Risks and assumptions

### 11.1 Risks

| Risk | Mitigation |
|---|---|
| Two-file drift over time | Mirror banner at top of each file; design doc lists allowed differences in §7.3. |
| Skill body still too long → low trigger probability | 280-line hard cap (§2 D10); pre-merge `wc -l` check; design lives outside the skill. |
| User explicit "narrow patch" gets ignored | Anti-trigger logic in §3.3 + skip-but-note epilogue logged in `AGENTS.md §11` extension. |
| `Explore` agents don't find sibling patterns the user can see | Phase 8 (post-fix sibling re-check) catches it; users can call out the miss in next turn. |
| Trigger description false-positives in unrelated session | All four auto-signals are gated; explicit triggers require keywords. False-positive empirically low. |

### 11.2 Assumptions

- Two SKILL.md files won't change more than ~2× per year after initial ship; manual sync is fine at that rate.
- `AGENTS.md §6` search commands stay roughly current; if the four-domain layout shifts (e.g., a fifth domain), §6.3 lane definitions must update.
- `superpowers` skill loader will respect the `description` frontmatter for triggering.

---

## 13. Open questions deliberately closed

- "Should we add a meta-skill for half-baked scaffolding?" — **No.** YAGNI; one occurrence; existing skills cover related needs.
- "Should `AGENTS.md` be restructured to consolidate pattern-fix content?" — **No.** Blast radius too high. Cross-links suffice.
- "Should the skill auto-trigger on any bug report?" — **No.** That defeats `tiny-fix` for genuinely small bugs and clutters every session.
- "Should `ce-debug` be deprecated?" — **No.** Pattern-repair is orthogonal; `ce-debug` still useful when no sibling concern.

---

## 14. Acceptance criteria

This spec is implementation-ready when reviewer confirms:

1. ☐ All architecture decisions D1–D10 are explicit, justified, and locked.
2. ☐ Trigger model (§3) covers explicit / auto / anti / handoff cases without contradiction.
3. ☐ Defect-class taxonomy (§4) is MiroThinker-specific, not generic, with concrete examples.
4. ☐ Sibling-search lanes (§6.3) match current MiroThinker repo layout.
5. ☐ Final report template (§6.4) extends `AGENTS.md §11` rather than replacing it.
6. ☐ Patches to `AGENTS.md` (§8.1) and `CLAUDE.md` (§8.2) are minimal and additive.
7. ☐ Both SKILL.md files will fit within 280-line cap and follow mirror discipline (§7).
8. ☐ Activation tests (§9.1) are concrete enough to run in a scratch session.
9. ☐ Retroactive sweep (§10) has hotspot identification, slice protocol, hard limits, completion criteria, and sequencing relative to skill ship.
