# G2 身份治理审计（四域，company 为重点）

- 数据源（只读，`mode=ro&immutable=1`）：
  - run14：`/var/tmp/mirothinker-data-v2/serving-pack-run14/lookup.sqlite3`（release `candidate-v2-20260819-r1`，47,071 docs）
  - s12f：`/var/tmp/mirothinker-canonical-v2-s12f/serving-pack/lookup.sqlite3`（release `candidate-s12f-20260801-v1`，5,659 docs）
- 本文只做实测与提案：未改任何代码、未动 serving worktree、未 git commit。
- 复现命令见 §0.4；机器可读结果在 `g-series/out/`。

## TL;DR（五条结论）

1. **identity 碎片化真实存在但规模有限**：company 域精确同名 0 重复；近似（品牌核）口径下 **72 个碎片实体 / 146 篇身份文档**（97% 是 2 文档簇，含 2 个 3 文档簇）。教授 18 簇、论文 6 簇、专利 0 簇。
2. **冲突是碎片化的常态而非例外**：72 个 company 品牌簇中 `profile_summary`/`normalized_name` 冲突率 **72/72**，`technology_route_summary` 66/72，地址 49/72，industry 43/72；`credit_code`/`registered_capital` 全库 7,089 篇全空——**没有可用的统一社会信用代码做合并锚点**。
3. **跨 release id 100% 换血**：s12f→run14，四域所有可匹配自然键（company 名称 1,733 对、professor 1,391 对、paper DOI 494 对、patent 号 1,931 对）的 `canonical_object_id` **无一保留**（0 对相同）。其中 575/1,733（33%）company 对 16 字段快照逐字段一致，仍换了 id——这是"重铸"而非"内容变化"。
4. **机制已定位**：`canonical_identity_resolution.py:2219-2237` 的 id = `{entity_type}-c-` + `sha256({release_id, entity_type, sorted(source_identity_ids), generation_key})[:24]`——**release_id 进了铸造哈希**，且两次构建之间没有任何持久身份状态承接，代际必然重铸。
5. **绑定引用完整性现状是好的**：两包内专利→公司的 `canonical_company_id` 全部可解析（run14 7,650 条/963 个公司 id、s12f 1,704 条/697 个公司 id，dangling 均为 0）；但绑定是"代内自洽"，**跨代即断**（优必选 58→450 条绑定围绕全新 id，C2 已见）。§4 给出稳定 id 协议草案（ledger + 版本 id 双层）作为两线契约家规 ADR 的输入。

---

## 0. 口径、数据源与复现

### 0.1 身份文档定义

`lookup_document` 一行 = 一个 canonical identity 对象（`canonical_object_id` == `lookup_content.id` == `canonical_identity_id`，包内无重复行）。文档计（run14）：company 7,089 / paper 24,520 / patent 11,504 / professor 3,958。

### 0.2 company 名称分层（本审计的"精确/近似"口径）

| 层 | 规则 | 定位 |
|---|---|---|
| T1 exact | 去空白后全等 | 精确同名 |
| T2 core | 去括号内容 → 剥地域前缀（白名单）→ 剥法律形式后缀（有限/股份/集团…） | 保守近似 |
| T3 stem | T2 再剥尾部行业词（科技/机器人/智能…，最多 2 轮） | 宽口径上界，含误合并 |

T2/T3 的地域前缀用**白名单**（深圳/成都/广东省…），不用"X 市"模糊正则——自查时发现正则会误剥"普智城市""图灵集市"这类含"城市/集市"的品牌词（已修）。

### 0.3 其它域匹配键

professor：`canonical_name_zh|name`（T1），二级键再拼 `institution`；paper：标题归一化（小写+去标点空白），二级键 DOI；patent：`patent_number` 归一化（去符号大写）。字段值可能是 `{reference_id,name}` dict 或 dict 列表，比较前统一取 `name` 拼接。

### 0.4 复现

```bash
cd /home/longxiang/MiroThinker
python3 .agents/runs/close-workbook-gaps/g-series/g2_identity_audit.py    # §1-§2 → out/g2-run14-identity-audit.json
python3 .agents/runs/close-workbook-gaps/g-series/g2_cross_release.py     # §3    → out/g2-cross-release.json
python3 .agents/runs/close-workbook-gaps/g-series/g2_probe_mergeability.py # §4 证据（强证据互斥统计）
python3 .agents/runs/close-workbook-gaps/g-series/g2_probe_recency.py     # §4 证据（时间/质量分布）
python3 .agents/runs/close-workbook-gaps/g-series/g2_view.py <audit.json> clusters|prof|paper|examples
```

### 0.5 局限（先声明）

- T3 是上界口径：72 簇未人工全量标注，含品牌撞名的误合并（例见 §1.3、§2.3）；因此 §2 的冲突率是**上界**，§4 的合并规则按"宽口径候选 + 强证据裁决"设计。
- 跨 release 对比只有两个代（s12f/run14），"100% 换血"是这两代的实测；机制分析（§3.3）来自代码，可推广到任意两代。
- 字段冲突比较不判断"谁对谁错"，只测"是否不一致"；具体覆盖优先级见 §4.2（部分推荐基于完备度统计，需产品侧校准）。

---

## 1. 身份碎片化计数

### 1.1 四域总表（run14）

| 域 | 匹配键 | 碎片实体数 | 涉及文档 | 每实体文档数分布 | 最大 | 碎片率(实体) |
|---|---|---|---|---|---|---|
| company | T1 精确名 | **0** | 0 | — | 1 | 0% |
| company | T2 core | **12** | 24 | {2: 12} | 2 | 0.17% |
| company | T3 stem | **72** | 146 | {2: 70, 3: 2} | 3 | 1.02% |
| professor | 姓名 | **18** | 37 | {2: 17, 3: 1} | 3 | 0.46% |
| professor | 姓名+机构 | **9** | 19 | {2: 8, 3: 1} | 3 | 0.23% |
| paper | 标题归一化 | **6** | 12 | {2: 6} | 2 | 0.02% |
| paper | DOI 精确 | **0** | 0 | — | 1 | 0% |
| patent | 专利号 | **0** | 0 | — | 1 | 0% |

两个"0"值得注意：**company 与 patent 域当前管道不会产出同名/同号孪生文档**——碎片化不是"重复行"，而是"同一实体多次建档（跨来源族/跨法人形态）"。professor 与 paper 的碎片化在 s12f 就存在且逐数相同（18 簇/37 文档、6 簇/12 文档），是**跨代继承**的存量问题。

### 1.2 company 典型样本 10 例（T3 stem 簇；完整 72 簇清单见 `out/g2-clusters.txt`）

| # | 品牌簇 | 文档数 | 成员（名称） | 类别（判读） | 强证据* |
|---|---|---|---|---|---|
| 1 | 普渡 | 3 | 深圳市普渡科技有限公司 / 深圳市普渡科技股份有限公司 / 成都市普渡机器人有限公司 | 更名（有限→股份）+ 异地主体，同一品牌族 | 单边缺失，无互斥证据；绑定 128/0/27 分裂 |
| 2 | 华芯 | 3 | 深圳市华芯机器人技术有限责任公司 / 深圳华芯信息技术股份有限公司 / 深圳市华芯智能装备有限公司 | **品牌撞名（3 个不同法律实体）** | 地址+法代+行业全互斥 |
| 3 | 云豹 | 2 | 深圳云豹智能股份有限公司 / 深圳云豹智能有限公司 | 更名（有限→股份），T2 同核 | 强证据不互斥 |
| 4 | 诺因 | 2 | 深圳市诺因智能有限公司 / 深圳诺因智能有限公司 | 同实体两档（市名前缀差异） | 强证据不互斥 |
| 5 | 中智科创 | 2 | 深圳中智科创机器人有限公司 / 中智科创机器人有限公司 | T2 同核但**强证据互斥**（疑不同实体） | 地址+法代互斥 |
| 6 | 志凌伟业 | 2 | 深圳市志凌伟业光电有限公司 / 深圳市志凌伟业技术股份有限公司 | 更名候选但强证据互斥（待人工） | 地址+法代互斥 |
| 7 | 顺丰 | 2 | 顺丰科技有限公司 / 顺丰控股股份有限公司 | 同集团不同法人 | 地址+法代互斥 |
| 8 | 中国广核 | 2 | 中国广核集团有限公司 / 中国广核电力股份有限公司 | 同集团不同法人 | 不互斥（一侧字段缺） |
| 9 | 银河通用 | 2 | 银河通用 / 北京银河通用机器人有限公司 | 同一实体（短名档 + 全名档） | 不互斥 |
| 10 | 海思 | 2 | 深圳海思机器人有限公司 / 深圳市海思半导体有限公司 | **品牌撞名（机器人 vs 半导体）** | 地址+法代互斥 |

\* 强证据 = `registered_address`/`legal_representative`（全库有值率分别 6,506/7,089、5,486/7,089）。"互斥"= 两档都有值且不同。

关键 cid（可追溯）：
- 普渡：`company-c-72b2ec528908ac199ee1dbc7`（有限）/ `company-c-f11204f5f0dee0d8a1e1fdd4`（股份）/ `company-c-f465962ae6d0ac84c5f8cad3`（成都）。
- 华芯：`company-c-09fd4866e9e1db6f68fcfabf` / `company-c-429482ca52b32010d14172e3` / `company-c-cfa53df2228f128f98e06801`。

### 1.3 其它三域样本

**professor（18 簇 / 37 文档）**：9 簇同机构、9 簇跨机构。
- 同机构 9 簇：多为"同一位老师被多个院系/来源重复建档"（如 罗智泉 CUHK-SZ 人工智能学院 vs 理工学院；朱宝亭 理工学院 vs 医学院；陈斌 HIT-SZ 理学院/计算机学院/国际 AI 研究院 3 档；刘清侠 SZTU 新材料 vs 人工智能学院）——**同人重复，真碎片**。
- 跨机构 9 簇：多为同名不同人（李兵 HIT-SZ vs 清华深研院；王伟 HIT-SZ vs 中大深圳；李佳 清华深研院 vs SZTU；Parvej Alam CUHK-SZ vs 清华深研院，邮箱机构均不同）——**同名不同人，不应合并**。

**paper（6 簇 / 12 文档）**：全部是"同一论文的多来源版本档"，且 6 对 DOI 各不相同（无一共享 DOI）：
- 预印本 vs 期刊版：`10.48550/arxiv.1908.09806` vs `10.1109/twc.2020.2978479`；LICS'92 会议版 vs 期刊版。
- 同一文章双 DOI 提供商：`10.2307/2337534` vs `10.1093/biomet/82.3.561`（Biometrika 1995）；`10.1198/jabes.…` vs `10.1007/s13253-…`。
- 德文版 vs 国际版（Angewandte）：`10.1002/ange.…` vs `10.1002/anie.…`。
→ **结论：论文去重不能只靠 DOI 精确相等**（DOI 相等口径 0 重复会漏掉这 6 对），需要"标题归一化 + 作者/年份/会议"联合判定，且"版本档是否算同一实体"是产品策略问题。

**patent（0 簇）**：`patent_number` 无重复——专利号是当前四域里最可靠的自然键。

### 1.4 判读

- 碎片化的主要成因是**多来源族叠加**（company：`company-p4` 5,491 档 + `COMP-legacy` 1,037 档 + `company-backfill` 561 档，同一实体可能同时存在 2–3 档），而不是采集重复。
- id 与"实体"是 n:1 关系（多个 canonical id ↔ 一个真实世界实体），当前没有任何"实体级"标识；这是 §4 稳定 id 协议要解决的对象。

---

## 2. 冲突字段清单（同一实体多 identity 之间）

### 2.1 普渡完整样本（3 档逐字段，run14）

| 字段 | id1 `…72b2ec…`（COMP-legacy，last_updated 2026-04-16） | id2 `…f11204…`（company-p4，2026-09-07） | id3 `…f46596…`（company-backfill，2026-09-07） |
|---|---|---|---|
| name | 深圳市普渡科技有限公司 | 深圳市普渡科技股份有限公司 | 成都市普渡机器人有限公司 |
| normalized_name | **普渡科技**（短名） | 深圳市普渡科技股份有限公司（未归一） | 成都市普渡机器人有限公司（未归一） |
| industry | **机器人** | **物流运输** | （空） |
| industry_tags | （空） | 物流运输 | （空） |
| tech_tags | （空） | 室内外配送机器人研发商 | （空） |
| geography | （空） | 广东省 | （空） |
| registered_address | （空） | 深圳市南山区西丽街道…国际创新谷1栋A座501 | （空） |
| founded_at | （空） | 2016-01-13 | （空） |
| legal_representative | （空） | 张涛 | （空） |
| website | https://www.pudurobotics.com | http://pudutech.com/ | （空） |
| profile_summary | 生成式："…聚焦机器人…商用服务机器人…" | **产品清单**："PUDU CC1 Pro、PUDU T600系列…" | 业务简介："…室内无人配送解决方案提供商…" |
| technology_route_summary | 生成式路线文 | 产品-场景清单 | `Not supplied by the backfill source.` |
| 专利绑定数（run14） | 128 | 0 | 27 |
| 来源族 | COMP-legacy（旧代残留） | company-p4 | company-backfill |

已知样本复现：id1 `industry=机器人`、id2 `industry=物流运输 + tech_tags=室内外配送机器人研发商` 与任务描述一致；补充发现 **id2 的 `profile_summary` 实为产品清单**（同一值也出现在 product_description），**id3 的绑定 27 件**（成都主体确有其专利），**id1 才是 128 件绑定的落点**。

### 2.2 全库冲突扫描

对 72 个 T3 品牌簇逐字段统计（冲突 = ≥2 个不同非空值；覆盖缺口 = 有值/无值并存）：

| 字段 | conflict /72 | 覆盖缺口 /72 | 备注 |
|---|---|---|---|
| profile_summary | **72 (100%)** | 0 | 语义层就不一致（生成文 vs 产品清单 vs 业务简介） |
| normalized_name | **72 (100%)** | 0 | 归一字段本身没归一（Pudu 三档三种形态） |
| technology_route_summary | 66 (92%) | 6 | 含大量 `Not supplied…` 占位 |
| registered_address | 49 (68%) | 18 | 强证据字段 |
| industry | 43 (60%) | 23 | 分类体系冲突（见 §2.3-2） |
| product_description | 43 (60%) | 16 | 与 profile_summary 常同值 |
| team_description | 41 (57%) | 25 | |
| tech_tags | 37 (51%) | 28 | |
| website | 36 (50%) | 26 | |
| founded_at | 36 (50%) | 28 | |
| legal_representative | 30 (42%) | 34 | 强证据字段 |
| industry_tags | 29 (40%) | 35 | |
| aliases | 3 | 9 | 覆盖率仅 342/7,089 |
| geography | 2 (3%) | 63 | 覆盖率 5,491/7,089 且多为"省/省-市"粒度差异 |
| quality_status | 0 | **72** | 全库恒为 `partial`，无信号 |
| registered_capital | 0 | 0 | **全空** |
| credit_code | 0 | 0 | **全空（无统一社会信用代码）** |

T2 core 层（12 簇，更严格）对照：profile_summary 12/12、technology_route_summary 9/12、tech_tags 3/12、industry 2/12、address 2/12、legal_rep 2/12、website 2/12、founded_at 2/12——**即使同核匹配，摘要与行业冲突依然存在**。

占位符分布（全库 7,089 篇）：`company-p4` 719 篇、`company-backfill` 561 篇（100%）的 profile/route 摘要含 `Not supplied…` 类占位文本；legacy 仅 2 篇。

来源族完备度（15 字段非空计数均值 / 中位 / 最大，满分 15）：

| 来源族 | 文档数 | 均值 | 中位 | 最大 | 摘要占位率 |
|---|---|---|---|---|---|
| company-p4 | 5,491 | 11.5 | 12 | 12 | 13.1% |
| COMP-legacy | 1,037 | 7.15 | 8 | 8 | 0.2% |
| company-backfill | 561 | 2.0 | 2 | 2 | 100% |

字段覆盖率（全库非空非占位）：normalized_name 7,087 / profile_summary 7,071 / industry 6,517 / registered_address 6,506 / technology_route_summary 5,815 / team_description 5,517 / geography 5,491 / founded_at 5,486 / legal_representative 5,486 / tech_tags 5,485 / industry_tags 5,480 / product_description 5,362 / website 5,339 / key_personnel 851 / aliases 342 / **credit_code 0 / registered_capital 0**。

### 2.3 冲突模式（6 条）

1. **摘要字段语义漂移**：同一实体，不同来源把"简介"字段装成不同东西——p4 常有产品清单（Pudu `PUDU CC1 Pro、PUDU T600系列…`）或生成式概述，legacy 有生成式概述（Pudu）或短标签（华芯 `无人机研发公司`），backfill 为业务介绍或占位符。同一字段名在不同来源下**装载不同语义的内容**，直接按优先级覆盖会污染档案。
2. **行业分类体系不一致**：`机器人` vs `物流运输`（Pudu）、`先进制造` vs `人工智能`（华芯）、`能源电力` vs `硬件`（中科）、`先进制造` vs `硬件`（中微）。同一实体在不同来源被分到不同一级类目，且 tags 粒度不同（无 tag vs 1–2 个 tag）。
3. **强证据互斥率 42%**：72 簇中 **30 簇**（42%）`registered_address` 与 `legal_representative` 双双互斥（其中 25 簇连 industry 也冲突）——**自动按品牌名合并会把不同法律实体并掉**（华芯、海思、中智科创、顺丰 vs 顺丰控股、比亚迪半导体 vs 比亚迪股份 均在此列）。
4. **更名/重组类"新旧并存"**：有限→股份（云豹、卧安、乐聚、普渡），市名前缀差异（诺因），短名/全名并存（银河通用）——这类是应合并的真碎片。
5. **normalized_name 反而最不归一**：三档三种写法（Pudu），且 72/72 全冲突——当前"短名通道"（serving 线 `_compact_company_alias` 派生）与文档存储的 `normalized_name` 是两套东西，未对齐。
6. **占位符与空值混排**：backfill 100% 摘要占位、`credit_code`/`registered_capital` 全空、`quality_status` 恒 `partial`——意味着**不能依赖"非空即真"**，字段级 quality flag 是合并前的必要步骤。

---

## 3. 跨 release id 稳定性（s12f → run14）

### 3.1 四域稳定性总表（自然键匹配、唯一对）

| 域/键 | 匹配键数 | 唯一配对 | id 相同 | id 变化 | 变化率 | 歧义键 |
|---|---|---|---|---|---|---|
| company 精确名 | 1,733 | 1,733 | **0** | 1,733 | **100%** | 0 |
| company T2 core | 1,731 | 1,722 | 0 | 1,722 | 100% | 9 |
| professor 姓名 | 1,409 | 1,391 | 0 | 1,391 | 100% | 18 |
| professor 姓名+机构 | 1,418 | 1,409 | 0 | 1,409 | 100% | 9 |
| paper DOI | 494 | 494 | 0 | 494 | 100% | 0 |
| paper 标题归一 | 557 | 551 | 0 | 551 | 100% | 6 |
| patent 专利号 | 1,931 | 1,931 | 0 | 1,931 | 100% | 0 |

覆盖率侧：s12f 的 1,737/1,428/563/1,931 篇文档中，**99.8% 公司名、98.7% 教授名、100% 论文标题、100% 专利号**在 run14 仍可找到（4 个公司名、19 个教授名在 run14 消失）；run14 相对 s12f 新增公司 5,356 档（4.1×）、论文 23,963 档、专利 9,573 档——规模扩张与 id 换血同时发生。

### 3.2 内容变动 vs id 变动（company 精确名 1,733 对）

| 16 字段快照 | id 相同 | id 变化 |
|---|---|---|
| 快照一致 | 0 | **575** |
| 快照不一致 | 0 | **1,158** |

→ **575 对（33%）"内容没变也换 id"**，是纯重铸损耗；其余 1,158 对伴随真实内容漂移。**没有任何一对保住 id**。

### 3.3 机制（代码定位）

`apps/miroflow-agent/src/data_agents/canonical_v2/canonical_identity_resolution.py:2219-2237`：

```python
def _canonical_identity_id(release_id, entity_type, source_identity_ids, *, generation_key):
    digest = _content_sha256({
        "release_id": release_id,
        "entity_type": entity_type,
        "source_identity_ids": sorted(source_identity_ids),
        "generation_key": generation_key,
    })
    return f"{entity_type}-c-{digest[:24]}"
```

三个输入里 **`release_id` 每代必变**；`source_identity_ids`/`generation_key` 随重规范化漂移。铸造哈希 → 换 release 即换 id。且两次构建之间没有持久身份状态：每个 release 从零解析，识别历史（identity decision 链）在代际间不承接身份号本身（决定 id 被重铸）。形式上 id 是"内容寻址 + 代际作用域"，语义上被下游当成"持久主键"用——**契约错配**。

### 3.4 样本 20 家（canonical_object_id 对照）

| 关键词 | s12f 名称 | s12f id | run14 名称 | run14 id | id 变化 |
|---|---|---|---|---|---|
| 优必选 | 深圳市优必选科技股份有限公司 | `company-c-64e631c0e0cd9e91d032d209` | 同名 | `company-c-b2aac54891e3fce8c98612d8` | 变 |
| 一博 | 深圳市一博科技股份有限公司 | `company-c-22a5896dab395032a70f475b` | 同名 | `company-c-8f303a46ca0b58ad9b92f2dc` | 变 |
| 普渡 | 深圳市普渡科技有限公司 | `company-c-c7447b81221857b0e6d3279c` | 同名 | `company-c-72b2ec528908ac199ee1dbc7` | 变（run14 另有 2 档） |
| 嘉立创 | 深圳嘉立创科技集团股份有限公司 | `company-c-c9f7ac38017325ec6747fc71` | 同名 | `company-c-2ccb5dd970b63ba26f6a3a47` | 变 |
| 深南电路 | 深南电路股份有限公司 | `company-c-217aec96f04d2c2a33181b17` | 同名 | `company-c-0c087bba8369e127acde08a2` | 变 |
| 云迹 | 云迹科技股份有限公司 | `company-c-d7c54a5dc6da0ade14005f36` | 同名 | `company-c-46be538b64accf560e186de3` | 变 |
| 九号 | 九号机器人 | `company-c-43df421eadbcedfa730a1b18` | 同名 | `company-c-fd3242c863d6bb6b3fa59213` | 变 |
| 越疆 | 深圳市越疆科技股份有限公司 | `company-c-5924fd2757a24f885d95f010` | 同名 | `company-c-7f76af831850602aeb8bc005` | 变 |
| 逐际动力 | 深圳逐际动力科技有限公司 | `company-c-dbc8d3e4fa9d06230f8d87f7` | 同名 | `company-c-fcdce12325469d4d7e022e6c` | 变 |
| 优地 | 深圳优地智能有限公司 | `company-c-0fec79c3bac76a220fe0a6e9` | 同名 | `company-c-ce16d7182d134cacca7061d7` | 变 |
| 大疆 | 深圳市大疆创新科技有限公司 | `company-c-c25587293bccecc5cdee9094` | 同名 | `company-c-0e423959d58e241f23c487ff` | 变（run14 增至 3 档*） |
| 海柔 | 深圳市海柔创新科技有限公司 | `company-c-a34c0c6380643b393a795938` | 同名 | `company-c-1872f7750afe13f38897e39d` | 变（run14 增至 3 档*） |
| 速腾聚创 | 深圳市速腾聚创科技有限公司 | `company-c-31ad6d19744b2f101c9cb53f` | 同名 | `company-c-c0148d5b0736647a3fe5be6f` | 变 |
| 迈瑞 | 深圳迈瑞生物医疗电子股份有限公司 | `company-c-2887b8f58525cd5f13159c9b` | 同名 | `company-c-9f581f4e28040bfad9cafdeb` | 变 |
| 奥比中光 | 奥比中光科技集团股份有限公司 | `company-c-54c39afbb068418cac50042a` | 同名 | `company-c-a26bd746b8854ca669ffba2c` | 变 |
| 众擎 | 深圳市众擎机器人科技有限公司 | `company-c-a2da803e704a06bd442b719d` | 同名 | `company-c-d4d6affe1c22344b1df6eec6` | 变 |
| 智平方 | 智平方（深圳）科技有限公司 | `company-c-36d6be622580c294ab285de3` | 同名 | `company-c-424090d101c433b80efde9de` | 变 |
| 元化智能 | 元化智能科技（深圳）有限公司 | `company-c-2025470a0285534bce1fd7b6` | 同名 | `company-c-9c8337c13ed347c19e4e9902` | 变 |
| 华大基因 | **无** | — | 深圳华大基因科技服务有限公司 / 深圳华大基因股份有限公司 | `company-c-54dd29d8cd0f9d1ad64eb890` / `company-c-fb9a5be209e4a257f39f08af` | 新增 2 档 |
| 拓竹 | **无** | — | **无** | — | 两侧皆无 |

\* 大疆/海柔行"增至 3 档"指关键词命中档数：另 2 档为词面/品牌近邻命中（大疆百旺、鑫大疆智能；前海柔云、海柔智能），均非同一实体的名称变体档。

### 3.5 专利 → 公司绑定重指与引用完整性（`applicants[].canonical_company_id`）

| 指标 | s12f | run14 |
|---|---|---|
| 申请人条目（带 company id） | 1,704 | **7,650** |
| 被引用公司 id 数 | 697 | 963 |
| dangling id（包内解析不到） | **0** | **0** |
| 单公司最多绑定 | 杉川机器人 72 | 优必选 **450** |

锚点复验（与 C2 一致）：**优必选 58 → 450**（按 id 与按名计数一致）；普渡：深圳有限 0 → **128**、成都 4 → **27**、新增股份档 0（合计按名 155）。另见同品牌绑定分裂实例：云鲸智能创新（深圳）135 + 云鲸智能（深圳）135（同一品牌两档各拿一半）。

**判读**：包内引用完整性是好的（每代都自洽、无悬空），坏的是**代际间的引用连续性**——绑定、答案引用、对话记忆里的 id 一旦越过 release 边界就失效（优必选 58→450 即此现象的绑定侧投影）。

### 3.6 模式总结（5 条）

1. **代际重铸是确定性行为**：id 铸造含 release_id ⇒ 换发布必换 id（四域 100%，含 575 对内容零变化）。
2. **重规范化放大效应**：来源集合/内容漂移让 67% 的 company 档连快照都变了；id 变化与内容变化同向叠加。
3. **自然键比 id 稳**：名称/DOI/专利号的跨代命中率 98.7%–100%，而 id 命中率 0%——**长寿命引用应锚定自然键或稳定号，而不是当前 id**。
4. **碎片化随规模放大**：同一品牌多档在 run14 更多（大疆、海柔、普渡、华大），绑定按档分裂（云鲸 135+135、普渡 128+27）。
5. **现契约的隐性假设被证伪**："canonical id 是稳定的"这一下游假设，在任何一次重规范化后即失效；不修复则每代都要对全部下游引用做一次重指/失效处理。

---

## 4. 合并规则提案（草案）

> 定位：这是"两线契约家规 ADR"的直接输入（草案，非实现）。§4.1–4.2 是 identity 合并规则，§4.3 是稳定 id 协议骨架。

### 4.1 主档（head）选择依据

按证据排序（可配置）：

1. **来源族优先级**：`company-p4`（完备度 11.5/15、地址/成立/法代/官网齐全）> `COMP-legacy`（7.15，短名/别名与旧摘要价值）> `company-backfill`（2.0，摘要 100% 占位，仅作补充）。
2. **字段完备度**：head 逐字段可换（不是"整档胜出"）——见 §4.2。
3. **时间**：`last_updated` 全体被重盖为构建戳（p4/backfill 100% 2026-09-07；legacy 99% 被重盖，仅 14 档保留 2026-04-16），**当前不可作为新鲜度依据**；需修复时间戳语义（写入源观测时间）后才可参与排序。
4. **质量标志**：`quality_status` 全库恒 `partial`，不可用；建议引入字段级 `quality_tier`/`source_reliability`（数据线已有 `_quality_tier` 概念，pack 内未见）。
5. **确定性 tie-break**：来源族 > 字段完备度 > 字符序 cid（保证可复现）。

### 4.2 字段合并策略（谁覆盖谁）

| 字段组 | 建议策略 |
|---|---|
| 规范名/法定名 | 取"最新法律形态"档（有限→股份的后者；按 source 的 registration 证据而非文档时间），旧名全部进 aliases |
| normalized_name | 由合并器统一重算（短名派生规则，如"普渡科技"），不再信任源字段（现 72/72 冲突） |
| credit_code | **全空**：任何合并都不得以它为锚；列入数据回填清单（最高优先） |
| registered_address / legal_representative / founded_at / website | 以 p4 档为主；与 legacy/backfill 冲突时**记冲突登记**不静默覆盖；website 冲突常见双官网（pudurobotics vs pudutech），建议多值保留 |
| industry / industry_tags / tech_tags | **不做单值覆盖**：保留来源标记的多值集合 + 统一映射表（机器人 vs 物流运输 是分类体系问题，属产品决策）；展示层选"主标签" |
| profile_summary / technology_route_summary | 质量优先：占位符（`Not supplied…`）永远不覆盖真值；"产品清单冒充简介"的档位降权（可用 product_description 高相似度检测）；正文简介 > 生成式 > 清单 |
| product_description / team_description | 按 p4 > backfill 取最长真值；与 profile_summary 的重复要去重（现常同值） |
| aliases | 全并集（含旧名、英文名、短名） |
| 专利绑定 | 合并实体后**绑定取并集**；读侧按合并组解析（如 普渡 128+27=155） |

**合并判定（evidence-gated，三档置信）**：

- **自动合并**：核心名相等（T2 或"实体更名"证据）且强证据不互斥（address/法代/成立时间/官网域 至少一项相等或单边缺失）。
- **人工复核队列**：仅品牌核（T3）相同。
- **禁止合并**：强证据互斥（本轮 30/72，42%）；红线样本：华芯、海思、中智科创、顺丰科技 vs 顺丰控股。

### 4.3 跨 release 稳定 id 协议草案（ADR 骨架）

**问题陈述**：`canonical_identity_id` 现为 `sha256(release_id, type, source_ids, generation_key)[:24]` 的内容寻址 id，代际 100% 重铸；而下游（serving 引用/答案、关系产物、对话记忆、缓存、评测夹具）把它当持久主键用。两线需要一份**显式契约**，把"版本 id"与"稳定身份"分离。

**协议骨架（推荐：ledger + 版本 id 双层）**

1. **stable_uid**：实体级稳定号，一次分配、永不重铸（opaque，建议 `company-uid-<ULID>`）。由 **identity ledger**（起步用 SQLite 表即可）唯一持有；分配发生在实体首次进入治理域时，与内容解耦。
2. **canonical_identity_id 保留**：继续做"当代版本 id"（内容寻址、审计可复现、字段 lineage 逐字节溯源不变）。
3. **Ledger 内容**：`stable_uid ↔ (release_id, canonical_identity_id)` 全代映射 + 事件日志（merge / split / rename，含 decision id、生效 release、survivor 规则）。历史 canonical id 一律保留为 alias，可反查。
4. **引用面改造**：所有跨 release 存活的产物（关系边、专利申请人绑定、对话记忆、缓存、评测夹具、看板）**只写 stable_uid**；pack 构建时由 ledger join 出当代 canonical id 写入 lookup 文档（新增 `stable_uid` 字段），读侧对内解析当代 id、对外输出 stable_uid。
5. **家规条文（可直接进 ADR）**：
   - R1（引用面）：跨 release 存活的产物禁止存 `canonical_identity_id`，只允许 stable_uid 或自然键。
   - R2（构建面）：pack 必须携带 stable_uid 映射；所有绑定产物必须可 join 回当代 canonical id，dangling 必须为 0。
   - R3（变更面）：identity 合并/拆分必须产生 ledger 事件（含 decision id），禁止静默重铸。
   - R4（验证面）：相邻 release 的 stable_uid 保持率进入发布门（KPI 见 §4.5）。

**备选（interim，建议作为过渡不替代目标）**：仅把 `release_id` 从铸造哈希中移除（一行改动+重铸一版）。能消除"仅因代际铸造"的换血；按本轮数据其**最小受益面 575/1,733（33%）**（且前提是 source 集合与 generation_key 也不变）。代价：一次全量重铸 + 关系重指（本来每代都发生）+ 打破"id 是 release 作用域"的隐性约定；不解决跨代引用承接问题本体。**目标方案仍应是 ledger**——它正是当前缺失的"持久身份状态"。

### 4.4 代价与开放问题

**代价（ledger 方案）**

- **新增持久状态**：备份/回滚/幂等校验义务；ledger 损坏 = 全库身份不可解析（高 blast radius）⇒ 只增日志 + checksum + 双备份。
- **公开契约变更**：lookup schema（+`stable_uid`）、关系/绑定产物、serving 读路径、评测夹具都要动 ⇒ 需 OpenSpec change + 迁移/回滚方案；兼容期双写→双读→切换，约两个 release 周期。
- **历史映射**：未建 ledger 的历史代只能"尽力映射"（按自然键回填），不保证 100%。
- **人工复核成本**：宽口径候选里 42% 强证据互斥，需裁决队列；自动合并误并的负样本（华芯类）必须为 0。
- **复杂度**：merge/split 的 survivor 规则、别名历史、事件写入方（构建器）都要定死。

**开放问题（需产品/架构决策）**

1. 论文"预印本 vs 期刊版"是否同一实体？（6 对全属此类，DOI 各不相同）
2. professor 同名同机构（9 簇）是否同人？建议人工确认后写死判定规则。
3. 行业分类统一词表（机器人 vs 物流运输）归产品域。
4. stable_uid 编号策略（ULID vs 顺号）与 ledger 归属（数据线构建器 vs 独立治理服务）。
5. 碎片化实体的"合并后展示名"规则（法定名 vs 品牌短名）。

### 4.5 验收指标建议（供 ADR/change 引用）

| # | 指标 | 当前基线 | 目标 |
|---|---|---|---|
| 1 | stable_uid 跨代保持率（排除真 merge/split） | **0%**（id 全换） | 100% |
| 2 | 绑定 dangling（包内可解析） | 0（两代均 0） | 保持 0 |
| 3 | 跨代引用解析率（对话/缓存中旧引用在新代可解析） | 不可解析 | 100%（ledger 期内） |
| 4 | 合并实体字段冲突的 resolution 覆盖率（自动或登记） | 无机制 | 100%，抽检 ≥95% 合格 |
| 5 | 强证据互斥簇的自动合并数（负样本 30 簇） | 无机制 | 0 |

---

## 附：产物清单（均在 `g-series/` 下）

| 文件 | 用途 |
|---|---|
| `g2-identity-audit.md` | 本文（唯一交付文档） |
| `g2_identity_audit.py` / `g2_cross_release.py` / `g2_lib.py` | §1–§2、§3 主脚本 + 共享只读 loader |
| `g2_probe_mergeability.py` / `g2_probe_recency.py` / `g2_probe_denominators.py` / `g2_probe_prof.py` / `g2_probe_paper.py` / `g2_probe_fields.py` / `g2_probe_docs.py` / `g2_probe_schema.py` / `g2_view.py` | 证据探针与查看器（全部只读） |
| `out/g2-run14-identity-audit.json` | §1–§2 机器可读结果（含全部 72 簇成员、冲突样例、Pudu 样本） |
| `out/g2-cross-release.json` | §3 机器可读结果（稳定性、样本、绑定、锚点） |
| `out/g2-clusters.txt` / `g2-examples.txt` / `g2-prof*.txt` / `g2-paper.txt` / `g2-mergeability.txt` / `g2-audit.log` / `g2-cross-release.log` | 运行日志与人读视图 |

（本审计未改任何代码、未动 serving worktree、未 git commit。）
