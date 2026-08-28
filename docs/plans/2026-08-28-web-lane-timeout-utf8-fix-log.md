# 修复日志：Web 通道三缺陷（早稻田必现失败）— R1

计划文档：[2026-08-28-web-lane-timeout-utf8-fix.md](2026-08-28-web-lane-timeout-utf8-fix.md)

## R1（2026-08-28）：三链修复 + 实时复验

### 做了什么

1. 定责实验：生产 key 实测 Bocha 双域名 16 次请求（280–403ms 全成功、UTF-8 全有效）
   → 排除供应商，日志 `/tmp/bocha-latency-log.json`；Serper 实测 1.7–2.8s。
2. OpenSpec change `fix-web-lane-timeout-and-utf8-truncation`（proposal/tasks）+
   验证契约先行（TDD 边界）。
3. 代码修复（worktree）：
   - `knowledge_serving_isolated.py`：新增 `_utf8_truncated()`，替换 4 处
     `.encode()[:cap]` 字节切片；`_DualWebLaneAdapter` per-provider 超时
     （bocha ≥2.0s / serper ≥4.0s）+ `_outer_wait_seconds()` 分通道外层等待。
   - `canonical_v2_admin.py`：`_budget_receipt_overrun_kind()` 分级（wall_time
     保留 / resource 剥除），`_validated_evidence_set` 改用分级判定。
4. 新单测 14 项（agent 9 + admin 5）；更新 1 处锁旧超时值（0.675→4.0）的既有断言。

### 发现

- 三条失败链全部坐实并修复（见计划文档根因节）。
- 既有失败 3 处（prose renderer 断言 ×1、query rewriter ×2）与 admin 适配器
  37 处，经 git stash 往返证实为 HEAD 既有，与本次无关（此前 hotfix 的遗留漂移）。
- **实时复验（18188 重启后）**：早稻田 2/3 PASS（12.7s/12.4s，首次答出
  「帕西尼创始人许晋诚」）；demo 4/4 PASS；internal_error 0/3；
  「wall-time 超支保留」日志行实测出现（elapsed 12204ms 保留）。
- 残差：冷缓存首轮仍降级话术（trace `f-xa59Ap`：lane 层 71 条 web 全
  cache_hit、无剥除告警，但 SSE 报 0）→ drop 在 read 层合并/充分性路径，
  非本 slice 三链，留待下一切片。

### 怎么验证的

- 新单测：`uv run pytest tests/canonical_v2/test_web_snapshot_utf8_truncation.py
  tests/canonical_v2/test_dual_web_lane_provider_timeouts.py`（agent，9/9）；
  `uv run pytest tests/test_canonical_v2_budget_degradation_grading.py`（admin，5/5）。
- 回归：`test_knowledge_serving_isolated.py` 236 pass / 1 既有失败；
  supplemental+ambiguity+resilience 71 pass；`test_llm_query_rewrite.py` 31 pass
  / 2 既有失败；admin chat adapter 96 pass（含新增 5）/ 37 既有失败。
- 实时：`/tmp/live-replay-after-fix.json`（7 问复验记录）+ turn trace journal
  （`var/turn-trace/2026-08-28.jsonl` 三轮 web_outcomes）。

### 影响哪些问题

- 早稻田查询从此栈 0% → 67% 成功率；internal_error 崩溃链（影响一切触发
  全文页面抓取的查询）根除；Serper 通道从结构性失效恢复为可用（双源交叉验证回归）；
  预算超支不再丢弃已到手的 web 证据（所有走 supplemental 探针的查询受益）。

## R1 补充（2026-08-28 下午）：E2E 验证与残差定性

### E2E 结果

- **测试集 16 题**：16/16 有答案、0 自白；单轮 11/12（唯一失手=早稻田残差）；
  「酒店送餐机器人」从 EMPTY 变 2/2 通过（修复对枚举类同样生效）。
- **官方重放门 7 会话**：17/19。G3 多轮代词（P4 族既有）；G7 枚举首轮 2/3、
  复跑 3/3 败（缺优必选）。

### 残差定性（重要，决定下一切片方向）

G7 全天 7 轮 trace 均 `web in=72 retained=72`、零错误零超时，但失败轮答案里
web 条目为 0（纯本地 594 字清单 vs 通过轮 1023 字 web 融合清单）——与早稻田
残差同族：**web lane 结果在 read 层装配阶段被整批丢弃**。pre-fix 的 09:43
早稻田 trace 已是 in=71 + outage 答案 → 该丢弃先于本次修复存在，此前被
崩溃/全剥掩盖，修复三链后上升为主要剩余失败模式。

**门禁含义**：重放门当前非绿（G7）→ 此状态不得热更新 release/customer-test；
read 层丢弃是下一切片的阻断项。

### 提交

- `fix(web-lane)`: 三链修复 + 14 测试 + OpenSpec + 文档（worktree 分支
  data/p4-serving-pack-rebuild）
- `ux(demo)`: 样例问题换为实测快速题 + 测试/服务脚本

## R2（2026-08-28 下午）：read 层 web 外层等待修复 —— E2E 迭代闭环

### 做了什么

R1 E2E 发现的首要缺口（read 层 web 证据整批丢弃）根因闭合并修复
（OpenSpec `fix-web-lane-read-outer-wait`）：

- **根因**：read 编排层把 provider 搜索预算（`web_policy.timeout_ms=1500ms`）
  复用成整条 web lane future 的外层等待；lane 真实工作（4 视图搜索×双
  provider + 枚举 refinement + fetch_depth=8 抓页 + LLM gap judge）设计上
  要跑 2–40 秒 → 超过 1.5s 即判 `unavailable`+0 候选，72 条结果整批丢弃
  （lane 线程继续跑完，所以 serving 层 trace 显示 in=72）。
- **修复**：`knowledge_read.py` 新增 `_web_lane_outer_wait_seconds()`
  （地板值 20s，policy 更大时用 policy；disabled 返回 None），execute 的
  web future 等待改用它。

### 发现

- G7（具身智能枚举）失败轮与通过轮的唯一差异 = web lane 是否在 1.5s 内
  凑巧跑完（缓存全热）——这就是"忽好忽坏"的全部来源。
- 早稻田 outage 话术的直接触发链：web trace `unavailable` →
  `_web_lane_unavailable_from_traces` → 改写。证据薄时 LLM 写"未找到"
  才触发；证据足时（supplemental 3 条）即使 lane 被杀也能答对——与 R1
  观察完全吻合。

### 怎么验证的

- 新测试 2/2（地板值数学 + 2s 慢 lane 在 1.5s policy 下落盘成功）。
- 回归 258 pass（1 处 HEAD 既有失败不变）。
- **实时 6/6**：G7 ×3 全过（web lane succeeded/48、优必选在场、37–40s）、
  早稻田 ×3 全过（12.5–13.1s、关键点命中、零 outage）。
- **全量重放门 18/19**：G7 转绿；仅剩 G3（见下）。
- **全量测试集 16 题：单轮 12/12 全过**（早稻田 1/1，含此前一直失败的
  题目在内全部命中）、16/16 有答案、0 自白；4 个失败全为脚本无会话上下文
  的多轮追问题（已知脚本限制）。

### 影响哪些问题

- G7 枚举重放从 4/6 波动转 6/6 稳定；早稻田从 67% 转 100%（本机采样）；
  web 融合回答（PCB/无界智航等）不再依赖缓存运气；重放门从非绿转 18/19，
  **热更新阻断解除**（除 G3 外）。
- TTFT 影响：web lane 干真活的轮次要等它跑完（典型 +2~10s，枚举更长），
  符合"质量优先+进度事件"裁定；纯本地轮（CN 专利 7s）不受影响。

### 遗留（G3，独立家族，需要独立 slice）

「他有哪些论文」接机构锚点：会话快照正确（机构锚点+指代提示在位），但
规划器把人称代词绑到机构锚点且不做类型校验 → 放行 paper 域 A:answer，
检索到垃圾论文。既有澄清规则（canonical_v2_chat.py:778「您的问题里使用
了他/她/它…」）未触发。修复方向：代词绑定加锚点类型守卫（人称代词 ×
非人物锚点 → 走澄清）。属规划器行为变更，按规矩立独立 change 再动。

## R3（2026-08-28 傍晚）：G3 代词×锚点类型守卫 —— 门内已知失败清零

### 做了什么（OpenSpec `fix-pronoun-anchor-type-guard`）

- `followup_referents.py` 新增 `has_personal_pronoun()`（他/她，沿用单数
  代词边界规则；它/这家/该不触发）。
- `canonical_v2_chat._referent_clarification_needed` 新增守卫分支：人称
  代词 × 非 professor 域锚点 → 澄清；查询自带显式主体或 referent 历史
  里有人物绑定时豁免。

### 发现与验证

- 新单测 9/9；referent-history 套件 11 个失败经 stash 往返证实为 HEAD
  既有（此前已记录的 admin 漂移之一），非本次引入。
- **重放门 G3 转绿**；整体 18/19 —— 唯一失败换成 G7 第 2 轮（优必选
  缺席）。
- G7 残差重新定性（lane 层已全绿后暴露的新面）：web lane 稳定
  succeeded/48、含优必选的榜单页（职友集排名/70+人形机器人链企）稳定
  到达答案层，但合成答案的条目预算有时被本地 vector 噪声公司（钟表/
  建筑/传播类）挤占，优必选落选。今日门内观测约 2/3 单轮通过率。属
  **P8 枚举完整性家族**（答案合成质量调优：条目预算/头部企业优先级），
  需要独立的 prompt/融合 slice，不做顺手改。

### 影响哪些问题

- G3（P4 家族的代词面）关闭；门内已知"缺陷类"失败清零，剩余唯一失败
  归入 P8 质量家族。多轮代词安全边界新增一条不变量：人称代词只绑人物
  锚点。
