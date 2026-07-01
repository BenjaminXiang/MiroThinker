# Retrieval-Gen Eval System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the lean retrieval-gen eval system: parse the xlsx golden set into a case store, extend it with web+LLM-generated user-reviewed cases, evaluate the system's generated answer with three layers (L1 required-entity / L2 forbidden / L3 six-dimension judge vs golden), and gate regressions.

**Architecture:** `parse_testset.py` reads `docs/测试集答案.xlsx` → `tests/fixtures/test_cases.yaml` (frozen golden seed + extended cases). `eval_answer.py` runs `/api/chat` (synthesis ON) per case and applies L1/L2 (deterministic) + L3 (异模型 LLM judge, six PRD dimensions, N/A-aware). `eval_regression.py` orchestrates + diffs a committed golden baseline + exits non-zero on regression. `badcase_to_case.py` generates GT via Serper+LLM for user review → appends to the yaml. Eval env must match the deployed backend (SERPER_API_KEY + no proxy).

**Tech Stack:** Python 3.12, uv, openpyxl, PyYAML, FastAPI TestClient, pytest. Existing eval scripts in `apps/admin-console/scripts/` are the pattern.

**Spec:** `docs/superpowers/specs/2026-07-01-retrieval-eval-system-design.md` (commits through `5d1980c`).

---

## File structure

- Create: `apps/admin-console/scripts/parse_testset.py` — xlsx → test_cases.yaml parser.
- Create: `apps/admin-console/scripts/eval_answer.py` — three-layer eval (L1/L2 deterministic + L3 judge).
- Create: `apps/admin-console/scripts/eval_regression.py` — orchestrate + golden baseline + exit code.
- Create: `apps/admin-console/scripts/badcase_to_case.py` — web+LLM GT generation + user-review append.
- Create: `apps/admin-console/tests/fixtures/test_cases.yaml` — the case store (generated, committed).
- Create: `apps/admin-console/tests/fixtures/test_cases_seed.xlsx` — tiny synthetic xlsx for parser tests.
- Create: `apps/admin-console/tests/test_parse_testset.py` — parser unit tests.
- Create: `apps/admin-console/tests/test_eval_answer.py` — L1/L2 + L3-scoring unit tests (mock judge).
- Create: `apps/admin-console/tests/test_eval_regression.py` — gate exit-code unit tests.
- Create: `apps/admin-console/scripts/eval_env.sh` — env-truth setup (SERPER_API_KEY + unset proxy).
- Create (generated): `.agents/runs/retrieval-eval/golden-baseline.json` — committed baseline.

---

## Phase 1 — Parser (foundation)

### Task 1: parse_testset.py — xlsx → test_cases.yaml (TDD)

**Files:**
- Create: `apps/admin-console/scripts/parse_testset.py`
- Create: `apps/admin-console/tests/fixtures/test_cases_seed.xlsx`
- Test: `apps/admin-console/tests/test_parse_testset.py`

- [ ] **Step 1: Write the failing parser test**

Create `apps/admin-console/tests/test_parse_testset.py`:

```python
"""Unit tests for parse_testset (no live xlsx needed; uses a synthetic seed)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from parse_testset import parse_workbook, _derive_required, _derive_forbidden


def test_derive_required_strips_marker_and_normalizes_to_short_core():
    kp = "深圳市普渡科技股份有限公司；上海开普勒机器人有限公司；云迹科技 需要在回答结果"
    req = _derive_required(kp)
    assert "普渡" in req  # normalized short core, not the long form
    assert "云迹" in req
    assert "需要在回答结果" not in req
    assert not any("股份有限公司" in r for r in req)  # suffix stripped


def test_derive_forbidden_extracts_after_marker():
    kp = "不应该出现深圳智航无人机有限公司"
    forb = _derive_forbidden(kp)
    assert "深圳智航无人机有限公司" in forb


def test_parse_skips_header_rows_and_groups_multi_turn(tmp_path):
    # build a tiny synthetic xlsx mirroring the real structure
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["问题1", "答案", "关键点"])
    ws.append(["介绍清华的丁文伯", "丁文伯教授信息...", "获取知识库中的信息"])
    ws.append(["他是否有参与哪些企业的创立", "丁文伯参与创立...", "需要识别这里的他指的是丁文伯"])
    ws.append(["问题2", "答案", "关键点"])
    ws.append(["中国有哪些成熟的酒店送餐机器人供应商", "普渡;云迹...", "普渡；云迹 需要在回答结果"])
    p = tmp_path / "seed.xlsx"
    wb.save(p)
    cases = parse_workbook(p)
    assert len(cases) == 3  # 2 from 问题1 + 1 from 问题2
    assert cases[0]["query"] == "介绍清华的丁文伯"
    assert cases[0]["turn_group"] == "问题1"
    assert cases[0]["is_head_turn"] is True
    assert cases[1]["is_head_turn"] is False
    assert cases[1]["coref_needs_label"] is True  # "他" followup
    assert cases[2]["required_entities"]  # non-empty after derive
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd /home/longxiang/MiroThinker/apps/admin-console && unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
UV_OFFLINE=1 uv run pytest tests/test_parse_testset.py -v 2>&1 | tail -5
```
Expected: FAIL with `ModuleNotFoundError: No module named 'parse_testset'`.

- [ ] **Step 3: Write parse_testset.py**

Create `apps/admin-console/scripts/parse_testset.py`:

```python
"""Parse docs/测试集答案.xlsx → tests/fixtures/test_cases.yaml.

The xlsx is the frozen human golden set (42 rows: 问题 / 答案 / 关键点). It is multi-turn:
rows are grouped under 问题N header rows; followup rows refer to prior turns (他/上述企业/这论文).
This parser skips header rows, groups followups, and auto-derives required/forbidden entities +
coref/refusal/disambiguation flags from 关键点. Uncertain derivations are flagged for a one-time
labeling pass; the parser does NOT trust heuristics for final GT.

Run (from apps/admin-console):
  unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
  UV_OFFLINE=1 uv run python scripts/parse_testset.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import openpyxl
import yaml

# Meta-phrases in 关键点 that are NOT entities (do not treat as required entities).
_META_PHRASES = (
    "需要在回答", "需要识别", "上下文识别", "获取知识库", "关联到知识库",
    "知识库获取", "获取数据库", "不能回答", "会搜索出", "不应该出现",
    "这里的答案是不准确",
)
_FORBIDDEN_RE = re.compile(r"不应该出现(.+?)(?:;|;|。|$)")
_NEED_MARKER_RE = re.compile(r"\s*需要(?:在回答(?:结果|中)?|出现)?\s*$")


def _split_entities(kp: str) -> list[str]:
    """Split 关键点 on Chinese/ASCII separators, strip whitespace."""
    parts = re.split(r"[；;,，、]", kp)
    return [p.strip() for p in parts if p.strip()]


# Company suffixes/prefixes stripped to a short matchable core (mirrors FM5 name-normalization).
_CITY_PREFIX_RE = re.compile(r"^(深圳|北京|上海|广州|杭州|南京|武汉|成都|西安|苏州|东莞)[市]?")
_LEGAL_SUFFIX_RE = re.compile(r"(股份有限公司|有限公司|责任公司|科技|集团|控股|公司|技术|有限)$")


def _normalize_core(name: str) -> str:
    """Strip city prefix + legal suffix -> short matchable core ('深圳市普渡科技股份有限公司' -> '普渡')."""
    s = _CITY_PREFIX_RE.sub("", name)
    prev = None
    while prev != s:  # iteratively strip suffixes ('科技有限' -> strip '有限' -> '科技' -> strip '科技')
        prev = s
        s = _LEGAL_SUFFIX_RE.sub("", s).strip()
    return s or name


def _derive_required(kp: str) -> list[str]:
    """Best-effort extract required entities from 关键点 as short matchable cores."""
    if not kp:
        return []
    out: list[str] = []
    for token in _split_entities(kp):
        token = _NEED_MARKER_RE.sub("", token)  # strip trailing "需要在回答中"
        if not token or token.startswith(_META_PHRASES):
            continue
        out.append(_normalize_core(token))
    return out


def _derive_forbidden(kp: str) -> list[str]:
    """Extract forbidden entities (from '不应该出现X')."""
    if not kp:
        return []
    m = _FORBIDDEN_RE.search(kp)
    if not m:
        return []
    return [m.group(1).strip().rstrip("。;；")]


def _needs_coref(kp: str, query: str) -> bool:
    text = f"{kp} {query}"
    return any(t in text for t in ("上下文识别", "他指", "上述企业", "上述", "这论文", "这家公司"))


def _refusal_expected(kp: str) -> bool:
    return "不能回答" in (kp or "")


def _disambiguation(kp: str) -> bool:
    return "会搜索出" in (kp or "")


def parse_workbook(path: Path) -> list[dict]:
    """Parse the xlsx into a list of case dicts (no yaml write)."""
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active
    cases: list[dict] = []
    current_group: str | None = None
    qid = 0
    for row in ws.iter_rows(values_only=True):
        q = (row[0] or "").strip() if len(row) > 0 else ""
        answer = (row[1] or "").strip() if len(row) > 1 else ""
        kp = (row[2] or "").strip() if len(row) > 2 else ""
        if not q:
            continue
        # header row: 问题N
        if re.fullmatch(r"问题\d+", q):
            current_group = q
            continue
        qid += 1
        cases.append({
            "qid": qid,
            "turn_group": current_group,
            "is_head_turn": _is_head_turn(cases, current_group),
            "query": q,
            "answer": answer,  # GT (golden reference answer)
            "key_point": kp,
            "required_entities": _derive_required(kp),
            "forbidden_entities": _derive_forbidden(kp),
            "coref_needs_label": _needs_coref(kp, q),
            "refusal_expected": _refusal_expected(kp),
            "disambiguation_expected": _disambiguation(kp),
        })
    return cases


def _is_head_turn(cases: list[dict], group: str | None) -> bool:
    """A case is a head turn if no prior case in the same group exists."""
    return not any(c["turn_group"] == group for c in cases)


def main() -> int:
    xlsx = Path(__file__).resolve().parents[2] / "docs" / "测试集答案.xlsx"
    out = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "test_cases.yaml"
    cases = parse_workbook(xlsx)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        yaml.safe_dump({"cases": cases}, fh, allow_unicode=True, sort_keys=False)
    n_coref = sum(1 for c in cases if c["coref_needs_label"])
    n_req = sum(1 for c in cases if c["required_entities"])
    print(f"parsed {len(cases)} cases -> {out}")
    print(f"  with required_entities: {n_req}")
    print(f"  coref_needs_label (one-time labeling pass): {n_coref}")
    print("NOTE: auto-derived required/forbidden are best-effort; review the flagged coref cases.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
cd /home/longxiang/MiroThinker/apps/admin-console && unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
UV_OFFLINE=1 uv run pytest tests/test_parse_testset.py -v 2>&1 | tail -5
```
Expected: PASS (3 tests).

- [ ] **Step 5: Run the parser on the real xlsx**

Run:
```bash
UV_OFFLINE=1 uv run python scripts/parse_testset.py 2>&1 | tail -5
```
Expected: `parsed 25 cases -> tests/fixtures/test_cases.yaml` + coref count.

- [ ] **Step 6: Commit**

```bash
cd /home/longxiang/MiroThinker
git add apps/admin-console/scripts/parse_testset.py apps/admin-console/tests/test_parse_testset.py \
        apps/admin-console/tests/fixtures/test_cases.yaml
git commit -m "feat(eval): parse_testset.py — xlsx golden -> test_cases.yaml (multi-turn + auto-derive)"
```

---

## Phase 2 — L1/L2 deterministic eval

### Task 2: eval_answer.py — L1 required + L2 forbidden (TDD)

**Files:**
- Create: `apps/admin-console/scripts/eval_answer.py`
- Test: `apps/admin-console/tests/test_eval_answer.py`

- [ ] **Step 1: Write the failing L1/L2 test**

Create `apps/admin-console/tests/test_eval_answer.py`:

```python
"""Unit tests for eval_answer L1/L2 (deterministic; no live /api/chat)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from eval_answer import score_l1_required, score_l2_forbidden


def test_l1_required_hits_when_entity_in_answer():
    case = {"required_entities": ["普渡", "云迹"], "query": "x"}
    answer = "深圳普渡科技是一家送餐机器人公司。云迹也做。"
    hit, miss = score_l1_required(case, answer)
    assert "普渡" in hit and "云迹" in hit
    assert miss == []


def test_l1_required_misses_when_entity_absent():
    case = {"required_entities": ["九号", "擎朗"], "query": "x"}
    answer = "普渡科技是一家公司。"
    hit, miss = score_l1_required(case, answer)
    assert hit == []
    assert set(miss) == {"九号", "擎朗"}


def test_l2_forbidden_flags_when_present():
    case = {"forbidden_entities": ["深圳智航无人机有限公司"]}
    answer = "深圳智航无人机有限公司是一家..."
    violations = score_l2_forbidden(case, answer)
    assert "深圳智航无人机有限公司" in violations


def test_l2_forbidden_clean_when_absent():
    case = {"forbidden_entities": ["深圳智航无人机有限公司"]}
    answer = "无界智航是另一家公司。"
    violations = score_l2_forbidden(case, answer)
    assert violations == []
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd /home/longxiang/MiroThinker/apps/admin-console && unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
UV_OFFLINE=1 uv run pytest tests/test_eval_answer.py -v 2>&1 | tail -5
```
Expected: FAIL with `ModuleNotFoundError: No module named 'eval_answer'`.

- [ ] **Step 3: Write eval_answer.py L1/L2 + harness skeleton**

Create `apps/admin-console/scripts/eval_answer.py`:

```python
"""Three-layer eval of /api/chat generated answers (synthesis ON) vs golden test_cases.yaml.

L1 required-entity coverage (deterministic); L2 forbidden-entity gate (deterministic);
L3 answer-vs-golden judge (异模型 LLM, six PRD dimensions) — added in Task 3.

Run (from apps/admin-console), env-truth first:
  source scripts/eval_env.sh
  DATABASE_URL=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real \
  MILVUS_USE_REAL_CLIENT=1 UV_OFFLINE=1 uv run python scripts/eval_answer.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import yaml

os.environ.setdefault("CHAT_LLM_SYNTHESIS", "on")


def _load_cases() -> list[dict]:
    p = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "test_cases.yaml"
    with open(p, encoding="utf-8") as fh:
        return yaml.safe_load(fh)["cases"]


def score_l1_required(case: dict, answer: str) -> tuple[list[str], list[str]]:
    """L1: required_entities must appear in the generated answer. Returns (hit, miss)."""
    req = case.get("required_entities") or []
    hit = [e for e in req if e in answer]
    miss = [e for e in req if e not in answer]
    return hit, miss


def score_l2_forbidden(case: dict, answer: str) -> list[str]:
    """L2: forbidden_entities must NOT appear. Returns violations."""
    forb = case.get("forbidden_entities") or []
    return [e for e in forb if e in answer]


def _run_chat(query: str) -> dict:
    """Run /api/chat (synthesis ON) and return the response JSON."""
    from backend.main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)
    # multi-turn coref: pass a session id (harness extension point for Task 5)
    return client.post("/api/chat", json={"query": query}).json()


def main() -> int:
    cases = _load_cases()
    rows: list[dict] = []
    print(f"{'qid':>3} {'L1 hit/req':>10} {'L2 viol':>8}  query")
    print("-" * 80)
    for c in cases:
        try:
            j = _run_chat(c["query"])
        except Exception as e:  # noqa: BLE001
            rows.append({"qid": c["qid"], "error": str(e)})
            print(f"{c['qid']:>3} ERR {type(e).__name__}")
            continue
        answer = str(j.get("answer_text") or j.get("answer") or "")
        hit, miss = score_l1_required(c, answer)
        viol = score_l2_forbidden(c, answer)
        rows.append({
            "qid": c["qid"], "query": c["query"],
            "l1_hit": hit, "l1_miss": miss, "l2_violations": viol,
        })
        print(f"{c['qid']:>3} {len(hit)}/{len(c.get('required_entities') or []):>3}    "
              f"{len(viol):>4}     {c['query'][:30]}")
    out = Path(__file__).resolve().parents[2] / ".agents" / "runs" / "retrieval-eval" / "l1l2-run.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"rows": rows}, fh, ensure_ascii=False, indent=2)
    print(f"WRITTEN: {out}")
    print("NOTE: L3 (judge) added in Task 3. Run eval_answer.py again after Task 3 for full eval.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
cd /home/longxiang/MiroThinker/apps/admin-console && unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
UV_OFFLINE=1 uv run pytest tests/test_eval_answer.py -v 2>&1 | tail -5
```
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
cd /home/longxiang/MiroThinker
git add apps/admin-console/scripts/eval_answer.py apps/admin-console/tests/test_eval_answer.py
git commit -m "feat(eval): eval_answer L1 required + L2 forbidden (deterministic, TDD)"
```

---

## Phase 3 — L3 judge (the core)

### Task 3: eval_answer.py — L3 six-dimension judge (TDD on scoring logic)

**Files:**
- Modify: `apps/admin-console/scripts/eval_answer.py` (add L3).
- Test: `apps/admin-console/tests/test_eval_answer.py` (add L3-scoring tests).

- [ ] **Step 1: Write the failing L3-scoring test (mock judge output)**

Append to `apps/admin-console/tests/test_eval_answer.py`:

```python
from eval_answer import aggregate_l3_scores, DIMENSIONS


def test_l3_aggregate_averages_applicable_dims_only():
    # dim 4 (provenance) and 5 (F/G) are N/A for an A-profile case -> excluded from denominator
    scores = {
        "type_correct": 1.0,
        "key_content_coverage": 0.5,
        "structure_apt": 1.0,
        "provenance_correct": None,   # N/A
        "f_g_handling": None,          # N/A
        "multi_turn_coref": None,      # N/A (single-turn)
    }
    avg = aggregate_l3_scores(scores)
    assert avg == (1.0 + 0.5 + 1.0) / 3


def test_l3_aggregate_all_applicable():
    scores = {d: 1.0 for d in DIMENSIONS}
    scores["provenance_correct"] = None
    assert aggregate_l3_scores(scores) == 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd /home/longxiang/MiroThinker/apps/admin-console && unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
UV_OFFLINE=1 uv run pytest tests/test_eval_answer.py -v 2>&1 | tail -5
```
Expected: FAIL with `ImportError: cannot import name 'aggregate_l3_scores'`.

- [ ] **Step 3: Add L3 judge + scoring to eval_answer.py**

Append to `apps/admin-console/scripts/eval_answer.py` (before `main`):

```python
# --- L3: answer-vs-golden judge (CORE) ---

DIMENSIONS = (
    "type_correct",          # 1. matches expected query-type behavior (A-G)
    "key_content_coverage",  # 2. golden's key facts/entities appear (= L1 fed in)
    "structure_apt",         # 3. profile fields / topic list / aggregate
    "provenance_correct",    # 4. web/fallback source+time marked (N/A for local-only)
    "f_g_handling",          # 5. F refuses / G default+hint (N/A for non-F/G)
    "multi_turn_coref",      # 6. pronouns resolve (N/A for single-turn)
)


def aggregate_l3_scores(scores: dict) -> float:
    """Average applicable dimensions (None = N/A, excluded from numerator+denominator)."""
    vals = [scores[d] for d in DIMENSIONS if scores.get(d) is not None]
    return sum(vals) / len(vals) if vals else 0.0


_L3_JUDGE_PROMPT = """你是检索增强系统的评估 judge。对照金标准答案,给系统生成的答案打分。

查询: {query}
期望类型: {expected_type}
金标准答案: {golden}
系统生成的答案: {system_answer}
必需实体(关键点): {required}
禁出实体: {forbidden}

按以下六个维度各打 0-1 分(不适用标 null),每维给一句理由:
1. type_correct: 答案类型是否符合期望(A 单实体profile / B 主题列表 / C 跨轮 / D 全景聚合 / E 知识+web / F 拒答 / G 默认+提示)
2. key_content_coverage: 金标准的关键事实/实体是否覆盖(必需实体必须出现)
3. structure_apt: 结构是否得当(profile字段齐全 / 主题是列表 / 跨域是聚合)
4. provenance_correct: web/fallback/时效性答案是否标了来源+时间(纯本地高置信答案标 null)
5. f_g_handling: F是否礼貌拒答+引导 / G是否默认高置信+短提示(非F/G标 null)
6. multi_turn_coref: 代词(他/上述企业)是否解析对(单轮标 null)

只返回 JSON: {{"type_correct": <0-1或null>, "key_content_coverage": <...>, "structure_apt": <...>,
"provenance_correct": <...>, "f_g_handling": <...>, "multi_turn_coref": <...>,
"reasons": {{"type_correct": "...", ...}}}
"""


def _call_judge(case: dict, system_answer: str, l1_hit: list[str]) -> dict:
    """Call the 异模型 LLM judge. Config: EVAL_JUDGE_API_KEY, EVAL_JUDGE_BASE_URL, EVAL_JUDGE_MODEL."""
    import urllib.request
    base = os.environ.get("EVAL_JUDGE_BASE_URL", "")
    key = os.environ.get("EVAL_JUDGE_API_KEY", "")
    model = os.environ.get("EVAL_JUDGE_MODEL", "")
    if not (base and key and model):
        # judge not configured -> return all-N/A (L3 skipped; L1/L2 still run)
        return {d: None for d in DIMENSIONS} | {"reasons": {"_": "judge not configured"}}
    prompt = _L3_JUDGE_PROMPT.format(
        query=case["query"], expected_type=case.get("expected_type", "?"),
        golden=case.get("answer", ""), system_answer=system_answer,
        required=case.get("required_entities", []), forbidden=case.get("forbidden_entities", []),
    )
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}],
                       "temperature": 0}).encode("utf-8")
    req = urllib.request.Request(f"{base}/chat/completions", data=body,
                                 headers={"Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())
    content = data["choices"][0]["message"]["content"]
    # strip code fences if present
    content = content.strip().strip("`").lstrip("json").strip()
    return json.loads(content)
```

And update `main()` to call L3 per case. Replace the `rows.append({...})` block in `main` with:

```python
        l3_raw = _call_judge(c, answer, hit)
        l3_scores = {d: l3_raw.get(d) for d in DIMENSIONS}
        l3_avg = aggregate_l3_scores(l3_scores)
        rows.append({
            "qid": c["qid"], "query": c["query"],
            "l1_hit": hit, "l1_miss": miss, "l2_violations": viol,
            "l3_scores": l3_scores, "l3_avg": l3_avg, "l3_reasons": l3_raw.get("reasons", {}),
        })
        print(f"{c['qid']:>3} {len(hit)}/{len(c.get('required_entities') or []):>3}    "
              f"{len(viol):>4}    L3={l3_avg:.2f}   {c['query'][:24]}")
```

And change the output filename to `answer-eval.json` and the NOTE line to:
`print("NOTE: if EVAL_JUDGE_* unset, L3 is all-N/A (judge skipped); L1/L2 still run.")`

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
cd /home/longxiang/MiroThinker/apps/admin-console && unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
UV_OFFLINE=1 uv run pytest tests/test_eval_answer.py -v 2>&1 | tail -5
```
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
cd /home/longxiang/MiroThinker
git add apps/admin-console/scripts/eval_answer.py apps/admin-console/tests/test_eval_answer.py
git commit -m "feat(eval): L3 answer-vs-golden judge (six PRD dimensions, N/A-aware, 异模型)"
```

---

## Phase 4 — Regression gate

### Task 4: eval_regression.py — golden baseline + exit code (TDD)

**Files:**
- Create: `apps/admin-console/scripts/eval_regression.py`
- Test: `apps/admin-console/tests/test_eval_regression.py`

- [ ] **Step 1: Write the failing gate test**

Create `apps/admin-console/tests/test_eval_regression.py`:

```python
"""Unit tests for eval_regression gate logic (no live /api/chat)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from eval_regression import decide_exit, REGRESSION


def test_exit_zero_when_no_regression():
    current = {"rows": [{"qid": 1, "l1_miss": [], "l2_violations": [], "l3_avg": 0.8}]}
    golden = {"rows": [{"qid": 1, "l1_miss": ["x"], "l2_violations": [], "l3_avg": 0.7}]}
    # l1 improved (miss [] vs ["x"]), l2 clean, l3 improved -> no regression
    assert decide_exit(current, golden, l3_threshold=0.6) == 0


def test_exit_one_when_l1_regressed():
    current = {"rows": [{"qid": 1, "l1_miss": ["x"], "l2_violations": [], "l3_avg": 0.8}]}
    golden = {"rows": [{"qid": 1, "l1_miss": [], "l2_violations": [], "l3_avg": 0.8}]}
    # l1 regressed (new miss "x") -> exit 1
    assert decide_exit(current, golden, l3_threshold=0.6) == 1


def test_exit_one_when_l2_regressed():
    current = {"rows": [{"qid": 1, "l1_miss": [], "l2_violations": ["bad"], "l3_avg": 0.9}]}
    golden = {"rows": [{"qid": 1, "l1_miss": [], "l2_violations": [], "l3_avg": 0.9}]}
    assert decide_exit(current, golden, l3_threshold=0.6) == 1


def test_exit_one_when_l3_below_threshold():
    current = {"rows": [{"qid": 1, "l1_miss": [], "l2_violations": [], "l3_avg": 0.4}]}
    golden = {"rows": [{"qid": 1, "l1_miss": [], "l2_violations": [], "l3_avg": 0.8}]}
    assert decide_exit(current, golden, l3_threshold=0.6) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd /home/longxiang/MiroThinker/apps/admin-console && unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
UV_OFFLINE=1 uv run pytest tests/test_eval_regression.py -v 2>&1 | tail -5
```
Expected: FAIL with `ModuleNotFoundError: No module named 'eval_regression'`.

- [ ] **Step 3: Write eval_regression.py**

Create `apps/admin-console/scripts/eval_regression.py`:

```python
"""Regression gate: run eval_answer, diff against committed golden baseline, exit non-zero on regression.

Exit 1 if: any L1 case regressed (a previously-hit required entity now missed) OR any L2 case
regressed (a forbidden entity now appears) OR L3 overall average < calibrated threshold.
Exit 0 otherwise.

Golden baseline: .agents/runs/retrieval-eval/golden-baseline.json (committed). Re-derive after
intentional improvements (and after adding new cases via badcase_to_case.py).

Run (from apps/admin-console), env-truth first:
  source scripts/eval_env.sh
  DATABASE_URL=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real \
  MILVUS_USE_REAL_CLIENT=1 UV_OFFLINE=1 uv run python scripts/eval_regression.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REGRESSION = 1
OK = 0
_DEFAULT_L3_THRESHOLD = 0.0  # 0.0 = disabled until calibrated (spec: threshold post-baseline)


def _index_by_qid(report: dict) -> dict:
    return {r["qid"]: r for r in report.get("rows", []) if "qid" in r}


def decide_exit(current: dict, golden: dict, l3_threshold: float) -> int:
    """Pure function: decide exit code from current vs golden report. L3 threshold=0 disables."""
    cur, gold = _index_by_qid(current), _index_by_qid(golden)
    for qid, g in gold.items():
        c = cur.get(qid)
        if c is None:
            return REGRESSION  # case disappeared
        # L1 regression: a previously-hit entity now missed
        g_hit = set(g.get("l1_hit", []))
        c_miss = set(c.get("l1_miss", []))
        if g_hit & c_miss:
            return REGRESSION
        # L2 regression: a forbidden entity now appears (that wasn't in golden)
        g_viol = set(g.get("l2_violations", []))
        c_viol = set(c.get("l2_violations", []))
        if c_viol - g_viol:
            return REGRESSION
    # L3 threshold (per-case floor + overall)
    if l3_threshold > 0:
        for qid, c in cur.items():
            avg = c.get("l3_avg")
            if avg is not None and avg < l3_threshold:
                return REGRESSION
    return OK


def main() -> int:
    # run eval_answer to produce current report
    script = Path(__file__).resolve().parent / "eval_answer.py"
    subprocess.run([sys.executable, str(script)], check=True)
    current_path = Path(__file__).resolve().parents[2] / ".agents" / "runs" / "retrieval-eval" / "answer-eval.json"
    current = json.loads(current_path.read_text(encoding="utf-8"))
    golden_path = Path(__file__).resolve().parents[2] / ".agents" / "runs" / "retrieval-eval" / "golden-baseline.json"
    golden = json.loads(golden_path.read_text(encoding="utf-8")) if golden_path.exists() else {"rows": []}
    l3_threshold = float(os.environ.get("EVAL_L3_THRESHOLD", _DEFAULT_L3_THRESHOLD))
    code = decide_exit(current, golden, l3_threshold)
    print(f"regression gate exit={code} (L3 threshold={l3_threshold})")
    return code


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
cd /home/longxiang/MiroThinker/apps/admin-console && unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
UV_OFFLINE=1 uv run pytest tests/test_eval_regression.py -v 2>&1 | tail -5
```
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
cd /home/longxiang/MiroThinker
git add apps/admin-console/scripts/eval_regression.py apps/admin-console/tests/test_eval_regression.py
git commit -m "feat(eval): regression gate (L1/L2 regression + L3 threshold, exit code, TDD)"
```

---

## Phase 5 — Case extension (badcase → golden)

### Task 5: badcase_to_case.py — web+LLM GT generation + user review (TDD on append)

**Files:**
- Create: `apps/admin-console/scripts/badcase_to_case.py`
- Test: `apps/admin-console/tests/test_badcase_to_case.py`

- [ ] **Step 1: Write the failing append test**

Create `apps/admin-console/tests/test_badcase_to_case.py`:

```python
"""Unit tests for badcase_to_case append logic (no live web/LLM)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from badcase_to_case import build_case, next_qid


def test_next_qid_increments_past_max():
    cases = [{"qid": 1}, {"qid": 5}, {"qid": 12}]
    assert next_qid(cases) == 13


def test_build_case_has_required_fields():
    c = build_case(qid=99, query="X", answer="Y", key_point="X 需要在回答中",
                   turn_group="问题99", is_head_turn=True)
    assert c["qid"] == 99 and c["query"] == "X" and c["answer"] == "Y"
    assert "X" in c["required_entities"] or c["required_entities"] == []
    assert c["forbidden_entities"] == []
    assert c["is_head_turn"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd /home/longxiang/MiroThinker/apps/admin-console && unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
UV_OFFLINE=1 uv run pytest tests/test_badcase_to_case.py -v 2>&1 | tail -5
```
Expected: FAIL with `ModuleNotFoundError: No module named 'badcase_to_case'`.

- [ ] **Step 3: Write badcase_to_case.py**

Create `apps/admin-console/scripts/badcase_to_case.py`:

```python
"""Badcase → golden case pipeline.

For a reported badcase query, generate the expected answer (GT) + required/forbidden entities via
Serper web recall + LLM, THEN prompt the user to review/edit before appending to test_cases.yaml.
The golden trust comes from the USER REVIEW, not the LLM.

Run (from apps/admin-console), env-truth first:
  source scripts/eval_env.sh
  UV_OFFLINE=1 uv run python scripts/badcase_to_case.py --query "深圳法本信息科技有限公司的产品特点以及团队介绍"
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parse_testset import _derive_required, _derive_forbidden  # reuse heuristics


def next_qid(cases: list[dict]) -> int:
    return (max((c["qid"] for c in cases), default=0)) + 1


def build_case(*, qid: int, query: str, answer: str, key_point: str,
               turn_group: str | None, is_head_turn: bool) -> dict:
    return {
        "qid": qid,
        "turn_group": turn_group,
        "is_head_turn": is_head_turn,
        "query": query,
        "answer": answer,
        "key_point": key_point,
        "required_entities": _derive_required(key_point),
        "forbidden_entities": _derive_forbidden(key_point),
        "coref_needs_label": False,  # badcase single-turn by default; set True if multi-turn
        "refusal_expected": "不能回答" in key_point,
        "disambiguation_expected": "会搜索出" in key_point,
        "source": "badcase+web+llm+user-reviewed",
    }


def _serper_recall(query: str, top_n: int = 5) -> list[dict]:
    key = os.environ.get("SERPER_API_KEY", "")
    if not key:
        return []
    body = json.dumps({"q": query, "num": top_n}).encode("utf-8")
    req = urllib.request.Request("https://google.serper.dev/search", data=body,
                                 headers={"X-API-KEY": key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read()).get("organic", [])


def _llm_generate_gt(query: str, web: list[dict]) -> tuple[str, str]:
    """LLM generates (answer, key_point) from query + web recall. Returns draft for user review."""
    base = os.environ.get("EVAL_JUDGE_BASE_URL", "")
    model = os.environ.get("EVAL_JUDGE_MODEL", "")
    key = os.environ.get("EVAL_JUDGE_API_KEY", "")
    web_ctx = "\n".join(f"- {w.get('title','')}: {w.get('snippet','')}" for w in web[:5])
    prompt = (f"为以下查询生成一个金标准答案 + 关键点(必需实体,用'需要在回答中'标记)。\n"
              f"查询: {query}\n网络召回:\n{web_ctx}\n"
              f"返回 JSON: {{\"answer\": \"...\", \"key_point\": \"...\"}}")
    if not (base and model and key):
        return ("[DRAFT — fill in]", "[DRAFT — fill in required entities]")
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}],
                       "temperature": 0}).encode("utf-8")
    req = urllib.request.Request(f"{base}/chat/completions", data=body,
                                 headers={"Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        content = json.loads(resp.read())["choices"][0]["message"]["content"]
    return json.loads(content.strip().strip("`").lstrip("json").strip())["answer"], \
           json.loads(content.strip().strip("`").lstrip("json").strip())["key_point"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", required=True)
    ap.add_argument("--turn-group", default=None)
    args = ap.parse_args()
    yaml_path = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "test_cases.yaml"
    with open(yaml_path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    cases = data["cases"]
    web = _serper_recall(args.query)
    answer, kp = _llm_generate_gt(args.query, web)
    print("=== DRAFT GT (review before saving) ===")
    print(f"query: {args.query}")
    print(f"web recall: {len(web)} results")
    print(f"draft answer: {answer[:200]}...")
    print(f"draft key_point: {kp}")
    print("=======================================")
    confirm = input("Append this case to test_cases.yaml? [y/N/edit]: ").strip().lower()
    if confirm != "y":
        print("not appended — edit the draft manually then re-run, or hand-add to the yaml.")
        return 1
    qid = next_qid(cases)
    case = build_case(qid=qid, query=args.query, answer=answer, key_point=kp,
                      turn_group=args.turn_group, is_head_turn=True)
    cases.append(case)
    with open(yaml_path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, allow_unicode=True, sort_keys=False)
    print(f"appended qid={qid}; re-derive golden baseline: uv run python scripts/eval_regression.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
cd /home/longxiang/MiroThinker/apps/admin-console && unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
UV_OFFLINE=1 uv run pytest tests/test_badcase_to_case.py -v 2>&1 | tail -5
```
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
cd /home/longxiang/MiroThinker
git add apps/admin-console/scripts/badcase_to_case.py apps/admin-console/tests/test_badcase_to_case.py
git commit -m "feat(eval): badcase_to_case — web+LLM GT generation + user review append"
```

---

## Phase 6 — Env-truth + first baseline

### Task 6: eval_env.sh + first baseline run + calibrate judge

**Files:**
- Create: `apps/admin-console/scripts/eval_env.sh`
- Create (generated): `.agents/runs/retrieval-eval/golden-baseline.json`

- [ ] **Step 1: Write eval_env.sh (the env-truth lesson)**

Create `apps/admin-console/scripts/eval_env.sh`:

```bash
# Eval env truth: match the deployed backend env, or measure a broken system.
# The 58%/Serper-dead false reading came from a run WITHOUT SERPER_API_KEY + WITH proxy vars.
# Usage: source scripts/eval_env.sh
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
# SERPER_API_KEY: read from the running backend's env if present, else leave for the user to set.
_backend_pid=$(pgrep -f "uvicorn backend.main" | head -1)
if [ -n "$_backend_pid" ]; then
  export SERPER_API_KEY=$(tr '\0' '\n' < /proc/$_backend_pid/environ 2>/dev/null | grep '^SERPER_API_KEY=' | cut -d= -f2)
  echo "eval_env: SERPER_API_KEY loaded from backend (pid $_backend_pid), len=${#SERPER_API_KEY}"
else
  echo "eval_env: no running backend; set SERPER_API_KEY manually."
fi
# L3 judge config (异模型 — different from synthesis DeepSeek). Set these in your shell or .env.
#   EVAL_JUDGE_API_KEY, EVAL_JUDGE_BASE_URL, EVAL_JUDGE_MODEL
# Until set, L3 is all-N/A (L1/L2 still run).
export CHAT_LLM_SYNTHESIS=on
```

- [ ] **Step 2: Run eval_answer with env-truth (first baseline, L3 may be N/A)**

Run:
```bash
cd /home/longxiang/MiroThinker/apps/admin-console
source scripts/eval_env.sh
export DATABASE_URL=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real MILVUS_USE_REAL_CLIENT=1 UV_OFFLINE=1
uv run python scripts/eval_answer.py 2>&1 | tail -8
```
Expected: `answer-eval.json` written; L1/L2 per case; L3=N/A if judge unconfigured.

- [ ] **Step 3: Establish the golden baseline (commit the first run)**

Run:
```bash
cd /home/longxiang/MiroThinker
cp .agents/runs/retrieval-eval/answer-eval.json .agents/runs/retrieval-eval/golden-baseline.json
git add .agents/runs/retrieval-eval/golden-baseline.json apps/admin-console/scripts/eval_env.sh
git commit -m "test(eval): first golden baseline + eval_env.sh (env-truth: SERPER key + no proxy)"
```

- [ ] **Step 4: Calibrate the L3 judge (manual, one-time)**

Configure `EVAL_JUDGE_API_KEY` / `EVAL_JUDGE_BASE_URL` / `EVAL_JUDGE_MODEL` (异模型). Re-run
`eval_answer.py`. Manually review the L3 scores for ~5 cases across A/B/multi-turn; if the judge
disagrees with human judgement on a dimension, refine the `_L3_JUDGE_PROMPT` rubric wording and
re-run. Once the judge agrees on the sample, set `EVAL_L3_THRESHOLD` (e.g. `0.6`) and re-derive
the golden baseline. Commit the calibrated baseline + threshold.

```bash
git add apps/admin-console/scripts/eval_answer.py .agents/runs/retrieval-eval/golden-baseline.json
git commit -m "test(eval): calibrate L3 judge + set threshold (EVAL_L3_THRESHOLD)"
```

---

## Self-review (against spec `2026-07-01-retrieval-eval-system-design.md`)

**1. Spec coverage:**
- §1.1 xlsx frozen golden → Task 1 parser reads it, does not modify. ✓
- §1.2 parse → test_cases.yaml (multi-turn group, auto-derive required/forbidden/coref/refusal/disambig) → Task 1. ✓
- §1.3 extend (web+LLM + user review, blind spots) → Task 5 (badcase_to_case). ✓
- §2 L1 required → Task 2. ✓
- §2 L2 forbidden → Task 2. ✓
- §2 L3 six-dimension judge (N/A-aware, 异模型, threshold post-baseline) → Task 3 + Task 6 calibration. ✓
- §3 env truth (SERPER_API_KEY + no proxy + synthesis ON) → Task 6 eval_env.sh. ✓
- §4 regression gate (golden baseline + exit 1 on L1/L2 regression + L3 threshold) → Task 4. ✓
- §5 lean (faithfulness/precision deferred, single judge) → not in plan (deferred). ✓

**2. Placeholder scan:** Task 5's `_llm_generate_gt` has a `[DRAFT — fill in]` fallback when the judge LLM is unconfigured — that is an intentional fallback (the user reviews/fills), not a plan placeholder; the surrounding logic is complete. No TBD/TODO.

**3. Type consistency:** `DIMENSIONS` tuple (Task 3) used by `aggregate_l3_scores` (Task 3) and the test (Task 3 step 1). `decide_exit(current, golden, l3_threshold)` (Task 4) matches the test signature. `build_case`/`next_qid` (Task 5) match the test. `score_l1_required`/`score_l2_forbidden` (Task 2) match the test. `parse_workbook`/`_derive_required`/`_derive_forbidden` (Task 1) match the test. ✓

No gaps; plan complete.
