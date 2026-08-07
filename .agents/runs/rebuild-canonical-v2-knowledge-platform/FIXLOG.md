# FIXLOG — canonical-v2 rebuild 修复记录

每条记录：问题现象 / 根因 / 修复内容 / 验证 / 引入时间。目的：每次修复有据可查，
避免版本回退后丢失上下文。按时间倒序追加。

---

## 2026-08-07 · complete_build 收尾卡死：hasher 计算爆炸（已修复）+ Milvus Lite close 死锁（迁移阻塞项）

**问题现象**：`test_complete_build_uses_verified_copies_landing_authority_projections_registry_index_and_verify`
长时间 CPU 100%+，磁盘产物仅 36K（只有 source-build-manifest，无 envelope）。

**根因（两个独立问题叠加）**：

1. **hasher 组合爆炸**（已修复，`canonical_identity_resolution.py::_IdentityDecisionInputHasher`）：
   py-spy 抓到卡在 `canonical_identity_resolution.py:1224` hexdigest 路径
   （`_logical_graph → _map_public_authority → resolve → validate`）。旧实现把 request
   的每个嵌套对象分别序列化 hash，identity resolution 对海量候选做逐项 hash 校验 →
   O(N×M) 组合性能问题。
   **修复**：hasher Merkle 化——request 先整体哈希一次得到 `_request_digest`，
   hexdigest 输出改为 `_content_sha256({decision, request_digest, supporting_assertion_ids})`；
   legacy 测试（test_canonical_identity_resolution_contract.py 的 legacy_payload 断言）同步更新。

2. **Milvus Lite 2.5.1 close 死锁**（未修复，独立迁移阻塞项）：
   hasher 修复后构建真实推进（566MB envelope 写出），但收尾时 Milvus Lite close 卡死：
   主线程 `pthread_join` 等待事件循环线程（`epoll_wait timeout=-1` 无限等待）→ 死锁。
   gdb 确认（Thread 1 futex join 事件循环线程）。隔离验证（停 18188 后重跑）同样卡死，
   与 18188 并发无关；最小复现（open/close、upsert+flush+close）不卡——需完整构建的复杂序列触发。

**3.2.0 升级试验（否决）**：依赖升 milvus-lite 3.2.0 后 complete_build 完整测试 PASSED
（32 分钟），close 死锁解决；但 **3.2.0 与 2.5.1 本地存储格式不兼容**：
- 2.5.1 的 `milvus.db` 是 SQLite 单文件；3.2.0 变成目录，`MilvusClient(uri=...)` 打不开 2.5.1 的 index
- 现有 s12f index（2.5.1 构建）无法复用，服务启动即 `Open local milvus failed`
- 全套件回归 18 failed + 13 errors（代码 `milvus_path.is_file()` 断言不匹配目录形态）

**结论**：milvus-lite 保持 **2.5.1**；complete_build 收尾死锁记为**迁移阻塞项**——
正式系统用正式 Milvus 服务（或验证其他 Lite 版本/绕过 close）后再收尾。hasher 修复
使构建本身真实完成（566MB 产物），剩余仅为 close 阶段的库缺陷。

**验证**：hasher 修复后 canonical 套件 900 passed（2.5.1）；3.2.0 下 complete_build 1 passed；
回退 2.5.1 后 fast_boot + internal_reference 两套件 74 passed，服务恢复。

---

## 2026-08-02 · 集合指代回归（T2 深圳筛选）— 待提交

**问题现象**：同 session 两轮：
- T1 "中国有哪些成熟的酒店送餐机器人供应商" 正常枚举
- T2 "上述企业里总部在深圳的企业有哪些" 答"由于未提供具体的企业名单，无法确定"
- T3 机械臂按电梯只能答出普渡（Excel 要求普渡必须答出，但覆盖不全）

**根因（两个独立缺陷叠加）**：

1. **reranker 把 vector 候选归入 other**（`knowledge_serving_isolated.py::_serving_reranker`）：
   `has_strong_local` 只认 exact/structured/lexical/relationship/internal_reference 五种 lane，
   **漏了 vector**。枚举场景下 48 个 web 候选 + 48 个 vector 候选进入 fusion（canonical=48），
   但 rerank 后 vector canonical 全部排在 web 之后，`ordered[:candidate_limit]`（48）被 web 占满，
   48 个 canonical 全部截断 → T1 的 `entity_handles` 里 0 个 canonical → `_displayed_ids` 为空
   → T2 无指代可解析。

2. **geography 约束与 lane claim 谓词不一致**（`knowledge_read.py::_constraint_failures`）：
   f99f062（8/2 12:16 引入"每个候选必须自带地理 claim"）后，约束只认
   `predicate == "geography"` 的 claim。但 web lane 对"总部"类问题生成的是
   `headquarters_city` 谓词，本地 structured/vector 候选**从不生成任何地理 claim**。
   结果 T2 的 16 个 structured + 16 vector + 48 web 候选全部被 geography 槽位拒绝
   （ordered=0），答案只剩 supplemental web 兜底 2 条。

**修复**：

1. `knowledge_serving_isolated.py::_serving_reranker`：枚举类问题（含
   `_ENUMERATION_QUERY_MARKERS`）时，vector lane 的 canonical 候选视同 strong local，
   与 web 候选 balanced 交替，保证 canonical 进入窗口；非枚举（实体类）问题保持原序
   （web gap 优先于 vector 邻居，保留王学谦语义）。
2. `knowledge_read.py::_constraint_failures`：geography 槽位接受地理谓词族
   `_GEOGRAPHY_CLAIM_PREDICATES = (geography, headquarters_city, registered_address,
   office_city, branch_city)`；company 域候选 display_name/identity 含城市词也可满足槽位
   （数据端 geography 字段 100% 为空，但 404/1037 家公司名以"深圳市"开头，注册名是可靠信号）。

**验证**：

- 新增测试：`test_serving_reranker_keeps_enumeration_vector_canonical_in_window`、
  `test_geography_slot_accepts_relation_and_registered_name_evidence`
- serving 全量 116 passed（原 115 + 新 1）；geography 原子契约 3 passed
- 端到端（v38）：T1 displayed_ids=16；T2 答出 11 家深圳企业（普渡/隆博/全世萝卜/海芯/探博/
  子空间/壹智控/不停/英雄赛博/阿米嘎嘎/般诺），并正确排除"博歌总部在香港"；
  T3 答出普渡机械臂按电梯
- Excel 全量回归：进行中

**引入时间**：回归发生于 v12/v15（8/2 重建 s12f 后）；缺陷 1 从 reranker 设计起即存在但
被枚举窗口扩大掩盖，缺陷 2 由 f99f062 引入。

**涉及文件**：
- `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py`
- `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read.py`
- `apps/miroflow-agent/tests/canonical_v2/test_knowledge_serving_isolated.py`
- `apps/miroflow-agent/tests/canonical_v2/test_knowledge_read_atomic_green_contract.py`

---

## 2026-08-02 · 服务启动失败：cmdline 缺 --serving-pack

**问题现象**：v34 启动即失败 `CompleteCandidateBuildEnvelope` ValidationError：
`receipt.recorded_decision_bundle_sha256 / recorded_embedding_bundle_sha256 /
recorded_embedding_dimension` 三字段 required。

**根因**：`/tmp/s12f-serve-cmdline.txt` 无 `--serving-pack` 参数。runner 的
`main()` 中 `serve_existing and serving_pack is not None` 才走 pack 快速路径（只做
manifest 校验 + 直接打开）；缺参数则走 `read_envelope` 完整校验，而 s12a envelope
（7-23 生成）缺新模型必填字段 → 校验失败。v32/v33 启动时命令带 `--serving-pack`。

**修复**：启动命令补 `--serving-pack /var/tmp/mirothinker-canonical-v2-s12f/serving-pack`。

**验证**：v35+ 启动成功（~70s），全部端到端测试基于此。

---

## 2026-08-02 · 流式回答 cookie 未落（已提交 433df07）

**问题现象**：T1→T2 单实体指代"他"失效（"丁文伯"后问"他有哪些成果"答无指代）。

**根因**：`chat_stream` 返回 `StreamingResponse` 后在 response 对象上 set_cookie，
流式响应已发出，cookie 未生效 → 每次都是新 session。

**修复**：session cookie 通过 `StreamingResponse(headers=...)` 显式注入 Set-Cookie。

**验证**：同 session 两轮指代恢复正常。

**引入时间**：流式改造（e02d1a9）时引入。


---

## 2026-08-02 · Q14 深圳具身智能厂商"无法回答"（跨话题指代误绑）

**问题现象**：单 session 中先问酒店送餐机器人，再问"目前深圳有哪些具身智能、灵巧手厂商，
他们在数据层面分别是什么路线"→ 答"未包含相关数据，无法回答"。Excel 测试集 Q14。

**根因**：query 含"他们"被 has_set_referent 判定为回指，绑定上一话题的 displayed set
（16 个酒店/PCB 企业）→ _matches_vector_request 按 displayed_entity_ids 过滤 → vector
lane 0 候选 → 本地候选全丢。而 query 内"厂商"是**内部先行词**（cataphoric），应自解析。
has_internal_set_antecedent 只在澄清门用了，_planning_displayed_ids 与
_history_displayed_ids 未用——修复后三处一致。

**修复**（canonical_v2_chat.py）：
1. _planning_displayed_ids 的 has_set_referent 分支：internal antecedent → 返回 ()
2. _history_displayed_ids 的 has_set_referent 分支：internal antecedent → 返回 ()
3. _answer_locked 的 history 兜底：explicit_new_subject 条件加入 internal antecedent

**验证**：新增 test_intra_query_set_antecedent_never_binds_archived_result_set；
referent_history 19 passed；端到端 Q14 答出 13+ 家厂商。全量 Excel 回归 25 轮全部有实质回答。

**引入时间**：s12f 之前（history 绑定逻辑引入，被 8/2 回归暴露）。
