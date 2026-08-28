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
