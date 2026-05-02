---
title: "W11-7: profile_summary 用 raw_text + 全量回填"
date: 2026-05-02
owner: claude
status: ready-for-codex
audience: codex（实施）；claude review + 操作回填
wave: Wave 11
gap: "#41 (插队)"
plan: docs/plans/2026-04-28-portfolio-update-wave-9-to-13.md
related_specs:
  - .agents/specs/2026-04-30-w9-1-prof-academic-metrics.md  # 同 V3 pipeline Stage 3 路径
prd_anchor: docs/Professor-Data-Agent-PRD.md §模块一 R3
shared_spec_anchor: docs/Data-Agent-Shared-Spec.md §4.3 教授 profile_summary 200-300 字
---

# W11-7: profile_summary 用 raw_text + 全量回填

## 1. Goal

PRD 要求教授 `profile_summary` 严格 200-300 字、领域具体、无套话。当前线上 787 教授中：

- 丁文伯（PROF-5F14BBA866D9）：`profile_summary=75 chars`，`profile_raw_text=4735 chars`，`h_index/citation_count/paper_count=NULL`
- `quality_status='ready'`（gate 未校验长度 → 数据被放进 admin-console / Milvus）
- 根因 1：`summary_generator.py:200-237` `build_profile_summary_prompt` 只用 `EnrichedProfessorProfile` 结构化字段（research_directions / top_papers / awards / education），**完全不喂 `profile.official_anchor_profile.bio_text`**（即主页原文）。结构化字段不够时 LLM 输出短，触发 fallback `_build_fallback_profile_summary`，进一步坍缩到结构化字段堆叠。
- 根因 2：`run_profile_summary_reinforcement.py:121` SQL `length(profile_summary) < 50` 阈值过低 → 75 chars 不进 backfill 候选池。
- 根因 3（不在本 spec 范围）：`quality_gate.py` 不校验 summary 长度 → W12-7 单列。

**本 spec**：让 V3 pipeline 新跑产出真长 summary（raw_text 喂 LLM），并把已有 787 prof summary < 150 的批量回填。

## 2. Non-goals

- **不**改 `validate_profile_summary` 阈值（仍 200-300）
- **不**改 `quality_gate` 逻辑（W12-7 处理）
- **不**改 `EnrichedProfessorProfile` 数据模型
- **不**改 `summary_reinforcement.py` 模块本身（其 `bio: str | None` 字段已能接 raw_text，只动 caller 阈值）
- **不**改其他 fallback 文案
- **不**触多源主页抓（W12-5 处理）

## 3. User-visible behavior

| 用户面 | 行为变化 |
|---|---|
| 之后 V3 pipeline 跑教授 | summary_generator LLM prompt 多 `profile_raw_text`（截断 4000 字）；产出更稳定满足 200-300 字 |
| 全量回填后 admin-console 教授卡片 | 787 prof 中 summary < 150 chars 的批量重写为 200-500 字 reinforced summary（reinforcement 模块上限 800） |
| 丁文伯 admin 卡片 | summary 从 75 chars → ≥ 200 chars，含信号处理 / 谱估计 / Group Website 等 raw_text 提取的研究信号 |
| 现存满足 ≥ 150 的 summary | 不动（避免无谓覆盖；--all flag 可强制覆盖）|

## 4. Affected paths

```
修改：
  apps/miroflow-agent/src/data_agents/professor/summary_generator.py
    build_profile_summary_prompt: 把 profile_raw_text 截到 max 4000 chars 后注入 prompt
    （raw_text 字段在 EnrichedProfessorProfile 已存在；models.py 不动）
  apps/miroflow-agent/scripts/run_profile_summary_reinforcement.py
    _build_select_sql: 阈值 50 → 150 (新增 --min-length CLI arg, default 150)
    summary_reinforcement_needed: 已有 min_length 参数，直接 default 改 150
  apps/miroflow-agent/src/data_agents/professor/summary_reinforcement.py
    _DEFAULT_MIN_REINFORCE_LENGTH: 50 → 150（保留向后兼容，仅改 default）

新增：
  apps/miroflow-agent/tests/data_agents/professor/test_summary_generator_raw_text.py
    1. raw_text 注入 prompt 的单测（assert prompt 含 raw_text 片段）
    2. raw_text 长度截断（输入 8000 chars → prompt 中 ≤ 4000 chars）
    3. raw_text 为空时 prompt 退回原行为（无新增 section）
  apps/miroflow-agent/tests/scripts/test_run_profile_summary_reinforcement_threshold.py
    1. SQL 默认阈值 150（mock SQL render assert "150"）
    2. --min-length 50 CLI override 仍生效
```

## 5. Architecture / Data flow

V3 pipeline Stage 3（summary_generator.generate_summaries）路径：

```
EnrichedProfessorProfile
  + name / institution / department / title
  + research_directions / top_papers / awards / education_structured
  + profile_raw_text  ← 新增进 prompt
  ↓
build_profile_summary_prompt(profile)
  ↓ LLM (Gemma-4)
profile_summary (200-300 chars)
  ↓ validate
ok? → 写 professor.profile_summary
no?  → _build_fallback_profile_summary（仅结构化）
```

回填路径（M6 reinforcement）：

```
SQL: SELECT * FROM professor WHERE length(profile_summary) < 150  ← 新阈值
  ↓
generate_reinforced_profile_summary(
    bio=profile_raw_text,
    paper_contexts=[...top 5 papers full text],
)
  ↓ LLM (Gemma-4)
reinforced_summary (100-800 chars，min_length 提至 150)
  ↓ persist
UPDATE professor SET profile_summary = ...
```

## 6. Interface contracts

### 6.1 `build_profile_summary_prompt(profile)` 改动

raw_text 来源：`profile.official_anchor_profile.bio_text`（已存在，由 homepage_crawler 写入；canonical `professor.profile_raw_text` 列亦同源）。

```python
def build_profile_summary_prompt(profile: EnrichedProfessorProfile) -> str:
    # ... existing structured field assembly ...
    
    # NEW: include raw_text excerpt from OfficialAnchorProfile.bio_text
    raw_text = ""
    if profile.official_anchor_profile and profile.official_anchor_profile.bio_text:
        raw_text = profile.official_anchor_profile.bio_text.strip()
    raw_text_section = ""
    if raw_text:
        raw_text_section = f"\n个人主页正文摘录（请提取关键信号补充上述结构化字段不足之处）：\n{raw_text[:4000]}"
    
    return f"""请为以下教授生成200-300字的中文简介...
...
教授信息：
姓名：{profile.name}
...
{raw_text_section}

直接输出简介文本，不要包含任何前缀或标签："""
```

要求：
- 截断长度 4000 chars（Gemma-4 32k 上下文有 buffer；其他 prompt 部分约 1000 chars，留 LLM 1000 token 输出）
- `official_anchor_profile is None` 或 `bio_text` 空字符串 → section 为空字符串（不破坏现有行为）
- 不动现有 prompt 模板顺序，仅在结尾追加
- 不修改 `EnrichedProfessorProfile` / `OfficialAnchorProfile` 模型字段

### 6.2 `_DEFAULT_MIN_REINFORCE_LENGTH` 与 SQL 阈值

```python
# summary_reinforcement.py
_DEFAULT_MIN_REINFORCE_LENGTH = 150  # was 50

# run_profile_summary_reinforcement.py
def _parse_args(...):
    parser.add_argument(
        "--min-length",
        type=int,
        default=150,
        help="Threshold below which profile_summary is regenerated (default 150)",
    )

def _build_select_sql(*, only_missing: bool, limit: int | None, min_length: int) -> ...:
    if only_missing:
        clauses.append(f"(profile_summary IS NULL OR length(profile_summary) < {int(min_length)})")
    # ... rest unchanged
```

注意：`min_length` 嵌入 SQL 用 int cast，不用参数化（无 user input；但 `int(min_length)` 强转防 injection）。

## 7. Invariants

- `validate_profile_summary` 仍 200-300（不动）
- LLM 输出 200-300 → 直接落盘；< 200 → fallback；> 300 → coerce
- reinforcement 模块 min_length 100 / max_length 800 不动（min_length 用于过滤候选；上限和 V3 stage 3 无关）
- raw_text 截断不破坏 utf-8（Python str slice 安全；中文 1 char = 1 codepoint）
- 不写新 run_id（reinforcement 已有 run_id 但不入 pipeline_run；W9-2 phase 2 单列）
- `--all` flag 仍能强制覆盖

## 8. Edge cases / failure modes

| 场景 | 处理 |
|---|---|
| `official_anchor_profile is None` | section 为空字符串；prompt 退回原版（structured-only） |
| `official_anchor_profile.bio_text=""` | 同上 |
| `bio_text` 含 HTML 标签（未清洗） | 不清洗；LLM 自行容错；后续 W12-5 可加 BeautifulSoup 预清洗 |
| bio_text > 4000 chars | 截到 4000 chars（结尾可能切到中文中部 — 接受） |
| LLM 返回 < 200 → fallback | _build_fallback_profile_summary 不动；保留 reinforcement 后路 |
| reinforcement 全量跑后某 prof 仍 < 150 | jsonl 标 `rejected`；后续手工排查（W12-7 quality gate 处理） |
| Gemma-4 调用 timeout / 5xx | summary_reinforcement 已有 try/except；写 `error` 字段；下次 resume 重试 |

## 9. Validation commands

```bash
cd apps/miroflow-agent

# 单测
DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock \
  uv run pytest tests/data_agents/professor/test_summary_generator_raw_text.py \
    tests/scripts/test_run_profile_summary_reinforcement_threshold.py \
    -n0 --no-cov -v

# 既有 summary_generator 单测不退化
uv run pytest tests/data_agents/professor/ -k summary -n0 --no-cov

# 操作回填（claude 跑，codex 不跑）
DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
  unset https_proxy HTTPS_PROXY  # Python pipeline 不走代理
  uv run python scripts/run_profile_summary_reinforcement.py \
    --only-missing --max-papers 5 \
    > logs/data_agents/professor/summary_backfill_2026-05-02.json

# 抽样验证
DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
  uv run python -c "
import psycopg
conn = psycopg.connect('postgresql://miroflow:miroflow@localhost:15432/miroflow_real')
cur = conn.execute('''
  SELECT canonical_name, length(profile_summary) AS slen, left(profile_summary, 80) || '...' AS preview
    FROM professor WHERE professor_id IN (
      'PROF-5F14BBA866D9'  -- 丁文伯
      -- + 4 个其他抽样
    ) ORDER BY slen
''')
for r in cur.fetchall(): print(r)
"
# 期望: 5/5 行 slen >= 150
```

## 10. Expected evidence

1. 单测 4 个全过
2. 既有 summary 类单测无退化
3. backfill 跑后 jsonl 中 `summaries_written` >= 90% 候选池（少数 LLM 失败可接受）
4. `SELECT count(*) FROM professor WHERE length(profile_summary) < 150` 应大幅下降（前: ~200+，后: < 30）
5. 丁文伯 summary ≥ 200 chars 且包含信号处理 / 谱估计或类似研究信号

## 11. Migration / rollback

- 无 schema 变更；纯代码改 + 数据回填
- rollback：`UPDATE professor SET profile_summary = old_value` 不可（未保留旧值）；但 reinforcement 仅在 `< 150` 时覆盖，原有 ≥ 150 不动 → 失败影响有限
- 如需更稳：reinforcement 之前导出 `pg_dump --table=professor --column-inserts` 备份 75 char 那批

## 12. Stop conditions

- summary_generator 单测改后既有 V3 pipeline 单测大量退化 → stop, escalate（可能 prompt 截断错位）
- backfill 大量 LLM timeout（> 30%） → stop，可能 Gemma-4 服务不稳；回退到 50 阈值临时
- raw_text 中嵌入 prompt-injection 文本（罕见；学术主页很难） → 当前不防御；W12-x 加 sanitize

## 13. Open questions（codex 实施前 claude 决策已锁）

| 问题 | 决策 |
|---|---|
| raw_text 截到多少字？ | 4000 chars（Gemma-4 32k 给充足余量） |
| 截断方式：head / tail / 摘要？ | head 4000（教授主页头部即"个人简介+研究方向"；尾部多是文章列表，结构化字段已覆盖） |
| 是否预清洗 raw_text？ | 不清洗，保留 LLM 容错；W12-5 多源时统一 |
| reinforcement 已有的 `bio` 路径 vs 新 V3 stage3 raw_text 路径 是否合并？ | 不合并；V3 stage3 走 summary_generator（短 prompt），reinforcement 走更全 prompt（含 paper full text）；两条路径互补 |
| 阈值 150 vs 200？ | 150（容忍 raw_text 弱时仍能保存；< 200 走 fallback 但仍写盘） |

## 14. Done criteria

1. ✅ summary_generator.py prompt 含 raw_text section
2. ✅ reinforcement default min_length 提至 150
3. ✅ 4 个新单测过；既有不退化
4. ✅ claude 操作回填全量 787 prof，jsonl 归档
5. ✅ 抽样 5 prof（含丁文伯）summary ≥ 200 chars 且内容相关
6. ✅ docs/solutions/ 写 1 篇 lesson：`profile-summary-raw-text-2026-05-02.md`（claude 写，简短）
