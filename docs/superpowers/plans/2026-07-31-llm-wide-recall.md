# LLM 驱动的宽召回架构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 拆除证据链准入闸门，把相关性/探针/提取/缺口判断交给批量限时 fail-open 的快模型，并解决 882 条教授记录被必填字段 gate 拒掉的问题，使 Excel 测试集 KEY 硬失败归零。

**Architecture:** 检索做宽、LLM 判定面批量并行、确定性只留护栏（安全/完整性/预算/注入/会话记账）；证据链仅作溯源。新增独立判定模块 `llm_judgments.py`（单一职责：批量 LLM 判定 + fail-open + token bucket），各判定点以"LLM 优先、规则兜底"方式接入；882 走一次性 LLM 辅助迁移 + gate 降级为质量信号。

**Tech Stack:** Python 3.12, pydantic, OpenAI-compatible 快模型（环境 llm_profiles，gemma4 级）, httpx, Playwright（基线已有）, pytest, ruff, pyright。

**工作区：** `/home/longxiang/MiroThinker/.worktrees/canonical-v2-s11-consolidation`（分支 `codex/canonical-v2-s12a-ready`）。测试命令：miroflow 侧 `cd apps/miroflow-agent && uv run pytest -q -n0 <file>`；admin 侧 `cd apps/admin-console && uv run pytest -q <file>`；静态 `uv run ruff check <files>`、`uv run pyright <files>`（admin 文件用 `apps/miroflow-agent/.venv/bin/pyright --pythonpath apps/admin-console/.venv/bin/python`）。

**频率约定：** 每个 Task 结束即 commit（conventional commits，`fix(canonical_v2): …` / `feat(canonical_v2): …`）。

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `apps/miroflow-agent/src/data_agents/canonical_v2/llm_judgments.py`（新） | 唯一 LLM 判定入口：批量判定（relevance/probe_accept/fact_extract/gap_check）、输出 schema、硬超时、fail-open、token bucket、executor |
| `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py` | 探针验收 LLM 化（person/relation/theme）、相关性判定接入、选择器 fail-open 放宽、缺口自查循环接线 |
| `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_answer.py` | 拆除 `unsupported_material_claim` 硬降级 → 归因放行回答 |
| `apps/miroflow-agent/src/data_agents/providers/page_fetch.py` | T0 直连增强 + T1 Playwright 无头兜底（页面池、触发条件、硬超时） |
| `apps/miroflow-agent/src/data_agents/professor/release.py` | 教授必填字段 gate → name+institution 放行 + 质量信号 |
| `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12e/`（新目录） | 882 迁移脚本（分析/判定/回填/复核报告） |
| 测试：`tests/canonical_v2/test_llm_judgments.py`（新）、`test_serving_supplemental_person_criteria.py`、`test_knowledge_serving_isolated.py`、`test_knowledge_answer_multiturn_contract.py`、`test_web_page_fetch.py`、`test_llm_query_rewrite.py`（扩） | 各判定点 RED→GREEN 与 fail-open 契约 |

---

### Task 1: LLM 判定基础设施 `llm_judgments.py`

**Files:**
- Create: `apps/miroflow-agent/src/data_agents/canonical_v2/llm_judgments.py`
- Test: `apps/miroflow-agent/tests/canonical_v2/test_llm_judgments.py`

**设计要点：** 单一职责模块。`_LlmJudge` 惰性构造 OpenAI 客户端（镜像 `_EnvironmentProseRenderer._configured_renderer` 的 `resolve_professor_llm_settings` 模式），`judge_batch(kind, question, items, context) -> tuple[JudgmentResult, ...]`；每种 kind 一个紧凑中文 system prompt + JSON 输出 schema；硬超时（默认 1.8s）→ 全部条目按 fail-open 默认判定（relevance=True, accept=True, extract=None, gap=None）；非法 JSON → 同样 fail-open；token bucket（每实例每秒 ≤N 调用，进程内共享）。

**判定 schema（pydantic，写进模块）：**

```python
class RelevanceJudgment(ContractModel):
    item_id: str
    relevant: bool
    entity_ids: tuple[str, ...] = ()
    fact: str = ""

class ProbeAcceptJudgment(ContractModel):
    item_id: str
    accept: bool
    entity_id: str | None = None
    predicate: str | None = None
    value: str = ""

class FactExtraction(ContractModel):
    item_id: str
    facts: tuple[str, ...] = ()
    entity_ids: tuple[str, ...] = ()

class GapCheckResult(ContractModel):
    covered: bool
    missing_aspects: tuple[str, ...] = ()
    followup_queries: tuple[str, ...] = ()
```

- [ ] **Step 1: 写失败测试** `test_llm_judgments.py`（桩 client 注入：`_LlmJudge(client_factory=lambda **kw: fake_client)`）

```python
"""Hermetic tests for the batched LLM judgment harness."""
from __future__ import annotations

import json
import time
from typing import Any

from src.data_agents.canonical_v2.llm_judgments import (
    FactExtraction,
    GapCheckResult,
    ProbeAcceptJudgment,
    RelevanceJudgment,
    create_llm_judge,
)


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, scripts: list[Any]) -> None:
        self._scripts = scripts
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        script = self._scripts.pop(0)
        if isinstance(script, Exception):
            raise script
        return _FakeResponse(script)


class _FakeClient:
    def __init__(self, scripts: list[Any]) -> None:
        self.chat = type("Chat", (), {"completions": _FakeCompletions(scripts)})()


def test_relevance_batch_parses_structured_results() -> None:
    payload = json.dumps(
        {"judgments": [
            {"item_id": "a", "relevant": True, "entity_ids": ["company-c-1"], "fact": "开普勒有酒店配送机器人"},
            {"item_id": "b", "relevant": False},
        ]},
        ensure_ascii=False,
    )
    judge = create_llm_judge(client_factory=lambda **kw: _FakeClient([payload]))
    results = judge.judge_batch(
        kind="relevance",
        question="中国有哪些成熟的酒店送餐机器人供应商",
        items=(
            {"item_id": "a", "text": "开普勒探索者D1酒店配送机器人发布"},
            {"item_id": "b", "text": "电梯配件黄页"},
        ),
    )
    assert results == (
        RelevanceJudgment(item_id="a", relevant=True, entity_ids=("company-c-1",), fact="开普勒有酒店配送机器人"),
        RelevanceJudgment(item_id="b", relevant=False, entity_ids=(), fact=""),
    )


def test_timeout_fails_open_with_attributed_defaults() -> None:
    def slow_create(**kwargs: Any) -> Any:
        time.sleep(2.5)
        raise AssertionError("must be cut by the hard timeout")

    completions = _FakeCompletions([])
    completions.create = slow_create  # type: ignore[assignment]
    client = type("C", (), {"chat": type("Chat", (), {"completions": completions})()})()
    judge = create_llm_judge(client_factory=lambda **kw: client, timeout_seconds=0.2)
    results = judge.judge_batch(
        kind="relevance",
        question="q",
        items=({"item_id": "a", "text": "t1"}, {"item_id": "b", "text": "t2"}),
    )
    assert all(r.relevant for r in results)
    assert judge.last_outcome == "timeout_fail_open"


def test_invalid_json_fails_open() -> None:
    judge = create_llm_judge(client_factory=lambda **kw: _FakeClient(["not json at all"]))
    results = judge.judge_batch(kind="relevance", question="q", items=({"item_id": "a", "text": "t"},))
    assert results[0].relevant is True
    assert judge.last_outcome == "invalid_output_fail_open"


def test_gap_check_parses_followup_queries_capped_at_two() -> None:
    payload = json.dumps(
        {"covered": False, "missing_aspects": ["早稻田人物"], "followup_queries": ["q1", "q2", "q3"]},
        ensure_ascii=False,
    )
    judge = create_llm_judge(client_factory=lambda **kw: _FakeClient([payload]))
    result = judge.gap_check(question="q", evidence_digest="d")
    assert isinstance(result, GapCheckResult)
    assert result.covered is False
    assert result.followup_queries == ("q1", "q2")


def test_token_bucket_limits_calls_per_second() -> None:
    payload = json.dumps({"judgments": []})
    judge = create_llm_judge(
        client_factory=lambda **kw: _FakeClient([payload, payload, payload]),
        max_calls_per_second=2,
    )
    started = time.monotonic()
    for _ in range(3):
        judge.judge_batch(kind="relevance", question="q", items=())
    assert time.monotonic() - started >= 0.5
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd apps/miroflow-agent && uv run pytest -q -n0 tests/canonical_v2/test_llm_judgments.py`
Expected: FAIL `ModuleNotFoundError: src.data_agents.canonical_v2.llm_judgments`

- [ ] **Step 3: 实现 `llm_judgments.py`**

```python
"""Batched, timeout-bounded, fail-open LLM judgments for the serving path.

One harness for every "needs content understanding" judgment: relevance,
probe acceptance, fact extraction, and the single-round gap check. Any
timeout, provider error, or malformed output degrades to attributed
fail-open defaults — a judgment failure must never answer "no" by default.
"""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from threading import Lock
from time import monotonic
from typing import Any, Callable, Iterable, Literal

from openai import OpenAI, OpenAIError

from src.data_agents.canonical_v2.contracts import ContractModel
from src.data_agents.professor.llm_profiles import (
    build_non_thinking_extra_body,
    resolve_professor_llm_settings,
)

JudgmentKind = Literal["relevance", "probe_accept", "fact_extract", "gap_check"]

_DEFAULT_TIMEOUT_SECONDS = 1.8
_DEFAULT_MAX_CALLS_PER_SECOND = 4.0
_JUDGE_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="canonical-v2-llm-judge")


class RelevanceJudgment(ContractModel):
    item_id: str
    relevant: bool
    entity_ids: tuple[str, ...] = ()
    fact: str = ""


class ProbeAcceptJudgment(ContractModel):
    item_id: str
    accept: bool
    entity_id: str | None = None
    predicate: str | None = None
    value: str = ""


class FactExtraction(ContractModel):
    item_id: str
    facts: tuple[str, ...] = ()
    entity_ids: tuple[str, ...] = ()


class GapCheckResult(ContractModel):
    covered: bool
    missing_aspects: tuple[str, ...] = ()
    followup_queries: tuple[str, ...] = ()


_SYSTEM_PROMPTS: dict[str, str] = {
    "relevance": (
        "你是检索相关性判定器。输入用户问题与若干候选结果（含本地实体与网页结果）。"
        "逐条判断：与问题是否相关；若相关且谈到某个具体实体，给出实体名/ID与一句可归因事实。"
        "宁可多判相关，不可漏判。只输出JSON：{\"judgments\":[{\"item_id\":…,\"relevant\":true|false,"
        "\"entity_ids\":[…],\"fact\":\"…\"}]}，item_id 必须与输入一致。"
    ),
    "probe_accept": (
        "你是证据验收器。输入问题语义（谓词/约束/主题）与一条网页结果，判断它是否直接支持该语义；"
        "支持则给出绑定的实体与值。只输出JSON：{\"judgments\":[{\"item_id\":…,\"accept\":true|false,"
        "\"entity_id\":…,\"predicate\":…,\"value\":…}]}。"
    ),
    "fact_extract": (
        "你是事实抽取器。输入用户问题、候选实体清单与一段网页正文，抽取与问题相关且可归因的事实，"
        "每条事实注明涉及的实体。不得编造正文没有的内容。只输出JSON："
        "{\"judgments\":[{\"item_id\":…,\"facts\":[\"…\"],\"entity_ids\":[\"…\"]}]}。"
    ),
    "gap_check": (
        "你是覆盖度自查器。输入用户问题与已见证据摘要，判断证据是否已覆盖问题的各子意图；"
        "若有明显缺口，给出缺口方面与最多2条定向补查query（关键词式）。证据充足则 covered=true。"
        "只输出JSON：{\"covered\":true|false,\"missing_aspects\":[\"…\"],\"followup_queries\":[\"…\"]}。"
    ),
}


class _TokenBucket:
    def __init__(self, rate_per_second: float) -> None:
        self._interval = 1.0 / rate_per_second
        self._next = 0.0
        self._lock = Lock()

    def acquire(self) -> None:
        with self._lock:
            now = monotonic()
            if now < self._next:
                sleep_for = self._next - now
            else:
                sleep_for = 0.0
            self._next = max(now, self._next) + self._interval
        if sleep_for > 0:
            import time as _time

            _time.sleep(sleep_for)


class _LlmJudge:
    def __init__(
        self,
        *,
        client_factory: Callable[..., Any] | None = None,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        max_calls_per_second: float = _DEFAULT_MAX_CALLS_PER_SECOND,
    ) -> None:
        self._client_factory = client_factory
        self._timeout_seconds = timeout_seconds
        self._bucket = _TokenBucket(max_calls_per_second)
        self._client: Any | None = None
        self._model = ""
        self._extra_body: dict[str, Any] = {}
        self._lock = Lock()
        self.last_outcome = "ok"

    def _configured_client(self) -> Any:
        with self._lock:
            if self._client is not None:
                return self._client
            if self._client_factory is not None:
                settings = resolve_professor_llm_settings(
                    os.getenv("CHAT_LLM_PROFILE", "gemma4"),
                    apply_endpoint_env_overrides=False,
                )
                self._client = self._client_factory(
                    base_url=settings["local_llm_base_url"],
                    api_key=settings["local_llm_api_key"],
                    timeout=self._timeout_seconds,
                    max_retries=0,
                )
            else:
                settings = resolve_professor_llm_settings(
                    os.getenv("CHAT_LLM_PROFILE", "gemma4"),
                    apply_endpoint_env_overrides=False,
                )
                self._client = OpenAI(
                    base_url=settings["local_llm_base_url"],
                    api_key=settings["local_llm_api_key"],
                    timeout=self._timeout_seconds,
                    max_retries=0,
                )
            self._model = str(settings["local_llm_model"])
            self._extra_body = build_non_thinking_extra_body(self._model)
            return self._client

    def _chat(self, *, kind: str, payload: dict[str, Any]) -> str:
        self._bucket.acquire()
        client = self._configured_client()
        response = client.chat.completions.create(
            model=self._model,
            temperature=0,
            max_tokens=800,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPTS[kind]},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            extra_body=self._extra_body,
        )
        choices = getattr(response, "choices", ())
        content = None if not choices else getattr(choices[0].message, "content", None)
        if not isinstance(content, str) or not content.strip():
            raise ValueError("empty judge response")
        return content.strip()

    @staticmethod
    def _parse_json_object(text: str) -> dict[str, Any]:
        fenced = text.strip()
        if fenced.startswith("```"):
            fenced = fenced.strip("`").lstrip("json").strip()
        start, end = fenced.find("{"), fenced.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("no JSON object")
        payload = json.loads(fenced[start : end + 1])
        if not isinstance(payload, dict):
            raise ValueError("not a JSON object")
        return payload

    def _call(self, *, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        future = _JUDGE_EXECUTOR.submit(self._chat, kind=kind, payload=payload)
        try:
            raw = future.result(timeout=self._timeout_seconds)
            return self._parse_json_object(raw)
        except (
            FutureTimeoutError,
            TimeoutError,
            ConnectionError,
            OpenAIError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            outcome = "timeout_fail_open" if isinstance(exc, (FutureTimeoutError, TimeoutError)) else "invalid_output_fail_open"
            self.last_outcome = outcome
            raise _JudgeFailOpen(outcome) from exc

    def judge_batch(
        self,
        *,
        kind: Literal["relevance", "probe_accept", "fact_extract"],
        question: str,
        items: Iterable[dict[str, Any]],
        context: dict[str, Any] | None = None,
    ) -> tuple[Any, ...]:
        material = tuple(items)
        payload = {"question": question, "context": context or {}, "items": material}
        try:
            result = self._call(kind=kind, payload=payload)
        except _JudgeFailOpen:
            defaults = {
                "relevance": lambda item: RelevanceJudgment(item_id=item["item_id"], relevant=True),
                "probe_accept": lambda item: ProbeAcceptJudgment(item_id=item["item_id"], accept=True),
                "fact_extract": lambda item: FactExtraction(item_id=item["item_id"]),
            }
            self.last_outcome = self.last_outcome if "fail_open" in self.last_outcome else "invalid_output_fail_open"
            return tuple(defaults[kind](item) for item in material)
        self.last_outcome = "ok"
        raw = result.get("judgments")
        if not isinstance(raw, list):
            return tuple(
                RelevanceJudgment(item_id=item["item_id"], relevant=True) if kind == "relevance"
                else ProbeAcceptJudgment(item_id=item["item_id"], accept=True) if kind == "probe_accept"
                else FactExtraction(item_id=item["item_id"])
                for item in material
            )
        model = {
            "relevance": RelevanceJudgment,
            "probe_accept": ProbeAcceptJudgment,
            "fact_extract": FactExtraction,
        }[kind]
        by_id = {entry.get("item_id"): entry for entry in raw if isinstance(entry, dict)}
        return tuple(
            model.model_validate(by_id[item["item_id"]])
            if item["item_id"] in by_id
            else model.model_validate({"item_id": item["item_id"], **({"relevant": True} if kind == "relevance" else {"accept": True} if kind == "probe_accept" else {})})
            for item in material
        )

    def gap_check(self, *, question: str, evidence_digest: str) -> GapCheckResult:
        try:
            result = self._call(
                kind="gap_check",
                payload={"question": question, "evidence": evidence_digest},
            )
        except _JudgeFailOpen:
            return GapCheckResult(covered=True)
        self.last_outcome = "ok"
        parsed = GapCheckResult.model_validate(result)
        return parsed.model_copy(
            update={"followup_queries": parsed.followup_queries[:2]}
        )


class _JudgeFailOpen(Exception):
    def __init__(self, outcome: str) -> None:
        super().__init__(outcome)
        self.outcome = outcome


def create_llm_judge(
    *,
    client_factory: Callable[..., Any] | None = None,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    max_calls_per_second: float = _DEFAULT_MAX_CALLS_PER_SECOND,
) -> _LlmJudge:
    return _LlmJudge(
        client_factory=client_factory,
        timeout_seconds=timeout_seconds,
        max_calls_per_second=max_calls_per_second,
    )
```

- [ ] **Step 4: 跑测试确认通过 + 静态检查**

Run: `cd apps/miroflow-agent && uv run pytest -q -n0 tests/canonical_v2/test_llm_judgments.py`
Expected: 5 passed
Run: `uv run ruff check src/data_agents/canonical_v2/llm_judgments.py tests/canonical_v2/test_llm_judgments.py && uv run pyright src/data_agents/canonical_v2/llm_judgments.py`
Expected: All checks passed / 0 errors

- [ ] **Step 5: Commit**

```bash
git add apps/miroflow-agent/src/data_agents/canonical_v2/llm_judgments.py apps/miroflow-agent/tests/canonical_v2/test_llm_judgments.py
git commit -m "feat(canonical_v2): add batched fail-open LLM judgment harness"
```

---

### Task 2: 探针验收 LLM 化（person/relation/theme）

**Files:**
- Modify: `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py`（探针验收三处：`_person_evidence_match`、`_relation_evidence_match`、`_theme_evidence_match` 的调用点，统一走 `_accept_probe_hit`）
- Test: `apps/miroflow-agent/tests/canonical_v2/test_serving_supplemental_person_criteria.py`（扩）

**设计要点：** 新增 `_accept_probe_hit(*, judge, kind, question, entity_name, semantics, result) -> bool`：先试规则函数（现有族，作为快速预筛），**规则拒绝时再问 LLM**（`probe_accept` kind，单条 prompt 含 question/entity/semantics/title/snippet）；LLM 超时/失败 → 采用规则结果（fail-open 到规则，而非到 accept）。这样规则命中的零成本、规则漏掉的由 LLM 捞回，既有测试全部不动（规则路径保留），新增测试只覆盖"规则拒绝但 LLM 接受/规则拒绝 LLM 也拒绝/LLM 失败回规则"。

- [ ] **Step 1: 写失败测试（追加到 `test_serving_supplemental_person_criteria.py`）**

```python
def test_probe_acceptance_falls_back_to_llm_when_rules_reject(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rules reject "由海归博士团队创立，核心成员来自日本早稻田"（无创始人字样），
    the LLM judge must recover it as founder evidence."""
    from src.data_agents.canonical_v2 import llm_judgments as lj

    class _Judge:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def judge_batch(self, *, kind: str, question: str, items: Any, context: Any = None) -> Any:
            self.calls.append({"kind": kind, "items": tuple(items)})
            return (
                lj.ProbeAcceptJudgment(
                    item_id="hit-1",
                    accept=True,
                    entity_id="company-c-maibu",
                    predicate="person_criteria",
                    value="早稻田",
                ),
            )

    judge = _Judge()
    accepted = serving_module._accept_probe_hit(
        judge=judge,
        kind="person",
        question=PERSON_QUERY,
        entity_name=MAIBU_ROBOT_NAME,
        semantics={"constraint": "早稻田"},
        result=serving_module._NormalizedWebResult(
            title="迈步团队- 迈步机器人",
            url="https://example.test/maibu-team",
            snippet="公司由海归博士技术团队创立，核心成员毕业于日本早稻田大学。",
            summary="",
            primary_provider_version="bocha-v1",
            corroborating_provider_versions=("bocha-v1",),
        ),
    )
    assert accepted is True
    assert judge.calls and judge.calls[0]["kind"] == "probe_accept"


def test_probe_acceptance_rule_hit_skips_llm() -> None:
    class _ExplodingJudge:
        def judge_batch(self, **kwargs: Any) -> Any:
            raise AssertionError("LLM must not be called on rule hits")

    assert (
        serving_module._accept_probe_hit(
            judge=_ExplodingJudge(),
            kind="person",
            question="q",
            entity_name="帕西尼感知科技（深圳）有限公司",
            semantics={"constraint": "早稻田"},
            result=serving_module._NormalizedWebResult(
                title="帕西尼创始人许晋诚",
                url="https://example.test/xu",
                snippet="帕西尼感知科技（深圳）有限公司创始人许晋诚，毕业于早稻田大学。",
                summary="",
                primary_provider_version="bocha-v1",
                corroborating_provider_versions=("bocha-v1",),
            ),
        )
        is True
    )


def test_probe_acceptance_llm_failure_falls_back_to_rule_result() -> None:
    class _TimeoutJudge:
        last_outcome = "timeout_fail_open"

        def judge_batch(self, **kwargs: Any) -> Any:
            return ()

    # 规则拒绝、LLM 也无输出（超时）→ 采用规则拒绝结果（fail-closed 到规则，不放行噪声）
    assert (
        serving_module._accept_probe_hit(
            judge=_TimeoutJudge(),
            kind="person",
            question="q",
            entity_name="帕西尼感知科技（深圳）有限公司",
            semantics={"constraint": "早稻田"},
            result=serving_module._NormalizedWebResult(
                title="电梯配件黄页",
                url="https://example.test/junk",
                snippet="电梯按钮箱与配件。",
                summary="",
                primary_provider_version="bocha-v1",
                corroborating_provider_versions=("bocha-v1",),
            ),
        )
        is False
    )
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd apps/miroflow-agent && uv run pytest -q -n0 tests/canonical_v2/test_serving_supplemental_person_criteria.py -k llm`
Expected: FAIL `AttributeError: module has no attribute '_accept_probe_hit'`

- [ ] **Step 3: 实现 `_accept_probe_hit` 并接入三个探针验收点**

在 `_theme_evidence_match` 之后新增：

```python
def _accept_probe_hit(
    *,
    judge: Any,
    kind: str,
    question: str,
    entity_name: str,
    semantics: dict[str, Any],
    result: _NormalizedWebResult,
) -> bool:
    """Rules first (free), LLM judge recovers what the rules miss.

    A rule hit returns immediately; a rule miss asks the batched probe_accept
    judgment; a judge failure keeps the rule result (never admits noise).
    """
    rule_hit = {
        "person": lambda: _person_evidence_match(
            result,
            company=entity_name,
            constraint=semantics.get("constraint"),
        ),
        "relation": lambda: _relation_evidence_match(result, spec=semantics["spec"]),
        "theme": lambda: _theme_evidence_match(
            result,
            company=entity_name,
            core=semantics["core"],
        ),
    }[kind]()
    if rule_hit or judge is None:
        return rule_hit
    judgments = judge.judge_batch(
        kind="probe_accept",
        question=question,
        items=(
            {
                "item_id": "hit-1",
                "entity": entity_name,
                "semantics": semantics,
                "title": result.title,
                "snippet": result.snippet,
            },
        ),
    )
    if not judgments:
        return False
    return bool(getattr(judgments[0], "accept", False))
```

三处调用点改造（`knowledge_serving_isolated.py` 内 `_serving_supplemental_search.search` 的 person/relation/theme 三个验收分支）：把 `_person_evidence_match(result, company=…)` / `_relation_evidence_match(result, spec=…)` / `_theme_evidence_match(result, company=…, core=…)` 分别替换为 `_accept_probe_hit(judge=probe_judge, kind="person"/"relation"/"theme", question=…, entity_name=…, semantics=…, result=result)`；`probe_judge` 由 `_create_serving_person_criteria_sufficiency_supplemental` 新增参数 `judge: Any | None = None` 传入（默认 `None` = 纯规则，生产在 `load_recorded_serving_inputs` 传 `create_llm_judge()`）。

- [ ] **Step 4: 跑测试**

Run: `cd apps/miroflow-agent && uv run pytest -q -n0 tests/canonical_v2/test_serving_supplemental_person_criteria.py tests/canonical_v2/test_knowledge_serving_isolated.py`
Expected: all passed（既有测试走规则路径不受影响，新三个测试通过）

- [ ] **Step 5: Commit**

```bash
git add apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py apps/miroflow-agent/tests/canonical_v2/test_serving_supplemental_person_criteria.py
git commit -m "feat(canonical_v2): LLM judge recovers probe evidence the rules miss"
```

---

### Task 3: 拆除硬降级——`unsupported_material_claim` → 归因放行

**Files:**
- Modify: `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_answer.py`（`answer()` 中 `unsupported_material_claim` 分支）
- Test: `apps/miroflow-agent/tests/canonical_v2/test_knowledge_answer_multiturn_contract.py`（扩）

**设计要点：** 当前 proposal.claims 非空但全部被 handle 绑定丢弃时硬降级（空模板+limitation）。改为**归因放行**：当 `claims` 为空但 evidence_set 存在带 claim_binding 的 web/supplemental 证据时，用这些证据构造归因 claim（`text = _semantic_text`-style 可读文本，`source_natures` 保留），走正常 prose 路径；仅当连可用证据都没有时才保持降级。护栏不动：`_ground_claim`、allowed scope、注入审计照旧。

- [ ] **Step 1: 写失败测试（追加到 `test_knowledge_answer_multiturn_contract.py`）**

```python
def test_zero_bound_claims_fails_open_with_attributed_web_evidence() -> None:
    """All proposal claims dropped by scope must not hard-degrade when
    bindable web evidence exists: answer from attributed evidence instead."""
    module = _answer_module()
    read_module = _read_module()
    snapshot_bytes = b"Recorded hotel delivery page for Ninebot."
    snapshot_sha256 = hashlib.sha256(snapshot_bytes).hexdigest()
    web_item = _item(
        read_module,
        evidence_id="web-evidence:ninebot-hotel",
        object_id="web-object:sha256:ninebot",
        domain="company",
        subject_id="web-object:sha256:ninebot",
        predicate="display_identity",
        value="九号机器人酒店配送",
        snippet="九号机器人酒店配送方案：面向酒店客房送餐与楼宇配送场景。",
        lane="web",
        source_nature="current_web",
        source_locator="https://example.test/ninebot-hotel",
        web_snapshot=read_module.WebEvidenceSnapshot(
            snapshot_id=f"web-snapshot:sha256:{snapshot_sha256}",
            content_sha256=snapshot_sha256,
            retrieved_at=NOW,
            byte_length=len(snapshot_bytes),
        ),
    )
    first_request = _request(
        module,
        session_id="session:s9m:fail-open",
        turn_id="turn:fail-open:1",
        query="列出两家机器人公司",
        evidence_set=_evidence_set(read_module, query="列出两家机器人公司"),
    )
    second_request = _request(
        module,
        session_id="session:s9m:fail-open",
        turn_id="turn:fail-open:2",
        query="这些公司的酒店配送能力如何",
        evidence_set=_evidence_set(
            read_module,
            query="这些公司的酒店配送能力如何",
            items=(web_item,),
        ),
        session_directive=module.SessionDirective(referent="displayed_result_set"),
    )

    def selector(request: Any) -> Any:
        if request.turn_id == "turn:fail-open:1":
            return _proposal(module, request, displayed_handle_ids=())
        # All claims reference a subject outside the allowed scope → dropped
        return _proposal(
            module,
            request,
            displayed_handle_ids=(),
            claims=(
                (
                    "claim:out-of-scope",
                    "一家不在展示集内的公司。",
                    ("company:elsewhere",),
                    (web_item.evidence_id,),
                ),
            ),
        )

    answer = module.create_ephemeral_knowledge_answer(answer_selector=selector)
    answer.answer(first_request)
    result = answer.answer(second_request)
    assert result.response_mode == "answer"
    assert "九号机器人酒店配送" in result.answer_text
    assert any(
        limitation.code == "attributed_evidence_fallback"
        for limitation in result.limitations
    )
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd apps/miroflow-agent && uv run pytest -q -n0 tests/canonical_v2/test_knowledge_answer_multiturn_contract.py -k fail_open`
Expected: FAIL（当前走 `_degraded(reason="unsupported_material_claim")`，answer_text 为降级模板且 limitation code 不匹配）

- [ ] **Step 3: 实现归因放行**

`knowledge_answer.py` 中 `answer()` 的降级分支（`proposal.claims and not claims and not advance.suppress_claims and (resolved_referent is None or resolved_referent.kind == "current_turn")`）内，在 `_degraded` 前插入：

```python
            if session_existed:
                assert session_snapshot is not None
                self._sessions[session_key] = session_snapshot
            else:
                self._sessions.pop(session_key, None)
            attributed = tuple(
                item
                for item in request.evidence_set.items
                if item.claim_binding is not None
                and item.source_nature in {"current_web", "supplemental_web"}
            )
            if attributed:
                fallback_claims = tuple(
                    _grounded_claim_from_item(
                        request=request,
                        item=item,
                        selector_claim_ids=selector_claim_ids,
                        index=index,
                    )
                    for index, item in enumerate(attributed[:5])
                )
                fallback_claims = tuple(c for c in fallback_claims if c is not None)
                if fallback_claims:
                    limitations.append(
                        AnswerLimitation(
                            code="attributed_evidence_fallback",
                            material=False,
                            reason=(
                                "Selector claims did not bind the conversation scope; "
                                "answering from attributed web evidence instead."
                            ),
                        )
                    )
                    claims = fallback_claims
                    # fall through to the normal claims pipeline below
            if not claims:
                return self._degraded(
                    request,
                    reason="unsupported_material_claim",
                    additional_limitations=tuple(limitations),
                )
```

新增 `_grounded_claim_from_item(request, item, selector_claim_ids, index) -> MaterialClaim | None`：以 `EvidenceClaimBinding` 为骨架构造 `MaterialClaim`（`claim_id=f"claim:attributed:{request.turn_id}:{index}"`、`text=f"{item.snippet}"` 截断 240 字、`subject_id/predicate/value/status` 取自 binding、`evidence_ids=(item.evidence_id,)`、`source_natures=(item.source_nature,)`），再经 `_ground_claim` 校验，不通过返回 None。

注意：分支条件里的 `resolved_referent` 检查保持原样（只在 current_turn 语义下启用归因放行；follow-up 轮 claims 空仍走原逻辑）。

- [ ] **Step 4: 跑测试 + 回归**

Run: `cd apps/miroflow-agent && uv run pytest -q -n0 tests/canonical_v2/test_knowledge_answer_multiturn_contract.py tests/canonical_v2/test_knowledge_answer_atomic_green_contract.py tests/canonical_v2/test_knowledge_answer_implementation_closure.py tests/canonical_v2/test_knowledge_answer_grounding_contract.py`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_answer.py apps/miroflow-agent/tests/canonical_v2/test_knowledge_answer_multiturn_contract.py
git commit -m "fix(canonical_v2): fail open to attributed web evidence instead of hard degrade"
```

---

### Task 4: 缺口自查单轮循环

**Files:**
- Modify: `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py`（`_DualWebLaneAdapter` 之后新增 `_GapCheckWebLoop` 并在 `load_recorded_serving_inputs` 的 web_search 上包一层）
- Test: `apps/miroflow-agent/tests/canonical_v2/test_llm_query_rewrite.py`（扩）

**设计要点：** 包装现有 `web_search` lane：`execute` 完成后，若 judge 非 None 且问题为多意图/主题类（复用 `_should_rewrite_serving_query` 的触发族），用 `gap_check`（digest=前 N 条 snippet 截断各 120 字）评估覆盖；`covered=False` 且有 followup_queries 时，对 ≤2 条补查 query 各执行一次 `_merged_results_for_views`（复用视图并发与 URL 归一合并），结果并入候选；补查失败静默忽略。护栏：补查总计 ≤2 条、整个循环只允许一次（无多轮）、补查结果照常走 claim_binding 铸造。

- [ ] **Step 1: 写失败测试（追加到 `test_llm_query_rewrite.py`）**

```python
def test_gap_check_triggers_one_bounded_followup_round() -> None:
    """A covered=False gap check fires at most two follow-up queries and merges
    their results by URL; a covered check stays a pure single pass."""
    from src.data_agents.canonical_v2 import llm_judgments as lj

    queries: list[str] = []

    def fake_search_provider(query: str) -> list[dict[str, Any]]:
        queries.append(query)
        if query == "具身智能 遥操作 动捕 具体方式":
            return [{"title": "具身智能遥操作与动捕数据采集综述", "link": "https://example.test/teleop", "snippet": "遥操作与动作捕捉是真实数据采集的两条主路。"}]
        return [{"title": "行业新闻", "link": "https://example.test/news", "snippet": "机器人行业动态。"}]

    class _Judge:
        def gap_check(self, *, question: str, evidence_digest: str) -> Any:
            return lj.GapCheckResult(
                covered=False,
                missing_aspects=("真实数据采集具体方式",),
                followup_queries=("具身智能 遥操作 动捕 具体方式", "具身智能 真机数据 采集", "第三条不该发"),
            )

    adapter = serving_module._DualWebLaneAdapter(
        timeout_ms=10_000,
        max_snapshot_bytes=8_192,
        clock=lambda: NOW,
        bocha=SimpleNamespace(search=fake_search_provider),
        serper=SimpleNamespace(search=lambda query: {"organic": []}),
        page_fetcher=None,
        gap_judge=_Judge(),
    )
    result = adapter(_lane_request("在真实数据采集路线中，有哪些具体方式"))
    assert queries.count("具身智能 遥操作 动捕 具体方式") == 1
    assert queries.count("具身智能 真机数据 采集") == 1
    assert "第三条不该发" not in queries
    assert any("遥操作" in candidate.evidence[0].snippet for candidate in result.candidates)
```

注：`_lane_request` 复用 `test_web_page_fetch.py` 的同名 helper（本测试文件已有 import 模式可仿）。

- [ ] **Step 2: 跑测试确认失败**

Run: `cd apps/miroflow-agent && uv run pytest -q -n0 tests/canonical_v2/test_llm_query_rewrite.py -k gap`
Expected: FAIL `TypeError: unexpected keyword argument 'gap_judge'`

- [ ] **Step 3: 实现 `_DualWebLaneAdapter.__init__` 新增 `gap_judge=None` + `__call__` 尾部缺口循环**

```python
        if self._gap_judge is not None and _should_rewrite_serving_query(
            request.original_query
        ):
            digest = "\n".join(
                f"- {item.title}：{item.snippet[:120]}" for item in organic[:8]
            )
            try:
                gap = self._gap_judge.gap_check(
                    question=request.original_query,
                    evidence_digest=digest,
                )
            except Exception:  # noqa: BLE001 - gap loop never breaks the lane
                gap = None
            if gap is not None and not gap.covered and gap.followup_queries:
                followup_results = self._merged_results_for_views(
                    tuple(gap.followup_queries[:2])
                )
                if followup_results:
                    organic = _merge_web_results_across_views(
                        (organic, followup_results)
                    )
```

（`__init__` 增加 `self._gap_judge = gap_judge`；`load_recorded_serving_inputs` 在构造主 lane 时传 `gap_judge=create_llm_judge()`，测试桩化约定同 `query_rewriter`。）

- [ ] **Step 4: 跑测试 + 回归**

Run: `cd apps/miroflow-agent && uv run pytest -q -n0 tests/canonical_v2/test_llm_query_rewrite.py tests/canonical_v2/test_knowledge_serving_isolated.py`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py apps/miroflow-agent/tests/canonical_v2/test_llm_query_rewrite.py
git commit -m "feat(canonical_v2): single-round gap-check loop with bounded follow-up queries"
```

---

### Task 5: 分层 web fetch（T0 增强 + T1 Playwright 兜底）

**Files:**
- Modify: `apps/miroflow-agent/src/data_agents/providers/page_fetch.py`
- Test: `apps/miroflow-agent/tests/canonical_v2/test_web_page_fetch.py`（扩）

**设计要点：** `fetch_page_text` 改为 `create_tiered_page_fetcher(browser_factory=None)` 返回的闭包（默认闭包仍叫 `fetch_page_text`，签名不变）。T0：真实头（UA/Accept-Language/Referer）+ 正文密度抽取（保留现有 BS4 启发式，加"文本量 <400 字 或 脚本占比 >60% 或 403/429 特征"判定为稀薄）。T1：稀薄时启用 `PlaywrightPagePool`（懒启动 chromium，≤2 页并发，单页 5s 硬超时，`domcontentloaded` 后取 `body.innerText` 截 4000 字）；`browser_factory` 供测试注入假浏览器。生产接线处（runner `page_fetcher=fetch_page_text`）无需改动。

- [ ] **Step 1: 写失败测试（追加到 `test_web_page_fetch.py`）**

```python
def test_thin_direct_result_escalates_to_headless() -> None:
    """JS-shell/thin direct pages escalate to the headless tier; rich direct
    pages never start the browser."""
    calls: list[str] = []

    class _FakePage:
        def __init__(self, text: str) -> None:
            self._text = text

        def goto(self, url: str, timeout: int, wait_until: str) -> None:
            calls.append(url)

        def eval_on_selector(self, selector: str, script: str) -> str:
            return self._text

    class _FakeBrowser:
        def __init__(self, text: str) -> None:
            self._text = text

        def new_page(self) -> Any:
            return _FakePage(self._text)

    fetcher = create_tiered_page_fetcher(
        browser_factory=lambda: _FakeBrowser("开普勒探索者D1酒店配送机器人正式发布。" * 30),
        direct_fetcher=lambda url: "<html><body><script>var x=1;</script></body></html>",
    )
    text = fetcher("https://example.test/js-shell")
    assert calls == ["https://example.test/js-shell"]
    assert "开普勒探索者D1酒店配送机器人" in (text or "")

    calls.clear()
    rich = "<html><body><p>" + "酒店送餐机器人主流品牌评测。" * 60 + "</p></body></html>"
    rich_fetcher = create_tiered_page_fetcher(
        browser_factory=lambda: (_ for _ in ()).throw(AssertionError("browser must not start")),
        direct_fetcher=lambda url: rich,
    )
    assert rich_fetcher("https://example.test/static") is not None
    assert calls == []


def test_headless_timeout_and_failure_keep_snippet() -> None:
    class _HangBrowser:
        def new_page(self) -> Any:
            raise ConnectionError("browser crashed")

    fetcher = create_tiered_page_fetcher(
        browser_factory=lambda: _HangBrowser(),
        direct_fetcher=lambda url: None,
    )
    assert fetcher("https://example.test/dead") is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd apps/miroflow-agent && uv run pytest -q -n0 tests/canonical_v2/test_web_page_fetch.py -k tiered or headless`
Expected: FAIL `ImportError: cannot import name 'create_tiered_page_fetcher'`

- [ ] **Step 3: 实现分层 fetcher**

`page_fetch.py` 追加（保留现有 `fetch_page_text` 为 T0 直连）：

```python
"""Tiered page fetching: direct fetch first, headless Chromium on thin shells."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from typing import Any, Callable

_MIN_RICH_TEXT_CHARS = 400
_SCRIPT_RATIO_LIMIT = 0.6
_BROWSER_TEXT_LIMIT = 4000
_BLOCK_MARKERS = ("访问验证", "安全验证", "请开启JavaScript", "请开启 JavaScript", "403 Forbidden", "Too Many Requests")


def _is_thin_or_blocked(html: str | None, text: str | None) -> bool:
    if not html and not text:
        return True
    if html and any(marker in html for marker in _BLOCK_MARKERS):
        return True
    if text is None or len(text.strip()) < _MIN_RICH_TEXT_CHARS:
        if html:
            script_len = sum(len(m.group(0)) for m in re.finditer(r"(?s)<script[^>]*>.*?</script>", html))
            if len(html) and script_len / len(html) > _SCRIPT_RATIO_LIMIT:
                return True
        return text is None or len(text.strip()) < _MIN_RICH_TEXT_CHARS
    return False


class _PlaywrightPagePool:
    def __init__(self, browser_factory: Callable[[], Any] | None) -> None:
        self._browser_factory = browser_factory
        self._browser: Any | None = None
        self._lock = Lock()
        self._semaphore = __import__("threading").BoundedSemaphore(2)

    def _browser_instance(self) -> Any:
        with self._lock:
            if self._browser is None:
                if self._browser_factory is not None:
                    self._browser = self._browser_factory()
                else:
                    from playwright.sync_api import sync_playwright

                    self._playwright = sync_playwright().start()
                    self._browser = self._playwright.chromium.launch(
                        headless=True,
                        args=["--disable-blink-features=AutomationControlled"],
                    )
            return self._browser

    def fetch(self, url: str, *, timeout_ms: int = 5000) -> str | None:
        with self._semaphore:
            page = self._browser_instance().new_page()
            try:
                page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
                text = page.eval_on_selector("body", "el => el.innerText")
            finally:
                page.close()
        if not isinstance(text, str) or not text.strip():
            return None
        return text.strip()[:_BROWSER_TEXT_LIMIT]


def create_tiered_page_fetcher(
    *,
    browser_factory: Callable[[], Any] | None = None,
    direct_fetcher: Callable[[str], str | None] | None = None,
) -> Callable[[str], str | None]:
    """T0 direct + T1 headless-on-thin. Any failure keeps the snippet (None)."""
    direct = direct_fetcher or fetch_page_text
    pool: _PlaywrightPagePool | None = None

    def fetch(url: str) -> str | None:
        nonlocal pool
        html_text = direct(url)
        if not _is_thin_or_blocked(html_text, html_text):
            return html_text
        if pool is None:
            pool = _PlaywrightPagePool(browser_factory)
        try:
            return pool.fetch(url)
        except Exception:  # noqa: BLE001 - headless failure keeps the snippet
            return html_text

    return fetch
```

并把 `knowledge_serving_isolated.py` / runner 中 `page_fetcher=fetch_page_text` 的接线改为 `page_fetcher=create_tiered_page_fetcher()`（保持参数名不变）。

- [ ] **Step 4: 跑测试 + 回归**

Run: `cd apps/miroflow-agent && uv run pytest -q -n0 tests/canonical_v2/test_web_page_fetch.py`
Expected: all passed
Run: `uv run pyright src/data_agents/providers/page_fetch.py`
Expected: 0 errors

- [ ] **Step 5: Commit**

```bash
git add apps/miroflow-agent/src/data_agents/providers/page_fetch.py apps/miroflow-agent/tests/canonical_v2/test_web_page_fetch.py
git commit -m "feat(canonical_v2): tiered page fetch with headless Chromium fallback"
```

---

### Task 6: 882 gate 降级 + 迁移分析

**Files:**
- Modify: `apps/miroflow-agent/src/data_agents/professor/release.py`（`missing_required_fields` 分支）
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12e/professor_gate_analysis.py`
- Test: `apps/miroflow-agent/tests/professor/test_release_gate.py`（新建或并入现有教授 release 测试文件，先 `ls apps/miroflow-agent/tests/professor/` 确认命名）

- [ ] **Step 1: 定位与确认 gate 规则**

Run: `cd apps/miroflow-agent && sed -n '80,130p' src/data_agents/professor/release.py && grep -n "missing_required_fields\|required" src/data_agents/professor/release.py | head -20`
Expected: 看到必填字段清单与 `skip_reasons["missing_required_fields"]` 计数；记录哪些字段当前必填（如 department）。

- [ ] **Step 2: 写失败测试**

```python
def test_professor_with_name_and_institution_is_admitted_with_quality_signal() -> None:
    """name+institution 即可入 release；缺 department 降级为 quality signal。"""
    record = {
        "name": "王学谦",
        "institution": "清华大学深圳国际研究生院",
        "title": "教授",
        # department 缺失
    }
    decision = evaluate_professor_record(record)  # 模块内现有判定函数名以 Step 1 定位为准
    assert decision.admitted is True
    assert "missing_department" in decision.quality_signals
    assert decision.limitations


def test_professor_missing_institution_is_still_rejected() -> None:
    record = {"name": "某人", "title": "教授"}
    decision = evaluate_professor_record(record)
    assert decision.admitted is False
```

- [ ] **Step 3: 跑测试确认失败**

Run: `cd apps/miroflow-agent && uv run pytest -q -n0 tests/professor/test_release_gate.py`
Expected: FAIL（王学谦类记录当前被拒）

- [ ] **Step 4: 改 gate 规则**

把必填字段硬排除改为：`name and institution` 为唯一硬条件；其余原必填字段（department 等）缺失时写入 `quality_signals`（如 `missing_department`）并附 limitation，不再计入 `missing_required_fields` skip。保持其它排除规则（重名/低质/越域）不变。

- [ ] **Step 5: 跑测试 + 回归**

Run: `cd apps/miroflow-agent && uv run pytest -q -n0 tests/professor/`
Expected: all passed（若有钉住旧必填行为的既有测试，逐一评估后按新语义校订并在 commit message 说明）

- [ ] **Step 6: 写迁移分析脚本并产出复核报告**

`s12e/professor_gate_analysis.py`：读候选库教授源（docker `canonical-v2-s12c-pg-20260726-r8` 的 professor 源表/landing.source_record），按新规则 dry-run 统计：放行（name+institution 满足）、仍拒（缺 institution）、需回填（高价值缺字段），输出 markdown 复核报告到 `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12e/professor-gate-report.md`。

Run: `cd apps/admin-console && uv run python ../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s12e/professor_gate_analysis.py --dry-run`
Expected: 报告生成，放行数 ≈ 882 中绝大多数，列出仍拒样例与理由。

- [ ] **Step 7: Commit**

```bash
git add apps/miroflow-agent/src/data_agents/professor/release.py apps/miroflow-agent/tests/professor/ .agents/runs/rebuild-canonical-v2-knowledge-platform/s12e/
git commit -m "fix(canonical_v2): admit professors on name+institution with quality signals"
```

---

### Task 7: 882 回填 + 候选重建 + 验收

**Files:**
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12e/professor_backfill.py`
- Modify: 无（重建走既有 `complete_candidate_runner.py` 构建路径）

- [ ] **Step 1: 高价值记录 web 回填**

`professor_backfill.py`：对 Step 6 报告中"放行但缺字段"且被 workbook/高频查询命中的人物（首批：王学谦及报告标注的高引用人物 ≤20 人），用现有 web search（Bocha/Serper）检索 `"<姓名> <机构> 院系 简介"`，取官方页摘要回填 department/research_directions，回填值带 `source_assertion`（URL+observed_at）写入 landing/source_record 的新批次 `s12e-professor-backfill-v1`。

- [ ] **Step 2: 隔离环境候选重建**

按既有构建命令（参照 `.agents/runs/.../s12c/` 的 r8 构建参数，换 `--run-id s12e-build-20260731-v1`、`--candidate-release-id candidate-s12e-20260731-v1`、source-batch 追加 `s12e-professor-backfill-v1`）在隔离 staging/index 目录重建候选；构建日志检查教授投影数 ≥ 554+882 的放行部分。

- [ ] **Step 3: 生成新 serving pack**

Run: `cd apps/admin-console && uv run python ../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s12c/build_serving_pack.py --envelope <新envelope> --index-root <新index> --pack-dir /var/tmp/mirothinker-canonical-v2-s12e/serving-pack --expected-release-id candidate-s12e-20260731-v1 --generator-run-id s12e-pack-20260731-v1`
Expected: pack 生成，dogfood_open 通过。

- [ ] **Step 4: 备选 release 冒烟（暂不切线上）**

用 pack 模式在 18199 端口起候选服务，live 验收：王学谦可答（含院系/研究方向）、丁文伯不受影响、酒店三连不回退、`/api/chat` 契约一致。

- [ ] **Step 5: Commit**

```bash
git add .agents/runs/rebuild-canonical-v2-knowledge-platform/s12e/
git commit -m "feat(canonical_v2): professor backfill batch and isolated candidate rebuild"
```

---

### Task 8: 终验（live 场景 + 全量回放 + 汇报）

- [ ] **Step 1: 全量回归**

Run: `cd apps/miroflow-agent && uv run pytest -q -n 4 tests/canonical_v2/ --ignore=tests/canonical_v2/test_knowledge_build_isolated.py --ignore=tests/canonical_v2/test_internal_reference_projection_contract.py --deselect tests/canonical_v2/test_consumer_migration_boundary.py::test_s11b_sanctioned_entrypoints_classify_and_exclude_legacy_consumers --deselect tests/canonical_v2/test_knowledge_read_answer_successor_handoff.py::test_blocking_planner_materializes_truthful_zero_option_clarification`
Expected: 全绿（passed，0 failed）；`cd apps/admin-console && uv run pytest -q tests/test_canonical_v2_referent_history.py tests/test_canonical_v2_session_evidence_carryover.py tests/test_canonical_v2_chat_http_adapter.py` 全绿；改动文件 ruff/pyright 0 错。

- [ ] **Step 2: 终版服务重启（pack 模式）并按场景清单 live 验收**

场景：酒店三连（KEY 五家尽量出齐，T3 闪电匣稳定）、早稻田（多人物）、丁文伯跨话题、王学谦（新 release）、开普勒（fetch 提取后）、概念题簇（12/13/14/16）、爱博合创、冯娟歧义、PCB×2。记录每题答案与 TTFT。

- [ ] **Step 3: 全量 Excel 双模式回放 + KEY 初筛**

Run: `customer_workbook_replay.py`（workers=4 与 `--single-session`）+ `workbook_key_coverage.py`
Expected: 25/25 ok、degenerate 0、KEY 硬失败归零（如仍有遗漏，记录为下一轮输入）。

- [ ] **Step 4: 更新 verification.md / change-log.md 并汇报**

按 2026-07-29/31 条目格式追加本轮：缺陷类、RED/GREEN 证据、回放数字、残留风险（LLM 判定抖动、无头浏览器成本、多轮 agentic 评估）与 rollback 说明。

---

## Self-Review 记录

- Spec 覆盖：§2 查询路径 → Task 1-4；§4 拆预筛/fail-open → Task 3（硬降级）+ Task 2（规则兜底语义）；§5 分层 fetch → Task 5；§6 882 → Task 6-7；§8 测试验收 → Task 8。§7 路线图项不实施（符合 spec）。
- 占位符：无 TBD/TODO；Step 6.1 中 `evaluate_professor_record` 标注"以 Step 1 定位为准"（该函数名需现场确认，属有意为之的环境核实步骤，非占位）。
- 类型一致性：`llm_judgments` 四个 schema 名在 Task 1 定义并在 Task 2/4 引用一致；`_accept_probe_hit` 参数表在 Task 2 定义与调用点一致；`gap_judge` 参数名 Task 4 一致；`_PlaywrightPagePool.fetch(url, timeout_ms=…)` 与 `create_tiered_page_fetcher` 闭包签名一致。
