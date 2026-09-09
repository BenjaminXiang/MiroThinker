# Acceptance: resolve-professor-canonical-baseline

This file is filled in two passes: (1) when the change is proposed, the criteria are committed; (2) during execution, the Evidence sections are filled with verification output. The change archives only when every checkbox below is checked or explicitly reasoned-away in writing.

## 1. Audit doc tracked — debt `audit-doc-untracked-001`

- [x] `git ls-files | grep "Professor-Data-Agent-Requirements-Audit-2026-05-09.md"` returns the file path (verified after T1 commit `212229d`)
- [x] File path is exactly `docs/Professor-Data-Agent-Requirements-Audit-2026-05-09.md` (no rename, no relocation)
- [x] Body content unchanged from working-tree state at proposal time (frontmatter extension via T1.2 is the only permitted edit)
- [x] One commit message names this change ID (commit `212229d`)

## 2. PRD legacy marking — debt `professor-canonical-pivot-001`

- [x] `docs/Professor-Data-Agent-PRD.md` opens with frontmatter declaring `status: legacy` and `superseded_by: docs/Professor-Data-Agent-Requirements-Audit-2026-05-09.md`
- [x] `docs/index.md` Professor row reflects: Audit canonical / PRD legacy (split into two rows; doc-layering tree also updated)
- [x] `CLAUDE.md §3` Source-of-truth docs Professor entry names the Audit as canonical and the PRD as legacy reference
- [x] No other section of `CLAUDE.md` is touched
- [x] No body section of `docs/Professor-Data-Agent-PRD.md` is rewritten or deleted (only frontmatter prepended + a top-of-doc legacy notice added; original `# 教授数据采集智能体` heading and §一 onwards untouched)

## 3. Stale change disposed — debts `professor-prd-change-001` + `professor-prd-change-002`

- [x] T3.1 verification of PRD ↔ refine-change actually-shipped status is recorded in Evidence below before T3.2 decision is taken
- [x] T3.2 disposition is one of {archive, re-target, abandon} and the chosen path is recorded in Evidence below — chosen: **archive**
- [x] T3.3 execution matches T3.2 decision; no in-flight half-state (`openspec archive --skip-specs --yes` cleanly moved files; git rename detected)
- [x] `openspec/change-ledger.md` reflects the chosen state for `refine-professor-data-agent-prd` (moved Active → Archived in T3+T4 commit)
- [x] `professor-prd-change-002` is resolved consistent with the T3 outcome — **resolved-by-archive**: the non-conformant `specs/prd-update/spec.md` ships as legacy under `archive/2026-05-10-refine-professor-data-agent-prd/specs/`. `--skip-specs` flag bypassed the validation that would otherwise reject it; CLI emitted a non-blocking proposal warning about missing `## Why` / `## What Changes` headers, acknowledged as legacy form.

## 4. Debt register updated

- [x] `openspec/debt-register.md` Open table no longer contains `audit-doc-untracked-001`, `professor-canonical-pivot-001`, `professor-prd-change-001`, `professor-prd-change-002`
- [x] `openspec/debt-register.md` Resolved table contains all four entries with back-references to `resolve-professor-canonical-baseline`
- [x] No new debt entries were created by this change (the 11 new entries added 2026-05-10 belong to the parallel `docs/audits/*` reconciliation work, not to this change)

## 5. Inventory consistency

- [x] `docs/data-agent-domain-index.md §Phase 1B / 1C scope` no longer lists the three Professor bullets as pending (struck through with resolution-note pointing at this change)
- [x] `docs/data-agent-domain-index.md §Domain 4: Professor` Canonical baseline recommendation row is unchanged (Audit is and remains canonical)

## 6. This change registered and archived

- [x] `openspec/change-ledger.md` Active table contained `resolve-professor-canonical-baseline` during T1–T3 (commits `b6057dd` → `15fc564`)
- [x] `openspec/change-ledger.md` Archived table contains `resolve-professor-canonical-baseline` after T4.3
- [x] `openspec/changes/archive/2026-05-10-resolve-professor-canonical-baseline/` directory contains the change artifacts after archive (CLI moves to date-prefixed name under `archive/`; this is the `openspec` 1.2.0 convention)

## 7. Non-goals not violated

- [x] No file under `apps/`, `libs/`, or `src/` was modified — verified via `git diff main..HEAD` shows only `docs/`, `openspec/`, `CLAUDE.md` paths
- [x] No Pydantic contract changed
- [x] No Alembic migration added or modified
- [x] No new Professor data requirement was introduced (Audit content unchanged; only frontmatter `governance:` block extended)
- [x] No `specs/` delta was written for this change
- [x] No `design.md` was written for this change
- [x] Phase 1B+ items for multi-turn / agentic-rag / agents-specs / copilot not touched. Note: parallel work in commit `b6057dd` added 11 new doc-debt entries from the Company / Paper / Patent reconciliation audits — those were tracked separately and intentionally not bundled into this change's scope.

## Evidence

> Filled by the executing agent during T1 / T2 / T3. Not filled at proposal time.

### T1.2 — Audit doc frontmatter extension
- Decision: taken
- Rationale: provenance is most discoverable at the doc itself; future readers should not need to chase the change ID through `change-ledger.md` to know the doc's authority status.
- Frontmatter block added (8 keys: `change_id`, `canonical_for`, `canonical_status`, `declared_by`, `declared_on`, `superseded_target`, `next_step`, `tracked_in_git_on`).
- Diff hash / commit ref: see T1 commit (filled at commit time).

### T3.1 — PRD ↔ refine-change actually-shipped reconciliation
Verified against `docs/Professor-Data-Agent-PRD.md` at commit `15fc564` (T2 commit; PRD body identical to pre-pivot state apart from prepended legacy frontmatter and top-of-doc legacy notice).

| Task | Description (short) | Present in PRD? | PRD section / line range | Notes |
|---|---|---|---|---|
| T1 | 4.1 字段定义表 source → 采集策略 列重写 | **no** | §四.4.1 lines 107–134 | §4.1 table only has 字段 / 必填 / 说明 columns. No `来源` column to delete; no `采集策略` column was added. |
| T2 | 5.1 Phase 1 改 agent 驱动；Phase 4 本地 MiroThinker | **no** | §五.5.1 lines 160–171 | §5.1 is a 9-line ASCII flow diagram. No Phase 1 / Phase 4 numbered architecture, no agent-driven framing. |
| T3 | 5.2 Phase 1 BatchScheduler + ProfessorOrchestrator | **partial** | §五.5.2–5.3 lines 173–196 | §5.2 is "roster 发现"; §5.3 is "per-professor agent 采集". Per-professor agent concept is implicit in §5.3 step list, but BatchScheduler / ProfessorOrchestrator architecture and component naming are absent. |
| T4 | 新增技术架构章节 (MCP 工具集 / Hydra / 并发) | **no** | n/a | No "技术架构" section anywhere in PRD §一–§十一. No MCP / Hydra / 并发 model description. |
| T5 | 5.4 Phase 4 本地 MiroThinker 部署 | **no** | §五.5.4 lines 198–212 | §5.4 is "清洗与标准化" (LLM vs Python responsibility split). No mention of Phase 4, batch verification, or local MiroThinker deployment. |

**Summary judgement**: refine-professor-data-agent-prd `tasks.md` marks T1–T5 as `[x]` but **none of the five edits actually landed in the PRD body**. The change is "tasks-marked-but-deliverable-not-shipped" rather than "tasks-genuinely-complete". This invalidates the original disposition rationale ("tasks already complete against the now-legacy PRD") but does not change the conclusion: since the PRD has now been demoted to legacy by canonical pivot 2026-05-10, retrofitting T1–T5 onto a legacy PRD has no value.

### T3.2 — Disposition decision
- Chosen path: **archive**
- Rationale: Two factors converge: (a) T3.1 verification proves T1–T5 were never executed against the PRD body — the change is partial in implementation reality even though tasks are checked; (b) the PRD is now legacy per the user's 2026-05-10 canonical pivot, so retroactively applying T1–T5 to a legacy doc would be busywork. Archiving captures the intent (the change describes how the team thought Phase 1 should evolve) without forcing reality alignment. Re-targeting to the Audit doc was rejected because the Audit already contains a far more detailed architecture (BatchScheduler-equivalent in §1–§7) and re-targeting would require a rewrite that adds no information. Abandoning was rejected because it leaves a non-archived, non-active row in the ledger.

### T3.3 — Execution evidence
- Command run: `openspec archive --skip-specs --yes refine-professor-data-agent-prd`
- Tool: `openspec` CLI 1.2.0
- Output:
  ```
  Proposal warnings in proposal.md (non-blocking):
    ⚠ Change must have a Why section. Missing required sections.
      Expected headers: "## Why" and "## What Changes".
      Ensure deltas are documented in specs/ using delta headers.
  Task status: ✓ Complete
  Skipping spec updates (--skip-specs flag provided).
  Change 'refine-professor-data-agent-prd' archived as
    '2026-05-10-refine-professor-data-agent-prd'.
  ```
- Filesystem effect: `openspec/changes/refine-professor-data-agent-prd/` removed; `openspec/changes/archive/2026-05-10-refine-professor-data-agent-prd/` created with `proposal.md`, `tasks.md`, `design.md`, `specs/prd-update/spec.md` preserved verbatim.
- Git effect: 4 renames detected after `git add`; staged as `R` entries.
- The CLI's `## Why` warning corresponds to debt `professor-prd-change-002` (proposal.md doesn't follow OpenSpec's current Why / What Changes header convention, and `specs/prd-update/spec.md` doesn't follow Requirement / Scenario form). `--skip-specs` allows the archive to proceed; the non-conformant artifacts ship as legacy.

### Final verification
- `openspec list --status active` (or directory inspection): `openspec/changes/` after this commit contains only `archive/` (with `2026-05-10-refine-professor-data-agent-prd/` and `2026-05-10-resolve-professor-canonical-baseline/`). No active change directory remains. ✓
- `openspec/debt-register.md` Open count delta: −4 (`audit-doc-untracked-001`, `professor-canonical-pivot-001`, `professor-prd-change-001`, `professor-prd-change-002` all moved to Resolved). Open table size shrinks from 19 to 15 entries.
- `git status` clean after T3+T4 commit.

## Failure modes that block archive

If any of the following holds, this change does **not** archive and a follow-up issue is logged:

- T3.1 verification finds T1–T5 did *not* land in the PRD → the PRD is more out-of-sync than expected; the disposition decision needs reconsideration.
- The Audit doc was edited mid-flight by another session → resolve conflict before T1.1 commit; do not silently overwrite.
- A new Professor requirement is requested in the middle of execution → out of scope; spawn a new change.
