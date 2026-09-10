# C2.1b 第三次启动阻塞 — `_supplementary` 烘入 lookup_content，serving 线读侧缺数据线的剥键块（2026-09-10）

## 结论（一句话）

run14 sealed 包的 public lookup 文档中有 **903 篇**（company 899 / professor 4）的
`lookup_content` JSON 文本内烘入了 `_supplementary` 键（multi-value-enrichment 为加宽
检索面写入）；数据线读侧 `_validated_public_projection` 有专门的剥键块（剥
`_supplementary`/`_quality_tier` 后再过 Pydantic），**serving 线从未移植这一段**，
启动时在第一篇带键文档上 fail-closed。这是"数据线 vs serving 线代差"的第四个表现，
且发生在**查询/加载路径**（前三个在封印/loader/索引模型）。按纪律停下汇报，未修任何代码。

## 原始报错（c2-scratch-boot3.log，原样）

```
serving_pack_loader.py:1565 create_serving_pack_knowledge_read
→ knowledge_read_isolated.py:6914 _create_audited_lookup_view
→ :6925 _public_lookup_entries → :8072 _validated_public_projection
pydantic_core._pydantic_core.ValidationError: 1 validation error for CompanyProjection
_supplementary
  Extra inputs are not permitted [type=extra_forbidden, input_value={'technology_route_summar...组件设备销售。']}]
```

末行 `fast_boot=0`。启动墙钟约 8 分钟（t≈500s）后失败，未就绪；RSS 峰值约 28G
（监控值 30.0G 含生产 2.3G）。

## 正面证据（本次失败同时确认了两件事）

1. **C2.1p/q 移植生效**：`open_serving_pack_authority` 完整通过（含
   `supplementary_field_values` 模型字段透传、封印 scalars、loader
   `exclude_unset=True` 条件传入），失败点在更后面的 knowledge-read 组合阶段。
2. **官方封印有效**：sealed 包通过了 loader 的全部权威校验——封印器日志缺失的
   dogfood 相位（`dogfood_open`，进程在 manifest_written 后被会话断连杀掉）由本次
   启动实测补上。

## 证据链

1. **带键文档实测**（sealed 包 lookup.sqlite3，只读 `mode=ro&immutable=1`）：

   | 域 | 总数 | 含 `_supplementary` | 含 `_quality_tier` |
   |---|---|---|---|
   | company | 7,089 | **899** | 0 |
   | paper | 24,520 | 0 | 0 |
   | patent | 11,504 | 0 | 0 |
   | professor | 3,958 | **4** | 0 |

   `_supplementary` 形态：`dict[str, list[str]]`，如
   `{"technology_route_summary": ["深圳市国微三代半导体…"]}`；professor 侧为
   `profile_summary`/`homepage`/`title`（张雅鸥/于广军/王晓浩/丁文伯 4 人）。
   （注意：`document_json` 外层 LIKE '%"_supplementary"%' 查不到——内层 JSON 字符串
   的引号被转义；须对 `json_extract(document_json,'$.lookup_content')` 做 LIKE。）

2. **数据线读侧有剥键块，serving 线没有**：
   - 数据线 `knowledge_read_isolated.py:7954-7967`（`_validated_public_projection` 开头）：
     注释明言 "Multi-value enrichment adds _supplementary/_quality_tier to lookup_content
     for wider lexical search; strip before Pydantic validation (the projection models
     have extra="forbid")"，随后 `json.loads` → `pop("_supplementary")` /
     `pop("_quality_tier")` → `document.model_copy(update={"lookup_content": …})`，
     再走进管校验。剥键后的副本同时供 lineage 校验和 round-trip 校验使用，自洽。
   - serving 线同函数（`knowledge_read_isolated.py:8068-8098`）**没有这一段**，
     直接 `CompanyProjection.model_validate_json(document.lookup_content)` → 撞
     `extra="forbid"`。除剥键块外两函数逐字节一致；`_public_lookup_entries` 两线
     也逐字节一致。

3. **唯一受影响解析点**：两线对 `lookup_content` 的严格解析只有两处——
   `_validated_public_projection`（public 四域）与 `_validated_internal_document`
   （person/technology_route 内部引用，两线逐字节一致、均无剥键）。内部引用文档
   不带 `_supplementary`（受影响文档全部落在 public 域），故只需补 public 一处。

4. **同一次 multi-value-enrichment 的两半**：C2.1p 移植的是**模型/管线半**
   （`IndexProjectionRequest.supplementary_field_values` 字段、封印 scalars、loader
   透传）——管 pack authority；本次撞上的是**读侧半**（剥键块）——管 lookup 读入。
   C2.1q"index_projection.py 一个文件即零漂移"的假设由此被证伪。

## 附：两线 `knowledge_read_isolated.py` 全量 drift（16 hunk / 338 行）分类

此前该文件差异未核（§2 清单只到文件级）。本次逐 hunk 过一遍：

| hunk | 方向 | 内容 | 定性 |
|---|---|---|---|
| 1-2 | serving 独有 | `_compact_company_alias` 导入 + 派生短名通道（约 35 行，`_resolve_named_company_patent_source`） | serving 领先 |
| 3-6 | serving 独有 | `_direct_patent_applicant_scan` 抽函数（113 行）+ 无 per-edge eligibility 时 company→patent 并集调用 | serving 领先（数据线仍是内联旧版） |
| 7-8 | 数据线独有 | `_professor_vector_display_names` O(1) 教授文档索引（2026-08-31 性能修复） | 数据线领先；serving 仍是 O(n×m) 线性扫 |
| 9-11 | 数据线独有 | 向量 trace 校验降级：`rel_tol 1e-12→1e-6`、mismatch 由 raise 降为 warning、函数开头直接 return（2026-08-30：embedding 服务在 build/serve 间迁移，哈希差异属环境性） | 数据线刻意放宽；**serving 仍是严格版——查询期潜在雷** |
| **12** | **数据线独有** | **本次阻塞：`_supplementary`/`_quality_tier` 剥键块（14 行）** | **数据线领先，启动硬阻塞** |
| 13-14 | 数据线独有 | `_exact_query_phrase`（剥 `[lane=exact]` 尾标 + 引号解包，Stage0-G2a）+ paper/patent 长标题包含匹配（G6） | 数据线领先；serving exact lane 是旧版 |
| 15-16 | 数据线独有 | `_matches_query_identifier_token` 拉丁标识符回退（`_IDENTIFIER_TOKEN_PATTERN`） | 数据线领先；serving lexical lane 是旧版 |

即：drift 是**双向**的。serving 在公司→专利召回侧领先；数据线在教授向量性能、
向量 trace 环境适配、exact/lexical 查询匹配、剥键块上领先。

## 修复选项（归主上下文决策，本切片未动任何代码）

- **选项 A（推荐，最小移植）**：把数据线剥键块（data-rebuild
  `knowledge_read_isolated.py:7954-7967`，14 行含注释）逐字移植到 serving 线同函数
  开头。理由：这是数据线为同一内容形态的自有生产机制；剥键后 lineage/round-trip
  校验照旧生效（不削弱验证）；新增引脚测试可构造带 `_supplementary` 的
  LookupProjectionDocument 走红绿。
- 选项 B：投影模型放宽 extra —— 违反"不削弱验证"纪律，且 round-trip 校验
  （`model_dump_json()` vs stored content）随后即会失败，不可行。
- 选项 C：改数据线不写 `_supplementary` 进 lookup_content 并重跑 run14 —— 推翻
  multi-value-enrichment 的加宽检索面设计，代价是一次完整 rebuild，不成比例。
- 后续独立决策点（不在本切片）：hunk 9-11 的向量 trace 严格版在 C2.1d 25 轮
  重基线期间若命中向量道可能 fail-closed（数据线降级注释说明哈希差异是环境性的）；
  hunk 13-16 意味着 serving 的 exact/lexical 道比数据线旧一代，可能影响重基线得分
  ——但 s12f 基线的 21 PASS 就是在本 serving 代码上跑出的，自洽性无新问题。
