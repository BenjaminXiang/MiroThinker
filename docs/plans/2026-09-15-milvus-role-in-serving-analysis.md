# Milvus 在服务期的真实角色与 60 秒空转的深层原因（2026-09-15 代码级归因）

> 定位：回答"Milvus 到底有没有被用到、为什么"——对一个直觉的代码级求证。
> 状态：一次成文分析（write once）。关联变更：`serving-index-process-scope`（其 T5 的归因输入）。

---

## 1. 一句话结论

服务期**没有任何查询走 Milvus**——向量打分是本地 numpy 矩阵（`vector_matrix.npz`），
这是 2026-08-03 perf 提交的有意设计；但 Milvus 仍是 serving pack 的一等物料，并在
**每次打开索引时被全量逐行读回**做证明链校验；这一读回经由 pymilvus 的 iterator
触发 Milvus Lite 不支持的 mvccTs 查询 → **每次 ~50 秒纯空转**。

**"没被用到"是设计；"每次打开付 50 秒 + 1.03GB 物料无查询消费者"是过度设计
叠加一个可避免的实现选择。**

## 2. 事实链（file:line）

| # | 事实 | 证据 |
|---|---|---|
| 1 | 打分本地化（有意）：build 时已嵌入过的向量额外写成 `vector_matrix.npz`，服务 boot 直接载矩阵打分，"skip the ~77s first-request full re-embed"，"float64-identical" | `index_projection_isolated.py:615-668` docstring；perf 提交 `3336aabe`（2026-08-03） |
| 2 | 服务期零 Milvus 引用 | `knowledge_read_isolated.py` / `knowledge_serving_isolated.py` 中 "milvus" 出现 **0** 次；非零者只在 build / 校验加载 / 管理面状态文件 |
| 3 | pack 契约仍含 Milvus，boot 打开索引 | `serving_pack_loader.py:131` `PACK_INDEX_FILENAMES=("lookup.sqlite3","milvus.db")`；`:642` `open_manifest_verified_index_snapshot(...)` |
| 4 | 打开时**全量逐行**读回 Milvus | `_read_all_points_with_client`（`index_projection_isolated.py:826-860`）：`query_iterator(batch_size=128)`，output_fields 含 `point_json`/`vector` |
| 5 | 50 秒的来源 | pymilvus `orm/iterator.py:243-260`：iterator 初始化先向 server 要 mvccTs；Milvus Lite 不返回 → 60 秒级超时后 warn "failed to get mvccTs … use client-side ts instead" 并回退。**同文件** `_read_points_with_client`（`:791-823`）用 `client.get(ids=…)`，**不需要** mvccTs |
| 6 | Milvus 今天仍"承重"：是 npz 的校验锚 | `knowledge_read_isolated.py:7563-7569` `load_persisted_vector_matrix(points=snapshot.points,…)`——`snapshot.points` 正是 Milvus 回读的产物 |
| 7 | boot 哲学（自述） | `serving_pack_loader.py:1-33`：per-file hash 全验、"Every reconstructed giant model is re-hashed at boot … any drift refuses the boot" |

## 3. 深层原因（三层）

1. **两代设计叠加**：第一代 = isolated index target 证明链（marker/receipt/projection，
   Milvus 是被证明的物理副本）；第二代 = perf 补丁（npz 本地打分，只替换了"打分"环节）。
   补丁没有回头回收第一代里**已无消费者**的 Milvus 读回。
2. **证明做在了错的层**：同一事实在 build / seal / boot 三次重复证明；bundle 已有
   per-file sha256 + 封印期全量校验，boot 再逐行回读属"重复证明"，代价 ~50s/次打开。
3. **可避免的实现选择**：即使保留逐行证明强度，把 iterator 换成 `get`/`query`
   即可去掉 50 秒——这是 pymilvus/Milvus Lite 的 API 适配问题，不是 Milvus 的固有成本。

## 4. 影响

- 每次打开索引 ≈50s 空转 + ~1.03GB 读 IO；pack 里 1.03GB 物料**无查询消费者**（但今天是 npz 的校验锚）；
- 校正排障直觉：向量轨 3–19s 与 Milvus **无关**（它不在链路里），真因是重复哈希/重复装载（见配套归因文档）；
- 隐患：若未来有人假设"服务期可用 Milvus 做 ANN"，会直接踩 Lite 无 server ts 的坑；且设计上它被限定为 verified copy（`evidence_adapters.py:593` "original Milvus is forbidden"）。

## 5. 修复选项（供 `serving-index-process-scope` T5 决策）

| 选项 | 动作 | 收益 | 代价/风险 |
|---|---|---|---|
| **A 最小** | `query_iterator` → 分批 `client.get`/`query` | 去 ~50s；行级验证强度不变 | 纯实现改动 |
| **B 对齐封印层** | boot 不再逐行读 Milvus（marker/receipt/文件 hash/行数即可），逐行证明留在封印期；npz 校验锚改为 lookup 回读 | 再省秒级 + 少 ~1GB 读 | 需小改造 + 明确"轻校验"边界 |
| **C 物料层** | 评估 pack 是否还需要 `milvus.db` | pack −1.03GB、启动少读 1GB | pack 契约变更（另立 change）；会丢掉 npz 的现成校验锚，须 B 先落地 |

三者与已裁定的方向一致：**"挂错包/截断/过期"的校验可以做轻，不必每次打开重证。**

## 6. 关联

- 延迟归因（本分析的 60s 数字来源）：[服务期延迟归因](./2026-09-15-serving-latency-attribution.md)
- 证据文件：`.agents/runs/serving-index-process-scope/milvus-role-20260915.md`
- 变更：`serving-index-process-scope` T5（"take Milvus off the query path"）

---

## 7. 追问："打分本地化"这个设计本身正确吗（同日补充实测）

**结论：正确，而且实测优于它旁边的 Milvus 副本；但整条设计有三个真问题——两个在周边，一个在自身。**

### 7.1 实测对照（run15 索引副本，只读；Milvus 在 /tmp 副本上打开）

| 维度 | numpy 本地矩阵（现设计） | Milvus Lite 副本（替代路线） |
|---|---|---|
| 每次向量检索 | **18.5ms**（51,026×4096 float64 全量 gemv） | **116.4ms**（warm TOP10）；首搜 2762ms |
| 结果 | 精确 cosine | **top10 同序同分**（id 集与顺序完全一致）——`AUTOINDEX` 报 `indexed_rows=0`，Lite 实际仍是精确扫描 |
| 打开 | npz 载入 1.41s | client open 0.57s；iterator 读回时 60s 级 mvccTs 空转 |
| 常驻 | 1.68GB（float64）；float32 可 0.84GB / 11.8ms | 1.03GB 文件 + 引擎内存 |
| 依赖/确定性 | 纯 numpy、无客户端、确定性 | pymilvus 客户端 + Lite 兼容坑 |

⇒ **"换 Milvus 会更快"在本环境为假**：Lite 没有真 ANN。本地矩阵换来精确性 +
确定性 + 零客户端依赖，代价 18.5ms——对 TTFT 无关痛痒。**打分本地化的选择是对的。**

### 7.2 但整条设计有三个真问题

1. **两个真相源，一个没有查询角色**（最重）：见 §2/§4。第一性原理＝服务期只需要一个
   权威索引（lookup + npz）；Milvus 至多是构建/审计工件，不该进入打开路径（→ §5 选项 B/C）。
2. **本地路径自身的增长缺陷**：float64 是 2× 白送（float32 → 0.84GB / 11.8ms，但
   "float64-identical"曾是刻意属性，改 dtype 需单独 change + top-k 等价证据）；
   O(N) 全扫描有天花板——10× 语料（51 万点）≈ 185ms/查询 + 16.8GB 常驻，应**现在就
   写下天花板与触发条件**（例：point_count > 20 万 → 漏斗预筛或真 ANN 重新立项）。
3. **决策没有闭环**（根因判断）：perf 补丁（`3336aabe`）把"打分"从旧路径换成 npz 后，
   没有回头回答"Milvus 还留在这条链里做什么"。

### 7.3 正确形态

**一个权威副本 + 一次证明**：npz 是唯一服务索引；它的证明锚改为 lookup 回读
（而非 Milvus 回读）；Milvus 退役为构建工件——或未来真需要 ANN 时按"带索引的独立
服务"重新立项（那是另一个量级的部署决策，不属于本期）。
