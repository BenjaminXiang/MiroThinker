# Design: patent-company-relationship-reprojection (C1)

Evidence base: run15 sealed pack (`/var/tmp/mirothinker-data-v2/serving-pack-run15-sealed/`,
release `candidate-v2-20260913-r1`, build `p4-build-20260913-v1`, built 2026-09-13)
plus its staged sources (`/var/tmp/mirothinker-data-v2/staging-v2/`, 13 landed
evidence members) and the build ledger
(`.worktrees/data-rebuild/.agents/runs/full-column-serving-pack-rebuild/build-run15.log`).
All reads were read-only; working copies live under `/tmp/c1-relationship-scratch/`.

---

## 1. T1-Q1/Q2 — who generates `patent_has_applicant`, and why only 123

### 1.1 Generator chain

`patent_has_applicant` edges are produced entirely inside the isolated build:

```text
knowledge_build_isolated._relationship_authority            :6766
  └── bound_company_ids_by_patent  (doc-layer bindings)      :6815-6833
  └── _typed_relationship_seeds(…)                           :6834  →  :6478
        └── 3 seeding lanes for patents                      :6671-6762
              1. resolved applicant bindings                 :6674-6701  (match_kind=resolved_binding)
              2. core_facts.company_ids                      :6702-6728
              3. applicant-name → released-company resolution :6729-6762
  └── seeds → RelationshipProjectionCandidate (typed assertions) :6966-7070
  └── create_ephemeral_relationship_projection().project()   :7124
  └── guard: len(current_relationships) == len(links)+len(typed_seeds)
        and all(outcome.admitted)                            :7127-7132
```

Input to the seed stage: `source_rows=rows` — **every landed evidence row**
(`_logical_graph` → `_relationship_authority` call, `:9413-9423`; rows come from
`_stage_and_land`, `:9261-9377`).

### 1.2 Why only 123 — the causal chain

1. The projection stage is innocent. run15's `relationship_projection_result`
   reports `patent_has_applicant`: `candidates = 123`, `admitted = 123`,
   `rejected = 0`, no reason codes at all. Whatever reached the projector was
   projected.
2. The seed stage produced only `123 + 1 = 124` typed seeds for the whole build
   (`typed_relationship_assertions = 124` = 123 applicant + 1 professor-company),
   and the completeness guard at `:7127` proves `typed_seeds` **was** 124
   (10,897 `current_relationships` = 10,773 professor→paper links + 124 seeds).
3. Of those 123 applicant edges, **122 carry
   `evidence_metadata.match_kind = "resolved_binding"`** (lane 1) and **1**
   carries `source_field = "core_facts.company_ids[0]"` (lane 2). So the
   applicant-binding lane did run — it just resolved almost nothing.
4. Lane 1 drops a binding at `:6677-6684`:

   ```python
   bound_object_id = source_object_by_canonical.get(bound_canonical_id)
   if bound_object_id is None:   # bound company is not an object the seeds can see
       continue
   ```

   `source_object_by_canonical` (`:6496-6502`) and the name indexes
   (`company_ids_by_name`, `professor_ids_by_name`, `applicant_link_index`,
   `:6503-6533`) are all built from **`rows_by_object`** (`:6485-6489`):

   ```python
   rows_by_object = {
       cast(str, row.payload["id"]): row
       for row in source_rows
       if isinstance(row.payload.get("id"), str)
   }
   ```

5. `rows_by_object` therefore only ever contains the rows whose **raw payload
   already is a released object**. In `_stage_and_land` only the released-objects
   source is unwrapped to released shape (`:9354-9361`); the 12 supplemental
   sources keep their native domain shape:
   - `p4-patent-full-v1.jsonl` keys the identity as **`patent_id`** (`_p4_patent_record`, `:4409-4417`);
   - `p4-company-full-v1.jsonl` as `company_name` (`_p4_company_record`, `:4317`);
   - `p4-applicant-binding-full-v1.jsonl` as `applicant_name`.
   None of them has `payload["id"]`, so **none of them enters `rows_by_object`**.
6. The released-object shape for those rows *does* exist — it is synthesized by
   `_merge_p4_created_rows` (`_P4_RECORD_BUILDERS`, `:4428-4433`; def `:4731`) and
   stored as `row_by_object[object_id] = synthesized` (`:4938`), exactly like the
   s12f company backfill (`:3816`) and the released rows themselves (`:5609`) —
   but `row_by_object` is handed to the *mapped authority*, never back to
   `_relationship_authority`.
7. Consequence, measured on run15 (see `.agents/runs/c1-relationship-reprojection/verification.md`):

   | population | count |
   |---|---|
   | released_objects rows (patents / companies) | 1,931 / 1,037 |
   | total admitted objects (patents / companies) | 11,504 / 7,086 |
   | in-document bound patents / companies | 7,042 / 960 |
   | in-document bound patents **that are released objects** | 1,681 |
   | in-document bound companies **that are released objects** | 113 |
   | (patent, company) pairs with **both** endpoints released objects | **122** |
   | relationship edges with `match_kind = resolved_binding` | **122** |

   The 122/122 equality is the proof: a binding only becomes a relationship edge
   when **both** endpoints happen to be released objects. The 123rd edge is the
   single `core_facts.company_ids` binding on a released patent.

So: **not** "the projector only accepts asserted relationships", and **not** a
`supporting assertion` requirement. It is a **seed-universe bug**: the seed stage
reads the raw landing rows instead of the mapped admitted-object universe, so
9,573 P4-collected patents and 6,049 P4-collected companies are structurally
invisible to relationship seeding even though their field assertions, canonical
identities and inclusion decisions exist.

### 1.3 Who consumes the edges

The edges are a first-class serving input; there is a reader list, not a dead
store:

| reader | reference |
|---|---|
| isolated path→relationship map (`company_to_patent` / `patent_to_company`) | `knowledge_read_isolated.py:150-170`, used at `:4960`, `:5409` |
| relationship-type gate in the isolated read path | `knowledge_read_isolated.py:3361-3366`, `:4811` |
| document-layer authority (independent of the edge store — unchanged) | `knowledge_read_isolated.py:3762` (`_direct_patent_applicant_scan`) |
| claim binding on answers | `knowledge_read_isolated.py:6147` |
| legacy (non-isolated) read path | `knowledge_read.py:1693`, `:1781`, `:2011`, `:2099`, `:3097-3098`, `:3678-3679` |
| answer layer / relation picker | `knowledge_answer.py:1701`, `:1718` |
| serving pack loader (re-derives the relationship request from `relationships.json`) | `serving_pack_loader.py:12`, `:399-413` |
| admin console relationship listing | `apps/admin-console/backend/services/canonical_v2_admin.py:85`, `:92` |

Because the document-layer scan is the serving-period authority, today's 123
edges are mostly shadowed at answer time — but the pack loader, path eligibility
and admin views read the relationship layer directly, and any future
"relationship traversal" work would inherit a 1.7%-complete graph.

### 1.4 Siblings (pattern-repair check)

| lane | run15 | same root cause? | action |
|---|---|---|---|
| `patent_has_applicant` lane 1/3 (`company_ids_by_name`, `applicant_link_index`) | 123 | **yes** — universe = released rows only | fixed by this change |
| `professor_company_role` (`:6503-6517`, `:6628-6670`) | **1** | **yes** — same two name indexes | fixed by this change (re-counted in run16) |
| `professor_attributed_to_paper` (link rows) | 10,773 | no — reads `links` directly, not the object universe | none |
| `paper_has_author`, `patent_has_inventor` | 0 | **no** — different cause: run15 ships `internal_reference_projection_result.person_projections = 0`, so there is no person graph; the person lanes (`:1490-1618`) never fire | reported only (see Open item O1) |
| `paper_references_paper`, `company_in_industry`, … | 0 | declared-only registry types, no producer | out of scope |

---

## 2. T2 — chosen repair path

**Both (a) and (b), in the order that makes each verifiable:**

**(a) Project every resolver-produced applicant binding as a
`patent_has_applicant` edge.** The fix is at the input boundary, not in the
seeding logic: `_typed_relationship_seeds` is given the mapped admitted-object
universe (`row_by_object`, id → released-shaped row) instead of the raw
`source_rows`. Raw supplemental rows are still passed for the
`professor_company_role` *source-purpose* lane (`:6585-6590`), which reads
per-record payloads (`professor_name` / `company_name` / `role`) rather than
objects.

Why this shape and not "name-resolve against released companies more
aggressively":
- The bindings are already resolved by the s12f audited pipeline with a
  uniqueness guard (7,614 applicant rows over 1,662 resolved binding records).
  Re-resolving names in the relationship stage would duplicate that pipeline and
  reintroduce the ambiguity the s12f audit removed.
- `row_by_object` is *the* admitted universe used by every other authority stage
  (inclusion, decisions, projections): reusing it makes the relationship layer
  consistent with the document layer by construction rather than by luck.
- No registry/model change is needed: the existing typed-seed →
  `TypedRelationshipAssertionInput` → decision path (`:6966-7070`) already
  produces one supporting retained assertion per edge, satisfying the
  relationship model's evidence requirements without new assertion plumbing.

**(b) Make the relationship layer's relationship to the document layer explicit
and enforced (D0).** The design accepts "the relationship layer only carries
resolved, evidence-backed relationships" as a *design* invariant — but then it
must be **checkable**:
- `PATENT_COMPANY_BINDING_LEDGER` (one JSON line per build, next to
  `APPLICANT_BINDING_LEDGER`) reports: `document_binding_rows`,
  `document_binding_pairs`, `document_bound_patents`, `document_bound_companies`,
  `relationship_candidates` (by seeding lane), `seed_pairs`, `unindexed_pairs`,
  `unexplained_missing`. This is the per-build quality-report entry (R21 feed).
- `INVARIANT-1` fails the build (`IsolatedKnowledgeBuildError`) when
  `document_pairs − seed_pairs − unindexed_pairs ≠ ∅`, naming counts and a
  sample of the missing pairs. "Unexplainable" means: a document binding whose
  patent and company are both admitted objects, yet no seed was produced. That
  is precisely the C1 defect class; the guard makes it impossible to ship again.

Why not "make the two stores equal": the document layer also carries bindings
whose company later merged or left the release, and `core_facts.company_ids`
edges that never were applicant bindings. Subset-plus-classification is the
honest contract; equality would be a brittle over-claim.

---

## 3. Verification plan

- Unit: both-endpoints-supplemental seeding (R1), reconciliation raise/pass (R2),
  sibling lane universe (R3); fixtures taken verbatim from run15
  (`PAT-002AF039E85C` ← 中建钢构股份有限公司) plus the existing synthetic
  applicant-binding fixture.
- Replay: `.agents/runs/c1-relationship-reprojection/replay_patent_applicant_bindings.py`
  reads the run15 staged sources + sealed pack (read-only), reconstructs the
  pre-fix universe (released rows only) and the post-fix universe
  (`row_by_object`), runs the real seed function for both and prints the count
  comparison and the classified difference list.
- Regression: `test_knowledge_build_isolated.py`,
  `test_applicant_binding_relationship_seeds.py`,
  `test_relationship_projection_contract.py`, `test_serving_pack_loader.py`,
  `test_patent_applicant_linking.py`.

## 4. Open items

- **O1** `person_projections = 0` in run15 ⇒ `patent_has_inventor` /
  `paper_has_author` stay empty even after this change. Different defect class
  (internal reference graph), separate change.
- **O2** The applicant-binding merge's own ledger counter is misleading
  (`patents_bound = 7,614` counts per binding record, not distinct patents; the
  real figure is 7,042). Reported, not changed here (out of slice).
- **O3** run16 must re-measure the three numbers in §1.2 step 7; the ledger line
  is the acceptance artifact.
