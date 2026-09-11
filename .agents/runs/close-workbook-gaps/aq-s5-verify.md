# AQ-S5 + S2b-r 验证文档（close-workbook-gaps，2026-09-11）

> 切片契约：主上下文任务书（AQ-S5 = design.md §AQ-S2b 之后接续的 A-2 落点；
> S2b-r = change-log 2026-09-11 AQ-S2b 采样记录的 refinement (a)——短品牌名
> 提及判定修正）。行号均指 s11 worktree。本切片含 AQ-S5（A-2 词表转述扩展，
> F1 召回排名）与 S2b-r（提及词形修正）；AQ-S3/S4 与 live 采样/部署不在范围内。

## 1. 改动清单

| 文件 | 动作 | 内容 |
|---|---|---|
| `src/data_agents/canonical_v2/anchoring_declaration.py` | 修改 | `AnchoringDeclarationTerm` 加 `expands: NonEmptyStr \| None = None`（声明该词是某触发词的转述成员）。`extra="forbid"` 不变，未知字段仍 fail-closed。 |
| `.agents/runs/close-workbook-gaps/c1_seed_anchoring_declaration.py` | 修改 | 新增 `_PARAPHRASE_FAMILIES = {"PCB": (16 词)}` + `_paraphrase_multiplier`（≥4 字→2，否则 1）；seed 追加成员条目（tier=T/anchor=None/multiplier=权重/confidence=text_only/expands="PCB"）；head 未声明或成员撞词→ raise（fail-closed）。种子脚本可复算产物 JSON。 |
| `src/data_agents/canonical_v2/catalogs/anchoring-declaration-v1.json` | 重新生成 | +16 转述成员条目（`expands: "PCB"`）；sources 追加 AQ-S5 出处行；其余逐字节不变（diff 已核）。 |
| `src/data_agents/canonical_v2/knowledge_read_isolated.py` | 修改 | 新增 `_CATEGORY_TERM_EXPANSIONS`（模块级，从声明派生：head/member 均 casefold）+ `_expand_category_query_terms`（触发词在抽取词中才展开；`setdefault` 语义——查询已含的词绝不降权；单跳，成员不再触发）；`_category_recall_entries` 在抽取后调用一次（`:8525`）。这是声明 `terms[]` 的首个消费者。 |
| `src/data_agents/canonical_v2/knowledge_answer.py` | 修改 | S2b-r：`_prose_mention_name_forms` 增两形——去城市前缀的法律词干（`^[一-鿿]{2,4}市`，≥4 字，镜像 serving `_web_identity_full_name_forms` 规则）+ `_compact_company_alias` 品牌别名（≥2 字，复用 followup_referents 既有助手，非新启发式）；2 字下限与去重保持。两个调用点（覆盖句 `:1352`、F2 commit 提及扫描 `:2637`）同时生效。 |
| `tests/canonical_v2/test_knowledge_read_isolated.py` | 修改 | +6 测试（§2.1）。 |
| `tests/canonical_v2/test_knowledge_answer_multiturn_contract.py` | 修改 | +4 测试（§2.2）；既有 union 测试断言更新到 S2b-r 语义（§2.2 末）。 |
| `d0-probe/aq_s5_explore.py` + `aq-s5-explore.json` | 新增 | 摸底探针：8 家 GT 画像词表命中 + 无截断基线排名 + 变体模拟（V1/V2/V3）。 |
| `d0-probe/aq_s5_paraphrase_probe.py` + `aq-s5-paraphrase-probe.json` | 新增 | 终版量测：before=已验证镜像（无扩展）、after=生产 `_category_recall_entries`（窗 32/64）+ 镜像全榜（镜像 top-64 与生产窗 64 逐 id 断言一致）。 |

显式不做：不动 serving 层选择/提示词；不动窗口常量（32/64 归主上下文裁定）；
不给非 PCB 族加转述（词表量测驱动，后续族另行裁定）；18188 未碰、全程禁网。

## 2. 量测表（sealed run14 包，只读）

### 2.1 变体对比（g5-t1 无截断排名，选定 V1）

| 变体 | 规则 | 嘉立创 | 深南 | 一博 | 顺易捷 | 兴森 | 则成 | 上达 | 精诚达 | 总召回 |
|---|---|---|---|---|---|---|---|---|---|---|
| 基线 | — | 54 | 41 | 98 | 9 | 70 | 62 | 窗外 | 窗外 | 150 |
| **V1（选定）** | ≥4字→2 否则 1 | 56 | 37 | 20 | 3 | 18 | 25 | 14 | 2 | 211 |
| V2 | 抽取同权(词2/长句1) | 31 | 55 | 21 | 1 | 26 | 16 | 13 | 4 | 268 |
| V3 | V1+拉丁词2 | 45 | 44 | 23 | 4 | 22 | 14 | 10 | 2 | 232 |

V1 选定理由：honor 裁定"展开词降权"（成员权重 ≤ 触发词抽取权重 2）；膨胀最小
（+61 vs V2 +118）；6 家 GT 以稳健边距进 top-32（V2 的嘉立创 31 是刀锋位，
且把深南打出窗）。词表（16 词）：印制电路板/印制线路板/柔性线路板/柔性电路板/
封装基板/刚挠结合/PCBA（权重2）+ 电路板/线路板/柔性板/FPC/SMT/打样/打板/制板/贴片
（权重1）——全部由 GT 画像实测词表驱动（aq-s5-explore.json），未加元器件/基板等
过宽词。

### 2.2 终版生产链路结果（aq-s5-paraphrase-probe.json）

g5-t1「我想找PCB打板， 有哪些推荐」与 pcb-list「深圳有哪些做PCB的公司」：

| GT | before | after（score） | 窗32 | 窗64 |
|---|---|---|---|---|
| 顺易捷 | 9 | 3（19） | ✓ | ✓ |
| 深南电路 | 41 | 37（7） | ✗ | ✓ |
| 嘉立创 | 54 | 56（5） | ✗ | ✓ |
| 则成 | 62 | 25（8） | ✓ | ✓ |
| 兴森 | 70 | 18（9） | ✓ | ✓ |
| 一博 | 98 | 20（9） | ✓ | ✓ |
| 上达 | 窗外 | 14（10） | ✓ | ✓ |
| 精诚达 | 窗外 | 2（20） | ✓ | ✓ |

- local 展示窗 32：1/8 → **6/8**；read 截断窗 64：4/8 → **8/8**。
- 生产链路镜像一致性：三查询的镜像 top-64 与生产窗 64 输出逐 id 相等（探针内断言）。
- **g2-t1（非 PCB 查询）零漂移**：基线与扩展后 8 家 GT 排名/score 逐数相同
  （普渡2/云迹1/开普勒3/擎朗4/九号8/艾唯尔12/锐曼26/安赛步436），扩展不触发。
- top-40 目检：新进头部为真实 PCB/FPC 厂（崇达技术/百芯智造/嘉之宏/鸿洋电路/
  星河电路/柳鑫实业等）；未见明显 out-of-domain 误入者（赛尔博特软件/科易博软件
  等泛电子范围文案命中者在基线 score-2  tie 中本就在列，扩展只重排不新增语义）。

## 3. 测试（分层）

### 3.1 S5 新增 6 个（read_isolated 文件）

RED 证据（实现前实跑）：2× AttributeError（`_expand_category_query_terms` 不存在）、
排名断言 `['company-c-s5-pcb'] != [flex, pcb, weak]`（转述-only 条目今日召不回）、
声明测试 `.expands` AttributeError。2 个负向/护栏测试（无触发不展开、未知字段
fail-closed）RED 阶段天然通过，作回归锁。

1. `test_category_term_expansions_fire_only_on_pcb_trigger`——PCB 查询展开 16 词
   （抽查权重）；酒店/机器人查询逐字节不变；空词组原样返回。
2. `test_category_term_expansions_keep_query_term_weights`——查询自带"电路板"(w2)
   不被成员权重 1 降权。
3. `test_category_recall_promotes_paraphrase_only_entries`——构造：纯转述 FPC 条目
   （零 pcb 字样）经 tag/product 层召回并排在 pcb 摘要条目之前。
4. `test_category_recall_never_fires_without_trigger`（护栏）——同 fixture 换机器人
   查询，全家不触发、结果为空。
5. `test_anchoring_declaration_carries_pcb_paraphrase_family`——声明族成员集合/权重
   规则/字段形状钉死；head 自身已声明；消费者 map 与声明逐词一致。
6. `test_anchoring_declaration_entry_unknown_field_fails_closed`（护栏）——条目带
   未知字段仍 ValidationError（expands 加白后 fail-closed 不松）。
   反例矩阵核心在 3/4：单次"线路板"杂提（覆盖度地板）与"机器视觉 vs 机器人"同形的
   弱信号压制（既有 `test_category_recall_min_score_excludes_single_bigram` 保持绿）。

### 3.2 S2b-r 新增 4 个（multiturn 文件）

RED 证据：词形断言今日只有 (全名, 法律词干)；commit 并集 `('company:f2-scc',) != (scc, jlc)`；两个 endswith 失败。

1. `test_prose_mention_name_forms_include_city_stripped_stem_and_brand_alias`——
   深圳市普渡科技有限公司 → (全名, 深圳市普渡科技, 普渡科技, 普渡)；
   深南电路股份有限公司 → (全名, 深南电路)（无城市前缀/无更短品牌，不出新形）；
   甲公司 → (甲公司,)（2 字下限保持）。
2. `test_prose_commit_union_picks_up_short_brand_mentions`——prose 裸写"嘉立创"，
   jlc 经别名进 F2 commit 并集（(scc, jlc)，选择器优先+展示序）。
3. `test_member_coverage_sentence_counts_short_brand_mentions`——prose 裸写
   贝塔（别名）/伽马精工（去城市词干）→ 覆盖句只列德尔塔。
4. `test_member_coverage_sentence_brand_alias_does_not_cross_match`——反例：
   prose 提"普天"，展示集中普渡不被误吞（覆盖句仍列普渡）。

既有测试更新 1 个：`test_prose_commit_unions_displayed_entities_named_in_answer`
——嘉立创裸名现计为提及，覆盖句回到"顺易捷、一博"两名（S2b-r 裁定语义），
docstring/注释已改写。

### 3.3 回归数字（本 session 实跑）

- 新测试 10 个全绿（S5×6 + S2b-r×4）。
- multiturn 文件：**29 passed + 1 存量失败**（off_anchor，基线同）。
- serving 文件：**293 passed**（S2b-r 别名并入未翻转任何 serving 断言）。
- 四文件+scrub 门：**352 passed**（346 基线 + S5×6；multiturn 不在门内）。
- 波及面六文件：**70 passed + 3 failed**——implementation_closure 同 3 个存量
  失败（今早 90159d0a 基线 stash 对照同名同数，本轮名/数均未变）。
- ruff：knowledge_answer.py E402 3→4（存量同类同位点：`_logger` 前置导致该
  import 块全部 E402；新增行为对齐本地既存写法，门禁基线含此类）。
- 全目录扫未跑（重目录 20 分钟超时，非本切片门；AQ-S1/S2 同）。

## 4. 保真边界与遗留风险

- 触发门禁：扩展仅在查询抽取词含族头（pcb）时生效；g2 车道逐字节零漂移（实测）。
- 展开词降权：成员权重 1-2 ≤ 触发词抽取权重 2；查询已含词不降权（setdefault）。
- fail-closed 全保持：schema 版本/未知字段/重复键；head 未声明或成员撞词 raise。
- **残余缺口（归主上下文，窗口/锚点级决策）**：嘉立创（56）/深南电路（37）仍在
  local 展示窗 32 之外——根因是两者 curated 字段为空（industry=电子制造、tags 空），
  词表转述对"只有长摘要的薄画像"结构性触顶；词表路径已穷尽（再加词=过宽误召）。
  两家已在 read 窗 64 内（8/8），最后一英里选项：(a) local 窗 32→64（payload
  +~6K 字符，TTFT 成本，change-log 已列）；(b) C1 批次补 tags/tech_tags 画像字段。
  按任务书停止条件：量测达标"多数 GT 进 top-32"（6/8），不硬调。
- S2b-r 误匹配面：2 字别名裸子串匹配，理论上正文中偶然含别名（如"九号"日期
  语境）会把该展示成员计为已提及（覆盖句少列一家/并集多留一家）——误伤上界=
  展示集内成员，无集外拉入；同名近似公司由测试 4 钉住不互吞。
- 收窄轮覆盖句形态沿用 S2b 裁定（pre-filter 池），未在本切片改动。
- 回滚：声明 JSON 回退 16 词 + 摘 `_expand_category_query_terms` 调用点 +
  `_prose_mention_name_forms` 两个新形；测试块整段可删。无 schema/存储迁移。

## 5. 产物

- 代码+声明+测试：本切片提交（s11 worktree 分支 `codex/canonical-v2-s12a-ready`）。
- 探针：`d0-probe/aq_s5_explore.py`(+json)、`d0-probe/aq_s5_paraphrase_probe.py`(+json)。
- 本文档：`.agents/runs/close-workbook-gaps/aq-s5-verify.md`。
