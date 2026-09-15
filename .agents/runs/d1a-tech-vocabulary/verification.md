# Verification: d1a-tech-vocabulary (D1-a)

Change: `openspec/changes/d1a-tech-vocabulary/` · Branch `feat/d1a-tech-vocabulary`
(worktree `.worktrees/d1a-tech-vocabulary`, baseline `data/p4-serving-pack-rebuild` @ `312a8beb`).
Run workspace: `.agents/runs/d1a-tech-vocabulary/`.

## 0. Commits

| Milestone | Commit |
|---|---|
| M1 module + replay + projection seam + OpenSpec + verification contract (RED first) | `8da81ce8` |
| M2 transcript-format fix (first recording attempt returned CSV) + attempt telemetry | `e8e3fee3` (see `git log`) |
| M3 recorded bundle + artifact + counters + docs | see `git log --oneline feat/d1a-tech-vocabulary` |

## 1. Environment and safety

- run15 pack read **only** through the copy `/tmp/d1a-scratch/lookup-run15.sqlite3`
  (`cp` from `/var/tmp/mirothinker-data-v2/serving-pack-run15-sealed/lookup.sqlite3`,
  668,884,992 bytes; the production directory was opened for reading only by that `cp`,
  never by sqlite).
- Zero writes under `/var/tmp/mirothinker-data-v2/` (`find` check recorded below).
- 18188 untouched: no restart, no request issued against it.
- No rebuild triggered; the change is documented as effective from run16.
- Credential: `.deepseek_api_key` read through `providers/local_api_key.py` /
  `llm_profiles.py`; never printed, hashed or written into any artifact (the bundle
  records provider/model/prompt version only).

## 2. Verification layered

### ① New tests written in this slice — `apps/miroflow-agent/tests/canonical_v2/test_tech_vocabulary.py`

18 tests, all passing. What each cluster locks:

| Cluster | Tests | Locks |
|---|---|---|
| replay determinism | `test_replay_is_deterministic_and_separates_mapped_from_unmapped` | two replays of one bundle are byte-identical; mapped/unmapped split; concept lookup |
| bundle integrity | `..._loader_rejects_a_modified_transcript`, `..._load_rejects_an_edited_bundle` | an edited transcript or an edited bundle is refused (no fallback) |
| composition integrity | `test_replay_rejects_a_lost_mapping_call`, `..._a_changed_source_value_set` | the batch composition is recomputed, so a bundle recorded for another value set cannot silently map a subset |
| transcript schema | `..._a_concept_outside_the_vocabulary`, `..._a_malformed_transcript_line`, `..._a_drifted_prompt`, `..._single_valued_field_cannot_map_to_several_concepts`, `..._mapping_parser_rejects_an_unrequested_value` | invented concepts, bad lines, prompt drift and arity violations fail closed |
| projection application | `test_application_publishes_concepts_and_keeps_unmapped_verbatim`, `test_applied_tags_validate_against_the_projection_model`, `test_other_domains_are_untouched` | mapped values publish concepts; unmapped values publish the raw label with the build's own reference id; the result still validates as `CompanyProjection`; other domains untouched |
| gate and report | `test_quality_section_counts_coverage_and_published_values`, `..._gate_rejects_coverage_below_the_floor`, `..._gate_rejects_a_published_value_without_a_decision`, `..._collection_gap_does_not_block_the_gate`, `test_attach_section_merges_idempotently_and_keeps_the_report` | coverage arithmetic, "no third case" published check, collection gap reported not blocked, idempotent report merge |

Fixture source: constructed scenarios. The fixture bundle is produced by the same
module functions the recorder uses (prompt renderers, batch composition, hashes), so
the tests exercise the production replay path rather than a golden string.

### ② Pre-existing regression suites

(run recorded below — `tests/canonical_v2` + the two suites the projection seam touches)

### ③ Real-data replay counters (RAG/data-line claims)

(run recorded below — `scripts/count_vocabulary_replay.py` over all 7,086 run15
company documents; the script itself asserts the packaged artifact equals the
recorded bundle's replay output.)

## 3. Commands and outcomes

(filled from the actual runs)
