# 教授域数据质量审计（Canonical V2 candidate r8, track: professor）

- 审计时间: 2026-08-01；全部只读 SELECT，未改动任何 DB/索引/进程。
- 数据源: 容器 `canonical-v2-s12c-pg-20260726-r8` / DB `miroflow_candidate_s12c_20260726_r8`，批次 `s12a-released-objects-full-v1`；lookup 索引 `r8/index/lookup.sqlite3`。
- "882" = landing 1439 条教授 payload 减去 `knowledge.source_identity` 已收录 557 条（实测差集恰为 882，与 s12e gate 复核一致）。已入库基数: canonical_identity / current_projection = 554（557 源身份被身份解析合并掉 3 条）。

## 1. 882 条放行候选分诊

### citation_count 分布（回填价值严重偏斜）

| 桶 | 条数 |
| --- | ---: |
| null（无指标） | 861 (97.6%) |
| 0 | 5 |
| 1–9 | 2 |
| 100–499 | 1 |
| 500–999 | 3 |
| 1000–4999 | 8 |
| ≥5000 | 2 |

- 仅 21 条有 citation_count（同样有 h_index）；有值者 p50=947, p90=4242, max=14746。187/882 有 paper_count。
- **高价值 Top-14（cc≥466，回填优先队列头部）**: 周垚 14746（南科大, no_dept）/ 唐仙 5569（SIGS, no_dept）/ 姚勇 4242（哈工大深圳, no_email+title）/ Parvej Alam 4236（港中大深圳, no_email）/ 黄建华 3201（港中大深圳）/ 田佳峻 2917（哈工大深圳）/ 张灿荣 1913（SIGS, no_dept）/ 孔庆磊 1245 / 高林 1205 / 冯建设 1153（中大深圳）/ 徐小川 947 / 王凯旭 909 / 吴日 845（南科大）/ 朱时裴 466。
- **指标贫但论文多的补漏**: 金欣 paper_count=170 无 cc（SIGS）；王学谦 PROF-132D3CC74120 paper_count=120 但 cc=1（指标对不自洽，建议一并复核）。

### 机构分布（882）

| 机构 | 条数 | 占比 | 已入库 554 占比（对比） |
| --- | ---: | ---: | ---: |
| 哈尔滨工业大学（深圳） | 651 | 73.8% | 1.6% (9 条) |
| 清华大学深圳国际研究生院 (SIGS) | 158 | 17.9% | 15.2% (84 条) |
| 深圳技术大学 | 21 | 2.4% | 23.6% |
| 香港中文大学（深圳） | 20 | 2.3% | 29.1% |
| 深圳理工大学 | 16 | 1.8% | 13.4% |
| 中山大学（深圳） | 9 | 1.0% | 17.0% |
| 南方科技大学 | 4 | 0.5% | 0.2% |
| 深圳大学 | 3 | 0.3% | 0% |

- **SIGS 占比 17.9%**；放行后域内机构结构将剧烈翻转（哈工大深圳 9→660 条），下游任何按机构分布校准的检索/评测基线需重估。

## 2. name+institution 碰撞清单（双份 canonical identity 风险）

### 与已入库 554 碰撞: 6 对

| 新记录（882 侧） | 已入库 identity | 判定线索 |
| --- | --- | --- |
| 张雅鸥 PROF-43A86E6DA926 (SIGS, 无 dept) | professor-c-643ff1...（分子与细胞生物学） | email+homepage 完全相同 → 确定同一人，应合并 |
| 罗智泉 PROF-2CE8D5F39807（人工智能学院） | professor-c-4f1007...（理工学院， myweb.cuhk.edu.cn/luozhiquan） | 同人跨院系主页；已入库 email 还是脏数据（见 §4） |
| 蔡小强 PROF-6C2F529C2B03（数据科学学院） | professor-c-f0ce9e...（理工学院） | 同人不同院系页 |
| 朱宝亭 PROF-71DC4C85522E（医学院） | professor-c-8a7270...（理工学院） | 同人不同院系页 |
| 黄宪达 PROF-17586612024F（医学院） | professor-c-5d05a0...（理工学院） | 同人不同院系页 |
| 赵阳 PROF-84D967588160（医工学院, /yangz） | professor-c-631716...（空天科技学院, /yang_zhao） | 常见名+不同学院+不同主页 → 可能不同人，需人工 |

### 882 内部重名组: 5 组 11 条

- 陈斌×3（哈工大深圳）: 三个不同主页（/chenbin, /chenbin2020, /BinChen）+三个不同学院 → **几乎确定是 3 个不同人**；若身份键仅用 name+institution 将被错误塌缩成 1 人。
- 王威×2（哈工大深圳， /wangwei3 vs /wangweihitsz，不同学院）→ 疑似不同人。
- 刘清侠×2（深圳技术大学， 新材料学院 vs 人工智能学院，均"讲席教授"）→ 疑似同人双聘。
- "师资列表"×2（南科大）、"教育经历"×2（SIGS）→ 垃圾名碰撞（见 §4），不是真人。
- 量化: 不处理则最坏新增 6 个重复 identity（对已入库）+ 误并 3–5 个真人（882 内部）。

## 3. 缺失字段组合模式（882）

| 信号 | 条数 | 占比 |
| --- | ---: | ---: |
| missing_email | 680 | 77.1% |
| missing_title | 576 | 65.3% |
| missing_department | 160 | 18.1% |
| missing_homepage / missing_profile_summary | 0 / 0 | 0% |

- 互斥组合: email∩title 528（含三项全缺 2）/ 仅缺 email 150 / 仅缺 title 46 / 仅缺 dept 154 / email∩dept 2 / title∩dept 2。**缺 email+title 交集 = 528 (59.9%)**，几乎全部来自哈工大深圳个人主页抓取（主页无邮箱/职称结构）。
- **department 缺失的机构集中度极高**: SIGS 157/158 (99.4%) + 南科大 3/4 = 全部 160 条；哈工大深圳 0/651。即 dept 缺口是 SIGS 站点结构（页面无院系字段）的单点 artifact，可用"机构=SIGS"确定性规则批量标注或定向重抓（王学谦即此类）。

## 4. 抽样 10 条 payload 数据卫生

- 8 条随机样（md5 序: 郑博/白玉超/李曜/赵琛/郑为杰/张成萍/赵飞/曹顺翔）: 字段对齐、中文摘要连贯、homepage 域与机构一致；全量 882 条 0 乱码（U+FFFD=0、Latin-1 mojibake=0）、core_facts/summary_fields 结构 100% 齐全。
- 时间戳合理: last_updated ∈ [2026-04-17, 2026-05-06]；1884 条 evidence fetched_at 同窗口，无未来时间、无空值。
- **严重: 6 条"栏目名当人名"记录**（可通过新 gate）: "师资介绍"（中大深圳）、"师资列表"×2（南科大, PROF-D03137EE5CCA/FB5B20CD886F）、"教育经历"×2（SIGS, PROF-32ED0A87708C/2B3826A1C95F）、"相关教师"（哈工大深圳, PROF-714553B67B44）。其中 PROF-32ED0A87708C 其余字段实属真人（email xdchen@sz.tsinghua.edu.cn、主页 .../Xiaodong CHEN（cxd）/）→ 名字段被页面栏目污染的抽取 bug；若不拦截，回答层会直接展示"教育经历教授"。
- **33/202 (16.3%) 邮箱为反爬倒置串**（如 `moc.liamg@88gnat.nilnuhs`、`nc.ude.tih@...`），做身份键/联系方式前必须反转解码。
- 语言混杂: 16 条纯拉丁名（Parvej Alam 等）、2 条中英混排（"Jong Mui Choo（杨美珠）"、"陈恺哲 Kai-Jher Tan"，可拆出 zh/en 双名）。
- 附带发现（已入库 554 的存量脏数据）: 25 条 email 是整页文本拼接（如 `emailchenzhongxin@cuhk.edu.cnofficeaddressphone...biographydr....`）、8 条倒置邮箱；罗智泉、赵阳现存 email 均不可用。
- 检索相关空字段: 353/882 (40.0%) research_directions 为空、669 (75.9%) 无教育经历、仅 21 (2.4%) 有 h_index → 语义召回对这批记录将主要依赖 profile_summary 文本。

## 5. canonical_name_en / aliases 空值率与检索影响

- 882 payload: canonical_name_en **0/882 (100% 空)**、aliases **0/882 (100% 空)**（连 canonical_name_zh 键也不存在，名字仅在 `name`）。
- 已入库 554 projection: canonical_name_en **0/554**、aliases **0/554**、canonical_name_zh 554/554。lookup 索引 554 份教授 envelope 同样无英文名/别名面。
- 影响: (a) 英文名查询（"Zhi-Quan Luo"、"Xiaoqiang Cai"）无法命中 exact-lookup 的中文名教授；(b) 882 中 16 条拉丁名记录只是"碰巧"可英文检索；(c) 身份解析缺少 en/zh 别名键，加剧 §2 碰撞风险。建议放行管线派生 canonical_name_en（主页 slug/邮箱本地部分/拼音）并把中英混排名拆成 zh+en+alias。

## 优先级建议

1. **P0 放行前拦截脏名 + 解码倒置邮箱**: 加人名质量规则（栏目词黑名单: 师资列表/师资介绍/教育经历/相关教师/相关教师…）隔离 6 条污染记录并修复 PROF-32ED0A87708C 类抽取；对 33 条倒置邮箱做确定性反转。
2. **P0 身份解析不得裸用 name+institution**: 预登记 6 对已入库碰撞（张雅鸥凭 email+homepage 直接合并；罗智泉/蔡小强/朱宝亭/黄宪达/赵阳人工复核）与 882 内部 陈斌×3/王威×2/刘清侠×2；merge 键必须含 homepage/email，否则最坏 6 个重复 identity + 3–5 个真人被误并。
3. **P1 回填队列与英文名面**: 以 Top-14（cc≥466）+ 金欣/王学谦（论文多、指标贫/不自洽）为回填首波；同步补 canonical_name_en/aliases（当前双侧 100% 空），否则英文检索与身份键持续残缺。
