# RED case — web-lane topical floor (T1)

Reported turn (user, live 18188, session `chat:bKkX9SSixSj6uj-11vNIQVFCWIr27M8M`,
turn 3). Verbatim from the live turn-debug dump
`/home/longxiang/MiroThinker/.agents/runs/close-workbook-gaps/turn-debug/turn-debug-bKkX9SSixSj6-03.json`:

```
query            = 详细介绍一下 国先中心（深圳）
turn_count       = 3
recalled_handles = [company-c-cdb522437bb0946c96ba7d33  深圳国际先进技术应用推进中心]
committed_names  = [深圳国际先进技术应用推进中心]
lane_timings     = structured 0.0 / exact 2.781 / lexical 3.223 / web 4.159 / vector 19.67
```

Web items in 「查看检索过程」 (3), titles/URLs verbatim:

1. `多彩深圳——减肥达人训练营深圳国贸营地简介` — www.sohu.com
2. `建重大平台强核心攻关优产业生态深圳新质生产力加速迸发` — www.sz.gov.cn
3. `百步先(深圳)信息技术有限公司` — www.11467.com

Snippets are **not** in the dump (it stores evidence counts, not raw provider
text); the reproduction below reconstructs them, marked as reconstructed. The
final answer cited only the local company, so the synthesis absorbed the noise —
but the three items are the turn's web evidence and ride into the next turn's
session carry-over.

## Reproduction

`python .agents/runs/web-lane-topical-floor/red_repro.py` (current tree, no
network, no model). Fixtures: the three titles/URLs above with reconstructed
snippets; request `bound_entity_names=(深圳国际先进技术应用推进中心,)`,
`original_query=详细介绍一下 国先中心（深圳）`.

Verbatim output (baseline commit `10dd2bd1`, before the floor):

```
bound=('深圳国际先进技术应用推进中心',) soft=None
  anchor_qualifier=None
  tier=5 entity_hit=False corroborated=False | 多彩深圳——减肥达人训练营深圳国贸营地简介
  tier=0 entity_hit=False corroborated=True  | 建重大平台强核心攻关优产业生态深圳新质生产力加速迸发
  tier=5 entity_hit=False corroborated=False | 百步先(深圳)信息技术有限公司
  gate kept 3/3; gate_drops=[]
    KEPT  建重大平台强核心攻关优产业生态深圳新质生产力加速迸发
    KEPT  多彩深圳——减肥达人训练营深圳国贸营地简介
    KEPT  百步先(深圳)信息技术有限公司
```

## Attribution

The diet-camp page is **tier 5 (missed)** — the wrong-organization channel —
and enters through **H2**, the backfill branch of
`_apply_web_subject_consistency` (`knowledge_serving_isolated.py:854`):

- kept (tier 0/1) = 1 — the sz.gov.cn round-up, promoted to **tier 0 by H3**,
  the `len(corroborating_provider_versions) >= 2` shortcut that is blind to
  relevance;
- 1 < `_WEB_SUBJECT_CONSISTENCY_FLOOR` (3), so the backfill branch runs with
  `backfill_room = 3 - 1 - 0 = 2` and `pool = suspect(T4) + missed(T5)`;
- the diet page (T5) and the 11467 page (T5) fill both slots.

Nothing is dropped: `record_gate_drop("web_subject_consistency", …)` stays
silent, so the turn trace shows no filtering either.

**H1 is not this case.** H1 (`if not bound_entity_names: return results`) is a
second, independent hole on web-only sessions (no bound entity, no soft
subject) and the floor closes it as well; the reproduction prints that path for
completeness (`CASE bound=() soft=None`: gate returns all results unfiltered).

## Reconstructed-snippet caveat

The sz.gov.cn round-up's fate under the floor depends on its real snippet: the
reconstruction carries no core token (国先 / 先中 / 中心), so it drops too
(`floor kept 0/3`). If the live page's snippet names the center (中心/国先/
先进技术), it survives and the lane keeps one item. The real snippet is
captured in the scratch run (§verification.md) and decides this.

## Assertion that must flip

Before: for this query the three pages are admitted (verbatim above).
After: the diet-camp page and the 11467 page are dropped, and the drop is
counted as `record_gate_drop("web_topical_floor", n)`.
