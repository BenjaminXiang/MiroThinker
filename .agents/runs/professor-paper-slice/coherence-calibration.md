# Link-coherence calibration (gate 3.3 → 3.2)

Date: 2026-10-27 (session clock). Source: `coherence-top200.json` (200 linked
professors with `research_directions`, top-5 paper titles, embedding cosine
against the direction text).

## Distribution (n = 200)

| stat | value |
|---|---|
| min / p10 | 0.129 / 0.220 |
| p25 / median / p75 | 0.297 / 0.347 / 0.389 |
| p90 / max | 0.460 / 0.565 |
| ≥ 0.25 | 173 (86%) |
| ≥ 0.30 | 146 (73%) |
| ≥ 0.33 | 120 (60%) |
| ≥ 0.40 | 44 (22%) |

## Labels (30 professors read by hand)

Earlier round (10): matches 0.303–0.470, merges 0.196–0.248, one
`no_directions` case unscorable at 0.182.

This round, the 10 lowest:

| professor | pack directions | linked papers | verdict |
|---|---|---|---|
| 李晶 (HIT-SZ) | 自然语言处理/大模型 | nickelate superconductivity, Cr(VI) reduction, red mud zeolite | **merge** |
| 冯娟 (Tsinghua-SZ) | 在线劳动力市场/定价/UGC | online reviews (match) + DNA methylation + NMDA receptors | **merge** |
| 李强 (Tsinghua-SZ) | 内波/深海/AUV | tactile servoing, LDO circuit, imitation learning | **merge** |
| 李勃 (Tsinghua-SZ) | 信息功能陶瓷/超构材料 | 3D sensor networks, hydrogel, apoptosis | **merge** |
| 李骏 (HIT-SZ) | 新体制雷达 | single-atom catalysts | **merge** |

And the 10 highest (0.487–0.565): 董超 (super-resolution), 冯平法 (ultrasonic
machining), 苏阳 (graphene membranes), 李佳 (organic phototransistors),
朱时裴 (liquid-liquid phase separation), 田佳峻 (fiber sensors), 张瑶晶
(integrated photonics), 李海文 (hydrogen storage), Faisal Nadeem Khan (optical
networks, 2/3 titles), 贺艳兵 (solid-state batteries) — **10/10 correct**.

## Provisional threshold

**0.33**: materialisation allowlist = professors scoring ≥ 0.33.
At the top-200 level that is 120 professors (60%); applying the same rate to the
741 linked professors that *have* directions gives ~445 professors. Professors
below 0.33 (and the 268 linked professors without directions) keep **no**
`paper_count` — the answer simply does not state a number.

Why 0.33 and not 0.30: at 0.30 the nearest labelled match (0.303) sits 0.005
above the line, while the nearest labelled merge sits at 0.248 — the band is too
thin to spend on recall. Precision dominates because the output is a factual
claim shown to users.

## Caveats (must be re-checked before/after materialisation)

- 30 labels is a convenience sample; the threshold is **provisional**.
- Direction text quality varies: some directions are duplicated strings
  (李勃 has the same direction twice), some are very broad ("大模型").
- Professors without directions cannot be scored at all; they are excluded, not
  judged.
- The metric compares Chinese directions with English titles; the embedding model
  handles cross-lingual reasonably but domain jargon can still miss.
- Materialisation is still gated by the record-level gate in gate 3.1
  (implausible name, bad homepage).

## Next (gate 3.2)

Score all linked professors with directions (~741 → ~220 embedding calls),
produce `professor-projection-allowlist.json` (only ≥0.33), and render a dry-run
of the professor claim text for 10 allowlisted + 10 excluded professors so the
difference is visible before any deploy.
