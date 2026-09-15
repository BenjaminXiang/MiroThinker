# Verification: data-cleaning-batch1 (D0-a)

Slice: `chore/data-cleaning-batch1` (worktree `.worktrees/data-cleaning-batch1`,
base `1ee824a7`).  Deliverable commit `39249412`.

## Honesty

* The verification contract was written from the assessment baselines before the
  implementation, but the *file* was materialized in the same session as the code
  (single-session slice, ~2h budget) - the code was not written before the
  assertions were fixed, but the usual "contract file first, then code" git
  ordering is not visible in this branch.
* The cleaning became effective for **run16 only**.  Nothing in
  `/var/tmp/mirothinker-data-v2/` was written; the run15 pack was opened
  `mode=ro&immutable=1` after being copied to `/tmp/dq-batch1-scratch/`.
* One of my own rules was falsified by the replay and rewritten (length-based
  "paragraph dump" -> falsified, see log §发现 4).

## Layer 1 - tests written in this slice

`apps/miroflow-agent/tests/canonical_v2/test_publication_cleaning.py`,
**53 tests, all pass** (`uv run pytest tests/canonical_v2/test_publication_cleaning.py`):

| cluster | count | what it locks | fixture source |
|---|---|---|---|
| placeholder families (exact/prefix/English-build-fallback/no-information) | 15 | absent-not-rewritten semantics; the build gate's own fallback literals classify as placeholders | run15 verbatim + the build's constants |
| glue damage vs legitimate prose | 10 | identifier/version damage is withheld; the patent-abstract prose case survives; prefix family wins over glue | run15 verbatim |
| geography derivation | 7 | province-only -> `省-市`; province-prefixed address does not swallow the province; autonomous-region address; nothing derived when the value is already city-level/absent/unparseable | run15 verbatim |
| research-direction rules | 11 | five junk rules fire; four clean shapes (incl. bilingual long direction) survive | run15 verbatim |
| whole-payload cleaning | 4 | company payload (withhold + derive + drop placeholder reference entries) and professor payload (placeholder fields absent, junk directions dropped with `reference_id` intact) | constructed from run15 values |
| model contract | 2 | cleaned payloads validate against the re-typed `CompanyProjection` / `ProfessorProjection` (installed catalog identity) | constructed |
| audit + gate | 4 | counts, fail-closed on placeholder/junk/thin-geography, clean payload passes, gate is wired into `IndexProjectionBuilder.build` | constructed |

## Layer 2 - pre-existing suites (regression)

Related suites first (fast, targeted):

```
uv run pytest tests/canonical_v2/test_domain_projection_contract.py \
  tests/canonical_v2/test_index_projection_embedded_content.py \
  tests/canonical_v2/test_knowledge_build_professor_backfill.py \
  tests/canonical_v2/test_knowledge_build_p4_full_column.py \
  tests/canonical_v2/test_domain_projection_postgres.py
-> 5 failed, 55 passed, 11 skipped   (first run)
-> 5 pinned-expectation tests updated for the new behaviour, re-run: all pass
```

The five updates are all "the old behaviour was the defect" pins, each changed
only in its assertion, never in its intent:

| test | before | after |
|---|---|---|
| `test_index_projection_embedded_content.py::test_public_embedded_content_omits_missing_field_placeholder` | built a projection carrying the fallback text and asserted the index layer hid it | builds a projection with the field absent and asserts the key is absent (the index-layer guard it used to exercise is now unreachable and deleted) |
| `test_index_projection_embedded_content.py::test_missing_field_placeholder_constant_matches_build_side` | asserted `index_projection` keeps a pinned copy of the constant | asserts the serving copy still matches the build, and that `publication_cleaning.placeholder_family` recognises the build's fallback |
| `test_knowledge_build_professor_backfill.py` (3 tests) | `projection.department.name == _PROFESSOR_MISSING_FIELD_FALLBACK` | `projection.department is None` - a demoted field is absent, not placeholder text |

Full `tests/canonical_v2` sweep: see §Suite sweep below.

## Layer 3 - replay evidence (RAG/data-level claim)

`count_cleaning_batch1.py` over a read-only copy of the run15 `lookup.sqlite3`
(668,884,992 bytes, `/tmp/dq-batch1-scratch/lookup.sqlite3`):

| metric | before | after |
|---|---|---|
| placeholder-family values published (full nested walk) | 15,976 | 0 |
| whole-value `未找到` (baseline 1,817) | 1,817 | 0 |
| `未找到` prefix (baseline 2) | 2 | 0 |
| glue runs (baseline 189) | 189 | 177 withheld + 3 nulled + 9 kept-as-prose |
| glue values still carrying the token | 189 | 9 (all legitimate prose, enumerated) |
| company geography: province-only / city-level | 4,887 / 601 | 2 / 5,486 |
| research-direction entries / junk | 10,238 / 796 | 9,442 / 0 |
| quarantine records | - | 973 (177 glue + 796 directions) |

Artifacts committed: `.agents/runs/data-cleaning-batch1/out/counts.json`,
`out/quarantine.jsonl` (332 KB), `out/kept-legit-prose.jsonl`.

## Suite sweep

Deterministically pre-existing failures (verified by re-running with the three
changed source files stashed on the base commit):

| test | with this slice | base commit |
|---|---|---|
| `test_canonical_scope_founder_red.py::test_founder_prefix_uses_handles_bound_to_the_same_claim` | FAIL (`answer off-anchor`) | FAIL (identical) |
| `test_knowledge_build_isolated.py` (13 tests: real-boundary/postgres-style boundary checks, `test_four_domain_mapper_normalizes_restored_source_shapes`, `test_complete_build_uses_verified_copies_...`) | 13 FAILED | 13 FAILED, **identical set** (`diff` of the two failure lists is empty) |

Green with this slice:

| command | result |
|---|---|
| `pytest tests/canonical_v2/test_publication_cleaning.py` | 53 passed |
| `pytest tests/canonical_v2/test_domain_projection_contract.py tests/canonical_v2/test_index_projection_embedded_content.py tests/canonical_v2/test_knowledge_build_professor_backfill.py tests/canonical_v2/test_domain_projection_contract.py` | 99 passed |
| `pytest tests/canonical_v2/test_domain_projection_postgres.py tests/canonical_v2/test_knowledge_build_p4_full_column.py` | passed (11 skipped: need `CANONICAL_V2_TEST_*` settings) |
| `pytest tests/canonical_v2/test_serving_pack_loader.py tests/canonical_v2/test_knowledge_build_interface.py` | 22 passed |
| `ruff check` / `ruff format` on the touched files | clean |

**Incomplete**: the full `tests/canonical_v2` sweep (`-n=4`, no `-x`) reached
~92% before the 45-minute cap; the two runs of
`test_knowledge_build_isolated.py` each hit the 900 s cap at ~89%.  Failures
beyond the verified pre-existing set are therefore **not enumerated** for the
tail of the suite (Milvus/serving tests dominate that tail and are the slow,
environment-dependent part).  Blocked by: per-test runtime, no pytest-timeout
plugin in the venv.  Confidence impact: the modules this slice touches are
covered by the targeted runs above; the unexercised tail is downstream of the
index projection, where the only new code is the publication gate (fail-closed,
covered by unit tests).  Next best command:
`uv run pytest tests/canonical_v2 -q -n=4 --no-cov --deselect <the two verified pre-existing failures>`
with a longer wall-clock budget.

Also checked: the 903 run15 documents that carry `_supplementary` values (merged
at the index layer, after this slice's cleaning point) contain **no** placeholder
or glue-damaged values, so the new gate cannot block a run16 rebuild on that
path.

## Not verified

* run16 rebuild / real gate execution (needs the packing pipeline; out of slice).
* Retrieval-level effects (recall, TTFT) - this slice changes stored content
  only; the R9 baseline (replay 7/7 + probes + TTFT) is unaffected because the
  serving process and the run15 pack are untouched.
* Correctness of the 4,885 derived city values beyond rule-level spot checks
  (30-value human sample not taken; the rule is address-local and conservative).

---

# Verification: data-cleaning-batch2 (D0-b)

Slice: same branch/worktree, commits `791f3787..HEAD`.  Contract:
`verification-contract-batch2.md`.

## Honesty

* Two items are delivered with an explicit scope note rather than fully:
  **dead-field retirement** (decision table only: retiring a declaration is a
  content-hash-pinned catalog revision - a release-identity change - so it is
  escalated, not unilaterally done) and **the end-to-end write of the quality
  report** (writer + wiring are unit-tested; the full isolated build fixture is
  a pre-existing failure on this branch).
* One mechanism was built and then reverted after verification falsified it:
  excluding retired fields at the publication surface (`model_dump_json(
  exclude=...)`) breaks `knowledge_read_isolated._read_public_projection`, which
  requires a published document to equal `projection.model_dump_json()`.
  Reverted; the constraint is documented in design.md §5.

## Layer 1 - tests written in this slice

`tests/canonical_v2/test_publication_cleaning_batch2.py`, **27 tests, all pass**:

| cluster | count | what it locks |
|---|---|---|
| venue key / canonicalisation | 4 | arXiv, PLoS, year suffix, Proceedings family, distinct venues stay apart |
| venue map | 4 | most-frequent winner, determinism, order independence, singleton untouched, reference rewrite |
| geography repair | 6 | separator, prefecture suffix, district tail NOT suffixed, province from address, unparsed kept+counted, final form untouched |
| applicants | 5 | bound/unbound/nameless/invalid counting; unbound-but-named passes the gate; nameless and foreign-binding fail it |
| dead declarations | 2 | per-domain measurement, partially-declared fields excluded from the metric, measurement never fails the build |
| quality report | 3 | quarantine re-derived from selections (rule + reference id), payload shape, writer wiring |
| edge dedup | 2 | smallest-id winner keeps the retained link; uniqueness assertion exists and accepts an empty set |

Updated batch-1 expectations (2): the geography case `广东省-珠海` moved from
"leave alone" to "city suffix" (it is now repaired), and the gate-wiring test
follows the renamed audit variable.  No test was weakened: the
`lookup_content == model_dump_json()` guarantee that blocked the exclusion is
left intact.

## Layer 2 - pre-existing suites

| command | result |
|---|---|
| publication_cleaning (batch1) + batch2 + domain_projection_contract + index_projection_embedded_content + professor_backfill + p4_full_column + serving_pack_loader + knowledge_build_interface + domain_projection_postgres | **160 passed, 11 skipped** |
| `test_knowledge_build_isolated.py` link-assembly tests (`test_mapper_merges_professor_snapshots_...`, `test_public_authority_records_missing_paper_anchor_...`, `test_patent_applicant_links_*`) | 4 passed |
| full `test_knowledge_build_isolated.py` | not re-run to completion (900 s cap, same as batch 1); the same 13 pre-existing failures were re-confirmed in batch 1 by a stashed-tree baseline run, and this slice's change to that file is additive (a new helper + one call site) |

## Layer 3 - replay evidence

`count_cleaning_batch2.py --pack-dir <sealed pack> --out out2` (read-only;
`relationships.json` pass loads the 3.4 GB payload):

| metric | before | after |
|---|---|---|
| distinct venue labels | 5,204 | 5,031 (153 groups / 326 labels / 2,684 rows) |
| `arXiv` label rows | `arXiv (Cornell University)` 418 + `arXiv` 242 | `arXiv` 660 |
| professor→paper edges / distinct pairs | 10,773 / 10,742 | 10,742 / 10,742 |
| duplicate pairs | 31 | 0 |
| applicant rows | 12,565 (7,614 bound, 4,951 unbound, 0 nameless, 0 invalid) | unchanged by design; now gated and reported |
| dirty geography | 3 | 0 (`开曼群岛`, `广东省-珠海市`, `江苏省-苏州市`) |
| declared-never-filled fields | 49 (company 10, professor 14, patent 8, paper 17) | 49 measured + 49-row decision table (27 keep / 22 retire-pending) |

## Not verified

* The quality report inside a real isolated build (see Honesty).
* run16 rebuild; retrieval effects of venue merging.
