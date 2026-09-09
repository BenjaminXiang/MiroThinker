# ADR-017: Web-only entities use evidence-bound session handles

- **Date:** 2026-07-13
- **Status:** Accepted and carried by the active OpenSpec change
- **Related:** `CONTEXT.md` (Result set, Web entity handle, Web evidence snapshot); ADR-011;
  OpenSpec `rebuild-canonical-v2-knowledge-platform`; Canonical V2 S8-S9
- **Contract:** carried by the active OpenSpec query/answer/session requirements before the
  affected slices are implemented

## Context and decision

Universal Web augmentation can discover relevant entities that do not exist in the accepted
Canonical release. Excluding every Web-only entity from the displayed result set would make useful
open-world answers impossible to continue in multi-turn conversation. Treating a source URL as a
Company, Paper, Patent, or Professor ID would instead confuse evidence location with real-world
identity, pollute set coreference, and allow unsupported canonical traversals.

A displayed Web-only entity may enter a session result set only as a typed `WebEntityHandle`. The
handle is session-scoped and content-bound to:

- a claimed public domain and display identity;
- one or more bounded Web evidence snapshots with URL, source nature, retrieval time, provider trace,
  exact excerpt or normalized response content, and content hash;
- identity-resolution state and any candidate accepted Canonical IDs considered by read-only fusion;
- the originating query, rewrite, lane, attempt, and displayed-answer position.

The raw URL is evidence metadata and never the entity ID. A Web entity handle may participate in
displayed-set coreference, narrowing over its retained evidence, and targeted supplemental Web
retrieval. It cannot execute a canonical relationship traversal, satisfy a canonical structured
filter, or claim canonical continuity while unresolved. If read-only resolution later binds it to an
accepted Canonical identity, the session retains the original handle/evidence lineage and records the
resolution; no online canonical identity mutation occurs.

The bounded evidence snapshot, not a future fetch of the live URL, is the reproducibility basis for
the original claim. A handle expires with session policy and does not become an offline identity or
source assertion merely because users referenced it in later turns.

## Consequences

- S8 candidate/result contracts need a tagged entity-handle union and must separate Web evidence IDs,
  handle IDs, and Canonical IDs. Fusion deduplicates resolved identities without losing Web lineage.
- S9 session state stores only displayed handles. Follow-up planning validates operations against each
  handle's resolution state and returns a limitation or targeted Web route for unsupported traversal.
- Trace replay and acceptance need Web-only displayed-set, later-resolution, unresolved-traversal,
  provider-change, snapshot-tampering, expiry, and URL-collision scenarios.
- Snapshot retention must be bounded and source-aware; this decision does not authorize unrestricted
  page archiving or direct Web-to-canonical publication.
- This ADR records the boundary decision but does not itself modify the active OpenSpec behavior.

## Alternatives rejected

- **Exclude Web-only entities from result sets:** identity-safe but breaks multi-turn continuation for
  the open-world results that Universal Web is intended to contribute.
- **Use URL as a domain entity ID:** simple but conflates provenance with identity, makes one entity at
  several URLs appear duplicated, and allows Web evidence to masquerade as canonical state.
