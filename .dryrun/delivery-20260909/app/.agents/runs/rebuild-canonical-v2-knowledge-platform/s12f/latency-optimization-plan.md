# s12f 聊天服务延迟优化方案（仅调研与设计，不改代码）

> 状态：**Candidate（方案文档，未实施）**。本任务只做调研 + 出方案，未修改任何代码。
> 范围：canonical-v2 知识平台聊天服务的两项延迟优化——向量矩阵持久化（方案 A）与 fetch 浏览器预热（方案 B）。

---

## 0. 背景与基线数据

25 轮测试集（`docs/测试集答案.xlsx`，single-session 模式）基线：

- 来源：`.agents/runs/rebuild-canonical-v2-knowledge-platform/s12f/regression/baseline-20260802-single-session.json`（服务版本 v39，pack 模式，`serve-18199-s12f-v39.log` 确认 `serving_pack=/var/tmp/mirothinker-canonical-v2-s12f/serving-pack`）。
- 总计 286.3s / 25 轮，**均值 11.5s/轮**，中位数约 10s，**最慢 33.6s**（T18），另有 T22 29.6s、T21 21.4s、T3 20.5s、T5 21.0s。
- 慢轮共性：概念/枚举类问题（web lane 检索 + LLM 合成 + fetch），见 baseline 报告 `regression/baseline-20260802-single-session.md:36-44`。
- 用户报告的冷启动 77s：首次 vector lane 请求触发 `vectorized_index` 惰性构建（见 §1.1），该数字不在 v39 基线轮内（基线进程已热），属进程重启后的首个向量轮尖峰。

**结论先行（诚实预期）**：11.5s 均值的稳态大头是 web lane（搜索 provider 调用 + 串行 T1 fetch + LLM 合成），方案 A/B 消除的是两类**一次性尖峰**——向量矩阵冷构建（约 77s，进程内仅一次）与 Chromium 首次启动（约 2-4s，进程内仅一次）。A/B 之后均值仍有明显空间，web lane 是后续优化主战场（§5）。

---

## 1. 现状调研：向量 lane 的惰性矩阵构建

### 1.1 `_create_pack_vector_recall_adapter`（pack 路径）

文件：`apps/miroflow-agent/src/data_agents/canonical_v2/serving_pack_loader.py`

- 适配器工厂 `_create_pack_vector_recall_adapter`（**1050-1218 行**）：
  - 1066-1069：包装 `_ValidatingEmbeddingAdapter`（`knowledge_read_isolated.py:259-…`，校验 model_id/dimension/cardinality，并带 `_vectors_by_text` 进程内缓存）。
  - **1072-1075**：`vectorized_index: tuple[dict[str, int], Any, Any] | None` + `vectorized_index_lock`——矩阵一次构建、进程内缓存。
  - **1095-1119** `vectorized_scores()`：`vectorized_index is None` 时（首个 vector 请求，持有锁）：
    - 1103-1105：`validating_adapter.embed_batch(tuple(point.embedded_content for point in snapshot.points))`——**对全部点文本重新 embedding**；
    - 1106-1107：`np.asarray(..., dtype=np.float64)` + `np.linalg.norm(axis=1)`；
    - 1108-1111：范数有限性/非零校验（违反则 `IsolatedKnowledgeReadIntegrityError`）；
    - 1112-1119：`positions = {point_id: 行号}`（行序 = `snapshot.points` 序）→ 返回 `(positions, matrix, norms)`。
  - 1168-1170：query 时每请求只 embed 1 条 query_topic（`embed_batch((query_topic,))`），然后 `matrix @ query / (norms * query_norm)`（1119-1132）。
- **调用链**：`create_serving_pack_knowledge_read`（**1402-1566 行**）→ 1523-1531：仅当 `embedding_adapter is not None` 时注册 vector lane，`vectorized_scoring=vectorized_recall`（默认 True，1402/1410 行），传入 `preopened_snapshot=authority.index_snapshot`（1529）。
- **1217 行 `validated_snapshot()` 在适配器创建时（boot 期）即被调用**——快照读取是启动期的，不是请求期；只有向量矩阵构建是首个请求期惰性的。
- 兄弟实现（非 pack 路径）：`knowledge_read_isolated.py:7000-7090`（`_create_vector_recall_adapter`，`vectorized_scores` 在 **7067-7089** 行同样惰性全量 embed）。runner 的 `--serve` 在无 `--serving-pack` 时走此路径（`complete_candidate_runner.py:1025-1033`），s12f 生产走 pack 路径（1025-1033 选 `create_pack_knowledge_read`）。两处需同步改造或共享 helper。

### 1.2 `IsolatedIndexSnapshot` 结构与 `embedded_content` 语义

文件：`apps/miroflow-agent/src/data_agents/canonical_v2/index_projection_isolated.py`

- `IsolatedIndexSnapshot`（**113-118 行**）：`receipt: IndexProjectionMaterializationReceipt` + `points: tuple[IndexProjectionPoint, ...]` + `lookup_documents: tuple[LookupProjectionDocument, ...]`。纯内存模型，不落盘。
- `IndexProjectionPoint`（`index_projection.py:165-216`）：**`embedded_content: NonEmptyStr` 是文本**（带 `embedded_content_sha256` 自绑定校验，214-215 行），**不是向量**。向量在构建期由 `embed_batch` 产出后只存进 milvus.db 的 `vector` 字段（见 §2）。
- s12f 当前规模：`post-build-verification-s12f.json` → `metrics/index/point_count = 6387`、`lookup_document_count = 4959`；embedding 维度 4096（`knowledge_build_isolated.py:268` `_QWEN_EMBEDDING_DIMENSION = 4096`）。

### 1.3 `embed_batch` 的成本模型（77s 的来源）

- 服务端 embedding 适配器：`_OpenAICompatibleEmbeddingAdapter`（`knowledge_build_isolated.py:6500-6517`），bundle 固定参数（6716-6727）：`Qwen/Qwen3-Embedding-8B`、`base_url=http://100.64.0.27:18005/v1`（**远程 OpenAI 兼容 HTTP 端点**）、`batch_size=32`、`max_workers=32`、`timeout_seconds=180`。
- 6387 条文本 = 200 批 × 32 并发（受远端吞吐约束），进程冷态无缓存 → 首次全量 embed 约 77s（用户实测）。适配器带 LRU 缓存（`_MAX_CACHE_ENTRIES=16384`，6517 行）与去重（`_inflight_texts`），但**缓存是进程内的，重启即失效**。
- 每次普通请求只有 1 条 query embed（毫秒级），不是瓶颈。

---

## 2. 现状调研：构建期已 embed，矩阵可落盘

### 2.1 构建期确实已 embed

`index_projection_isolated.py` `_IsolatedIndexMaterializer.materialize()`（**225-330 行**）→ `_write_milvus_projection`（**605-656 行**）：

- **626-628 行**：`vectors = embedding_adapter.embed_batch(tuple(point.embedded_content for point in points))`——**构建期对全部点做且只做一次 embed**。
- 636-655 行：`vectors` 按 128 条/批 upsert 进 milvus（`vector` 字段），`flush` 后写入。
- 278-289 行：写后读回校验（`_read_points_with_client`，`embedding_adapter` 非 None 时按 cosine ≥ 0.999 校验，`_MIN_VECTOR_COSINE_SIMILARITY = 0.999`，42 行）。

**结论：向量在构建期已生成并持久化在 milvus.db 里；缺失的是 numpy 矩阵/范数的落盘。** 落盘点就是 `_write_milvus_projection` 拿到 `vectors` 的这一刻（626 行之后），此时 `points` 与 `vectors` 一一对应、行序确定，直接 `np.asarray` + `np.linalg.norm` 写 `.npz` 零额外成本。

### 2.2 服务端快照读取时向量其实已被读入内存

`_open_verified_index_snapshot`（435-503 行）→ `_read_all_points_with_client`（694-728 行）`output_fields` **包含 `"vector"`**（706-714 行），但 `embedding_adapter=None`（`open_manifest_verified_index_snapshot`，411-432 行）时 `_validate_physical_point_rows` 只校验元数据、**丢弃向量**（731-757 行）。

> 备选方案 A0（不落盘）：boot 快照读取时保留 `row["vector"]` 供评分用。零新文件，但要把向量绑定进 `IsolatedIndexSnapshot`/读取路径，改动面在共享快照层，且把"评分矩阵"耦合进 milvus 行读取语义。**不推荐为主方案**；用户已确认 A（.npz 落盘）方向，A0 仅作备选记录（§3.4）。

### 2.3 pack 里能否加文件

- 打包器：`.agents/runs/rebuild-canonical-v2-knowledge-platform/s12c/build_serving_pack.py`（`build_serving_pack_from_authority`，191-422 行）：`index_sources`（248-255 行）拷贝 `lookup.sqlite3`/`milvus.db`/marker → `manifest["files"]`（369 行）逐文件 SHA-256。
- 校验器：`open_serving_pack_authority`（`serving_pack_loader.py:483-…`）：
  - **538-548 行**：`expected_files = {relationships, institution_catalog, marker, *PACK_INDEX_FILENAMES}`，要求 **`set(manifest.files)` 与期望集合严格相等**——旧包加新文件会被拒（"file hash registry differs"）。
  - 加载器**不扫描 pack 目录**，目录里多放未登记文件本身不报错；但要在 manifest 里登记并受校验，就必须同步改 `expected_files` 与构建器。
- **关键事实**：loader 的 serving 快照不是从 pack 副本打开的，而是从 `manifest.index_root` 实时打开（638 行 `open_manifest_verified_index_snapshot(index_target, ...)`，`index_target.root = manifest.index_root`，631-637 行）。pack 副本只做哈希绑定。**因此 .npz 放 index root 即可被 loader 直接使用，无需动 pack 格式**（方案 A 主版本）；把 .npz 也拷进 pack 属于"pack 自包含"增强（变体 A2，§3.5）。

---

## 3. 方案 A：向量矩阵持久化（.npz）

### 3.1 落盘格式

`<index_root>/vector_matrix.npz`（单文件，`np.savez`），数组：

| key | shape / 类型 | 说明 |
|---|---|---|
| `point_ids` | `(N,)` unicode | 与矩阵行一一对应（写序 = 构建期 `points` 序） |
| `matrix` | `(N, D)` float64 | `np.asarray(vectors, dtype=np.float64)`，**与当前运行时逐位一致** |
| `norms` | `(N,)` float64 | 构建期 `np.linalg.norm(matrix, axis=1)` |
| `meta` | 0-d object | JSON 字符串：`{"schema_version": "canonical-v2-vector-matrix-v1", "embedding_model_id", "dimension", "point_count"}` |

- 规模：6387 × 4096 × 8B ≈ **209MB**（与当前惰性路径运行时峰值一致，不新增内存；磁盘一次性成本）。
- float64 与现状 `np.asarray(..., dtype=np.float64)`（1106 行）一致，**保证评分与当前行为逐位相同**（检索结果、evidence、rerank 输入零漂移）。
- 命名不带 hash/模型后缀：index root 每 release 全新（`prepare_isolated_index_target` 要求 fresh root，121-178 行），无冲突；`meta.embedding_model_id` 用于加载时绑定校验。
- 可选加固（不建议本期做）：把 npz 的 `point_count`/`point_ids` hash 记入 lookup.sqlite3 的 receipt——会改 receipt schema，波及读回校验，收益低。

### 3.2 构建期钩子（写）

`apps/miroflow-agent/src/data_agents/canonical_v2/index_projection_isolated.py`：

- `_write_milvus_projection`（605-656 行）改为**返回 `vectors`**（或加 `target_root` 参数），在 `materialize()` 272 行调用处拿到 `vectors` 后调用新 helper：
- 新 helper `write_persisted_vector_matrix(root: Path, points, vectors) -> None`：
  1. 构建 `point_ids`/`matrix`/`norms`/`meta`；
  2. 校验：`len(point_ids) == len(points)`、`matrix.shape == (N, dimension)`、`norms` 全有限且非零（复用 1108 行语义，失败抛 `IndexProjectionIntegrityError`）；
  3. `np.savez(root / "vector_matrix.npz", ...)`（points 为空时跳过写入）。
- 该 helper 放本文件，pack 与非 pack 两条 serving 路径共用加载 helper（§3.3），避免双份实现。

### 3.3 加载路径（读）

`apps/miroflow-agent/src/data_agents/canonical_v2/serving_pack_loader.py`：

- 新常量 `PACK_VECTOR_MATRIX_FILENAME = "vector_matrix.npz"`（若走变体 A2 则同时进 `expected_files`，见 §3.5）。
- `_create_pack_vector_recall_adapter`（1050-1218 行）：
  1. **创建期（boot）加载**：`vectorized_scoring` 为真时，在 1217 行 `validated_snapshot()` 之后立即尝试加载 `bundle.index_target.root / PACK_VECTOR_MATRIX_FILENAME`（`bundle.index_target` 即 loader 从 manifest 重建的 target，631-637 行，root = index root，与快照同源），构建 `vectorized_index`——"启动直接加载"。
  2. **加载校验（helper `load_persisted_vector_matrix(path, points, dimension)`）**：
     - `meta.schema_version` 匹配；`meta.embedding_model_id == bundle.index_result.policy_snapshot.embedding_model`；
     - `matrix.shape == (len(snapshot.points), dimension)`（dimension = 校验适配器维度）；
     - `set(point_ids) == {p.point_id for p in snapshot.points}` 且无重复（**行序不假设与快照一致**，`positions` 直接从 npz 的 `point_ids` 建，替换 1112-1116 行按 `snapshot.points` 序建的 dict）；
     - `norms` 全有限且非零；
     - 任一不符 → `IsolatedKnowledgeReadIntegrityError`（文件在但坏 = fail closed）。
  3. **缺文件回退**：文件不存在 → 保留现状惰性全量 embed 路径（§1.1 的 1100-1119 行原样保留作 fallback），打一条 warning。这样**旧 index root / 旧测试包零改动继续可用**，迁移平滑。
  4. `vectorized_scores()`（1095-1119 行）只保留"已加载直接算分 + 未加载则惰性构建"的分支；`positions` 语义不变（`scores[positions[point.point_id]]`，1172 行）。
- 兄弟实现 `knowledge_read_isolated.py:7000-7090` 用同一 helper 同步改（非 pack serve 路径；`validated_bundle.index_target.root` 为 npz 路径）。

**本版本不改** `open_serving_pack_authority`、manifest schema、`build_serving_pack.py`——旧 pack 完全兼容（A1 主版本的关键收益）。

### 3.4 备选方案 A0（不落盘，仅记录）

boot 快照读取时（`_read_all_points_with_client` 已取 `vector` 字段）保留向量构建 `positions/matrix/norms`。零磁盘、零新文件，但改动共享快照读取路径与 `IsolatedIndexSnapshot` 契约（113-118 行），且把评分矩阵与 milvus 行读取绑定。风险面大于 npz 方案，不推荐。

### 3.5 变体 A2（pack 自包含，可选、非本期）

若要求 pack 完全自包含：`build_serving_pack.py` 的 `index_sources`（248-255 行）加 npz 拷贝 + `manifest["files"]`（369 行）登记；loader `expected_files`（538-543 行）加文件；`PACK_SCHEMA_VERSION`（119 行 `"canonical-v2-serving-pack-v1"`）升 v2；加载从 `pack_dir` 读。**代价：旧 pack 全部失效需重打**（s12c r8 / s12f 两个 serving-pack）。当前架构本就要求 index root 在场（快照从 root 开），自包含收益有限，**建议不做**，留作未来分发需求出现时的选项。

### 3.6 验证方式

1. 单测（`apps/miroflow-agent/tests/canonical_v2/`）：
   - 构建端：小索引 + stub embedding → `write_persisted_vector_matrix` 产出 npz，内容/形状/点集正确；
   - 加载端：**逐位一致性**——同一快照下，持久化路径与惰性路径（stub 返回同批向量）产出的 `positions/matrix/norms` 与最终 score 完全相等；
   - 负例：meta 模型不符 / 维度不符 / 点集漂移 / 范数非有限 → 抛 `IsolatedKnowledgeReadIntegrityError`；文件缺失 → 回退惰性路径不报错；
   - 回归：`tests/canonical_v2/test_serving_pack_loader.py` 全绿（回退设计下无需改 fixture）。
2. 集成（冷启动验证，代替 `probe_vector_cost.py` 占位）：
   - 全新进程 boot → 首个 vector 轮延迟应 < ~5s（npz 加载 ~0.3-1s + query embed），对比现状 ~77s；
   - 重跑 `workbook_regression.py`（s12f 基线命令）对比 25 轮总量：**不得高于 286.3s**，冷启动轮应显著下降；
   - 抽查向量轮答案与基线一致（评分逐位相同，结果必须相同）。
3. 资源：boot RSS +约 209MB（与现状惰性路径峰值相同，只是提前）。

### 3.7 风险

- **矩阵与 milvus 向量一致性**：npz 由构建期同一 `vectors` 写出（626 行），与 milvus upsert 数据同源，构造上一致；构建端写入前校验形状/范数。加载端不做逐行 cosine 复验（构建期 `_MIN_VECTOR_COSINE_SIMILARITY=0.999` 读回已证明），如需更严可抽样比对，成本可忽略。
- **旧 root 无 npz**：回退惰性路径，行为与现状完全一致（仅多一条 warning）。
- **磁盘/内存**：+209MB 磁盘（index root 每 release 全新）；内存峰值不变。
- **双路径漂移**：pack 与非 pack 两处适配器必须共用 helper，否则行为分叉（§3.3 已安排）。
- **逐位一致性依赖 float64**：禁止改 float32 落盘（会引入量化误差、评分漂移、rerank 输入变化）。

---

## 4. 方案 B：fetch 浏览器预热（keepwarm 扩展）

### 4.1 现状

- `apps/miroflow-agent/src/data_agents/providers/page_fetch.py`：`create_tiered_page_fetcher`（208-233 行）T0 直连 httpx+BS4，`_is_thin_or_blocked`（120-135 行）判定太薄/被拦时升级到 T1 `_PlaywrightPagePool`（**138-205 行**）：
  - **惰性启动**（177-187 行 `_browser_instance`）：首个 T1 请求才 `sync_playwright().start()` + `chromium.launch(headless=True)`（160-175 行），**一次约 2-4s**；
  - **线程绑定**（138-147 行注释）：Playwright sync dispatcher 绑定启动线程，所有浏览器操作必须经单线程池 `self._t1`（max_workers=1）提交——**预热必须经由该池线程**，不能从调用方线程直接 launch；
  - 启动失败置 `_launch_failed` 永不再试（185 行），T0 单独服务；
  - 浏览器一旦启动**永不复用回收、也不关闭**（无生命周期管理）。
- 调用方：web lane `_DualWebLaneAdapter._enrich_with_page_text`（`knowledge_serving_isolated.py:1094-1134`），对每个 view 前 2 个结果并发调 fetcher（1110-1113 行），T1 串行 5s/页。
- keepwarm 现状：`admin-console/backend/services/canonical_v2_keepwarm.py` `AdaptiveIdleKeepwarm`——单后台线程、非重叠回调、**空闲 300s 才跑一轮**（`backend/main.py:175-178` `idle_seconds=300.0`），startup 启动 / shutdown 停止（180-181 行），请求时 `mark_activity`（`backend/api/canonical_v2_chat.py:85-86`）。cycle 来自 `knowledge_serving_isolated.py:4431-4438` 的 `_provider_keepwarm_cycle`：**bocha 搜索 + serper 搜索 + embedding 单条 ping + LLM 1-token 热身**（4407-4430 行），**不含 fetch/浏览器**。装载链：`load_recorded_serving_inputs`（4326-…）→ `RecordedServingInputs.idle_keepwarm_cycle`（237 行）→ runner `_serve` 568 行 → `create_canonical_v2_candidate_app`。

### 4.2 改动设计

**a. `page_fetch.py`：暴露 `warm()`**

- `_PlaywrightPagePool` 加 `warm(timeout: float = 10.0) -> bool`：向 `self._t1` 提交 `self._browser_instance`（强制在专用线程内启动），`future.result(timeout=timeout)`；异常吞掉并**不置 `_launch_failed`**（预热失败不毒化后续真实 T1 重试；真实 fetch 路径 177-187 行行为不变）。已启动则幂等返回 True。
- `create_tiered_page_fetcher` 返回值改为**可调用对象** `TieredPageFetcher`（`__call__` = 现有 fetch 逻辑 + `.warm`）。所有调用点按函数调用（`_enrich_with_page_text` 1111 行 `self._executor.submit(self._page_fetcher, ...)`）——可调用对象向后兼容，测试 `tests/canonical_v2/test_web_page_fetch.py`（144-171 行用 `browser_factory` 注入）不受影响。

**b. boot 预热（关键，解决"首个请求就要用"）**

- runner `complete_candidate_runner.py` `load_recorded_serving_inputs`（889-899 行）创建 fetcher 后：`threading.Thread(target=fetcher.warm, name="canonical-v2-fetch-warm", daemon=True).start()`——**后台线程预热，不阻塞 boot**；若 boot 期内首请求先到，池内启动互斥锁保证只启动一次。

**c. idle keepwarm 周期加入 fetch 预热**

- `knowledge_serving_isolated.py:4431-4438` operations 追加 `warm_fetch`（`lambda: page_fetcher.warm()`），捕获异常（`_provider_keepwarm_cycle` 已 best-effort，4091-4098 行）。作用：长空闲（≥300s）后浏览器进程若被 OOM/系统回收，下个空闲周期自动重启；预热失败不置毒（见 a）。

**d. 生命周期**

- 维持现状：浏览器常驻至进程退出（daemon 线程 + OS 回收），不新增关闭逻辑；shutdown 由 `AdaptiveIdleKeepwarm.stop`（`canonical_v2_keepwarm.py:78-82`）只停调度线程。
- 常驻成本：headless Chromium 空闲约 200-400MB RSS + 少量 CPU，接受（与现状"启动后永驻"语义一致，只是提前）。

### 4.3 验证方式

- 单测（`tests/canonical_v2/test_web_page_fetch.py` 扩展）：
  - `warm()` 在专用线程上触发 `browser_factory` 且只触发一次（幂等）；
  - warm 失败（factory 抛错）后真实 fetch 仍会再次尝试启动（`_launch_failed` 未被置位）；
  - warm 后 `fetch()` 不再二次 launch。
- 集成：boot 后立即发一条会触发 T1 的请求（薄结果 URL），首条 T1 页延迟应只剩 goto 耗时（~2-4s 启动被消除）；`probe_fetch_cost.py` 第二段"预热后"对比可作回归指标。
- 回归：25 轮 workbook 总量不得高于基线（B 本身不减均值，防回归为主）。

### 4.4 风险

- 启动失败静默：warm 失败无日志?——需在 warm 里 `logger.warning`（当前 `_start_browser` 异常仅向上抛）。
- 线程模型：warm 必须走 `self._t1`，否则违反 Playwright 线程绑定（§4.1）——实现红线。
- 常驻内存 +约 200-400MB；机器内存紧张时可能反过来挤掉其他缓存（embedding LRU 等），需观察。
- 收益边界：仅消除进程内首个 T1 启动尖峰（约 2-4s，最多影响 1 轮）；对 25 轮均值贡献约 <0.5s。T1 本身 5s/页串行（1094-1134 行）才是 web 轮大头之一，属于后续优化（§5），不在本方案。

---

## 5. 优先级建议

1. **先做方案 A**（收益确定、改动集中、风险可控）：
   - 消除进程重启后首个向量轮 **~77s → ~1-2s** 尖峰（对演示/压测冷启动场景是数量级改善）；
   - 顺带把评分矩阵与**构建期权威向量**对齐（现状 query 时重 embed 与 milvus 存储向量存在模型侧非确定性漂移，虽被 0.999 阈值容忍，但评分一致性更好）；
   - 不影响 pack 格式（A1），迁移零成本（旧 root 回退）。
2. **再做方案 B**（小、独立）：
   - 消除首个 T1 请求 **~2-4s** 启动尖峰；纯增量、无格式变更；可与 A 并行实现。
3. **后续（超出本次范围，仅记录）**：11.5s 均值的稳态大头是 web lane——搜索 provider 调用（`_merged_results_for_views`，`probe_latency.py` 可测分段）、**T1 5s/页串行 fetch**、LLM 合成与 gap judge（`knowledge_serving_isolated.py:4405` `create_llm_judge`）、以及枚举轮候选窗（`_ENUMERATION_CANDIDATE_WINDOW`）。T18 33.6s / T22 29.6s 均为 web 重轮，A/B 只削尖峰、不降均值，均值优化需另立方案（fetch 并发化/超时收紧、provider 降级策略、LLM 流式先行等）。

---

## 6. 改动文件清单（实施时）

| 文件 | 改动 | 方案 |
|---|---|---|
| `apps/miroflow-agent/src/data_agents/canonical_v2/index_projection_isolated.py` | `_write_milvus_projection`（605-656）返回 vectors；新增 `write_persisted_vector_matrix` / `load_persisted_vector_matrix` helper；`materialize`（272）调用写 helper | A |
| `apps/miroflow-agent/src/data_agents/canonical_v2/serving_pack_loader.py` | 新常量；`_create_pack_vector_recall_adapter`（1050-1218）boot 加载 + 校验 + 缺文件回退 | A |
| `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read_isolated.py` | 兄弟适配器（7000-7090）同步接入同一 helper | A |
| `apps/miroflow-agent/src/data_agents/providers/page_fetch.py` | `TieredPageFetcher`（`__call__`+`warm`）；`_PlaywrightPagePool.warm`（经 `self._t1`） | B |
| `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py` | keepwarm operations（4431-4438）追加 `warm_fetch` | B |
| `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/complete_candidate_runner.py` | boot 后台线程调 `fetcher.warm`（889-899 附近） | B |
| 测试 | `tests/canonical_v2/test_index_projection_isolated.py`（或就近）、`test_serving_pack_loader.py`（回归）、`test_web_page_fetch.py`（warm 用例） | A/B |

不改：`open_serving_pack_authority`、`build_serving_pack.py`、pack schema、`canonical_v2_keepwarm.py`（调度器本身无需改，B 只换 cycle 内容与 boot 时机）。

## 7. 结论

- 两个方向的根因与改点均已定位并有代码行级依据（§1-§4）。
- 方案 A 采用"构建期落盘 .npz 于 index root + boot 加载 + 缺文件回退"，**不改 pack 格式、与旧产物兼容、评分逐位一致**，是确定性的冷启动尖峰消除。
- 方案 B 通过 `warm()`（专用线程内启动）+ boot 后台预热 + keepwarm 周期保活，消除首个 T1 启动尖峰，行为语义不变。
- 两者均不触碰公开 API、数据契约、RAG 语义与 evidence 形状（评分逐位相同）；按 §3.6/§4.3 验证后即可实施。
