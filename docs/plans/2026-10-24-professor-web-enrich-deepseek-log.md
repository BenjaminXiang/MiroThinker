# 教授画像补全改用 DeepSeek 搜索 + 回退链（执行日志）

> 对应变更：`professor-web-enrich-deepseek-fallback`
> 日期：2026-10-24 ｜ 客户现场线

## 做了什么

1. 新增统一回退搜索器 `FallbackWebSearchProvider`：按顺序试
   **DeepSeek → 博查 → Serper**，某个源报错或返回空结果就换下一个，不再让
   教授任务整条失败。
2. 新增 `resolve_deepseek_search_key()`：先读环境变量 `DEEPSEEK_API_KEY`，
   读不到再读管理台维护的受管密钥文件（`llm.api_key`）。这样任务子进程不依赖
   启动脚本是否导出过变量。
3. `pipeline_v3`（管理台“上传文档 → 教授”导入、批量重跑脚本都会走它）改为通过
   同一个函数构造搜索源。`skip_web_search` 的语义没变。
4. 运维脚本 `run_professor_web_enrich.py` 改用同一回退链，并补上仓库标准的
   `PROJECT_ROOT` 路径引导，使它可以被任意工作目录拉起（任务门不会替它设
   `PYTHONPATH`）。
5. 三个文件已同步到客户机，md5 与源文件一致；两处调用都发生在任务子进程里，
   **不需要重启服务**。

## 发现了什么

- 客户机 `.env` 里**没有** `SERPER_API_KEY`，所以现场的搜索链实际是
  **DeepSeek → 博查**，Serper 根本不会被追加，已被彻底旁路。
- 之前 `run_professor_web_enrich.py` 从任务门拉起会直接报
  `ModuleNotFoundError: No module named 'src.data_agents.providers.deepseek_search'`。
  根因不是文件缺失，而是脚本以 `python scripts/xxx.py` 运行时 `sys.path[0]`
  变成了 `scripts/` 目录，仓库根不在搜索路径里；同目录下 `python -c "import src..."`
  能成功正是这个差别。补 3 行路径引导即可，无需设置 `PYTHONPATH`。
- 每日教授 Seed 刷新（`run_admin_seed_refresh.py` → `seed_runner` →
  `pipeline.py`）**全程不做网页搜索**，本次改动不涉及它，也不能说“每日 Seed
  已切到 DeepSeek”。

## 怎么验证

本地（serving worktree）：

```bash
cd apps/miroflow-agent && uv run pytest \
  tests/data_agents/providers/test_fallback_web_search.py \
  tests/data_agents/providers/test_deepseek_search.py \
  tests/data_agents/professor/test_pipeline_v3.py \
  tests/scripts/test_professor_profile_summary_source_contract.py -q
```

→ **35 passed**。其中新增 6 个测试：3 个回退器测试（首个有结果即返回、
报错/空结果换源、全部失败返回空），3 个链路顺序测试（有 DeepSeek key 时
DeepSeek→博查→Serper、无 key 时博查打头、`skip_web_search` 时不建搜索源），
其余为既有回归。

客户机实测：

1. 用生产函数 `_build_professor_search_provider` 构造，链为
   `['DeepSeekSearchProvider', 'BochaSearchProvider']`；
   `丁文伯 清华大学 专利` 返回 10 条。
2. 同一进程里跑“LLM 生成查询 + 搜索”：模型 `qwen3.6-35b-a3b` 生成 2 条查询，
   各返回 10 条，首条分别是清华官网的丁文伯报道与深圳国际研究生院团队成果。
3. 从 `/tmp` 直接运行 `run_professor_web_enrich.py --help`：正常打印用法、退出 0
   （改动前同一命令报 `ModuleNotFoundError`）。

## 没验证的部分（如实说明）

- 没有在客户数据库上跑一次会写库的完整补全（会更新
  `professor.profile_summary` 与 `professor_fact`）。本次改的是“用哪个搜索源”，
  写库路径未改动；搜索源已用生产构造函数 + 真实 DeepSeek API 验证。
- 管理台没有“教授网页补全”这个按钮；该脚本是运维脚本，不在任务注册表里。

## 影响哪些问题

- 教授画像补全不再依赖已欠费的 Serper；DeepSeek 不通时自动落到博查，任务不再
  因单一搜索源失败而整条报错。
- `/upload` 的教授导入、批量重跑与运维补全脚本共用同一条搜索链，行为一致。

## 补验（2026-10-24 晚）：完整写库 + 两个附带缺陷

上一轮结论里有两句需要收紧：
“没在客户库跑过一次会写库的完整补全”和“每日教授 Seed 刷新不走这条路径”。
补验后，第一句可以升级为“已在隔离 schema 跑通完整写库”；第二句结论对，但
“每日”这个前提是错的，措辞也要改。

### 完整写库（隔离 schema，不碰生产表）

在客户库建 `enrich_scratch` schema，用 `CREATE TABLE ... (LIKE public.<t>
INCLUDING ALL)` 复制 5 张表（professor / professor_affiliation / source_page /
professor_fact / pipeline_run），插入一个真实教授（丁文伯，短摘要）和主页记录，
用 `--dsn "...?options=-csearch_path=enrich_scratch"` 跑部署版脚本：

```text
1/1 enriched (261c, 23 verified, 5 pages fetched) ✓ written
DONE: 1/1 enriched, 0 failed, status=succeeded
```

落库结果：`professor.profile_summary` 261 字；`professor_fact` 一行
`homepage / active / web_enrich: 23 verified / 0.85`；`pipeline_run`
`succeeded / items_processed=1`。跑完已 drop schema。

失败路径也跑了：`--llm-profile gemma4`（star 网关 502）得到
`0/1 enriched, 1 failed, status=failed`、退出码 1、`pipeline_run=failed/0`。

余量：clone 不复制外键（真实 5 张表共 15 个外键，写入值均满足）；真实表没有
用户触发器；生产表本身仍未写入。

### 附带缺陷 1：DeepSeek 合成返回空

`deepseek-v4-flash` 不带 `thinking: disabled` 时，800 token 全花在 reasoning 上，
`content` 为空、`finish_reason=length`。查询生成有 fallback 掩盖了这一点，合成
没有，于是每个教授都被 “synthesis too short (0c)” 跳过。修复：脚本两处 LLM 调用
都传 `build_non_thinking_extra_body(model)`。同一 prompt 实测：不带 0 字，带 171 字。

### 附带缺陷 2：全失败被记成成功

脚本最后一行永远写 `status='succeeded'`。两次全失败（gemma4 502、DeepSeek 空合成）
都留下 `succeeded / items_processed=0` 且退出码 0。修复：累计 `failed_count`，
有候选但一个都没补全时写 `failed` 并返回 1。实测失败/成功两条路径状态正确。

### 对第二句的修正

- Seed 刷新**没有 cron**，不是每日任务：`admin-seed-refresh` /
  `admin-seed-refresh-sample` 是管理台按 seed 手动触发，任务定义里没有
  `schedule_cron`。
- 它走 `seed_runner` → `pipeline.py`（v2），不 import `pipeline_v3`，也不 import
  任何搜索 provider；唯一的 HTTP 客户端用于抓已知名录/主页 URL。
- 任务注册表里的 `quota="web_search"` 是**配额桶标签**，不代表它调用搜索 API。
  这一点容易被误读，需在对外说明里写清楚。

准确说法：**Seed 刷新不调用搜索 API、不经过本次改动的 pipeline_v3，因此不受
DeepSeek 切换影响；它是管理台手动触发，无定时任务。**
