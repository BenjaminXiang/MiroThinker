# Proposal: synthesis-depth-min (slice ①min)

> Behavior-affecting. Touches the sealed serving pack's Web-material chain
> (`canonical_v2/knowledge_serving_isolated.py`): the read-side Web window for
> Web-only list/concept turns and the LLM query-rewrite views' vocabulary.
> Human-side plan: `docs/plans/2026-10-15-gap-status-and-fix-order.md` §4 片①min.

## Why

Round 42 recorded the complaint verbatim: 「目前有哪几种主流的JEPA变体？」 answered
with a thin flat list while the customer's reference answer is a 7-category, 20+
variant survey. Slice ② fixed the retrieval-layer half (a question sentence can no
longer pose as a subject). This slice is the synthesis-side remainder — and the
first thing its diagnosis found is that **the synthesis layer never received the
material**: on the live line today the same question returns a 719-char answer
with **zero citations**, because the evidence set is eight irrelevant pages and
nothing else.

Measured today on the dev line (verbatim, `.agents/runs/synthesis-depth-min/red-case.md`):

| observation | value |
|---|---|
| material actually kept for the answer | 8 of 16 Web candidates (`max_web_results=8`); **all 8 are 「EJA 压力变送器」 pages** (JEPA→EJA name collision) |
| why the good views lose | the merged Web list is **view-order concatenation**, the deterministic view (the raw question) leads, so ranks 1–10 are junk and the rewrite views' real material starts at rank 11 — past the window |
| provider probe, 4 pipeline views | deterministic 0/10 relevant · `JEPA 变体` 4/12 · `JEPA 主要变体 类型` 0/12 · `联合嵌入预测架构 变体` 4/11 |
| same window widened to 16 / 24 | **3 / 4** relevant kept (vs **0 / 8** today) |
| the gate that withholds the widening | `enumeration_window_widened` requires a **local-scope foothold**; a Web-only concept turn can never have one, so list-shaped concept questions keep the 8-wide window by construction |
| the rewrite prompt | asks only for 简短中文关键词式 queries; an English/full-name form (`JEPA joint embedding predictive architecture variants`) returns **11/11 relevant arXiv papers** |

## What Changes

1. **Web window for Web-only list-shaped turns.** When the turn is Web-only
   (no local-scope foothold) *and* the query carries list/enumeration intent, the
   read side keeps `bundle.max_candidates + bundle.max_web_results` (16 today)
   Web results instead of 8. Local-candidate windows are untouched (nothing
   local executes on those turns).
2. **Rewrite views keep an English / full-name form.** One clause is added to the
   Web query-rewrite prompt: when the subject is an abbreviation or a technical
   term, one of the 1–3 queries may be its English full name / English keywords.
   (No entity fabrication: expanding an acronym is not an entity claim.)
3. **Answer shape: no change.** The renderer already instructs categorised
   concept answers ("按行业常见分类分条组织答案…"); this slice's acceptance is
   that the same renderer, given real material, produces them.

## Invariants

- Never-refuse wording, protected slots, per-view protected-value retention,
  marker-token discipline, candidate caps and the citation/grounding rules are
  untouched.
- The change is a plan-level window + a prompt clause: no new lane, no new
  provider, no model-knowledge injection, no change to A–G semantics.
- Rollback = keep the current pack byte-identical and flip back; a kill switch
  (`CANONICAL_V2_WEB_WIDE_WINDOW`) turns the window change off in-process.

## Out of scope

- Parametric-knowledge depth (the `intent-aware-synthesis` idea, un-implemented
  pre-canonical artifact) — a product decision, not this slice.
- English-lane providers, rerank policy, snippet budgets.
- Anything in the answer-renderer prompt (measure first; only revisit if the
  material alone does not lift the answer).
