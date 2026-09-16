# Verification contract: data-cleaning-batch1 (D0-a)

RED = the baseline numbers in `docs/plans/2026-09-15-data-quality-assessment.md`
and `.agents/runs/data-quality-assessment/placeholder-recount.txt`, measured on
the run15 sealed pack.  GREEN = the same measurements re-run through the new
rules with `count_cleaning_batch1.py`.

Provenance note: the assertions below were fixed from the assessment *before*
implementation; the contract file itself was materialized in the same session as
the code (single-session slice).  See `verification.md` §Honesty.

## Contract

| ID | RED (before) | GREEN (after) | How verified |
|---|---|---|---|
| C1 | whole-value `未找到` = 1,817 published values | 0 | `out/counts.json.baseline_classes_after` (no `whole_value_*` keys) |
| C2 | `未找到`-prefix values = 2 | 0 | same |
| C3 | glue runs = 189, of which 177 carry format damage | 177 withheld, 0 published | `after.glue_damaged_values == 0` |
| C4 | - | the 9 legitimate-prose glue values are kept and enumerated | `out/kept-legit-prose.jsonl` (9 lines) |
| C5 | placeholder-family values published = 15,976 (audit walk) | 0 | `after.placeholder_hits == 0` |
| C6 | company geography province-only = 4,887 | <= 2 (only unparseable addresses) | `geography_after.province_only == 2` |
| C7 | company geography city-level = 601 (incl. `广东省-深圳市` 554) | >= 5,400 | `geography_after.city_level == 5,486` |
| C8 | research-direction junk = 796 of 10,238 | 0 | `after.research_direction_junk == 0` |
| C9 | - | every quarantined value traceable (rule + verbatim value + `reference_id`) | `out/quarantine.jsonl` 973 records |
| C10 | - | a pack that would republish junk cannot build | unit tests `test_gate_refuses_*`, `test_index_projection_gate_is_wired_into_the_build` |
| C11 | - | cleaning output validates against the typed projections | `test_cleaned_*_payload_validates_against_the_projection_model` |
| C12 | - | no writes to `/var/tmp/mirothinker-data-v2/` | pack opened `mode=ro&immutable=1`; scratch copy only |

## Unit-test RED/GREEN pairs (rule level)

Each rule ships a positive sample (must be cleaned) and a negative sample (must
survive) taken verbatim from run15 - fixtures in
`.agents/runs/data-cleaning-batch1/fixtures/run15-samples.json`:

| Rule | positive (cleaned/withheld) | negative (untouched) |
|---|---|---|
| exact/prefix placeholder | `未找到`, `-`, `暂无数据`, "Not supplied by the historical source." | `深圳市普渡科技有限公司` |
| glue damage | `DM-7未找到未找到C...`, `V1.未找到`, `Web3.未找到` | patent abstract `...或未找到最终目标节点...` |
| no-information sentence | `根据现有信息，未找到该公司产品的具体应用场景信息。` | `根据现有信息，该公司业务与智能家居领域相关，但未找到...` |
| geography | `广东省` + `深圳市南山区...` -> `广东省-深圳市` | `广东省-深圳市` unchanged; no address -> unchanged |
| research directions | nav block, `蛹等）`, `1`, `不同取食策略生物的耐热性，仍缺乏系统验证`, dated dump | `人工智能`, `2D/3D目标检测`, bilingual long direction |

## Exit

* All counts reconciled (see acceptance.md §Reconciliation; the two explained
  deltas are scanner scope and the assessment's own internal bookkeeping).
* run16 is where the cleaning becomes effective (no production data touched).
