# Round 6 regression (2026-08-03, v41 pack with company_name + C2_0012)

- PASS 21/25 (baseline 20/25): Q25 专利申请人 now renders 深圳市优必选科技
  股份有限公司; Q20 模拟器生成数据 route improved to pass.
- No turn regressed (all baseline passes remain passes).
- Total latency 291.7s vs baseline 286.3s (+1.9%, within web variance).
- Remaining gaps (tracked): T3 上海开普勒 (data-end semantics), T19/T22/T23
  concept-question KEY coverage (web-lane variance; answers cover most
  semantics). T3 机械臂按电梯 answers 普渡 FlashBot Arm on re-run (web
  variance on first attempt).
