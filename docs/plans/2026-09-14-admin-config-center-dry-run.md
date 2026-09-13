# 管理配置中心（W1）干跑盘点：系统里到底有哪些「配置项」

> 归属：`docs/plans/2026-09-07-system-wrapup-config-center-and-periodic-refresh.md` §3 线 A 第一片。
> 对应 change-id：`add-admin-config-center`（`openspec/changes/add-admin-config-center/`）。
> 本文只回答三个问题：**系统里有哪些配置项 · 它们现在是什么值 · 哪些需要页面、哪些不需要**。
> 执行明细与验证证据见 `docs/plans/2026-09-14-admin-config-center-log.md`；机器可读原始盘点见
> `.agents/runs/admin-config-center-w1/dry-run-inventory.json`。

盘点方式（真跑，不是 grep 猜）：读活进程 `/proc/<pid>/environ`、读活 serving pack 的 `manifest.json` 并校验
成员哈希、以只读方式 `PRAGMA quick_check` + 行数统计三个 SQLite 库、`sha256` 回算活索引 marker、
探 `df`/`crontab`/PG 端口。凡"读不到"都记成**不可用 + 原因**，不编数字。

---

## 1. 盘点结论（先看这段）

1. **不改 serving 进程**：线上 18188 的每个行为旋钮要么来自 env、要么钉在 serving pack 里；受管配置文件对它们是
   "env 优先"的信息补充，不是新真相源。因此本片**没有**给 serving 进程接新输入。
2. **原以为要建、实际不需要**：serving 侧 SQLite `settings` 表（计划 §3.3 原方案）不必建——文件更可 inspect、
   不需要迁移，也不会和 env 打架；"keepwarm/会话缓存状态"字段没有可暴露的运行时状态；pack"版本号"字段不存在
   （manifest 只有 `release_id`/`pack_id`/`schema_version`）；serving-pack 路径不能做可编辑项（它是进程 argv 钉死值，
   Web 改它对已运行进程无效，只会制造第二真相源）。
3. **原计划没写、实际必需**：活索引 marker 的**期望 sha256**（否则"hash 校验结果"无从比对）、pack 清单里的
   **各域记录数**、access-log / corrections / manual-recall 的**行数与最近时间**、日志保留期（90 天，写在清理脚本里，
   此前任何页面都看不见）、以及 `CANONICAL_V2_DATABASE_URL` 未配置这一**降级标记**。
4. **各域"上次成功采集时间"在服务机上不可得**：`pipeline_run` 表只存在于构建期 Postgres（alembic V001），
   服务机连的库里没有这张表，活进程也没有 `CANONICAL_V2_DATABASE_URL`。所以面板改为展示"pack 构建时间 + 各域记录数 +
   各运维库最近时间"，并把采集历史显式标成"不可用（构建期库不可达）"——这是**如实降级**，不是缺字段。
5. **真发现一个隐患（本片不修，转 W6）**：Bocha / Serper 的 key 文件查找只沿"导入路径 + 当前工作目录"向上找，
   而 `.bocha_api_key` / `.serper_api_key` 只在主仓根目录；从 worktree 启动的采集脚本会读不到 key 而静默变成
   "未配置"。`llm_profiles.py` 已经会向上越过 worktree 根，Bocha/Serper 不会。W6 接线 cron 前必须处理。

---

## 2. 配置项盘点表

### 2.1 Serving 线环境变量（活进程实测）

| 配置项 | 当前来源 | 谁在哪读 | 生效时机 | 敏感 |
|---|---|---|---|---|
| `CHAT_LLM_PROFILE`（现值 `deepseekv4flash`） | env | `canonical_v2/knowledge_serving_isolated.py:1907,5777,5875`、`llm_judgments.py:304`、`canonical_v2_query_interpreter.py:170` | 首次调用时 | 否 |
| `CHAT_CONTEXTUAL_INTERPRETATION`（`on`） | env | `canonical_v2_query_interpreter.py:72` | 每轮 | 否 |
| `CANONICAL_V2_LEXICAL_INDEX`（`0`） | env（systemd drop-in） | `knowledge_read_isolated.py:160,7169` | 启动时 | 否 |
| `CANONICAL_V2_ACCESS_LOG_DB` | env | `s12a/complete_candidate_runner.py:479` | 启动时 | 否 |
| `CANONICAL_V2_CORRECTIONS_DB` | env | 同上 `:504` | 启动时 | 否 |
| `CANONICAL_V2_MANUAL_RECALL_DIR` | env | 同上 `:529` | 启动时 | 否 |
| `CANONICAL_V2_TURN_DEBUG_DIR` | env | `services/canonical_v2_chat.py:1328`、`knowledge_read.py:49` | 每轮 | 否 |
| `CANONICAL_V2_RERANK_BASE_URL/_MODEL/_API_KEY/_API_KEY_FILE/_TIMEOUT_SECONDS/_MAX_DOCUMENTS` | env（当前全空，见 `rerank.conf.pending`） | `canonical_v2/rerank_client.py:74-235` | 启动时 | key 是 |
| `CHAT_LLM_TIMEOUT_SECONDS`（默认 30） | env | `knowledge_serving_isolated.py:5788,5807,5884` | 每次调用 | 否 |
| `CHAT_LLM_SYNTHESIS`（默认 on） | env | `api/chat.py:4672` | 每轮 | 否 |
| `CHAT_AUGMENT_WEB`（默认 1） | env | `api/chat.py:3336,3433` | 每轮 | 否 |
| `CHAT_QUERY_CLASSIFIER`（默认 on） | env | `api/chat.py:794` | 每轮 | 否 |
| `CHAT_SYNTHESIS_TIMEOUT`（默认 60s） | env | `api/chat.py:87` | 进程启动 | 否 |
| `TURN_TRACE_DIR` | env | `services/canonical_v2_turn_trace.py:320`、`web_lane_resilience.py:52` | 每轮 | 否 |
| `WEB_LANE_DAILY_QUOTA` | env（当前未设＝不限） | `web_lane_resilience.py:287` | 每次 web 调用 | 否 |
| `CANONICAL_V2_DATABASE_URL` 等 4 项 | env（**当前未设**） | `backend/canonical_v2_deps.py:33` | 每次调用 | 是 |
| `DATABASE_URL` / `DATABASE_URL_TEST` | env（V2 线上未设） | `api/chat.py:1885`、`api/seeds.py:278`、`backend/deps.py:68` | 每次调用 | 是 |

### 2.2 Provider / 模型凭据（页面只显示"是否配置 + 尾号 4 位"）

| Provider | 解析顺序 | 读点 | 活环境实测（2026-09-14） |
|---|---|---|---|
| Bocha | `BOCHA_API_KEY` → 主仓根 `.bocha_api_key` | `providers/bocha_search.py:11,61` | env 未设；key 文件在**主仓根**（36B） |
| Serper | `SERPER_API_KEY` → `.serper_api_key` | `providers/web_search.py:13,55` | env 未设；文件在主仓根（41B） |
| 本地/校内 LLM | `<profile>_API_KEY` → `LOCAL_LLM_API_KEY` → `.sglang_api_key` | `professor/llm_profiles.py:11-16,50-61` | env 未设；`.sglang_api_key` 在（27B） |
| DeepSeek（当前档） | `DEEPSEEK_API_KEY` → `.deepseek_api_key` | `llm_profiles.py:75-83` | env 未设；文件在（35B，600 权限） |
| DashScope（其他档的在线腿） | `DASHSCOPE_API_KEY` → `.dashscope_api_key` | `llm_profiles.py:90-95` | **两处都没有** → 这些档的在线腿不可用 |
| OpenAlex / Semantic Scholar | `OPENALEX_API_KEY`/`OPENALEX_KEY`；`SEMANTIC_SCHOLAR_API_KEY`/`S2_API_KEY` | `providers/openalex.py:12,71`、`semantic_scholar.py:5-19` | 均未配置，走无 key 模式 |
| Rerank | `CANONICAL_V2_RERANK_*`；域侧 `providers/rerank.py:52` 用 `.sglang_api_key` | 见上 | 全空；该车道当前关闭 |

### 2.3 模型档与端点（代码内钉死 + env 覆盖）

- 档位表：`professor/llm_profiles.py:76` `_LLM_PROFILES` —— `gemma4` / `qwen35` / `mirothinker` / `ark` /
  `deepseekv4flash` / `deepseekv4lite`；每档 local + online 两个端点。
- 覆盖：`LLM_PROFILE`、`LOCAL_LLM_BASE_URL`/`LOCAL_LLM_MODEL`、`ONLINE_LLM_BASE_URL`/`ONLINE_LLM_MODEL`
  （`llm_profiles.py:246-262`，`apply_endpoint_env_overrides=True` 时生效）。
- Embedding：档位由 serving pack 的 `embedding_model_id` 钉死（实测 `Qwen/Qwen3-Embedding-8B`），**不可配**。
- Rerank（serving 侧）：`rerank_client.py` 默认 `qwen3-reranker-8b` / 3s / 128 篇；域侧
  `providers/rerank.py:13-15` 默认 `http://100.64.0.27:18006/v1` / 60s。
- **两个"答案 LLM"入口**：教授/采集侧走 `LLM_PROFILE`（默认档），serving 侧答案走 `CHAT_LLM_PROFILE`
  （线上 = `deepseekv4flash`），同表不同读数——页面按只读信息展示，不做编辑。

### 2.4 路径变量、存储与保留期（实测）

| 项目 | 来源 | 实测值 | 健康探测 |
|---|---|---|---|
| serving pack 目录 | 进程 argv / `CANONICAL_V2_SERVING_PACK` | `.../serving-pack-run14-sealed` | manifest 可读，`release_id=candidate-v2-20260819-r1`，生成于 2026-09-10T06:34Z |
| 活索引根 | 进程 argv | `/var/tmp/mirothinker-data-v2/index-v1` | marker sha256 `8848197c…97c8` **与进程接收的绑定值一致** |
| `lookup.sqlite3`（活） | 索引根 | 665,395,200 B | `quick_check=ok`；`lookup_document`=47,071、`lookup_manifest`=7 |
| `index-v1/milvus.db` | 索引根 | 1,078,865,920 B | 存在，`.milvus.db.lock` 被活服务持有 |
| access log | `CANONICAL_V2_ACCESS_LOG_DB` | 5,550,080 B | `quick_check=ok`；会话 960 / 轮次 1,599；最近 2026-09-13T09:05Z |
| corrections | `CANONICAL_V2_CORRECTIONS_DB` | 4,096 B | `quick_check=ok`；纠错 3（全部已撤销）、手工新增 2 |
| manual recall | `CANONICAL_V2_MANUAL_RECALL_DIR` | 目录存在，**0 条**（旧 `s12f/manual-recall-v1/manual-recall.json` 属上一代 serving 根） | 只读列举 |
| 日志保留期 | `deploy/purge-access-logs.sh:6`（`RETENTION_DAYS=90`，cron 03:41） | 90 天 | 此前无任何页面可见 |
| 备份 | cron 03:17 `deploy/backup-canonical-v2.sh` | 每日 | — |
| 磁盘 | 实测 `df` | `/`（含 `/var/tmp`）1.89TB 中剩 1.20TB（36.7%）；`/md1` 19.1TB 中剩 2.13TB（88.9%） | — |

### 2.5 采集脚本与节奏（计划 §5.3）

七个脚本都在 `apps/miroflow-agent/scripts/`：`run_company_news_ingest.py`、`run_company_official_product_capture.py`、
`run_paper_search_backfill.py`、`run_paper_summary_zh_backfill.py`、`run_paper_doi_verify.py`、
`run_profile_bio_rescrape.py`、`run_homepage_paper_ingest.py`。

本机 crontab **只有** 03:17 备份、03:41 日志清理、03:07 GitHub 备份三条；**没有任何采集 cron**，
也没有 `deploy/cron/` 声明表（那是 W6）。所以本片的面板没有"调度任务清单"可展示，只能展示产物新鲜度。

---

## 3. 依据盘点划定的边界

**进受管配置文件（可写、非敏感、白名单）**：各域采集开关；每轮 web search / LLM 调用上限；执行窗口（UTC 小时）；
采集侧端点与模型名（LLM / Embedding / Rerank 的 base_url 与模型名，**不含 key**）；serving pack 目录（只读展示 +
可写但 env 优先）；access-log 保留天数。

**明确不进文件（页面只读或完全不展示）**：所有 `*_API_KEY`/`*_API_KEY_FILE`；所有 `DATABASE_URL*`；
`CANONICAL_V2_BACKUP_GATE_ROOT` 与 `CANONICAL_V2_S11B_*`（发布门禁，改了等于削弱 fail-closed 检查）；
serving pack / 索引根 / 各 SQLite 路径（进程 argv 钉死，Web 改了也不影响运行中的进程）；
`CANONICAL_V2_LEXICAL_INDEX*` 等被重放证据冻结的检索策略开关。

**"env 优先"覆盖表**（页面在这些字段上显示"由 env 覆盖"并禁用输入）：`WEB_LANE_DAILY_QUOTA`、
`CANONICAL_V2_COLLECTION_WINDOW_*_HOUR_UTC`、`LOCAL_LLM_BASE_URL`/`LOCAL_LLM_MODEL`、
`CANONICAL_V2_EMBEDDING_*`、`CANONICAL_V2_RERANK_BASE_URL`/`_MODEL`、`CANONICAL_V2_SERVING_PACK`、
`CANONICAL_V2_ACCESS_LOG_RETENTION_DAYS`。
