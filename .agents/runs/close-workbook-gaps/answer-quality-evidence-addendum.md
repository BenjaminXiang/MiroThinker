# 答案质量切片——补充证据（主上下文，2026-09-11）

> 配合 `change-log.md` 的 r3/r4 归因条目使用；设计切片的额外发现，按证据分类。

## 1. 展示窗口被 lexical 模式候选占满，vector（语义）候选结构性地排最后

- 事实链（s11 worktree 行号）：
  - 文档车道候选（exact/structured/lexical）一律 `raw_score=1.0`
    （`knowledge_read_isolated.py:8756`，同函数 `8717 score=1.0`）；
  - vector 车道候选带真实相似度 `raw_score=similarity_score`（`:7799`）；
  - serving 重排桶内按 `-raw_score` 排序（F4 后，`knowledge_serving_isolated.py:2524-2534`）
    → 所有 1.0 候选先于全部 vector 候选；lexical 进池 48 时，
    selector 的 local≤16 窗口（`knowledge_serving_isolated.py:5851-5858`）
    被 lexical 候选人填满，vector 候选人进不了展示集。
- 注意：这不是 F4 引入的（F4 前主键同为 -raw_score，只是并列组内随机）；
  是既有的"车道分数量纲不一"问题。
- 与 GT 的关联：g5 的「PCB打板」与其库里文本「PCB 打样」是**转述关系**
  （嘉立创 profile：`PCB 打样、SMT 与电子供应链基础设施服务`），
  子串/短语匹配桥不过去；语义车道是天然桥梁，但结构上排最后。
  同类：一博/兴森/则成/上达/精诚达（lexical pool 62–98 或无分）。
- 候选修法（供设计评估）：① vector 分数归一到可比尺度（F1-B 提案 B 的窄版）；
  ② 车道间按 rank 交错而非按分数重排；③ 给 vector 保留展示名额；
  ④ 类目词表补转述词（打板→打样/快板）。

## 2. 协议 JSON 泄漏（用户可见）

- `{"selected_claim_indexes": [...], "selected_entity_indexes": [...]}`
  概率性地出现在用户可见答案正文里（r2 g5-t2、r3 g2-t2，≈每跑 1 处；
  r1/r4 无）。B5 的 redaction 只覆盖 `<|canonical_v2_...|>` marker 形态，
  纯 JSON 形态漏过。属 B5 同类（wire 协议泄漏），归答案质量切片。

## 3. GT 公司的主流路径是 web 标题而非本地实体（嘉立创例）

- 重放 after-F4 g5-t1：展示集第 8 位是网页「嘉立创下单助手_PCB免费打样…」，
  **本地实体「深圳嘉立创科技集团股份有限公司」不在其中**
  （lexical 候选名列表里只有深南电路@41，嘉立创缺席）。
- 含义：g5 的"点名"有时靠 web 标题命中（不稳定，r3 有/r4 无），
  本地实体召回缺口是根因；验收要稳定达标必须让本地实体进展示集。

## 4. 「资料薄」的两种形态（g2-t1）

- 九号机器人：`product_description=null`、profile 为模板句（"聚焦机器人…"）、
  tech_tags 空 → 无任何酒店/送餐证据可依。
- 开普勒：只有产品名（先行者K2/K1/S1/D1），"酒店"只出现在
  `technology_route_summary` 的场景枚举里。
- 对照：锐曼（有"德利哥2.0/熊二送餐机器人"、`KTV/酒店/餐厅配送`）与
  安赛步（`酒店客房送餐…`）**资料充足却排在 local-16 窗口之外**。
  → "资料薄"与"窗口外"是两类不同根因，修法不同。
