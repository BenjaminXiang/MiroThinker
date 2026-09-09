# Canonical V2 S11 Consolidated Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for the serialized Git writes in this plan. Read-only audits may use subagents, but one primary writer owns every archive, ref, commit, and worktree mutation.

**Goal:** Preserve every current Canonical V2 byte, create one honest and clean S11 consolidation commit, and establish its verified commit as the only parent for subsequent development without moving `main`, pushing, or starting S12.

**Architecture:** First create a permission-restricted external archive and an exact local Git recovery ref from the authoritative dirty worktree. Then create a separate aggregate consolidation commit directly on top of `f0e6224`, omitting only quarantined preview artifacts that remain recoverable from the archive and recovery ref. Reconcile the control-plane documents in a follow-up commit, verify the clean worktree, and leave all historical branches and worktrees intact.

**Tech Stack:** Git temporary indexes and `commit-tree`, Git worktrees, SHA-256 manifests, OpenSpec CLI, uv/pytest, Ruff/Pyright where already configured.

---

## Task Contract

**Goal:** Establish `Canonical V2 S11 Consolidated Baseline`.

**Expected invariant:** The original dirty worktree, its real Git index, `canonical-v2-s2-baseline`, local `main`, remote refs, original PostgreSQL, original Milvus, and every existing side branch remain unchanged while two new local refs and one clean linked worktree are created.

**Context:** The authoritative worktree is `/home/longxiang/MiroThinker/.worktrees/canonical-v2-s2` at `f0e6224e1c675c6d6c58993676783b2fbe0cd8f6`. Its current bytes contain the accepted S2C2/S6R/S7-S11 implementation state, but the task-level intermediate blobs were never committed and cannot be reconstructed honestly.

**Constraints:** No reset, clean, stash, rebase, merge, force update, branch deletion, worktree deletion, push, PR, cutover, S12 implementation, original-source access, database write, Milvus write, or fabricated historical commit.

**Done when:** A protected archive verifies, `codex/canonical-v2-s11-recovery-20260722` preserves the complete nonignored state, `codex/canonical-v2-s11-consolidation` is clean and verified, control-plane status identifies it as the sole future parent, and `main` remains `f0e6224`.

**Out of scope:** Per-task history reconstruction, S2C external human review, Tasks 8.1/8.8/9.8, S12, production-like promotion, remote push, and deleting or renaming legacy branches.

## File and state boundaries

The recovery ref includes every nonignored tracked modification and untracked file, including preview evidence. The consolidation ref excludes only these quarantined preview-only paths:

```text
.agents/runs/rebuild-canonical-v2-knowledge-platform/frontend-preview-2026-07-21/
.agents/runs/rebuild-canonical-v2-knowledge-platform/preview-p1/
docs/superpowers/plans/2026-07-21-canonical-v2-real-data-preview.md
docs/superpowers/specs/2026-07-21-canonical-v2-real-data-preview-design.md
```

The recovery archive and recovery ref retain those paths. The consolidation commit retains all receipt-bound evidence, including S7/S8 receipts, S9J desktop/mobile PNGs, S11B baseline JUnit/collected files, and all S11C evidence.

The following files are cumulative final bytes and must not be split into fabricated historical commits:

```text
apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read.py
apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_answer.py
apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py
apps/admin-console/backend/canonical_v2_deps.py
apps/admin-console/backend/api/canonical_v2_chat.py
apps/admin-console/backend/services/canonical_v2_chat.py
apps/admin-console/backend/main.py
apps/admin-console/backend/static/browse.html
apps/admin-console/backend/static/chat.html
openspec/changes/rebuild-canonical-v2-knowledge-platform/tasks.md
openspec/changes/rebuild-canonical-v2-knowledge-platform/acceptance.md
openspec/changes/rebuild-canonical-v2-knowledge-platform/change-log.md
openspec/changes/rebuild-canonical-v2-knowledge-platform/agent-links.md
.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md
```

### Task 1: Create an external byte-preservation archive

**Files:**
- Generate outside Git: `/home/longxiang/.mirothinker_recovery/<UTC>-canonical-v2-s11-consolidation/`
- Read only: all changed/nonignored paths in the authoritative worktree

- [ ] **Step 1: Re-prove the frozen pre-write state**

Run from the authoritative worktree:

```bash
git rev-parse HEAD
git rev-parse main
git diff --cached --quiet
git status --porcelain=v2 -z -uall | sha256sum
git diff --binary HEAD | sha256sum
git ls-files --others --exclude-standard -z | sort -z | xargs -0 sha256sum | sha256sum
```

Expected: both refs equal `f0e6224e1c675c6d6c58993676783b2fbe0cd8f6`, the real index is unstaged, and the hashes are recorded before any write.

- [ ] **Step 2: Generate the path and per-file hash manifests**

Create a mode-`0700` recovery directory. Generate a NUL-delimited sorted path list from `git diff --name-only -z` plus `git ls-files --others --exclude-standard -z`, a NUL-delimited SHA-256 manifest, porcelain-v2 status, HEAD/branch metadata, and an archive containing exactly those paths. Set every generated recovery file to mode `0600`.

- [ ] **Step 3: Verify the archive independently**

Verify archive SHA-256, archive listing count, per-file hash manifest count, and extraction into a new temporary directory. Rehash the extracted files and require exact equality with the manifest. Remove only the temporary verification extraction after it passes; retain the archive and manifests.

### Task 2: Create the exact aggregate recovery ref without touching the real index

**Files:**
- Create Git ref: `refs/heads/codex/canonical-v2-s11-recovery-20260722`
- Do not change: authoritative worktree, real index, checked-out branch, or `main`

- [ ] **Step 1: Build the recovery tree through a temporary index**

```bash
tmpdir=$(mktemp -d)
idx="$tmpdir/index"
GIT_INDEX_FILE="$idx" git read-tree f0e6224
GIT_INDEX_FILE="$idx" git add -A -- .
tree=$(GIT_INDEX_FILE="$idx" git write-tree)
```

Expected: ordinary ignore rules apply; no `-f` is used.

- [ ] **Step 2: Create the aggregate recovery commit and ref**

Create one commit with parent `f0e6224` and subject:

```text
chore(recovery): checkpoint accumulated canonical-v2 S11 worktree
```

The body must state that this is an aggregate recovery snapshot, not reconstructed task history, and record the archive SHA-256 plus the pre-write inventory hashes. Create the new ref with `git update-ref` using an all-zero expected old object ID.

- [ ] **Step 3: Prove zero mutation of the authoritative checkout**

Re-run HEAD, `main`, real-index SHA-256, status SHA-256, tracked diff SHA-256, and untracked content/path hashes. Require exact pre/post equality. Rebuild the tree using a second temporary index and require equality with the recovery commit tree. Run `git fsck --strict <recovery-commit>`.

- [ ] **Step 4: Create and verify a local Git bundle**

Create a mode-`0600` bundle in the recovery directory containing the recovery ref. Run `git bundle verify` and record bundle SHA-256.

### Task 3: Create the clean aggregate consolidation commit and worktree

**Files:**
- Create Git ref: `refs/heads/codex/canonical-v2-s11-consolidation`
- Create worktree: `/home/longxiang/MiroThinker/.worktrees/canonical-v2-s11-consolidation`
- Exclude only the four quarantined preview paths listed above

- [ ] **Step 1: Build a formal consolidation tree from the authoritative current bytes**

Use a new temporary index based on `f0e6224`, add the current nonignored state, then reset only the four quarantine paths back to `f0e6224` in the temporary index. Write the tree and prove that every other recovery path is present with the same blob bytes.

- [ ] **Step 2: Create the honest aggregate import commit**

Create one commit with parent `f0e6224` and subject:

```text
feat(canonical-v2): import accepted S11 consolidated state
```

The body must state that the commit imports final accepted bytes for S2C2/S6R/S7-S11, does not reconstruct task history, keeps Tasks 2.8/8.1/8.8/9.8/12.* open, and references the recovery commit and bundle SHA-256.

- [ ] **Step 3: Create the isolated clean worktree**

From the repository root, verify `.worktrees/` is ignored, then add the linked worktree at `/home/longxiang/MiroThinker/.worktrees/canonical-v2-s11-consolidation` on the new consolidation branch. Require clean `git status` before any further edit.

### Task 4: Reconcile the control plane on the consolidation branch

**Files:**
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/git-consolidation-baseline-2026-07-22.md`
- Modify: `.agents/portfolio.md`
- Modify: `.agents/runs/rebuild-canonical-v2-knowledge-platform/mainline-promotion-gate.md`
- Modify: `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification-contract.md`
- Modify: `openspec/change-ledger.md`
- Modify: `openspec/changes/rebuild-canonical-v2-knowledge-platform/agent-links.md`
- Modify: `openspec/changes/rebuild-canonical-v2-knowledge-platform/change-log.md`

- [ ] **Step 1: Record the baseline contract**

The new English baseline document must record exact base/recovery/consolidation commits, archive/bundle/inventory hashes, included and quarantined paths, task count `70/80`, acceptance count `49/97`, open tasks, receipt hashes, test commands, branch dispositions, rollback, and the invariant that this consolidation commit is the only parent for subsequent development.

- [ ] **Step 2: Remove stale status contradictions**

Update the ledger from `36/75; S7 unstarted` to the exact consolidated `70/80` state. Mark S6R/S7-S11 implementation slices according to their existing accepted receipts while keeping S2C Task 2.8, Tasks 8.1/8.8/9.8, and S12 open. Do not mark the Epic Candidate or Accepted.

- [ ] **Step 3: Record the historical commit-policy exception honestly**

In `agent-links.md`, retain the per-task commit rule for all future work and add the explicit user-approved recovery exception: the uncommitted 2026-07-13 through 2026-07-21 final bytes are imported once as an aggregate baseline because intermediate blobs do not exist. Do not claim fabricated task-level commits.

- [ ] **Step 4: Commit only the control-plane reconciliation**

After verification, create one commit:

```text
docs(canonical-v2): establish S11 consolidated development baseline
```

### Task 5: Verify the consolidated baseline

**Files:**
- Test existing consolidated production/tests only
- Do not generate or overwrite accepted receipts

- [ ] **Step 1: Run structural and contract checks**

```bash
git diff --check f0e6224..HEAD
openspec validate rebuild-canonical-v2-knowledge-platform --strict
cd apps/miroflow-agent
PYTHONDONTWRITEBYTECODE=1 uv run alembic -c canonical_v2_alembic.ini heads
```

Expected: no whitespace errors, OpenSpec valid, and exactly one Canonical V2 migration head `C2_0011`.

- [ ] **Step 2: Run the safe S7/S8 pure matrix**

```bash
uv run pytest -o addopts='' -p no:cacheprovider -q \
  tests/canonical_v2/test_knowledge_build_interface.py \
  tests/canonical_v2/test_release_publication_interface.py \
  tests/canonical_v2/test_knowledge_read_interface.py \
  tests/canonical_v2/test_knowledge_query_planning_contract.py \
  tests/canonical_v2/test_knowledge_read_universal_web_contract.py \
  tests/canonical_v2/test_knowledge_read_sufficiency_retry_contract.py \
  tests/canonical_v2/test_knowledge_read_retrieval_fusion_contract.py \
  tests/canonical_v2/test_knowledge_read_atomic_green_contract.py
```

- [ ] **Step 3: Run the current S9-S11 owner matrix**

```bash
uv run pytest -n0 -q --no-cov \
  tests/canonical_v2/test_consumer_acceptance_contract.py \
  tests/canonical_v2/test_consumer_migration_boundary.py

cd ../../admin-console
uv run pytest -q \
  tests/test_canonical_v2_chat_http_adapter.py \
  tests/test_canonical_v2_consumer_migration.py \
  tests/test_canonical_v2_operations_api.py \
  tests/test_smoke_canonical_v2_candidate.py
```

- [ ] **Step 4: Re-run secret, path, and receipt integrity checks**

Require no changed symlink, nested repository, path escape, high-confidence credential pattern, unexpected binary, or unaccounted large file. Verify every accepted receipt JSON parses and every receipt-bound current artifact hash matches. Do not display potential secret values.

- [ ] **Step 5: Prove the baseline is clean and isolated**

Require a clean consolidation worktree, consolidation branch ahead of `f0e6224` by exactly the aggregate import and control-plane commits, unchanged `main`, unchanged authority worktree hashes, and valid archive/recovery/bundle refs.

### Task 6: Record non-destructive branch dispositions

**Files:**
- Update only the baseline document created in Task 4 if verification changes evidence
- Do not delete or move existing refs/worktrees

- [ ] **Step 1: Classify Canonical V2 branches**

Record `included`, `superseded-but-preserved`, `divergent-preserved`, `recovery`, or `future-parent` for every `canonical-v2-*` and `codex/canonical-v2-*` branch. Perform content-level comparisons for the S6c/S6d/S6f divergent branches, but do not merge, rebase, or delete them.

- [ ] **Step 2: Freeze the future-development rule**

Record that every future Ready slice branches from the final `codex/canonical-v2-s11-consolidation` commit, uses one writer and one independently verifiable checkpoint, and integrates serially only after acceptance. `main` moves, push, branch deletion, and S12 remain separate later decisions.

## Self-review checklist

- [ ] Every current nonignored byte is recoverable from the external archive and aggregate recovery ref.
- [ ] Quarantined preview paths are absent from consolidation history but present in recovery artifacts.
- [ ] S9J and S11 receipt-bound generated evidence remains included.
- [ ] No intermediate task history is fabricated.
- [ ] Tasks 2.8/8.1/8.8/9.8/12.* remain open.
- [ ] `main`, remote refs, original sources, databases, indexes, and all old branches/worktrees remain unchanged.
- [ ] The final clean consolidation commit is explicitly named as the only future development parent.

## Rollback

No existing ref is moved. To abandon consolidation, stop using the new consolidation worktree/ref; the original dirty worktree remains unchanged and the recovery ref plus bundle/archive retain its bytes. Do not delete any recovery artifact until a later user-authorized cleanup proves an independently accepted successor.
