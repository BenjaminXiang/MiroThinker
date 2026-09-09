---
title: profile_summary 太短 — V3 pipeline 不喂 raw_text + reinforcement 阈值过低
date: 2026-05-02
category: docs/solutions/integration-issues
module: apps/miroflow-agent/data_agents/professor
problem_type: integration_issue
component: data_pipeline
severity: medium
applies_when:
  - 教授 admin-console 卡片 profile_summary 显示过短（< 150 chars）
  - quality_status='ready' 但 summary 内容明显不足
  - V3 pipeline 跑过但 LLM 输出短/触发 fallback
tags: [w11-7, profile-summary, llm-prompt, summary-reinforcement]
status: complete
---

# profile_summary 太短 — V3 pipeline 不喂 raw_text + reinforcement 阈值过低

## 表象

admin-console 教授卡片 `profile_summary` 内容过短。例：

- 丁文伯（PROF-5F14BBA866D9）：75 chars
- 全 787 教授中 100% 有 `length(profile_summary) < 150`（本质是没人达到 PRD §模块一 R3 要求的 200-300 字）

但 `profile_raw_text` 字段实际有 91% 教授（719/787）已采集 ≥ 200 chars，丁文伯的 raw_text 4735 chars。raw_text 内容足够丰富但没进入 summary。

## 根因

两条独立路径都吞掉了 raw_text：

1. **V3 pipeline `summary_generator.py:200-237` `build_profile_summary_prompt`** 只用 `EnrichedProfessorProfile` 顶层结构化字段（`research_directions / top_papers / awards / education_structured`）。`OfficialAnchorProfile.bio_text`（即 raw_text 字段）**根本没进 prompt**。结构化字段不够时 LLM 输出短 → `validate_profile_summary`（200-300）失败 → 触发 `_build_fallback_profile_summary`（仅结构化堆叠 → 还是短）。

2. **M6 `summary_reinforcement.py` SQL 阈值** `length(profile_summary) < 50` 过低。75 chars 不进 backfill 候选，永远不会被重生成。`_DEFAULT_MIN_REINFORCE_LENGTH = 50` 同。

## 修复（W11-7 commit 5fa8099）

```python
# summary_generator.py
def build_profile_summary_prompt(profile):
    raw_text = ""
    if profile.official_anchor_profile and profile.official_anchor_profile.bio_text:
        raw_text = profile.official_anchor_profile.bio_text.strip()
    raw_text_section = ""
    if raw_text:
        raw_text_section = (
            "\n个人主页正文摘录（请提取关键信号补充上述结构化字段不足之处）：\n"
            f"{raw_text[:4000]}"  # Gemma-4 32k 上下文给充足余量
        )
    return f"""请为以下教授生成200-300字的中文简介...
    ...{existing_structured_fields}...
    {raw_text_section}

    直接输出简介文本..."""

# summary_reinforcement.py
_DEFAULT_MIN_REINFORCE_LENGTH = 150  # was 50

# run_profile_summary_reinforcement.py
parser.add_argument("--min-length", type=int, default=150, ...)
```

加 LATERAL JOIN 修复 V003 的 schema bug（commit 70dc00a，与 W11-7 配套）：

```sql
SELECT p.professor_id, p.canonical_name, pa.institution, ...
  FROM professor p
  LEFT JOIN LATERAL (SELECT institution FROM professor_affiliation
                     WHERE professor_id = p.professor_id
                     ORDER BY is_primary DESC NULLS LAST,
                              is_current DESC NULLS LAST,
                              start_year DESC NULLS LAST
                     LIMIT 1) pa ON true
  LEFT JOIN LATERAL (SELECT array_agg(value_raw ORDER BY confidence DESC NULLS LAST) AS directions
                       FROM professor_fact
                      WHERE professor_id = p.professor_id
                        AND fact_type = 'research_topic'
                        AND status != 'deprecated') rd ON true
```

注意：
- `professor.institution` 从 V003 移到 `professor_affiliation`（同 `run_professor_orcid_backfill` / `run_professor_metrics_backfill` 修复）
- `professor.research_directions` 从未单列，存在 `professor_fact` 中 `fact_type='research_topic'`
- `paper.title` 不存在，应用 `COALESCE(p.title_clean, p.title_raw, '')`
- `conn.rollback()` 必须在 per-prof exception handler 中调，否则 transaction abort 会传染

## 验证（5 条抽样 → 254-593 chars）

```bash
DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
  uv run python scripts/run_profile_summary_reinforcement.py \
  --only-missing --max-papers 5 --limit 5
```

输出（jsonl）：
```
{"prof_id": "PROF-...", "status": "written", "chars": 468, "source_paper_count": 0}
{"prof_id": "PROF-...", "status": "written", "chars": 593, "source_paper_count": 5}
{"prof_id": "PROF-...", "status": "written", "chars": 538, "source_paper_count": 5}
{"prof_id": "PROF-...", "status": "written", "chars": 587, "source_paper_count": 5}
{"prof_id": "PROF-...", "status": "written", "chars": 576, "source_paper_count": 0}
```

## 后续

- W12-7（待开 spec）：quality_gate.py 加 summary 长度校验，使 `quality_status='ready'` 真要求 length ≥ 200
- W12-5：多源主页抓（follow Group Website / 课题组首页 link）
- W12-6：paper-driven academic summary 整合 V011 paper.summary_zh

## 相关 commit

- `5fa8099` feat(W11-7): summary_generator 用 raw_text + reinforcement 阈值 150
- `70dc00a` fix(W11-7): reinforcement script uses LATERAL join on professor_affiliation
