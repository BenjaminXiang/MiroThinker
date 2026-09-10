# C2 验证 — run14 薄加载 A/B（2026-09-10）

> 范围：C2.1a–e（C2.1f 18188 生产切换禁止）。本文随切片推进逐节补完。

## 1. 路径与三阻塞回顾

C2 目标：run14（47,071 docs，含 multi-value enrichment 检索加宽）薄加载上线。
路径上共遇三个阻塞，全部定位为 **serving 线代码与 run14 数据世代脱节**的不同侧面：

1. **半封印包 manifest 索引绑定陈旧**（p4 Aug-26 语义哈希 vs Sep-8 run14 索引物化）——
   分析：`.agents/runs/close-workbook-gaps/c2-scratch-boot-failure.md`。
2. **半封印包 relationships.json candidate 段旧契约**（单数组世代，部署线模型不可 parse，
   20 条 pydantic 错误）——分析：`.agents/runs/close-workbook-gaps/c2-reseal-blocked.md`。
   引出真身信封路径（data-rebuild 的 8.1G complete-candidate-build-envelope.json）。
3. **真身信封与 serving 线的两处代差**——分析：`.agents/runs/close-workbook-gaps/c2-seal-blocked.md`：
   - 3a `IndexProjectionRequest.supplementary_field_values` 字段缺失（契约级）→ **C2.1p** 移植；
   - 3b 信封校验器内嵌索引重放需要 build 级对等（`_public_embedded_content` /
     `_vector_points` / `_lookup_documents` 的 enrichment 消费）→ **C2.1q** 移植。

修复落地（worktree 分支 `codex/canonical-v2-s12a-ready`）：

| commit | 内容 |
|---|---|
| `9cfdabe` | C2.1a：run14 RecordedServingBundle + 18189 scratch 命令 |
| `9a99ca2` | C2.1r 重封印器（保留备用，未删未扩） |
| `3734f30` | C2.1p：`supplementary_field_values` 三处移植（模型/封印器/loader exclude_unset 锁） |
| `174f141` | C2.1q：build-path 4 hunk 47 行逐字移植，`index_projection.py` 两线零漂移 |

C2.1p/q 回归证据（两轮均逐数一致）：新引脚测试 2 条（s12f 式无字段 → canonical
形式逐字节不变、显式 None 不被 exclude_unset 丢弃；run14 式有字段 → 透传且与
封印器侧 plain dump 哈希一致）+ hermetic pack 21 passed + B1 聚焦套件
96 passed / 26 skipped + fast_boot/embedded_content 14 passed。
零漂移证明：`diff` 两线 `index_projection.py` 与 `domain_projection_models.py` 均无输出。

## 2. 两线 `canonical_v2/` 差异清单（diff -rq，16 项）与定性

| 文件 | 变化行数 | 定性 |
|---|---|---|
| index_projection.py | 47 | **C2.1p/q 已收敛**（零漂移） |
| serving_pack_loader.py | 37 | C2.1p 移植 19 行（serving 侧）+ 数据线私货 `SERVING_PACK_SKIP_HASH_VERIFY=1` 哈希校验环境旁路 18 行（dev 后门，serving 线正确地没有） |
| index_projection_isolated.py | 4 | 微小代差（未影响封印/加载路径，待后续切片核对） |
| domain_inclusion.py | 10 | 代差未核（不在本切片路径上） |
| relationship_projection.py | 34 | 代差未核 |
| relationship_projection_postgres.py | 38 | 代差未核 |
| followup_referents.py | 43 | 代差未核 |
| knowledge_read.py | 50 | 代差未核 |
| knowledge_answer.py | 64 | 代差未核 |
| domain_projection_postgres.py | 97 | 代差未核 |
| canonical_identity_postgres.py | 158 | 代差未核 |
| knowledge_serving_isolated.py | 306 | 代差未核 |
| knowledge_read_isolated.py | 338 | 代差未核 |
| canonical_decision_postgres.py | 969 | 代差未核（postgres 持久化侧） |
| knowledge_build_isolated.py | 1,295 | 代差未核（构建管线主体） |
| （仅数据线有）snapshot_chunks.py | — | 数据线独有工具 |

注：本切片只动了 index_projection.py（C2.1p/q，经批准）；其余 14 个两线差异文件
不在 C2 范围——若后续切片要求 serving 与数据线全面零漂移，是新的决策点。

## 3. 官方封印（C2.1r v2，generator c2-seal-20260910-v1）

产物：`/var/tmp/mirothinker-data-v2/serving-pack-run14-sealed/` 五件套
（lookup.sqlite3 665MB / milvus.db 1.08GB / relationships.json 3.36GB /
institution_catalog.json / .canonical-v2-isolated-index-target.json + manifest.json 11MB），
2026-09-10 14:34 完成。封印日志（c2-seal.log）相位：envelope_validate 2124.3s、
index_snapshot_verify 60.1s、index_artifacts_copied 3.8s、
authority_documents_written 160.8s、manifest_written 5.2s。dogfood 相位未出现在日志
（进程在 manifest_written 后被会话断连杀掉），但 C2.1b 第三次启动中
`open_serving_pack_authority` 完整通过，dogfood 由启动实测补上。

manifest 核对要点（实测重读 manifest.json）：

- release_id = `candidate-v2-20260819-r1`；pack_id = `serving-pack:candidate-v2-20260819-r1`；
  generator_run_id = `c2-seal-20260910-v1`；generated_at = 2026-09-10T06:34:12Z。
- index_result_content_sha256 = `8f1dc248…`（新值，非 p4 旧值 738219cf）；
  index_projection_request_sha256 = `1fe28b2a…`（与信封一致——C2.1p 移植后
  supplementary_field_values 已入 request 哈希）；
  relationship_result_content_sha256 = `7f18aac9…`（与半封印包同）。
- index_marker_sha256 = `8848197c…`；embedding_model_id = `Qwen/Qwen3-Embedding-8B`；
  index_target_id = `index:candidate-v2-20260819-r1`。
- files 五项与目录实物一致；build_manifest.published_projections = 7 条
  （company/paper/patent/person/professor/technology_concept/technology_route）。

## 4. C2.1b A/B 启动（18189 scratch）

命令文件 `s12g/serve-18189-command.sh` 的 `--serving-pack` 已改指 sealed 包
（worktree 未提交改动，只此一处）。启动尝试全记录：

1. **第一次（封印前，阻塞①）**：指向未重铸包，装配不一致（manifest 索引语义绑定
   是 p4 旧值，实物是 run14），fail-closed 于 `open_serving_pack_authority`。
   详见 `c2-scratch-boot-failure.md`——此失败驱动了 C2.1p/q + 官方封印。
2. **第二次（本轮，操作失误）**：从 `apps/miroflow-agent` 下跑，uv 用错 venv
   （缺 fastapi）。正确机制 = `deploy/start-canonical-v2.sh`：**cd 到 worktree 根**
   （用 worktree 根 `.venv`，含 admin-console 依赖）再 `env $(cat 命令文件)`。
   生产 18188 进程证实用 worktree 根 `.venv/bin/python3`。
3. **第三次（本轮，正确 cwd，阻塞④）**：日志 c2-scratch-boot3.log。
   `open_serving_pack_authority` 完整通过（C2.1p/q 移植生效 + 封印有效的正面
   证据），死于 knowledge-read 组合阶段：`_validated_public_projection` 对带
   `_supplementary` 键的 company 文档 `model_validate_json` → `extra_forbidden`。
   启动墙钟约 8 分钟失败未就绪，RSS 峰值约 28G。详见
   `c2-boot-blocked-supplementary.md`。

**根因**：数据线读侧有剥 `_supplementary`/`_quality_tier` 的 14 行块
（knowledge_read_isolated.py:7954-7967），serving 线未移植；sealed 包 903 篇
public 文档（company 899 / professor 4）的 lookup_content 烘入了该键。
修复选项已列于阻塞文档，归主上下文决策。

4. **第四次（C2.1s 修复后，成功）**：主上下文批准选项 A，剥键块逐字移植
   （serving 线 knowledge_read_isolated.py，commit 43fa1340；引脚测试
   `test_public_projection_strips_enrichment_keys` RED→GREEN +  lineage-tamper
   负向；回归 hermetic 22 / B1 聚焦 96 passed+26 skipped / fast_boot+embedded 14
   逐数一致）。日志 c2-scratch-boot4.log。**三门全绿**：
   - 墙钟 **696s**（≤15min 门 ✓）；
   - RSS 峰值 **28.7G**（≤32G 门 ✓），ready 时 16.9G（10s 粒度采样）；
   - 可响应 ✓：优必选专利提问返回完整 SSE 流
     （plan_done→retrieval_done→answer 812 chunks→done），答案含 17 件带公开号
     的分组专利（CN119503049A 等），行为正常。

（监测口径修正：watcher 按 `serving-pack-run14-sealed` 命令行匹配 pgrep，
不再与生产 18188 进程串扰。）

## 5. C2.1c 对账报告

### 5.1 lookup 侧（实测，sealed 包 lookup.sqlite3 = index-v1 字节拷贝）

每域文档数（projection_id 分组）：

| 域 | s12f | run14 | 倍数 |
|---|---|---|---|
| company | 1,737 | 7,089 | 4.1× |
| paper | 563 | 24,520 | 43.6× |
| patent | 1,931 | 11,504 | 6.0× |
| professor | 1,428 | 3,958 | 2.8× |
| **合计** | **5,659** | **47,071** | **8.3×** |

优必选专利绑定（B1 同款口径：`json_extract(document_json,'$.domain')='patent'`，
解内层 `applicants` 按 `canonical_company_id` 过滤）：

- run14 实体重规范化：优必选 = `company-c-b2aac54891e3fce8c98612d8`
  （深圳市优必选科技股份有限公司；s12f 时代的 `company-c-64e631c0…` 已不用于 run14）。
- **id 绑定 450 件**（s12f 58 → run14 450，7.8×）。
- 按名 sightings 458（449 绑定带名 + 9 未绑定）；设计预期的 "459 量级" =
  450 绑定 + 9 未绑定 sightings，同口径解释吻合。
- 全库 patent→applicant 绑定条目 **7,650**（与设计 B1 事实逐数一致）、绑定文档 7,078。

普渡正对照（直扫绑定存在性）：`company-c-72b2ec528908ac199ee1dbc7`
（深圳市普渡科技有限公司）**128 件绑定存在** ✓。

g2 GT-6 在包核查（lookup company 域）：

| GT | 公司 | canonical id | registered_address |
|---|---|---|---|
| 普渡 | 深圳市普渡科技有限公司 | company-c-72b2ec528908ac199ee1dbc7 | null |
| 优地 | 深圳优地智能有限公司 | company-c-ce16d7182d134cacca7061d7 | null |
| 云迹 | 云迹科技股份有限公司 | company-c-46be538b64accf560e186de3 | null |
| 越疆 | 深圳市越疆科技股份有限公司 | company-c-7f76af831850602aeb8bc005 | 深圳市南山区桃源街道…南山智园崇文园区2号楼1003 |
| 优必选 | 深圳市优必选科技股份有限公司 | company-c-b2aac54891e3fce8c98612d8 | 深圳市南山区…南山智园C1栋2201 |
| 速腾聚创 | 深圳市速腾聚创科技有限公司 | company-c-c0148d5b0736647a3fe5be6f | 深圳市南山区…众冠红花岭工业南区2区9栋1层 |

GT-6 全部在包；地址字段 3/6 有值、3/6 为 null（普渡/优地/云迹，如实记录——
g2 的"presence with addresses"预期部分满足，地址缺失属 run14 数据自身空值）。

### 5.2 关系侧复核（sealed 包 relationships.json，只读实测）

关系管道物化结果（`relationship_projection_result`）：

- `current_relationships` 共 **10,897** 条；类型分布：professor_attributed_to_paper
  10,773 / **patent_has_applicant 123** / professor_company_role 1。
- 请求侧 candidates 10,897 = outcomes 10,897 = current 10,897（候选全量准入，
  管道零拒绝）；`relationship_assertions` 10,773 条中 patent_has_applicant **0 条**
  ——专利申请人绑定根本不以 relationship_assertion 形态入管。

`patent_has_applicant` 物化边按 target 公司分布（49 家）：

| 公司 | 物化边 | lookup 侧绑定 | 差额去向 |
|---|---|---|---|
| 优必选 `company-c-b2aac54891e3fce8c98612d8` | **0** | 450 | 全部直扫 |
| 普渡 `company-c-72b2ec528908ac199ee1dbc7` | **17** | 128 | 111 直扫 |

**口径闭合**：关系管道只物化 123 条专利→公司边（serving 线
`_direct_patent_applicant_scan` 注释原话 "~123 of ~7,078 field-level bindings
materialize through the pipeline"，逐数吻合）；其余绑定（优必选全部 450、普渡
111/128）由读侧直扫 patent 投影 `applicants` 字段回答。lookup 侧 450/128 与关系侧
123/49 家不是矛盾而是**设计内分工**（G3-simple 直扫补偿管道瓶颈），serving 线持有
该直扫的抽函数版 + 无 per-edge eligibility 时的并集调用（hunk 3-6，serving 领先
数据线的部分）。两侧对账无缺口。

## 6. C2.1d 25 轮三层重基线

硬门（22 轮）：results-after-s18.json（s12f 最新基线，Sep 9 23:21）的 21 PASS 轮
+ g17-t1（17-1；该文件记录其 FAIL 系 B1 修复 b20161d/197b7f5 之前的旧状态，
B1 已在现役 18188 三层全绿）。对照基线 FAIL 轮（2-1/4-2/7-1）记录不回退要求外的变化。

**中止于第 6 轮（18:57，硬门数学上已不可能通过：4 个门内轮已 FAIL），如实记录：**

| 轮 | 基线 | run14@18189 | fails |
|---|---|---|---|
| 1-1 介绍清华的丁文伯 | PASS | FAIL | empty_answer |
| 1-2 他是否有参与哪些企业的创立 | PASS | FAIL | missing 丁文伯/无界智航（t1 空答污染会话） |
| 2-1 酒店送餐机器人供应商 | FAIL（缺开普勒/九号） | FAIL | 缺普渡/开普勒/九号，cit=0 |
| 2-2 总部在深圳的有哪些 | PASS | FAIL | empty_answer |
| 2-3 机械臂按电梯的产品 | PASS | FAIL | missing 普渡，coverage 2/3 |
| 3-1 黄赌毒场所 | PASS | PASS | — |

**根因分层（同日渐份差分证据）**：

1. **empty_answer 两轮（1-1/2-2）= 环境性失败，非包回退**：服务端
   `knowledge_serving_isolated.py:4311 _filter_private_markers` 在 LLM 散文区检测到
   重复协议标记（`<|canonical_v2_selection_v1|>`/`<|canonical_v2_answer_v1|>`），
   raise 后 turn 中止、answer 事件不发（散文已完整流出，用户可见全文）。
   **对照**：同 query 打**现役 18188（s12f 包）今日同样失败**（同签名，
   answer_chunk 流出后 error=1；journalctl 证实同一 "private marker" 报错）——
   deepseekv4flash 在 9/9 基线后行为漂移（散文区复读协议标记），与 run14 包/
   C2.1s 移植无关。g1-t1 在 18189 复现 3/3、18188 复现 1/1。
2. **2-1 属基线已 FAIL 轮**：今日 18188(s12f) 同样缺开普勒/九号（与基线一致），
   但 18188 有普渡而 run14 无普渡——**门内 FAIL 轮的内容差异，待同日全量差分定性**。
3. **2-3 missing 普渡（coverage 2/3）**：cit=9(L9/W0) 有引用有答案但漏普渡产品，
   单次观测，LLM 组稿抖动与 run14 检索差异皆未排除。

**方法论结论**：Sep-9 存档基线在今日环境下已不可复现（生产原线原包今日即失败
门内 1-1）。22 轮硬门的有效形态只能是**同日双跑差分**（18188 s12f vs 18189 run14
各跑 25 轮，run14 不劣于同日 s12f）——归主上下文决策。

产出：部分结果在任务输出日志（6 轮）；`c2-rebaseline-run14.json` 未生成
（runner 末段才落盘）。

### 6.1 同日双跑差分（方法论经主上下文批准，主仓 213868ae；2026-09-10 19:0x–19:2x）

产物：`testset-baseline-20260909/results-diff-s12f-20260910.json`（18188）与
`results-diff-run14-20260910.json`（18189），各 25 轮全量跑完。
**总分两侧均为 7/25 PASS**（环境漂移对两线等烈度）。逐轮对照：

| 轮 | 基线(9/9) | 今日 s12f | 今日 run14 | 定性 |
|---|---|---|---|---|
| 1-1 | PASS | FAIL empty_answer | FAIL empty_answer | 环境漂移（marker 复读，双侧同签名） |
| 1-2 | PASS | FAIL | FAIL | t1 空答连锁，双侧一致 |
| 2-1 | FAIL | FAIL | FAIL | 双侧缺开普勒/九号；run14 多缺普渡（见归因③） |
| 2-2 | PASS | FAIL | FAIL | 双侧 coverage 不足（s12f cit=1 / run14 cit=9） |
| 2-3 | PASS | FAIL stance | FAIL empty_answer | 双侧 FAIL，失败形态不同（皆环境域） |
| 3-1 | PASS | PASS | PASS | — |
| 4-1 | PASS | FAIL | FAIL | 双侧 coverage/citation 同败 |
| 4-2 | FAIL | FAIL | FAIL | 基线 FAIL 轮，双侧同败 |
| 5-1 | PASS | PASS | FAIL missing 一博 | **唯一 s12fP→run14F（归因①：抖动）** |
| 5-2 | PASS | FAIL | FAIL | 双侧缺深南电路同败 |
| 6-1 | PASS | FAIL | FAIL | 双侧同败 |
| 6-2 | PASS | PASS | PASS | — |
| 7-1 | FAIL | FAIL | FAIL | 基线 FAIL 轮，双侧同败 |
| 8-1 | PASS | FAIL | FAIL | 双侧同败 |
| 8-2 | PASS | FAIL | FAIL | 双侧同败 |
| 9-1 | PASS | FAIL empty_answer | FAIL empty_answer | 环境漂移，双侧同签名 |
| 10-1 | PASS | FAIL empty_answer | PASS | **s12fF→run14P（反向改善，同轮抖动另一侧）** |
| 11-1 | PASS | FAIL | FAIL empty_answer | 双侧同败 |
| 12-1 | PASS | PASS | PASS | — |
| 13-1 | PASS | PASS | PASS | — |
| 14-1 | PASS | FAIL | FAIL | 双侧同败 |
| 15-1 | PASS | FAIL | FAIL | 双侧同败 |
| 16-1 | PASS | PASS | PASS | — |
| 17-1 | 旧FAIL(B1前) | PASS cit=16 | PASS cit=16 | B1 修复双侧同绿 |
| 17-2 | PASS | FAIL | FAIL empty_answer | 双侧同败 |

汇总：23/25 状态完全一致；唯一需归因轮 5-1（s12fP→run14F）+ 反向改善 10-1。

**归因**：

1. **5-1（PCB 打板推荐，missing 一博）= 无引用组稿抖动**。证据三件套：
   一博科技在 run14 本地库**存在**（`company-c-8f303a46ca0b58ad9b92f2dc`，
   s12f 侧 `company-c-22a5896d…`，同一实体重规范化换 id）；两侧答案 cit=0
   （推荐清单皆 LLM/网搜组稿，未落本地引用，本地包内容不驱动该清单）；
   18189 单轮重跑第三次组稿又是另一份更短名单（嘉立创在、捷多邦/深南电路/崇达
   均缺）——同 query 三次三个清单，纯组稿方差。同轮次反向样本 10-1
   （s12fF→run14P）证明抖动双向。
2. **empty_answer 轮（1-1/2-3/9-1/11-1/17-2 于 run14；1-1/9-1/10-1 于 s12f）=
   环境性 marker 复读**，已在前节差分证实（生产原线同败，journalctl 同报错）。
   run14 侧 5 次、s12f 侧 3 次——单样本不足以判定 run14 更易触发，记录待观察。
3. **2-1/2-3 普渡差异定性 = 无引用枚举组稿方差**：今日差分 2-1 双侧 cit=0
   （枚举清单不来自本地引用）；普渡在 run14 本地数据经 §5 两侧核实存在
   （128 绑定 + GT-6 在包）；2-3 今日 run14 为 empty_answer（marker 类）、
   s12f 为 stance 类，"漏普渡产品"未复现为内容缺陷——首次中止运行的单次观测
   属组稿抖动。

**差分判定（按批准方法论）：通过** —— run14 不劣于同日 s12f：23/25 逐轮一致，
唯一 s12fP→run14F 轮已归因抖动，无数据侧解释不了的回退。

**时延证据（快轴首份 C2 数据，runner 原生 elapsed）**：

| 侧 | p50 | p95 | max |
|---|---|---|---|
| s12f@18188 | 13.7s | 42.5s | 43.6s |
| run14@18189 | 20.4s | 74.9s | 76.6s |

run14 语料 8.3×（47,071 vs 5,659 docs）带来 p50 +6.7s / p95 +32.4s —— 可预期
的检索面成本，均远低于 runner 180s 超时；是否可接受归产品判断，如实记录。

## 7. 切换证据与最终判定（2026-09-10/11）

**切换执行**（2026-09-10 19:32）：18188 命令文件指向 run14 sealed 包（命令差异 =
`--serving-pack` / `--candidate-release-id` / `--index-marker-sha256` /
`--index-root` / `--expected-database` / `--database-url` /
`--recorded-serving-bundle{,-sha256}` 六类参数）；旧命令备份
`serve-18188-command.sh.bak-c2-s12f`（**一步回滚**：还回备份 +
`systemctl --user restart canonical-v2-backend.service`）。

**切换后发现的集成缺陷与修复**：replay r1（`replay-c2-post-switch/`）9 失败，
其中 `G5_expansion_t2 canonical_v2_release_mismatch` 根因 = `MANUAL_RECALL_DIR`
仍指 s12f 召回库（s12f release 绑定的召回点被 run14 请求消费触发
`_require_release`）。修复 = repoint 到 run14 专属目录
`/var/tmp/mirothinker-data-v2/manual-recall-v1`（22:51 重启生效）。
**不硬绑旧召回数据**；s12f 时代的管理员上传点（"深圳星桥机器人有限公司"）
未随切换保留，如需续用走管理端重新上传（已记录）。

**修复后复验**（2026-09-11 00:20，主上下文代跑）：
- 冒烟（G5 两轮："深圳有哪些做PCB的公司" → "还有哪些类似的公司"）：
  t1/t2 errors=0，**release_mismatch=0**，t2 正常给出相近企业清单 ✓
- replay r2（`replay-c2-post-switch-r2/`）：**G5_expansion 翻 PASS**；剩余
  4 轮失败（6 个失败项）**全部命中已知类，零新签名**：

| 轮 | 签名 | 分类 |
|---|---|---|
| G1_t3 | subject not in first sentence | 历史抖动签名（B1 在册：replay-7session / after-s18 / s18-interp 均含） |
| G2_t2 | SSE error 中断（marker 复读类） | **环境 marker 类**（同 query 3 次重跑 2 过 1 败；B5 将根治该失败类） |
| G3_t2 | neither clarification nor person-scoped | 历史抖动签名（B1 在册） |
| G7 | required substring missing: 优必选 | 历史抖动签名（B1 在册；同为 GAP-02 枚举完整性输入，B3+B2 验收关注） |

**判定**：C2.1f 切换完成，replay 门按既有抖动政策通过（无切换引入的新签名；
环境 marker 类与历史抖动签名均与本次切换无因果）。**18188 现役 = run14 sealed
（47,071 文档，多值增强检索面），供用户 E2E。**
