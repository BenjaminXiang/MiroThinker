## ADDED Requirements

### Requirement: Paper-topic-search queries SHALL route to paper topic retrieval

A query that expresses **topic-search intent over papers** SHALL classify as type **B** with
`target_domain="paper"` and route to `B_paper_topic_search` (paper topic retrieval), NOT as
exact-paper (type A) and NOT as `unknown`. Topic-search intent over papers is: the query
mentions 论文/文章/paper AND a search/topic marker (关于/有关/哪些/有哪些/有什么/有没有/找/查找/
搜索/检索/推荐/最新/最近/相关). This intent classification SHALL take precedence over the
exact-paper rule for such queries.

Two guards preserve existing routing:
- A **bare English paper title** (`^[A-Za-z][A-Za-z0-9\s:,\-./]{15,}$`, no search marker) SHALL
  continue to classify as type A (exact paper profile) — it is not a topic search.
- An **entity-anchored** query (mentions 教授/研究员/创始人/企业家/公司/企业) SHALL NOT be
  classified as paper-topic-search by this rule — it routes via the professor/company paths.

This removes the over-fire by which a paper-topic query containing an English term (e.g.
perovskite, federated learning) was classified as exact-paper (A) with the whole query as the
title, then fell through to `unknown` with zero retrieval.

#### Scenario: a topic-search query with an English term routes to paper topic search
- **GIVEN** the query "关于perovskite钙钛矿材料的论文有哪些" (mentions 论文 + 关于 + the ASCII run perovskite)
- **WHEN** classified by the deterministic rule classifier
- **THEN** it classifies as type B, `target_domain="paper"`, and `/api/chat` returns
  `query_type="B_paper_topic_search"` with perovskite-paper citations (not `unknown`)

#### Scenario: a "latest papers" query routes to paper topic search
- **GIVEN** the query "关于联邦学习federated learning的最新论文"
- **WHEN** classified
- **THEN** it classifies as type B, `target_domain="paper"`, routes to `B_paper_topic_search`
  with federated-learning-paper citations

#### Scenario: a bare English paper title stays exact-paper
- **GIVEN** the query "ShuffleNet V2: Practical Guidelines for Efficient CNN Architecture Design"
- **WHEN** classified
- **THEN** it classifies as type A, `target_domain="paper"` (english-title rule), unchanged

#### Scenario: an entity-anchored paper query is not re-routed to paper-topic
- **GIVEN** the query "常瑞华教授发表了哪些论文" (mentions 论文 + 哪些, but also 教授)
- **WHEN** classified
- **THEN** it is NOT classified as paper-topic-search by this rule; it routes via the professor
  path (type A, `target_domain="professor"`), unchanged

#### Scenario: a query ending in 论文 still matches the original topic clause
- **GIVEN** the query "钙钛矿太阳能电池方向的论文"
- **WHEN** classified
- **THEN** it classifies as type B, `target_domain="paper"` (unchanged from prior behavior)
