# Gap Registry — 16 缺口 → 可执行断言（harden-serving-test-harness）

> 每条缺口映射到一个可执行断言及其当前状态（RED = 缺口存在）。
> 判定器：`.agents/runs/testset-baseline-20260909/run_testset.py`（三层判定）
> + `data_probes.py`（数据侧）。RED 基线：离线复判
> `results-ds-flash-systemd.json`（2026-09-09 flash 存档，关键词口径 22/25）。

## 端点侧断言（run_testset.py 三层判定）

| Gap | 断言 | 锚点 | RED 证据（离线复判存档） |
|---|---|---|---|
| GAP-01 企业→专利不可达 | g17-t1: ≥3 个 CN 号 + local_citations ≥1 | `g17-t1` | RED: patent_ids 1<3, local 0<1 |
| GAP-02 枚举召回不完整 | g2-t1: 五家关键点全出现 | `g2-t1` entities | RED: missing 开普勒/九号 |
| GAP-03 多约束人物检索 | g7-t1: ≥2 金标人物/公司 | `g7-t1` pool | RED: pool 0<2 |
| GAP-04 上下文收窄不完整 | g2-t2 / g5-t2: 收窄覆盖 GT ≥80% | `g2-t2`,`g5-t2` | RED: 1/6, 2/12 |
| GAP-05 立场与 GT 相反 | g2-t3: stance_forbid 正则（普渡否定按电梯） | `g2-t3` stance | RED: 两条 stance 命中 |
| GAP-06 实体事实错误 | g4-t2: forbidden 李志豪 + 法定代表人⇒穆世龙 | `g4-t2` | RED: forbidden 命中 + fact 锚失败 |
| GAP-07 本地引用缺失 | 本地答案轮 local_citations ≥1 | g1-t1/t2, g4-t1/t2, g6-t1, g7-t1, g8-t1, g17-t1/t2 | RED: 7/9 provenance 失败 |
| GAP-08 web 内容污染 | web 引用不含导航/错误模板 | `CITATION_FORBIDDEN_PATTERNS`（仅 live 可判） | RED by evidence（存档无引用文本，live 断言已上线） |
| GAP-09 LLM 守卫硬失败 | 守卫命中→模板降级不空答 | 故障注入测试（close-workbook-gaps B5） | RED by evidence（pro 档 g17-t1 空答案，knowledge_serving_isolated.py:4033） |
| GAP-10 关键词判定过松 | 本三层判定器本身 | run_testset.py + anchors.py | FIXED（本 change）：g2-t2/g2-t3/g4-t2 已翻 RED |
| GAP-11 五轮无锚点 | g6-t2/g8-t2/g9/g10/g14 锚点策展 | anchors.py `human_verified` | FIXED（本 change）：5 轮已补 |
| GAP-12 三命中率无目标线 | stage0 阈值裁决 | 待用户裁定（建议：点名≥90%/语义≥70%/关系≥70%） | PENDING DECISION |

## 数据侧断言（data_probes.py，已跑，8 RED / 1 PASS）

| Gap | 断言 | 现状 |
|---|---|---|
| GAP-13a 教授 profile_summary 套话 | <10% | RED: 54.3% (2151/3958) |
| GAP-13b paper_summary 占位 | =0% | RED: 100% (3958/3958) |
| GAP-13c title 占位 | <5% | RED: 63.5% (2515/3958) |
| GAP-13d email 占位 | =0% | RED: 31.6% (1251/3958) |
| GAP-13e research_directions 填充 | ≥80% | RED: 49.7% (1969/3958) |
| GAP-14 企业 aliases 覆盖 | ≥30% | RED: 4.8% (342/7089) |
| GAP-15 数据版本对齐 run14 | serving==47,071 | RED: serving 5,659 vs run14 47,071（论文 563 vs 24,520） |
| GAP-16 论文 professor_ids 链接 | ≥10%（暂定阈值） | RED: 0.0% (0/24,520) |
| （对照）GAP-01 数据侧 | 服务包专利申请人绑定 ≥60% | **PASS**: 82.4% (1592/1931)，优必选 58 条在包内 |

## 三层判定新基线（离线复判 flash-systemd 存档）

- 关键词口径 22/25 → **三层口径 9/25**。全部 16 个 FAIL 可追溯到缺口：
  - GAP-02: g2-t1；GAP-04: g2-t2, g5-t2；GAP-05: g2-t3；GAP-06: g4-t2；
  - GAP-03: g7-t1；GAP-01: g17-t1；GAP-07: g1-t2, g4-t1, g4-t2, g6-t1, g7-t1, g17-t1, g17-t2；
  - GAP-13/15（知识库深度未服务出来）: g1-t1, g1-t2, g4-t1, g8-t1；
  - GAP-16（论文↔教授）: g6-t1；语义召回（本地厂商未召回）: g14-t1；
  - 关键点契约缺项: g12-t1（真机实测）, g15-t1（基于规则生成）。
- PASS 9 轮均为实质正确（g3 安全拒答 / g5-t1 / g6-t2 / g8-t2 / g9 / g10 / g11 / g13 / g16）。
- 锚点纠错记录：g9「博导→博士生导师」别名、g5-t1 去掉超关键点的过宽完整性集、g11/g12 改为关键点契约集（ratio 1.0）。
