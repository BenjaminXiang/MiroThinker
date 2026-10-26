# Link-coherence calibration (gate 3.3 → 3.2)

Date: 2026-10-27. Source: `coherence-all.json` (736 linked professors with
`research_directions`; directions embedded against the top-5 linked paper titles,
cosine).

## Metric: top-3 mean, not mean

The first pass averaged all five paper similarities. That penalises prolific
authors, who legitimately span sub-topics even when the core work matches:
张纵辉 (55 papers, wireless) scored 0.304 on the mean but 0.348 on its best
three; 陈高洁 (41 papers, communications) moved 0.301 → 0.337. The question the
gate needs is "does the core of the work sit near the declared directions", so
the gate uses **top-3 mean**; the mean is kept in the artefacts for reference.

## Distribution (n = 736)

| stat | top-3 | mean (reference) |
|---|---|---|
| median | 0.409 | 0.365 |
| p10 | 0.249 | 0.229 |
| ≥ 0.33 | 539 | 550 (at ≥0.30) |

## Labels (30 professors read by hand)

| professor | verdict | mean | top-3 |
|---|---|---|---|
| 朱军 | match | 0.374 | 0.409 |
| 杨朋 | partial | 0.299 | 0.375 |
| 陈名华 | match | 0.303 | 0.370 |
| 张纵辉 | probable match | 0.304 | 0.348 |
| 陈高洁 | probable match | 0.301 | 0.337 |
| 黎维彬 | probable match (2 papers) | 0.323 | 0.323 |
| 王强 | **merge** | 0.249 | 0.275 |
| 张旻 | **merge** | 0.198 | 0.211 |
| 李骏 | **merge** | 0.195 | 0.211 |
| 宋清海 | match, `no_directions` | 0.182 | unscorable |

The ten highest (0.487–0.565 on the mean) were 10/10 correct; the ten lowest
(0.129–0.194) contained five clear merges.

## Threshold

**top-3 ≥ 0.33 → materialisation allowlist** (536 professors, 6,112 papers).
Below-threshold (200) and no-direction (272) professors keep no `paper_count`.

- 杨朋 at 0.375 is included and is the known grey case (one strongly matching
  paper among five) — the band 0.33–0.38 holds 92 professors and is the first
  place to look when something looks wrong.
- 黎维彬 at 0.323 is a false negative (a 2-paper professor whose titles still
  read like his field); acceptable, because missing a number is cheaper than
  stating a wrong one.

## Caveats

- 30 labels is a convenience sample; the threshold is **provisional**.
- 272 linked professors (27%) have no directions and cannot be scored at all.
- Directions themselves vary in quality (duplicated entries, very broad terms).
- Chinese directions vs English titles: the model is cross-lingual, domain
  jargon can still miss.
- The record-level gate (implausible name, bad homepage) still applies first;
  today it rejects 11 linked records, including 师资力量 and 面包屑.

## Artefacts

- `coherence-all.json` — per professor: paper scores, mean, top-3.
- `professor-projection-allowlist.json` — 536 professors with
  `paper_count`, `top_papers`, both scores, flags.
- `professor-projection-review.json` — the 200 below threshold.
- `projection-allowlist.md` — dry-run of what the answer would say.

## Next (gate 3.2)

Render the claim text for allowlisted professors through the real composer path
(or a faithful dry run), then add a **sidecar overlay** the serving runtime can
opt into (`CANONICAL_V2_PROFESSOR_PROJECTION=<path>`, default off), because the
pack files are hash-checked and must not be patched in place. Behaviour change →
OpenSpec change + eval gate on the 27 turns before it is enabled on the customer
site.
