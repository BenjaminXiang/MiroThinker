# Review: deepening-turn-anchor-carryover

- Date: 2026-08-17
- Reviewer: 用户（产品所有者，session 内直接评审）
- Implementer: ZCode (本 session)
- Verdict: **Accept**

## Basis of acceptance

1. Artifact review: proposal / design / verification 摘要与逐项讲解（含 proposal 白话重述）。
2. Design probe: 评审中用户质询词表覆盖度 → 实测漏网清单（该团队/这所大学/零指代省略等），
   确认闭集词表不穷尽、漏网静默回退旧行为——用户判断其为"头痛医头"式补丁并接受为
   **过渡方案**，定位为后续 LLM 理解层（contextual query interpretation）的确定性兜底与
   回归下限。
3. Production evidence (implementer-run, recorded in verification.md § Production smoke):
   both registered triggers PASS on 18188 (subject carried, no substitution, no junk web list).
4. Design-level confirmation (同日晚些): design.md（6 断点根因表 + M1 认路/M2 点名核对/
   M3 计数器三机制，含 M2 的"误请合法锚点"取舍与优先级顺序）经白话逐项讲解后，
   用户明确确认无异议（"这个我也没问题 Accept"）。

## Decisions recorded

- 词表覆盖边界：接受为已知边界，不扩表；后续走"LLM 理解 + 确定性校验"新 change
  （用户要求先深入调研再立项）。
- 两个生产观察（anchor 路径重写视图脱锚；一致性门将 web lane 过滤到 0）：接受现状，
  并入登记 §3 遥测 follow-up 一起看。
- 本 change 的定位改写：deterministic fallback layer + regression floor for the future
  LLM interpretation layer。

## Residual notes

- 登记 §2（截断 prose）、§3（web-lane 遥测）仍 Open。
- `test_knowledge_build_isolated.py` 本机超时为预存在问题（stash 归因），CI 复跑待做。
- 零指代省略（"那融资情况呢"）闭集无解，明确留给 LLM 理解层。

## State transition

- Change `deepening-turn-anchor-carryover`: Candidate → **Accepted** (2026-08-17).
- 依赖解锁：登记 §2/§3、后续 LLM 理解层 change 可立项。
