# 服务期延迟归因：向量轨的 3–19 秒花在哪（2026-09-15 实测）

> 定位：回答"首答里向量轨那 3–19 秒具体由什么构成"，为 `serving-index-process-scope`
> 变更提供可对照基线。方法：**对活线进程做 py-spy 采样**（只读、不重启、不改代码）+
> 在索引副本上做分段微测。
> 状态：一次成文的实测分析（write once）。

---

## 1. 现象（已验证）

| 场景 | 向量轨耗时 | 证据 |
|---|---|---|
| **冷态**：连续 7 个新会话的 `turn=1` | **18.7 – 30.6s** | `turn-debug/*-01.json`（09-15 00:53–00:59） |
| **热态**：新会话 `turn=1` | **3.0 – 3.2s** | 09-15 10:2x 两个新会话 |
| 同会话 `turn≥2` | **0.1 – 0.9s** | 同一批 debug 文件 |
| 全量统计（358 个含 vector 的回合） | 慢(≥10s) 116 次里 **107 次是 turn=1** | 同上 |

⇒ **这是"会话/冷热相关"的重复装载成本，不是单次查询的固有成本**。

## 2. 采样归因（14 秒窗口、3311 样本、200Hz）

对照的查询与耗时：`vector 12.5s`、`lexical 4.5s`、`web 10.6s`、`exact 1.8s`。

| 占比 | 帧 | 说明 |
|---|---|---|
| **28.7%** | `_canonical_sha256`（`knowledge_read.py:147/153`） | 规范化 JSON 哈希 |
| └ 其中 **90.8%** | **`bind_trace`**（`:1345` 31.2%、`:1352` 27.3%、`:1358` 32.3%） | **轨迹绑定**：每个 trace 对象要做 3 次 `model_dump` + 3 次 canonical 哈希（candidate id → evidence id → content hash） |
| └ 仅 5.5% | `bind_content`（`:164`） | 内容模型自哈希（**不是**主因） |
| **10.0%** | `_normalize`（`knowledge_read_isolated.py:8503`）经 `visit`（`:8523`） | 对每个标量做 NFKC + casefold + split 的**递归规范化** |
| **10.3% / 7.1%** | numpy `read_array` / `_read_bytes` | 读 `vector_matrix.npz`（1.68GB） |
| ~7% | pydantic `model_dump` / `__init__` | 模型（反）序列化 |
| ~15% | asyncio runner / provider / SSL | 等网络轨（web/embedding） |
| **1.9%** | `_ContentModel` 整体 | 内容寻址模型的总开销其实很小 |

## 3. 分段微测（索引副本，隔离）

| 步骤 | 耗时 |
|---|---|
| `open_manifest_verified_index_snapshot`（号称 fast-boot） | **59.9 / 65.3 / 60.5s**（三次） |
| └ 其中产物哈希 1.67GB（lookup 638MB + milvus 1029MB） | **10.24s** |
| └ 其中 **Milvus 检查** | **≈50s 是在等 60s 超时**（`failed to get mvccTs` 每 60 秒一次）——而服务期**从不查询 Milvus** |
| `vector_matrix.npz` 载入（51,026×4096 float64） | **1.41s** |
| 远端查询嵌入（`100.64.0.27:18005`） | **0.03s**（三次） |

## 4. 结论：钱花在两种"重复计算"上

1. **重复哈希/重复规范化**（采样里合计 ≈36%）：`bind_trace` 对**不可变**的轨迹对象每轮重算 3 个 canonical 哈希；`_normalize` 对每个标量值递归重算。二者都是**确定性函数 of 不可变数据**，本可"算一次、存下来"。
2. **重复装载**（≈10% + 冷态放大）：1.68GB 矩阵与索引句柄按会话重新装载；冷热差异（3s ↔ 19s）主要来自页缓存与 Milvus 那 50s 超时等外部状态。

## 5. 对修复的直接含义（供 `serving-index-process-scope` 使用）

| 项 | 动作 | 预期 |
|---|---|---|
| 索引/矩阵/句柄 | 提升为**进程级一次 + 启动预热** | 抹掉每会话的装载与冷态抖动 |
| Milvus 检查 | 从查询路径移出（服务期不用它），或修好客户端 | 去掉 ~50s 量级的等待 |
| `bind_trace` 3 连哈希 | 每个不可变 trace **算一次并缓存**（或改为惰性计算） | 有望吃掉 ~1/4 的采样占比 |
| 标量规范化 | 改为**构建期预计算**或进程级 memo（数据不可变） | 吃掉 ~10% |
| 审计需求 | 启动时落一份 **verification receipt**（哈希 + 耗时） | 可追溯性不减、运行期成本归零 |

> 本文件与 `.agents/runs/serving-index-process-scope/attribution-20260915.md`（英文原始证据）配套；
> 变更契约见 `.agents/runs/serving-index-process-scope/verification-contract.md`。
> 局限：单次采样窗口；结论与分段微测、冷/热 lane 计时三者互相印证，若要更紧的置信区间可重复采样。
