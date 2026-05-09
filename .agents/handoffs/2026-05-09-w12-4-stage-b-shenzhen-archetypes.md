---
title: "Codex handoff — W12-4 Stage B: 主页论文 Shenzhen 高校 archetype 覆盖"
date: 2026-05-09
spec: .agents/specs/2026-05-09-w12-4-stage-b-shenzhen-archetypes.md
slice: single（一次性交付，不分子切片）
mode: codex implements; claude reviews
estimated_effort: 0.5–1 day
---

# Codex handoff: W12-4 Stage B

> 你是 codex，本任务的实施代理。Claude 负责 review。**实施前必读 spec 全文。**
>
> Spec: `.agents/specs/2026-05-09-w12-4-stage-b-shenzhen-archetypes.md`

## 1. 任务简述

往 `homepage_publications.py` 加上深圳高校 4 个 archetype 的内容覆盖能力（清华 SIGS / 深圳理工 / 中大深圳 / 深圳技术），让端到端 `run_homepage_paper_ingest.py --dry-run --limit 10` 在这 4 类样本上 ≥ 4 个教授拿到 papers > 0。

**重要架构点**：原 W12-4 spec §6 设想的 `_SHENZHEN_CMS_ARCHETYPES` dispatcher 与当前代码架构对不上（当前是「内容策略 dispatcher」而非「institution-template dispatcher」）。新 spec §0 / §4 / §6 给了对齐当前架构的实施路径，**不要照搬原 spec §6**。

## 2. 必读源文档（按顺序）

1. `.agents/specs/2026-05-09-w12-4-stage-b-shenzhen-archetypes.md`（本任务的 spec，权威）
2. `.agents/specs/2026-05-02-w12-4-m2-1-selector-expansion.md`（原意图来源；§6 dispatcher 设计已废，§3 表格仍有效作为目标定义）
3. `.agents/reviews/2026-05-08-sweep-w12-4-escalated.md`（升级缘由；Stage A drift 现已清场）
4. `apps/miroflow-agent/src/data_agents/professor/homepage_publications.py`（当前实现 983 lines）
5. `apps/miroflow-agent/src/data_agents/professor/homepage_publication_headings.py`（heading 词典；spec 默认不动）
6. `apps/miroflow-agent/tests/data_agents/professor/test_homepage_publications.py`（既有 32+ scenarios；**不要改这文件**，它有 277 行别人正在做的 parser robustness drift）
7. `apps/miroflow-agent/scripts/run_homepage_paper_ingest.py`（dry-run 入口）
8. `docs/Paper-Data-Agent-PRD.md` §M2.1 / §模块三 R3（用户可见目标）

## 3. 实施流程（强制顺序）

```
Step 1  调研先行（spec §5）
        └─ 1a) 跑 dry-run before（spec §5.1），归档日志
        └─ 1b) 对每个 Shenzhen 样本：分析 _find_publications_sections 是否返回 section？
              对每个 section 跑 5 个现有 _extract_from_* 策略，确认哪个返回 0 / 哪个返回非 0
        └─ 1c) 写 logs/data_agents/paper/homepage_ingest_runs/2026-05-09/diagnosis.md

Step 2  设计选 A/B（spec §5.3）
        └─ 共享 DOM 模式 → 选项 A（新策略 _extract_from_shenzhen_cms_blocks，加在现有 5 策略后）
        └─ 各 archetype 失败原因不同 → 选项 B（patch 现有策略，最小改动）
        └─ 在 handoff 回报里写明选择理由

Step 3  实现（spec §6 / §7 invariants）
        └─ 修改 homepage_publications.py（A 或 B）
        └─ 不改 heading 词典除非 §5.2 明确发现缺词
        └─ 新建 tests/data_agents/professor/test_homepage_publications_shenzhen_cms.py
              至少 4 个 archetype × 1 fixture × ≥ 5 papers assertion

Step 4  验证（spec §9）
        └─ 4a) 新单测 PASS
        └─ 4b) 既有 publications 单测无退化
        └─ 4c) 端到端 dry-run after，归档对照

Step 5  回报（见本 handoff §6）
```

## 4. 修改文件清单（按预期）

```
修改:
  apps/miroflow-agent/src/data_agents/professor/homepage_publications.py
新增:
  apps/miroflow-agent/tests/data_agents/professor/test_homepage_publications_shenzhen_cms.py
  logs/data_agents/paper/homepage_ingest_runs/2026-05-09/diagnosis.md
  logs/data_agents/paper/homepage_ingest_runs/2026-05-09/before.log
  logs/data_agents/paper/homepage_ingest_runs/2026-05-09/after.log
  （可选）logs/data_agents/paper/homepage_ingest_runs/2026-05-09/<prof_id>.html  # fixture 来源
按需（仅当 §5.2 明确发现缺词）:
  apps/miroflow-agent/src/data_agents/professor/homepage_publication_headings.py
```

## 5. Do-not（强制约束）

- ❌ 不要触碰 `apps/miroflow-agent/tests/data_agents/professor/test_homepage_publications.py`（277 行别人的 drift）
- ❌ 不要改 `extract_publications_from_html` 入口签名
- ❌ 不要改 `HomepagePublication` 数据类
- ❌ 不要改 `_find_publications_sections`（除非 §5.2 调研明确指向它，且必须先停下回报）
- ❌ 不要重写或重命名现有 `_extract_from_list / paragraphs / table / year_groups / definition_list` 5 个策略
- ❌ 不要引入 LLM / Selenium / Playwright / network 调用
- ❌ 不要动 Alembic / DB schema / `_VALID_DOMAINS` / classifier / chat / retrieval / admin-console
- ❌ 不要硬编 fixture 来「让测试通过」——若 §5.1 dry-run 起不来必须停下回报（spec §11 stop condition）
- ❌ 不要 amend 已发布的 commit；只新增 commit
- ❌ 不要使用 `--no-verify` 跳 hook

## 6. 必报项（回到 claude review 时附上）

```markdown
# Codex Stage B 完工回报 — W12-4 Shenzhen archetypes

## A. 选项决策
- A 还是 B？理由（基于 §5.2 diagnosis）

## B. 修改文件清单 + LOC
- ...

## C. before/after 对照（spec §9）
| prof | 学校 | before | after |
|---|---|---:|---:|
| ... | Tsinghua SIGS | 0 | N |
| ... | SYSU Shenzhen | 0 | N |
| ... | SIT          | 0 | N |
| ... | SZTU         | 0 | N |
| ... | 其他 6      | x | x |

## D. 测试结果（spec §9）
- 新单测：N PASS / 0 FAIL
- 既有 publications: N PASS / 0 FAIL
- 命令 + 输出片段（每段 < 30 行）

## E. 风险 / 假设破坏
- 哪些 spec §13 假设不成立了？
- 选了 A 但是否影响某个非 Shenzhen 教授（false positive 风险）？

## F. R3 重新评估（spec §10.7）
- ≥ 5 papers/prof × ?/10 → R3 现状仍 fail / 部分通过 / 通过

## G. 不在 spec 范围但发现的 follow-up
- （可选；只列举，不要顺手做）
```

## 7. Done criteria（与 spec §10 对齐）

提交前自检：

- [ ] §10.1 before dry-run 日志归档
- [ ] §10.2 diagnosis.md 已写
- [ ] §10.3 A/B 决策有理由
- [ ] §10.4 4 archetype 单测 PASS（≥ 5 papers/archetype）
- [ ] §10.5 既有 publications 单测无退化
- [ ] §10.6 after dry-run 对照在回报里
- [ ] §10.7 R3 一句结论
- [ ] §11 stop condition 全部检查过；任一触发必须停下不要硬推

## 8. Verification commands（一行串）

> **DSN note (revised after Codex stop #1)**：DSN 必须是 libpq `postgresql://...`，不能用 SQLAlchemy `postgresql+psycopg://...`（CLAUDE.md §6 那个是 admin-console 的）。
>
> **Proxy note (revised after Codex stop #2)**：项目环境 `ALL_PROXY=socks5://...` 会拦截 loopback TCP；codex 子 shell 不必然有 `NO_PROXY=localhost` 例外。**所有 verification 命令必须先 `unset proxy`，否则 Postgres / Milvus / 任何 localhost 服务握手会失败**（"connection is bad: no error details available"）。

```bash
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy && \
  cd /home/longxiang/MiroThinker/apps/miroflow-agent && \
  uv run pytest tests/data_agents/professor/test_homepage_publications_shenzhen_cms.py -n0 --no-cov -v && \
  uv run pytest tests/data_agents/professor/ -k "publication" -n0 --no-cov && \
  echo "--- dry-run after ---" && \
  DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
    uv run python scripts/run_homepage_paper_ingest.py --dry-run --limit 10
```

## 9. 工作树状态（codex 接手时）

- branch: `main`
- `homepage_publications.py`: 无 drift（已验证 2026-05-09）
- `test_homepage_publications.py`: **+277 lines drift（不要碰）**
- 其它 professor src/test 文件多处 drift：与本任务无关，**不要顺手 commit/revert**
- 51 个 drift 文件分布广泛 — 严格只动本 handoff §4 列出的文件

## 9.bis 环境前置（必须先做）

**Codex 子 shell 第一件事**：

```bash
# 必须 unset 这 6 个变量再跑任何 localhost 服务（Postgres/Milvus/dev-server）
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy

# claude 已实测：unset 后 psycopg 连 miroflow_real 秒通；OpenAlex/arxiv 外网 API 也正常返 200
# 因为外网走的是 https 端点而 https 不依赖 ALL_PROXY 即可访问（路由可达）
# 如果某个外网 API 真的需要走代理才能访问，遇到再补救（不在本 spec 范围内）
```

**Claude 已 baseline 实测**（2026-05-09，unset proxy 后）：
- Postgres `miroflow_real` 含 29 张 public 表，含 `professor / paper / company / patent` 系列
- `scripts/run_homepage_paper_ingest.py --dry-run --limit 2` 真的能跑、能调 OpenAlex / arxiv API
- 所以 §5.1 dry-run 在 Codex 端预期可以跑通；如再失败，根因不是 proxy / DSN，而是 spec §11 其它条件

## 10. 完工后

1. Codex `git add` 仅 §4 列出的文件
2. 创建 commit；message 建议格式：

   ```
   feat(homepage_publications): Shenzhen CMS archetype coverage (W12-4 Stage B)

   - 选项 A/B（写明）
   - before/after dry-run delta
   - PRD §M2.1 R3: ≥ 5 papers × 4 archetypes × 10 prof samples
   ```

3. **不要 push**，把回报粘回，由 claude 创建 review 并决定 accept/revise/reject
