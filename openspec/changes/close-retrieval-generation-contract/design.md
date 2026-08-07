# Design: close-retrieval-generation-contract

## Context

Commit `c0f3db2` repaired several paper routing and candidate-retrieval cases, but the measured
result does not yet establish an end-to-end retrieval contract:

- the current recall scorer searches the serialized response, including the echoed request, so a
  required token can pass without appearing in retrieved evidence or an answer;
- professor-paper payloads can contain papers that are discarded when prompt evidence is built,
  and the synthesis intent can still be treated as professor profile;
- model citation markers, backend citation records, and frontend numbering are produced from
  different lists;
- Type2 list semantics are bounded by implementation limits rather than the requested predicate;
- Type3 lacks a company-to-professor-to-paper plan and edge-level provenance;
- Type4 performs dense chunk retrieval before paper aggregation, has no independent local lexical
  lane, and can suppress usable `partial+rich` papers whenever a ready result exists;
- the backfill number mixes active work with terminal rejected or merged records, while no
  per-paper ledger proves Postgres-to-Milvus parity.

Current database observations are planning evidence, not durable product constants. Prior notes also
mixed active work with rejected/merged records and did not retain a reproducible query artifact for
every quoted count. Slice F MUST recompute and persist the exact counts, ID sets, predicate version,
source snapshot, and query hash instead of copying historical totals into an acceptance claim.

This is a cross-cutting Epic. It changes chat response fields, evidence assembly, synthesis,
frontend citations, retrieval planning, paper ranking, relationship traversal, index lifecycle,
and evaluation. The implementation is therefore divided into six sequential slices. Only Slice A
is Ready initially; each later slice remains Specified until the previous slice is Accepted.

## Goals

- Establish one source of truth for evidence identity and citation order from retrieval through UI.
- Make every material generated claim machine-checkable against atomic evidence.
- Give Type1-Type4 paper paths explicit query semantics and path-specific quality gates.
- Prove results against a fixed manifest, database snapshot, index version, and raw responses.
- Make paper embedding eligibility and Postgres-Milvus parity observable and replayable.
- Roll out additively through shadow comparison and an immediate legacy rollback mode.

## Non-Goals

- Rewriting ranking for non-paper domains.
- Treating public Web results as local records or using them to pass local recall gates.
- Adding a new embedding, reranking, LLM, or Web provider.
- Defining streaming, retry orchestration, or long-form report generation.
- Running production data backfills, index mutations, or canonical cutover as part of this
  documentation change.
- Removing legacy response fields before all consumers have cut over.

## Decisions

### 1. Deliver the Epic as six gated slices

The sequence is fixed:

1. **A — Oracle and RED:** freeze the case manifest and snapshot identity, repair the evaluator,
   and preserve true RED evidence. It MUST NOT change production retrieval or generation behavior.
2. **B — Grounded answer contract:** add canonical evidence, structured claims, typed outcomes,
   derived legacy fields, frontend-compatible API fields, shadow mode, and rollback.
3. **C — Deterministic path closure:** close Q004/Q017 entity extraction, natural exact-title
   Type1, and Type2 predicate/pagination/synthesis behavior.
4. **D — Type4 retrieval quality:** add structured filters, local hybrid candidates, paper-level
   aggregation, partial-rich policy, and local/Web provenance separation.
5. **E — Type3 traversal:** add company-to-professor-to-paper traversal with two-hop provenance.
6. **F — Index parity and data lanes:** add the embedding ledger, reconciler, resumable lanes, and
   snapshot parity evidence.

A slice can depend only on an Accepted predecessor. Each slice is separately verified and reviewed,
with an immutable diff/artifact hash; an isolated commit is recorded only when explicitly
authorized. A later slice MUST NOT absorb a failed predecessor's work.

Large B and D scopes have mandatory internal acceptance checkpoints while remaining the six locked
top-level slices:

- **B0 foundation:** provenance preflight, public model/golden schema, additive retrieval-status
  port, and reversible result-set store/cursor;
- **B1 grounding:** evidence identity/composition, typed supports, bounded verifier, outcomes,
  canonical API, and compatibility projection;
- **B2 consumers/rollout:** React/static consumers, minimized signed feedback, shadow isolation,
  cutover evidence, and rollback;
- **C0 identity/Type1:** Q004/Q017 entity/route closure, exact-title resolution, and separately
  provenanced Web fallback;
- **C1 Type2:** predicate, stable materialized pagination, shared topic-search port, and paper-aware
  synthesis;
- **D0 substrate:** paper-subject schema/source cohort, category aliases, lexical indexes, derivative
  snapshot, migration/query-plan/rollback evidence;
- **D1 retrieval:** structured planner, dense/lexical fusion, paper aggregation/rerank, partial/Web
  policy, sealed holdout quality, semantics, and latency.

Each checkpoint moves Specified -> Ready -> Candidate -> Accepted with its own immutable diff/artifact
hash, review decision, and rollback proof. B1 cannot edit before B0 Accepted; B2 waits for B1; C1
waits for C0; D1 waits for D0. Slice B/C/D as a whole becomes Accepted only after all of its
checkpoints are Accepted.

### 2. Use one ordered list of atomic evidence

The server constructs `evidence_items` once. Prompt serialization, output validation, API response,
legacy citation derivation, and UI numbering consume that exact ordered list. No layer independently
rebuilds or renumbers citations.

The logical evidence shape is:

```text
EvidenceItem
  evidence_id       deterministic identity, never a display ordinal
  object_type       paper, professor, company, relation, patent, web_page, ...
  object_id         canonical local ID or stable Web-source identity
  field             field or relationship fact supported by the evidence
  value             typed value/object ID used by deterministic claim validation
  snippet           smallest useful fact or source span
  source_type       existing EvidenceSourceType (for example official_site or public_web)
  source_url/file   at least one, as required by Data-Agent-Shared-Spec §4.5
  fetched_at        required ISO-8601 timestamp for every source
  confidence        optional 0..1 source confidence
  source_lane       local | web; follows canonical-local vs uncatalogued-live-Web identity
  record_quality    canonical stored quality enum or null; never overloaded with relation meaning
  relation_tier     none | strong | secondary
  limitations       zero or more user-safe quality/provenance limitations
```

`EvidenceItem` extends rather than replaces the shared `Evidence` contract. A database row locator
may be retained as extra trace metadata, but it does not replace the required source URL/file and
fetch time. `secondary_relation` is a relation tier/limitation, not a quality-status value.
`source_lane` follows object identity: a canonical local object stays `local` even when its original
provenance `source_type` is `public_web`; only an uncatalogued live Web result uses lane `web`.
Local/Web is never encoded by inventing new shared source-type values.
`record_quality` is a required nullable field in the canonical JSON shape. It carries the exact
wire value from `record-quality-v1 = ready | needs_review | low_confidence | needs_enrichment |
partial | rejected | null`. This is a chat evidence projection enum, not a redefinition of the
shared four-state quality contract: the first four map directly; current domain-local `partial` is
preserved so partial-rich disclosure is schema-valid; `rejected` is allowed only in exclusion/audit
evidence and never makes an object eligible. Legacy `incomplete`/`shallow_summary` normalize to
`needs_review` before the wire and are not enum values. The field is null for uncatalogued live Web
pages, relation-only evidence, or a canonical object without retained quality, with a
`quality_not_available` limitation when material. Null means not applicable/unavailable, not a new
quality value, and synthesis cannot treat it as ready.

`evidence-id-v1` is `ev1_` plus lowercase SHA-256 hex over `lp(canonical_json_bytes)`, where
`lp(x) = uint32_be(byte_length(x)) || x`, and the UTF-8 canonical JSON is RFC 8785 serialization of
`{source_type, source_url, source_file, fetched_at, object_type, object_id, field, typed_value,
snippet}`. Both locator keys are always present with string or JSON null and at least one MUST be
non-null; if both are retained, both participate. Empty strings normalize to null.

`evidence-url-v1` accepts only absolute HTTP(S) URLs without userinfo and uses the WHATWG URL parser
and serializer: lowercase scheme/host, WHATWG IDN/percent/dot-segment serialization, remove the
default port and fragment, and preserve serialized query order/duplicates (never sort query
parameters). `evidence-file-v1` is a logical POSIX locator: UTF-8 NFC, backslash converted to slash,
duplicate slash and `.` segments removed, `..`/NUL rejected, case preserved, and no filesystem
resolution. `fetched_at-v1` parses an offset-bearing RFC 3339 instant, rejects naive/leap-second
input, converts to UTC, and emits exactly `YYYY-MM-DDTHH:MM:SS.ffffffZ` (padding zero microseconds).
All other strings use Unicode NFC and LF newlines; object keys/numbers use RFC 8785. Response order
is absent. A duplicate hash with unequal
canonical bytes is a hard collision error (no suffix-by-order); identical bytes deduplicate. Golden
Python/TypeScript cross-process/platform/order vectors lock URL IDN/escaping/query, file paths,
timestamps, null/both locators, and the full ID. One item supports one atomic fact/coherent
span, and relationship claims cite edge plus destination evidence.

Before Slice B implementation, a read-only per-domain/per-field provenance preflight measures how
many candidate facts can be joined to shared-contract source type, URL/file, fetched-at, and snippet.
A DOI-derived URL, canonical `updated_at`, table locator, or invented browse link cannot substitute
for retained source evidence. Missing provenance makes the affected claim unavailable or a disclosed
partial result. If a required P0 intent lacks joinable provenance and fixing it needs canonical
schema/data/auth expansion outside B, the slice stops for re-planning rather than weakening evidence.

### 3. The model proposes structured claims; the server owns validation and rendering

Synthesis returns structured sections/items/claims rather than a free-form answer with embedded
numeric markers:

```text
AnswerSection(section_id, title, items[])
AnswerItem(item_id, result_set_id, object_id, claims[])
AnswerClaim(claim_id, claim_type, subject_id, predicate, value, text, support_refs[])
SupportRef = EvidenceSupport(evidence_id) | ResultSetSupport(result_set_id, assertion) |
             LaneSupport(lane_assertion_id, assertion)
ResultSetMeta(result_set_id, domain, predicate, ordering, completeness, total, page_size,
              next_cursor, snapshot_id, item_ids[])
```

The server validates every referenced ID against `evidence_items`, rejects unknown IDs, checks that
required list items have evidence, applies deterministic coverage rules, and renders the canonical
answer and citation markers. Identity, field, relationship, set-membership, count, and completeness
claims are checked against typed evidence/payload fields rather than text similarity. A model cannot
create display ordinals or citation records.

For deterministically typed claims, server templates render user-visible claim text from the
validated subject/predicate/value; model-suggested text cannot contradict the tuple. Derived claim
text is validated in full by the cited-span entailment verifier. Section titles are non-material
labels and cannot carry an unvalidated factual assertion.

A **material claim** is any externally checkable assertion about an entity, field value,
relationship, date, number, rank, set completeness/absence, causal statement, or recommendation
basis. Pure formatting and connective text are non-material. A derived-summary material claim that
cannot be checked deterministically must pass a fail-closed runtime entailment verifier against only
its cited evidence spans. Rank, comparative, representative/top, count, absence, and completeness
claims must instead be checked deterministically against the full materialized `result_set_id`, its
predicate/order versions, and typed item facts; a single cited span or entailment model cannot prove
a universe-wide comparison. Successful-empty/error/degradation claims bind to typed lane trace, not
a fabricated source citation. Unknown, contradictory, unsupported, or unverifiable material claims
cannot appear in `success`; verifier unavailability yields `partial_result` or `synthesis_error`
rather than silently trusting the synthesis model. The offline independent semantic judge remains a
separate acceptance layer and does not substitute for this runtime support check.

Runtime derived support uses one named port:

```text
ClaimEntailmentVerifier.verify(
  claims: tuple[DerivedClaim, ...],
  cited_spans: tuple[EvidenceItem, ...],
  context: VerifierContext,
) -> tuple[EntailmentVerdict, ...]

EntailmentVerdict(claim_id, supported, reason_code, model_id, prompt_version)
```

Before B becomes Ready, the production adapter is bound to an approved existing LLM model/prompt/
version with temperature, timeout, and cost settings; no new provider is added. One request batches
at most 20 derived claims and 12,000 cited-span characters with a 5-second verifier deadline. Larger
required input yields explicit partial/synthesis failure rather than silent truncation. Tests use a
deterministic fixture adapter and cover malformed/missing/timeout/mixed verdicts. The adapter never
receives uncited evidence or credentials.

For list answers, each returned object is an item with its own identity claim and evidence. For
cross-domain answers, the evidence builder composes all applicable domain blocks; a professor block
must not cause an early return that drops joined paper evidence.

List responses include `result_sets` metadata. The API accepts an optional opaque
`continuation_cursor`; the cursor is bound to query predicate, stable ordering, and snapshot ID.
`completeness` is one of `complete`, `page`, `ranked`, or `partial`. A stale/mismatched cursor fails
truthfully instead of restarting at a different snapshot. This additive schema is created in Slice
B and populated by Slice C/E list planners.

The public JSON shape is not left to implementation:

```text
TypedValue = StringValue | IntegerValue | NumberValue | BooleanValue |
             StringListValue | IdListValue
ClaimType = identity | field | relationship | set_membership | aggregate |
            completeness | absence | ranking | derived_summary
ObjectType = professor | paper | company | patent | relation | web_page
Completeness = complete | page | ranked | partial

CanonicalChatRequest
  query
  entity_id_hint?                       # retained explicit canonical-ID selector
  clarification_token?                 # required by canonical UI selection round-trip
  continuation_cursor?, page_size?      # additive list continuation

CanonicalChatResponse
  contract_version: "canonical-v1"
  response_id: UUID
  response_integrity: signed canonical-payload hash
  query, query_type
  evidence_items: EvidenceItem[]
  result_sets: ResultSetMeta[]
  lane_assertions: LaneAssertion[]
  sections: AnswerSection[]
  outcome: Outcome
  compatibility: CompatibilityProjection
  answer_text, citations                 # derived compatibility only
  evidence, structured_payload           # derived legacy compatibility only
  clarification, suggested_followups     # retained public interaction fields
  answer_style, citation_map              # derived compatibility only

ResultSetMeta
  result_set_id: UUID
  domain: professor | paper | company | patent
  predicate_id, predicate_version, predicate_args
  order_id, order_version
  completeness, total, page_size, next_cursor, snapshot_id
  object_ids[]                           # current-page canonical IDs, not AnswerItem IDs
  ordered_manifest_hash                  # full materialized ordered ID/sort-tuple set

CompatibilityProjection
  legacy_projection: lossless | lossy
  omitted_evidence_ids[]
  reasons[]
```

Canonical mode retains every field in the current public `ChatResponse`; none is silently removed:

- `answer_text` is server-rendered from validated sections/claims; `citations` and `citation_map`
  are derived from the one ordered evidence list. `citation_map` maps each rendered marker to the
  exact `evidence_id` and cannot be independently supplied by synthesis.
- legacy `evidence` is a documented projection of canonical evidence. Any object/source type it
  cannot represent is declared in `compatibility`; it cannot be recast as another entity type.
- `structured_payload` is a read-only compatibility projection from canonical result sets/items and
  never becomes a second retrieval or grounding source.
- `answer_style` remains exactly `template | llm_synthesized`: deterministic-only rendering maps to
  `template`; accepted structured model output maps to `llm_synthesized` even though final text is
  server-rendered.
- `entity_id_hint` remains supported. A bare hint is an explicit user canonical-ID selector and
  still must resolve to source-grounded canonical evidence; the request value itself cannot satisfy
  retrieval or citation. The canonical UI's clarification selection sends the chosen hint plus the
  response's signed `clarification_token`; the server rejects an ID outside the bound option set,
  stale/tampered/cross-session tokens, and token/query-domain mismatch. Legacy mode retains its
  existing bare-hint behavior and golden round-trip fixture.
- `clarification` remains the existing `ClarificationPayload | null`, additively extended in
  canonical mode with a `clarification_token`, per-option typed support refs, and result-set support
  for `omitted`. It is required for `clarification_required` and covered by the response signature.
  The prompt is a neutral server template; each option label/hint fact must validate against atomic
  evidence (unsupported hint fields are omitted), and option/omitted counts bind the materialized
  candidate result set. Its legacy `default_id` is display compatibility only and MUST NOT
  auto-select an ambiguous entity or imply a recommendation.
- `suggested_followups` remains a maximum-five string list, is server-generated only from validated
  route/result metadata, and cannot introduce unsupported factual claims.

Golden old-client/new-client fixtures cover required, null, empty, and absent behavior for all of
these fields in legacy, shadow, and canonical modes. In legacy/shadow the exact existing schema is
preserved; in canonical mode the fields are present with the mappings above. The response-integrity
signature covers canonical fields and every retained public compatibility/interaction field.
Request fixtures also cover the existing `entity_id_hint`, canonical hint+token round-trip,
continuation, and invalid combinations: a clarification token requires an entity hint; selection
fields cannot accompany a continuation cursor; and continuation page size must equal its bound value.

Each `TypedValue` is a discriminated object with exactly one value field. `predicate_id`,
`reason_codes`, and claim predicate values come from versioned server registries/enums declared in
the Pydantic/OpenAPI schema; arbitrary model strings are rejected. Initial reason codes are
`clarification_required`, `unsupported_query`, `local_snapshot_miss`, `partial_coverage`,
`lane_error`, `lane_timeout`, `evidence_truncated`, `invalid_cursor`, `stale_cursor`,
`clarification_conflict`, `unsupported_claim`, `verifier_unavailable`, `synthesis_invalid`, `web_supplement`, and
`category_coverage_incomplete`. Golden JSON and OpenAPI snapshots lock required/null/absent fields
before Slice B production edits.

Source-grounded facts use `EvidenceSupport`; count/rank/completeness/set assertions use
`ResultSetSupport`; and successful-empty/error/degradation assertions use `LaneSupport`. A material
claim may not have an empty support list. Result-set/lane supports are structured audit assertions,
not fabricated source documents, and do not enter the citation ordinal list.

The result store computes a deterministic ordered manifest hash (and inclusion proof for a claimed
rank/member) over `(ordinal, object_id, sort_tuple_hash)`. Canonical result-set and lane supports copy
sanitized assertion data/proofs into the signed response, so validation, semantic judging, and later
feedback do not dangle after transient result rows or trace logs expire.

The wire algorithms are versioned and fixed before B0 implementation. In every algorithm below,
`lp(x) = uint32_be(byte_length(x)) || x`; `lp_utf8(s) = lp(UTF-8(NFC/LF(s)))`; ordinals are
zero-based unsigned 64-bit integers; and concatenation is byte concatenation:

- **`result-manifest-v1`:** canonicalize each sort tuple as RFC 8785 JSON after Unicode NFC/LF
  normalization. A leaf is `SHA-256(0x00 || uint64_be(ordinal) || lp_utf8(object_id) ||
  lp(sort_tuple_json_bytes))`; an internal node is `SHA-256(0x01 || left || right)`, duplicating the
  final node at an odd level. The root is `rm1_` plus lowercase hex. A proof contains ordinal,
  object ID, canonical sort tuple, and ordered sibling `{side, hash}` values. Empty sets use the
  root `rm1_` plus lowercase hex of `SHA-256(0x02)`. Unequal duplicate object IDs are invalid rather than silently
  merged.
- **`response-integrity-v1`:** canonicalize the complete public response except
  `response_integrity` as RFC 8785 UTF-8 after NFC/LF normalization and hash with SHA-256. The token
  is `ri1.<key_id>.<issued_at>.<expires_at>.<payload_hash_b64url>.<signature_b64url>`; signature is
  `HMAC-SHA256(key, lp_utf8("ri1") || lp_utf8(key_id) || lp_utf8(response_id) ||
  lp_utf8(session_id) || uint64_be(issued_at_epoch_s) || uint64_be(expires_at_epoch_s) ||
  lp(payload_hash_bytes))`. Base64url omits padding. Verification uses constant-time comparison and an environment-held
  active/previous key ring; a key ID never reveals key material.
- **`cursor-v1`:** token is `c1.<payload_b64url>.<signature_b64url>`. Its RFC 8785 payload contains
  version, key ID, result-set ID, next ordinal, preceding full-sort-tuple hash (or literal
  `c1_start`), predicate/order hash, page size, session-binding hash, issued-at, and expiry;
  signature is `HMAC-SHA256(key, ASCII("c1") || lp(payload_bytes))`. Decoding
  rejects unknown keys/fields/version, noncanonical re-encoding, bad signature, expiry, cross-
  session binding, and predicate/order mismatch before reading a page.
- **`clarification-token-v1`:** token is `ca1.<payload_b64url>.<signature_b64url>`. Its RFC 8785
  payload contains version, key ID, random 128-bit nonce, response ID, query/domain hash, ordered
  allowed option IDs, session-binding hash, issued-at, and a maximum 30-minute expiry. Signature is
  `HMAC-SHA256(key, ASCII("ca1") || lp(payload_bytes))`. Canonical selection requires the chosen
  `entity_id_hint` to occur in that ordered set. First use atomically records the selection;
  concurrent or later reuse with the same ID is idempotently accepted, while reuse with a different
  ID fails as `clarification_conflict`.

Golden vectors from at least two processes and the backend/frontend language boundary lock byte
encoding, Unicode, number, empty/odd tree, entity-hint selection, key rotation, and tamper behavior. A future algorithm
requires a new version prefix and dual-read migration; implementations cannot change v1 in place.

Stable continuation uses an additive reversible `chat_result_set` plus `chat_result_set_item`
store, not a fictitious long-lived Postgres MVCC snapshot. At first-page time it materializes the
complete ordered object-ID/sort-tuple hashes/values and manifest state under a result-set ID,
predicate/order versions, source snapshot fingerprint, session, creation time, and
30-minute expiry. A signed opaque cursor carries result-set ID, next ordinal, preceding full-sort-
tuple hash, predicate/order hash, and expiry. Expired, missing, cross-session, or mismatched cursors
return `stale_cursor`/
`invalid_cursor` with a restart action. TTL cleanup and payload-size/privacy limits are tested. Slice
B owns this generic store/codec; Slice C/E own their real set materialization and page semantics.

The result-set store contains only canonical IDs, sort-tuple hashes/values, predicate/order metadata,
session binding, and manifest state—no query, raw Web snippet, or source payload. Page evidence is
fetched/validated normally; source-row drift yields a disclosed partial result while enumeration
stays stable.

A separate reversible `chat_clarification_action` TTL store owns replay semantics. It contains only
the SHA-256 nonce hash, response/session hashes, candidate result-set/option-set hash, selected
canonical ID, first-consumed timestamp, and expiry—no query, label, hint, snippet, URL, or response
body. Selection uses one atomic compare-and-set: first use records the ID; the same ID is an
idempotent retry; a different ID is a conflict; expired/missing state is stale. B0 owns migration,
30-minute cleanup, concurrency, and downgrade tests. Downgrade occurs only after TTL drain and
legacy mode restore; B2 consumers do not invent client-side replay semantics.

Because the admin console currently has no authentication, Slice B does **not** add a durable raw
canonical-response store or a new unauthenticated read surface. Canonical feedback echoes the exact
canonical response plus `response_integrity`. The token is HMAC-signed with an environment-managed
rotatable key, binds response ID/session ID/payload hash/issued-at/7-day expiry/key ID, and never
contains the key or cookie. The server verifies it, rejects expired/tampered/cross-session payloads,
and idempotently creates at most one issue per response/feedback kind. It writes only a
minimized redacted issue record (response ID/version, outcome/reasons, claim/object/evidence IDs,
source lanes/tiers, result/lane assertion hashes, and run IDs—no query, snippets, URLs, cookies,
authorization, or raw provider payload). Legacy feedback remains compatible. Any durable raw
response/evidence review UI is an auth/trust-boundary change and blocks for a separately approved
OpenSpec; it cannot be smuggled into Slice B.

### 4. Add a typed outcome instead of conflating absence and failure

The canonical response includes:

```text
Outcome
  status: success | partial_result | no_result | retrieval_error | synthesis_error
  reason_codes[]
  degraded_notes[]
```

The retrieval boundary returns a typed envelope rather than a bare list:

```text
RetrievalResult(candidates[], lane_statuses[], errors[], timing, snapshot_id, trace_id)
LaneStatus(lane, status=success|empty|error|timeout|skipped, reason_code, elapsed_ms)
```

Slice B introduces this as an additive chat-owned retrieval port/new method. Existing shared
`RetrievalService.retrieve() -> list[Evidence]` remains compatible and projects only candidates;
internal provider/storage adapters expose status to the new port instead of swallowing it. Candidate
selection and ranking do not change. Therefore chat can distinguish successful empty retrieval from
provider, storage, or timeout failures before Type4 behavior is deepened in Slice D.

- `success` means the requested intent is satisfied with validated evidence.
- `partial_result` means useful validated evidence exists but a requested constraint, page, source
  lane, or synthesis portion is incomplete; it also represents safe clarification/refusal responses
  with `clarification_required` or `unsupported_query` reason codes and no unsupported factual
  claims. The limitation or next action is explicit.
- `no_result` is valid only after the planned retrieval completed successfully and found no
  qualifying evidence.
- `retrieval_error` means a required retrieval path failed or could not be verified.
- `synthesis_error` means evidence exists but validated structured synthesis could not be produced.

Provider fallback does not silently turn an error into `no_result`. Deterministic rendering of
retrieved evidence may accompany an error or partial outcome, but the status remains truthful.

### 5. Migrate the API additively and keep rollback immediate

The response adds `contract_version`, canonical `evidence_items`, `result_sets`, structured
`sections`/`claims`, `outcome`, and `compatibility` fields. In canonical mode, `answer_text` and
`citations` are derived exclusively from validated canonical fields; they are not a second
generation path. A legacy citation can represent only its existing local entity enum. Web or
relationship evidence MUST NOT be miscast as a local paper/company/etc.; an unrepresentable item is
listed in `compatibility.omitted_evidence_ids` with `legacy_projection=lossy`. Canonical mode cannot
serve a consumer that still requires a lossless legacy projection for such a response.

`CHAT_GROUNDED_ANSWER_MODE` has three modes:

- `legacy`: externally return the byte/schema-compatible existing legacy path with no
  `contract_version`; field absence means legacy to the dual-read frontend;
- `shadow`: externally byte/schema-compatible with legacy and with no `contract_version`; canonical
  execution and redacted diffs stay internal and
  MUST NOT leak canonical fields to the caller;
- `canonical`: `contract_version=canonical-v1`; return canonical fields plus explicitly lossless or
  lossy derived compatibility fields.

The frontend selects exactly one renderer from `contract_version`; it never merges canonical and
legacy citation arrays. Absence of `contract_version` selects legacy. Returning to legacy mode
exercises the existing renderer and response shape.
Cutover requires the frozen suite plus a privacy-approved, redacted shadow corpus covering every
supported A-G route (at least 10 cases per route), every outcome/failure fixture, and local/Web
lanes. Required gates are zero canonical schema/citation/unsupported-claim/P0 failures, no frozen
semantic regression, external legacy-response identity in shadow, canonical latency SLO compliance,
and zero secret/cookie/authorization persistence. Real user traffic is not retained without an
explicit approved data-handling basis.

Shadow execution is failure-isolated and bounded: it cannot change legacy status/body, and it runs
off the response-critical path. Enqueue/instrumentation adds at most 50 ms p95 and 100 ms p99 to the
legacy response under the frozen protocol; shadow timeout/failure is recorded internally and never
converted into a user-visible legacy failure.

Cutover requires accepted shadow evidence. Switching the mode back to `legacy` is the immediate
rollback. Legacy implementation removal is a later, separately approved cleanup after frontend and
API consumers have migrated.

### 6. Freeze evaluation identity before implementation

The manifest records, per case, the query, route/path, expected local object IDs, predicates,
required intents, forbidden claims, expected outcome, and scoring policy. A run also records the
database snapshot/version, Milvus collection and index version, embedding model/version, code SHA,
judge configuration, and raw request/response artifacts.

“Snapshot/version” means an immutable read-only clone or a verified cryptographic manifest, not a
mutable database label or Milvus alias. The database manifest covers the full query-visible table
projection for every exercised planner—eligible candidates, distractors, exclusions, content/
lifecycle fields, and relationship IDs/statuses—not only gold IDs. The Milvus manifest covers the
physical collection target/schema plus ordered chunk/paper/content and deterministic vector-byte/
dimension hashes (or a trusted immutable physical-segment checksum) and entity count. Both
fingerprints are captured before and after each paired run; any drift invalidates the
comparison. Slice A also performs a read-only two-level paper/chunk parity preflight. If current
index gaps make the frozen Type4 substrate non-viable, Slice A stops for an explicit sequencing or
substrate decision rather than letting D fail after B/C acceptance.

Parent and candidate runs use the same snapshot and manifest. The scorer reads only canonical
retrieved IDs, evidence IDs, claims, and typed outcomes; request echoes, prompts, debug payloads,
and configuration fields are excluded. The 100-case classifier benchmark also asserts expected
target domain, normalized name/topic, and planned endpoint where applicable; type alone cannot pass.

For Type4, topic queries, inclusion criteria, relevance rubric, and a blinded labeling protocol are
frozen before implementation. The corpus has a visible development set and a separate sealed
acceptance holdout. After parent and candidate raw holdout outputs are captured, their returned local
paper-ID union is anonymized/randomized and independently labeled by at least two blinded reviewers
with saved rationales. Disagreements are adjudicated and labels sealed before scores/run identities
are revealed; raw agreement and Cohen's kappa are reported, and kappa below 0.60 blocks scoring until
the rubric is repaired and a fresh blind review runs. If implementation changes after holdout
judgments are unblinded, that holdout becomes regression-only and a fresh versioned sealed holdout/
union is required for re-certification. This is precision over frozen topics, not a pre-labeled
corpus universe, so it MUST NOT report recall.

The sealed holdout is not plaintext in the working tree. The repository contains its schema,
stratum counts, rubric, and cryptographic hash; an independent reviewer/CI secret custodian holds
the encrypted query/expected artifact with access logging. Evaluation is one-shot, emits a signed
result tied to the versioned hash, then discloses/rotates the used holdout into regression-only. No
agent implementing D receives the sealed queries or labels before the run.

### 7. Give path activity and Type1/Type2 explicit semantics

The word “active” is not an implementation-defined convenience. `retrieval-active-v1` maps current
physical states as follows and Slice A freezes its SQL/rule hash:

- company: `identity_status='resolved'` only;
- professor: `identity_status='resolved' AND lifecycle_state='active'`;
- paper: `identity_status IN ('confirmed','unverified')` and
  `coalesce(quality_status,'needs_enrichment') <> 'rejected'`; unverified identity is visibly
  limited and cannot support an implicit confirmed-identity claim; rejected/merged are terminal;
- professor-paper and strong company-professor edges: `link_status='verified'`; secondary team
  membership additionally uses the latest-snapshot/matched rule in Decision 10.

This is the Type1-Type3 node/edge universe. A merged paper may resolve only to a survivor satisfying
the mapping. Type4 dense/index admission additionally requires `index_eligibility=true`. The mapping
is grounded in the current company/professor canonical identity enums, professor lifecycle enum,
paper V020 identity enum, and verified-link enums; a generic `!= rejected` substitute is not
equivalent.

Type1 exact-title parsing removes conversational wrappers such as “这篇论文的详细信息” while
preserving the candidate title. Quoted and bare titles resolve to the same canonical paper ID; no
substring-only pass is accepted. Multiple active exact-title IDs require clarification; no rank
guess selects one. A merged match follows the canonical merge survivor with merge-edge trace, while
rejected/terminal-only matches do not count as local success and enter the explicit-title Web-miss
policy. An exact identity with no source-grounded detail can return only a disclosed partial identity
answer (and optional Web supplement), never invented profile facts.

Type2 first resolves the professor and then applies a typed paper predicate:

- **all/list**: the complete verified, nonterminal linked set is exposed through stable pagination;
- **year/range/recent**: use canonical `paper.year`, filter/order by the requested constraint, and
  disclose the effective constraint/reference year;
- **topic**: intersect the resolved professor's verified papers with the parsed paper topic;
- **representative**: rank by documented significance signals and label the result as ranked rather
  than complete.

The exact ordering/product rules are fixed here rather than selected during implementation:

- all/list and year/range pages default to 20 and cap an explicit page size at 50; ordering is
  `year DESC NULLS LAST, citation_count DESC NULLS LAST, paper-title-sort-v1 ASC, paper_id ASC`;
- exact year/range excludes rows with null year; all/list retains them at the end;
- bare “最近/最新” means recency-ranked first page with `completeness=ranked`, not an invented time
  cutoff; explicit “近 N 年” is the inclusive range `[reference_year-N+1, reference_year]`, where
  `reference_year` is captured in Asia/Shanghai at the first request and bound into the cursor;
- representative work defaults to 10 (maximum 20 when explicitly requested) and orders by
  `citation_count DESC NULLS LAST, year DESC NULLS LAST, paper-title-sort-v1 ASC, paper_id ASC`;
- topic queries call the single shared `PaperTopicSearch` interface on the same snapshot and
  intersect its canonical paper IDs with the professor's complete verified set. Slice C reuses the
  current provider behind that interface; Slice D deepens the provider and must rerun Type2 topic
  gates. No second shallow matcher may be added. Topic output is ranked unless a frozen exhaustive
  predicate set exists.

The new shared port is explicit:

```text
PaperTopicSearch.search(
  predicate: PaperTopicPredicate,
  candidate_ids: tuple[paper_id, ...] | None,
  snapshot_id: str,
) -> RetrievalResult[PaperTopicCandidate]

PaperTopicCandidate(paper_id, fused_score, lane_scores, matched_constraints, evidence_ids)
```

Slice C supplies a production adapter over the current paper-topic provider and a deterministic test
adapter; it intersects returned canonical IDs with the verified professor set. Slice D may replace/
deepen the production adapter but not fork the port, payload, lane status, or predicate semantics.

Pagination returns a total, stable cursor/page identity, effective predicate/order, and no
duplicates or omissions under the frozen snapshot. The opaque cursor binds the last full sort tuple,
predicate/order version, page size, and materialized result-set snapshot. `paper-title-sort-v1` is
the two-key SQL tuple
`(CASE WHEN btrim(regexp_replace(coalesce(title_clean, ''), E'\\s+', ' ', 'g')) = '' THEN 1 ELSE 0 END,
btrim(regexp_replace(coalesce(title_clean, ''), E'\\s+', ' ', 'g')) COLLATE "C")`, both ascending.
The first key is computed, not a schema column; it puts empty/whitespace-only titles last. No
application-local normalizer participates. Synthesis
consumes the current paper page plus this metadata.
Fixed answer truncation or a pre-pagination database LIMIT cannot define completeness.

Organization/location prefixes in Q004/Q017 are context, not part of the professor name. These
frozen cases ask for a professor profile, so the classifier, normalized professor name, professor
domain endpoint, resolved professor ID, and citation must agree; they do not imply a paper
predicate or Type2 traversal. The same normalization mechanism also applies before a distinct
professor-paper query begins Type2 traversal.

### 8. Build Type4 candidates through independent local lanes and aggregate by paper

The current canonical paper table has no persisted category/field-of-study relation and no approved
mixed Chinese/English lexical index. Slice D therefore begins with a reversible substrate checkpoint
inside its own scope, after Slice C is Accepted:

- add a normalized `paper_subject` relation (paper ID, taxonomy/scheme, subject ID and label,
  normalized label, shared source evidence, confidence, run ID, lifecycle timestamps) rather than a
  lossy comma-separated field;
- populate only categories supported by retained authoritative academic-source evidence; unknown
  category remains unknown and is never inferred from title text merely to pass a filter;
- add the narrowly scoped reversible PostgreSQL FTS/trigram indexes needed for bounded mixed-language
  title/abstract/summary/full-text lexical search, with query-plan and rollback evidence;
- version the category alias map. An ambiguous category asks for clarification; missing category
  coverage produces a disclosed partial result rather than silently ignoring the filter.

The category backfill cohort is selected only by a pre-output frozen canonical lifecycle/source SQL
predicate and source snapshot, never benchmark query/expected-ID membership. Input IDs, denominator,
processed IDs, exclusions, and residual owner are saved; the declared cohort is fully processed or
its residual is reported. Because this approved substrate changes the DB, D creates a new immutable
derivative of the A snapshot after migration/backfill and before retrieval outputs. Its manifests and
category expectations are frozen/reviewed, then both parent and candidate run against that identical
derivative (the parent may ignore the new table/index). The original A baseline remains immutable;
no post-output substrate or expected-ID changes are allowed.

The planner extracts topic text plus structured year/range, category, and recency constraints.
It reuses the shared paper time predicate: canonical field is `paper.year`; exact/range and explicit
N-year filters exclude null; the Asia/Shanghai reference year is captured in the predicate; bare
latest adds no hidden cutoff and orders qualifying topic papers by year descending null-last, fused
relevance descending, then paper ID. Exact/range/category filters apply before fusion/rerank; bare
latest's recency order applies after relevance qualification and paper deduplication.
Dense vector retrieval and local lexical/FTS retrieval execute as independent candidate lanes when
available. Either lane can produce local candidates; embedding failure degrades to lexical rather
than producing a false empty result.

Candidates are normalized and grouped by canonical `paper_id` before fusion and reranking. Chunk
matches contribute features to one paper candidate, so repeated chunks cannot occupy multiple
final positions. Structured filters apply at paper level. The final top five are evaluated with a
frozen-topic micro-`Precision@5 >= 85%` gate. For N frozen topics, the denominator is exactly
`5 * N`; each unique relevant local paper in its top-five slot contributes one, while missing slots,
duplicate slots, non-local/Web items, and irrelevant items contribute zero. The manifest includes
only topics for which reviewers establish at least five relevant local papers in the snapshot.
Per-topic P@5 is reported as a diagnostic; the 85% hard gate applies to the defined micro aggregate,
not to each five-slot topic independently.

Active `partial+rich` papers participate with an explicit rank penalty and visible quality notes;
they are not globally suppressed merely because a ready paper exists. Title-only records are not
eligible for dense retrieval until enriched, though exact/lexical behavior may expose them only
when the relevant slice defines and discloses that degradation.

### 9. Keep local and Web provenance in separate lanes

Web evidence has shared `source_type=public_web`, `source_lane=web`, a canonical URL, and fetch time.
It can supplement an
answer when local evidence is insufficient or the user explicitly asks for latest external
information. It cannot satisfy a local-object recall assertion, masquerade as a local paper, or
inherit local quality status. Local and Web sections remain distinguishable in the rendered answer
and evaluation.

### 10. Make Type3 a provenance-bearing two-hop plan

Company-to-paper retrieval is:

```text
company --professor_company_role--> professor --verified professor_paper--> paper
company --resolved company_team_member--> professor --verified professor_paper--> paper
```

`professor_company_role` is the strong relationship tier. A
`company_team_member.resolved_professor_id` edge is a secondary tier and is labeled as such; it is
not upgraded to verified employment. Unresolved names do not participate. Professor-to-paper edges
must be verified and nonterminal. Each result preserves the company ID, professor ID, both edge
identities/tiers, paper ID, and supporting evidence; deduplication must not erase alternate paths.

Eligibility and output semantics are fixed:

- strong edges require `link_status=verified`; general “相关论文” includes current, former, and
  unknown-time verified roles with `is_current/start_year/end_year` disclosed, while an explicit
  current-role query requires `is_current=true`;
- secondary edges require the latest company snapshot by
  `(snapshot_created_at DESC, snapshot_id DESC)`, `resolution_status=matched`, and a non-null
  `resolved_professor_id`; `candidate` and merely non-null unresolved rows are excluded;
- company, professor, and paper nodes plus professor-paper edges must satisfy
  `retrieval-active-v1` under the snapshot;
- unique paper pages default to 20/max 50 and use the Type2 stable year/citation/title/ID order;
  each paper returns path count and up to 10 paths ordered strong before secondary, then professor
  and edge IDs. An opaque path cursor exposes remaining paths, so prompt budgets may summarize but
  the canonical API can traverse every alternate path without loss.

Slice E owns planner capability, not relationship-data population. It must publish a read-only
production-snapshot report with strong/secondary edge counts, eligible professors/papers/companies,
zero-coverage causes, and the separately owned data-remediation worklist. Fixture GREEN cannot be
described as production Type3 coverage closure when the real eligible set is empty or sparse.

### 11. Persist a per-paper embedding ledger and reconcile desired state

Canonical paper/full-text/lifecycle data plus the existing versioned `index_eligibility` predicate
remain the sole readiness authority. Index eligibility is recomputed on every reconciliation. A
separate versioned `enrichment_lane_membership` predicate family derives active needs-enrichment,
partial-title-only, and needs-review operational lanes; it cannot admit a paper to desired index
state or become a second readiness signal. The ledger stores a non-authoritative observation with
both applicable rule versions and derivation time; retrieval
admission never trusts a stale ledger row. This preserves the prior “no second persisted readiness
signal” contract.

Every paper in the declared reconciliation snapshot gets an audit row containing paper ID, derived
eligibility/reason, rule/source snapshot, normalized source-content hash, chunker/schema version,
expected chunk count/manifest hash, embedding model/version, target collection/index version, last
confirmed success, attempts, and failures. Success means the entire expected current chunk manifest
was confirmed, not merely that one vector exists.

Milvus `paper_chunks` is chunk-addressed: one paper legitimately has multiple `chunk_id` rows. Slice
F therefore adds a chunk/vector manifest with chunk ID, paper ID, type/index, content hash, embedding
model/version, chunker/schema version, target index version, and write/run identity. The candidate
collection row or a cryptographically linked sidecar exposes that tuple; a Postgres self-report is
not proof. Content, chunker/schema, model, or index drift triggers replay.

Parity is two-level: distinct desired paper coverage and exact expected-versus-actual chunk
ID/manifest/version state. Repeated paper IDs across different expected chunks are normal;
duplicate/conflicting chunk identity or unexpected manifests are defects. Ready and active
partial-rich papers selected by `index_eligibility` are index candidates; active
`needs_enrichment` and active partial title-only papers selected by their lane predicates are
enrichment lanes; `needs_review` is audit-only; rejected/merged are excluded from mutable lanes.

Lane jobs are checkpointed, idempotent, resumable, and safe to replay. A read-only full production
paper/chunk coverage report is required even when mutation is not authorized. A bounded
non-production rehearsal proves the mechanism only; production parity/backfill/promotion and each
residual enrichment lane remain explicitly pending until an authorized production run and active
index report establish them.

### 12. Acceptance is a three-stage, path-specific hard gate

Every P0 case passes only when all applicable stages pass:

1. the expected object ID is retrieved under the correct predicate;
2. the expected object/fact is correctly cited through canonical evidence identity;
3. the answer is semantically correct and complete for its required intents.

Priority is part of the frozen manifest, not a post-result label. Every distinct minimum-coverage
case, named true-RED case, and known citation/synthesis counterexample is P0 for each applicable
gate. P1 exists only for additive cases beyond those floors and is assigned with rationale before
any output. Deterministic-only classifier cases may mark live/semantic N/A only before output; P0
cannot be demoted, swapped, or waived after results are visible.

Deterministic checks cover schema, ID sets, predicates, pagination, citation validity/coverage, and
outcomes. An independently configured model judges semantic correctness, unsupported claims, and
required-intent coverage. Boundary scores are adjudicated by a human using the same saved evidence.
The command exits nonzero on any hard-gate failure.

Path gates are not averaged away:

- Type1 target-ID retrieval and citation: 100%;
- Type2 predicate/page completeness and returned-item citation: 100%;
- Type4 frozen-topic `Precision@5 >= 85%` and returned-item citation: 100%;
- Type3 eligible two-hop path IDs/tiers and returned-item citation: 100%;
- Q004/Q017 classifier, normalized name, professor domain/endpoint, professor ID, and citation:
  100%;
- P0 semantic cases: 100%; remaining semantic cases: at least 90%;
- unsupported material claims: zero;
- previously passing frozen cases: zero regression.

### 13. Preserve latency budgets with path-specific observations

Retrieval-on p95 remains at most 6 seconds and synthesis-on end-to-end p95 remains at most 15
seconds. Results are bucketed by Type1-Type4 and by local-only versus local-plus-Web execution so a
fast path cannot hide a slow one. Dense and lexical Type4 work should run concurrently where safe;
timeouts and degraded lanes must be represented in `outcome`, not hidden.

### 14. Verify through public boundaries and saved provider fixtures

Pure parsing, ID, ledger, and validator logic receives focused unit tests. Retrieval plans are
tested through the retrieval service with a real test database and deterministic vector/lexical
fixtures. Chat behavior is tested through `/api/chat` response models and frontend citation
rendering. Model, embedding, rerank, Milvus, and Web systems are mocked only at their provider or
storage boundaries; saved raw fixtures retain realistic schemas and failure modes. Paired
parent/candidate causal checks use identical saved boundary fixtures. Pinned live-provider
configuration is reported separately and is repeated at least three times per P0 case; it is never
described as deterministic fixture replay.

Unit tests alone cannot accept routing, RAG, citation, or generated-answer behavior. Acceptance
also requires API benchmark artifacts, semantic judge output, provenance inspection, and targeted
browser rendering evidence where the UI changes.

### 15. Preserve and eventually archive behavior dependencies explicitly

`make-partial-papers-retrievable` is an Accepted structural behavior dependency even though its
historical D3 measurement task remained open. Its implemented pure partial-rich eligibility and
snippet/admission requirements remain authoritative for this Epic. The unmeasured ready-but-not-
embedded D3 work is disjoint from that accepted behavior and is superseded by Slice F's full
paper/chunk reconciliation, which measures it as one residual lane under a frozen predicate.

Before Slice F becomes Ready, the dependency's accepted review and exact spec deltas are linked and
strict-valid. After its behavior has been represented in canonical specs (normally by archiving
`make-partial-papers-retrievable` with normal spec migration), its D3 task is recorded as superseded
by this Epic rather than falsely marked measured. The three narrow paper-retrievability predecessors
have broader overlapping in-flight `agentic-rag-retrieval` deltas; once their linked canonical gates
pass, they are accepted only as historical evidence and archived with `--skip-specs`, with
`superseded_by=close-retrieval-generation-contract` recorded. Default archival of those three is
forbidden because it could migrate stale overlapping behavior into the canonical specs.

`sigs-official-publications-to-paper-domain` is a modified in-verification dependency, not a fully
superseded predecessor: its official-publication ingest/bridge capability remains valuable and
eventually requires normal spec migration. Its historical Type1 title-only exclusion and ready-first/
non-ready-fallback Type4 clause are superseded by C0 identity-partial semantics and D1's single
ready+active-partial-rich paper competition. That change MUST NOT archive normally until C0/D1 plus
its pending task prove both aligned policies; `--skip-specs` would discard the unique SIGS capability.

### 16. Roll back through one dependency-aware matrix

Every Accepted checkpoint records its immutable diff/artifact hash, code SHA, schema revision,
data run/alias-map version, feature-flag values, index alias/target, and predecessor hashes. Planner
flags are mandatory and retained through the full observation window:
`CHAT_GROUNDED_ANSWER_MODE`, `CHAT_C0_IDENTITY_TYPE1_MODE`, `CHAT_C1_TYPE2_PLANNER_MODE`,
`PAPER_D1_TOPIC_RETRIEVAL_MODE`, `COMPANY_PAPER_TRAVERSAL_MODE`, and the F paper-index target/alias.
Removing a legacy branch or flag is outside this Epic.

An external safety rollback first sets chat to `legacy`; that restores the legacy public response
but does not pretend that data, planners, or index state were reverted. A real checkpoint rollback
then runs in reverse dependency order and records one rollback run/hash:

| Rolled-back checkpoint | Control and prerequisite | Accepted state that becomes Candidate with `invalidated_by` |
|---|---|---|
| A | Restore prior oracle only when no later work is relied on | B0-F, Epic, and all linked predecessor acceptance/archive eligibility |
| B0 | First set chat legacy, drain result/action TTL, then downgrade stores/models | B1, B2, C0-F, Epic |
| B1 | Set chat legacy and disable canonical construction; retain unused B0 | B2, C0-F, Epic |
| B2 | Set chat legacy, stop shadow/consumer rollout | Slice B acceptance, C0-F dependency eligibility, Epic cutover; B0/B1 evidence may remain Accepted |
| C0 | Disable C1 first, then C0 identity/Type1 flag | C1, D0-F, Epic, linked Q004/Q017/Type1 predecessor archive eligibility, and SIGS Task 5.20 |
| C1 | Restore prior Type2 adapter/planner | D0-F, Epic and Type2 predecessor archive eligibility |
| D0 | Restore F alias, disable E/D1, then remove run-owned subjects/indexes and alias map | D1, E, F, Epic and SIGS compatibility acceptance |
| D1 | Restore prior topic planner after any F alias restore | E, F, Epic, Type4 predecessor and SIGS Task 5.20 acceptance |
| E | Disable company-paper traversal before F replay/promotion | F and Epic |
| F | Stop jobs and restore the recorded prior index alias/target | F parity/promotion and Epic cutover only; A-E evidence remains Accepted |

If multiple checkpoints roll back, execute rows from F toward A, after the initial chat-legacy safety
switch. D0/B0 destructive downgrade is last within its dependency branch and only after consumers
are disabled and TTL/data-retention rules pass. An expected rollback drill does not invalidate
status; an operational rollback caused by a failed threshold does. Any real invalidation blocks
cutover and archive, creates a new observation window after re-acceptance, and prevents the three
historical predecessors or SIGS dependency from archiving. No archive occurs until the observation
window completes without a real rollback.

## Risks / Trade-offs

- **More response structure increases migration work.** Mitigation: additive fields, derived
  compatibility output, shadow mode, and a single rollback setting.
- **Atomic evidence may increase prompt size.** Mitigation: deduplicate by stable evidence identity,
  budget by required intent, and measure truncation/coverage explicitly rather than silently
  dropping a domain.
- **Runtime support verification and independent semantic judging can be nondeterministic.**
  Mitigation: use deterministic typed checks whenever possible, fail closed on verifier failure,
  pin model/prompt/version, repeat live P0 cases at least three times, save full inputs/outputs, and
  adjudicate boundary cases.
- **Hybrid retrieval can increase latency and ranking variance.** Mitigation: concurrent bounded
  lanes, paper-level fusion, fixed fixtures, per-path latency buckets, and lexical degradation.
- **Secondary company relations can be mistaken for verified roles.** Mitigation: typed tiers,
  edge-level evidence, and visible disclosure in output and tests.
- **Milvus reconciliation is not transactional with Postgres.** Mitigation: desired-state ledger,
  confirmed full chunk manifests, checkpoints, idempotent replay, and two-level paper/chunk parity
  before promotion.
- **Category/lexical substrate is absent from the current canonical schema.** Mitigation: make the
  normalized subject relation and PostgreSQL search indexes an explicit reversible Slice D
  prerequisite, preserve source evidence, and stop rather than infer categories or run an unindexed
  full scan.
- **The dataset changes while implementation proceeds.** Mitigation: frozen snapshot identity for
  comparison; new snapshots create new baselines instead of rewriting old results.

## Migration Plan

1. Accept Slice A's fixed manifest, evaluator, frozen RED artifacts, and snapshot fingerprint.
2. Accept B0 result-store/public-schema foundation, B1 grounding, then B2 consumers/rollout with
   mode `legacy`; validate every retained public compatibility field before collecting `shadow` diffs.
3. Accept C0 Q004/Q017 plus Type1, then C1 Type2 predicate/pagination/synthesis without changing
   Type4 or Type3.
4. Accept D0 subject/lexical substrate, then D1 hybrid Type4 quality/degradation under the frozen
   topic set and latency SLO.
5. Accept Slice E verified/secondary two-hop provenance with no inferred unresolved edges.
6. Accept Slice F ledger/manifest migrations and dry-run reconciliation before bounded execution;
   promote only after two-level paper/chunk/version parity and rollback evidence.
7. Switch chat mode to `canonical` only after all applicable slices and frontend consumers are
   Accepted. Keep `legacy` available through an observation window. Delete it only in a later
   approved change.

Rollback is slice-local. Chat rolls back by mode. Retrieval planners retain legacy selection behind
their rollout flag until accepted. Index work rolls back to the recorded collection alias/version;
the additive ledger remains audit evidence and does not rewrite canonical paper data.

## Open Questions

No blocking product question remains from the grilling session. Behavior parameters and all oracle,
verifier, judge, sampling, provider-version, index-target, and observation-window choices must be
frozen and reviewed before the owning checkpoint moves to Ready or begins RED execution. Candidate
evidence records the observed configuration; it cannot introduce or retroactively select it after
outputs are known.
