# C1 批 0 验证 — 占位过滤 + 锚定声明 + 封装门（2026-09-11）

> 变更（close-workbook-gaps，design.md §C1 五条锁定裁定；范围依据
> `c1-batch0-scoping.md`，门契约 `c1-gate-contract-v1-proposal.md` §7/§10，
> RED 工件 `verification-contract.md` §C1 批 0）。三件事：读侧投影级 scrub、
> 锚定声明骨架（只接 F1 消费方 a）、s12c 封装门（告警不阻断）。未重启/未部署
> 18188，未跑 live replay（归主上下文验收窗口）。

## 1. 改动清单

| 文件 | 改动 |
|---|---|
| `src/data_agents/canonical_v2/placeholder_scrub.py`（新） | 四族匹配器（(a) 英文整句前缀 (b) 中文整值/前缀含 `^无$` (c) 粘连 `未找到` run token 级擦除 (d) 结构值 `^-+$`/`none`/`n/a`），140 字符上限保留；`scrub_projection_payload`（跳过记录身份字段 name/title/patent_number）；门侧普查 `scan_lookup_index`（g1 classify 语义复刻 + 值级拆分）。 |
| `src/data_agents/canonical_v2/knowledge_read_isolated.py` | `_projection_terms` content_terms 改喂 scrub 后 payload（验证之后，:8141-8154 血缘断言不动）；`_projection_category_term_buckets` 的 industry 名/双 tags/product_description 逐值 scrub（name/normalized_name 身份字段不动）；F1 五个硬编码常量删除，改从 `PACKAGED_ANCHORING_DECLARATION.f1_category_scoring` 读（`_F1_CATEGORY_SCORING`），实测依据注释保留并注明值已入声明。 |
| `src/data_agents/canonical_v2/anchoring_declaration.py`（新） | 加载器（domain_catalog 先例：importlib.resources 读资源、重复键拒绝、未知 schema 直接 RuntimeError fail-closed、ContractModel 校验）。 |
| `src/data_agents/canonical_v2/catalogs/anchoring-declaration-v1.json`（新） | 种子：g3-vocabulary 110 词（S77/T31/N2，S 档 anchor_field=命中最多的结构化字段）+ F1 打分块（8/4/2/2/2，与旧常量逐值相同）+ `generated_from.pack_sha256=c392d559…`（= sealed run14 manifest 的 lookup.sqlite3 哈希，实测与 index-v1 源文件同值）。生成器：`c1_seed_anchoring_declaration.py`（可复算）。 |
| `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12c/build_serving_pack.py` | 门插在 `index_snapshot_verify` 之后、`_prepare_pack_dir`/拷贝循环之前：读源 index（`mode=ro&immutable=1`）→ 旁挂报告写到包目录**同级**（`<pack-dir>.placeholder-scan-report.json`，不进包不进 index；进包还会触发 fresh-dir 拒绝与 manifest 固定清单问题）；打印计数；扫描异常只告警不退出（首版 warn-only）。 |

落点行号与 scoping 核对：`_validated_public_projection` 血缘断言 :8141-8154（scrub 在其后）、`_projection_terms` :8158 / `_projection_category_term_buckets` :8195、F1 常量区 :8406-8432、`s12c` :243/:248-268——全部与设计一致，无口径偏差。

## 2. 新增单测（12 个，全部 GREEN；RED 以夹具内对照钉死）

`tests/canonical_v2/test_placeholder_scrub.py`（10 个）：
- 四族正例：英文整句前缀（Not supplied/no data/NOT AVAILABLE…）、中文整值（未找到/暂无/未知/待补充/单字无）、结构值（-/--/none/N/A）、粘连擦除（run14 原样 `VE1未找到未找到B,VE3未找到AS等系列GPS/北斗定位器` → `VE1B,VE3AS等系列GPS/北斗定位器`，真词保留）。
- 负例：`未知词识别…` 长正文（>140）存活（cap 是挡它的唯一机制）；短合法值存活；`无数据` 不被 `^无$` 误杀；嵌入句中的英文片段不误杀。
- 身份字段：name/title/patent_number 即使值为占位也不被值清洗（置空留给构建侧 R1/R2）。
- 投影级：`_projection_terms`/`_projection_category_term_buckets` 经 `model_construct` 夹具——RED pin 断言未 scrub 的 dump 确实含 `未找到`/`暂无`（旧路径下它们进 content_terms/桶），GREEN 断言 scrub 后消失且真词保留、输入不被突变。
- 门扫描器：临时 sqlite 夹具（2 company + 1 professor 文档）——字段级 3/1、整值 未找到 1、粘连 1、样例入报，扫描前后 db 文件 sha256 不变（只读实证）。

`tests/canonical_v2/test_knowledge_read_isolated.py`（+2）：
- 未知 schema/非对象/重复键三路 fail-closed；合法载荷可解析。
- F1 等价：声明打分块 == (8,4,2,2,2) 且 `module._F1_CATEGORY_SCORING is scoring`；行为等价用例（label 16 > tag 8 > summary 2 排名）与硬编码常量时代逐值一致。

## 3. 预存回归（与基线逐数对照）

| 套件 | 结果 | 基线 |
|---|---|---|
| read_isolated + serving_isolated + turn_trace_reporting + serving_pack_loader + placeholder_scrub（新） | **340 passed** | 328（F4 后）+ 12 新增 = 340 ✓ |
| 其中 F1 断言所在两文件（read_isolated / serving_isolated） | 全绿，无一条断言改动 | — |

`serving_pack_loader` 的 `_PackFixture` 走 `build_serving_pack_from_authority`——封装门在测试固件上真实执行（微型 index 扫描 + 旁挂写入 tmp），全绿。

## 4. 门 dry-run（run14 index，只读）

- 命令形态：`scan_lookup_index('/var/tmp/mirothinker-data-v2/index-v1/lookup.sqlite3')`（与门内同一函数、同一 `mode=ro&immutable=1` 打开方式）。
- 计数（与只读普查四数全对上）：**professor 12,872 / company 3,099 / 粘连 189 / 整值未找到 1,817**；另报 `whole_value_weizhaodao_prefix=2`（更长的 `^未找到…` 整值变体，与 exact 1,817 分列）。by_field 头部：professor.paper_summary 3,958 / patent_summary 3,958 / title 2,515 / company.technology_route_summary 1,600。
- 零字节实证：dry-run 前后 `index-v1/lookup.sqlite3`、`index-v1/milvus.db`、`serving-pack-run14-sealed/lookup.sqlite3` 三文件 sha256 逐一对照一致（c392d559…/a10f4b06…/c392d559…）；报告写在 /tmp，未落 index 或包。
- 报告样件：`/tmp/c1-placeholder-scan-report.json`（schema v1，逐域/字段计数 + 样例 + previous_pack_report=null）。

## 5. 保真边界与遗留风险

- 读侧盲区（design §C1 批 0 必须声明）：raw `lookup_content` / `lookup_content_sha256` / 读原文路径（internal reference :2686/:2701、管理台核对视图）仍见占位；vector 语料（milvus.db、professor research 视图）不受影响。批 0 只清派生词表。
- 门首版 warn-only：扫描异常也只告警；转 fail-closed 需批 2 校准后另行裁定。
- F1 触发词/停用短语仍硬编码（只迁 multiplier/tier/阈值五项；查询侧词表不是锚定数据）。
- 声明 terms 数组批 0 无消费方（骨架种子）；答案侧措辞（消费方 b）归 answer-quality 切片。
- `_projection_terms` 的 :2729/:5379 调用点只取 display_name（位 0），不受 content_terms scrub 影响。
- 回归之外的行为差分（GT 查询 lexical/category recall 不变）须 live 证据——主上下文验收窗口内做，本切片不碰 18188。

## 6. 产物

- 代码：`placeholder_scrub.py`、`anchoring_declaration.py`、`catalogs/anchoring-declaration-v1.json`、`knowledge_read_isolated.py`（3 处）、`s12c/build_serving_pack.py`（门）。
- 测试：`test_placeholder_scrub.py`（新 10）、`test_knowledge_read_isolated.py`（+2）。
- 工具：`c1_seed_anchoring_declaration.py`（种子生成器，可复算）。
- 本文件。
