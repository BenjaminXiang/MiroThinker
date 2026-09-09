# Aggregate S6 Review — 2026-07-13

## Disposition

Accepted at `2026-07-13T14:48:01Z` under the user's objective-verification self-approval
authorization. Tasks 6.1-6.8 form one reviewable S6 foundation with zero open Critical/Important
findings. This is a repository implementation checkpoint, not an S7 release, product-data
candidate, database/index promotion, or production-like cutover.

## Reviewed boundary

- Predecessor: Task 5.7/S5G and Tasks 6.1-6.7 through
  `9b300222338e24e8faac661cf7154ef7f7fb19b8`.
- Included seams: frozen PRD catalog, domain inclusion, four typed domain projections, C2_0009
  persistence, typed relationship projection, C2_0010 persistence, and six-path eligibility.
- Bounded candidate meaning: deterministic in-memory fixtures plus newly created, explicitly marked
  disposable PostgreSQL targets. The durable C2_0004 landing checkpoint remained unchanged.
- Deferred boundary: S7 owns `KnowledgeBuild`, immutable candidate manifests, published
  projections, Milvus indexes, parity, promotion, and rollback. S8/S9 own read/answer consumers.

## Coverage accounting

| Surface | Exact bounded coverage | Evidence |
|---|---:|---|
| Domain roots | 4 (`company`, `paper`, `patent`, `professor`) | Explicit root models, inclusion scenarios, projection and path matrices |
| Shared/domain fields | 9 shared + 101 domain fields | Content-addressed catalog validation, packaged-model parity, C2_0009 materialization |
| Typed subobjects | 28 (8/8/5/7 by domain) | Catalog/model parity, sibling lineage/cardinality/temporal tests, durable rows |
| Relationship types | 34 | Every catalog type is exercised through its owning family matrix |
| Relationship families | 7 | Identity/lifecycle, organization/role, scholarly, IP, Company business, taxonomy, evidence lineage |
| Cross-domain directions | 8 | Forward/inverse Professor↔Paper/Company/Patent and Company↔Patent orientation tests |
| Published paths | 6 | One evidence/policy/release-bound decision per exact, structured, traversal, semantic, recommendation, ranking path |
| Source-accounting scenarios | 42 | 34 type rows + 8 traversal rows; supported/absent/insufficient remains source potential only |

The matrix also exercises duplicate inputs, wrong domain/field/owner/release, dangling assertion,
typed-subobject and endpoint references, temporal precision/currentness, evidence and decision
continuity, invalid roles/directions/layers, release/request/result hash tampering, replay,
concurrency, append-only behavior, rollback, downgrade refusal, and candidate-only writes.

## Review finding and repair

One Important systemic test defect was found by the first full real-PostgreSQL run:

- C2_0010 correctly requires new shared and typed relationship decision rows to be created while a
  release is `candidate`, but four older C2 foundation tests inserted relationship decisions after
  creating their releases directly as `accepted`.
- Three tests failed at the candidate-release guard before reaching their intended endpoint or
  supersession constraint. The self-supersession test passed for that same wrong reason, making it a
  false positive.
- All four tests now model the actual lifecycle: write the first decision in a candidate, promote
  that release to accepted when cross-release ancestry is needed, then write the successor decision
  in the next candidate. No migration or production behavior was weakened.
- Focused RED was `3 failed` plus one identified false positive. Focused GREEN is `4 passed`; the
  complete real matrix is `348 passed, 4 expected xfailed` across the general and fixed-name S4C
  disposable targets.

No other Critical/Important code, migration, contract, or evidence finding remains. The fixed S4C
database-name assertion was a verification orchestration contract, not a product defect; its ten
tests passed on a separately created exact-name disposable and that database was removed.

## Side-branch and worktree accounting

| Ref/worktree | Accounting disposition |
|---|---|
| `canonical-v2-s1-safety` / `a58184c` | Clean; no patch absent from the integration line. |
| `codex/canonical-v2-s6c-db-red` / `8f1dbd8` | Intentionally superseded. Its domain migration used `C2_0008`, now owned by accepted S5G. The integration line rebased the behavior as `C2_0009`; all 7 side tests are represented and the integration matrix has 13 tests, including concurrency, rejected-root, multi-root, ownership, and downgrade siblings. Blind integration would create a revision collision. |
| `codex/canonical-v2-s6d-red` / `d380405` | All 9 named RED groups are present on the integration line; the accepted copy additionally binds exact S6c projection roots/subobjects. The stale patch topology is abandoned. |
| `codex/canonical-v2-s6f-red` / `9605dcc` | All 5 named RED groups are present; the accepted line adds 4 request/content/topology/inclusion-review integrity tests. The stale patch topology is abandoned. |
| `codex/canonical-v2-task61-prep` / `3d9db81` | Branch commit is already an ancestor. Four untracked `preparation_only` catalog-candidate files are intentionally abandoned in place: they say Tasks 5.5/5.6 are `not_accepted`, defer time/state policy, and are not a frozen catalog. Accepted Task 6.1 is the post-dependency 9/101/28/34 catalog. The worktree was not cleaned or modified. |
| dirty root `/home/longxiang/MiroThinker` | Untouched on `feat/professor-retrievability`; preflight status hash `466173c3...8ff5`, tracked-diff hash `c42579bf...31ce`, cached diff empty. |

`git cherry` reports patch differences for the three RED side branches because the accepted tests
were deliberately rebound and strengthened, not blindly cherry-picked. Function-level accounting
shows S6d 9/9 present, S6f 5/5 present plus four siblings, and the S6c side behavior represented at
the non-conflicting C2_0009 revision with a larger matrix.

## Verification evidence

- Focused pure S6 aggregate: `54 passed`.
- Complete no-external-database Canonical V2: `211 passed, 137 skipped, 4 xfailed`.
- Focused C2_0009/C2_0010 persistence: `26 passed`.
- Initial full real database discovery run: `336 passed, 3 failed, 9 errors, 4 xfailed`; it exposed
  the lifecycle-test defect and the fixed-name S4C orchestration requirement.
- Corrected general real database matrix: `338 passed, 4 xfailed`.
- Exact-name S4C real database matrix: `10 passed`.
- Owned-database cleanup: no `canonical_v2_s6h*` or fixed-name S4C database remains; the explicit
  S6c base has zero schemas/tables and was never a business-data target.
- Original invariants: `pgtest` remains paused; original Milvus SHA-256 remains
  `43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc`.
- Deterministic/static gates: catalog `--check`, 24 catalog/shared tests, Ruff format/check, Pyright
  zero findings, strict OpenSpec at 36/75, and formal S2B `accepted/50` all pass. The frozen FPI
  salvage hash remains `cef8eb6ba18ebd23fde3e47023222ecb82bc8f27582040efe5a212a7f9fdfbb7`;
  the recovery lab remains network-none/no-port.

The remaining exact-commit, secret/diff, clean-worktree, and Git topology checks are recorded in the
mainline-promotion gate immediately before the ref move.

## Pattern-fix report

- Reported case fixed: three relationship database-integrity failures after C2_0010 and one
  sibling false-positive.
- Defect class: historical integrity fixtures bypassed the now-enforced candidate→accepted release
  lifecycle, so an earlier guard masked the constraint each test intended to exercise.
- Sibling patterns searched: every `relationship_decision` test, shared decision graph helper,
  C2_0010 release-scoped trigger, relationship persistence test, and all direct release-state
  transitions.
- Sibling issues found/fixed: exactly four direct tests; the other relationship integrity families
  already use `_insert_decision_test_graph(... state="candidate")`.
- Not fixed and why: the S4C fixed database name remains by design and is orchestrated separately;
  the preparation-only Task 6.1 artifacts remain untouched in their owner worktree.
- New invariant/helper/contract/test: all relationship decisions are inserted only while their
  release is candidate; cross-release supersession accepts the predecessor before creating the next
  candidate.
- Remaining systemic risk: S7 must keep this lifecycle when it implements actual candidate
  construction and promotion; it may not reopen accepted releases for relationship writes.

## Acceptance rationale

S6 is a coherent internal build foundation: typed objects and relations are evidence-bound and
persistable, path decisions are independent and partial-data tolerant, and cross-domain sibling
integrity is enforced in Python and PostgreSQL. The review intentionally makes no claim that an S7
release manifest, published projection, Milvus index, query path, or answer path exists. Aggregate
S6 is therefore safe as the repository development mainline and as the Accepted predecessor for a
future S7 Ready slice, while product/data/index cutover remains forbidden.
