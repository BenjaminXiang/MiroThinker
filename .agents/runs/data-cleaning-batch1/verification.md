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

`tests/canonical_v2/test_publication_cleaning_batch2.py`, **26 tests, all pass**
(26 test functions; the cluster table below sums to 26 - see §Review corrections):

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

## Review corrections (2026-09-15, post-handoff)

Two findings from the owner's review of the D0-b handoff, both corrected here.

### RC-1 - `out2/counts-batch2.json` reported zeros for edges

* **Symptom**: the committed JSON had `edges_before/pairs_before/duplicate_pairs_before/
  edges_after/pairs_after = 0` while the handoff cited 10,773 -> 10,742 and 31
  duplicate pairs.
* **Cause**: not a wrong aggregation key and not "never ran" - the *last* run of
  the counter used `--skip-relationships` (it was re-run only to refresh the
  dead-declaration metric) and **overwrote** the JSON the full run had produced.
  The full run's numbers were real (10,773 / 10,742 / 31) and appear in the handoff
  verbatim, but they were no longer in the artifact.
* **Aggravating factor (fixed)**: the script wrote the same zero-valued edge keys
  when skipping, so a skipped block was indistinguishable from "no duplicates
  found".  A skipped run now writes `{"skipped": true}` and no counts at all.
* **Fix + evidence**: full run re-executed against the sealed pack (read-only):
  `{"skipped": false, "edges_before": 10773, "pairs_before": 10742,
  "duplicate_pairs_before": 31, "edges_after": 10742, "pairs_after": 10742}`,
  plus consistency assertions in the verification command chain
  (`edges_before == 10773`, `duplicate_pairs_before == 31`, venue 5,204 -> 5,031,
  applicants `{12565, 7614, 4951, 0, 0}`) - all pass.

### RC-2 - test count was overstated (27 vs 26)

* **Symptom**: the handoff and three documents said "27 new batch-2 tests".
* **Cause**: a header typo.  `test_publication_cleaning_batch2.py` contains **26**
  test functions (verified by `grep -c '^def test_'` and by pytest:
  `78 passed` over both cleaning files = 52 batch-1 cases + 26 batch-2 cases);
  the cluster table in this document already summed to 26.
* **Fix**: corrected to 26 in `verification.md`, `acceptance.md`, `tasks.md`,
  the human log and the change-ledger row.  No test was removed.

Neither finding changes a rule, a gate or a measured data number; both were
evidence-reporting defects and are corrected in the artifacts.

## run16 attempt 3 — the gate catches the supplementary channel (2026-09-16)

run16 launched 2026-09-15 22:53 and aborted 2026-09-16 00:32 with
`IndexProjectionIntegrityError: published pack failed the data-cleaning gate:
placeholder values published: 5` (chain: `PublicationQualityError` raised by
`index_projection._lookup_documents`' gate at `index_projection.py:503`).

Root cause (code-grounded): `knowledge_build_isolated._supplementary_field_values`
collects **non-selected assertion values** and hands them to
`_lookup_documents` / `_vector_points` as `supplementary_by_canonical`.  That
channel is fed by raw assertion values and never passes the projection cleaning
seam (`domain_projection.project_identity`), so the build's own fallback
sentences — `_P4_COMPANY_PROFILE_FALLBACK = "No dedicated summary was supplied
by the full-column workbook source."`, `_P4_COMPANY_ROUTE_FALLBACK = "Not
supplied by the full-column workbook source."` — and withheld glue-damaged
values reached the pack.  The classifier already covers those literals
(`PLACEHOLDER_PREFIX_VALUES`); the values simply never met it.

Evidence that the projections were clean: scanning every string in the run16
database's `company/professor/paper/patent` projection tables with
`placeholder_family` returns **0 hits** (the seam worked); the offenders can only
enter through the supplementary channel.

Fix (data-line commit `3a9f9149`):

- `_supplementary_field_values` applies `clean_text` (drop placeholder-family,
  no-information and glue-withheld values) plus the research-direction rule, so
  the channel obeys the same single rule set as the seam;
- `assert_publication_quality` now names up to four offenders per kind
  (`placeholder_examples`, `glue_examples`, `research_direction_examples` —
  collected by `audit_projection_payload(..., examples=)`), so the next failure
  is diagnosable without re-running a multi-hour build;
- tests: `tests/canonical_v2/test_supplementary_publication_filter.py` (new; RED
  before the fix: the placeholder sentence and the glue-withheld value were both
  published; GREEN after) and `test_gate_failure_names_its_offenders`;
  132 passed across the D0-a/D1-a suites.

## run16 attempt 4 — venue reference fallback (2026-09-16)

Attempt 4 (launched 11:01, with the supplementary-channel fix) aborted before
14:40 at the same gate, but now **naming its offenders** (the diagnostics added
in `3a9f9149`):

```
placeholder values published: 5
  (e.g. paper.venue.name: 未提供期刊出处 ×4, +1 more)
```

Root cause: `knowledge_build_isolated._p4_paper_record` lands
`_P4_PAPER_VENUE_FALLBACK = "未提供期刊出处"` as the paper's venue reference when
the P4 salvage record has no venue.  `venue` was the one reference-shaped field
missing from `CLEANED_REFERENCE_FIELDS["paper"]` — `canonicalize_venue_reference`
only normalises labels through the venue map and never runs the placeholder
classifier, so the fallback reached the documents.  (Attempt 3's five offenders
were the same five; the fix in `3a9f9149` removed a real but different leak and
made this round diagnosable.)

Fix (`fee2fc85`): `venue` joins the paper reference-field cleaning list.

- RED/GREEN: `test_paper_venue_placeholder_reference_is_not_published` fails
  before the fix (the placeholder reference survives `clean_projected_values`)
  and passes after; 134 passed across the D0-a/D1-a suites.
- New invariant: `test_every_build_fallback_literal_is_recognized_by_the_cleaner`
  pins that every `*_FALLBACK` literal in the build module is placeholder-family
  text, so a future fallback cannot silently miss the classifier.

Detection: the run16 watchdog writes `run16-failure-report-<ts>.md` the moment
the runner disappears (log tails + artifact state + triage checklist), and a
10-minute cron wakes the session to triage; the dossier is what made this
diagnosis immediate instead of another hours-late discovery.

## run16 attempt 5 — venue cleaning meets the typed projection (2026-09-16)

Attempt 5 (14:45) passed the publication gate's placeholder check and then
aborted in `domain_projection.project_identity`:

```
invalid typed paper projection: PaperProjection.venue
  Input should be a valid dictionary or instance of NamedReference
  [input_value=None]
```

This is the direct fallout of `fee2fc85`: cleaning the placeholder venue to
absent is correct, but `PaperProjection.venue` was still required, so the
cleaned projection failed typed validation.  (Net effect: the fallback was
never a legal published value — the model and the gate simply disagreed about
where to enforce it.)

Fix: `PaperProjection.venue: NamedReference | None = None` (data-line
`41a8d96e`, the same pattern D0-a used for the professor/company fields),
pinned by the RED/GREEN test `test_paper_projection_accepts_an_absent_venue`;
135 passed across the D0-a/D1-a suites.

Serving side: the run16 pack will carry `venue: null`, so the serving model
takes the same field — `feat/serving-model-sync` `c1c17ad5` (new test
`test_paper_venue_null_is_accepted_by_the_serving_model`), merged into the
switchover tree `codex/canonical-v2-run16-ready` (`c2d2c246`, 78 passed).

## run16 attempt 6 — the model relaxation meets the database (2026-09-16)

Attempt 6 was the **first** attempt to reach the persistence stage (it passed
the projection seam, the publication gate and the relationship seeding), and
died there at 19:0x:

```
psycopg.errors.NotNullViolation: null value in column "technology_route_summary"
of relation "current_projection" violates not-null constraint
```

Root cause: D0-a made nine projection fields optional in the typed models and
the venue follow-up added a tenth, but the PostgreSQL `current_projection`
columns still carried NOT NULL — the model and the schema disagreed, and only a
build that reached `_persist_owners` could notice.

Fix (data-line `ca50ae68`): migration **C2_0015** drops NOT NULL for the
reviewed ten columns (company `profile_summary`/`technology_route_summary`,
paper `venue`, professor `department`/`email`/`homepage`/`paper_summary`/
`patent_summary`/`profile_summary`/`title`); `paper.title` and `patent.title`
stay NOT NULL because no cleaning rule can null them.  The frozen
live-schema catalog sha256 was recomputed on two independently migrated scratch
databases (`08aa5c3f372d2e215edddad90835d41985e101ba4fc166806d2d10b6cadf46f6`,
counts unchanged) and the migration scope is pinned by
`test_c2_0015_relaxes_exactly_the_reviewed_projection_columns`.

Cross-line check (verified, not assumed): the serving line tolerates a newer
database without carrying the migration — the live service serves a **C2_0013**
database while its own chain ends at C2_0012 (the revision checks live in
build-side stores only).  Attempt 7 launched 19:06.

## run16 attempt 7 — the shape CHECKs behind the NOT NULLs (2026-09-16)

Attempt 7 reached persistence again (assertions 627k, decisions 423k were
written) and died on the paper projection insert:

```
psycopg.errors.CheckViolation: new row for relation "current_projection"
violates check constraint "ck_paper_current_projection_venue_shape"
```

C2_0015 dropped NOT NULL, but the shape constraint still read
`COALESCE(is_valid_projection_named_reference(venue), false)` — false for NULL.

Fix (data-line `84100331`): **C2_0016** relaxes that constraint and its
`department` twin to `(X IS NULL) OR COALESCE(...)`.  Sibling-class sweep:
every other unguarded `COALESCE(is_valid_..., false)` shape constraint across
the four domain schemas sits on a NOT NULL column (15/15 verified), every
`*_nonempty` check on the relaxed columns is NULL-tolerant (`btrim(NULL) <> ''`
is NULL, which a CHECK accepts), and `paper.publication` /
`professor.affiliation_history` already carry the guarded form.  Frozen catalog
sha recomputed on two scratch databases (`b9befa25...`); scope pinned by a
test.  Attempt 8 launched 22:06.
