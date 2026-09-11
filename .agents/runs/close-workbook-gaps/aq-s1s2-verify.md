# AQ-S1 + AQ-S2 验证文档（close-workbook-gaps，2026-09-11）

> 切片契约：`.agents/runs/close-workbook-gaps/answer-quality-design.md` §1
> （C-1 与 A-1 两段）+ `openspec/changes/close-workbook-gaps/design.md`
> §"Answer-quality slice"（裁定汇总）。行号均指 s11 worktree。本切片只含
> AQ-S1（C-1 注册地证据，门控）与 AQ-S2（A-1 枚举窗口放宽）；S3/S4/S5 不在
> 范围内。C1 的声明文件与 matcher 未动（仅复用 `scrub_placeholder_value`）。

## 1. 改动清单

| 文件 | 动作 | 内容 |
|---|---|---|
| `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py` | 修改 | ① `_semantic_text` 加 keyword-only `include_registered_address=False`；公司分支在开关开时追加 `注册地：…`（值取 `registered_address`，缺省回退 `geography.name`，均过 C1 `scrub_placeholder_value` 过滤占位值，长度过 `_LOCAL_CLAIM_FIELD_LIMIT`）。② 新增 `_registered_address_claim_value`。③ `_answer_selector.select` 计算 `geography_turn` 开关 = `_question_frame(query).predicate ∈ _RELATION_FRAME_PREDICATES`（headquarters_city/registered_address/office_city/branch_city/product_capability）**或** `evidence_set.protected_slots` 含 `kind=="geography"` 槽；调用点传参。④ `_ENUMERATION_CANDIDATE_WINDOW` 48→64；新增 `_ENUMERATION_LOCAL_CLAIM_WINDOW=32`、`_ENUMERATION_WEB_CLAIM_WINDOW=32`；selector 的 `local_claim_limit`/`web_claim_limit` 枚举分支改读新常量（web 窗与 cut 常量解耦）。 |
| `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read_isolated.py` | 修改（注释） | `_category_recall_entries` 注释 "48 on the enumeration branch" → 64。无行为改动。 |
| `apps/miroflow-agent/tests/canonical_v2/test_knowledge_serving_isolated.py` | 修改 | +5 测试（见 §2）；既有 `test_enumeration_selector_web_claim_limit_follows_widened_window` docstring 更新为新口径（断言不变仍过）。 |
| `.agents/runs/close-workbook-gaps/d0-probe/aq_s2_window_probe.py` | 新增 | 离线探针：sealed run14 包只读，F1 窗 48 vs 64 的 GT 进窗表 + 注册地证据可用率 + claim payload 字符成本。输出 `aq-s2-window-probe.json`。 |

未碰：plan 窗口（`:736-752`）与 read 侧 web 上限（`:762-775`）的**引用形式**（仍引用 `_ENUMERATION_CANDIDATE_WINDOW`，值随常量到 64——设计裁定的耦合点）；`planning_policy.max_candidates`（`:6030-6033`，同一常量，天花板随动）；reranker、提示词、coverage 句（裁定 2 维持只报数）。

## 2. 测试（分层）

### 2.1 本切片新增 5 个测试（全部 RED→GREEN）

RED 证据（改动前实跑）：TypeError（flag 不存在）/ `assert 16 == 32`（旧 local 窗 16）/ `assert 48 == 64`（旧 plan 窗）/ AttributeError（新常量不存在）/ 地址行缺席（`assert False` on any(注册地)）。

1. `test_semantic_text_company_registered_address_requires_geography_flag`（构造场景）——
   单测级四态：深圳地址开→`注册地：深圳市南山区示例路1号`；`geography.name` 回退；双 null →
   无地址行；占位值（`未找到`/`暂无`）→ 不渲染（C1 matcher 复用）。**关闭态逐字节锁定**：
   断言 flag off 输出 == 字面量 `深圳示例机器人有限公司；简介：聚焦酒店送餐机器人。；技术路线：自主导航。。`
   （该断言在 RED 阶段即通过 = 锁定今日形状）。
2. `test_selector_renders_registered_address_only_on_geography_turns`（构造场景）——
   selector 级三态 fixture（深圳/上海/null）：关系帧触发（`上述企业里总部在深圳的有哪些`，
   slots 空，隔离帧路径）、geography 槽触发（`深圳有哪些做PCB的公司` + geography 槽，
   隔离槽路径）、枚举非地域关闭（无 `注册地` 且逐字节锁定）、仅城市词无帧无槽关闭
   （`深圳示例机器人有限公司的主营业务`，named-entity span 抑制路径）。
3. `test_enumeration_selector_local_and_web_claim_windows_widen_to_32`（构造场景）——
   40 local + 40 web 枚举 fixture：枚举轮 local claims == 32（`evidence:local:32` 进、
   `:33` 不进）、web claims == 32（同形断言）、`displayed_handle_ids` 含 local #17–#32；
   非枚举同 fixture 仍 local==3 / web==8（前后均绿，回归锁）。
4. `test_enumeration_window_constants_and_plan_windows`——不变式：
   `_ENUMERATION_CANDIDATE_WINDOW == 64`、`local == cut//2`（1:1 交错）、web == 32（解耦）。
5. `test_enumeration_plan_windows_follow_the_64_candidate_window`（tmp_path bundle）——
   枚举 plan `max_candidates == 64` 且 `max_web_results == 64`（read/F1 截断随动）；
   非枚举 plan 保持 `bundle.max_candidates + bundle.max_web_results` / `bundle.max_web_results`。

### 2.2 既有回归

- 四文件套件 + placeholder_scrub：**345 passed**（基线 340 = C1 后状态；+5 本切片新增，逐数对照 ✓）。
- 既有 `test_enumeration_selector_web_claim_limit_follows_widened_window`（20 web items、
  九号 @18）在新 web 窗 32 下仍过；`test_content_addressed_serving_bundle_is_secret_free_and_executable`
  的 policy 天花板断言（`max(bundle…, _ENUMERATION_CANDIDATE_WINDOW)`）两侧同动仍过。
- 波及面扫：所有引用 `_answer_selector`/`_semantic_text`/claim 窗口的测试文件
  （`test_knowledge_answer_implementation_closure` / `test_enumeration_deep_fetch` /
  `test_coverage_presentation` / `test_knowledge_answer_multiturn_contract` /
  `test_answer_anchor_lead`）78 测试中 4 个失败——经 `git stash` 对照在 `ad401302`
  基线上同样失败（逐数一致），是**存量失败**（prose-renderer audit/multiturn 契约类，
  与本切片无关），非本切片引入。全目录扫在 20 分钟超时内未完成（重目录，非本切片门）。

### 2.3 离线包探针（sealed run14，只读）

`aq_s2_window_probe.py` 实跑输出（证据 `aq-s2-window-probe.json`）：

**F1 窗 48 → 64 的 GT 进窗表**（`_category_recall_entries`，生产链路）：

| 查询 | GT | rank@48 | rank@64 |
|---|---|---|---|
| g5-t1 我想找PCB打板， 有哪些推荐 | 嘉立创 | 窗外 | **54 ✓进** |
| | 则成 | 窗外 | **62 ✓进** |
| | 深南电路 | 41 | 41 |
| | 顺易捷 | 9 | 9 |
| | 一博/兴森/上达/精诚达 | 窗外 | 仍窗外（A-2 排队） |
| pcb-list 深圳有哪些做PCB的公司 | 嘉立创 | 窗外 | **53 ✓进** |
| | 则成 | 窗外 | **61 ✓进** |
| g2-t1 酒店送餐机器人 | 普渡2/开普勒3/云迹1/九号8/擎朗4/艾唯尔12/锐曼26 | 同左 | 同左（头部序不变，宽窗只加尾部） |

免费收益坐实：嘉立创/则成恰好按设计预测的 pool 位次（54/62）进窗；g2-t1 的锐曼
rank 26 也随 local claim 窗 16→32 进入展示集（g2-t2 路径）。recalled 数 48→64。

**AQ-S1 证据可用率**（公司条目 7,089）：`registered_address` 过 C1 scrub 可用
6,506（91.78%，吻合设计引用的 91.8%）；仅 `geography.name` 回退 8 条；任一注册地
证据覆盖 91.89%。

**payload 字符成本**（每枚举轮）：本地 claim 实渲染长度 mean 171–198 / median
166–194 / max 345 字符；Δ ≈ local +16×~185 ≈ **+3.0K 字符** vs web −16×≤267 ≈
**−4.3K 字符**（web claim 上限 240+来源尾缀）→ 净变化约 −1.3K，接近持平偏降。
AQ-S1 的 `注册地` 行只在地域/收窄轮加 ~10–40 字符/claim。TTFT 由主上下文 live 实测。

## 3. 保真边界与遗留风险

- 非枚举轮完全不动：local 3 / web=bundle.max_web_results / plan=bundle 窗口（回归锁断言）。
- AQ-S1 开关关态逐字节锁定（单测字面量 + selector 级断言）；开关开态只在
  `_RELATION_FRAME_PREDICATES`（含 product_capability——设计判据原文照录）或
  geography 槽轮次生效。
- 措辞"注册地"，不写"总部"（裁定 3）；`geography.name` 可能是省级（如"广东省"），
  如实渲染，模型侧措辞归 C-2（本切片不动提示词）。
- web 抓取上限随 plan `max_web_results` 到 64（设计裁定的耦合点）；web claim 仍 32，
  提示词不放大。web 尾部 33–48 的 web-only 供应商不再进 claim（differential 观察项，
  归主上下文 live 窗口）。
- 风险：枚举轮 p95 延迟（本地 claim +16 条）；回滚 = 常量回 48/16/48（三处常量）。
- 未做（切片外）：AQ-S3/S4/S5、提示词 C-2、coverage 点名、18188 部署与 replay 门
  （主上下文窗口）。

## 4. 产物

- 代码+测试：本切片提交（s11 worktree 分支 `codex/canonical-v2-s12a-ready`）。
- 探针：`.agents/runs/close-workbook-gaps/d0-probe/aq_s2_window_probe.py` +
  `aq-s2-window-probe.json`。
- 本文档：`.agents/runs/close-workbook-gaps/aq-s1s2-verify.md`。
