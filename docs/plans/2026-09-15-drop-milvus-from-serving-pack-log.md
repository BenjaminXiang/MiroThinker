# 服务包瘦身：`milvus.db` 退出服务包（P1）

> 定位：R9「过度设计消除」阶段一 P1 片的执行日志（对人）。
> 计划出处：`2026-09-15-requirements-gap-plan.md` §3.2 P1 行、§9.2 消除清单前两行。
> Agent 侧契约：`openspec/changes/drop-milvus-from-serving-pack/`。
> 证据目录：`.agents/runs/drop-milvus-from-serving-pack/`。
> 分支：`fix/slim-serving-pack`（基线 `2fe4c16c`）。

---

## 1. 一句话结论

服务包里的 1.03GB `milvus.db` **没有任何查询消费者**，却每次启动都要打开并逐行读回 5.1 万点（其中约 50s 卡在 Milvus Lite 不支持的 mvccTs 查询），5 天里还因单写锁造成 2 次启动失败。
本片把「点对象的权威存储」从 Milvus 行内 `point_json` 迁到**同一个 release 的 `lookup.sqlite3` 里新增的 `index_point` 表**，服务包（v2 契约）不再包含 Milvus 文件，启动路径**完全不 import pymilvus**；带 `milvus.db` 的旧包（v1）照旧可启动。

**一个权威副本 + 一次证明**：release 目录 = `lookup.sqlite3`（文档+点） + `vector_matrix.npz` + `relationships.json` + `catalog` + `manifest` + marker。

## 2. 为什么点对象不能"顺手删掉"

P1 不是删文件，而是给 5.1 万个 `IndexProjectionPoint` 找新家。事实：

| 存储 | 有什么 | 能不能替代点对象 |
|---|---|---|
| Milvus `point_json` 列 | **完整点对象**（`embedded_content` / `embedded_content_sha256` / `embedding_model` …） | 唯一权威，被判"无查询消费者"要撤 |
| `lookup.sqlite3` → `lookup_document` | `LookupProjectionDocument`（`lookup_content` / `lookup_content_sha256`） | **不能**：字段不同、哈希不同 |
| `vector_matrix.npz` | `point_ids` + float64 矩阵 + 范数 | **不能**：只有 id 和向量，没有正文与元数据 |

⇒ 必须新设一个权威存储，并要求它：打开开销小、天然随包哈希绑定、改动面最小。

## 3. 选型（T1 结论）

**选 A：在 release 的 `lookup.sqlite3` 里加一张 `index_point` 表**（而不是独立小文件）。

```sql
CREATE TABLE index_point (
    point_id TEXT PRIMARY KEY, release_id TEXT NOT NULL,
    projection_id TEXT NOT NULL, canonical_object_id TEXT NOT NULL,
    embedded_content_sha256 TEXT NOT NULL, point_json TEXT NOT NULL
) STRICT;
```

理由：
1. **0 个新文件**——启动本来就只读打开这个文件取 4.7 万条 lookup 文档；点表顺带读，manifest/挂载收据/哈希登记**都不用加新条目**；
2. **证明强度不变**——四个元数据列与 Milvus 行内列一一对应，保留「物理行必须与点 JSON 一致」的逐行绑定；
3. **改动面最小**——只动"写点/读点"两处 + manifest 版本号，不引入新的文件契约、新的复制步骤、新的拒载分支；
4. 符合 §5 目标形态「一个权威副本」：同一事实只留一份真身。

v1/v2 区分方式：**`manifest.json: schema_version`**（`…-v1` / `…-v2`），不做文件嗅探。marker 文件格式不动（它管的是"这个目标不能是原始 Milvus"这类安全身份）。

失败一律 fail closed：v2 缺 `index_point` 表 → 拒载；v2 的 index root 里还留着 `milvus.db` → 拒载（半迁移目录当场暴露）；点集与 receipt 不一致 → 拒载。

## 4. 做了什么

| 文件 | 变化 |
|---|---|
| `apps/miroflow-agent/src/data_agents/canonical_v2/index_projection_isolated.py` | 新增 `index_point` 写/读（`write_lookup_index_points` / `_read_index_points_from_path` / `has_lookup_index_points`）、`_open_verified_index_snapshot(point_store=…)` 分流（v2 分支不碰 Milvus）、`convert_isolated_index_to_v2` 迁移函数 |
| `…/serving_pack_loader.py` | `PACK_SCHEMA_VERSION_V2`、`PACK_INDEX_FILENAMES_V2`、`pack_index_filenames()` / `pack_point_store()`；manifest/挂载收据/全量哈希按版本选文件清单；快照打开按 manifest 选点存储 |
| `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12c/build_serving_pack.py`（封包器） | `--pack-schema-version`（默认 v1 不变）；v2 不复制 `milvus.db`、要求已转换的 index root；占位符普查整段删除 |
| `…/canonical_v2/placeholder_scrub.py` | 删除普查代码（`scan_lookup_index` / `classify_field_value` / 字段清单），**保留**读侧用的匹配器与 `scrub_*` |
| `.agents/runs/drop-milvus-from-serving-pack/{convert_index_to_v2,seal_scratch_pack,make_scratch_bundle,probe_scratch}.py` | 迁移 CLI、scratch 封包、scratch bundle、探针 |
| `apps/miroflow-agent/tests/canonical_v2/test_serving_pack_no_milvus.py` | 新增 14 个测试（v2 启动不碰 Milvus / v1 兼容 / 三类拒载 / npz 锚双向 / 收据 / 封包器 / 迁移 / 删除项） |

**占位符普查的处置＝删除，不是接门**，理由（详见 design.md §5）：
- 它是**源数据**的属性，封包器修不了它；在此设门只会因"包工改不动的原因"卡发布，最终被降阈值绕过；
- 计数随语料规模增长（7,086 家公司 → 3,097 次命中），绝对阈值没有意义；按比例设门属于数据质量线（R15/D1）的事；
- 真正保护用户的是**读侧 scrub**（`knowledge_read_isolated` / `knowledge_serving_isolated` 都在用），它保留、测试保留；
- 仓库自己的第一性原理文档已把它列为反例："一个没有读者的数字"（`2026-09-15-proof-chain-first-principles.md:170`）。

## 5. 做了什么验证

**① 新增测试（14 个，`test_serving_pack_no_milvus.py`）**：v2 授权在 `pymilvus` 被 import 守卫毒化时仍能打开（且 `_open_milvus_client` 被替换为抛错探针）；v1 包在同样毒化下**必须失败**（证明 v1 路径没变）；缺表 / 留 Milvus / 点集漂移三种拒载；npz 锚多一个点、少一个点两向都拒；收据首启 `full`、再启 `receipt` 且文件清单只有 lookup+marker；封包器 v2 不产 Milvus 且拒绝 v1 index root；迁移保点集、去 Milvus、重写 marker；占位符普查已删而匹配器还在。

**② 既有套件**：`test_serving_pack_loader.py` + `test_placeholder_scrub.py`（37→36，删掉普查那一个）+ `test_fast_boot.py` + `test_knowledge_read_isolated.py` 全绿。

**③ scratch 端到端（18296，run15 素材副本）**：

| 项 | 结果 |
|---|---|
| 迁移（v1 index → v2 index） | 51,026 点 / 47,068 文档；`lookup.sqlite3` 668.9MB → 896.9MB（+218MB），`milvus.db` 1.078GB 不再产出；**index root −850MB（−24.8%），pack −850MB（−16.5%）** |
| 权威等价 | v2 pack 的 `index_result_content_sha256` 与 run15/v1 包**逐字相同**（`690946f3…`）——即"sqlite 点集 == Milvus 点集"由启动路径的哈希重建直接证明 |
| v2 启动日志 | 全文出现 `milvus` **0 次**、无 mvccTs 超时；挂载收据只登记 `lookup.sqlite3` + marker |
| 挂载耗时（收据） | v2 **289.1s** vs 同机 v1 **345.9s**（全量挂载对照 311.5s → 289.1s），启动阶段省 ≈31–57s |
| replay 门 | 见下 |
| 两个逐字探针 | `字节跳动` → 答案含 `ByteDance Ltd.`；`优必选有哪些专利` → **32 条本地 CN** |
| 用户案例 | `详细介绍一下 国先中心（深圳）` → 答案完整、`web_items=[]`（与基线一致） |
| v1 兼容 | 同一份代码跑 run15 副本包，启动 + replay 冒烟通过 |

（外呼配额：3 个探针 + replay 7 会话各 1 轮，全部走 web 轨，如实计入。）

## 6. 影响哪些问题

- R9 消除清单：`Milvus 陪跑物料 + 逐行回读`（判据 1/2/3）→ **本片处置**；`placeholder 普查`（判据 2）→ **本片删除**；
- G22「无读者证明仍在跑」→ 两项都已落地（另一项 Milvus 逐行回读同步消失）；
- P2（启动证明降级）的大前提就位：v2 包不再有 1GB 文件要哈希/证明。

## 7. 未做 / 待拍板

1. **未部署**：18188 仍跑 run15（v1）——部署与 run16 切包（含回滚演练）按计划合并到同一个窗口；
2. 数据线构建路径（`create_isolated_index_projection_builder`）仍写 Milvus；run16 用本片迁移脚本把 index root 转成 v2（或后续切片让构建直接产出 v2）；
3. 非 pack 的 envelope 服务路径 + `audit_isolated_index_snapshot`（需要向量回读的全量审计）仍只支持 v1——设计里已明确边界。
