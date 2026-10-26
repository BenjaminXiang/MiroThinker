# Verification: professor-paper projection (gate 3.1)

Date: 2026-10-27 07:15 (session clock 2026-10-26 23:15 CST). Branch
`feat/professor-paper-slice` (off `hotfix/customer-20261026`).

Pack: `/var/tmp/mirothinker-data-v2/serving-pack-fembed-v3-synthdepth`
(the pack the customer site runs).

## What the builder does

`scripts/build_professor_paper_projection.py` reads the pack read-only and
projects, per professor, `paper_count`, `paper_ids` (capped) and `top_papers`
from the relationship edges — but only for records that pass a field-quality
gate:

- name is a person's name (2–4 CJK characters or a latin name) and not page
  chrome (`面包屑`, `首页`, `更多`, …) or a generic title (`教授`, `院士`, …);
- homepage is a URL;
- a corrupted email is dropped from the projection but does not reject the
  person (the crawler concatenates page labels into the address).

Flagged, not dropped: `high_paper_count` (≥100), `duplicate_name`,
`template_summary`, `no_directions`, `low_confidence_edge`.

## Results

```
professors: 3958            papers: 24520           edges: 10742
professors_with_edges: 1019 projected_professors: 1009 rejected: 10
rejected_by_reason: {bad_homepage: 5, implausible_name: 5}
email_dropped: 107
projected_professor_paper_pairs: 10417   projected_distinct_papers: 10123
professors_gaining_paper_count: 866
flags: template_summary 384, no_directions 268, duplicate_name 8, high_paper_count 1
```

- The 5 junk names (`教授`, `院士`, `讲师`, `副教授`, `面包屑`) are rejected —
  `面包屑` (217 papers, previously the top node) no longer appears.
- 107 corrupted emails dropped (≈10.6% of the linked professors).
- **Edge confidence is not a usable signal**: all 10,742 edges carry
  `confidence = 1.0`, `method = deterministic`. The graph declares full
  confidence for every attribution, including merged ones.

## Manual review of the top 10 by paper count (10 samples)

| Professor | Pack directions | Top papers | Verdict |
|---|---|---|---|
| 朱军 (CUHK-SZ) | 物理有机化学 | Möbius aromatic pentalenes, hydroboration, nanohoops | match |
| 陈名华 (CUHK-SZ) | 信息论/安全 | privacy in video surveillance, regenerating codes | match |
| 宋清海 (HIT-SZ) | 光学/激光 | perovskite random lasers, nanolasers | match |
| 王向荣 (CUHK-SZ) | 凝聚态/自旋电子学 | topological magnonics, magnetic semiconductor | match |
| 李志刚 (CUHK-SZ) | 电力系统调度 | unit commitment, wind power dispatch | match |
| 张健全 (CUHK-SZ) | 有机太阳能电池 | indoor organic photovoltaics, non-fullerene acceptors | match |
| 王强 (HIT-SZ) | HPC/AI 系统 | hyperspectral anomaly detection + photonic crystals + CO₂ adsorbents | **mismatch** |
| 张旻 (Tsinghua-SZ) | 昆虫级软体机器人 | terahertz absorber, Uni-MoE LLM, acousto-optic modulation | **mismatch** |
| 李骏 (HIT-SZ) | 新体制雷达 | single-atom catalysis, iridium catalysts | **mismatch** |
| 杨朋 (Tsinghua-SZ) | 仓储调度 | DOA estimation, high-dimensional optimization, picking optimization | partial |

**6/10 clear matches, 3 clear same-name merges, 1 partial.** The mismatches are
not fixable by the record gate: the professor records are fine, the *edges*
joined papers by author name without affiliation evidence.

## Conclusion (drives the next step)

The projection is correct as data and wrong as facts: projecting it into
answers would state "王强 66 篇论文" for a professor whose actual field is HPC.
**Materialisation (3.2) must not happen before identity disambiguation (3.3).**

Identity sources checked this session:

| source | status |
|---|---|
| OpenAlex | HTTP 429 — free daily budget exhausted on the shared IP, resets 00:00 UTC |
| Semantic Scholar | HTTP 429 |
| ORCID public API | **200**, returns `orcid-id`, given/family names (institution field empty in search results) |

## Tests

`pytest tests/test_professor_projection_gate.py` → **11 passed** (no pack needed):
name gate (junk/CJK/latin/length), strict email gate (page-label concatenation,
TLD bounds, spaces), corrupted-email handling, bad homepage, edge aggregation,
top-paper ordering, unknown paper/professor handling, flags
(duplicate/high-count/template/no-directions/low-confidence), and 2-tuple edge
back-compatibility.

## Artefacts

- `.agents/runs/professor-paper-slice/projection-report.json`
- `.agents/runs/professor-paper-slice/professor-projection.json` (1,009 records)
- `.agents/runs/professor-paper-slice/projection-audit.json` (gate 3.0 audit)
- The 3.5 GB relationships file is not copied; the builder caches edges to a
  caller-specified JSONL (deleted after the run).

## Identity-source probe (gate 3.3 pre-work, 2026-10-27)

Tested whether a professor's identity can be confirmed from public sources
before anything is materialised.

| source | result |
|---|---|
| ORCID expanded-search + works/employments | **unusable for this population**: 丁文伯 18 candidates, all empty records (0 works, no employments) except a PolyU PhD student; 王强 79,769 candidates; no candidate carries both works and a matching institution |
| OpenAlex | HTTP 429 (free daily budget exhausted on the shared IP) |
| Semantic Scholar | HTTP 429 |
| professor homepage (王强 / 张旻 / 李骏 / 朱军) | 3 pages fetched (3.3–6.9k chars), **0/3 of the linked top papers appear on the page**; 朱军's site fails TLS negotiation. Homepages are landing pages, not publication lists |

## Semantic coherence experiment

`scripts/measure_professor_paper_coherence.py` embeds the professor's declared
directions and their top-5 linked paper titles, then reports the mean cosine.

| professor | verdict from manual review | coherence |
|---|---|---|
| 张健全 | match | 0.470 |
| 李志刚 | match | 0.434 |
| 朱军 | match | 0.374 |
| 王向荣 | match | 0.351 |
| 陈名华 | match | 0.303 |
| 杨朋 | partial | 0.295 |
| 王强 | **merge** | 0.248 |
| 张旻 | **merge** | 0.203 |
| 李骏 | **merge** | 0.196 |
| 宋清海 | match, but `no_directions` | 0.182 (scored against a generic summary) |

Among professors **with** directions the five matches sit at 0.295–0.470 and
the three merges at 0.196–0.248 — separable on this sample, but the margin is
thin (0.248 vs 0.295) and n=8. Professors without directions cannot be scored
at all. Conclusion: a useful **review signal**, not a gate yet; needs 30+
labelled samples before any threshold is used to filter materialisation.

Artefact: `.agents/runs/professor-paper-slice/coherence.json`.
