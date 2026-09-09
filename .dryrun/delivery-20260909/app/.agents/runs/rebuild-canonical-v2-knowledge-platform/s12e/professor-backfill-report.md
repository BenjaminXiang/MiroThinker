# 教授回填批次报告（s12e-professor-backfill-v1）

- 时间: 2026-08-01；执行: Task 7c（`docs/superpowers/plans/2026-07-31-llm-wide-recall.md` Task 7 Step 1）。
- 目标库: 容器 `canonical-v2-s12c-pg-20260726-r8` / DB `miroflow_candidate_s12c_20260726_r8`，批次 `s12e-professor-backfill-v1`。
- 写入方式: **append-only**（仅 INSERT，未 UPDATE/DELETE 任何既有行；landing 表有拒改触发器兜底）。
- 脚本: `professor_backfill.py`（`--collect` 采集 → `--review` 活人复核+实时断言 → 默认 dry-run → `--apply` → `--verify`）。
- 覆盖: 审计优先级队列 Top-14（cc≥466）+ 金欣 + 王学谦 = 16 人（hard-cap 20，未超）。

## 1. 总量

| 指标 | dry-run | applied |
| --- | ---: | ---: |
| 记录数 | 16 | 16 |
| department | 6 | 6 |
| email | 9 | 9 |
| title | 6 | 6 |
| canonical_name_en | 16 | 16 |
| aliases | 15 | 15 |

- dry-run 与 applied 完全一致；artifact_id / parse_run_id 与 dry-run 预览逐字符相同（内容寻址、与时间无关）:
  - `artifact:sha256:e37e8c2d2b348b4593fa884f3621ae427e5aa71662fb4c835f992aaa75d9d2af`
  - `parse-run:sha256:7ddbc92697710801b6ad0578b47242a81d427ef279a4793828db3ef5cde9d03e`
- 批次文件: `professor_backfill_batch.jsonl`（16 行, 33352 bytes; 同步 staging 至 `/var/tmp/mirothinker-canonical-v2-s12e/staging/professor_backfill_s12e_v1.jsonl`）。
- 每个回填值均带 source assertion（source_url + observed_at + evidence_quote + method）；`--verify` 实测缺 assertion 的字段数 = 0。

## 2. 逐人明细

### 回填成功字段（21 个核心字段 + 16 英文名 + 15 别名）

| 人 | 字段 | 值 | 来源（method） |
| --- | --- | --- | --- |
| 周垚 PROF-F7D43B28799E | department | 高等教育研究中心 | cher.sustech.edu.cn/faculty/detail/id/277.html（official_page，引文: “周垚，女，1993年生…南方科技大学高等教育研究中心研究助理教授”） |
| 唐仙 PROF-814BDB064B97 | department | 数据与信息研究院 | SIGS 师资检索后端（official_api，exField4=“信息科学与技术学部,数据与信息研究院”） |
| 姚勇 PROF-F65FAFD07ECB | email | yaoyong@hit.edu.cn | homepage.hit.edu.cn/yaoyong（official_page_email_deobfuscated，页面反爬倒置串 `nc.ude.tih@gnoyoay` 反转解码） |
| 姚勇 | title | 教授 | cist.hitsz.edu.cn 集成电路科学与工程学科师资列表（official_page，教授组含“姚勇”） |
| Parvej Alam PROF-A4A3D3B0C942 | email | alamparvej@cuhk.edu.cn | alam-parvej.github.io（personal_homepage_linked_from_official；官方 SSE 页“个人网站”链向该主页，主页署名 CUHK-Shenzhen） |
| 黄建华 PROF-1EC0B2448E6D | email | jhuang@cuhk.edu.cn | sai.cuhk.edu.cn/teacher/108（official_page，页面“邮箱 jhuang@cuhk.edu.cn”） |
| 田佳峻 PROF-8BCB9CE81A01 | email | tianjiajun@hit.edu.cn | homepage.hit.edu.cn/tianjiajun（deobfuscated，`nc.ude.tih@nujaijnait`） |
| 田佳峻 | title | 教授 | cist.hitsz.edu.cn 集成电路科学与工程学科列表（official_page） |
| 张灿荣 PROF-19535075873E | department | 数据与信息研究院 | SIGS 师资检索后端（official_api，exField4=“物流与交通学部,数据与信息研究院”） |
| 孔庆磊 PROF-77D468AF93F5 | email | kongqinglei@hit.edu.cn | homepage.hit.edu.cn/kongqinglei（deobfuscated，`nc.ude.tih@ielgniqgnok`） |
| 高林 PROF-70F168547DAE | email | gaol@hit.edu.cn | homepage.hit.edu.cn/gaolin（deobfuscated，`nc.ude.tih@loag`） |
| 高林 | title | 教授 | cist.hitsz.edu.cn 信息与通信工程学科列表（official_page，教授组首位“高林”） |
| 冯建设 PROF-FF636C8A09C3 | email | fengjsh7@mail.sysu.edu.cn | am.sysu.edu.cn/teacher（official_page，专任教师列表“冯建设 副教授…电子邮箱：fengjsh7@mail.sysu.edu.cn”） |
| 徐小川 PROF-A732D59BBDB0 | email | xuxiaochuan@hit.edu.cn | homepage.hit.edu.cn/xuxiaochuan（deobfuscated，`nc.ude.tih@nauhcoaixux`） |
| 徐小川 | title | 教授 | cist.hitsz.edu.cn 集成电路科学与工程学科列表（official_page） |
| 王凯旭 PROF-C91EBBAC3D23 | title | 副教授 | cist.hitsz.edu.cn 信息与通信工程学科列表（official_page，副教授组含“王凯旭”） |
| 吴日 PROF-ABBDE6D18E0E | department | 理学院化学系（与先进光源科学中心双聘） | sustech.edu.cn/zh/faculties/riwu.html（official_page，“吴日博士，南方科技大学理学院先进光源科学中心与化学系双聘副教授”） |
| 吴日 | title | 副教授 | 同上页（“吴日 副教授 wuri@sustech.edu.cn”；页内载 2026-06 晋升副教授 tenure-track） |
| 朱时裴 PROF-E0221A651BF9 | email | zhushipei@hit.edu.cn | homepage.hit.edu.cn/zhushipei（deobfuscated，`nc.ude.tih@iepihsuhz`） |
| 金欣 PROF-013E2C1D4602 | department | 数据与信息研究院 | SIGS 师资检索后端（official_api，exField4=“信息科学与技术学部,数据与信息研究院”） |
| 王学谦 PROF-132D3CC74120 | department | 数据与信息研究院 | sigs.tsinghua.edu.cn/2026/0714/c7687a292200/page.htm（official_page，“王学谦，清华大学深圳国际研究生院教授、博士生导师、数据与信息研究院党总支书记”） |

另: 全体 16 人补 `canonical_name_en`（western-order，如 “Xueqian Wang”），15 人补 `aliases`（family-first 变体，如 “Wang Xueqian”）；Parvej Alam 原名即拉丁文（method=identity），不产生别名。派生方法标注为 `pinyin`（pypinyin 0.55.0, 项目既有依赖，未新增）。

### 留占位符的字段（按“无确信来源则不动”原则）

| 人 | 字段 | 原因 |
| --- | --- | --- |
| 孔庆磊 | title | 官方渠道（homepage.hit.edu.cn 个人页无职称结构、空天科技学院无公开师资职称列表、搜索仅命中同名医生/教师）未找到任何可引用职称来源 |
| 王凯旭 | email | 个人主页（homepage.hit.edu.cn/WangKaiXu）邮箱栏为空；faculty.hitsz.edu.cn/wangkaixu 显示“教师主页未开通”；任何官方页均无邮箱，不猜测 |

### 跳过的人

无。16 人全部产出记录（至少含 canonical_name_en + 一个核心字段）。

## 3. 王学谦专项核对（对照其 SIGS 主页）

- department: 回填 **数据与信息研究院**。双源互证: (a) SIGS 官方新闻页（2026-07-14, c7687a292200）明写“数据与信息研究院党总支书记”；(b) SIGS 师资检索后端 exField4=“信息科学与技术学部,数据与信息研究院”。
- title: 记录已有“教授、博士生导师”，与主页（wxq/main.htm “教授，博士生导师”）及新闻页一致，**不重复回填**。
- research_directions: 记录已有 7 条（LPV 鲁棒故障检测、空间机器人等），与主页“研究领域”一致，**不重复回填**。
- 附带发现（不在本批次范围）: 审计指出其指标不自洽（paper_count=120 但 citation_count=1、h_index=1）；新闻页载“发表学术论文300余篇、授权发明专利100余项、获国家科技进步奖特等奖1项、国家技术发明奖二等奖1项”，佐证 cc=1 明显失真。指标修正属于 metrics 回填范畴，**本批次未触碰**，建议列入后续任务。

## 4. 验证 SELECT 输出（apply 后实跑）

```
[verify] source_record: ('s12e-professor-backfill-v1', 16, 'parsed')
[verify] ingest_run: ('landing:s12e-professor-backfill-20260801:staging/professor_backfill_s12e_v1.jsonl', 'accepted', 16, 33352)
[verify] fields missing source assertion: 0
```

```
 record_ordinal |    name     |        pid        |                   fields
----------------+-------------+-------------------+--------------------------------------------
              0 | 周垚        | PROF-F7D43B28799E | aliases,canonical_name_en,department
              1 | 唐仙        | PROF-814BDB064B97 | aliases,canonical_name_en,department
              2 | 姚勇        | PROF-F65FAFD07ECB | aliases,canonical_name_en,email,title
              3 | Parvej Alam | PROF-A4A3D3B0C942 | canonical_name_en,email
              4 | 黄建华      | PROF-1EC0B2448E6D | aliases,canonical_name_en,email
              5 | 田佳峻      | PROF-8BCB9CE81A01 | aliases,canonical_name_en,email,title
              6 | 张灿荣      | PROF-19535075873E | aliases,canonical_name_en,department
              7 | 孔庆磊      | PROF-77D468AF93F5 | aliases,canonical_name_en,email
              8 | 高林        | PROF-70F168547DAE | aliases,canonical_name_en,email,title
              9 | 冯建设      | PROF-FF636C8A09C3 | aliases,canonical_name_en,email
             10 | 徐小川      | PROF-A732D59BBDB0 | aliases,canonical_name_en,email,title
             11 | 王凯旭      | PROF-C91EBBAC3D23 | aliases,canonical_name_en,title
             12 | 吴日        | PROF-ABBDE6D18E0E | aliases,canonical_name_en,department,title
             13 | 朱时裴      | PROF-E0221A651BF9 | aliases,canonical_name_en,email
             14 | 金欣        | PROF-013E2C1D4602 | aliases,canonical_name_en,department
             15 | 王学谦      | PROF-132D3CC74120 | aliases,canonical_name_en,department
```

存量批次行数复核（未被动过）: s12a-released-objects-full-v1=5561, s12c-r7 各批次=8/13/1/1/2，新增 s12e-professor-backfill-v1=16。

## 5. 风险与注意事项（给 Task 7b 重建/身份解析）

1. **周垚（PROF-F7D43B28799E）身份污染**: 记录的 name/email/homepage/title 锚定的是高教研究 周垚（女，1993年生，华中科技大学管理学博士，高等教育研究中心）；但 citation_count=14746/h_index=57 与 6/7 条 research_directions（形式化方法/模型检测）属于另一位同名者。本批次仅补其 department（锚定身份所属单位），**未触碰**被污染的指标/方向；建议身份解析或指标回填轮单独处置，重建前勿将该记录当作“高被引微电子/形式化方法学者”使用。
2. **田佳峻职称证据取舍**: eie.hitsz.edu.cn 旧新闻称“田佳峻副教授”，信息学部当前师资列表（cist.hitsz.edu.cn）列为“教授”——取当前权威列表（晋升解释旧闻），引文即列表原文。
3. **姚勇/徐小川/田佳峻的 department 未回填**（记录本不缺）：注意学部现行列示他们在“集成电路科学与工程学科”，与存量 department 值“信息学部/信息科学与技术学院（深圳）”存在机构沿革差异，留待 7b/身份解析决定，不在本批次职责内。
4. **Parvej Alam 双记录**: 库内另有 SIGS 记录 PROF-9F7B367BD507（alamparvej@sz.tsinghua.edu.cn）；本批次只回填 CUHK 记录（PROF-A4A3D3B0C942，cc=4236）。疑似同人调动，属审计 §2 已列的碰撞类问题，不在本批次合并。
5. **SIGS department 语义**: exField4 为“旧学部名,新研究院名”并列；回填取新研究院名（数据与信息研究院），与已入库 SIGS 记录（如“环境与生态研究院”）同粒度。
6. **邮箱反爬倒置**: 7 个 hit.edu.cn 邮箱均由页面倒置串确定性反转解码（method=official_page_email_deobfuscated），引文保留原始倒置串备查。
7. **cuhk.edu.cn TLS**: 该域对 Python TLS 握手拒绝（SSLV3_ALERT_HANDSHAKE_FAILURE）；脚本 `fetch_page` 内置 curl(TLS1.2+浏览器头) 回退，review 已实测通过。
8. **payload 形状**: 每条记录以 `professor_id` 主键 + `fields.<字段>.{value,source_url,observed_at,evidence_quote,method}` 自描述，供 7b 重建合并；合并逻辑（写 projection/别名键）属 Task 7b。
9. 检索引擎仅用于发现候选页；所有落库值均来自官方页/官方后端实时抓取并逐条断言（`--review` 全绿后才 apply），未使用搜索快照直接充当证据。
