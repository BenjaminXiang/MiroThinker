# S12C r8 Systemic Repair Implementation Plan

**Goal:** Produce one isolated Candidate that answers the customer workbook through the real chat
path without duplicate exact identities, audit-candidate leakage, evidence-closure 409s, or known
fixed-source coverage gaps.

**Architecture:** Keep canonical mutation inside the offline build. `KnowledgeRead` retains complete
audit traces but exposes a separate answer-eligible handle set; `KnowledgeAnswer` renders only those
handles. Restore-verified supplemental files enter through the existing landing/build seam and are
never loaded by production chat.

**Tech stack:** Python 3.12, Pydantic, PostgreSQL, NumPy/Qwen embeddings, FastAPI, pytest/xdist.

## Task 1: Evidence closure and final selection

- [x] Add a failing Admin adapter test where a max-results-dropped candidate retains an audit trace
  but is absent from answer-eligible items; prove the request does not return 409.
- [x] Replace recursive `evidence_ids` discovery with explicit live-reference closure validation;
  claim/handle/citation-bearing references remain fail-closed and audit-only references remain
  traceable.
- [x] Add failing serving tests proving a singular exact/lexical hit excludes vector-only neighbors,
  while enumeration still permits multiple canonical handles.
- [x] Make the answer selector consume selected canonical handles/candidates rather than raw evidence
  order, then run the two focused test files.

## Task 2: Multi-turn anchor discipline

- [x] Add failing tests for one unique entity followed by a singular relationship question, a
  multi-result set followed by an ambiguous singular pronoun, and a new-topic turn.
- [x] Set an active anchor only for one selected/explicitly chosen identity; preserve result sets for
  set referents and clear prior display IDs on topic switches.
- [x] Run the focused Admin chat tests.

## Task 3: Fixed-source landing and offline identity

- [x] Add failing mapper tests for the five restore-verified supplemental members, exact Paper and
  Patent projection, Company enrichment, Professor-Company role projection, and source lineage.
- [x] Admit only manifest-pinned file path/size/SHA-256 members and map them through existing domain
  adapters into immutable landing records.
- [x] Add failing identity tests proving exact accepted Professor email/homepage evidence merges the
  duplicated source identities and same-name conflicts remain separate.
- [x] Populate normalized identity keys from admitted fields, group assertions by canonical
  identity/path, retain older snapshots, and select only the as-of-current snapshot.
- [x] Preserve the Paper roster rule by deriving a Professor-Paper anchor only from unique retained
  author/identity evidence; unresolved attribution remains a gap.
- [x] Run the focused build, identity, domain, and relationship tests with bounded pytest parallelism.

## Task 4: r7 build and real replay

- [x] Build a fresh disposable PostgreSQL database and isolated lookup/vector index using all
  available local CPU and the bounded Qwen provider concurrency.
- [x] Audit release counts, lookup/vector parity, evidence/identity/relationship lineage, empty active
  pointer, unchanged original Milvus hash, and paused original PostgreSQL.
- [x] Start the r8 server on `0.0.0.0:18188` and smoke exact Professor, Company, Paper, Patent,
  safety, enumeration, and Professor-to-Company follow-up queries.
- [x] Replay all 17 conversations/25 turns with at most 17 parallel conversation workers and write
  content-bound JSON plus readable Markdown.

## Task 5: Lean acceptance evidence

- [x] Run only affected tests, Ruff for changed Python, Pyright for changed modules, OpenSpec strict,
  and `git diff --check`.
- [x] Update Task 12.3/12.4 and verification evidence only if their exact conditions pass. Leave Task
  12.5 unchecked until the user explicitly accepts the running system.

Rollback is deletion of the disposable r7 database/index and re-serving r6. No active release,
original source, original Milvus, or production database is mutated. No commit is created without
explicit user authorization.
