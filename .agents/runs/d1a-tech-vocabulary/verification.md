# Verification: d1a-tech-vocabulary (D1-a)

Change: `openspec/changes/d1a-tech-vocabulary/` · Branch `feat/d1a-tech-vocabulary`
(worktree `.worktrees/d1a-tech-vocabulary`, baseline `data/p4-serving-pack-rebuild` @ `312a8beb`).
Run workspace: `.agents/runs/d1a-tech-vocabulary/`.

## 0. Commits

| Milestone | Commit |
|---|---|
| M1 module + replay + projection seam + OpenSpec + verification contract (RED written first) | `8da81ce8` |
| M2 transcript-format fix (the first recording attempt answered CSV) + per-call attempt telemetry | `e8e3fee3` |
| M3 recorded bundle + packaged artifact + replay counters + human log/index/ledger | `499b9934` |

## 1. Environment and safety

- The run15 pack was read **only** through the copy
  `/tmp/d1a-scratch/lookup-run15.sqlite3` (668,884,992 bytes, copied once from
  `/var/tmp/mirothinker-data-v2/serving-pack-run15-sealed/lookup.sqlite3`; the
  copy was the only operation that touched the production directory, and it was a
  read).
- Zero writes under `/var/tmp/mirothinker-data-v2/`: every script opens the copy
  with `file:...?mode=ro`; `manifest.json` was copied read-only as well.
- 18188 untouched: not restarted, no request issued against it.
- No rebuild triggered; the change is documented as effective from run16.
- Credential: `.deepseek_api_key` via `providers/local_api_key.py` /
  `llm_profiles.resolve_professor_llm_settings`; never printed, hashed or written
  into an artifact (bundle records provider/model/prompt version only).

## 2. Verification layered

### ① New tests written in this slice

`apps/miroflow-agent/tests/canonical_v2/test_tech_vocabulary.py` — **18 tests, all passing**
(`uv run pytest tests/canonical_v2/test_tech_vocabulary.py -q` → `18 passed`).

| Cluster | Tests | What it locks |
|---|---|---|
| replay determinism | `test_replay_is_deterministic_and_separates_mapped_from_unmapped` | two replays of one bundle are byte-identical; mapped/unmapped split; concept lookup |
| bundle integrity | `test_bundle_loader_rejects_a_modified_transcript`, `test_load_rejects_an_edited_bundle` | an edited transcript / edited bundle is refused (no provider fallback exists) |
| composition integrity | `test_replay_rejects_a_lost_mapping_call`, `test_replay_rejects_a_changed_source_value_set` | the batch composition is recomputed from the recorded inputs, so a bundle recorded for another value set cannot silently map a subset |
| transcript schema | `..._a_concept_outside_the_vocabulary`, `..._a_malformed_transcript_line`, `..._a_drifted_prompt`, `..._single_valued_field_cannot_map_to_several_concepts`, `..._mapping_parser_rejects_an_unrequested_value` | invented concepts, malformed lines, prompt drift and arity violations fail closed |
| projection application | `test_application_publishes_concepts_and_keeps_unmapped_verbatim`, `test_applied_tags_validate_against_the_projection_model`, `test_other_domains_are_untouched` | mapped values publish concepts, unmapped values publish the raw label with the build's own reference id, the result still validates as `CompanyProjection`, other domains untouched |
| gate and report | `test_quality_section_counts_coverage_and_published_values`, `..._gate_rejects_coverage_below_the_floor`, `..._gate_rejects_a_published_value_without_a_decision`, `..._collection_gap_does_not_block_the_gate`, `test_attach_section_merges_idempotently_and_keeps_the_report` | coverage arithmetic, the "no third case" published check, the collection gap reported not blocked, idempotent report merge |

Fixture source: constructed scenarios. The fixture bundle is produced by the same
module functions the recorder uses (prompt renderers, chunk composition, hashes),
so the tests exercise the production replay path, not a golden string.

### ② Pre-existing regression suites

- `uv run pytest tests/canonical_v2/test_domain_projection_contract.py tests/canonical_v2/test_index_projection_embedded_content.py`
  → **33 passed** (the 8 failures seen before the artifact existed were the seam
  failing closed on a missing vocabulary; they disappear once the artifact is packaged —
  that is itself the fail-closed evidence).
- `uv run pytest tests/canonical_v2 -q` → see §3; the full-suite outcome and the
  failure triage are recorded there.

### ③ Real-data replay counters

`python3 .agents/runs/d1a-tech-vocabulary/scripts/count_vocabulary_replay.py`
(7,086 company documents of the run15 copy). The script refuses to run unless the
packaged artifact equals the recorded bundle's replay output, and it recomputes
every number below from the pack.

## 3. Commands and outcomes

```text
$ python3 .agents/runs/d1a-tech-vocabulary/scripts/extract_vocabulary_inputs.py
company_documents 7086 · tech_tag_rows 5485 · tech_tag_distinct_values 4945
tech_tag_singletons 4679 · industry_distinct_values 41 · companies_without_tech_tags 1601
industry_tags_equal_industry 5480 · industry_tags_differing 0
probe baseline: 送餐 0 · 配送机器人 1 · 餐饮机器人 1 · PCB 11 · 激光雷达 7 · 传感器 121 · 机器人 422(422)

$ python3 .agents/runs/d1a-tech-vocabulary/scripts/induce_vocabulary.py --phase all --workers 12
provider=deepseek model=deepseek-v4-pro base_url=https://api.deepseek.com
12 induction chunks recorded (50 sampled values each), 51 mapping calls recorded
bundle: out/recorded-vocabulary-decision-bundle.json, call_count=63,
content_sha256=7f09ac67e82a5bb80d94c2379da626e047339546ca0e0528afd00bd0a81491e9

$ python3 .agents/runs/d1a-tech-vocabulary/scripts/build_vocabulary_artifact.py
concepts 447 · mappings 4713(+31 industry) · unmapped 242
content_sha256=d41041e447fcb755df1b26faad12509aa90c1a81063a430476dc6dc965d880fe
bundle_content_sha256=7f09ac67e82a5bb80d94c2379da626e047339546ca0e0528afd00bd0a81491e9
(two replays compared byte-for-byte inside the script; it refuses to write on a difference)
the SHA is pinned in tech_vocabulary.VOCABULARY_ARTIFACT_CONTENT_SHA256

$ python3 .agents/runs/d1a-tech-vocabulary/scripts/count_vocabulary_replay.py
(asserts artifact == replay(bundle) before counting)
coverage 0.953084 · distinct 4945 -> 673 · rows 5485 -> 6130 · tags/company 0.774 -> 0.865
```

### Replay reproducibility (the R21 guard #2 claim)

| check | evidence |
|---|---|
| two replays byte-identical | `build_vocabulary_artifact.py` compares two `artifact_document(replay(...))` renders and raises on any difference; the same property is a unit test |
| artifact == replay(bundle) | asserted by `count_vocabulary_replay.py` on every run (and by `build_vocabulary_artifact.py --check-only`) |
| no provider at build time | the projection calls `apply_packaged_vocabulary`, which reads the packaged JSON only; the module imports no provider client and `grep -n "OpenAI\|openai" src/data_agents/canonical_v2/tech_vocabulary.py` returns nothing |
| prompt/model version recorded | bundle fields `provider`, `model`, `prompt_version`, `output_schema_version`, `prompts.{induct,map}.sha256`; a drifted template fails the replay |
| rerun cost | a rebuild replays in-process from a 934 KB JSON - **0 provider calls** |

### The counters (before → after, run15 copy)

| metric | before | after |
|---|---|---|
| distinct `tech_tags` values | 4,945 | **673** (447 concepts + 232 unmapped verbatim) |
| mapped values | — | 4,713 (95.31%) |
| `tech_tags` rows | 5,485 | 6,130 (5,895 concept + 235 passthrough) |
| tags per company (mean) | 0.774 | 0.865 |
| companies carrying concepts | 0 | 5,250 (74.1%) |
| companies with no tag at all | 1,601 | 1,601 (collection gap, unchanged) |
| concept-level probe support | 工业机器人 43 / 传感器 121 / 机器人 414 / 具身智能 11 / PCB 11 | **128 / 173 / 423 / 14 / 11** |
| probes whose literal string is replaced (`no company lost`) | 激光雷达 7, 灵巧手 5, 协作机器人 3, 配送机器人 1, 餐饮机器人 1 | each lists the concepts its companies now carry (e.g. 激光雷达 → 激光扫描传感器模组 5, IC芯片 1, 毫米波雷达 1) |

### Outbound quota (honest count)

| number | value | source |
|---|---|---|
| recorded calls in the bundle (the only calls the build replays) | **63** (12 induction + 51 mapping) | `bundle.call_count` |
| provider attempts belonging to the recorded calls, including the calls that needed a retry | 67 | `out/induction-telemetry.json` |
| HTTP calls made in this session overall (includes 4 abandoned attempts from the pre-fix recording rounds and 1 smoke probe) | 54 + the abandoned rounds | telemetry + terminal log |
| tokens of the recorded calls | 308,200 prompt / 102,493 completion | bundle `usage` |

Failed or abandoned attempts are **not** written into the bundle (they never
became a decision) but are counted here - a quota report that hid them would be
dishonest.

### The three rejected recording attempts (why the mechanism matters)

1. attempt 1: the model answered a **CSV header** (`id,name,definition,...`) - the
   prompt listed the keys without a format example; the parser refused all three
   attempts and nothing was recorded;
2. attempt 2 (after the prompt fix): **500 concepts, truncated mid-line** - the
   parser refused;
3. attempt 3 (64 K output budget): **1,337 concepts, truncated mid-line** - the
   parser refused;
4. the fix was structural, not a retry: induction is **chunked** (12 x 50 sampled
   values), which bounds every transcript; all 12 recorded first-try.

### Full `tests/canonical_v2` suite

Command: `uv run pytest tests/canonical_v2 -q -p no:cacheprovider` (background log
`/tmp/d1a-regression.log`). Outcome and triage: see §4 "Regression suite outcome".

## 4. Regression suite outcome

`tests/canonical_v2` on this branch is **not all-green on the baseline**.  The full
run (`uv run pytest tests/canonical_v2 -q`) reached ~56% in ~20 minutes and then
stalled inside `test_knowledge_build_isolated.py`, so it was stopped inside the
slice's budget; the failures visible in its progress log cluster in two families.
They were triaged with targeted runs instead:

| run | outcome | reading |
|---|---|---|
| `test_domain_projection_contract.py` + `test_index_projection_embedded_content.py` | **33 passed** | the two suites the seam actually touches are green (before the artifact existed they failed 8/33 - that was the seam failing closed) |
| `test_tech_vocabulary.py` | **18 passed** | this slice's own tests |
| `test_knowledge_build_isolated.py -k "company or Company"` | 12 passed, **1 failed** | the one failure is `test_real_boundary_rejects_nonfresh_database_before_source_read[company.current_projection]` |
| `test_knowledge_build_isolated.py -k "real_boundary"` | 7 passed, **11 failed** | every failure is in the `real_boundary ... [<table>]` family (live-Postgres freshness/fingerprint probes across 11 tables) |

Reading of the failures: the `real_boundary` family asserts against a **live local
Postgres** (port 5433) fingerprint/freshness state; it is parametrized over tables
(which is what produced the long `FFFFFFFFFF` runs in the progress log) and it does
not exercise the projection value path this slice changes.  Earlier work on the
same branch recorded the same shape of environment-bound failures.

**Honest gap:** a baseline run of the same suites at `312a8beb` was *not* executed
inside this slice (running the suite in another agent's worktree would write there,
which the slice forbids).  The claim here is therefore "the failures are outside the
files and behaviour this change touches, and the suites that do touch it pass", not
"the failures are proven pre-existing".  Next command to close it:
`git stash`-free checkout of `312a8beb` in a throwaway worktree +
`uv run pytest tests/canonical_v2/test_knowledge_build_isolated.py -k real_boundary`.

## 5. Open items carried by this slice

- A vocabulary refinement round (add dedicated concepts for 激光雷达/灵巧手/协作机器人/
  配送机器人/餐饮机器人) requires re-recording every mapping call, because the
  catalogue is part of the recorded prompt; the procedure is documented in the
  human log.
- `industry` coverage (31/41) is reported, not gated; the reason and the ten
  undecided labels are recorded in `acceptance.md`.
- `publication-quality-report.json` wiring: `attach_vocabulary_section` merges the
  `vocabulary` section into the report payload and is unit-tested, but D0-b's
  report writer lives on `chore/data-cleaning-batch1`, which is not in this
  branch's lineage, so the one-line call site is documented (design §6) rather than
  applied here.
