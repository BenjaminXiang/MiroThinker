# Proposal: d1a-tech-vocabulary (D1-a controlled technical vocabulary)

> D1-a of `docs/plans/2026-09-15-requirements-gap-plan.md` §8.5 (R21) and launch
> gate #5 of §11 ("D1-a 受控技术词表 (LLM 归纳 + 录制重放可复现) 至少主体完成").
> Human log: `docs/plans/2026-09-15-d1a-tech-vocabulary-log.md`.
> Assessment input: `docs/plans/2026-09-15-data-quality-assessment.md` findings 4 and 5.

## Why

`tech_tags` and `industry` are free text, so category queries cannot recall a category.

- `tech_tags`: 5,485 rows / **4,945 distinct values** (run15, re-measured here),
  90.2% of them appearing exactly once, each company carrying at most one tag.
  70.4% of the values carry a vendor suffix ("研发商/服务商/提供商/生产商").
  Normalising case/width/space merges **0** labels: the problem is not formatting,
  it is the absence of a controlled vocabulary.
- `industry`: 41 overlapping labels (`人工智能` 1297 / `硬件` 1193 / `生产制造` 931 /
  `先进制造` 881 = 61%), the same business lands in different labels (PCB appears as
  `电子制造` for three companies and `生产制造` for three others), and `industry_tags`
  is a 100% duplicate of `industry` (5,480 companies, zero differing rows).
- Retrievability: the substring `送餐` matches **0** companies in the tag fields,
  `配送机器人` **1**, `餐饮机器人` **1**; the 8 companies labelled `industry=机器人`
  have no `tech_tags` at all.

The tags are not only published, they are part of the vector content of the company
projection (`index_projection.py`), so the vocabulary decides whether the vector lane
can answer "which Shenzhen companies build delivery robots".

## What Changes

1. **A controlled concept vocabulary** with, per concept, a canonical name, a
   definition and the evidence forms that qualify a company for it - induced by an
   LLM with world knowledge (user rule §8.5), in batches, covering every distinct
   `tech_tags` value (4,945) and every distinct `industry` value (41).
2. **A recorded decision bundle** holding the exact provider transcripts, provider,
   model and prompt version. The build **replays** the bundle instead of calling an
   LLM, so a rebuild reproduces the mapping byte for byte (R21 guard #2).
3. **Projection-time application**: the published `tech_tags`/`industry`/`industry_tags`
   values become vocabulary concept references, at the same seam where D0 cleaning
   happens, so lookup documents *and* vector content inherit the mapping. A value the
   LLM could not decide stays published **verbatim** and is counted as `unmapped` -
   nothing is guessed and nothing is dropped.
4. **A vocabulary gate and report section**: unique value count, concept count,
   mapping coverage, unmapped count and category-probe support go into
   `publication-quality-report.json`; the build fails when coverage drops below the
   declared floor or when a published tag reference is not backed by the vocabulary.
   The *collection* gap (one tag per company, 1,601 companies with none) is reported,
   never blocked - it is not a vocabulary defect.

## Out Of Scope

- No re-tagging of companies from local free text (product/route summaries): the
  candidate-generation step of §2.5 is deferred, so no "LLM 推断" tag enters the
  retrieval surface in this change.
- No mining of new tags from other batches, no company re-collection.
- No rebuild: the change is effective from run16.
- No retirement of the `industry_tags` declaration (it needs a catalog revision; the
  axis is mapped in place and reported).
