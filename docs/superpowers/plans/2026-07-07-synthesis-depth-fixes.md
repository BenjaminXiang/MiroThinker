# Synthesis-Depth Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface rich facts for list entities, reformulate knowledge queries before web search, and make synthesis deterministic — lifting true accuracy from 9/19 (47%) toward ~12-13/19 (~60-70%).

**Architecture:** Three independent, reversible edits to the chat synthesis path in `apps/admin-console/backend/api/chat.py`. Fix 3 (temperature) is a one-line determinism fix. Fix 1 fetches rich facts for the top list entities and extends both list render paths to surface them. Fix 2 adds an LLM-backed query reformulation that retries web search only when a `qa`-intent query returns zero results. Pure helpers are unit-tested; integration behavior is eval-verified (CLAUDE.md §8 — synthesis/RAG work is eval-first, not unit-TDD).

**Tech Stack:** Python 3.12, uv, pytest, OpenAI SDK (local qwen3.6 endpoint), FastAPI TestClient, the existing `eval_true_accuracy.py` LLM-judge.

**Spec:** `docs/superpowers/specs/2026-07-07-synthesis-depth-fixes-design.md`
**Contract decision:** doc-as-contract (option c) — `openspec/` does not exist on this branch; the spec doc is the behavior contract.

---

## File Structure

- **Modify:** `apps/admin-console/backend/api/chat.py`
  - Fix 3: `_call_gemma_synthesis` (line ~3840) — add `temperature=0`.
  - Fix 1: new helpers `_compact_prof_rich` / `_compact_company_rich` / `_enrich_list_entities` (after `_company_rich_facts`, ~line 2263); call `_enrich_list_entities` in `_build_chat_response` (after line 3972); extend render Path A (lines 3633-3650) and Path B (lines 3747-3777) in `_build_evidence_blocks`.
  - Fix 2: new `_web_search_to_rows` + `_reformulate_query_for_search` helpers (near `_call_gemma_synthesis`); move `intent` computation earlier in `_build_chat_response`; rewrite the web-search block (lines 3978-3998) to retry on 0 results.
- **Create:** `apps/admin-console/tests/test_chat_synthesis_depth.py` — unit tests for the pure helpers + render + reformulation (mock LLM client).
- **No schema, no migration, no data, no public-API change.**

---

## Task 1: Fix 3 — Synthesis `temperature=0`

Determinism fix. Per CLAUDE.md §8, synthesis-call behavior is eval-verified, not unit-tested — `_call_gemma_synthesis` constructs its own OpenAI client internally, so a unit test would require an injection refactor that is out of scope for a one-liner. GREEN = eval stability (Task 4).

**Files:**
- Modify: `apps/admin-console/backend/api/chat.py:3840-3853`

- [ ] **Step 1: Add `temperature=0` to the synthesis call**

Find this block in `_call_gemma_synthesis` (chat.py:3840):

```python
    response = client.chat.completions.create(
        model=llm_settings["local_llm_model"],
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"用户问题: {query}\n\n"
                    f"证据（请引用 [N]）:\n{evidence_text}"
                ),
            },
        ],
        extra_body=_chat_synthesis_extra_body(llm_settings["local_llm_model"]),
    )
```

Replace with (added `temperature=0,`):

```python
    response = client.chat.completions.create(
        model=llm_settings["local_llm_model"],
        temperature=0,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"用户问题: {query}\n\n"
                    f"证据（请引用 [N]）:\n{evidence_text}"
                ),
            },
        ],
        extra_body=_chat_synthesis_extra_body(llm_settings["local_llm_model"]),
    )
```

- [ ] **Step 2: Sanity-import (no syntax break)**

Run (unset proxies per env-proxy-bypass memory):
```bash
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
cd /home/longxiang/MiroThinker/apps/admin-console && UV_OFFLINE=1 uv run --no-sync python -c "from backend.api.chat import _call_gemma_synthesis; print('ok')"
```
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add apps/admin-console/backend/api/chat.py
git commit -m "fix(synthesis): set temperature=0 for deterministic chat answers

_call_gemma_synthesis had no temperature → LLM default (~0.7) → identical
queries produced different answers (qid11 flapped 0.00↔1.00). Eval-verified
in a later slice (CLAUDE.md §8: synthesis is eval-first, not unit-TDD).

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 2: Fix 1 — List-entity enrichment

Surface rich facts (flagship product, top award, research summary) for the top list entities, in both render paths. One commit at the end.

**Files:**
- Modify: `apps/admin-console/backend/api/chat.py` — new helpers (~line 2263), call site (~line 3972), render Path A (3633-3650) + Path B (3747-3777).
- Create: `apps/admin-console/tests/test_chat_synthesis_depth.py`

- [ ] **Step 1: Write the failing unit tests**

Create `apps/admin-console/tests/test_chat_synthesis_depth.py`:

```python
from __future__ import annotations

from backend.api.chat import (
    _build_evidence_blocks,
    _compact_company_rich,
    _compact_prof_rich,
    _enrich_list_entities,
)


# --- _compact_prof_rich ---
def test_compact_prof_rich_picks_top_award_and_summary() -> None:
    facts = {
        "awards": ["国家杰青", "教育部一等奖"],
        "profile_summary": "从事具身智能与强化学习研究",
    }
    out = _compact_prof_rich(facts)
    assert "国家杰青" in out
    assert "具身智能" in out


def test_compact_prof_rich_empty_returns_empty() -> None:
    assert _compact_prof_rich({}) == ""


def test_compact_prof_rich_falls_back_to_education() -> None:
    out = _compact_prof_rich({"education": ["清华大学博士"]})
    assert "清华大学" in out


# --- _compact_company_rich ---
def test_compact_company_rich_picks_product_and_team() -> None:
    facts = {
        "company_products": ["PANVIS-A 血管介入手术机器人"],
        "company_team": ["郭书祥（创始人/董事长）"],
    }
    out = _compact_company_rich(facts)
    assert "PANVIS-A" in out
    assert "郭书祥" in out


def test_compact_company_rich_empty_returns_empty() -> None:
    assert _compact_company_rich({}) == ""


# --- _enrich_list_entities (DI'd fetchers, no DB) ---
def test_enrich_list_entities_attaches_rich_summary() -> None:
    payload = {
        "matched_professors": [
            {"professor_id": "p1"},
            {"professor_id": "p2"},  # empty facts → no key
        ],
        "matched_objects": [{"company_id": "c1"}, {"id": "paper-x"}],  # 2nd has no company_id
    }
    prof_fn = lambda conn, pid: {"awards": ["杰青"]} if pid == "p1" else {}
    company_fn = lambda conn, cid: {"company_products": ["PANVIS-A"]}
    _enrich_list_entities(
        payload, conn=object(), prof_rich_fn=prof_fn, company_rich_fn=company_fn
    )
    assert "rich_summary" in payload["matched_professors"][0]
    assert "杰青" in payload["matched_professors"][0]["rich_summary"]
    assert "rich_summary" not in payload["matched_professors"][1]
    assert "PANVIS-A" in payload["matched_objects"][0]["rich_summary"]
    assert "rich_summary" not in payload["matched_objects"][1]


# --- _build_evidence_blocks surfaces rich_summary in BOTH list paths ---
def test_build_evidence_blocks_surfaces_prof_list_rich_path_a() -> None:
    payload = {
        "matched_professors": [
            {
                "professor_id": "p1",
                "canonical_name": "张三",
                "institution": "清华大学",
                "rich_summary": "奖项：国家杰青",
            }
        ]
    }
    text, _ = _build_evidence_blocks(payload)
    assert "张三" in text
    assert "国家杰青" in text  # rich surfaced, not just name+institution


def test_build_evidence_blocks_surfaces_company_list_rich_path_b() -> None:
    payload = {
        "matched_objects": [
            {
                "company_id": "c1",
                "canonical_name": "爱博合创",
                "rich_summary": "产品：PANVIS-A",
            }
        ]
    }
    text, _ = _build_evidence_blocks(payload)
    assert "爱博合创" in text
    assert "PANVIS-A" in text
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/longxiang/MiroThinker/apps/admin-console && UV_OFFLINE=1 uv run --no-sync pytest tests/test_chat_synthesis_depth.py -q
```
Expected: FAIL with `ImportError: cannot import name '_compact_prof_rich'` (helpers + `_enrich_list_entities` don't exist yet).

- [ ] **Step 3: Add the three helpers**

Insert after `_company_rich_facts` ends (chat.py:2263, right before `def _paper_rich_fields`):

```python
def _compact_prof_rich(facts: dict[str, Any]) -> str:
    """Compact one-line rich-fact string for a professor list entry.

    Picks the 1-2 highest-signal facts (top award + research summary) so a list
    query surfaces depth without token bloat. Returns '' if nothing notable.
    """
    if not facts:
        return ""
    parts: list[str] = []
    awards = facts.get("awards") or []
    if awards:
        parts.append(f"奖项：{str(awards[0])[:80]}")
    summary = (facts.get("profile_summary") or "").strip()
    if summary:
        parts.append(f"研究概要：{summary[:100]}")
    if not parts:
        edu = facts.get("education") or []
        if edu:
            parts.append(f"教育：{str(edu[0])[:80]}")
    return "；".join(parts)[:200]


def _compact_company_rich(facts: dict[str, Any]) -> str:
    """Compact one-line rich-fact string for a company list entry.

    Picks flagship product + founder so a list query surfaces depth.
    """
    if not facts:
        return ""
    parts: list[str] = []
    products = facts.get("company_products") or []
    if products:
        parts.append(f"产品：{str(products[0])[:100]}")
    team = facts.get("company_team") or []
    if team:
        parts.append(f"团队：{str(team[0])[:80]}")
    return "；".join(parts)[:200]


def _enrich_list_entities(
    structured_payload: dict[str, Any],
    *,
    conn: Any,
    prof_rich_fn: Any = _prof_rich_profile_facts,
    company_rich_fn: Any = _company_rich_facts,
) -> None:
    """Attach a compact `rich_summary` to the top list entities (in place).

    List queries return matched_professors / matched_objects with name+snippet
    only; the rich-fact fetchers were never called for them, so synthesis saw
    shallow detail. This fetches rich facts for the top-3 of each and stores a
    compact one-liner the list renderers surface. Fetchers are injectable for
    unit testing (no DB needed).
    """
    for prof in (structured_payload.get("matched_professors") or [])[:3]:
        if not isinstance(prof, dict):
            continue
        pid = prof.get("professor_id")
        if not pid:
            continue
        compact = _compact_prof_rich(prof_rich_fn(conn, str(pid)))
        if compact:
            prof["rich_summary"] = compact
    for obj in (structured_payload.get("matched_objects") or [])[:3]:
        if not isinstance(obj, dict):
            continue
        cid = obj.get("company_id")
        if not cid:
            continue  # only companies have a rich-facts fetcher; papers/patents skipped
        compact = _compact_company_rich(company_rich_fn(conn, str(cid)))
        if compact:
            obj["rich_summary"] = compact
```

- [ ] **Step 4: Call `_enrich_list_entities` in `_build_chat_response`**

In `_build_chat_response`, after the single-entity paper block (chat.py:3968-3972):

```python
    paper_id_for_rich = structured_payload.get("paper_id")
    if paper_id_for_rich:
        paper_rich = _paper_rich_fields(conn, str(paper_id_for_rich))
        if paper_rich:
            structured_payload.update(paper_rich)
```

Add immediately after it:

```python
    # List-entity enrichment (Fix1): fetch rich facts for the top list entities so
    # the list render surfaces depth (flagship product, top award), not just name.
    _enrich_list_entities(structured_payload, conn=conn)
```

- [ ] **Step 5: Extend render Path A (matched_professors) to surface rich_summary**

In `_build_evidence_blocks`, the matched_professors loop (chat.py:3635-3649). Current:

```python
        for prof in matched_professors[:10]:
            topics = prof.get("matched_topics") or []
            topic_text = f"，匹配方向：{'、'.join(topics[:3])}" if topics else ""
            marker = _append_evidence_block(
                blocks=blocks,
                citation_map=citation_map,
                marker=marker,
                kind="professor",
                summary=(
                    f"{prof.get('canonical_name') or '姓名未知'}，"
                    f"{prof.get('institution') or '机构未知'}"
                    f"{topic_text}"
                ),
                evidence_id=prof["professor_id"],
            )
```

Replace with:

```python
        for prof in matched_professors[:10]:
            topics = prof.get("matched_topics") or []
            topic_text = f"，匹配方向：{'、'.join(topics[:3])}" if topics else ""
            rich_text = ""
            rich = (prof.get("rich_summary") or "").strip()
            if rich:
                rich_text = f"，亮点：{rich}"
            marker = _append_evidence_block(
                blocks=blocks,
                citation_map=citation_map,
                marker=marker,
                kind="professor",
                summary=(
                    f"{prof.get('canonical_name') or '姓名未知'}，"
                    f"{prof.get('institution') or '机构未知'}"
                    f"{topic_text}{rich_text}"
                ),
                evidence_id=prof["professor_id"],
            )
```

- [ ] **Step 6: Extend render Path B (matched_objects) to surface rich_summary**

In `_build_evidence_blocks`, the list_rows loop (chat.py:3764). Current:

```python
        summary = f"{name}：{detail}" if detail else str(name)
        marker = _append_evidence_block(
            blocks=blocks,
            citation_map=citation_map,
            marker=marker,
            kind=str(item.get("type") or "evidence"),
            summary=summary[:200],
            evidence_id=str(
                item.get("id")
                or item.get("professor_id")
                or item.get("company_id")
                or name
            ),
        )
```

Replace with:

```python
        summary = f"{name}：{detail}" if detail else str(name)
        rich = (item.get("rich_summary") or "").strip()
        if rich:
            summary = f"{summary}（亮点：{rich}）"
        marker = _append_evidence_block(
            blocks=blocks,
            citation_map=citation_map,
            marker=marker,
            kind=str(item.get("type") or "evidence"),
            summary=summary[:320],
            evidence_id=str(
                item.get("id")
                or item.get("professor_id")
                or item.get("company_id")
                or name
            ),
        )
```

(Note: cap raised 200→320 only on this list block so the appended rich fact is not truncated; profile blocks are unaffected.)

- [ ] **Step 7: Run the unit tests to verify they pass**

```bash
cd /home/longxiang/MiroThinker/apps/admin-console && UV_OFFLINE=1 uv run --no-sync pytest tests/test_chat_synthesis_depth.py -q
```
Expected: PASS (all tests).

- [ ] **Step 8: Commit**

```bash
git add apps/admin-console/backend/api/chat.py apps/admin-console/tests/test_chat_synthesis_depth.py
git commit -m "feat(synthesis): surface rich facts for list entities (generation depth)

List queries returned matched_professors/matched_objects with name+snippet
only; the rich-fact fetchers (_prof_rich_profile_facts/_company_rich_facts)
were never called for them, so synthesis emitted shallow list answers
(qid3/9/21/27 failed on completeness). Now fetches rich facts for the top-3
list entities and surfaces a compact one-liner in both list render paths.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 3: Fix 2 — LLM query reformulation for web search

Rewrite over-contextualized knowledge queries into search keywords via the local qwen3.6 LLM, retry web search once when the first call returns zero results. Synthesis keeps the raw user query. One commit at the end.

**Files:**
- Modify: `apps/admin-console/backend/api/chat.py` — new `_web_search_to_rows` + `_reformulate_query_for_search` (near `_call_gemma_synthesis`, ~line 3820); move `intent` computation earlier; rewrite web-search block (3978-3998).
- Modify: `apps/admin-console/tests/test_chat_synthesis_depth.py` — add reformulation + web-block tests.

- [ ] **Step 1: Write the failing tests**

Append to `apps/admin-console/tests/test_chat_synthesis_depth.py`:

```python
from backend.api.chat import _reformulate_query_for_search, _web_search_to_rows


# --- _web_search_to_rows ---
class _FakeProvider:
    def __init__(self, organic: list[dict]) -> None:
        self._organic = organic
        self.queries: list[str] = []

    def search(self, query: str) -> dict:
        self.queries.append(query)
        return {"organic": self._organic}


def test_web_search_to_rows_normalizes_organic() -> None:
    provider = _FakeProvider([{"link": "http://a", "title": "A", "snippet": "s"}])
    rows = _web_search_to_rows(provider, "q")
    assert rows == [
        {"id": "http://a", "title": "A", "snippet": "s", "url": "http://a", "type": "web"}
    ]
    assert provider.queries == ["q"]


def test_web_search_to_rows_empty() -> None:
    provider = _FakeProvider([])
    assert _web_search_to_rows(provider, "q") == []


# --- _reformulate_query_for_search (mock LLM client) ---
class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = _FakeMessage(content)


class _FakeCompletion:
    def __init__(self, content: str, capture: dict) -> None:
        self._content = content
        self._capture = capture

    def create(self, **kwargs):  # type: ignore[no-untyped-def]
        self._capture["kwargs"] = kwargs
        return type("Resp", (), {"choices": [_FakeChoice(self._content)]})()


class _FakeChat:
    def __init__(self, content: str, capture: dict) -> None:
        self.completions = _FakeCompletion(content, capture)


class _FakeOpenAIClient:
    def __init__(self, content: str) -> None:
        self.capture: dict = {}
        self.chat = _FakeChat(content, self.capture)


def test_reformulate_returns_keywords_and_temperature_zero() -> None:
    fake = _FakeOpenAIClient("具身智能 真实数据采集 遥操作 动捕数据")
    out = _reformulate_query_for_search(
        "在真实数据采集路线中，有哪些具体方式", client_factory=lambda: fake
    )
    assert "遥操作" in out
    assert fake.capture["kwargs"].get("temperature") == 0


def test_reformulate_failure_returns_empty() -> None:
    class _BoomClient(_FakeOpenAIClient):
        def __init__(self) -> None:
            super().__init__("")

        class chat:  # noqa: N801
            class completions:
                @staticmethod
                def create(**kwargs):  # type: ignore[no-untyped-def]
                    raise RuntimeError("LLM down")

    out = _reformulate_query_for_search("q", client_factory=lambda: _BoomClient())
    assert out == ""
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/longxiang/MiroThinker/apps/admin-console && UV_OFFLINE=1 uv run --no-sync pytest tests/test_chat_synthesis_depth.py -q
```
Expected: FAIL with `ImportError: cannot import name '_reformulate_query_for_search'`.

- [ ] **Step 3: Add `_web_search_to_rows` and `_reformulate_query_for_search`**

Insert just before `def _call_gemma_synthesis` (chat.py:3823):

```python
def _web_search_to_rows(web_provider: Any, query: str) -> list[dict[str, Any]]:
    """Run one web search and normalize to evidence-row dicts (id/title/snippet/url/type).
    Raises propagate to the caller, which wraps in best-effort try/except."""
    payload = web_provider.search(query)
    organic = payload.get("organic") or payload.get("results") or []
    rows: list[dict[str, Any]] = []
    for item in organic[:10]:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "id": item.get("link") or item.get("url") or f"web-{len(rows)}",
                "title": (item.get("title") or "").strip(),
                "snippet": (item.get("snippet") or "").strip(),
                "url": item.get("link") or item.get("url") or "",
                "type": "web",
            }
        )
    return rows


_SEARCH_REFORMULATE_SYSTEM = (
    "你是一个搜索查询改写器。将用户问题改写为适合网络搜索的中文关键词组合："
    "保留核心意图，去除上下文引用（如'在...路线中'、'有哪些具体方式'），"
    "补充相关领域术语。只输出关键词，用空格分隔，不要解释，不要标点。"
)


def _reformulate_query_for_search(
    query: str,
    *,
    client_factory: Any = None,
    timeout: float = 8.0,
) -> str:
    """Rewrite a knowledge sub-question into search-friendly keywords via the local
    LLM (qwen3.6, free). Used ONLY as the web-search query; synthesis keeps the raw
    user query. Returns '' on any failure (caller falls through to local-only —
    best-effort contract, CLAUDE.md §5)."""
    _clear_proxy_env()
    llm_settings = resolve_professor_llm_settings(None)
    api_key = llm_settings.get("local_llm_api_key")
    if not api_key:
        return ""
    if client_factory is not None:
        client = client_factory()
    else:
        client = OpenAI(
            base_url=llm_settings["local_llm_base_url"],
            api_key=api_key,
            timeout=timeout,
        )
    try:
        response = client.chat.completions.create(
            model=llm_settings["local_llm_model"],
            temperature=0,
            messages=[
                {"role": "system", "content": _SEARCH_REFORMULATE_SYSTEM},
                {"role": "user", "content": query},
            ],
            extra_body=_chat_synthesis_extra_body(llm_settings["local_llm_model"]),
        )
        text = _extract_chat_completion_text(response).strip()
    except Exception:  # noqa: BLE001 - best-effort, never break the response
        return ""
    text = text.splitlines()[0].strip() if text else ""
    return text[:200]
```

- [ ] **Step 4: Run the reformulation unit tests to verify they pass**

```bash
cd /home/longxiang/MiroThinker/apps/admin-console && UV_OFFLINE=1 uv run --no-sync pytest tests/test_chat_synthesis_depth.py -q
```
Expected: PASS (all tests, including the new reformulation ones).

- [ ] **Step 5: Move `intent` computation earlier in `_build_chat_response`**

In `_build_chat_response`, the current web-search block starts at chat.py:3974 and `intent` is computed later at chat.py:4006. Insert the intent computation right after the single-entity enrichment (the `_enrich_list_entities` call added in Task 2 Step 4), before the web-search block:

```python
    _enrich_list_entities(structured_payload, conn=conn)

    intent = _detect_answer_intent(query, query_type, structured_payload)
```

Then remove the later recomputation — at chat.py:4006 the line `intent = _detect_answer_intent(query, query_type, structured_payload)` becomes a no-op duplicate; delete that single line (the `intent` variable is already bound above).

- [ ] **Step 6: Rewrite the web-search block to retry on 0 results (qa intent)**

Replace the whole web-search block (chat.py:3978-3998):

```python
    if not structured_payload.get("web_evidence"):
        web_provider = _get_web_search_provider_or_none()
        if web_provider is not None:
            try:
                web_payload = web_provider.search(query)
                organic = web_payload.get("organic") or web_payload.get("results") or []
                web_evidence_rows: list[dict[str, Any]] = []
                for item in organic[:10]:
                    web_evidence_rows.append(
                        {
                            "id": item.get("link") or item.get("url") or f"web-{len(web_evidence_rows)}",
                            "title": (item.get("title") or "").strip(),
                            "snippet": (item.get("snippet") or "").strip(),
                            "url": item.get("link") or item.get("url") or "",
                            "type": "web",
                        }
                    )
                if web_evidence_rows:
                    structured_payload["web_evidence"] = web_evidence_rows
            except Exception as exc:  # noqa: BLE001 - web is best-effort
                logger.warning("Web search augmentation failed for %r: %s", query, exc)
```

With:

```python
    if not structured_payload.get("web_evidence"):
        web_provider = _get_web_search_provider_or_none()
        if web_provider is not None:
            try:
                web_evidence_rows: list[dict[str, Any]] = _web_search_to_rows(web_provider, query)
                # Fix2: a raw knowledge sub-question is often too contextualized for
                # Bocha (e.g. "在真实数据采集路线中，有哪些具体方式" → 0 results). On a
                # qa-intent miss, rewrite to search keywords via the local LLM and
                # retry once. Synthesis still answers the raw query.
                if not web_evidence_rows and intent == "qa":
                    reformulated = _reformulate_query_for_search(query)
                    if reformulated and reformulated != query:
                        web_evidence_rows = _web_search_to_rows(web_provider, reformulated)
                if web_evidence_rows:
                    structured_payload["web_evidence"] = web_evidence_rows
            except Exception as exc:  # noqa: BLE001 - web is best-effort
                logger.warning("Web search augmentation failed for %r: %s", query, exc)
```

- [ ] **Step 7: Sanity-import + run the full helper test file**

```bash
cd /home/longxiang/MiroThinker/apps/admin-console && UV_OFFLINE=1 uv run --no-sync python -c "from backend.api.chat import _reformulate_query_for_search, _web_search_to_rows; print('ok')"
UV_OFFLINE=1 uv run --no-sync pytest tests/test_chat_synthesis_depth.py -q
```
Expected: `ok` then PASS.

- [ ] **Step 8: Commit**

```bash
git add apps/admin-console/backend/api/chat.py apps/admin-console/tests/test_chat_synthesis_depth.py
git commit -m "feat(synthesis): LLM-reformulate knowledge queries before web search

Raw knowledge sub-questions (qid19/20/22: '在真实数据采集路线中，有哪些具体方式')
are too contextualized for Bocha → 0 results → no web evidence → synthesis has
nothing to say. On a qa-intent miss, the local qwen3.6 LLM now rewrites the
query to search keywords and retries once. Synthesis still answers the raw
user query. Best-effort: any failure falls through to local-only.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 4: Integration GREEN — eval + record

The unit tests cover pure helpers; the end-to-end behavior (deeper answers, qid19/20/22 unblocked, qid11 stable) is eval-verified per CLAUDE.md §8.

**Files:**
- Run: `apps/admin-console/scripts/eval_true_accuracy.py`
- Record: `docs/solutions/2026-07-07-synthesis-depth-fixes-results.md`

- [ ] **Step 1: Run the 3-run-median eval (proxy unset, backend DOWN — Milvus single-writer lock)**

```bash
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
cd /home/longxiang/MiroThinker/apps/admin-console
export DATABASE_URL=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real
export MILVUS_USE_REAL_CLIENT=1 CHAT_LLM_SYNTHESIS=on UV_OFFLINE=1
# NOTE: do NOT set LOCAL_LLM_MODEL — default profile resolves to the local qwen3.6 endpoint.
UV_OFFLINE=1 uv run --no-sync python scripts/eval_true_accuracy.py --runs 3
```
Expected gates:
- Overall: 9/19 → ~12-13/19 (~60-70%).
- No regression on stable-pass retrieval cases (qid1/3/14/16/17/18/23/24/26).
- qid19/20/22: 0.00 → substantive (Bocha matches reformulated keywords).
- qid11: no longer flaps 0.00↔1.00 across runs.

- [ ] **Step 2: Record results to docs/solutions/**

Create `docs/solutions/2026-07-07-synthesis-depth-fixes-results.md` with: before/after table (per-qid), which fixes moved which cases, remaining failures (expected: qid13 cross-domain, qid27 recall, qid6 rejection — all out of this slice's scope), and the next-workstream pointer (eval methodology → data pipeline).

- [ ] **Step 3: Commit the results doc**

```bash
git add docs/solutions/2026-07-07-synthesis-depth-fixes-results.md
git commit -m "docs(solutions): synthesis-depth-fixes eval results (47% -> ?)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

- [ ] **Step 4: Report**

Report the final accuracy, the per-fix effect, and the remaining-failure breakdown. If a gate failed (regression or no movement), do NOT mark the slice Accepted — diagnose and Revise per CLAUDE.md §12.

---

## Self-Review

**1. Spec coverage:**
- RC1 (list shallow) → Task 2 (fetch + render both paths). ✓
- RC2 (raw query web search) → Task 3 (reformulation + retry). ✓
- RC3 (temperature) → Task 1. ✓
- Token discipline (top-3 × ~2 facts) → `_enrich_list_entities` `[:3]` + `_compact_*` `[:200]`. ✓
- Trigger discipline (qa + 0-results only) → Task 3 Step 6 `if not web_evidence_rows and intent == "qa"`. ✓
- Synthesis keeps raw query → reformulation result never reaches `_call_gemma_synthesis`'s `query` arg. ✓
- Best-effort/rollback → try/except in web block; one commit per fix. ✓

**2. Placeholder scan:** none — every code step shows complete code.

**3. Type/signature consistency:**
- `_enrich_list_entities(structured_payload, *, conn, prof_rich_fn=_prof_rich_profile_facts, company_rich_fn=_company_rich_facts)` — matches call `_enrich_list_entities(structured_payload, conn=conn)` and the DI test. ✓
- `_compact_prof_rich(facts: dict) -> str` / `_compact_company_rich(facts: dict) -> str` — match tests. ✓
- `_web_search_to_rows(web_provider, query) -> list[dict]` / `_reformulate_query_for_search(query, *, client_factory=None, timeout=8.0) -> str` — match tests. ✓
- `rich_summary` key set in `_enrich_list_entities`, read in both render paths. ✓
- `intent` computed once (Task 3 Step 5), reused at template selection (line 4006 duplicate deleted). ✓

**Risk note:** Task 3 Step 5 deletes the `intent =` line at 4006 — verify after the move that `intent` is in scope at the template-selection block (it is: both are inside `_build_chat_response`). If a later edit re-adds it, the move is idempotent (harmless rebind).
