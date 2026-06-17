# 逐 seed 执行清单 — 高校教师→论文 论文抽取修复

> 2026-06-16. Actionable companion to `2026-06-16-professor-paper-cleanup-gap-analysis.md`. One row per seed; check a seed to start it. Priority tier = 0-论文率（论文抽取失败的代理指标）。Roster/adapter 层已完成（见 gap-analysis §关键纠偏），所以这里的"下一步"全部是 **Part 2.1 论文抽取模板修复**，不是造 roster 爬虫。
>
> 数据口径：`professor_seed` × affiliation 匹配 × `professor_paper_link`（任一 link_status）。0-论文 = 教授无任何论文链接。

## 怎么用

- 从 **P0** 起勾选。每个 seed 是一个独立工作单元：抓样本主页 → 认出引用模板 → 加/修抽取 → 验收该 seed 0-论文率下降。
- 同一 adapter 家族的 seed（如 szu-teacher-family ×7）可批量处理：模板可能共用，先做一个、验证是否复用。
- P3 不做论文抽取（健康），只跟 Part 1.2 画像质量。

---

## P0 — 严重（0-论文率 ≥ 60%，明确的抽取失败）· 9 seed / ~498 位 0-论文教师

| ☐ | sid | 院系 | adapter | 教授 | 0-论文 (率) | 下一步 |
|---|---|---|---|---|---|---|
| ☐ | 24 | 深圳信息职业技术大学/中德机器人 | suit-sziit | 14 | 14 (100%) | 抓主页样本→认模板→加抽取 |
| ☐ | 5 | 深圳大学/计算机与软件 | szu-csse-teacher-team | 79 | 77 (97.5%) | 同上（最高绝对值之一） |
| ☐ | 44 | 深圳技术大学/人工智能 | sztu-teacher-family | 60 | 47 (78.3%) | 同上（与 43/45/46/47 同家族，先做它验证复用） |
| ☐ | 11 | 深圳大学/物理与光电 | szu-cpoe | 265 | 194 (73.2%) | 同上（绝对值最大） |
| ☐ | 27 | 电子科技大学(深圳)/软件工程 | uestc-yjsjy | 7 | 5 (71.4%) | 同上（与 25/26/28 同家族） |
| ☐ | 43 | 深圳技术大学/中德智能制造 | sztu-teacher-family | 32 | 22 (68.8%) | 同上 |
| ☐ | 26 | 电子科技大学(深圳)/计算机技术 | uestc-yjsjy | 44 | 29 (65.9%) | 同上 |
| ☐ | 32 | 深圳理工/算力微电子 | suat-teacher-family | 20 | 13 (65%) | 同上（与 29/30/31 同家族） |
| ☐ | 25 | 电子科技大学(深圳)/电子信息 | uestc-yjsjy | 156 | 97 (62.2%) | 同上 |

## P1 — 高（40–59%）· 5 seed / ~129 位

| ☐ | sid | 院系 | adapter | 教授 | 0-论文 (率) | 下一步 |
|---|---|---|---|---|---|---|
| ☐ | 28 | 电子科技大学(深圳)/机械 | uestc-yjsjy | 11 | 6 (54.5%) | 同 P0（uestc 家族） |
| ☐ | 15 | 深圳大学/材料 | szu-teacher-family | 100 | 47 (47%) | 同 P0 |
| ☐ | 19 | 哈尔滨工业大学(深圳)/计算机 | hitsz-college-teacher-family | 103 | 46 (44.7%) | 抓主页样本→认模板→加抽取 |
| ☐ | 20 | 哈尔滨工业大学(深圳)/集成电路 | hitsz-college-teacher-family | 33 | 14 (42.4%) | 同上（hitsz 家族，与 19 共用） |
| ☐ | 18 | 深圳大学/电子与信息 | szu-teacher-family | 40 | 16 (40%) | 同 P0 |

## P2 — 中（20–39%）· 8 seed / ~456 位（含 SUSTech 323）

| ☐ | sid | 院系 | adapter | 教授 | 0-论文 (率) | 下一步 |
|---|---|---|---|---|---|---|
| ☐ | 9 | 南方科技大学 | sustech-roster | 989 | 323 (32.7%) | 抽样区分"抽取失败"vs"源真少"；失败的修模板 |
| ☐ | 31 | 深圳理工/材料能源 | suat-teacher-family | 42 | 15 (35.7%) | 同 P0（suat 家族） |
| ☐ | 45 | 深圳技术大学/工程物理 | sztu-teacher-family | 90 | 29 (32.2%) | 同 P0（sztu 家族） |
| ☐ | 12 | 深圳大学/化学与环境 | szu-teacher-family | 57 | 18 (31.6%) | 同 P0 |
| ☐ | 14 | 深圳大学/机电与控制 | szu-teacher-family | 123 | 38 (30.9%) | 同 P0 |
| ☐ | 36 | 中山大学(深圳)/电子与通信 | sysu-sece-faculty | 28 | 6 (21.4%) | 抽样确认 |
| ☐ | 38 | 中山大学(深圳)/集成电路 | sysu-sic-members | 28 | 6 (21.4%) | 抽样确认 |
| ☐ | 10 | 深圳大学/数学 | szu-teacher-family | 101 | 21 (20.8%) | 同 P0 |

## P3 — 健康（< 20%）· 15 seed / ~81 位 · 不做论文抽取

| ☐ | sid | 院系 | adapter | 教授 | 0-论文 (率) | 下一步 |
|---|---|---|---|---|---|---|
| ☐ | 46 | 深圳技术大学/集成电路与光电 | sztu | 47 | 9 (19.1%) | 仅画像质量 |
| ☐ | 6 | 香港中文大学(深圳)/人工智能 | cuhk | 37 | 7 (18.9%) | 仅画像质量 |
| ☐ | 35 | 香港中文大学(深圳)/理工 | cuhk | 158 | 21 (13.3%) | 仅画像质量 |
| ☐ | 37 | 中山大学(深圳)/智能工程 | sysu-ise | 93 | 10 (10.8%) | 仅画像质量 |
| ☐ | 42 | 中山大学(深圳)/柔性电子 | sysu-sofe | 10 | 1 (10%) | 仅画像质量 |
| ☐ | 8 | 清华SIGS | sigs_teacher_api | 256 | 17 (6.6%) | 已修过；仅监控 |
| ☐ | 41 | 中山大学(深圳)/理学院 | sysu-science | 49 | 3 (6.1%) | 仅画像质量 |
| ☐ | 7 | 香港中文大学(深圳)/数据科学 | cuhk | 98 | 6 (6.1%) | 仅画像质量 |
| ☐ | 30 | 深圳理工/合成生物 | suat | 45 | 2 (4.4%) | 仅画像质量 |
| ☐ | 29 | 深圳理工/计算机与AI | suat | 86 | 3 (3.5%) | 仅画像质量 |
| ☐ | 47 | 深圳技术大学/创意设计 | sztu | 60 | 2 (3.3%) | 仅画像质量 |
| ☐ | 13 | 深圳大学/生命与海洋 | szu | 15 | 0 (0%) | 健康 |
| ☐ | 21 | 深圳大学/微众金融科技 | szu | 9 | 0 (0%) | 健康 |
| ☐ | 40 | 中山大学(深圳)/网络空间安全 | sysu-scst | 28 | 0 (0%) | 健康 |
| ☐ | 39 | 中山大学(深圳)/先进制造 | sysu-am | 26 | 0 (0%) | 健康 |

> Roster 边角：PKUSZ（`pkusz.edu.cn/szdw.htm`）无命名 adapter（archived `prof-seed-adapter-coverage`），单独处理。

---

## 单 seed 执行 runbook（论文抽取模板修复）

1. **取样**：从该 seed 取 5–10 位 0-论文教师的主页 URL（`professor.primary_official_profile_page_id → source_page.url`）。
2. **认模板**：人工/LLM 看主页 HTML，定位"发表论文"区块的结构（`<table>`/`.sudy-tab`/编号列表/JSON API…）和引用格式（作者-标题-期刊 如何分割）。
3. **加/修抽取**：在 `homepage_publications.py` 加针对该模板的提取（mirror SIGS 先例 `prof-sigs-tab-template-extraction`）；若引用分割易错，配 `_split_*` splitter + LLM fallback 的 boundary 守卫（gap-analysis C2/C3）。
4. **验收**：对该 seed 重跑抽取（dry-run），统计 0-论文率下降 + 抽出的标题经 `is_plausible_paper_title` 过滤（避免再造垃圾标题）。
5. **入库**：通过 `run_homepage_paper_ingest.py` 写入；新论文走 Part 2.2 富集（B1/D1/D2）+ Part 2.3 摘要翻译。

## 跨切面（非 per-seed，但阻塞整体）

| ☐ | 项 | 说明 | portfolio |
|---|---|---|---|
| ☐ | A1 收口闭环 | pipeline_issue 永不 resolved | W3a |
| ☐ | F1 账本/index 对账 | change-ledger 无 6 月行；index 停 5/4 | W3b |
| ☐ | Part 1.2 画像质量 | 短 summary/缺综述/缺 paper_summary/COALESCE 粘性 | W0c/W2b/W2d |
| ☐ | Part 2.2 富集 | B1 provider / D1 web 污染 / D2 DOI | W0a/W1a/W0d |
| ☐ | Part 2.3 摘要翻译 | ~29k 缺 summary_zh + Jina fallback | W2a |

---

## 起点（建议）

- **最高杠杆 + 最清晰失败**：**sid 5 深大计软（97.5%，77 人）** 或 **sid 11 深大物光（73.2%，194 人）**——绝对值大、失败明确、szu 家族可能复用。
- **最易验收**：**sid 24 深圳信息（100%，14 人）**——小、100% 失败、修完一眼看出。
- **家族复用验证**：先做一个 uesc/sztu/suat 家族 seed，验证模板能否复用到同家族其它 seed。
