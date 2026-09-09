# Verification: harden-serving-test-harness

## A1.3 — 离线复判存档（三层判定翻转表）

Command:
`python .agents/runs/testset-baseline-20260909/run_testset.py --offline .agents/runs/testset-baseline-20260909/results-ds-flash-systemd.json`

Result: 关键词口径 22/25 → 三层口径 **9/25**。

### 必须翻转的脆弱通过（GAP-10 验收点）

| 轮次 | 旧判定 | 新判定 | 失败层 | 映射缺口 |
|---|---|---|---|---|
| g2-t2 | PASS | FAIL | entity pool 1<5, completeness 1/6 | GAP-04 |
| g2-t3 | PASS | FAIL | stance ×2（"普渡没有一款…按电梯"） | GAP-05 |
| g4-t2 | PASS | FAIL | forbidden 李志豪, fact 法定代表人⇒穆世龙, completeness 1/3 | GAP-06 |

✓ 三轮全部翻转为 FAIL，失败原因逐层可读。

### 其余翻转（逐轮裁决：缺口性 vs 过紧）

| 轮次 | 新判定 | 裁决 | 依据 |
|---|---|---|---|
| g1-t1 | FAIL (1/5) | 缺口性 | 答案缺邮箱/佐治亚/博士后等 GT 核心档案字段 → GAP-13/15 |
| g1-t2 | FAIL (1/5+prov) | 缺口性 | 缺 联合创始人/首席科学家/穆世龙/熊祺 + 本地引用 0 → GAP-07 + 知识库深度 |
| g2-t1 | FAIL | 缺口性 | 缺 开普勒/九号 → GAP-02 |
| g4-t1 | FAIL (3/6+prov) | 缺口性 | 缺 穆世龙/X-H1/X-Sim → GAP-06 家族 + GAP-07 |
| g5-t2 | FAIL (2/12) | 缺口性 | 收窄只剩 2 家（嘉立创/一博），GT 11 家 → GAP-04 家族 |
| g6-t1 | FAIL (3/5+prov) | 缺口性 | 缺 涉及教授(丁文伯/李阳) → GAP-16；prov → GAP-07 |
| g7-t1 | FAIL (pool 0) | 缺口性 | GAP-03 原样复现 |
| g8-t1 | FAIL (2/5) | 缺口性 | 缺 六维/铂力特/腾讯 → 知识库深度（GAP-15） |
| g12-t1 | FAIL (2/3) | 缺口性 | 关键点契约「真机实测」未答出 |
| g14-t1 | FAIL (pool 1) | 缺口性 | 召回的是 web 厂商（伯牙/星际光年），GT 本地厂商未召回 → 语义召回缺口 |
| g15-t1 | FAIL (2/3) | 缺口性 | 关键点契约「基于规则生成」未答出 |
| g17-t1 | FAIL | 缺口性 | GAP-01 原样复现（1 CN 号、本地引用 0） |
| g17-t2 | FAIL (prov) | 缺口性 | 内容对但本地引用 0 → GAP-07 |

### 过紧纠正（锚点策展错误，已修正后复跑）

| 轮次 | 初判 | 纠正 | 终判 |
|---|---|---|---|
| g9-t1 | FAIL (3/5) | 「博导」加别名「博士生导师」（答案确实写了博士生导师） | PASS (4/5) |
| g5-t1 | FAIL (3/5) | 删掉超出关键点契约的完整性集（华秋/兴森）；推荐清单以关键点三家为准 | PASS |
| g11-t1 | — | 改为关键点契约集（真实数据+合成数据，ratio 1.0） | PASS |
| g12-t1 | — | 改为关键点契约集（遥操作/动捕/真机实测，ratio 1.0） | FAIL（契约性） |

### 保持 PASS 的轮次（实质正确，无误伤）

g3-t1（安全拒答）、g5-t1、g6-t2、g8-t2、g9-t1、g10-t1、g11-t1、g13-t1、g16-t1 —— 9 轮。
对照检查：这些轮的 GT 关键点均被完整覆盖、立场一致、无伪造实体。

### 层面汇总（flash-systemd 存档，离线）

- entity 16/22 applicable；stance 0/2；completeness 8/20；provenance 2/9。
- 离线局限：存档 JSON 无引用文本，GAP-08（web 污染）只能 live 判定；离线时该子层跳过（不误伤）。

## A1b.2 — 数据探针 RED 基线

Command: `python .agents/runs/harden-serving-test-harness/data_probes.py`
Result: 8 RED / 1 PASS（见 gap-registry.md 数据侧表；唯一 PASS 证明 GAP-01
数据在包内、断的是读取路径）。

## 复跑兼容性

- 同一判定器离线复判 `results-full-20260909.json`（模板档存档）：正常运行、正常出分层汇总。
- live 模式新增 web 引用文本采集（GAP-08 判定依据），不影响存档格式兼容。
