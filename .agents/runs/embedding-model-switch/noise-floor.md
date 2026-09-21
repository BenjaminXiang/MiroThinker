# Noise floor — control run of the pre-switch configuration

Purpose: the recall gate (`docs/plans/2026-09-21-embedding-model-switch-plan.md` §4) is a
non-regression gate, so it must be able to tell a signal from run-to-run variation. This control
is a second capture of the **identical** pre-switch configuration, so every difference it shows is
noise by construction.

Method: same scratch boot (`.agents/runs/embedding-model-switch/serve-18295-command.sh`, port
18295, same pack/index/state dirs), same case files, same order, only the label and the output
path changed.

| | `baseline.json` | `control.json` |
|---|---|---|
| label | `baseline-qwen3-8b-4096` | `control-1-qwen3-8b-4096` |
| captured (UTC) | 12:29–12:41 | 13:53–14:04 |
| run id | `85ee` | `4da4` |
| wall clock | 698.7 s | 489.8 s |
| turns ok | 37/37 | 37/37 |
| answer entity hits | 31/37 | 31/37 |
| candidate-layer hits | 22/37 | **29/37** |
| vector median (n) | 61.0 (34) | 61.0 (34) |
| citations local/web | 239/80 | 228/128 |
| web provider calls / cache hits | 323 / 40 | **94 / 260** |
| web provider **timeouts** | **17** | **0** |

## 1. Raw verdict

```
$ uv run python scripts/eval_recall_canonical_v2.py --diff baseline.json control.json
VERDICT: REVIEW — 0 fail-level, 3 review-level
  REVIEW rule1(concept) q15t1 [生成式模型生成] ANSWER hit->miss [web timeouts=2] (wording, not an entity)
  REVIEW rule1(concept) q15t1 [物理仿真引擎生成] ANSWER hit->miss [web timeouts=2] (wording, not an entity)
  REVIEW rule1(concept) q15t1 [基于规则生成] ANSWER hit->miss [web timeouts=2] (wording, not an entity)
```

Read with the plan's literal rule (concept strings = hard assertions), the same pair is:

```
$ uv run python scripts/eval_recall_canonical_v2.py --strict-concepts --diff baseline.json control.json
VERDICT: FAIL — 3 fail-level, 0 review-level      (same three rows)
```

**So the plan's §4.4.1 rule as written fires on noise alone.** That is the finding this run
exists for.

## 2. What flipped, case by case

| Metric | Flips between two identical runs |
|---|---|
| vector-lane candidate counts | **0 of 34 cases** (median 61.0 → 61.0, min/max identical) |
| labeled entity assertions | **0 of 37** (0 of 18 labeled cases; 21 labeled assertions in the clean subset, all identical) |
| concept assertions | **6 of 11** — q15t1 lost 3 (物理仿真引擎生成/生成式模型生成/基于规则生成), q12t1 gained 3 (遥操作/动捕数据/真机实测) |
| candidate-layer hits | 7 gains, **0 losses** — every one a concept string matching a web page title |
| citation local/web mix | 18 of 37 cases changed (median |Δ| 0, max Δ 10 local / 12 web) |
| web-lane candidate counts | 18 of 37 cases changed |
| lane set / `query_type` / `answer_style` / `understood_subject` | 0 changes (planning was stable) |
| answer text byte-identical | only 3 of 37 turns |

The last row is the one to internalise: **the answer text is essentially never reproducible**
(median length delta 51 characters), yet the labeled-entity assertions over that text are
*stable*. Stability lives in the assertion, not in the prose.

## 3. The vector-lane spread — calibrating §4.4.3

* per case: `0/34` changed, on any case, by any amount;
* median: 61.0 → 61.0 (`+0`); per-suite medians 61.0 → 61.0 (test set) and 72.0 → 72.0 (probes);
* the distribution is bimodal — `{1×1, 16×15, 58×1, 64×2, 128×15}` — 16 for subject/name plans and
  128 for category plans (a saturation cap). Nothing moved across that boundary either, because the
  planner's lane sets were identical on all 37 turns.

**Conclusion:** on this metric the measured run-to-run noise is **zero**, so §4.4.3's
"median drop > 30 % ⇒ FAIL" is *usable as written* — it cannot fire on noise at this sample size.
Two caveats for the after-run: (a) the bimodality makes the median coarse — a handful of cases
crossing the 16↔128 boundary moves it a lot, so read the per-case column, not just the median;
(b) with the lane set stable here, any boundary crossing after the switch is itself worth a look
(it would mean the planner or the similarity cutoff changed, not just scores).

## 4. The concept flip — and why the labeled rule is safe

All 6 answer-layer flips are **concept strings** (关键点 wording such as 合成数据), and all 6 sit on
cases where **A's web lane had timed out** (q12t1: 1 timeout, q15t1: 2). The mechanism, verbatim:

* `q12t1` — A: web lane empty (2 timeouts) → answer built from local company evidence
  ("真实数据采集路线在深圳这些企业里主要落在几种具体方式上…传感器与设备侧采集…"), no 遥操作/动捕/真机;
  B: web lane healthy (104 candidates, 12 web citations) → "真机遥操作：由操作员通过远程控制器实时操控机器人…"
  → all three strings appear. **Gain caused by web availability.**
* `q15t1` — A: web lane empty (2 timeouts), 2 local citations → the 关键点 wording survived;
  B: web healthy (67 candidates, 12 web citations) → the answer followed a web narrative
  ("视频合成+3D重建 vs 端到端3D生成") → the 关键点 wording vanished. **Loss caused by web availability.**

Restricting to the **24 cases where neither run hit a provider timeout**: **0 flips** — and 9 of
those 24 still had *different* web-lane candidate counts. The labeled rule therefore did not fire
even under a substantial real-world web perturbation, which is the property a blocking gate needs.

## 5. Why the two runs had different web evidence

| | baseline | control |
|---|---|---|
| provider calls (live) | 323 | 94 |
| served from cache | 40 | 260 |
| provider timeouts | 17 | 0 |
| instance quota counters (`web_quota`) | +173 bocha / +171 serper | +47 / +47 |

The baseline ran with a cold cache and made ~27 live provider calls per minute, which is what its
17 timeouts look like; the control ran against the cache the baseline had already filled, made ~8
live calls per minute, and timed out zero times. **The baseline is the degraded run on the web
lane, not the control.** The vector lane is unaffected by either condition (it is local
retrieval), which is why the metric the embedding switch moves is the one that is exactly stable.

Provider quota: this scratch instance's own counters now read **bocha 220 / serper 218 for
2026-09-21** — 438 live provider calls for the whole chain (323 baseline + 94 control + ~21
smoke/aborted). The live 18188 line's counters are separate and were 1 call per provider today.

## 6. Recommendations (measured, for the plan's §4.4)

| §4.4 rule | Measured noise | Recommendation |
|---|---|---|
| labeled entity lost from **both** the candidate set and the answer | 0 in 18 labeled cases | **FAIL** — unchanged, this is the gate's core (it is the retrieval losing the entity, which is what a worse embedding does) |
| labeled entity lost from the **answer only** (candidate set still holds it) | 0 labeled; the only mechanism ever observed was web evidence | **REVIEW** (was FAIL) — a human reads the two answers; it cannot block on its own |
| labeled entity lost from the **candidate layer only** (answer still names it) | 7 gains / 0 losses | **REVIEW** (was FAIL) — handle-set churn, web-title sensitive |
| **concept** strings (关键点 wording) | 3 lost + 3 gained between identical runs | **REVIEW** by default; `--strict-concepts` restores the plan-literal FAIL for a paper-trail reading |
| probe GT lost (answer or top-k) | no probe flipped | **REVIEW** — unchanged |
| any case losing **>50 % of its vector candidates** | 0 of 34 | **REVIEW for every suite, with an anchor ≥ 8 floor** (was probes-only, no floor); below the floor a 4→0 change is a cutoff artefact, not a halving |
| **median vector drop >30 %** | median identical | **FAIL — keep exactly as written.** With zero measured noise it cannot fire spuriously; it is coarse (bimodal) but it is the only aggregate tripwire that maps to "召回退化" |
| candidate-layer scoring of concept strings | 7 spurious "gains" | **dropped from verdicting** — a concept string is not an entity handle, so its candidate cell is informational only |

**Dropped as unusable:** concept strings as FAIL-level assertions, and sub-floor vector deltas
(< 8 candidates). **Annotated rather than dropped:** every verdict line now carries
`[web timeouts=n]` when the run of record had a degraded web lane, so the reader sees why an
answer-layer row moved.

**Protocol change for the after-run** (the only remaining source of ambiguity): capture it the way
the control was captured — run the full pass **twice** and judge the second one. The first pass
fills the web cache and is discarded; the judged pass then makes ~1/3 of the live provider calls
and (measured) zero timeouts, which is the condition under which the labeled rule was stable here.
Cost: one extra pass (~47–94 provider calls, ~8 min).

## 7. What this control does not tell you

* It cannot bound the **cold-cache** answer-layer noise: the control's web evidence was largely the
  baseline's own cached results. The 24 clean cases perturbed *which* results arrived, but not the
  fetch/failure behaviour of a cold pass. If the after-run is captured cold, expect the baseline's
  kind of web-timeout noise back.
* It says nothing about the after-switch direction (no switched index exists yet).
* One control is n=1 as a sample of the *process*: it proves the labeled rule survived one large
  perturbation, not that its false-positive rate is zero. A second control would strengthen that.
* LLM call counts remain unobservable from the service (no usage ledger); the provider counters
  above are web-search only.
