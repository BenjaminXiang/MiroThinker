# Alias gap evidence — 字节跳动 → ByteDance Ltd. (2026-09-13)

Question (user, 2026-09-13): should the alias / entity-link gap be solved at
the data-governance layer? Verdict: **yes — build-side projection + data
supplement (C1 "alias closure"); no query-side fuzzy matching.**

## Evidence

### Pack side (`serving-pack-run14-sealed`; byte-identical to `index-v1`)

- `ByteDance Ltd.` exists as a canonical company
  (`company-c-c725850f55349b6b308ec1ca`) with `aliases: []`,
  `industry=企业服务`, `tech_tags=[大型互联网公司]`, product description
  listing 抖音/TikTok/今日头条/飞书/豆包… — the entity is right, the Chinese
  brand surface is missing.
- Alias coverage: **342 / 7,089 companies (4.8%)** carry any alias.
- 「字节跳动」 appears in 16 company docs — all *mentions* in prose
  (e.g. 深圳新言意码 or team bios "原字节跳动AIoT线技术负责人"), i.e. the
  query text-matches the wrong entities precisely because the right entity
  lacks the alias surface.
- Serving already consumes aliases correctly: verbatim alias channel +
  normalized-name channel + derived compact short-name channel
  (`knowledge_read_isolated.py` company binding), with uniqueness/fanout
  guards. Missing data, not missing machinery.

### Source side (accepted restore, batch inputs)

- `p4-company-full-v1.jsonl` (6,514 rows): **6,504 rows (99.8%)** carry
  `project_name` and it differs from `company_name`; ByteDance's row:
  `company_name="ByteDance Ltd."`, `project_name="字节跳动"`.
- `company_knowledge_fields.jsonl`: 8 rows, no ByteDance.
- `company_backfill.jsonl`: 700 records, **467 with aliases** — the only
  alias batch actually merged into the pack (优必选's aliases, e.g.
  `["优必选科技","UBTECH",…]`, come from here). Shenzhen-focused, no
  ByteDance.
- Build chain: `knowledge_build_isolated.py:2567` projects
  `core_facts.aliases` only when the payload carries it; no reference to
  `project_name` exists anywhere in `canonical_v2/` — so the p4 brand name
  is dropped at projection time, not by the serving read path.

## Direction (C1 slice)

1. **Projection mapping** (mechanical): `project_name → aliases` for
   company projections, normalized and deduplicated per release.
2. **Supplement batch** for entities that stay alias-empty after (1)
   (curated file, same admission pattern as `company_backfill.jsonl`).
3. **Guardrails kept at serving** (already implemented): generic-word
   exclusion (公司/深圳/机器人-class forms), cross-entity fanout cap,
   ambiguity → fallback instead of guessing.
4. **Out of scope**: query-time fuzzy/semantic alias invention; web
   completion remains the path for entities genuinely absent locally.

## Expected effect

- '字节跳动' binds ByteDance Ltd. via the existing verbatim-alias channel;
  alias coverage for the pack rises from 4.8% toward source availability
  (~99.8% of p4 rows carry a brand name), subject to the guardrails.
- Affected queries: bare-brand name lookups, brand→patent/company
  traversals, and category queries that name brands in short form.

## Verification (to run with the C1 slice)

- Rebuild-side: alias count delta + collision report (forms shared by >1
  entity) + generic-form rejection report.
- Serving-side: after pack pick-up, `字节跳动` → ByteDance Ltd. exact
  binding probe; G2b replay session re-run; no regression on the alias
  fanout guards (`_ENTITY_LINK_MAX_FORM_FANOUT` tests).
