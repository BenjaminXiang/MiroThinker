# Acceptance: anchor-standalone-professor-relations

| # | Criterion | Evidence |
|---|---|---|
| A1 | Standalone professor→company query anchors the professor | live plan `lanes=[relationship, web]`, `domains=[company]`; relationship lane 1 candidate |
| A2 | Standalone professor→paper query anchors the professor | `test_standalone_anchor` unit + planner path; no live paper query in this slice |
| A3 | Ambiguous name is not anchored | resolver declines when >1 canonical id; `test_standalone_anchor_declines_unrelated_or_ambiguous` |
| A4 | Unrelated query is unchanged | `深圳有哪些机器人公司` / `丁文伯教授的研究方向` live answers unchanged |
| A5 | Live company query | `丁文伯创办的公司是哪家` → 深圳无界智航科技有限公司，citation `local-source-08f0d53d00dda3a8`; no 丁文波/千信科技 |
| A6 | Live patent query | `丁文伯有哪些专利` → 申请号 202410612834.1 + 15-patent public report; no 丁文博/丁文胜; citations are web-source only |
| A7 | Local company→patent count is not capped by the lane window | `本地知识库收录了优必选多少专利` and `优必选有多少专利` → 450 件, citation `local-source-5ac2eb76475da877`, `structured_payload.local_patent_count=450` |
| A8 | Count path does not hijack listing queries | `优必选有哪些专利` still uses relationship+web listing (12 local patent citations), no count fast path |

Evidence: `.agents/runs/anchor-standalone-professor-relations/verification.md`.
| A9 | Professor claims render the pack's non-summary fields and all company roles | `_semantic_text` synthetic payload → 院系/邮箱/主页/论文数/专利数/教育/工作/获奖/企业角色; non-founder role → "担任首席科学家" |
| A10 | Honorific and institution constraints bind the intended professor | `王伟教授` → `王伟`; `清华的王伟教授的评价如何` → 王伟; prefix match `清华大学` ↔ `清华大学深圳国际研究生院` = True, `北京大学` = False |
| A11 | A named professor with no local match does not inherit a neighbour; `他/她` attribute turns keep the professor anchor | `赵大锤教授的研究方向` no unrelated professor claim; `丁文伯有哪些论文` → `他的研究方向` keeps 丁文伯 (live) |
