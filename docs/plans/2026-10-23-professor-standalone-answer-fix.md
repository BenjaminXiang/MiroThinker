# 丁文伯类单轮问题：公司/专利答错（2026-10-23）

> 状态：**已修复并上线**（2026-10-23；客户机 `/api/health` 200，实测见 §6）。

关联 OpenSpec：`anchor-standalone-professor-relations`
关联验收：[严格验收审计](./2026-10-23-customer-site-strict-acceptance.md)

## 1. 现象

在客户 `/chat` 上单轮提问：

- “丁文伯创办的公司是哪家” → 答成 **丁文波**（武汉市千信科技）或“无公开记录”；
  没有答出公开报道中的 **深圳无界智航科技有限公司（Xspark AI，联合创始人/首席科学家）**。
- “丁文伯有哪些专利” → 答“没有查到”；只提到 **丁文博**、**丁文胜** 等相近姓名。
  但公开资料显示丁文伯拥有多项中国/美国专利（清华 SIGS 主页：“More than 10 China
  patents and 1 US patent”；清华新闻网报道“授权或公开发明专利15项”）。

同一关系在**多轮**里是正确的：先问“介绍清华的丁文伯”，再问“他参与创立了哪些企业”，
能答出深圳无界智航。说明缺陷在“单轮命名主体没有锚定”，不是关系数据完全缺失。

## 2. 根因

1. **规划器不锚定单轮人名**：`_relationship_path` 只在
   `request.displayed_entity_ids` 非空时生成关系路径；单轮请求没有 displayed 实体，
   所以“丁文伯创办的公司”只跑 company 域的 exact/structured/lexical/vector/web，
   不跑 `professor_company_role` 关系车道。
2. **Web 主体一致性没有锚**：`bound_entity_names` 为空时，
   `_apply_web_subject_consistency` 直接放行全部 web 结果；Bocha 对“丁文伯”的召回是
   丁文波/广州文伯化工等近名结果，答案被带偏。
3. **Bocha 对中文人名召回弱**：直连测试显示“丁文伯 创办的公司”返回丁文波、广州文伯；
   而 DeepSeek 搜索 API 对同一问题返回 Xspark AI/无界智航、对“丁文伯 专利”返回清华
   成果与专利页和人物专访。

## 3. 修复

- **单轮命名主体锚定**：新增 `create_local_entity_resolver`（pack lookup 精确名称匹配，
  同名多实体不锚定）；chat 层在单轮关系问句上解析出教授/企业，作为 planning request 的
  displayed anchor。关系词触发：
  - 教授 + 创办/创立/创业/公司/企业 → `professor_company_role`
  - 教授 + 论文/研究成果/… → `professor_authored_paper`
  - 企业 + 教授/老师/学者/创始人/联合创始人 → `professor_company_role`
- **DeepSeek 搜索接入 chat web lane**：新增 `DeepSeekSearchProvider`，在
  `CHAT_LLM_PROFILE=deepseek*` 且 key 可用时替代 Serper 作为第二通道
  （Serper 余额已透支）；Bocha 保留中文摘要召回。DeepSeek 结果与 Bocha 合并、
  去重、按双通道印证优先排序。
- 锚定后 `bound_entity_names=丁文伯`，现有 web 主体一致性门会丢弃丁文波/广州文伯等
  近名结果，避免把别人答成他。

## 4. 验收

- `丁文伯创办的公司是哪家`：答案出现“无界智航/Xspark”，不出现“丁文波/千信科技”作为
  丁文伯的答案；citation 能指向 Xspark/无界智航相关页面或本地企业 handle。
- `丁文伯有哪些专利`：不再把丁文博/丁文胜当作丁文伯；至少给出清华主页/成果专利页
  的公开记录，不再断言“没有专利”。
- 对照问句（如“深圳有哪些机器人公司”）行为不变。
- 单轮 professor→company 与 professor→paper 的 planner 单测通过；歧义名称不锚定。

## 5. 回滚

恢复客户机
`knowledge_serving_isolated.py.bak-namedanchor-20261023-1055`、
`serving_pack_loader.py.bak-namedanchor-20261023-1055`、
`canonical_v2_chat.py.bak-namedanchor-20261023-1055`、
`complete_candidate_runner.py.bak-namedanchor-20261023-1055`，删除
`providers/deepseek_search.py`（或保留但不注入），重启。

## 6. 实测结果（2026-10-23，客户机最终重启后）

- `丁文伯创办的公司是哪家`
  - plan：`lanes=[relationship, web]`、`domains=[company]`（教授锚定生效）；
  - relationship 车道 1 个候选，web 4 个候选（近名结果被主体一致性门过滤）；
  - 答案：深圳无界智航科技有限公司，citation `local-source-08f0d53d00dda3a8`；
  - 文本中不再出现丁文波/千信科技。
- `丁文伯有哪些专利`
  - 答案：申请号 202410612834.1《一种基于无线光通信的目标检测与识别系统和方法》，
    发明人含丁文伯；并引用清华官网“授权或公开发明专利15项”；
  - citation 全部为 `web-source-*`，不再有无关联的本地专利 handle；
  - 文本中不再出现丁文博/丁文胜。
- 回归：
  - `无界智航的创始人是谁` → 丁文伯；
  - `介绍清华的丁文伯` → 画像正常；
  - `他参与创立了哪些企业`（同一会话）→ 无界智航；
  - `深圳有哪些机器人公司`、`丁文伯教授的研究方向` → 行为不变。

边界：专利域仍没有 `professor_has_patent` 关系类型；单轮专利回答依赖 web 检索，
本地专利只在证据文本包含人名时参与。当前公开数据只能确认 1 件完整著录 +
“15 项”数量披露，不能逐项列出全部专利。

## 7. 追加：本地专利计数（2026-10-23）

- 现象：`本地知识库收录了优必选多少专利` 走 patent 域普通检索（local 各车道 0，
  web 71），答“没有统计口径”；`优必选有多少专利` 虽走 relationship，但关系车道
  候选被 plan 窗口截到 128，答案仍说“没有确切数字”。
- 根因：
  1. 关系车道的候选在 `_company_to_patent_relationship_candidates` 末尾
     `[: request.max_candidates]` 截断，真实 450 条拿不到；
  2. 包内公司名只有全称/“优必选科技”，短名“优必选”是名称索引派生形式，
     resolver 仍要求原始 display term 出现在 query，导致无法锚定公司。
- 修复：
  - 新增 `create_company_patent_counter`：按专利申请人 `canonical_company_id`
    统计完整专利投影（懒加载、按公司缓存），不受关系车道 128 截断影响；
  - chat 层新增计数快路径：`多少/几件/数量/收录/总数/共计` + `专利` 的问句，
    解析公司后直接返回“本地知识库收录 N 件”并带公司 citation；
  - resolver 改为信任名称索引的派生形式，不再要求原始名称字面出现在 query。
- 实测：
  - `本地知识库收录了优必选多少专利` → **450 件**，citation
    `local-source-5ac2eb76475da877`，structured_payload 含 450 与公司 id；
  - `优必选有多少专利` → 同样 450；
  - `优必选有哪些专利` → 仍走 relationship+web 列表（12 条本地专利 citation），
    未被计数快路径劫持。
- 边界：首次计数请求需构建 audited lookup view（约 3.5 分钟，启动预热期），
  之后秒级；450 为当前 serving pack 中申请人与该公司关联的专利记录数，
  联合申请按记录计。
