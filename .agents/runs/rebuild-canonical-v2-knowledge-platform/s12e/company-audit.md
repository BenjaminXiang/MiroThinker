# Company Domain Audit — candidate-s12c-20260726-r8

Track: 公司域审计 (read-only). DB: `miroflow_candidate_s12c_20260726_r8` on container `canonical-v2-s12c-pg-20260726-r8`. Index: `/var/tmp/mirothinker-canonical-v2-s12c/r8/index/lookup.sqlite3`. All numbers verified by SELECT in this session.

## 1. Funnel: landing.source_record → company.current_projection

| Stage | Count | Note |
|---|---|---|
| landing.source_record (object_type='company') | 1037 | all in batch `s12a-released-objects-full-v1`; parse_status ok |
| knowledge.source_identity (company) | 1037 | all `active`, 0 superseded/rejected |
| knowledge.canonical_identity (company) | 1037 | 1:1 with source identities, no merge/split |
| domain_inclusion_decision (company) | 1037 admitted / 0 excluded / 0 review | limitations={} on all; contrast: professor gate rejected 王学谦 |
| company.current_projection | 1037 | quality_status='partial', quality_signals={partial} on ALL rows |
| lookup documents (`lookup:exact-lookup:company`) | 1037 | 1:1 with projections |

- Zero rejections: the inclusion gate has effectively never fired for companies. There is no rejected population to mine for recall recovery — all loss happens upstream (source coverage) or inside the pipeline (assertion whitelist).
- Supplement batches are inert: 21 records (`s12c-r7-company-workbook-supplement-v1` 13 + `s12c-r7-company-knowledge-v1` 8) are parse_status='parsed' and mapped in `source_identity_record` (21 rows) but produced **0 source_assertions**. Their content reached projections only because the main-batch payloads were pre-merged before landing — and even that merge kept only the text fields: the workbook's 网址/注册地址 (e.g. 普渡 `pudurobotics.com`, 嘉立创 `jlcgroup.cn`) never made it into the merged core_facts (website still NULL for those 13).
- Source coverage gap (recall ceiling): major expected companies absent — 优必选/大疆/汇川技术/速腾聚创/越疆/腾讯/宇树/松延动力/加速进化/众为兴/雷赛 all 0 name hits (only `华为精密制造有限公司` matches 华为*). Name prefix: 733 深圳*, 304 other. 4 informal names lacking 公司/有限 suffix: 群核科技, 光轮智能, 九号机器人, 银河通用.

## 2. Thin-profile statistics (company.current_projection, n=1037)

| Field | NULL/empty | Source (landing core_facts) fill | Gap type |
|---|---|---|---|
| website | 1037 (100%) | 625 (60.3%) | **assertion drop** |
| key_personnel (column + child table) | 1037 (100%) / 0 rows | 851 cos, 1293 entries (82.1%) | **assertion drop** |
| industry / industry_tags | 1037 (100%) | 1037 (100%) | **assertion drop** |
| evaluation_summary (no column) | — | 1037 (100%) | dropped by design |
| founded_at / registered_address / registered_capital / legal_representative / geography / credit_code / aliases | 1037 (100%) each | 0 — never collected | **source gap** |
| product_description / products / team_description / latest_public_updates / tech_tags / patent_count | 1037 (100%) | 0 | source gap |
| All 8 child tables (product, key_personnel, capability, business_scenario, financing_event, public_update, personnel_education, personnel_work_experience) | 0 rows | — | source+assertion gap |

- Non-empty projected content is exactly 4 fields: name, normalized_name, profile_summary (avg 179 chars), technology_route_summary (avg 162 chars). knowledge.source_assertion confirms: only 6 field_paths exist for companies (the 4 content fields + identity.name_key + identity.historical_source_id), 1037 each.
- Root cause in code: `_ALLOWED_FIELD_PATHS_BY_OBJECT_TYPE["company"]` whitelists only `core_facts.name`, `core_facts.normalized_name`, `summary_fields.profile_summary`, `summary_fields.technology_route_summary` (`apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_build_isolated.py:778-784` in the s11 worktree). Everything else in the payload is silently discarded at assertion time.
- lookup_content envelopes in the index mirror this: field_lineage covers only the same 4 paths; all other keys empty in all 1037 docs.
- landing payload quality_status='ready' for all 1037 vs projection quality_status='partial' for all — uniform downgrade with zero per-company differentiation; the signal carries no information.

## 3. Staleness spot-check (15 companies)

Provenance: evidence source_type = xlsx_import 1037 (1024 from `专辑项目导出1768807339.xlsx`, 13 from `company_workbook_critical_supplement.xlsx`), manual_review 7, public_web **1** (only 1 company has any URL evidence). Every record's last_updated = 2026-04-16; projection as_of = 2026-07-26. The domain is a static spreadsheet snapshot ~3.5 months old with no web refresh path.

| Company | Basis | Summary claim | Risk note |
|---|---|---|---|
| 上海开普勒机器人有限公司 | workbook | 通用人形机器人 | old "酒店配送" defect now FIXED; still workbook-only, no URL evidence |
| 深圳市普渡科技有限公司 | workbook | 商用配送机器人(餐饮/酒店/零售) | plausible; workbook 网址 lost in merge (see §1), website NULL |
| 云迹科技股份有限公司 | workbook | 酒店/楼宇机器人智能体 | plausible; frozen 2026-04 |
| 上海擎朗智能科技有限公司 | workbook | 商用无人配送 | plausible; frozen |
| 九号机器人 | workbook | 服务机器人+短交通 | informal name; summary vague, misses 滑板车/割草机 main lines |
| 银河通用 | workbook | 仿真数据预训练具身模型 | informal name (北京银河通用机器人), 1-line profile |
| 深圳嘉立创科技集团股份有限公司 | workbook | PCB/SMT 一站式 | plausible; workbook 网址 lost in merge, website NULL |
| 帕西尼感知科技（深圳）有限公司 | export | 多维触觉+人形机器人 | rich text but frozen at export; no founded/financing fields |
| 戴盟（深圳）机器人科技有限公司 | export | 触觉灵巧手+遥操作 | frozen; key_personnel dropped |
| 星尘智能（深圳）有限公司 | export | AI 机器人助理 (Astribot) | English name only inside free text, not queryable |
| 深圳元戎启行科技有限公司 | export | L4 自动驾驶 | frozen; DeepRoute 英文名不可查 |
| 深圳市众擎机器人科技有限公司 | export | 人形机器人研发商 | frozen 2026-04 |
| 深圳逐际动力科技有限公司 | export | 具身智能/全尺寸人形 | frozen; LimX Dynamics 英文名不可查 |
| 自变量机器人科技（深圳）有限公司 | export | 通用具身大模型 | frozen; WALL-A 系列后续版本不可见 |
| 深圳市智元芯科技有限公司 | export | 异构计算/数据存储 | frozen |

Heuristic conclusion: no post-2026-04 business change can be represented; any company that pivoted/launched after the export (e.g. 开普勒-type drift) will be silently stale again. Summaries are template-generated (`{name}是一家聚焦{行业}的企业。细分方向覆盖{子领域}…`), so low-info and stale profiles are indistinguishable from good ones without external checks.

## 4. Alias / English name / credit-code coverage

- aliases: 0/1037 (0%). credit_code: 0/1037. Latin characters in name or normalized_name: 0/1037 — no English names anywhere in the queryable projection.
- normalized_name ≠ name on 1032/1037 (suffix stripping works and is the ONLY alternate key).
- Serving exact-match compares against display_name (casefold equality or ≥8-char substring, knowledge_serving_isolated.py:3701-3708). Short brand names (普渡/擎朗/云迹/逐际) and English names (Pudu/Kepler/LimX/Astribot/DeepRoute) cannot exact-hit; they fall back to semantic recall only.

## 5. Top-5 field gaps ranked by recall impact

1. **aliases / English names (0%)** — kills exact-lookup for brand names, English names, and former names; highest direct查全 impact.
2. **industry/industry_tags (source 100% → projection 0%)** — pure assertion-whitelist drop; breaks domain filtering, fusion boosts, and 行业类 A-G queries.
3. **key_personnel (source 82.1%, 1293 entries → 0%)** — pure assertion drop; blocks professor_company_role growth (currently 1 relationship); 10 key_personnel names string-match professor display names (common-name caveat).
4. **website (source 60.3% → 0%)** — pure assertion drop; removes a strong entity-disambiguation/identity-resolution key and a user-facing traceability anchor.
5. **registered_address / founded_at / credit_code (0% at source)** — never collected; blocks dedup confidence, 地区类 queries (geography also 0%), and any time-based (成立年限) reasoning. Fixing requires a source backfill, not just a pipeline change.

## 6. Prioritized recommendations

1. **Widen the company assertion whitelist** (`knowledge_build_isolated.py:778-784`) to include `core_facts.industry`, `core_facts.website`, `core_facts.key_personnel` (and decide on `summary_fields.evaluation_summary`): zero new ingestion needed, instantly lifts industry/website/key_personnel from 0% to 100%/60.3%/82.1% in projections, and unblocks the 8 empty child tables where mappable. Add a contract test asserting payload-vs-assertion field coverage per domain.
2. **Alias backfill**: derive aliases from normalized_name + 项目名称 (workbook) + English names mined from existing profile free text (e.g. Astribot, LimX Dynamics, PaXini already present inside summaries); populate `aliases` so exact-lookup works for brand/English names. Then add credit_code/founded_at/registered_address via a registry backfill source.
3. **Fix the inert supplement path + freshness**: the 21 parsed-but-unasserted supplement records show the pipeline silently swallows late batches — wire them into assertion runs or reject them loudly; then establish a web-evidence refresh for company profiles (currently 1/1037 has any URL evidence, all frozen at 2026-04-16), prioritizing the ~30 high-visibility robotics companies, and fill the source-coverage hole for missing majors (优必选/大疆/速腾聚创/越疆…).
