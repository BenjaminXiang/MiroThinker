# Pattern-Repair Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a `pattern-repair` skill (mirrored across `.claude/skills/` and `.agents/skills/`) that forces systemic fix discipline — Diagnosis block → defect classification → sibling search → shared fix → regression matrix — and apply it retroactively to clean up accumulated half-baked artifacts in the MiroThinker repo.

**Architecture:** Two ~250-line SKILL.md files (full mirror with 5 enumerated allowed differences). Skill body is the protocol owner; `AGENTS.md` and `CLAUDE.md` get small additive cross-link patches only. After ship, run a one-time retroactive sweep over identified hotspots using the same skill protocol.

**Tech Stack:** Markdown (skill files), git, ripgrep (`rg`), `Explore` / `general-purpose` Claude Code subagents (Claude side); Codex `rg` (Codex side). No code in libs/apps/.

**Spec:** `docs/superpowers/specs/2026-05-08-pattern-repair-skill-design.md` (read first; this plan inlines all content the executor needs but the spec is the source of truth for design rationale).

**Working directory:** `/home/longxiang/MiroThinker`

**Hard constraints (from spec D1–D10):**
- Each SKILL.md ≤ 280 lines (D1, D10)
- Two SKILL.md files mirror, only 5 enumerated differences (D8, §7.3)
- Never commit without explicit user approval (CLAUDE.md global rule)
- Never modify V001–V018 alembic migration history
- Trigger words MUST appear in skill `description` frontmatter

---

## File Structure

| Path | Status | Responsibility |
|---|---|---|
| `.claude/skills/pattern-repair/SKILL.md` | **Create** | Claude Code skill: trigger description, workflow phases, defect taxonomy, parallel Explore lanes, final report |
| `.agents/skills/pattern-repair/SKILL.md` | **Create** | Codex CLI skill: same body, Codex-tuned platform notes, sequential `rg` for sibling search |
| `AGENTS.md` | **Modify** | Compress §4.3 fallback template (line 199–213); add §11 cross-link |
| `CLAUDE.md` | **Modify** | Update §8 path reference (line 194) |
| `docs/superpowers/specs/2026-05-08-pattern-repair-skill-design.md` | Already exists | Spec; commit as part of ship |
| `docs/superpowers/plans/2026-05-08-pattern-repair-skill.md` | This file | Plan; commit as part of ship |
| `.agents/reviews/2026-05-XX-pattern-repair-retroactive-sweep.md` | Create in Task 10 | Sweep summary |
| `.agents/reviews/2026-05-XX-sweep-<slug>.md` | Create per hotspot in Task 9 | Per-slice sweep mini-report |

---

## Dependency Graph

```text
T1 (Claude SKILL)  ─┬─→ T3 (mirror+length verify) ──→ T6 (activation tests) ──→ T7 (commit) ──→ T8 → T9 → T10
T2 (Codex SKILL)   ─┘
T4 (AGENTS.md)     ──────────────────────────────────→ T6
T5 (CLAUDE.md)     ──────────────────────────────────→ T6
```

T1, T2, T4, T5 are independent and can run in parallel. T3 needs T1 and T2. T6 needs all four. T7 needs T6. T8/T9/T10 are sequential and gated by T7.

---

## Task 1: Write Claude Code SKILL.md

**Files:**
- Create: `.claude/skills/pattern-repair/SKILL.md`

**Acceptance:**
- File exists at exact path
- `wc -l` reports ≤ 280
- Frontmatter has `name: pattern-repair` and `description:` containing all trigger words from spec §3.1
- All 9 workflow phases (Diagnosis through Self-review) present
- All 7 primary + 2 cross-cutting defect classes present in §5
- All 4 sibling-search lanes documented in §4 Phase 2

- [ ] **Step 1: Create directory**

```bash
mkdir -p /home/longxiang/MiroThinker/.claude/skills/pattern-repair
```

Expected: directory created, no output on success.

- [ ] **Step 2: Write SKILL.md with the exact content below**

Path: `/home/longxiang/MiroThinker/.claude/skills/pattern-repair/SKILL.md`

Content (copy verbatim — this IS the skill body, not a draft):

````markdown
---
name: pattern-repair
description: Use for systemic bug repair, repeated defects, patch-only fixes, escaped defects, sibling-pattern search, invariant extraction, and regression-test-driven fixes. Trigger when the user says 系统性, 同类问题, 类似问题, 不要打补丁, 不要单点修复, 根因, 反复出现, 全面检查, 跨领域同样问题, 第二次出现, patch-only, systemic, recurring, regression, escaped defect, sibling pattern, root cause, defect class, system-wide, second time, not-just-this-case, OR when a bug appears after a prior fix in the same feature area in the current session, OR when the user describes the same symptom in multiple files / nodes / domains. Skip when the user explicitly says 只修这一处, narrow patch, don't broaden, minimal change, or has pasted a complete diff or patch.
---

# Pattern Repair Skill (Claude Code)

> **Mirror banner.** This skill is mirrored at `.agents/skills/pattern-repair/SKILL.md` for Codex CLI. The two files share their body and differ only in five enumerated places (§9 here; §7.3 of `docs/superpowers/specs/2026-05-08-pattern-repair-skill-design.md`). When you change one, change the other.

## 0. Core principle

Treat the user's reported example as a symptom, not the task. The real task is:

```text
reported symptom → expected invariant → defect class → sibling search → shared fix
                 → regression coverage → verification evidence
```

A successful repair must answer:

```text
What invariant was broken?
Where else could the same invariant be broken?
What fix prevents the class of bug, not only this example?
What regression test will fail if the same class returns?
```

## 1. When this skill activates

### 1.1 Explicit trigger words (any of these in the user's message)

```text
中文: 系统性、同类问题、类似问题、不要打补丁、不要单点修复、根因、
      反复出现、全面检查、跨领域同样问题、第二次出现
英文: patch-only, systemic, recurring, regression, escaped defect,
      sibling pattern, root cause, defect class, system-wide, second time,
      not-just-this-case
```

### 1.2 Auto-detection signals (skill self-checks before activating)

| Signal | Detection | Confidence |
|---|---|---|
| **A. In-session repeat** | Same file path or function name appeared in an earlier user turn this session | High |
| **B. Recent-commit hint** | `git log --oneline -10` shows `fix(...)` / `revert(...)` touching same file as current bug | Medium — ask user one clarifying line before fully activating |
| **C. Multi-file pattern** | User mentions multiple sites, nodes, or domains | Very high |
| **D. Cross-domain shared surface** | Bug touches `_VALID_DOMAINS`, `evidence`, `run_id`, `canonical/`, `contracts.py`, four-domain shared invariants | Medium-high |

### 1.3 Anti-triggers (skill MUST NOT activate)

| Signal | Action |
|---|---|
| User says "只修这一处" / "narrow patch" / "don't broaden" / "minimal change" | Run tiny-fix; **append** to final report: `Sibling risk: <where to look> — not investigated per user request.` |
| Change is typo / docs / comments / format-only / rename | Tiny-fix |
| User pasted a complete diff or patch | Tiny-fix |
| `.agents/specs/` or `.agents/handoffs/` text-only edit | Tiny-fix |

## 2. Hard rules

1. Do not edit code until Phase 1 Diagnosis block is emitted.
2. Pattern-fix work is **never** a tiny fix (per `AGENTS.md §0`). Do not classify as tiny.
3. Do not fix only the reported case unless sibling search (Phase 2) proves no class.
4. Do not weaken tests, schemas, evidence checks, Pydantic validation, or safety checks to make a fix pass.
5. Preserve V001–V018 alembic migration history. Migration changes need their own slice.
6. Preserve public APIs, serialized formats, classifier A–G semantics, `_VALID_DOMAINS` filter, evidence shape, `run_id` traceability, secrets boundary.
7. Never claim a verification command passed unless it ran successfully in the current session.

## 3. Triple-skill routing (handoff)

| Situation | Skill |
|---|---|
| Explicit trigger word OR auto-signal C | `pattern-repair` (skip reproduce phase) |
| Auto-signal A or B fired | `pattern-repair`, ask one clarifying Q first |
| Auto-signal D alone | `pattern-repair`, optional reproduce |
| Bug not understood / not reproducible | `superpowers:systematic-debugging` first → re-evaluate triggers afterwards |
| Anti-trigger fired | tiny-fix + skip-but-note epilogue (§1.3) |

`compound-engineering:ce-debug` is deprioritized when pattern-repair triggers fire.

## 4. Workflow phases

### Phase 1 — Diagnosis block (REQUIRED before any edit)

Emit this block exactly:

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

### Phase 2 — Sibling search (parallel, default 4 lanes)

Dispatch parallel `Explore` agents using the `Agent` tool. Use `general-purpose` instead for lanes >100 files.

```text
Lane 1 — admin-console
  Roots: apps/admin-console/backend/api/, services/, storage/, tests/
  Brief: <invariant>; find sites that violate or might violate it.

Lane 2 — canonical / contracts
  Roots: apps/miroflow-agent/src/data_agents/{canonical,contracts.py,
         evidence.py,linking,normalization,publish}.py
  Brief: <invariant>; check shared layer.

Lane 3 — per-domain
  Roots: apps/miroflow-agent/src/data_agents/{company,professor,paper,patent}/,
         apps/miroflow-agent/tests/
  Brief: <invariant>; audit each of four domains independently.

Lane 4 — docs + migrations + scripts
  Roots: docs/, apps/miroflow-agent/alembic/versions/,
         apps/miroflow-agent/scripts/run_*
  Brief: <invariant>; find stale docs (C2) and migration drift (L4).
```

If the bug is clearly local (auto-signal C absent, user only named one file, defect class L1 likely), run a single scoped lane instead of full 4-lane fan-out.

Reference search recipes: `AGENTS.md §6`.

### Phase 3 — Decide invariant

State the invariant in one sentence. Lock before editing.

### Phase 4 — Implementation plan (in-message; no separate file unless Level 6)

```text
Invariant to enforce:
Sibling findings (fixed / ruled out / out of scope):
Fix level (1–6):
Slices:
Regression tests:
Verification commands:
Rollback path:
Risks:
```

### Phase 5 — Implement

Smallest coherent shared fix. No drive-by refactor. Honor §2 hard rules.

### Phase 6 — Regression tests

Tied to invariant; parameterize when class spans multiple sites. See `AGENTS.md §9` matrix.

### Phase 7 — Verification

Narrowest relevant first. Use `AGENTS.md §10` command palette. Do not claim pass without running.

### Phase 8 — Post-fix sibling re-check

Rerun the most important sibling search. Report remaining matches and why they are safe / out of scope.

### Phase 9 — Self-review + final report (template in §6)

## 5. Defect class taxonomy

### 5.1 Primary classes (pick one)

| ID | Class | Typical clue | Preferred fix level |
|---|---|---|---|
| **L1** | Local Branch Bug | Only one branch / node / route violates the invariant | Level 1 |
| **L2** | Duplicated Logic | Same logic copied across files (e.g., evidence handled differently in each of 4 domains) | Level 2–3 |
| **L3** | Missing Shared Helper / Boundary Guard | Many call sites re-implement normalization / validation / routing / formatting | Level 3 or 4 |
| **L4** | Schema / State Contract Drift | V001–V018 + DDL + Pydantic + storage + tests not synchronized; or state enters illegal form | Level 4 + matrix |
| **L5** | Routing / Classification Drift | A–G semantics, `_VALID_DOMAINS`, fusion / rerank, SessionContext entity stack inconsistent | Level 4–5 |
| **L6** | Evidence / Provenance Violation | `run_id` / `source_url` / `fetched_at` / `confidence` weakened or missing | Level 4 + matrix |
| **L7** | Provider / Integration Boundary Failure | Anthropic / Qwen / Dashscope / Milvus / Postgres errors leaking; missing fallback | Level 3–4 |

### 5.2 Cross-cutting (always check alongside primary)

- **C1. Test-Matrix Gap** — single-case test exists; add parameterized matrix.
- **C2. Stale-Doc Revival** — code follows legacy doc; check `docs/index.md` for authoritative.

## 6. Final report template (extends `AGENTS.md §11`)

```md
## Pattern-fix report
- Reported case fixed: <yes/no>
- Defect class: <L?, optionally + C1/C2>
- Invariant enforced: <one sentence>
- Fix level applied: <Level 0–6, with reason>

## Sibling search
- Lane 1 (admin-console):   <findings or "clean">
- Lane 2 (canonical):       <findings or "clean">
- Lane 3 (per-domain):      <findings or "clean">
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

## Self-review (extends AGENTS.md §11)
- Scope control:
- Invariants preserved (data-agent contract, A–G, _VALID_DOMAINS, evidence,
  V001–V018, secrets):
- Patch-only risk:
- Rollback / checkpoint:

## Skip-but-note epilogue (only if anti-trigger fired)
- Sibling risk: <where to look> — not investigated per user request.
```

## 7. Fix-level ladder

```text
Level 0: No code change — reported behavior expected / stale / setup-caused.
Level 1: Local patch + regression test — sibling search confirmed singleton.
Level 2: Local helper / table-driven local logic — multiple branches in one file.
Level 3: Shared domain helper — multiple files in same domain.
Level 4: Boundary guard / contract enforcement — many call sites can violate.
Level 5: Parameterized invariant matrix — class spans nodes / domains / providers.
Level 6: Re-plan — architectural contradiction; write `.agents/specs/` first.
```

**Default for systemic triggers:** Level 3 or 4. Drop to Level 1 only if sibling search proves no class.

## 8. Examples (MiroThinker-specific)

```text
"chat 路由 turn 2 域错"             → L5 + C1 (classifier/SessionContext + matrix)
"patent evidence 缺 fetched_at"     → L6 (cross-domain audit)
"V016 加列但 Pydantic 模型未跟"     → L4 + C2 (likely)
"Anthropic 5xx 透传到 /api/chat"    → L7 (client wrapper + failure tests)
"professor / company enricher 同 regex 写法不一" → L2 / L3 (helper)
```

## 9. Platform notes (Claude Code only)

This section differs in the Codex mirror — see `.agents/skills/pattern-repair/SKILL.md` §9.

- Announce activation explicitly using `Skill` tool style.
- Use `TaskCreate` per phase; mark completed when done.
- Sibling search defaults to **parallel** `Explore` agents (4 lanes). Use `general-purpose` for very large lanes.
- Avoid running `rg` in the main thread for sibling search — main context gets polluted; lane agents return synthesis only.

## 10. References

- Spec: `docs/superpowers/specs/2026-05-08-pattern-repair-skill-design.md`
- Project invariants: `AGENTS.md §7`
- Search recipes: `AGENTS.md §6`
- Report base template: `AGENTS.md §11`
- Tiny-fix vs pattern-fix decision: `AGENTS.md §0`, `CLAUDE.md §8`
- Codex mirror: `.agents/skills/pattern-repair/SKILL.md`
````

- [ ] **Step 3: Verify length and structure**

```bash
wc -l /home/longxiang/MiroThinker/.claude/skills/pattern-repair/SKILL.md
grep -c "^## " /home/longxiang/MiroThinker/.claude/skills/pattern-repair/SKILL.md
grep -E "^name: pattern-repair$" /home/longxiang/MiroThinker/.claude/skills/pattern-repair/SKILL.md
```

Expected: line count ≤ 280; section count ≥ 11 (§0 through §10); the `name:` line found exactly once.

- [ ] **Step 4: Verify all trigger words present in description**

```bash
grep -oP '系统性|同类问题|类似问题|不要打补丁|不要单点修复|根因|反复出现|全面检查|跨领域同样问题|第二次出现|patch-only|systemic|recurring|regression|escaped defect|sibling pattern|root cause|defect class|system-wide|second time|not-just-this-case' /home/longxiang/MiroThinker/.claude/skills/pattern-repair/SKILL.md | sort -u | wc -l
```

Expected: 21 (10 Chinese + 11 English unique trigger phrases). If less, the description got truncated — restore.

---

## Task 2: Write Codex CLI SKILL.md mirror

**Files:**
- Create: `.agents/skills/pattern-repair/SKILL.md`

**Acceptance:**
- File exists at exact path
- `wc -l` reports ≤ 280
- Frontmatter is identical to Claude version EXCEPT `description` may have minor wording adjustment (still must contain all 21 trigger words)
- §9 content differs per mirror rule (§7.3 of spec)
- Mirror banner points to Claude path

- [ ] **Step 1: Create directory** *(verify; should already exist)*

```bash
mkdir -p /home/longxiang/MiroThinker/.agents/skills/pattern-repair
ls /home/longxiang/MiroThinker/.agents/skills/pattern-repair/
```

Expected: empty directory exists.

- [ ] **Step 2: Write Codex SKILL.md with the exact content below**

Path: `/home/longxiang/MiroThinker/.agents/skills/pattern-repair/SKILL.md`

The content is **byte-identical to the Claude version above** EXCEPT for the five differences enumerated below. Copy the Claude version verbatim, then apply these substitutions:

**Diff 1 — Title (line ~7 of body):**

```diff
- # Pattern Repair Skill (Claude Code)
+ # Pattern Repair Skill (Codex CLI)
```

**Diff 2 — Mirror banner (the `> **Mirror banner.**` paragraph):**

```diff
- > **Mirror banner.** This skill is mirrored at `.agents/skills/pattern-repair/SKILL.md`
- > for Codex CLI. The two files share their body and differ only in five enumerated
- > places (§9 here; §7.3 of `docs/superpowers/specs/2026-05-08-pattern-repair-skill-design.md`).
- > When you change one, change the other.
+ > **Mirror banner.** This skill is mirrored at `.claude/skills/pattern-repair/SKILL.md`
+ > for Claude Code. The two files share their body and differ only in five enumerated
+ > places (§9 here; §7.3 of `docs/superpowers/specs/2026-05-08-pattern-repair-skill-design.md`).
+ > When you change one, change the other.
```

**Diff 3 — Phase 2 sibling search (in §4 Phase 2):**

Replace the paragraph **"Dispatch parallel `Explore` agents using the `Agent` tool. Use `general-purpose` instead for lanes >100 files."** with:

```text
Run the lane-scoped `rg` searches in sequence. The four lanes below partition the
MiroThinker repo by responsibility; pick the lanes that match your invariant.
Reference search recipes: `AGENTS.md §6`.
```

The lane block (Lane 1–4) stays as-is — it documents the same partition.

**Diff 4 — §9 Platform notes (full replacement):**

```diff
- ## 9. Platform notes (Claude Code only)
-
- This section differs in the Codex mirror — see `.agents/skills/pattern-repair/SKILL.md` §9.
-
- - Announce activation explicitly using `Skill` tool style.
- - Use `TaskCreate` per phase; mark completed when done.
- - Sibling search defaults to **parallel** `Explore` agents (4 lanes). Use `general-purpose` for very large lanes.
- - Avoid running `rg` in the main thread for sibling search — main context gets polluted; lane agents return synthesis only.
+ ## 9. Platform notes (Codex CLI only)
+
+ This section differs in the Claude mirror — see `.claude/skills/pattern-repair/SKILL.md` §9.
+
+ - Announce activation explicitly: state "Entering pattern-repair." before Phase 1.
+ - Sibling search runs `rg` sequentially per lane. The Claude mirror parallelizes via `Explore` agents — Codex CLI does not have that capability.
+ - Use `AGENTS.md §6` search recipes verbatim; tune the regex per invariant.
+ - When a lane returns >100 hits, narrow the regex with explicit field / function names rather than spending budget reading all hits.
```

**Diff 5 — §10 References:**

```diff
- - Codex mirror: `.agents/skills/pattern-repair/SKILL.md`
+ - Claude Code mirror: `.claude/skills/pattern-repair/SKILL.md`
```

- [ ] **Step 3: Verify length and structure**

```bash
wc -l /home/longxiang/MiroThinker/.agents/skills/pattern-repair/SKILL.md
grep -c "^## " /home/longxiang/MiroThinker/.agents/skills/pattern-repair/SKILL.md
grep "Codex CLI" /home/longxiang/MiroThinker/.agents/skills/pattern-repair/SKILL.md | head -3
```

Expected: line count ≤ 280; section count ≥ 11; "Codex CLI" appears in title and §9.

- [ ] **Step 4: Verify trigger words preserved**

```bash
grep -oP '系统性|同类问题|类似问题|不要打补丁|不要单点修复|根因|反复出现|全面检查|跨领域同样问题|第二次出现|patch-only|systemic|recurring|regression|escaped defect|sibling pattern|root cause|defect class|system-wide|second time|not-just-this-case' /home/longxiang/MiroThinker/.agents/skills/pattern-repair/SKILL.md | sort -u | wc -l
```

Expected: 21.

---

## Task 3: Verify mirror discipline and length budgets

**Files:**
- No file changes; verification only.

**Acceptance:**
- Diff between the two SKILL.md files matches exactly the 5 enumerated allowed differences
- Both files ≤ 280 lines
- Frontmatter `name:` is `pattern-repair` in both

- [ ] **Step 1: Run mirror diff and inspect**

```bash
diff -u /home/longxiang/MiroThinker/.claude/skills/pattern-repair/SKILL.md /home/longxiang/MiroThinker/.agents/skills/pattern-repair/SKILL.md
```

Expected: 5 hunks corresponding to Diffs 1–5 in Task 2 Step 2. No other hunks.

If the diff shows additional differences (e.g., typos, extra whitespace, accidental edit drift): fix them by re-running Task 2 Step 2 against the canonical Task 1 content.

- [ ] **Step 2: Confirm length budget on both**

```bash
for f in /home/longxiang/MiroThinker/.claude/skills/pattern-repair/SKILL.md /home/longxiang/MiroThinker/.agents/skills/pattern-repair/SKILL.md; do
  echo "$f: $(wc -l <"$f") lines"
done
```

Expected: each ≤ 280. If over, see Rollback below.

- [ ] **Step 3: Confirm name field in both**

```bash
grep -E "^name: pattern-repair$" /home/longxiang/MiroThinker/.claude/skills/pattern-repair/SKILL.md /home/longxiang/MiroThinker/.agents/skills/pattern-repair/SKILL.md
```

Expected: 2 lines, one per file.

**Rollback (if length budget breached):**
The skill body in Task 1 was sized to ~220 lines. If your version is over 280, you have likely added content beyond the spec. Compare against Task 1 Step 2 verbatim content and remove additions. Do not "compress" the templates in §1.2 / §4 / §6 / §7 — those are load-bearing copy-paste targets.

---

## Task 4: Patch AGENTS.md per spec §8.1

**Files:**
- Modify: `/home/longxiang/MiroThinker/AGENTS.md` lines 199–213 (compress §4.3 fallback)
- Modify: `/home/longxiang/MiroThinker/AGENTS.md` §11 (add cross-link line)

**Acceptance:**
- §4.3 inline 7-line fallback template removed; replaced with skill reference + fallback pointer
- §11 has one new cross-reference line pointing to skill
- Other sections of AGENTS.md unchanged (verify with `git diff --stat AGENTS.md`)

- [ ] **Step 1: Read current §4.3 to confirm exact bytes**

```bash
sed -n '199,213p' /home/longxiang/MiroThinker/AGENTS.md
```

Expected output (current state):

```text
### Pattern-fix work

Use `pattern-repair` when the user says 系统性、同类问题、类似问题、不要打补丁、不要单点修复、根因、反复出现、全面检查, patch-only, systemic, recurring, regression, escaped defect, or when a bug appears after a previous fix in the same feature area.

If `.agents/skills/pattern-repair/SKILL.md` exists, invoke it. If unavailable, do not silently tiny-fix; first produce:

```text
Reported symptom:
Expected invariant:
Why this may be systemic:
Search plan:
Proposed fix level:
Regression test plan:
Out of scope:
```
```

- [ ] **Step 2: Replace §4.3 fallback with compressed version using Edit tool**

In the Edit, replace this `old_string`:

```text
### Pattern-fix work

Use `pattern-repair` when the user says 系统性、同类问题、类似问题、不要打补丁、不要单点修复、根因、反复出现、全面检查, patch-only, systemic, recurring, regression, escaped defect, or when a bug appears after a previous fix in the same feature area.

If `.agents/skills/pattern-repair/SKILL.md` exists, invoke it. If unavailable, do not silently tiny-fix; first produce:

```text
Reported symptom:
Expected invariant:
Why this may be systemic:
Search plan:
Proposed fix level:
Regression test plan:
Out of scope:
```
```

With this `new_string`:

```text
### Pattern-fix work

Use `pattern-repair` when the user says 系统性、同类问题、类似问题、不要打补丁、不要单点修复、根因、反复出现、全面检查、跨领域同样问题、第二次出现, patch-only, systemic, recurring, regression, escaped defect, sibling pattern, root cause, defect class, system-wide, or when a bug appears after a previous fix in the same feature area.

Invoke `pattern-repair` (`.agents/skills/pattern-repair/SKILL.md`). If the skill file is unavailable, fall back to the 9-line Diagnosis block from `pattern-repair` Phase 1 and the Pattern-fix report in §11.
```

- [ ] **Step 3: Find AGENTS.md §11 Pattern-fix report block**

```bash
grep -n "## Pattern-fix report" /home/longxiang/MiroThinker/AGENTS.md
```

Expected: one line number around 467–468.

- [ ] **Step 4: Add cross-link line to §11**

Use Edit to replace:

```text
For pattern-fix work, also include:

```md
## Pattern-fix report
```

With:

```text
For pattern-fix work, also include the section below. The skill at `.agents/skills/pattern-repair/SKILL.md` produces an extended version with sibling-search lanes; use that when the skill is active.

```md
## Pattern-fix report
```

- [ ] **Step 5: Verify diff is minimal and intentional**

```bash
git diff --stat /home/longxiang/MiroThinker/AGENTS.md
git diff /home/longxiang/MiroThinker/AGENTS.md | head -80
```

Expected: 1 file changed; ~2 hunks; only the §4.3 and §11 areas touched. No other lines mutated.

**Rollback:** `git checkout -- AGENTS.md`

---

## Task 5: Patch CLAUDE.md per spec §8.2

**Files:**
- Modify: `/home/longxiang/MiroThinker/CLAUDE.md` line 194 (Pattern-fix paragraph in §8)

**Acceptance:**
- Pattern-fix paragraph references both `.claude/skills/` and `.agents/skills/` paths
- Triggers list aligned with skill description (no drift)
- Other lines unchanged

- [ ] **Step 1: Read current line 194 area to confirm exact bytes**

```bash
sed -n '192,198p' /home/longxiang/MiroThinker/CLAUDE.md
```

Expected: paragraph beginning `**Pattern-fix**: reach for ...`.

- [ ] **Step 2: Replace via Edit tool**

Replace `old_string`:

```text
**Pattern-fix**: reach for `.agents/skills/pattern-repair/SKILL.md` (or its plain-workflow fallback in AGENTS.md §4) when the user says 系统性 / 同类问题 / 不要打补丁 / 根因, or when a bug recurs after a previous fix. Pattern-fix is never a tiny fix.
```

With `new_string`:

```text
**Pattern-fix**: invoke the `pattern-repair` skill (Claude Code: `.claude/skills/pattern-repair/SKILL.md`; Codex: `.agents/skills/pattern-repair/SKILL.md`) when the user says 系统性 / 同类问题 / 不要打补丁 / 根因 / 反复出现 / 全面检查 / 跨领域同样问题, or when a bug recurs after a previous fix in the same area. Pattern-fix is never a tiny fix. See `AGENTS.md §4.3` for the Codex-side fallback.
```

- [ ] **Step 3: Verify diff is single-paragraph**

```bash
git diff --stat /home/longxiang/MiroThinker/CLAUDE.md
git diff /home/longxiang/MiroThinker/CLAUDE.md
```

Expected: 1 file, 1 hunk, lines around 194 only.

**Rollback:** `git checkout -- CLAUDE.md`

---

## Task 6: Activation tests in scratch session

**Files:**
- No file changes (manual verification).
- Optionally: log results in `.agents/reviews/2026-05-08-pattern-repair-activation-test.md` (optional, not required).

**Acceptance:**
- All three scenarios behave as documented in spec §9.1
- Skill activation announcement appears for A and B; does NOT appear for C
- Skip-but-note epilogue appears for C

These are **manual** tests run in a scratch Claude Code conversation (or Codex CLI session for the Codex skill). Each scenario is run in a fresh session with no prior history.

- [ ] **Scenario A: Explicit trigger**

Open a new Claude Code session in the repo root. Send this user message verbatim:

```
我发现 paper 的 evidence 缺 fetched_at, 这个不要打补丁，看看其他领域是不是也有同样问题。
```

**Expected behavior:**
- Claude announces activation of `pattern-repair`.
- Claude emits the 9-line Diagnosis block before any edit.
- Claude proposes 4-lane sibling search (or scoped subset with reasoning).

**Pass condition:** Diagnosis block present in first response; no edit attempted before block.
**Fail condition:** Claude jumps straight to editing `paper/evidence.py` (or similar) without the block.

If fail: re-check skill `description` frontmatter for trigger words; ensure `.claude/skills/pattern-repair/SKILL.md` is at the exact path; restart Claude Code.

- [ ] **Scenario B: Auto-signal C (multi-file pattern)**

Fresh session. User message:

```
professor enricher 和 company enricher 都返回了同样的错误格式。
```

**Expected behavior:** Same as Scenario A — skill activates because user mentioned multiple sites.

**Pass / fail conditions:** Same as A.

- [ ] **Scenario C: Anti-trigger (narrow patch)**

Fresh session. User message:

```
professor 这一处 enricher 的 normalization 写错了，只修这一处。
```

**Expected behavior:**
- Claude does **NOT** activate `pattern-repair`.
- Claude runs tiny-fix workflow per `AGENTS.md §0`.
- Claude's final report includes a one-line `Sibling risk: ...` epilogue.

**Pass condition:** No skill activation; tiny-fix runs; epilogue line appears.
**Fail condition:** Skill activates despite explicit "只修这一处".

If fail: review §1.3 anti-triggers; ensure the description frontmatter does not over-broaden activation.

- [ ] **Optional: Log results**

If you want a record, write to `.agents/reviews/2026-05-08-pattern-repair-activation-test.md`:

```md
# Pattern-Repair Activation Test — 2026-05-08

## Scenario A — Explicit trigger
- Result: PASS / FAIL
- Notes:

## Scenario B — Auto-signal C
- Result: PASS / FAIL
- Notes:

## Scenario C — Anti-trigger
- Result: PASS / FAIL
- Notes:
```

**Rollback:** No state changes from these tests (scratch sessions).

---

## Task 7: Get user approval and commit

**Files:**
- Commit: 4 tracked files
  - `AGENTS.md` (modified)
  - `CLAUDE.md` (modified)
  - `docs/superpowers/specs/2026-05-08-pattern-repair-skill-design.md` (new)
  - `docs/superpowers/plans/2026-05-08-pattern-repair-skill.md` (new — this file)
- **NOT committed (excluded by `.gitignore`):**
  - `.claude/skills/pattern-repair/SKILL.md` — created locally only
  - `.agents/skills/pattern-repair/SKILL.md` — created locally only

**Note on skill-file distribution.** `.gitignore` excludes `.agents/skills/`
(line 235, intentional per inline comment) and `.claude/` (line 214). The two
SKILL.md files therefore live **local per developer**. Each developer recreates
them by re-running Tasks 1+2 of this plan. The recreation recipe (the plan
itself) is tracked, so the procedure propagates even if the artifacts don't.
`AGENTS.md §4 (Pattern-fix work subsection)` provides a plain-workflow fallback
when the skill file is absent in a session.

**Acceptance:**
- User has explicitly said "commit" (per CLAUDE.md global rule)
- Commit message follows repo convention (recent: `feat(W13-...)` / `docs(W13-...)` / `fix(W13-...)`)
- Commit includes only the 6 files listed above

- [ ] **Step 1: Show user the staged-state preview**

```bash
git status --short
git diff --stat AGENTS.md CLAUDE.md
ls -la .claude/skills/pattern-repair/ .agents/skills/pattern-repair/
```

Show the user this output and ask: "All 6 files ready. Commit now? Suggested message:
`feat(harness): add pattern-repair skill (Claude + Codex mirror) + spec/plan`"

**STOP HERE until user explicitly approves.** Do not proceed to Step 2 without user saying "yes" / "commit" / "go".

- [ ] **Step 2: Stage exactly these files and commit (only after user approval)**

```bash
cd /home/longxiang/MiroThinker
git add .claude/skills/pattern-repair/SKILL.md \
        .agents/skills/pattern-repair/SKILL.md \
        AGENTS.md \
        CLAUDE.md \
        docs/superpowers/specs/2026-05-08-pattern-repair-skill-design.md \
        docs/superpowers/plans/2026-05-08-pattern-repair-skill.md

git status --short
```

Expected: exactly those 6 files staged; nothing else (e.g., no stray modifications from other ongoing work).

If `git status` shows files you did not intend to stage: **STOP**, run `git restore --staged <file>` to unstage them. Do not commit until staged set is exactly the 6.

- [ ] **Step 3: Create the commit**

```bash
git commit -m "$(cat <<'EOF'
feat(harness): add pattern-repair skill (Claude + Codex mirror) + spec/plan

Ship pattern-repair skill mirrored across .claude/skills/ and .agents/skills/
to enforce systemic-fix discipline (Diagnosis -> defect class -> sibling
search -> shared fix -> regression matrix). Patches AGENTS.md and CLAUDE.md
with minimal cross-references (no structural changes). Spec and plan archived
under docs/superpowers/.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"

git log --oneline -1
```

Expected: one new commit on current branch with the message above.

**Rollback:** `git reset --soft HEAD~1` (keeps file changes; only undoes the commit).

---

## Task 8: Retroactive sweep — hotspot identification

**Files:**
- Create: `.agents/reviews/2026-05-08-pattern-repair-retroactive-sweep-hotspots.md`

**Acceptance:**
- Hotspot list compiled from all 5 sources in spec §10.1
- Each hotspot has: source category, file/area, why-suspected, planned slice owner (skill / `ce-compound-refresh` / `ce-doc-review` / abandon)
- User has reviewed and pruned the list before Task 9 begins

- [ ] **Step 1: Source 1 — current working-tree drift**

```bash
cd /home/longxiang/MiroThinker
git status --short | grep -v "^?? " | head -100
```

Expected: list of M/D/A files. Capture each unique top-level area (e.g., `apps/admin-console/backend/`, `apps/miroflow-agent/src/data_agents/professor/`).

- [ ] **Step 2: Source 2 — doc-status matrix**

```bash
grep -E "🟡|🚧|📝" /home/longxiang/MiroThinker/docs/index.md | head -50
```

Capture each row showing 🟡 / 🚧 / 📝 with the doc name and current status note.

- [ ] **Step 3: Source 3 — recent revert/rollback hints**

```bash
cd /home/longxiang/MiroThinker
git log --oneline -50 | rg -i "revert|partial|TODO|WIP|rollback"
```

Capture each matching commit + the file area it touched (use `git show --stat <hash>` for top entries).

- [ ] **Step 4: Source 4 — open spec/handoff with no review**

```bash
cd /home/longxiang/MiroThinker
ls .agents/specs/ .agents/handoffs/ .agents/reviews/ 2>/dev/null
```

Then for each spec/handoff filename, check whether `.agents/reviews/` has a matching slug. Open ones without matching reviews are candidates.

- [ ] **Step 5: Source 5 — user-named hotspots**

Ask the user: "From your knowledge, what areas of the codebase do you suspect carry half-finished work that the previous four sources missed?"

Capture each user-named area.

- [ ] **Step 6: Compile hotspot doc**

Write to `/home/longxiang/MiroThinker/.agents/reviews/2026-05-08-pattern-repair-retroactive-sweep-hotspots.md`:

```md
# Retroactive Sweep — Hotspot Inventory (2026-05-08)

| # | Source | Area / file | Why suspected | Proposed owner |
|---|---|---|---|---|
| 1 | working-tree | <path> | <why> | skill / ce-compound-refresh / ce-doc-review / abandon |
| 2 | doc-matrix   | <doc>  | <why> | ... |
| 3 | revert-hints | <commit + path> | <why> | ... |
| 4 | open-specs   | <spec name> | <why> | ... |
| 5 | user-named   | <area> | <why> | ... |
```

Replace placeholder rows with real entries from Steps 1–5. There may be 5 entries or 50 — the size depends on actual repo state.

- [ ] **Step 7: User review and pruning**

Show the user the hotspot file. Ask: "This is the proposed sweep target list. Mark any you want to drop or batch differently before Task 9 begins."

**STOP HERE until user has reviewed and approved the list.** The number of slices in Task 9 depends on this approved list.

**Rollback:** `rm /home/longxiang/MiroThinker/.agents/reviews/2026-05-08-pattern-repair-retroactive-sweep-hotspots.md`

---

## Task 9: Retroactive sweep — execute slices

**Files:**
- Per hotspot: create `.agents/reviews/2026-05-08-sweep-<slug>.md`
- Per real-defect outcome: code changes per pattern-repair flow
- Per doc-only outcome: invoke `compound-engineering:ce-compound-refresh` or `ce-doc-review`

**Acceptance:**
- Each hotspot from Task 8 has one slice with one outcome
- Each slice produces an `.agents/reviews/2026-05-08-sweep-<slug>.md` file (per spec §10.2)
- No slice exceeds 1 day of effort (per spec §10.3); larger ones escalated to a new `.agents/specs/` plan
- No V001–V018 alembic migration history modified
- No public API / serialized format / data contract silently changed
- No commits without explicit user approval per slice

This is a **template-driven loop** — repeat Steps 1–7 for each hotspot in the Task 8 inventory.

For each hotspot (call its slug `<slug>`):

- [ ] **Step 1: Activate `pattern-repair` skill on this hotspot**

In a fresh Claude Code session (or continue current session if context allows), state:

```
Run pattern-repair on hotspot <slug> from
.agents/reviews/2026-05-08-pattern-repair-retroactive-sweep-hotspots.md row #<N>.
Treat the hotspot description as the reported symptom.
```

The skill must activate (auto-signal D / explicit trigger).

- [ ] **Step 2: Phase 1 — Diagnosis block**

The skill emits the 9-line block. Capture it. If the diagnosis reveals the hotspot is "doc-only drift" or "abandoned/superseded", skip to Step 5.

- [ ] **Step 3: Phase 2 — Sibling search (scoped)**

Spec §10.2 says sweep slices may use 1–2 lanes (not full 4-lane fan-out). Choose lanes based on the hotspot's area:
- Working-tree drift in `apps/admin-console/` → Lane 1 only
- Working-tree drift in a single domain → Lane 3 scoped to that domain
- `_VALID_DOMAINS` or evidence drift → Lane 2 + Lane 3
- Stale-doc → Lane 4 only

Run lane(s) and capture findings.

- [ ] **Step 4: Phase 3–7 — Implement, verify per skill**

Honor §2 hard rules (no V001–V018 changes, no API drift, no test weakening). Run narrowest verification per `AGENTS.md §10`.

If at any point the slice expands beyond 1 day of effort: STOP. Write `.agents/specs/2026-05-08-sweep-<slug>-escalated.md` describing what was found and what still needs doing. Mark the slice outcome as "escalated" (not "fixed").

- [ ] **Step 5: Outcome decision and mini-report**

Pick exactly one outcome per spec §10.2:
- **3a. Real defect fixed** — code change applied
- **3b. Doc-only drift** — invoke `compound-engineering:ce-compound-refresh` (for `docs/solutions/`) or `ce-doc-review` (for other docs); no manual code change
- **3c. Abandoned / superseded** — delete the file or add a deprecation marker with explicit reason
- **3d. Out of scope (parked)** — file the report explaining why deferred, no code change

Write `/home/longxiang/MiroThinker/.agents/reviews/2026-05-08-sweep-<slug>.md` using the §6 final report template, with one extra line at the top:

```md
**Sweep slice outcome:** <3a-fixed | 3b-doc-only | 3c-abandoned | 3d-parked | escalated>
```

- [ ] **Step 6: User approval per slice**

Show the user the mini-report and any code changes. Ask: "Slice `<slug>` produced this outcome. Commit now, or batch with later slices?"

**STOP HERE until user explicitly approves.** Do not commit unilaterally.

- [ ] **Step 7: Commit (per slice or batched)**

Per user choice in Step 6:

```bash
cd /home/longxiang/MiroThinker
git add <files for this slice>
git commit -m "$(cat <<'EOF'
fix(sweep-<slug>): <one-line summary of slice outcome>

Sweep slice from pattern-repair retroactive sweep. Outcome: <3a/3b/3c/3d>.
Report: .agents/reviews/2026-05-08-sweep-<slug>.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Loop back to Step 1 for the next hotspot.

**Rollback per slice:** `git reset --soft HEAD~1` and `git restore <files>` for that slice's changes.

**Loop exit condition:** All hotspots in Task 8 inventory have an outcome line.

---

## Task 10: Retroactive sweep — final summary and `docs/index.md` update

**Files:**
- Create: `.agents/reviews/2026-05-08-pattern-repair-retroactive-sweep.md`
- Modify: `docs/index.md` (status matrix updates only)

**Acceptance:**
- Summary lists all Task 9 slices with outcomes
- `docs/index.md` 🟡 / 🚧 / 📝 entries updated where slice outcomes warrant new status
- User-approved commit completes the sweep

- [ ] **Step 1: Compile sweep summary**

Aggregate every `.agents/reviews/2026-05-08-sweep-<slug>.md` outcome line:

```bash
cd /home/longxiang/MiroThinker
grep -H "Sweep slice outcome:" .agents/reviews/2026-05-08-sweep-*.md
```

- [ ] **Step 2: Write summary file**

Write `/home/longxiang/MiroThinker/.agents/reviews/2026-05-08-pattern-repair-retroactive-sweep.md`:

```md
# Pattern-Repair Retroactive Sweep — 2026-05-08

## Inventory
- Source: `.agents/reviews/2026-05-08-pattern-repair-retroactive-sweep-hotspots.md`
- Total hotspots identified: <N>
- Total slices executed: <M>
- Total slices escalated: <K>

## Slice outcomes
| Slug | Outcome | Files touched | Mini-report |
|---|---|---|---|
| <slug-1> | 3a-fixed | <list> | `.agents/reviews/2026-05-08-sweep-<slug-1>.md` |
| <slug-2> | 3b-doc-only | <list> | `.agents/reviews/2026-05-08-sweep-<slug-2>.md` |
| ... | ... | ... | ... |

## docs/index.md status changes
| Doc | Before | After |
|---|---|---|
| <doc-1> | 🟡 partial | ✅ ready |
| <doc-2> | 🚧 in-progress | 🟡 partial |
| ... | ... | ... |

## Escalations (slices >1 day, parked as separate specs)
- `.agents/specs/2026-05-08-sweep-<slug-X>-escalated.md` — <one-line description>

## Remaining systemic risk
- <area> — <reason; why deferred>

## Process learnings
- <what we'd do differently next sweep>
```

Fill in actual values from Task 9 review files.

- [ ] **Step 3: Update `docs/index.md` status entries**

For each row in §10.1 doc-matrix table where a slice changed status, update the emoji marker. Use Edit tool, one row at a time.

Example: if `docs/Multi-turn-Context-Manager-Design.md` was 🟡 partial and the slice promoted it to ✅ ready:

```bash
grep -n "Multi-turn-Context-Manager-Design" /home/longxiang/MiroThinker/docs/index.md
```

Then Edit replacing `🟡` with `✅` on that exact line.

Do **not** edit rows where no slice produced status change.

- [ ] **Step 4: Verify changes**

```bash
cd /home/longxiang/MiroThinker
git diff --stat docs/index.md
git status --short .agents/reviews/
```

Expected: `docs/index.md` shows only emoji-marker line changes; `.agents/reviews/` shows the new summary file plus any per-slice files from Task 9 that haven't been committed yet.

- [ ] **Step 5: User approval and commit**

Show user the summary file and `docs/index.md` diff. Ask: "Sweep complete. Commit summary + docs/index.md updates?"

**STOP HERE until user approves.**

```bash
cd /home/longxiang/MiroThinker
git add docs/index.md .agents/reviews/2026-05-08-pattern-repair-retroactive-sweep.md
git commit -m "$(cat <<'EOF'
docs(sweep): pattern-repair retroactive sweep summary + status matrix update

Concludes the one-time retroactive sweep run after pattern-repair shipped.
<N> hotspots processed, <M> slices, <K> escalated. Status matrix updated to
reflect post-sweep state.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

**Rollback:** `git reset --soft HEAD~1`; `git restore docs/index.md`.

---

## Self-review (writing-plans skill checklist)

**1. Spec coverage check** — every section of the spec has a task:

| Spec section | Covered by task |
|---|---|
| §1 Problem and goal | (context only; no task needed) |
| §2 Architecture decisions D1–D10 | T1 (D1, D7), T2 (D8), T3 (D1, D8, D10), T4–T5 (D2), T6 (D9), T7 (CLAUDE.md commit rule), T9 (D10 length, V001–V018 preserve) |
| §3 Trigger model | T1 Step 4 + T2 Step 4 (description trigger words verified) |
| §4 Defect class taxonomy | T1 Step 2 (inlined) |
| §5 Fix-level ladder | T1 Step 2 (inlined) |
| §6 Skill workflow | T1 Step 2 (inlined) |
| §7 File layout / mirror | T1, T2, T3 |
| §8 AGENTS.md / CLAUDE.md patches | T4, T5 |
| §9 Activation tests | T6 |
| §10 Retroactive sweep | T8, T9, T10 |
| §11 Implementation handoff | this plan |
| §12 Risks | T3 (length), T6 (activation), T7 (commit gate), T9 (1-day cap) |
| §13 Closed open questions | (no task needed) |
| §14 Acceptance criteria | enforced per-task |

No gaps.

**2. Placeholder scan** — searched plan for "TBD", "TODO", "fill in details", "implement later", "similar to Task N", placeholder code blocks. None found. Per-slice rows in T9/T10 reports use `<slug>`/`<files>` as variable substitutions, which is acceptable since they are loop variables defined by Task 8 output.

**3. Type / name consistency check** —
- Skill name: `pattern-repair` (consistent T1, T2, T4, T5, T6)
- Trigger word count: 21 (T1 Step 4, T2 Step 4 same expectation)
- Path `.claude/skills/pattern-repair/SKILL.md` (consistent)
- Path `.agents/skills/pattern-repair/SKILL.md` (consistent)
- Spec path `docs/superpowers/specs/2026-05-08-pattern-repair-skill-design.md` (consistent)
- Plan path `docs/superpowers/plans/2026-05-08-pattern-repair-skill.md` (consistent)
- Lane numbers (1=admin-console, 2=canonical, 3=per-domain, 4=docs+migrations) consistent T1, T2, T9
- 5 enumerated diffs T2 referenced and verified T3

No inconsistencies.

---

## Risks and rollback summary

| Risk | Mitigation | Rollback |
|---|---|---|
| Skill exceeds 280 lines | T3 length check pre-merge | Edit T1 content to remove additions |
| Mirror drift between two SKILL files | T3 diff verification | Re-apply T2 diffs against T1 canonical |
| Trigger word truncation in description | T1/T2 Step 4 grep count must equal 21 | Restore description from T1 Step 2 verbatim |
| Accidental commit of unrelated working-tree files | T7 Step 2 explicit `git add` of named files only | `git reset --soft HEAD~1` |
| Sweep slice expands beyond 1 day | T9 Step 4 escalation to `.agents/specs/` | Slice marked "escalated"; no rollback needed |
| User rejects commit at T7 | T7 Step 1 STOP gate | No commit happens; files remain staged for revision |
| `docs/index.md` over-updated | T10 Step 3 explicit row-by-row Edit | `git restore docs/index.md` |
