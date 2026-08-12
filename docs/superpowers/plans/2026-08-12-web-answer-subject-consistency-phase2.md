# Web Answer Subject Consistency Phase 2 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rank web evidence by branch/organization/wrong-organization relevance, pin qualified anchors to their branch, guide users of multi-branch organizations via prompt-level guidance, enrich retrieval with authority-seeking views, and feed the correction retry with one fetched authority page.

**Architecture:** All retrieval-side logic lives in `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py` (gate, identity forms, query views, renderer). Answer-side plumbing reuses the phase-1 correction hooks (`_anchor_correction_name` / `_answer_mentions_anchor` / `_anchor_correction_message`) and the existing stream raise/fallback flow in `knowledge_answer.py`. Fetch reuses `apps/miroflow-agent/src/data_agents/providers/page_fetch.py`.

**Spec:** `docs/superpowers/specs/2026-08-12-web-answer-subject-consistency-phase2-design.md` (commit `04e01a3`).

**Tech Stack:** Python 3.12, pytest, ruff; no new dependencies.

## Global Constraints

- Worktree: `/home/longxiang/MiroThinker/.worktrees/canonical-v2-s11-consolidation` (branch `codex/canonical-v2-s12a-ready`). All paths below are relative to it.
- No new third-party dependencies. `pypinyin` (lazy_pinyin) and httpx/BS4 are already used by the module.
- `prompt_version` bump: `canonical-v2-prose-v15` → `canonical-v2-prose-v16` (single bump, in the task that changes the prompt).
- Company-entity behavior must not regress: company legal-suffix truncations (`深圳市普渡科技有限公司 → 普渡科技`) remain **full-name forms**, never compact aliases.
- Never-refuse invariant (phase 1): no new refusal/interrogation channel; referent clarification stays untouched.
- Stream correction must be fail-open: a failed corrective retry on the stream path returns the original streamed result, it must NOT raise — `knowledge_answer.py:2189-2192` rolls back and re-raises when chunks were already published.
- Test commands (run from `apps/miroflow-agent` unless noted):
  `uv run pytest tests/canonical_v2/<file> -q --no-cov`
- Lint: `uv run ruff check <changed files>` must pass before every commit.
- Commit style: follow `git log --oneline` conventions (`fix(canonical-v2): …` / `feat(canonical-v2): …`).

---

### Task 1: Identity-form split + branch qualifier helpers + relevance tier classifier

**Files:**
- Modify: `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py` (helpers live near `_web_identity_forms` at :1877-1898)
- Test: `apps/miroflow-agent/tests/canonical_v2/test_knowledge_serving_isolated.py`

**Interfaces:**
- Consumes: existing `_normalized_web_identity(value) -> str` (:1873), `_web_identity_forms(value) -> tuple[str, ...]` (:1877), `_compact_company_alias` (same file), `_NormalizedWebResult` (:774-781).
- Produces (later tasks rely on these exact names):
  - `_ANCHOR_LOCATION_LEXICON: frozenset[str]`
  - `_parenthesized_qualifier(value: str) -> str | None` — raw qualifier inside `（…）`/`(...)`, normalized.
  - `_org_name_stem(value: str) -> str` — normalized full name minus any parenthesized qualifier.
  - `_anchor_location_qualifier(anchor_name: str, query: str) -> str | None` — qualifier if it is location-like, else a lexicon location co-occurring with the stem in the query, else None.
  - `_web_identity_full_name_forms(value: str) -> tuple[str, ...]` — normalized full name + parenthesized variants + company suffix truncations (NO compact alias).
  - `_web_identity_compact_aliases(value: str) -> tuple[str, ...]` — only the `_compact_company_alias`-derived forms.
  - `_evidence_branch_qualifiers(*, org_stem: str, texts: tuple[str, ...], anchor_qualifier: str | None) -> tuple[str, ...]` — location qualifiers attached to the org name in raw evidence texts, excluding the anchor qualifier, deduped in first-seen order.
  - `_web_result_relevance_tier(*, result: _NormalizedWebResult, bound_entity_names: tuple[str, ...], anchor_qualifier: str | None) -> int` — returns 0..5 (T0 corroborated … T5 no match).

**Tier semantics (from spec §1):**

- T0: `len(result.corroborating_provider_versions) >= 2`
- Compute `searchable = _normalized_web_identity(f"{result.title} {result.snippet}")`.
- T1 (needs `anchor_qualifier`): org stem in `searchable` AND normalized qualifier in `searchable`.
- T3: org stem in `searchable` AND a *different* location qualifier from `_evidence_branch_qualifiers` attached to the stem in the title/snippet.
- T2: org stem in `searchable` (none of T1/T3). Also T2 when there is no `anchor_qualifier` and a full-name form hits.
- Company suffix truncations hitting count as the same tier as the stem hit they imply (they are full-name forms).
- T4: only `_web_identity_compact_aliases` forms hit (via `_web_identity_text_matches`, :1925).
- T5: nothing hits. With multiple bound names, the best (lowest) tier wins.

- [ ] **Step 1: Write the failing tests**

```python
_ANCHOR = "国际先进技术应用推进中心（深圳）"

def _result(title, snippet="", url="https://example.com/a", providers=("bocha",)):
    return _NormalizedWebResult(
        title=title, url=url, snippet=snippet, summary="",
        primary_provider_version=providers[0],
        corroborating_provider_versions=providers,
    )

def test_tier_t1_branch_qualified_hit():
    r = _result("国际先进技术应用推进中心（深圳）揭牌", "河套深港科技创新合作区")
    assert _web_result_relevance_tier(
        result=r, bound_entity_names=(_ANCHOR,), anchor_qualifier="深圳",
    ) == 1

def test_tier_t2_same_org_unqualified():
    r = _result("国际先进技术应用推进中心是由国家发展改革委指导的综合性技术应用机构")
    assert _web_result_relevance_tier(
        result=r, bound_entity_names=(_ANCHOR,), anchor_qualifier="深圳",
    ) == 2

def test_tier_t3_other_branch_content():
    r = _result("国先中心（合肥）执行主任程羽强调推动机器人真实应用")
    assert _web_result_relevance_tier(
        result=r, bound_entity_names=(_ANCHOR,), anchor_qualifier="深圳",
    ) == 3

def test_tier_t4_loose_alias_only():
    # 南开国际先进研究院 shares the compact alias 国际先进 but not the org stem.
    r = _result("南开国际先进研究院（深圳福田）在实验室参观交流中")
    assert _web_result_relevance_tier(
        result=r, bound_entity_names=(_ANCHOR,), anchor_qualifier="深圳",
    ) == 4

def test_tier_t0_corroborated_trumps_everything():
    r = _result("完全无关的标题", providers=("bocha", "serper"))
    assert _web_result_relevance_tier(
        result=r, bound_entity_names=(_ANCHOR,), anchor_qualifier="深圳",
    ) == 0

def test_tier_t5_no_match():
    r = _result("两台国际先进水平手术的背后", "华西口腔医院")
    assert _web_result_relevance_tier(
        result=r, bound_entity_names=(_ANCHOR,), anchor_qualifier="深圳",
    ) == 5

def test_company_truncation_stays_full_name_form():
    forms = _web_identity_full_name_forms("深圳市普渡科技有限公司")
    assert any("普渡科技" in f for f in forms)
    assert _web_result_relevance_tier(
        result=_result("普渡科技完成Pre-D轮融资"),
        bound_entity_names=("深圳市普渡科技有限公司",),
        anchor_qualifier=None,
    ) == 2

def test_anchor_location_qualifier_from_parens_and_query():
    assert _anchor_location_qualifier(_ANCHOR, "介绍一下") == "深圳"
    assert _anchor_location_qualifier(
        "国际先进技术应用推进中心", "国际先进技术应用推进中心在深圳的布局"
    ) == "深圳"
    assert _anchor_location_qualifier("国际先进技术应用推进中心", "介绍一下") is None

def test_evidence_branch_qualifiers_excludes_anchor_and_non_locations():
    texts = (
        "国际先进技术应用推进中心（合肥）成立理事会",
        "国先中心（深圳）揭牌",
        "国际先进技术应用推进中心（大湾区）中心在广州南沙设立",
    )
    assert _evidence_branch_qualifiers(
        org_stem=_org_name_stem(_ANCHOR), texts=texts, anchor_qualifier="深圳",
    ) == ("合肥", "大湾区")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/miroflow-agent && uv run pytest tests/canonical_v2/test_knowledge_serving_isolated.py -k "tier_t or truncation_stays or anchor_location_qualifier or evidence_branch" -q --no-cov`
Expected: FAIL (`NameError`/`ImportError` — helpers do not exist).

- [ ] **Step 3: Implement the helpers**

In `knowledge_serving_isolated.py`, after `_web_identity_forms` (:1898), add:

```python
_ANCHOR_LOCATION_LEXICON = frozenset({
    "北京", "上海", "广州", "深圳", "合肥", "南沙", "杭州", "苏州", "南京",
    "武汉", "成都", "重庆", "西安", "天津", "青岛", "宁波", "无锡", "长沙",
    "郑州", "佛山", "东莞", "珠海", "厦门", "福州", "济南", "大连", "沈阳",
    "哈尔滨", "长春", "昆明", "贵阳", "南昌", "太原", "石家庄", "兰州",
    "乌鲁木齐", "呼和浩特", "南宁", "海口", "银川", "西宁", "拉萨", "香港",
    "澳门", "台北", "雄安", "大湾区",
})

_PAREN_QUALIFIER_RE = re.compile(r"[（(]([^（）()]{1,8})[）)]")


def _parenthesized_qualifier(value: str) -> str | None:
    match = _PAREN_QUALIFIER_RE.search(value)
    if match is None:
        return None
    qualifier = _normalized_web_identity(match.group(1))
    return qualifier or None


def _org_name_stem(value: str) -> str:
    return _normalized_web_identity(_PAREN_QUALIFIER_RE.sub("", value))


def _anchor_location_qualifier(anchor_name: str, query: str) -> str | None:
    qualifier = _parenthesized_qualifier(anchor_name)
    if qualifier is not None:
        return qualifier if qualifier in _ANCHOR_LOCATION_LEXICON else None
    stem = _org_name_stem(anchor_name)
    if not stem:
        return None
    normalized_query = _normalized_web_identity(query)
    if stem not in normalized_query:
        return None
    for location in _ANCHOR_LOCATION_LEXICON:
        if location in normalized_query:
            return location
    return None
```

Split `_web_identity_forms` without changing its output contract (existing callers `:1951-1965`, `:4148-4159`, `:1968-1994` rely on it):

```python
def _web_identity_full_name_forms(value: str) -> tuple[str, ...]:
    normalized = _normalized_web_identity(value)
    forms = [normalized]
    stem = _org_name_stem(value)
    if stem and stem != normalized:
        forms.append(stem)
    for suffix in ("有限责任公司", "股份有限公司", "有限公司", "公司"):
        normalized_suffix = _normalized_web_identity(suffix)
        if normalized.endswith(normalized_suffix):
            shortened = normalized[: -len(normalized_suffix)]
            if len(shortened) >= 4:
                forms.append(shortened)
                without_city = re.sub(
                    r"^[\u3400-\u9fff]{2,4}市", "", shortened, count=1,
                )
                if len(without_city) >= 4:
                    forms.append(without_city)
            break
    return tuple(dict.fromkeys(form for form in forms if form))


def _web_identity_compact_aliases(value: str) -> tuple[str, ...]:
    compact_alias = _normalized_web_identity(_compact_company_alias(value))
    full = set(_web_identity_full_name_forms(value))
    if len(compact_alias) >= 2 and compact_alias not in full:
        return (compact_alias,)
    return ()


def _web_identity_forms(value: str) -> tuple[str, ...]:  # re-implemented, same output
    return (*_web_identity_full_name_forms(value), *_web_identity_compact_aliases(value))
```

NOTE: `_web_identity_forms` currently appends the compact alias even when it
duplicates a full-name form (`dict.fromkeys` dedupes). Verify with the
existing test suite (any test pinning forms output) that the re-implementation
produces identical tuples for company names; if `_compact_company_alias`
returns the full name for non-companies, `_web_identity_compact_aliases`
returns `()` — preserve that behavior.

Then the branch extraction and tier classifier:

```python
def _evidence_branch_qualifiers(
    *, org_stem: str, texts: tuple[str, ...], anchor_qualifier: str | None,
) -> tuple[str, ...]:
    if not org_stem:
        return ()
    found: list[str] = []
    pattern = re.compile(
        r"[（(]([^（）()]{1,8})[）)]"
    )
    for text in texts:
        if org_stem not in _normalized_web_identity(text):
            continue
        for match in pattern.finditer(text):
            qualifier = _normalized_web_identity(match.group(1))
            if (
                qualifier in _ANCHOR_LOCATION_LEXICON
                and qualifier != anchor_qualifier
                and qualifier not in found
            ):
                found.append(qualifier)
    return tuple(found)


def _web_result_relevance_tier(
    *,
    result: _NormalizedWebResult,
    bound_entity_names: tuple[str, ...],
    anchor_qualifier: str | None,
) -> int:
    if len(result.corroborating_provider_versions) >= 2:
        return 0
    searchable = _normalized_web_identity(f"{result.title} {result.snippet}")
    best = 5
    for entity_name in bound_entity_names:
        stem = _org_name_stem(entity_name)
        full_hit = any(
            _web_identity_text_matches(form, searchable)
            for form in _web_identity_full_name_forms(entity_name)
        )
        if full_hit:
            if anchor_qualifier is not None and stem and stem in searchable:
                if anchor_qualifier in searchable:
                    return 1  # best possible, stop early
                other_branches = _evidence_branch_qualifiers(
                    org_stem=stem,
                    texts=(f"{result.title} {result.snippet}",),
                    anchor_qualifier=anchor_qualifier,
                )
                best = min(best, 3 if other_branches else 2)
            else:
                best = min(best, 2)
            continue
        if any(
            _web_identity_text_matches(form, searchable)
            for form in _web_identity_compact_aliases(entity_name)
        ):
            best = min(best, 4)
    return best
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/miroflow-agent && uv run pytest tests/canonical_v2/test_knowledge_serving_isolated.py -k "tier_t or truncation_stays or anchor_location_qualifier or evidence_branch" -q --no-cov`
Expected: PASS (8 tests).

- [ ] **Step 5: Regression + lint + commit**

Run: `cd apps/miroflow-agent && uv run pytest tests/canonical_v2/test_knowledge_serving_isolated.py -q --no-cov && uv run ruff check src/data_agents/canonical_v2/knowledge_serving_isolated.py tests/canonical_v2/test_knowledge_serving_isolated.py`
Expected: all pass (existing gate tests unchanged — Task 2 changes behavior).

```bash
git add apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py apps/miroflow-agent/tests/canonical_v2/test_knowledge_serving_isolated.py
git commit -m "feat(canonical-v2): identity-form split and relevance tier classifier"
```

---

### Task 2: Three-tier subject-consistency gate

**Files:**
- Modify: `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py` (`_apply_web_subject_consistency` :833-868)
- Test: `apps/miroflow-agent/tests/canonical_v2/test_knowledge_serving_isolated.py` (extend the `_subject_consistency_*` fixture region :2938-3156)

**Interfaces:**
- Consumes: `_web_result_relevance_tier`, `_anchor_location_qualifier` (Task 1); `request.bound_entity_names`, `request.soft_context_subject` (existing).
- Produces: gate output ordering contract — `T0∪T1` first (stable), then T2, then T3; T4/T5 dropped when `len(kept) >= FLOOR`; backfill T2→T3→T4→T5 to FLOOR otherwise.

- [ ] **Step 1: Write the failing tests**

Reuse the existing fixture style (`_subject_consistency_request` /
`_subject_consistency_adapter` at :2938-3156 — read them first and construct
results directly with `_NormalizedWebResult` as in Task 1).

```python
def _gate(results, *, bound=("国际先进技术应用推进中心（深圳）",), soft=None):
    request = _subject_consistency_request(
        bound_entity_names=bound, soft_context_subject=soft,
    )  # adjust kwargs to the existing fixture's signature
    return _apply_web_subject_consistency(results=tuple(results), request=request)

def test_gate_drops_loose_alias_and_miss_when_kept_meets_floor():
    results = [
        _result("国际先进技术应用推进中心（深圳）揭牌"),                    # T1
        _result("河套深圳园区打造深港科技创新聚集地", providers=("bocha", "serper")),  # T0
        _result("国际先进技术应用推进中心（合肥）理事会扩容"),                # T3
        _result("南开国际先进研究院（深圳福田）在实验室参观交流中"),          # T4
        _result("两台国际先进水平手术的背后"),                              # T5
        _result("国际先进技术应用推进中心是由国家发展改革委指导的机构"),      # T2
    ]
    out = _gate(results)
    titles = [r.title for r in out]
    assert "南开国际先进研究院（深圳福田）在实验室参观交流中" not in titles  # T4 dropped
    assert "两台国际先进水平手术的背后" not in titles                        # T5 dropped
    assert titles.index("国际先进技术应用推进中心（合肥）理事会扩容") > titles.index(
        "国际先进技术应用推进中心是由国家发展改革委指导的机构"
    )  # T2 before T3
    assert set(titles[:2]) == {
        "国际先进技术应用推进中心（深圳）揭牌",
        "河套深圳园区打造深港科技创新聚集地",
    }  # T0∪T1 first

def test_gate_backfills_in_tier_order_below_floor():
    results = [
        _result("国际先进技术应用推进中心（深圳）揭牌"),  # T1 only, kept=1
        _result("国际先进技术应用推进中心（合肥）理事会扩容"),  # T3
        _result("国际先进技术应用推进中心由发改委指导"),      # T2
        _result("南开国际先进研究院（深圳福田）"),            # T4
        _result("完全无关"),                                 # T5
    ]
    out = [r.title for r in _gate(results)]
    assert out == [
        "国际先进技术应用推进中心（深圳）揭牌",
        "国际先进技术应用推进中心由发改委指导",
        "国际先进技术应用推进中心（合肥）理事会扩容",
    ]  # backfilled to FLOOR=3 in T2→T3 order; T4/T5 dropped

def test_gate_soft_subject_still_binds_and_qualifier_comes_from_soft_name():
    # Web-only path: no canonical bound names, soft subject carries （深圳）.
    results = [
        _result("南开国际先进研究院（深圳福田）"),  # T4 for the soft anchor
        _result("国际先进技术应用推进中心（深圳）依托粤港澳大湾区数字经济研究院建设"),  # T1
        _result("国际先进技术应用推进中心（合肥）"),  # T3
        _result("河套揭牌新闻", providers=("bocha", "serper")),  # T0
    ]
    out = [r.title for r in _gate(results, bound=(), soft="国际先进技术应用推进中心（深圳）")]
    assert "南开国际先进研究院（深圳福田）" not in out
    assert len(out) == 3

def test_gate_without_bound_names_is_passthrough():
    results = [_result("a"), _result("b", providers=("bocha", "serper"))]
    assert list(_gate(results, bound=(), soft=None)) == results
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/miroflow-agent && uv run pytest tests/canonical_v2/test_knowledge_serving_isolated.py -k "gate_drops or gate_backfills or gate_soft_subject or gate_without" -q --no-cov`
Expected: FAIL (current gate keeps 南开 as a hit / drops T2/T3 entirely at floor).

- [ ] **Step 3: Rewrite the gate**

Replace the body of `_apply_web_subject_consistency` (:833-868), keeping the signature and the soft-subject merge preamble (:838-848) unchanged:

```python
    anchor_qualifier = next(
        (
            qualifier
            for name in bound_entity_names
            if (
                qualifier := _anchor_location_qualifier(
                    name, str(getattr(request, "original_query", "") or "")
                )
            )
            is not None
        ),
        None,
    )
    tiered = [
        (
            _web_result_relevance_tier(
                result=result,
                bound_entity_names=bound_entity_names,
                anchor_qualifier=anchor_qualifier,
            ),
            index,
            result,
        )
        for index, result in enumerate(results)
    ]
    kept = [entry for entry in tiered if entry[0] in (0, 1)]
    related = [entry for entry in tiered if entry[0] in (2, 3)]
    suspect = [entry for entry in tiered if entry[0] == 4]
    missed = [entry for entry in tiered if entry[0] == 5]

    def unwrap(entries):
        return [result for _, _, result in entries]

    if len(kept) >= _WEB_SUBJECT_CONSISTENCY_FLOOR:
        # T4/T5 are the wrong-organization channels and drop out; T2/T3 are
        # same-organization background and stay, ordered after the anchor hits.
        return tuple(unwrap(kept) + unwrap(related))
    pool = unwrap(related) + unwrap(suspect) + unwrap(missed)
    return tuple(unwrap(kept) + pool[: _WEB_SUBJECT_CONSISTENCY_FLOOR - len(kept)])
```

(If `LaneRequest` has no `original_query` attribute the `getattr` default
handles it; the parens-derived qualifier still works — verify with
`grep -n "original_query" src/data_agents/canonical_v2/knowledge_read.py | head`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/miroflow-agent && uv run pytest tests/canonical_v2/test_knowledge_serving_isolated.py -k "gate_drops or gate_backfills or gate_soft_subject or gate_without" -q --no-cov`
Expected: PASS.

- [ ] **Step 5: Full file regression + lint + commit**

Run: `cd apps/miroflow-agent && uv run pytest tests/canonical_v2/test_knowledge_serving_isolated.py -q --no-cov && uv run ruff check src/data_agents/canonical_v2/knowledge_serving_isolated.py tests/canonical_v2/test_knowledge_serving_isolated.py`
Expected: PASS. Existing phase-1 gate tests may need expectation updates where they asserted binary hit/miss with alias collisions — update fixtures, not production logic, and call each change out in the commit message.

```bash
git add apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py apps/miroflow-agent/tests/canonical_v2/test_knowledge_serving_isolated.py
git commit -m "feat(canonical-v2): three-tier subject-consistency gate (branch/org/wrong-org)"
```

---

### Task 3: Qualifier pinning on the sync answer path

**Files:**
- Modify: `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py` (`_answer_mentions_anchor` :4148-4159, `_anchor_correction_message` :4162-4168, `_OpenAIProseRenderer.__call__` :4480-4543)
- Test: `apps/miroflow-agent/tests/canonical_v2/test_knowledge_serving_isolated.py` (renderer fixtures `_SequentialProseCompletions` / `_anchored_prose_result` at :1429-1595)

**Interfaces:**
- Consumes: `_anchor_location_qualifier`, `_org_name_stem` (Task 1); existing `_anchor_correction_name(result, active_anchor) -> str | None` (:4106).
- Produces:
  - `_answer_mentions_anchor(answer_text: str, anchor_name: str, *, location_qualifier: str | None = None) -> bool` — with a qualifier, requires the org stem AND the normalized qualifier to co-occur in the answer; without, phase-1 behavior.
  - `_anchor_correction_message(anchor_name: str, *, location_qualifier: str | None = None, reference_material: str | None = None) -> str` — `reference_material` is consumed by Task 7 (default None here; pass-through only).
  - `_anchor_location_qualifier_for_result(result: Any, anchor_name: str) -> str | None` — pulls `original_query` off the result for query co-occurrence.

- [ ] **Step 1: Write the failing tests**

```python
def test_mentions_anchor_with_qualifier_requires_branch_cooccurrence():
    assert _answer_mentions_anchor(
        "国际先进技术应用推进中心（深圳）依托粤港澳大湾区数字经济研究院建设。",
        "国际先进技术应用推进中心（深圳）",
        location_qualifier="深圳",
    )
    # Org mentioned, branch never pinned -> treated as off-anchor.
    assert not _answer_mentions_anchor(
        "国际先进技术应用推进中心（合肥）采用事业单位企业化运作模式。",
        "国际先进技术应用推进中心（深圳）",
        location_qualifier="深圳",
    )
    # No qualifier -> org-level mention passes (phase-1 behavior).
    assert _answer_mentions_anchor(
        "国际先进技术应用推进中心（合肥）采用事业单位企业化运作模式。",
        "国际先进技术应用推进中心",
    )

def test_correction_message_mentions_branch_when_qualified():
    msg = _anchor_correction_message(
        "国际先进技术应用推进中心（深圳）", location_qualifier="深圳",
    )
    assert "深圳" in msg and "不得反问" in msg and "明确归属" in msg
```

And a renderer-level test (reuse `_SequentialProseCompletions` / `_anchored_prose_result` from :1429-1595): first response answers only about 合肥, corrective retry mentions 深圳 → assert exactly 2 calls, final text is the retry, and the correction message contains 深圳. Mirror the existing `test_openai_prose_renderer_corrects_against_soft_subject_over_lookalike` shape.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/miroflow-agent && uv run pytest tests/canonical_v2/test_knowledge_serving_isolated.py -k "qualifier_requires_branch or correction_message_mentions_branch" -q --no-cov`
Expected: FAIL (`TypeError: unexpected keyword argument 'location_qualifier'`).

- [ ] **Step 3: Implement**

Extend `_answer_mentions_anchor` (:4148):

```python
def _answer_mentions_anchor(
    answer_text: str, anchor_name: str, *, location_qualifier: str | None = None,
) -> bool:
    searchable = _normalized_web_identity(answer_text)
    if location_qualifier is not None:
        stem = _org_name_stem(anchor_name)
        return bool(stem) and stem in searchable and location_qualifier in searchable
    for form in _web_identity_forms(anchor_name):
        if len(form) >= 3:
            if form in searchable:
                return True
        elif _web_identity_text_matches(form, searchable):
            return True
    return False
```

Extend `_anchor_correction_message` (:4162):

```python
def _anchor_correction_message(
    anchor_name: str,
    *,
    location_qualifier: str | None = None,
    reference_material: str | None = None,
) -> str:
    if location_qualifier is not None:
        instruction = (
            f"上一轮答案没有聚焦“{anchor_name}”作答，请重新回答："
            f"围绕“{anchor_name}”组织答案；该分部的公开信息不足时，"
            "基于已确认的信息概括作答，涉及其他分部的内容须明确归属，"
            "不得把其他分部的事实写入该分部；不得反问用户，不得要求用户补充信息；"
            "保持既定的返回格式不变。"
        )
    else:
        instruction = (
            f"上一轮答案没有围绕主体“{anchor_name}”作答，请重新回答："
            f"仅依据与“{anchor_name}”直接相关的输入信息组织答案；"
            "没有直接信息时，基于该主体可确认的信息概括作答。"
            "不得反问用户，不得要求用户补充信息；保持既定的返回格式不变。"
        )
    if reference_material:
        return (
            f"{instruction}\n以下是与该主体直接相关的补充材料，"
            f"优先采用其中与“{anchor_name}”直接相关的事实：\n{reference_material}"
        )
    return instruction
```

Add the result-level qualifier helper and wire it into `__call__` (:4520-4543):

```python
def _anchor_location_qualifier_for_result(result: Any, anchor_name: str) -> str | None:
    return _anchor_location_qualifier(
        anchor_name, str(getattr(result, "original_query", "") or "")
    )
```

In `__call__`, after `anchor_name = _anchor_correction_name(result, active_anchor)`:

```python
        qualifier = (
            None
            if anchor_name is None
            else _anchor_location_qualifier_for_result(result, anchor_name)
        )
        if anchor_name is None or _answer_mentions_anchor(
            _rendered_prose_answer_text(rendered), anchor_name,
            location_qualifier=qualifier,
        ):
            return rendered
        corrected = synthesize(
            [
                *messages,
                {
                    "role": "user",
                    "content": _anchor_correction_message(
                        anchor_name, location_qualifier=qualifier,
                    ),
                },
            ]
        )
        if not _answer_mentions_anchor(
            _rendered_prose_answer_text(corrected), anchor_name,
            location_qualifier=qualifier,
        ):
            raise ValueError("answer off-anchor")
        return corrected
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/miroflow-agent && uv run pytest tests/canonical_v2/test_knowledge_serving_isolated.py -k "qualifier_requires_branch or correction_message_mentions_branch or corrects_against" -q --no-cov`
Expected: PASS.

- [ ] **Step 5: Regression + lint + commit**

Run: `cd apps/miroflow-agent && uv run pytest tests/canonical_v2/test_knowledge_serving_isolated.py tests/canonical_v2/test_knowledge_answer_multiturn_contract.py -q --no-cov && uv run ruff check src/data_agents/canonical_v2/knowledge_serving_isolated.py tests/canonical_v2/test_knowledge_serving_isolated.py`
Expected: PASS.

```bash
git add apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py apps/miroflow-agent/tests/canonical_v2/test_knowledge_serving_isolated.py
git commit -m "feat(canonical-v2): pin qualified anchors to their branch on the sync path"
```

---

### Task 4: Stream final-answer correction (fail-open)

**Files:**
- Modify: `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py` (`_OpenAIProseRenderer.__call__` :4480-4543 refactor + `.stream` :4545-4612)
- Test: `apps/miroflow-agent/tests/canonical_v2/test_knowledge_serving_isolated.py`

**Interfaces:**
- Consumes: Task 3's upgraded `_answer_mentions_anchor` / `_anchor_correction_message` / `_anchor_location_qualifier_for_result`.
- Produces: `_OpenAIProseRenderer._synthesize_once(self, *, result, request_messages, claims, candidate_handles, handle_ids, active_anchor, displayed_set) -> str | ProseSynthesisResult` — the `synthesize` closure from `__call__` extracted into a shared private method (sync `__call__`, stream correction, and Task 7 all call it).
- Stream contract: on drift, ONE non-stream corrective retry; success → return corrected result (final `answer` event carries corrected text, frontend re-renders via the existing mismatch path); failure → **return the original streamed result** (fail-open, `logging.getLogger(__name__).info` marker). Never raises for off-anchor on the stream path (`knowledge_answer.py:2189-2192` rolls back and re-raises once chunks are published).

- [ ] **Step 1: Write the failing tests**

Model the stream fake on the existing sync fixture (`_SequentialProseCompletions`); the stream path iterates chunks, so give the fake a `stream=True` mode yielding objects with `.choices[0].delta.content` fragments (check how the current test suite fakes `stream` — grep `stream=True` in `test_knowledge_serving_isolated.py`; the pin-test for "stream does not retry" added in phase 1 is the template).

```python
def test_stream_correction_replaces_final_answer_on_drift(...):
    # stream chunks render "南开国际先进研究院（深圳福田）…" (off-anchor);
    # non-stream retry returns "国际先进技术应用推进中心（深圳）依托…".
    rendered = renderer.stream(result, on_chunk=lambda chunk: None)
    assert "国际先进技术应用推进中心（深圳）" in _rendered_prose_answer_text(rendered)
    assert fake_client.sync_create_calls == 1   # one corrective retry
    assert fake_client.stream_create_calls == 1

def test_stream_correction_failure_returns_original_streamed_answer(...):
    # retry also misses -> original streamed text is returned, no exception.
    rendered = renderer.stream(result, on_chunk=lambda chunk: None)
    assert "南开国际先进研究院" in _rendered_prose_answer_text(rendered)

def test_stream_on_anchor_makes_single_call(...):
    # on-anchor stream -> no correction call at all.
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/miroflow-agent && uv run pytest tests/canonical_v2/test_knowledge_serving_isolated.py -k "stream_correction or stream_on_anchor_single" -q --no-cov`
Expected: FAIL (stream currently returns the drifted text; no retry call).

- [ ] **Step 3: Implement**

3a. Extract `_synthesize_once` from `__call__` (:4490-4518) — move the closure body verbatim into a method with the locals as keyword params; `__call__` calls it twice (initial + retry) exactly as today.

3b. At the end of `stream` (:4606-4612), wrap the `_finalize_response` return:

```python
        finalized = self._finalize_response(
            answer_text=normalizer.finish(),
            selection=decoder.selection,
            claims=claims,
            candidate_handles=candidate_handles,
            handle_ids=handle_ids,
        )
        anchor_name = _anchor_correction_name(result, active_anchor)
        if anchor_name is None:
            return finalized
        qualifier = _anchor_location_qualifier_for_result(result, anchor_name)
        if _answer_mentions_anchor(
            _rendered_prose_answer_text(finalized), anchor_name,
            location_qualifier=qualifier,
        ):
            return finalized
        # Chunks are already published and irrevocable; correct the FINAL
        # answer with one non-stream retry. The SSE answer event then differs
        # from the streamed draft and the frontend re-renders (see
        # chat.html answer-event mismatch fallback). Failure is fail-open:
        # the original streamed result stands, matching phase-1 behavior.
        try:
            corrected = self._synthesize_once(
                result=result,
                request_messages=[
                    *messages,
                    {
                        "role": "user",
                        "content": _anchor_correction_message(
                            anchor_name, location_qualifier=qualifier,
                        ),
                    },
                ],
                claims=claims,
                candidate_handles=candidate_handles,
                handle_ids=handle_ids,
                active_anchor=active_anchor,
                displayed_set=displayed_set,
            )
        except Exception:  # provider/parse failure mid-correction: keep original
            _logger.info("stream off-anchor correction failed; keeping streamed answer")
            return finalized
        if _answer_mentions_anchor(
            _rendered_prose_answer_text(corrected), anchor_name,
            location_qualifier=qualifier,
        ):
            return corrected
        _logger.info("stream off-anchor correction missed; keeping streamed answer")
        return finalized
```

Add `import logging` / `_logger = logging.getLogger(__name__)` if absent.
Update the stream docstring (:4548-4553) to describe the final-answer
correction instead of "no off-anchor correction retry here".

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/miroflow-agent && uv run pytest tests/canonical_v2/test_knowledge_serving_isolated.py -k "stream_correction or stream_on_anchor_single or stream" -q --no-cov`
Expected: PASS — including the phase-1 pin "stream keeps a single provider call" UPDATED: rename/replace it to pin "single STREAM call; off-anchor adds one bounded non-stream correction call" (the behavior contract intentionally changed; call it out in the commit message).

- [ ] **Step 5: Regression + lint + commit**

Run: `cd apps/miroflow-agent && uv run pytest tests/canonical_v2/test_knowledge_serving_isolated.py tests/canonical_v2/test_knowledge_answer_multiturn_contract.py -q --no-cov && uv run ruff check src/data_agents/canonical_v2/knowledge_serving_isolated.py tests/canonical_v2/test_knowledge_serving_isolated.py`
Expected: PASS.

```bash
git add apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py apps/miroflow-agent/tests/canonical_v2/test_knowledge_serving_isolated.py
git commit -m "feat(canonical-v2): stream final-answer off-anchor correction (fail-open)"
```

---

### Task 5: Prompt-driven multi-branch guidance (§2b)

**Files:**
- Modify: `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py` (`_chat_request` payload/system content :4278-4359, prompt_version :4279)
- Test: `apps/miroflow-agent/tests/canonical_v2/test_knowledge_serving_isolated.py`

**Interfaces:**
- Consumes: `_anchor_location_qualifier`, `_org_name_stem`, `_evidence_branch_qualifiers` (Task 1).
- Produces: `_multi_branch_guidance_block(*, anchor_name: str, branch_qualifiers: tuple[str, ...]) -> str` — returns the injected situational text; `_multi_branch_context_for_result(result: Any) -> str | None` — None when guidance must NOT be injected (prompt byte-identical to today).

**Injection rules (from spec §2b):**

- Anchor name source: `context_receipt.soft_context_subject` if present, else `active_anchor.display_name` (mirrors `_anchor_correction_name` priority, minus the id checks).
- Inject only when `_anchor_location_qualifier(anchor_name, original_query) is None` (user gave no city) AND `_evidence_branch_qualifiers(org_stem, texts, anchor_qualifier=None)` is non-empty. Texts = claim texts from `result.claims` (each `.text`) — they carry the branch-qualified facts.
- Zero branches → no injection, prompt unchanged.

- [ ] **Step 1: Write the failing tests**

```python
def test_multi_branch_guidance_injected_with_detected_branches(...):
    # result whose claims mention 国际先进技术应用推进中心（合肥） and
    # 国际先进技术应用推进中心（大湾区）, anchor org-level (no qualifier).
    block = _multi_branch_context_for_result(result)
    assert block is not None
    assert "合肥" in block and "大湾区" in block
    assert "不得拒答" in block or "不得反问" in block
    assert "引导" in block or "注明" in block or "城市" in block

def test_multi_branch_guidance_absent_without_branch_evidence(...):
    # claims only mention the org unqualified -> None.
    assert _multi_branch_context_for_result(result) is None

def test_multi_branch_guidance_absent_when_user_named_a_city(...):
    # original_query contains the org name + 深圳 -> None (pin, don't guide).
    assert _multi_branch_context_for_result(result) is None

def test_chat_request_appends_guidance_block_and_bumps_version(...):
    messages, *_ = renderer._chat_request(result_with_branch_claims)
    system = messages[0]["content"]
    assert "合肥" in system
    assert '"prompt_version": "canonical-v2-prose-v16"' in messages[-1]["content"] \
        or "canonical-v2-prose-v16" in system  # depends where payload rides
```

(Adjust the last assertion to reality: the payload dict at :4278 is
JSON-serialized into a user message — grep the test file for
`prompt_version` to copy the existing assertion shape from the v15 bump.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/miroflow-agent && uv run pytest tests/canonical_v2/test_knowledge_serving_isolated.py -k "multi_branch" -q --no-cov`
Expected: FAIL (helpers missing / version still v15).

- [ ] **Step 3: Implement**

New helpers (near `_anchor_correction_message`):

```python
def _multi_branch_guidance_block(
    *, anchor_name: str, branch_qualifiers: tuple[str, ...],
) -> str:
    branches = "、".join(branch_qualifiers)
    return (
        f"情境说明：用户问的是机构级名称“{anchor_name}”，未指明城市。"
        f"输入信息显示该机构在以下地区设有分部：{branches}。"
        "要求：先完整回答用户的问题，总部及各分部的内容都是合法素材，"
        "但涉及具体分部的事实时必须明确归属（不得把一个分部的事实写成另一个分部的）；"
        "任何情况下不得拒答、不得反问。"
        "如果用户的需求可能特指某一分部，请在答案中自然地说明该机构在上述城市设有分部，"
        "并顺势引导用户在提问中注明想了解的城市——引导要与答案内容融为一体，"
        "不要使用模板式附录句；如果对话上下文已经表明用户聚焦某一分部，"
        "则直接按该分部作答，不再引导。"
    )


def _multi_branch_context_for_result(result: Any) -> str | None:
    context = getattr(result, "context_receipt", None)
    soft_subject = getattr(context, "soft_context_subject", None)
    anchor = getattr(context, "active_anchor", None)
    anchor_name = (
        soft_subject
        if isinstance(soft_subject, str) and soft_subject.strip()
        else getattr(anchor, "display_name", None)
    )
    if not isinstance(anchor_name, str) or not anchor_name.strip():
        return None
    original_query = str(getattr(result, "original_query", "") or "")
    if _anchor_location_qualifier(anchor_name, original_query) is not None:
        return None
    stem = _org_name_stem(anchor_name)
    if not stem:
        return None
    claim_texts = tuple(
        str(getattr(claim, "text", "") or "")
        for claim in getattr(result, "claims", ())
    )
    branches = _evidence_branch_qualifiers(
        org_stem=stem, texts=claim_texts, anchor_qualifier=None,
    )
    if not branches:
        return None
    return _multi_branch_guidance_block(
        anchor_name=anchor_name, branch_qualifiers=branches,
    )
```

Wire into `_chat_request`: after the `payload` dict (:4278-4327), before `messages = ...`:

```python
        guidance = _multi_branch_context_for_result(result)
```

and append to the system content string (:4331+):

```python
                        + ("" if guidance is None else f"\n{guidance}")
```

Bump `"prompt_version": "canonical-v2-prose-v15"` → `"canonical-v2-prose-v16"` (:4279). Update every test pinning v15 or the exact system-content suffix (grep `canonical-v2-prose-v15` across tests and source).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/miroflow-agent && uv run pytest tests/canonical_v2/test_knowledge_serving_isolated.py -k "multi_branch or prompt_version" -q --no-cov`
Expected: PASS.

- [ ] **Step 5: Regression + lint + commit**

Run: `cd apps/miroflow-agent && uv run pytest tests/canonical_v2/ -k "serving or answer or renderer or prose" -q --no-cov && uv run ruff check src/data_agents/canonical_v2/knowledge_serving_isolated.py tests/canonical_v2/test_knowledge_serving_isolated.py`
Expected: PASS.

```bash
git add apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py apps/miroflow-agent/tests/canonical_v2/test_knowledge_serving_isolated.py
git commit -m "feat(canonical-v2): prompt-driven multi-branch guidance (prompt_version v16)"
```

---

### Task 6: Authority-seeking query views (§2c)

**Files:**
- Modify: `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py` (`_serving_query_views` :1776-1870)
- Test: `apps/miroflow-agent/tests/canonical_v2/test_knowledge_serving_isolated.py`

**Interfaces:**
- Consumes: `_anchor_location_qualifier`, `QueryViewProposal` shape (:1792-1803 — note `soft_context_subject=request.soft_context_subject` is passed to every view).
- Produces: `_authority_seeking_view_texts(request: QueryPlanningRequest, original_query: str) -> tuple[str, ...]` — up to 2 texts (`{subject} 百度百科`, `{subject} 官网`), empty for non-qualifying anchors; `_serving_query_views` appends them as `producer_kind="authority_seeking"` views, deduplicated against existing view texts.

**Qualifying anchors:** the first name of `request.displayed_entity_names` or `request.soft_context_subject` whose `_anchor_location_qualifier(name, original_query)` is None. Org-level only: a user who already named the city keeps the phase-1 view set (pin, don't broaden).

- [ ] **Step 1: Write the failing tests**

```python
def test_authority_views_added_for_org_level_soft_subject():
    texts = _authority_seeking_view_texts(
        request=planning_request(soft="国际先进技术应用推进中心"),  # reuse existing fixture
        original_query="介绍一下国际先进技术应用推进中心",
    )
    assert texts == (
        "国际先进技术应用推进中心 百度百科",
        "国际先进技术应用推进中心 官网",
    )

def test_authority_views_absent_when_city_named():
    assert _authority_seeking_view_texts(
        request=planning_request(soft="国际先进技术应用推进中心（深圳）"),
        original_query="介绍一下国际先进技术应用推进中心（深圳）",
    ) == ()

def test_authority_views_absent_without_any_anchor():
    assert _authority_seeking_view_texts(
        request=planning_request(soft=None, names=()), original_query="深圳有哪些机器人公司",
    ) == ()

def test_serving_query_views_appends_authority_views_deduped(...):
    views = _serving_query_views(...)  # existing call shape; query_rewriter=None for determinism
    texts = [v.text for v in views]
    assert len(texts) == len(set(texts))
    assert "国际先进技术应用推进中心 百度百科" in texts
    assert all(v.soft_context_subject == request.soft_context_subject for v in views)
    assert [v.producer_kind for v in views if "百度百科" in v.text] == ["authority_seeking"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/miroflow-agent && uv run pytest tests/canonical_v2/test_knowledge_serving_isolated.py -k "authority_views" -q --no-cov`
Expected: FAIL (helper missing).

- [ ] **Step 3: Implement**

```python
def _authority_seeking_view_texts(
    *, request: QueryPlanningRequest, original_query: str,
) -> tuple[str, ...]:
    candidates = (
        *request.displayed_entity_names,
        *((request.soft_context_subject,) if request.soft_context_subject else ()),
    )
    for name in candidates:
        if not isinstance(name, str) or not name.strip():
            continue
        if _anchor_location_qualifier(name, original_query) is not None:
            continue
        stripped = name.strip()
        return (f"{stripped} 百度百科", f"{stripped} 官网")
    return ()
```

In `_serving_query_views` (:1776), after the deterministic view is built (:1792-1803) and before the rewrite/term views are appended, collect existing texts and append:

```python
    views = [deterministic]
    seen_texts = {deterministic.text}
    ...
    # after rewrite/term views are appended (keep existing order), before `return tuple(views)`:
    for text in _authority_seeking_view_texts(
        request=request, original_query=request.original_query,
    ):
        if text in seen_texts:
            continue
        seen_texts.add(text)
        views.append(
            QueryViewProposal(
                view_id=f"view:serving:{request.request_id}:authority:{len(views)}",
                kind="serving_search",
                text=text,
                original_query_sha256=request.original_query_sha256,
                retained_protected_values=retained_values,
                producer_kind="authority_seeking",
                producer_version=_SERVING_QUERY_REWRITER_VERSION,
                bound_entity_ids=request.displayed_entity_ids,
                bound_entity_names=request.displayed_entity_names,
                soft_context_subject=request.soft_context_subject,
            )
        )
```

Check the actual `views` accumulation order in the current code (:1804-1870: rewrites appended then term view inserted at index 1) — append authority views LAST so they never displace the deterministic or term views; the lane's per-view concurrency (:1034-1071) treats them as extra views.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/miroflow-agent && uv run pytest tests/canonical_v2/test_knowledge_serving_isolated.py -k "authority_views" -q --no-cov`
Expected: PASS.

- [ ] **Step 5: Regression + lint + commit**

Run: `cd apps/miroflow-agent && uv run pytest tests/canonical_v2/test_knowledge_serving_isolated.py tests/canonical_v2/test_knowledge_query_planning_contract.py -q --no-cov && uv run ruff check src/data_agents/canonical_v2/knowledge_serving_isolated.py tests/canonical_v2/test_knowledge_serving_isolated.py`
Expected: PASS. If planning-contract tests cap the number of views, update the contract constant deliberately and note it in the commit message.

```bash
git add apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py apps/miroflow-agent/tests/canonical_v2/test_knowledge_serving_isolated.py
git commit -m "feat(canonical-v2): authority-seeking query views for org-level anchors"
```

---

### Task 7: Correction-triggered tiered fetch (§3)

**Files:**
- Modify: `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py` (`_OpenAIProseRenderer.__init__` :4180-4183, `_EnvironmentProseRenderer` :4624+, `__call__` retry site, stream retry site from Task 4, builder wiring near :5019-5086)
- Test: `apps/miroflow-agent/tests/canonical_v2/test_knowledge_serving_isolated.py`

**Interfaces:**
- Consumes: `_web_identity_domain_matches` (:1934), `_web_identity_forms` (Task 1 split version), `_org_name_stem`; `result.citations` (shape at :4222-4225 — objects with `.evidence_id`, `.source_locator`, `.source_nature`).
- Produces:
  - `_OpenAIProseRenderer.__init__(self, *, client, model, extra_body, page_fetcher: Callable[[str], str | None] | None = None, fetch_timeout_seconds: float = 10.0)` — new optional params, defaults preserve current behavior.
  - `_fetch_anchor_reference_material(self, *, result: Any, anchor_name: str) -> str | None` — candidate selection + fetch + anti-echo guard, returns truncated text or None.
  - `_EnvironmentProseRenderer.__init__(self, *, page_fetcher=None)` — passes through to `_OpenAIProseRenderer` at :4629+; builder (`create_*` near :5019-5086, where `page_fetcher` already exists) passes `web_lane._page_fetcher` (see :3579 for the existing accessor).

**Rules (from spec §3):**

- Candidate URLs: `result.citations` where `source_nature == "current_web"`. Prefer the first URL with `_web_identity_domain_matches(anchor_name, url)`; else the first URL whose citation title (attr `.title`, may be absent — fall back to snippet split on `"："` like :1222) hits `_web_identity_forms(anchor_name)`. At most 1 URL; none → return None.
- Fetch: `self._page_fetcher(url)` wrapped in the renderer's existing executor pattern if one exists, else a direct call guarded by try/except — the fetcher itself is tiered and timeout-bounded (page_fetch.py); enforce `fetch_timeout_seconds` only if the codebase already has an executor with timeouts at this layer (`_page_fetch_timeout` precedent at :1095). If none fits cleanly, call directly and rely on the fetcher's internal timeouts (tier0 5s); do NOT build a new thread pool.
- Anti-echo guard: returned text must contain `_org_name_stem(anchor_name)`; else None.
- Truncate to 1200 chars (precedent `_enrich_with_page_text` :1106).
- Fail-open: any exception → None.

- [ ] **Step 1: Write the failing tests**

```python
def test_reference_material_fetched_from_domain_matched_url(...):
    fetcher = lambda url: "国际先进技术应用推进中心（深圳）是依托粤港澳大湾区数字经济研究院建设的机构。" * 30
    renderer = _OpenAIProseRenderer(
        client=fake_client, model="m", extra_body={}, page_fetcher=fetcher,
    )
    material = renderer._fetch_anchor_reference_material(
        result=result_with_citations, anchor_name="国际先进技术应用推进中心（深圳）",
    )
    assert material is not None and len(material) <= 1200
    assert "国际先进技术应用推进中心" in material

def test_reference_material_rejected_by_anti_echo_guard(...):
    fetcher = lambda url: "中国科学院深圳先进技术研究院简介……" * 50
    ... assert material is None

def test_reference_material_fail_open_on_fetch_error(...):
    def fetcher(url): raise RuntimeError("boom")
    ... assert material is None

def test_correction_message_carries_reference_material(...):
    # off-anchor -> retry message includes the fetched material (assert on the
    # recorded request messages of the fake client, second call).
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/miroflow-agent && uv run pytest tests/canonical_v2/test_knowledge_serving_isolated.py -k "reference_material" -q --no-cov`
Expected: FAIL (params/method missing).

- [ ] **Step 3: Implement**

3a. `__init__` params + `_fetch_anchor_reference_material` (place next to the correction helpers). Candidate extraction:

```python
    def _fetch_anchor_reference_material(
        self, *, result: Any, anchor_name: str,
    ) -> str | None:
        if self._page_fetcher is None:
            return None
        citations = tuple(
            citation
            for citation in getattr(result, "citations", ())
            if getattr(citation, "source_nature", None) == "current_web"
        )
        if not citations:
            return None
        def locator(citation: Any) -> str:
            return str(getattr(citation, "source_locator", "") or "")
        chosen = next(
            (c for c in citations if _web_identity_domain_matches(anchor_name, locator(c))),
            None,
        )
        if chosen is None:
            forms = _web_identity_forms(anchor_name)
            def title_hits(citation: Any) -> bool:
                raw = str(getattr(citation, "title", "") or getattr(citation, "snippet", "") or "")
                head = raw.partition("：")[0]
                searchable = _normalized_web_identity(head)
                return any(_web_identity_text_matches(f, searchable) for f in forms)
            chosen = next((c for c in citations if title_hits(c)), None)
        if chosen is None:
            return None
        try:
            text = self._page_fetcher(locator(chosen))
        except Exception:
            _logger.info("anchor reference fetch failed", exc_info=True)
            return None
        if not isinstance(text, str) or not text.strip():
            return None
        stem = _org_name_stem(anchor_name)
        if not stem or stem not in _normalized_web_identity(text):
            return None
        return text.strip()[:1200]
```

3b. Wire into both retry sites (sync `__call__` and stream correction from Task 4): build `reference = self._fetch_anchor_reference_material(result=result, anchor_name=anchor_name)` immediately before the corrective `_synthesize_once`, pass `reference_material=reference` into `_anchor_correction_message(...)` (Task 3 signature already accepts it).

3c. `_EnvironmentProseRenderer.__init__` gains `page_fetcher=None` and stores it; `_configured_renderer` (:4629) passes it into `_OpenAIProseRenderer(...)`. Find the builder site constructing `_EnvironmentProseRenderer` (grep `_EnvironmentProseRenderer(` in serving; near :5019-5086) and pass the serving stack's `page_fetcher` through (the same object handed to `_DualWebLaneAdapter`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/miroflow-agent && uv run pytest tests/canonical_v2/test_knowledge_serving_isolated.py -k "reference_material or correction" -q --no-cov`
Expected: PASS.

- [ ] **Step 5: Regression + lint + commit**

Run: `cd apps/miroflow-agent && uv run pytest tests/canonical_v2/ -k "serving or answer or renderer or prose" -q --no-cov && uv run ruff check src/data_agents/canonical_v2/knowledge_serving_isolated.py tests/canonical_v2/test_knowledge_serving_isolated.py`
Expected: PASS.

```bash
git add apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py apps/miroflow-agent/tests/canonical_v2/test_knowledge_serving_isolated.py
git commit -m "feat(canonical-v2): correction-triggered tiered fetch with anti-echo guard"
```

---

### Task 8: End-to-end verification + production deploy

**Files:**
- No production code. Scratch files under `/tmp` only (cleaned up at the end).

- [ ] **Step 1: Local production-replica verification**

Follow the established retest procedure (documented in `.agents/runs/restart-18188/restart-18188.sh` header):

```bash
# 1. Copy the restart script and change the port (18188 -> 39878)
sed 's/ 18188 / 39878 /' .agents/runs/restart-18188/restart-18188.sh > /tmp/retest2-serve.sh
# 2. Copy the index (Milvus-Lite single-process lock) and bind-mount over the original path
cp -a /var/tmp/mirothinker-canonical-v2-s12f/index-v1 /var/tmp/retest2-index-v1
unshare -Urm --propagation private bash -c \
  'mount --bind /var/tmp/retest2-index-v1 /var/tmp/mirothinker-canonical-v2-s12f/index-v1 && exec bash /tmp/retest2-serve.sh' \
  >> /tmp/retest2-serve.log 2>&1 &
# 3. Wait for health
until curl -s -m 3 http://127.0.0.1:39878/api/health | grep -q ok; do sleep 5; done
```

Then run three sessions against `POST http://127.0.0.1:39878/api/chat/stream` (cookie jar per session, `curl -N`, 150s+ timeout):

1. **Badcase (qualified):** `介绍一下 国际先进技术应用推进中心（深圳）` → `有没有更详细的信息` → `能再具体一点吗`
   - PASS criteria: turn 2/3 answers stay on the 深圳 branch; no SIAT/南开 as answer subject; no refusal; turn 2/3 `retrieval_done.web_items` tops contain 切题 results (河套/百度百科/政府), 南开 (T4) absent when kept≥3.
2. **Unqualified multi-branch:** `介绍一下国际先进技术应用推进中心` (fresh cookie)
   - PASS criteria: full org-level answer (never a refusal); branch facts correctly attributed; answer naturally notes the branches (合肥/南沙/深圳 per evidence) and invites naming a city; not a boilerplate appendix.
3. **Control (canonical entity):** `介绍一下深圳市普渡科技有限公司` → `有没有更详细的信息`
   - PASS criteria: no regression, normal deepening.

Record SSE dumps under `/tmp/phase2_{badcase,unqualified,control}_t*.sse`. Verdicts are per-turn; LLM nondeterminism means a borderline turn is retried once before being called a failure.

- [ ] **Step 2: Full regression**

```bash
cd apps/miroflow-agent && uv run pytest tests/canonical_v2/ -q --no-cov -n 2 -p no:randomly
cd apps/admin-console && uv run pytest tests/test_canonical_v2_chat_http_adapter.py tests/test_chat_anchor_clarification.py tests/test_canonical_v2_referent_history.py -q
cd apps/admin-console && node --test tests/chat_ui_behavior_test.mjs
```

Expected: green except the known baseline `test_s11b_sanctioned_entrypoints_classify_and_exclude_legacy_consumers` (fails on HEAD).

- [ ] **Step 3: Deploy**

```bash
PID=$(pgrep -f "\.venv/bin/python3.*serve_s12e_port.py 18188" | head -1)
kill -TERM "$PID"
# wait for the python AND the milvus_lite child to exit before relaunch
while kill -0 "$PID" 2>/dev/null; do sleep 1; done
while ps -eo args | grep "milvus_lite.*index-v1" | grep -v grep >/dev/null; do sleep 2; done
cd /home/longxiang/MiroThinker/.worktrees/canonical-v2-s11-consolidation
setsid nohup bash .agents/runs/restart-18188/restart-18188.sh >> .agents/runs/restart-18188/restart-18188.log 2>&1 < /dev/null &
until curl -s -m 3 http://127.0.0.1:18188/api/health | grep -q ok; do sleep 5; done
```

Then production smoke: repeat the badcase turn 1+2 and the unqualified query against `http://127.0.0.1:18188/api/chat/stream`; verify PASS criteria as in Step 1.

- [ ] **Step 4: Cleanup**

Stop the retest service, `rm -rf /var/tmp/retest2-index-v1 /tmp/retest2-* /tmp/phase2_*`. Confirm production 18188 healthy and untouched by the retest namespace.

---

### Task 9: OpenSpec backfill

**Files:**
- Create: `openspec/changes/followup-subject-consistency/proposal.md`
- Create: `openspec/changes/followup-subject-consistency/specs/`
- Create: `openspec/changes/followup-subject-consistency/tasks.md`
- Create: `openspec/changes/followup-subject-consistency/acceptance.md`
- Create: `openspec/changes/followup-subject-consistency/design.md`
- Create: `.agents/runs/followup-subject-consistency/verification-contract.md`
- Create: `.agents/runs/followup-subject-consistency/verification.md`

**Interfaces:**
- Consumes: deployed commits `27d0231`, `a9b695b`, `50c4f3a` (phase 1) and Tasks 1-8 (phase 2); the design spec `docs/superpowers/specs/2026-08-12-web-answer-subject-consistency-phase2-design.md`; follow-up record `.agents/runs/followups/2026-08-11-web-lane-subject-consistency.md`.

- [ ] **Step 1: Write the artifacts (English, per AGENTS.md §9)**

`proposal.md` — one change covering the follow-up/subject-consistency arc:
problem (context loss on elaboration follow-ups; wrong-organization drift via
Bocha lookalikes; refusal-shaped degradation), the shipped phase-1 slices
(marked DEPLOYED with commit ids), and phase-2 slices (this plan).

`specs/` — delta for capability `canonical-v2-chat`: follow-up continuation
semantics, soft subject anchor, dual-provider corroboration + three-tier
consistency gate, qualifier pinning, multi-branch guidance, authority views,
correction fetch, never-refuse fallbacks. One `## ADDED Requirement` block per
behavior with `#### Scenario:` bullets.

`design.md` — point to the phase-2 spec; summarize phase-1 decisions.

`tasks.md` — checklist with phase-1 items pre-checked (with commit ids) and
phase-2 items mirroring Tasks 1-8 of this plan.

`acceptance.md` — the e2e PASS criteria from Task 8 Step 1 verbatim, plus the
regression commands from Task 8 Step 2.

`.agents/runs/.../verification-contract.md` + `verification.md` — RED/GREEN
evidence references (per-task test names) and the e2e/production smoke logs'
locations.

- [ ] **Step 2: Validate + commit**

Run: `cd /home/longxiang/MiroThinker/.worktrees/canonical-v2-s11-consolidation && git add openspec/changes/followup-subject-consistency .agents/runs/followup-subject-consistency && git commit -m "docs(openspec): backfill follow-up subject-consistency change artifacts"`
If an openspec CLI validator is configured in the repo (`openspec validate` — check `pyproject.toml`/justfile first), run it before committing.

---

## Self-review notes (planner)

- Spec coverage: §1→Tasks 1-2, §2→Tasks 3-4, §2b→Task 5, §2c→Task 6, §3→Task 7, testing/e2e→Task 8, OpenSpec→Task 9. No gaps.
- Type consistency: `_anchor_location_qualifier` / `_org_name_stem` / `_evidence_branch_qualifiers` / `_web_result_relevance_tier` / `_web_identity_full_name_forms` / `_web_identity_compact_aliases` / `_multi_branch_context_for_result` / `_multi_branch_guidance_block` / `_authority_seeking_view_texts` / `_fetch_anchor_reference_material` / `_synthesize_once` are used consistently across tasks; `_anchor_correction_message(anchor_name, *, location_qualifier=None, reference_material=None)` is defined in Task 3 and consumed in Tasks 4 and 7.
- Deliberate spec refinements recorded in-plan: stream retry failure returns the original streamed result instead of raising (knowledge_answer.py:2189-2192 rollback constraint); limitations marker replaced by a log marker on the stream path (no contract change).
