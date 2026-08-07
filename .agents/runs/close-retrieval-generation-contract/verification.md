# Verification — close-retrieval-generation-contract

## Status

- **Epic:** Contract complete; execution stopped inside gate-only Slice A.
- **Slice A:** In Progress; evaluator/preflight code exists, but Task 1.5 stopped the slice on a
  stable, non-viable DB/Milvus paper/chunk substrate. An explicit sequencing/substrate decision is
  required before the manifest/holdout/replay work resumes.
- **Slices B-F:** Specified and blocked on sequential predecessor acceptance; B/C/D internal
  checkpoints remain Specified until their owning predecessor/checkpoint is Accepted.
- **Implementation GREEN:** not claimed.
- **Production/data/index changes in current Slice A work:** none.

## Proposal-time verification — 2026-07-10

### OpenSpec

- Command: `openspec status --change close-retrieval-generation-contract --json`
- Result: proposal, design, specs, and tasks all `done`; `isComplete: true`.
- Command: `openspec validate close-retrieval-generation-contract --strict`
- Result: exit 0, `Change 'close-retrieval-generation-contract' is valid`.
- Commands: `openspec validate <change> --strict` for
  `fix-paper-topic-query-classification`, `wire-professor-paper-list-traversal`,
  `fix-professor-ambiguity-intro-rule`, `make-partial-papers-retrievable`, and
  `sigs-official-publications-to-paper-domain`.
- Result: every command exited 0; every corresponding `openspec status --change <change> --json`
  reported `isComplete: true` with proposal/design/specs/tasks `done`.
- Task ledger: Epic `tasks.md` is 1/92 complete; only the contract-creation task is checked. Slice A
  remains the sole Ready execution scope and no implementation GREEN is implied by artifact status.
- Command: `git diff --check`.
- Result: exit 0.
- Tool warning: `openspec instructions design --change close-retrieval-generation-contract`
  reproducibly reports
  `Rules for 'design' must be an array of strings, ignoring this artifact's rules` while loading the
  repository's existing `openspec/config.yaml`. The artifact still validates. This proposal did not
  alter shared OpenSpec configuration.

### Audit counter-evidence that keeps predecessors Candidate

- The current response-wide recall scorer can find expected strings in the echoed query rather than
  retrieved result IDs; 14 of 41 required-token entries are exposed to query echo, including the
  Type1 qid100-qid105 form.
- Comparable paper counts are not established by the stored reports: the actual paper slice was
  observed as 8/20 before the targeted changes and 17/18 after the Type4 oracle changed from four
  specific titles to two generic topic tokens.
- Current Type2 prompt evidence can return early on professor payloads and omit joined papers;
  professor-paper queries were observed retrieving paper rows while producing a profile answer or
  saying the list was unavailable.
- Model marker mapping, backend citations, and frontend citation numbering are independently
  assembled, so retrieval or answer text does not prove the cited source is the same object.
- Q004/Q017 compare only expected type in the current benchmark while malformed normalized names
  reach an unknown entity endpoint.
- Type3 has neither a populated strong relation path sufficient for all cases nor a service-level
  company-to-professor-to-paper planner.
- Type4 lacks structured filters, independent local lexical fallback, paper-before-rerank grouping,
  and a policy that lets partial-rich records compete with ready records.
- No persisted per-paper embedding ledger proves active eligibility or Postgres-Milvus ID/version
  parity; raw backlog counts include terminal records.

These are audit findings, not Slice A executable RED artifacts. Slice A must reproduce them under
the frozen manifest and snapshot before production implementation.

### Current dataset observation caveat

Historical notes quoted several read-only counts without retaining one complete reproducible query
artifact and mixed raw backlog with terminal rows. They are planning clues, not proposal evidence.
Slice F must recalculate and save exact ID sets/counts, SQL/query hash, rule version, and named
snapshot before making any active-lane or parity claim. This does not authorize a backfill or index
write.

## Required evidence by slice

### Slice A

- Completed evaluator-only implementation:
  - `apps/admin-console/scripts/paper_retrieval_gate.py` defines
    `paper-retrieval-case-manifest-v1`, an extra-forbid normalized scoring record, canonical-only
    response adapter, conjunctive retrieval/citation/semantic/outcome scoring, four-field classifier
    scoring, nonzero P0 aggregation, fixed five-slot Type4 micro-P@5, and signed holdout receipt/
    two-reviewer kappa checks.
  - `apps/admin-console/tests/test_paper_retrieval_gate.py` proves query echo, prompt, debug, and
    configuration cannot satisfy retrieval; retrieved-but-uncited and cited-but-incomplete cases
    fail; duplicate/Web/missing Type4 slots score zero; no recall metric is emitted; a single P0
    failure exits nonzero; and type-correct/entity-wrong classification fails.
  - `apps/admin-console/scripts/paper_snapshot_preflight.py` is a read-only DB/Milvus manifest and
    paper/chunk parity command. It hashes the full query-visible DB tables, exact approved
    index-eligible expected chunks, ordered Milvus chunk/paper/content state, collection schema,
    and the complete 1,298,632,704-byte Milvus Lite physical target before and after inspection.

- Test-first evidence:
  - Command: `uv run pytest tests/test_paper_retrieval_gate.py -q` before implementation.
    Result: expected collection RED, `ModuleNotFoundError: paper_retrieval_gate`.
  - Command: `uv run pytest tests/test_paper_snapshot_preflight.py -q` before implementation.
    Result: expected collection RED, `ModuleNotFoundError: paper_snapshot_preflight`.
  - Command: `uv run pytest tests/test_paper_snapshot_preflight.py tests/test_paper_retrieval_gate.py -q`.
    Result: exit 0, 18 passed.

- Baseline compatibility check:
  - Command: `uv run pytest tests/test_paper_retrievability.py tests/test_classifier_benchmark.py -q -m 'not requires_classifier_llm'`.
    Result: exit 0, 20 passed and 1 deselected before Slice A edits.

- Read-only substrate preflight:
  - Command: proxy variables unset; `DATABASE_URL` points at the existing read-only evaluation DB;
    `MILVUS_USE_REAL_CLIENT=1 uv run python scripts/paper_snapshot_preflight.py`.
  - Result: expected hard-gate exit 1 after artifacts were written; `snapshot_stable=true` and
    `viable=false`.
  - Artifact root:
    `.agents/runs/close-retrieval-generation-contract/artifacts/paper-snapshot-4afb567921be3dab/c0f3db2e0493-eval-a09534d6133d/`.
    Evaluator source SHA-256:
    `a09534d6133d0b22d2210febc8ddd095ce1a90e79daff3419b6ccfb46073372b`.
  - DB ordered-manifest before/after SHA-256:
    `58f81e1fb66e2715e1bbb09598c86bc566d00bc291704056736ea95288c8789a` (equal).
  - Milvus ordered chunk/paper/content before/after SHA-256:
    `9cbbf0f1d21b595516bb8cb5583b58d67408b9fa3c42f793e870a3999704efc0` (equal).
  - Milvus physical-target before/after SHA-256:
    `43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc` (equal).
  - Artifact hashes: `manifest.json`
    `a7a8d14ee581e1e49f4c4bbf642f7e463236e5810b356a405cdd447103092cd9`;
    `parity.json` `ad0cf96f8012544c225143f9eacdf356087106e118ba3b2ba1b9ba1d2f1a8fb1`;
    `environment.json` `aeb8faefbbb01d59d4e47e2219ecfd8539e3e7e96e7596d49f4f86bd744917c2`.
  - Paper parity: 29,434 expected / 26,095 actual; 16,777 missing, 13,438 unexpected.
  - Chunk parity: 65,222 expected / 46,035 actual; 36,835 missing, 17,648 unexpected,
    3,012 content-stale.
  - Physical version parity: all 46,035 actual chunks lack the required model/chunker/index/write
    tuple in the active collection schema and are therefore unverifiable.

- Stop decision:
  - The Slice A contract says to stop when current index gaps make the fixed Type4 substrate
    non-viable. That condition is met on a stable snapshot, so Slice A is not Candidate or Accepted,
    Slice B remains blocked, and no production behavior/data/index mutation was attempted.
  - Pending after an approved sequencing/substrate decision: complete minimum-floor/P0 manifest,
    independently held sealed holdout, all-100 classifier four-field fixture, same-snapshot parent/
    candidate replay, live-provider protocol, corrected production RED table, independent review,
    and immutable Slice A diff hash.

- Current-session verification after the stop evidence was recorded:
  - Command: `uv run ruff check scripts/paper_retrieval_gate.py scripts/paper_snapshot_preflight.py tests/test_paper_retrieval_gate.py tests/test_paper_snapshot_preflight.py`.
    Result: exit 0, all checks passed.
  - Command: `uv run pytest tests/test_paper_retrieval_gate.py tests/test_paper_snapshot_preflight.py tests/test_paper_retrievability.py tests/test_classifier_benchmark.py -q -m 'not requires_classifier_llm'`.
    Result: exit 0, 38 passed and 1 live-classifier test deselected by the recorded marker expression.
  - Command: `openspec validate close-retrieval-generation-contract --strict`.
    Result: exit 0, change is valid.
  - Commands: `git diff --check`; production-scope diff check over
    `apps/admin-console/backend` and `apps/miroflow-agent/src`.
    Result: exit 0; no production source diff.
  - Command: case-insensitive secret/credential-pattern scan over the snapshot artifact directory.
    Result: no match.

- Skipped/blocked:
  - The first physical scan requested every vector through the Milvus query API and was manually
    interrupted after seven minutes while still read-only. The accepted rerun used the contract's
    allowed alternative: full physical-target SHA-256 before/after plus ordered chunk/paper/content
    and schema/dimension hashes. The completed rerun is the evidence cited above; the interrupted
    attempt is not counted as a pass.
  - Parent/candidate/provider/semantic/latency replays and independent review did not run because
    Task 1.5 requires the substrate decision first.

### Slice B

- Blocked on Slice A Accepted.

### Slice C

- Blocked on Slice B Accepted.

### Slice D

- Blocked on Slice C Accepted.

### Slice E

- Blocked on Slice D Accepted.

### Slice F

- Blocked on Slice E Accepted.

## Skipped in this proposal step

- No unit/integration/API/browser/semantic/latency benchmark was rerun; the requested deliverable is
  the approved contract set, not implementation or a new live baseline.
- No database migration, write, enrichment, embedding, Milvus operation, rollout-mode switch, push,
  PR, or commit was performed.
- Existing unrelated dirty and untracked workspace files were left untouched.
