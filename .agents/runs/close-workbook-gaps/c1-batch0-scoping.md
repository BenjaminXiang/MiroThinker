# C1 批 0 范围界定（只读，2026-09-11）——占位过滤 + 锚定声明

> 来源：explore agent-12 只读报告（serving worktree 视角）。设计裁定见
> `openspec/changes/close-workbook-gaps/design.md` §C1。行号口径：未注明者
> 均指 s11 worktree（`canonical-v2-s11-consolidation`）rev；主仓 rev 行号见
> G1/C1 文档（例如主仓 `knowledge_read_isolated.py:7978-7993` = s11 `:8248-8263`）。

## 0. 前置事实

- 生产 serving 线 = s11 worktree；`deploy/canonical-v2-backend.service` →
  `deploy/start-canonical-v2.sh:6` → s12g `serve-18188-command.sh`
  （`--serving-pack /var/tmp/mirothinker-data-v2/serving-pack-run14-sealed
  --index-root /var/tmp/mirothinker-data-v2/index-v1`）。
- 封印器唯一 builder = **s11 副本**：P4 runbook
  `full-column-serving-pack-rebuild/build_p4_serving_pack.sh:11`
  `BUILDER="$S11_RUNS/s12c/build_serving_pack.py"`（verifier 同例
  `s12f/post_build_verify.py`）。两 worktree 的 `build_serving_pack.py`
  已 `diff -q` 不同 → **门挂错副本等于没挂**。

## 1. content_terms 构建点与挂钩层

- 读侧：`lookup_content`（lookup.sqlite3 JSON）→
  `_validated_public_projection`（`:8110-8157`，`:8151` 断言
  `projection.model_dump_json() == lookup_content`）→ `_public_lookup_entries`
  （`:6923`）→ `_projection_terms`（`:8158`）→ `content_terms =
  _normalized_scalar_values(projection.model_dump(mode="json"))`（`:8191`）；
  `_normalized_scalar_values` `:8248-8263`；`_normalize`（NFKC+casefold+空格
  折叠）`:8232`。
- 消费点：exact 排他 `:8286`；structured 排他 `:8315`；lexical 子串
  `:8338`；F1 类目召回 `:8464`（打分 `:8487` 排他 `:8286` 侧）；
  `_has_excluded_term :8620`；vector 请求排他 `:7566`；manual sidecar 排他
  `manual_recall_points.py:100`。
- 打包侧：`index_projection.py:1024 _lookup_documents` → `:1040 content =
  projection.model_dump_json()` → `_supplementary` `:1044-1052` →
  `LookupProjectionDocument` `:1059-1080` → `index_projection_isolated.py:968
  _write_lookup_projection`（INSERT `:1009`；`materialize` `:229/:269` 仅对
  全新目标）→ 封印器逐字节拷贝进包 `s12c/build_serving_pack.py:248-268`
  并 hash 进 manifest（`:257-266`、`:377-381`）。
- 先例：打包侧占位抑制目前**只**对 vector 车道 professor identity 视图做过
  （`index_projection.py:62-64` 常量、`:752-756` 过滤）；lookup_content 全量
  保留占位，research 视图 `:758-771` 原样保留 `paper_summary/patent_summary`。

## 2. 占位模式清单（run14 sealed 包只读普查，47,071 文档）

- 种子：`g1_probe_fields.py:131-153` = 12 条前缀模式 + `PH_MAX_LEN=140` +
  `pattern.match`（前缀语义）。复算 run14：professor 12,872 / company 3,099。
- 建议 4 族：(a) 英文整句前缀
  `^(not supplied|no dedicated summary|no data|not available)\b`；
  (b) 中文整值/前缀 {`未找到`,`暂无`,`未知`,`待补充`} + 单字 `^无$`；
  (c) 子串 run 擦除（长值内连续 `未找到` 段）；(d) 结构值 `^-+$` /
  `^(none|n/?a)$`。
- 实测增量：前缀规则漏 **189 处粘连 `未找到`**（company
  product_description 88 / profile_summary 76 / technology_route_summary 23；
  patent abstract 1 / summary_text 1；样例
  `VE1未找到未找到B,VE3未找到AS等系列GPS/北斗定位器`）；**189 处擦 run 后
  全部仍有实体内容（0 处擦空）** → 不能整值丢弃，必须 token 级擦除。
  整值 `未找到` 1,817（860+631+326）、`暂无` 1、单字 `-` 4
  （company.industry / industry_tags / tech_tags / legal_representative）。
- 误伤边界（关键）：run14 `^未知` 命中仅 1 条且是**合法正文**
  （paper.summary_zh《未知词识别是自然语言处理中的关键问题…》），140 字符
  上限在挡它；放宽为子串或去长度阈值立即误杀。`^none$`/`^n/?a$` 零命中。
- 动作分派：值级命中 = "按空/写 null"（语料与覆盖统计用）；命中
  `name/title/patent_number` 时走 R1/R2 **记录级拒绝**（C1 §2.5），不是擦词。

## 3. 打包侧 gate 挂点（封印脚本内显式步骤）

- 步骤位（`s12c/build_serving_pack.py`）：`index_snapshot_verify :243` →
  拷贝+哈希 `:248-268`（`mark("index_artifacts_copied") :268`）→
  `authority_documents_written :332` → `manifest_written :381` →
  `dogfood_open :408`。建议：`:243` 之后、`:257` 拷贝循环**之前**读源 index
  （拒绝时不落字节）；或 `:268` 之后对包内副本复扫一次（与
  `post_build_verify.py` 复验风格一致）。
- 输入/输出/失败语义：输入 = release_id + lookup.sqlite3 路径（+ projection
  清单）；输出 = 旁挂 `placeholder-scan-report.json`（逐投影/字段计数 + 命中
  样例 + 与前包 diff）；**不得改写 lookup.sqlite3**（改即毁 manifest 哈希与
  release 绑定）。首版**告警不阻断**（与既有两处告警带一致），复测校准后转
  fail-closed。

## 4. 锚定声明消费方

- 现状：消费方已存在、规则硬编码在代码——F1 打分 `knowledge_read_isolated.py`
  字段分档 `:8195-8232` + 触发词/停用短语/`MIN_BIGRAM_COVERAGE=2`/
  `MIN_SCORE=2`/multiplier 8/4/2 `:8355-8440`；G3 产出已是数据
  （`g-series/g3-vocabulary.json`：`tier`/`hits`/`company_structured_coverage`/
  `admitted_by`/`in_lexicon`/`in_taxonomy_value`）。
- 建议骨架：`canonical_v2/catalogs/anchoring-declaration-v1.json`
  （先例 `domain_catalog.py:34` 读 `catalogs/domain-catalog-v1.json`，
  `:130` `json.loads`，未知 schema fail-closed）：
  `{schema_version, generated_from:{pack_sha256}, terms:[{term, tier,
  anchor_field, match_mode, multiplier, confidence_class, whitelisted}]}`。
- 消费方三处：(a) 检索侧 F1 加载替代硬编码常量、按 tier 分支
  （S=确定性过滤 / T=打分 + 答案带"仅文本锚定"声明 / N=无锚定分支）；
  (b) 答案侧低置信白名单（G3 §4.5-2）→ 置信声明（`serving:3184/3357`
  一带 confidence 字段）；(c) 构建侧缺口报表（字段清洗决策仍归 G1 R1-R9，
  避免双处方打架）。

## 5. 风险与前置

- 读侧过滤直接改变 live 线行为（exact/lexical 排他、F1 类目召回结果集全
  变），且**无需 rebuild 即刻生效** → 属"检索关键"改动，先 replay/回归
  证据再上 18188；回归面 = `tests/canonical_v2/test_knowledge_read_isolated.py`
  + `test_knowledge_serving_isolated.py`（F1 相关断言）+ 7 会话 replay 门。
- 读侧过滤盲区（批 0 必须写明）：只清"派生词表"，不改 pack 内容——
  `lookup_content` 原文 / `lookup_content_sha256` / 读原文路径
  （`:2686/:2701` internal reference、管理台核对）仍见占位；vector 语料
  （milvus.db）professor research 视图 `paper_summary/patent_summary` 占位
  不受影响。
- 须全量 rebuild 才生效：打包侧清洗（新 lookup.sqlite3）、vector 语料清占位、
  整包阈值复测（C1 批 2）、R1-R9 记录级"拒绝入库"。
- 前置/阻塞：① ADR-023 家规下封印器双副本已不同、数据线另有
  `SERVING_PACK_SKIP_HASH_VERIFY=1` 旁路——门的位置须锁 s11 副本；
  ② 门输出不得改写既有 sealed 产物（只能旁挂报告）；③ 占位匹配器扩展责任方
  与新来源变体入表路径需在批 0 定，否则新变体静默漏过；④ 本域动作须在
  `close-workbook-gaps` change 下进行。
