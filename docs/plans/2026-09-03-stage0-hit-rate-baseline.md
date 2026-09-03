# 阶段0：三命中率基线与 ROI 缺口清单（2026-09-03）

> 数据线阶段0传感器交付物。目标函数（已裁定）：**对池内每个真实实体：可达（查得到、可指认）× 诚实分级（呈现质量与数据质量一致）**。
> 三个可测指标：点名命中（exact）/ 语义命中（vector）/ 关系命中（relationship）。
> 测量对象：canonical 栈 127.0.0.1:18188，服务包 `candidate-v2-20260819-r1`（2026-08-26 产物，lookup 32,941 docs + milvus 776MB + relationships 2.4GB）。

## 一、测量设计（可复现）

两个传感器，全部只读：

1. **实体级盘点**（全量、无抽样）：`stage0_entity_inventory.py` —— 包↔池集合差异、别名覆盖、准入分层、绑定覆盖、答案关键字段非空率。产出 `stage0-inventory.json`。
2. **golden set 逐车道归因**（seed=42 抽样，34 查询）：`stage0_golden_attribution.py` —— 分层抽样实体，生成点名/点名-池外/属性/关系四类查询，打 `/api/chat/stream`，解析 `plan_done`/`retrieval_done`/`answer` 事件，逐查询归因。产出 `stage0-golden-set.json` + `stage0-attribution.json`。

复现（worktree `data/p4-serving-pack-rebuild`）：

```bash
cd .agents/runs/full-column-serving-pack-rebuild/stage0
uv run --directory ../../../../../apps/miroflow-agent python stage0_entity_inventory.py
uv run --directory ../../../../../apps/miroflow-agent python stage0_golden_attribution.py
```

## 二、基线结果

### 三命中率（修正后诚实口径）

| 指标 | 结果 | 明细 |
|---|---|---|
| 点名命中（目标被本地引用或 exact 命中） | **12/29 ≈ 41%** | 教授 5/5 ✓、专利号 3/3 ✓、企业 2/7、包内论文 2/4、池外论文 0/5 |
| 其中 exact 车道命中 | **3/24（仅专利号）** | 企业/教授/论文名称查询 exact 全部为 0 |
| 语义命中（属性查询有本地引用） | **2/4 = 50%** | 企业 2/2 ✓、教授 0/2 |
| 关系命中（关系车道召回目标关系） | **3/6 = 50%** | 教授→论文 3/3 ✓、企业→专利 0/3 |

修正说明：row21（池外论文）原判 PASS 实为误报——本地引用是 'company' 类型（语义邻居顶包），目标论文不在包内；rows29-31 原判 RELATION_NOT_PLANNED 实为 RELATION_EMPTY（关系车道已规划但 0 召回）。

### 逐车道观察

- **exact 车道对名称类查询全军覆没**（31/34 为 0；仅专利号 identifier 命中 1）。包括查询词=包内规范名全等的情形（如「深圳市飞象工业科技有限公司」exact=0、lexical=1）。
- **lexical/vector 基本都能召回**（vector 几乎恒 16=上限），但 **14/34 查询的最终引用全部是 web**——本地证据在融合/引用选择层被 web 挤出。
- 好消息：教授点名、专利号点名、教授→论文关系、企业属性查询四条链路是通的。

## 三、ROI 缺口清单（按修复性价比排序）

**G1 引用层 web 挤出本地证据（最高频失败：14/34）**
本地车道有召回（lexical 1–16 + vector 16）但引用全 web。点名类查询尤其致命：实体就在包里、被召回了、答案却只引澎湃/维基。对「查得到就引本地出处」是直接违反。修复面=融合/引用选择（`fusion-recall-floor-and-disclosure` 方向）：点名查询且召回含目标时必须本地引用。**纯代码线，不依赖数据补齐，建议最先切。**
（诚实标注：部分 LOCAL_DROPPED 的本地召回可能是语义邻居而非目标——但企业点名行（row1）lexical=1 且查询=规范名，目标在召回内无疑，诊断对该子集成立。）

**G2 exact 车道对名称零命中 + 别名面缺失**
名称查询 exact=0（含规范名全等情形——exact 匹配规则对名称类 display terms 是否生效存疑，修复切片需先读 `_matches_exact_request`）；包内企业别名仅 4.8% 有值（342/7,089），ByteDance Ltd. 全包无任何中文对应（仅 2 家英文名企业无 CJK）。修复面=exact 匹配规则 + 别名闭包（数据工件，载体无关）。

**G3 企业↔专利关系类型断链（关系命中率 0/3 的根因）**
规划策略 `supported_relationship_paths` 含 `company_has_patent` 双向（[knowledge_serving_isolated.py:6054](../../apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py)），但**包内关系注册表没有该类型**——绑定以 `patent_has_applicant` 入库（注册表 c 段完整枚举所有 company_* 类型，无 company_has_patent），规划器永不会遍历它。2.4GB 关系文件里躺着池内 957 条 resolved 绑定却不可达。修复面=构建侧统一关系类型 ID（或在路径注册支持 applicant 遍历）——一次类型映射修复，关系命中率 0/3→可通。

**G4 论文池覆盖 41%（唯一剩余范围缺口）**
包内 10,390 vs 池 24,058，缺 14,189。端到端确认：池外论文点名 0/5 全灭（本地只有语义邻居顶包+web）。企业/专利/教授池覆盖≈100%（0/0/2 缺）——**范围缺口已收敛到论文单域**。修复面=瘦构建补论文批次（阶段2管线修形后）。

**G5 教授画像字段薄弱（语义命中教授 0/2 的候选根因）**
research_directions 仅 37.0% 非空、name_en 7.0%、教授别名 0/3,958、仅 24.8% 教授有任何论文链接。教授属性查询 vector 召回 16 但答案只用 web——画像内容撑不起本地回答。修复面=字段补齐（按查询侧词汇）。

**G6 诚实分层未启用（不挡命中率，是披露债）**
包内 32,941 条全部 admitted、0 limited——质量分层标签未使用。needs_review 教授（池内 ~1,800）目前以 admitted 同权展示，与「诚实分级」目标不符。归阶段1准入矩阵决策。

## 四、对阶段1/2 方案的更新

- **G1 提为阶段1第一切片**：纯代码、最高频、直接兑现「查得到→引本地」。
- 阶段1数据补齐顺序：G3（类型断链，一次修复通关系）→ G2 别名闭包 → G4 论文批次（依赖阶段2瘦管线）→ G5 教授字段。
- 阶段2（决策持久层修形，上轮方案B）不变，是 G4 的前置。
- 传感器复用：本 golden set + 归因脚本作为回归基线，每切片后复测三命中率。

## 五、边界与已知局限

- 样本量 34（seed=42 可复现、可扩样）；池外论文仅测论文域（其余域池覆盖≈100%，无池外可测）。
- 归因到「融合/引用层丢弃」依赖车道计数+引用类型，未逐条核对召回是否含目标（G1 修复切片需带召回明细核验）。
- 单轮查询基线；多轮锚定不在本测量内（G1/G2 修复会影响多轮，复测需补会话用例）。
