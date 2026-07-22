# Canonical V2 Real-Data Preview Design

## Status

Proposed for user review on 2026-07-21. This is a preview-only execution design under the active
OpenSpec change `rebuild-canonical-v2-knowledge-platform`; it does not close Task 12.1.

## Goal

Replace the synthetic four-object demo with a small, honest Canonical V2 preview built from an
accepted historical restore copy. The first preview contains one Company, one Patent, one Professor,
one Paper, and one Professor-to-Paper relationship. It must be useful in the existing `/browse` and
`/chat` UI while preserving evidence lineage, visible limitations, and zero active-release effect.

## Selected approach

Use exact-ID extraction from the accepted S2B restore of `released_objects.db`, then project the five
selected rows through the accepted Canonical V2 domain/relationship/release interfaces into a new
disposable preview candidate.

The selected graph is:

- Company `COMP-3B95F48EB687`;
- Patent `PAT-009605B1E383`, whose applicant data links to the selected Company;
- Professor `PROF-8000C9F994C3`;
- Paper `PAPER-1258119BC264`;
- Professor-Paper link `PROF-PAPER-LINK-00A7B60465F2`.

This is preferred over two alternatives:

1. Reusing S4E directly is not viable: its accepted checkpoint contains only 21 landing rows, the
   five SQLite rows are all Companies, and every knowledge/domain/release/index table is empty.
2. Waiting for the full S12A build is architecturally complete but does not meet the request for a
   rapid visual preview. The preview remains explicitly non-authoritative and is later replaced by
   S12A rather than promoted.

## Data flow

```text
accepted S2B restore + accepted hashes
  -> preview selection manifest
  -> hash gate before open
  -> exact-ID, read-only extraction (exactly five rows)
  -> typed source records and field/relationship decisions
  -> four public-domain projections + two verified relationships
  -> isolated preview Candidate and lookup projection
  -> S11 release-bound runtime
  -> /browse and /chat
  -> content-addressed preview receipt + screenshots
```

The extractor must use parameterized exact-ID queries only. It rejects a missing, duplicate,
unexpected, cross-domain, or cross-link row and never falls back to `LIMIT`, latest, fuzzy, or
environment-selected input. The source file is opened read-only only after its accepted byte size
and SHA-256 match the S2B restore manifest.

## Workflow and artifacts

Keep the workflow reusable rather than hand-editing UI fixture data:

- one preview Slice Contract under
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/slices/`;
- one content-addressed `preview-selection-manifest-v1.json` containing the accepted restore
  identity, exact five source IDs, expected source kinds, and selection rationale;
- one run-local preview builder/runner that validates the manifest, extracts exact rows, calls the
  accepted typed projection/release seams, and starts or materializes the disposable Candidate;
- focused tests for hash gate, exact set membership, relationship endpoints, no fabricated fields,
  release scoping, and no promotion capability;
- one `preview-build-receipt.json` containing input/output hashes, object/relationship counts,
  limitations, release ID, active-state before/after identity, and source freeze checks;
- API/browser evidence and a short demo-question list generated from the final candidate contents.

The runner is preview-only and must not become a second production build API. Any generally useful
composition learned here is folded into S12A's single `KnowledgeBuild.build` implementation; the
preview runner is removed or retained only as a bounded verification tool after S12A exists.

## Field and privacy policy

Only source-grounded fields needed for the demo are projected. Missing values remain absent or
produce typed limitations. No placeholder summary, parent, identifier, or relationship is invented.
Direct contact fields and non-public personal data are excluded from the preview payload unless the
accepted source and product contract explicitly establish them as public and necessary. Source row
payloads, local paths, hashes, assertion IDs, and execution enums stay out of public prose.

## Verification

The preview is ready for display only when all of the following hold:

- the accepted restore hash/size gate passes before the database is opened;
- extraction returns exactly the five named rows and the two relationship paths have exact endpoints;
- the candidate exposes exactly one object in each public domain and no fifth public domain;
- every displayed material field/relationship has evidence and decision lineage;
- `/browse` shows the real names/fields/relationships and labels partial quality honestly;
- `/chat` answers at least one entity question and one relationship follow-up without internal IDs;
- desktop/mobile browser checks and console checks pass;
- original sources and active pointers are byte/state identical before and after;
- independent review reports zero Critical or Important findings.

## Non-goals

- No claim that these five rows represent full conversion or accepted production truth.
- No OpenSpec Task 12.1 checkbox, S12A receipt, promotion, Cutover, Commit, Push, or PR.
- No original PostgreSQL/Milvus/forensic access, online recollection, provider call, broad cleanup,
  schema migration, or new public API.

## Rollback

Stop the preview process and remove only its explicitly owned temporary database/index/staging
targets and run artifacts. Restore the prior disposable preview process if needed. No canonical
source, accepted checkpoint, active pointer, or remote Git state changes.
