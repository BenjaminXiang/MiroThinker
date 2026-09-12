# AQ-S2d 验证文档（close-workbook-gaps，2026-09-12）

> 切片契约：change-log 2026-09-12 末条用户裁定 —— 枚举召回窗
> `_ENUMERATION_CANDIDATE_WINDOW` 64→128（量测不足再试 160/192）+ 披露上限
> `_ENUMERATION_MEMBER_COVERAGE_LIMIT` 32→64，目标：嘉立创/深南电路进融合
> local 半区从而被 S2c 覆盖句披露（g5-t2 预期 8/12；8 家 in-pack GT 天花板
> 已验证：华秋/中信华/领智/广州不在本地数据）。web 轨别人做。行号均指
> s11 worktree（分支 `codex/canonical-v2-s12a-ready`）。本切片只含 AQ-S2d。

## 0. 量测结论（先行探针，选定窗口值的唯一依据）

探针 `.agents/runs/close-workbook-gaps/d0-probe/aq_s2d_window_probe.py`
（离线硬化：同日 web 缓存 + `_bocha/_serper` fail-closed + `_ZeroEmbedding`
+ `create_llm_judge=None` + Milvus 字节拷贝到 `/var/tmp/s2d-probe-index`，
不碰 18188、禁网络），sealed pack run14 + s12g bundle（sha 846d3a…）。
每窗只 patch 常量 + re-plan + execute；输出
`aq-s2d-window-probe.json`。坐标定义（1-based，名字子串匹配）：
`fused_abs` = rerank `ordered` 位次（截窗前）；`handle` =
`evidence_set.entity_handles` 位次（截窗后，None = 被窗切掉）；`disclosure`
= entity_handles 的 canonical company 子序位次（S2c 覆盖句的成员池与 cap
坐标，None = 窗内该名只有 web 句柄或不在窗内）。

### g5-t1「我想找PCB打板， 有哪些推荐」（目标场景，8 家 in-pack GT）

| window | plan/web_max | eligible | handles | 披露池 | items | execute | 句长上限 | GT 在窗 |
|---|---|---|---|---|---|---|---|---|
| 64（现状） | 64/64 | 192 | 64 | 32 | 64 | 5.26s | 472 | 6/8 |
| **128** | 128/128 | 321 | 128 | 64 | 128 | 6.05s | 903 | **8/8** |
| 160 | 160/160 | 385 | 160 | 94 | 160 | 6.46s | 1308 | 8/8 |
| 192 | 192/192 | 444 | 192 | 126 | 194 | 6.08s | 1748 | 8/8 |

窗 64 下两家缺口的确切形态：**深南电路 fused_abs=73 被窗切掉**
（handle=None）；**嘉立创 handle=22 是 web 句柄**（disclosure=None），其
canonical 句柄在窗 64 之外 —— 即"进融合 local 半区"是正确判据，而非
"名字出现在窗内"。窗 128 下 GT 披露位次：精诚达 2、顺易捷 3、上达 14、
兴森 18、一博 20、则成 25、深南电路 37、**嘉立创 56** —— 全部 ≤ 新 cap
64（嘉立创余量 8 席；披露池恰 64，无尾注）。

### g2-t1「中国有哪些成熟的酒店送餐机器人供应商」（漂移对照）

| window | eligible | handles | 披露池 | execute | 句长上限 | GT 在窗 |
|---|---|---|---|---|---|---|
| 64 | 192 | 64 | 32 | 4.86s | 456 | 7/8 |
| 128 | 326 | 128 | 64 | 4.50s | 894 | 7/8 |
| 160 | 390 | 160 | 90 | 5.42s | 1246 | 7/8 |
| 192 | 454 | 192 | 122 | 5.52s | 1682 | 7/8 |

安赛步 `fused_abs=None`（四窗皆然）——不在 pack，非窗口问题；其余 7 家
在窗 64 已全在窗，窗值变化不改变其位次（融合序稳定），无漂移。

### 裁定执行：128 是最小充分窗口

128 达成 g5-t1 8/8 且 8 家披露位次全入 cap 64；160/192 无 GT 增益，
只放大披露池（94/126）与最坏句长（1308/1748 字符）。按裁定"量测不足再
试 160/192"的阶梯，**采用 128 + cap 64**，未触发 192 仍不足的停手上报。

成本：execute 5.26→6.05s（+0.8s，g5；g2 4.86→4.50s 属噪声）；句长上限
（全未提及模拟，128 窗 64 池全列）472→903 字符 —— live prose 通常先提
5-8 家，实际更短；web 窗随既有耦合跟随到 128（见 §4）。

## 1. 改动清单

| 文件 | 动作 | 内容 |
|---|---|---|
| `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py` | 修改 | ① `_ENUMERATION_CANDIDATE_WINDOW` 64→128（`:2784`），块注释改写：记录 AQ-S2 48→64 与 AQ-S2d 64→128 两级理由（融合 read 窗 1:1 交错 ⇒ 64 窗只留 ~32 local，深南电路 fused 73 出局；128 窗保住全部 8 家 in-pack PCB GT，引探针坐标）。② claim 窗块注释改写：AQ-S2d 把 local claim 窗与 candidate 窗解耦（原注释要求"恰好=candidate 窗一半"，被本切片打破）；`_ENUMERATION_LOCAL_CLAIM_WINDOW`/`_WEB_CLAIM_WINDOW` 均保持 32 不动。③ claim-limit 调用点两处行内注释同步（"half the 64 candidate window"→解耦表述）。 |
| `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_answer.py` | 修改 | `_ENUMERATION_MEMBER_COVERAGE_LIMIT` 32→64（`:1327`），常量上方注释记录依据（128 窗 local 半区 ~64 家、嘉立创披露位 56）；`_commit_prose_scope` 调用点注释 "cap 32"→"cap 64"。成员源、过滤、措辞、尾注格式全不动。 |
| `apps/miroflow-agent/tests/canonical_v2/test_knowledge_serving_isolated.py` | 修改 | 2 个测试更新（见 §2.2）。 |
| `apps/miroflow-agent/tests/canonical_v2/test_knowledge_answer_multiturn_contract.py` | 修改 | fixture 40→80 家；4 个测试更新 + 1 个新增（见 §2.1/§2.2）。 |

显式不做：claim 窗 32/32 不动；`max_web_results` 跟随 candidate 窗的既有
耦合（`knowledge_serving_isolated.py:763-776`，注释本就写明 "cap must
follow the enumeration candidate window"）保留 —— 1:1 交错下 local 槽位数
= 窗/2，与 web 上限无关（web ≥ 半窗即可，128 自动满足）；read 侧
`candidate_limit = plan.max_candidates`（`knowledge_read.py:8059`）与
policy 天花板（`:6085`）均符号跟随，无需改；reranker、融合序、schema、
存储、prompt、prose 渲染均未动；web 轨归别人。

## 2. 测试（分层）

### 2.1 本切片新增 1 个测试

`test_member_coverage_sentence_ignores_interleaved_web_handles`——融合 read
窗 1:1 交错的 unit 层锁定：entity_handles 交错 6 canonical + 6 web 句柄，
覆盖句必须只列 canonical（6 家全列、保相对召回序），web 句柄既不出现也
不占披露位。该性质是"local 半区披露"语义的直接对应物（窗截断本身由
read 层负责，已由探针实测覆盖）。诚实标注：此锁定在 cap 32 下同样成立，
属语义锁而非 RED 复现。

### 2.2 既有测试更新（行为变化属本切片裁定语义，共 6 个）

1. `test_enumeration_window_constants_and_plan_windows`——窗钉 128；local
   claim 窗从 `window // 2` 耦合断言改为钉绝对值 32（docstring 写明 S2d
   解耦理由）；web claim 窗 32 不动。
2. `test_enumeration_plan_windows_follow_the_64_candidate_window` →
   `..._follow_the_128_candidate_window`：枚举 plan 断言 128/128；非枚举
   分支（bundle 8+8）不动。`:268`/`:412` 两处符号断言自动跟随，未改。
3. `test_member_coverage_sentence_caps_at_32_with_overflow_count` →
   `..._caps_at_64_...`：fixture 80 家，断言粤科64 入句 / 粤科65 不入 /
   `等（共 80 家）`。
4. `test_member_coverage_sentence_sources_the_recalled_set_beyond_the_claim_window`
   ——显式传 `[:40]` 切片固定 40 召回场景（默认值已变 80），期望值同步
   `[8:40]`；原断言语义（ranks 33-40 段被披露、不触发 cap）不变。
5. `test_member_coverage_sentence_names_all_resolve_to_recalled_handles`——
   80 fixture 下：64 listed 全部 resolve 回召回句柄 + overflow `80 家）`。
6. `_S2C_RECALL_IDS/NAMES` fixture 40→80（`粤科NN` 品牌别名互不冲突的
   构造不变），注释同步。

未改而通过的同形用例：rank-order 锁定、全提及不触发、非枚举轮逐字节+
commit 门禁、S2b 五家场景、镜像钉（marker 双拷贝一致）等。

### 2.3 回归数字（本 session 实跑）

- 新测试 1 个绿；更新测试 6 个绿。
- multiturn 文件：**33 passed + 1 failed**；唯一失败
  `test_off_anchor_correction_exhaustion_falls_back_without_refusal` 为存量
  （本切片 HEAD 基线 stash 对照同名失败；S2c 记录 32+1 同源）。
- serving 文件：**293 passed**（含窗常量钉与镜像钉；基线 293 一致）。
- 四文件门（read_isolated / serving_isolated / turn_trace_reporting /
  serving_pack_loader）+ placeholder_scrub：**352 passed**（S2c 后基线
  352，逐数对照 ✓）。
- 波及面六文件（implementation_closure / answer_anchor_lead /
  grounding_contract / coverage_presentation / enumeration_deep_fetch /
  ambiguity_gate_serving）：**70 passed + 3 failed**；3 个失败全部位于
  implementation_closure（prose-renderer audit 类，同 S2b/S5/S2c 基线同名
  同数），存量，非本切片引入。
- canonical_v2 其余全部 import 触及面（16 文件：ambiguity_switch_execution /
  canonical_scope_founder_red / consumer_acceptance_contract /
  index_projection_embedded_content / internal_reference_projection_contract /
  knowledge_answer_assessment_contract / knowledge_answer_atomic_green_contract /
  knowledge_answer_interface / knowledge_gap_online_write_boundary /
  knowledge_read_answer_successor_handoff / knowledge_read_atomic_green_contract /
  llm_query_rewrite / multi_subject_no_correction /
  serving_supplemental_person_criteria / web_lane_resilience / web_page_fetch）：
  **218 passed + 3 skipped + 4 failed**；4 个失败（founder_red×1、
  llm_query_rewrite×2、web_page_fetch×1）在 HEAD stash 对照下逐断言一致
  （含 web_page_fetch 的 `6 == 5` 同列表同数字），存量，非本切片引入。
  （全目录 1468 例聚合跑 3600s 超时未完成，由上述逐文件覆盖取代 —— 两常量
  的全部 import 触及面已无遗漏。）
- lint/format：`ruff check` 6 errors（E402×4 + F821 + F841）与
  `ruff format --check` 4 文件漂移在 HEAD 版本上逐行一致
  （`/tmp/s2d-ruff-before.txt` vs `/tmp/s2d-ruff-after.txt` 排序后 diff 为空），
  存量，非本切片引入。

## 3. 保真边界

- 非枚举轮 plan 窗（bundle 8+8）与非枚举 claim 窗（min(bundle,3) /
  bundle.max_web_results）逐字节不动（serving 测试②钉住）。
- claim 窗 32/32 不动 ⇒ prose prompt 预算不扩；扩的只是召回/披露，披露走
  覆盖句（count-only 项仍无能力声明）。
- 覆盖句成员源、过滤（canonical company + 未提及）、措辞、
  `等（共 N 家）` 尾注格式与 S2c 逐字节一致；只有 cap 数字变。
- 顺序 == 召回 rank 序（entity_handles 序）；web 句柄不进句不占位
  （新测试钉住）。
- 披露上限 64 以探针坐标锚定：g5-t1 披露池恰 64，嘉立创位 56（余量 8）。

## 4. 遗留风险与观察项

- **收窄轮覆盖句放大**（S2c 已记）：128 窗下收窄轮若仍命中枚举 marker，
  覆盖句最坏 903 字符（64 家全列 + 无尾注，因池=64 不超 cap）；会话宇宙
  继承全池的效应同步放大。归主上下文 live 观察项（g2-t3/g5-t3 stance
  采样）。
- **web 窗跟随到 128**：既有耦合（plan `max_web_results` = candidate 窗）
  使 web lane read 上限 64→128 —— live 下 web 结果页拉取/快照成本翻倍
  量级；execute 实测仅 +0.8s（离线缓存），live 网络成本需主上下文观察。
  若 web 侧成本敏感，可后续把 web 窗钉回 64 而不影响 local 半区
  （1:1 交错只需 web ≥ 半窗）—— 本切片不预判。
- `等（共 N 家）` 形态上限：披露池 > cap 时才出现；128 窗 g5-t1 池=64 恰好
  不触发，更大主题（g2 类 122 池 in 192 窗形态）若窗再扩会触发尾注。
- commit 扫描池扩到 128 句柄：O(128 × 词形数) 子串扫描，成本可忽略；
  result_set hash 输入变长属预期（确定性不变）。
- 未做（切片外，需 live 环境，本切片禁网络、不碰 18188）：live g5-t2 实测
  8/12、generalization probe 重跑（P2 precision 不得退化）、replay 门与
  18188 部署 —— 主上下文窗口。
- 回滚 = 还原本提交四个文件；无 schema/存储/契约改动。

## 5. 产物

- 探针：`.agents/runs/close-workbook-gaps/d0-probe/aq_s2d_window_probe.py`
  + `aq-s2d-window-probe.json`（窗 × GT 覆盖全量坐标表）。
- 代码+测试：本切片提交（s11 worktree 分支 `codex/canonical-v2-s12a-ready`）。
- 本文档：`.agents/runs/close-workbook-gaps/aq-s2d-verify.md`。
- canonical_v2 全目录回归：聚合跑 3600s 超时未完成；以逐文件覆盖取代
  （四门+scrub 352、multiturn 33+1、波及面六文件 70+3、其余 16 import
  触及面文件 218+3s+4 存量失败），两常量 import 触及面无遗漏。
- 句长样例（g5-t1，128 窗，全未提及模拟上限）：903 字符 / 64 家全列；
  cap 测试样例（80 召回 / 0 提及 / cap 64，单测实跑）：
  「此外，本次检索还召回以下相关本地企业：深圳市粤科01机器人有限公司、…、
  深圳市粤科64机器人有限公司 等（共 80 家）。」
