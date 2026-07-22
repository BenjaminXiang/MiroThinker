# S8C Aggregate KnowledgeRead Runtime Closure Dependency Audit — 2026-07-20

## Outcome

S8C can close OpenSpec Tasks 8.3, 8.5, and 8.7 with one small release-bound integration slice. The
public `create_ephemeral_knowledge_read` factory already owns the required seven-lane concurrency,
fusion, constraint, rerank, Web-handle, sufficiency, enumeration, and supplemental mechanics. The
real release-bound composition factory already owns all physical local adapters, but it does not yet
expose the existing identity-fuser, reranker, sufficiency, supplemental, or handle-resolution ports.

The smallest honest production delta is therefore to thread the already-existing optional ports
through `create_isolated_release_knowledge_read`, then prove the complete composition through one
release-bound vertical integration owner. S8C must not add another provider framework, retrieval
service, policy registry, or copy of the Accepted mechanics.

S8C is **Specified**, not Ready. It SHALL NOT become Ready and no S8C code/test implementation may
begin until S8R5 has both an Accepted Slice Contract and an Accepted verification receipt. One lean
review with zero open Critical/Important findings is then sufficient for Ready. Minor and YAGNI
findings are recorded and non-blocking.

## Accepted dependency inventory

| Dependency | Accepted capability reused by S8C |
| --- | --- |
| S8RG | One public `KnowledgeRead.execute`, bounded concurrent seven-lane execution, full traces, identity-aware fusion, hard constraints, late rerank degradation, Web snapshots/handles, read-only resolution, sufficiency, enumeration, and supplemental mechanics |
| S8S / Task 8.6 | RED and GREEN coverage for material-part sufficiency, all three enumeration modes, targeted retry, four-axis budgets, and partial continuation |
| S8E1 | Release-binding validation and caller-hidden physical lane composition |
| S8L1/L2/L3 | Release-scoped exact, structured/displayed-set, and lexical adapters |
| S8V1/V2 | Audited release-scoped vector adapter and typed Professor vector-view selection |
| S8IR1 | Release-scoped internal Person/Technology auxiliary adapter with public-origin traceability |
| S8R1 | Release-scoped Technology relationship evidence with state distinctions and no fifth public domain |
| S8R2/R3 | Accepted Company-to-Patent and Professor-to-Paper public relationship directions |
| S8R4 | Paper-to-Professor direction; currently a sequencing predecessor and must be Accepted before S8R5 |
| S8R5 | Patent-to-Company direction; final mandatory Ready gate for S8C |

S8R4 and S8R5 are now Accepted. Their Accepted contracts and verification receipts, rather than
their earlier Specified/Ready/In-Progress plans, are the dependency authority.

## Current code audit

### Complete public mechanics

`apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read.py` already provides:

- the exact seven supported lanes: `exact`, `structured`, `lexical`, `vector`, `relationship`,
  `internal_reference`, and `web`;
- bounded internal concurrency through one `ThreadPoolExecutor` execution stage;
- validated lane outputs and query-view/lane/attempt/release/provider traceability;
- `identity_fuser`, `reranker`, deterministic constraint enforcement, and ambiguity handoff;
- content-addressed bounded Web snapshots, typed Web handles, replay/tamper/expiry receipts, and
  read-only resolution against an accepted-release identity lookup;
- `sufficiency_decider`, all enumeration-accounting shapes, `supplemental_search`, four-axis budget
  receipts, limitations, and typed continuation reasons.

The public factory signature already exposes all of those optional ports:

```text
create_ephemeral_knowledge_read(
  identity_fuser=...,
  reranker=...,
  sufficiency_decider=...,
  supplemental_search=...,
  web_handle_resolver=...,
  accepted_identity_lookup=...,
  web_handle_ttl=...,
  ...
)
```

Its Accepted S8RG/S8S/S8RF owners already cover the detailed hostile and degradation matrices. S8C
shall reuse those tests as aggregate evidence rather than duplicate every synthetic case.

The S8C integration attempt found one narrow release-composition mismatch not visible in the
ephemeral owners: `RetrievalPlan` accepts unbound `interaction_mode="handle_replay"`, but the same
shape becomes planner-owned when an isolated release binding is attached and is rejected by the
final unsupported-interaction branch. Consequently the public release-bound service cannot execute
the already-Accepted replay/resolution mechanics. Capturing and invoking its internal delegate would
only hide this public-path defect and is not acceptable evidence.

### Narrow release-bound composition gap

`apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read_isolated.py` already composes:

- exact, structured, and lexical adapters unconditionally;
- vector when an explicit release-compatible embedding adapter is present;
- internal-reference and relationship adapters when the accepted release bundle carries their
  authority;
- the explicit current-Web port, snapshot policy, release binding, and physical postvalidation.

However, `create_isolated_release_knowledge_read` currently delegates only the physical lane map,
Web port, clock, and snapshot policy to `create_ephemeral_knowledge_read`. It has no public keyword
parameters for the already-existing identity-fuser, reranker, sufficiency, supplemental, handle
resolver, accepted-identity lookup, or handle TTL. A real release-bound caller therefore cannot
exercise the complete Accepted runtime through the composition root without bypassing it.

The re-planned S8C delta therefore includes one bounded validator branch in `knowledge_read.py`:
planner-owned/release-bound `handle_replay` is admitted only with no lanes, disabled Web execution,
no freshness/assessment/material-part execution, a non-empty session ID, and every retained/replayed
handle bound to that exact session. It adds no field or serialized-shape change and delegates to the
already-Accepted replay implementation after the release wrapper validates the exact release
binding. No other shared-contract, schema, storage, migration, lane, provider, or physical-adapter
change is justified.

## Relationship closure boundary

The aggregate public relationship claim is limited to the four catalog-supported directions:

1. Company to Patent;
2. Patent to Company applicant;
3. Professor to Paper attribution;
4. Paper to Professor attribution.

S8C does not infer Professor-to-Company, Professor-to-Patent, Company-to-Paper, or any other absent
direction. A direction whose accepted release has no supporting relationship returns an explicit
authoritative zero, limitation, or `insufficient_evidence` gap as applicable; it never fabricates an
edge from names, URLs, vector similarity, applicant strings, author strings, or Web prose. Internal
Technology relationship evidence remains auxiliary and retains the Accepted state distinctions; it
does not expand the four public-direction closure claim.

## OpenSpec task mapping

- **Task 8.3:** the vertical owner executes all seven validated lanes through the real release-bound
  composition, while the Accepted L/V/IR/R owners prove each physical adapter and four public
  relationship directions.
- **Task 8.5:** the same composition invokes the existing identity-fuser/reranker and Web-handle
  resolver ports; Accepted S8RG/S8RF owners provide complete fusion, constraint, ambiguity,
  snapshot, tamper, expiry, lineage, and degradation coverage.
- **Task 8.7:** the same composition invokes the existing sufficiency/supplemental ports; Accepted
  S8S/S8RG owners provide all material-part, enumeration-mode, budget-axis, and partial-continuation
  coverage.

Task 8.1 calibrated oracle work and Task 8.8 aggregate claim-level/provider/latency/cost acceptance
are explicitly outside S8C. S2C blocks those two tasks only; it does not block this deterministic
release-bound runtime closure.

## Options considered

1. **Extend the existing release-bound factory and add one vertical owner — selected.** It preserves
   one composition root and adds only optional pass-through parameters plus acceptance evidence.
2. Assemble physical adapters directly around `create_ephemeral_knowledge_read` in a test. This
   would prove mechanics but bypass the release-bound public owner that consumers need.
3. Add a new production provider/runtime framework. This duplicates Accepted abstractions and is
   rejected as YAGNI.

## Ready and acceptance decision

Ready requires all of the following:

- S8R5 Slice Contract and receipt both say Accepted;
- this audit, Slice Contract, and plan have one lean review with zero open Critical/Important;
- strict OpenSpec and document/scope checks pass;
- reviewed Specified hashes are frozen into the Ready transition.

Accepted requires the focused release-bound RED/GREEN, the complete Accepted owner matrix, full
no-external regression, static/scope/write-safety checks, and zero open Critical/Important findings.
Only then may Tasks 8.3, 8.5, and 8.7 be checked together, moving the formal ledger exactly from
`56/80` to `59/80`. Tasks 8.1 and 8.8 remain unchecked.

## Durable sources

- `openspec/changes/rebuild-canonical-v2-knowledge-platform/tasks.md`;
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/specs/evidence-first-query-orchestration/spec.md`;
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/convergence-plan-remaining-24-2026-07-20.md`;
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/slices/s8rg-atomic-knowledge-read-green.md`;
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/slices/s8s-sufficiency-retry-red.md`;
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/slices/s8e1-release-bound-knowledge-read-composition.md`;
- the Accepted S8L1-L3, S8V1-V2, S8IR1, and eventual S8R1-R5 contracts/receipts;
- `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read.py`;
- `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read_isolated.py`.

This audit changed no production code, test, task, acceptance artifact, existing slice, external
store, source, pointer, Commit, Push, PR, Archive, promotion, or Cutover.
