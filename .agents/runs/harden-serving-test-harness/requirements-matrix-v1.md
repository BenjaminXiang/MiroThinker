# 需求矩阵 v1（harden-serving-test-harness / A2）

> 来源：`docs/测试集答案.xlsx`（17 组/25 轮，验收基准）+ 2026-09-09/10 需求讨论
> + 干跑证据。状态三值：**met**（有证据满足）/ **gap**（有据缺口，断言 RED）/
> **pending**（未判定，标注负责阶段）/ **non-goal**（需用户裁定）。
> 证据指针：`g{n}-t{m}` = 三层判定轮次；`probe:*` = data_probes.py；
> `dryrun#n` = 交付干跑发现；`replay` = 重放门。
> 基线：三层判定 9/25（2026-09-10 离线复判 flash-systemd 存档）。

## L0 系统定位（4）

| ID | 需求 | 状态 | 证据 |
|---|---|---|---|
| L0-1 | Web 自然语言对话检索入口 | met | 18188 `/api/chat/stream` 在跑，25 轮可复跑 |
| L0-2 | 四域覆盖：教授/企业/论文/专利 | met | 路由+A–G 分类在跑；深度见 L1 |
| L0-3 | 深圳科创生态聚焦 | met | 本地包 + 本地优先逻辑在 |
| L0-4 | 本地知识库优先 + web 兜底 | gap | 兜底在；本地引用/深度不足（g1/g4/g6/g8 provenance RED） |

## L1 单域检索（14）

| ID | 需求 | 状态 | 证据 |
|---|---|---|---|
| L1-1 | 教授精确点名画像 | gap | g1-t1 完整性 1/5（邮箱/教育/荣誉缺）→ GAP-13/15 |
| L1-2 | 企业精确点名画像 | gap | g4-t1 3/6、g8-t1 2/5 → GAP-15 |
| L1-3 | 论文精确详情 | gap | g6-t1 缺涉及教授 → GAP-16 |
| L1-4 | 专利号精确详情 | gap | g17-t2 内容对但本地引用 0 → GAP-07 |
| L1-5 | 企业别名/简称解析（字节跳动→ByteDance） | gap | 盘点 G2b；probe: aliases 4.8% → GAP-14 |
| L1-6 | 同名消歧（两家无界智航） | met | g4-t2 forbidden 智航无人机未混入 |
| L1-7 | 语义枚举（酒店送餐机器人供应商） | gap | g2-t1 缺开普勒/九号 → GAP-02 |
| L1-8 | 语义搜索本地召回（深圳具身智能厂商） | gap | g14-t1 pool 1/3，召回 web 厂商 |
| L1-9 | 行业知识问答（数据路线/方法） | gap | g11/g13/g16 PASS；g12 缺真机实测、g15 缺规则法 → 契约缺项 |
| L1-10 | 人物评价（是否大牛） | met | g9-t1 三层 PASS |
| L1-11 | 企业评价/市场竞争力 | gap | g10 PASS；g8-t1 完整性 FAIL |
| L1-12 | 多约束人物检索（教育×地域×行业） | gap | g7-t1 pool 0 → GAP-03 |
| L1-13 | 长枚举（>20 条） | pending | 覆盖边界 → D1 |
| L1-14 | 模糊查询引导澄清 | pending | 澄清门在（contextual-query-interpretation）；缺系统用例 → D1 |

## L2 关系检索（8）

| ID | 需求 | 状态 | 证据 |
|---|---|---|---|
| L2-1 | 教授→企业（丁文伯→无界智航） | gap | g1-t2 内容薄+本地引用 0 → GAP-07 |
| L2-2 | 企业→专利（优必选） | met | g17-t1 三层 PASS（2026-09-10 B1）：16 CN 号 + 本地引用 16 → GAP-01 关闭 |
| L2-3 | 专利→企业（反向） | pending | 覆盖边界 → D1 |
| L2-4 | 教授→论文 | gap | probe: professor_ids 0% → GAP-16 |
| L2-5 | 论文→教授（涉及教授） | gap | g6-t1 → GAP-16 |
| L2-6 | 教授→专利 | pending | 覆盖边界 → D1（patent.professor_ids 字段已在 schema） |
| L2-7 | 企业→关键人物（key_personnel∩教授） | pending | 90 例交集已实测 → C3 |
| L2-8 | 跨域聚合（类型 D 全景） | pending | 覆盖边界 → D1 |

## L3 多轮上下文（8）

| ID | 需求 | 状态 | 证据 |
|---|---|---|---|
| L3-1 | 指代消解（他/这/该） | met | g1-t2/g6-t2 PASS；replay G1-T3 PASS |
| L3-2 | 上下文收窄（上述企业里深圳的） | gap | g2-t2 1/6、g5-t2 2/12 → GAP-04 |
| L3-3 | 话题切换 | pending | 覆盖边界 → D1 |
| L3-4 | 长会话（>10 轮） | pending | → D2 |
| L3-5 | 用户纠偏后的消歧保持 | gap | g4-t2 消歧对但事实错（法定代表人 李志豪≠穆世龙）→ GAP-06 |
| L3-6 | 深度追问（有哪些布局和进展） | met | replay G1-T3（解释器 3s 超时修复后） |
| L3-7 | 枚举后细节追问立场一致 | gap | g2-t3 → GAP-05 |
| L3-8 | 会话主体一致性 | met | replay 7/7（followup-subject-consistency） |

## L4 答案质量（10）

| ID | 需求 | 状态 | 证据 |
|---|---|---|---|
| L4-1 | 立场与事实/GT 一致 | gap | g2-t3 → GAP-05 |
| L4-2 | 完整性 ≥80% 关键点 | gap | 三层基线 completeness 8/20 |
| L4-3 | 关键事实正确 | gap | g4-t2 李志豪 → GAP-06 |
| L4-4 | 安全类拒答不列地点 | met | g3-t1 PASS |
| L4-5 | 超范围拒答/不外推 | pending | 覆盖边界 → D1 |
| L4-6 | 空答案零容忍（守卫降级） | gap | GAP-09（pro 档 g17-t1 空答案）→ B5 |
| L4-7 | 时效性查询（"最新"） | pending | 覆盖边界 → D1 |
| L4-8 | 不伪造本地数据（无绑定则明说） | pending | spec delta 已立（close-workbook-gaps）→ B1 验证 |
| L4-9 | 答案结构可读 | met | 存档答案均分节/列表 |
| L4-10 | 低置信度 hedging | met | replay + 存档（"无法确认"类措辞在正确场景出现） |

## L5 引用与溯源（6）

| ID | 需求 | 状态 | 证据 |
|---|---|---|---|
| L5-1 | 本地答案本地引用 ≥1 | gap | GAP-07：三层基线 provenance 2/9 → B4 |
| L5-2 | web 引用卫生（无导航/错误模板） | gap | GAP-08：live 断言已上线 → B4 |
| L5-3 | 引用尽量可指出处 | pending | 溯源降级裁定后定义 → B4 |
| L5-4 | 引用排序目标实体优先 | pending | simple_serve 实测缺陷；部署线待查 → B4 |
| L5-5 | 来源类型标注（本地/web） | met | citations.type 已在 API |
| L5-6 | 审计级溯源 | non-goal | 2026-08-21 裁定冻结（用户确认） |

## L6 数据地基（8）

| ID | 需求 | 状态 | 证据 |
|---|---|---|---|
| L6-1 | 教授字段质量（套话/占位/填充） | gap | probe GAP-13a–e 全 RED → C1 |
| L6-2 | 企业别名覆盖 | gap | probe: 4.8% → GAP-14 → C1 |
| L6-3 | 数据版本对齐 run14（47,071） | gap | probe: serving 5,659 → GAP-15 → C2 |
| L6-4 | 关系数据覆盖（patent_has_applicant 等） | gap | 123 行/48 家 vs 绑定 7,650 → C3 |
| L6-5 | 论文↔教授 ID 链接 | gap | probe: 0/24,520 → GAP-16 → C4 |
| L6-6 | 专利↔企业字段绑定在包内 | met | probe: 82.4%（1,592/1,931），优必选 58 条 |
| L6-7 | 向量索引可用 | met | Milvus Lite 51,029 向量在线，embedding/reranker 可达 |
| L6-8 | 字段质量契约门槛每次发布对账 | pending | → C1/C2 |

## L7 非功能（5）

| ID | 需求 | 状态 | 证据 |
|---|---|---|---|
| L7-1 | 单轮延迟可接受 | met | 存档实测 5–43s/轮 |
| L7-2 | 无 GPU 运行（客户现场） | met | embedding/reranker/LLM 全部走远程端点 |
| L7-3 | 并发能力 | pending | → G |
| L7-4 | 长期稳定运行 | pending | → G |
| L7-5 | 外部依赖故障降级 | pending | → G（故障注入） |

## L8 运维与交付（5）

| ID | 需求 | 状态 | 证据 |
|---|---|---|---|
| L8-1 | 配置页面化（页面编辑受管配置文件） | pending | B 方案已裁定，先干跑后建页 → F |
| L8-2 | 交付包可移植（无机器绑定路径） | gap | dryrun#1：manifest 硬编码绝对路径 → F |
| L8-3 | 服务入口与构建入口分离 | gap | dryrun#3：入口=构建 runner，20+ 构建参数 → F |
| L8-4 | runbook（6–10 步从零到能问一题） | pending | → F |
| L8-5 | 访问日志 | met | access-log sqlite 在跑（462+696 轮已入析） |

---

**汇总**：68 条 = met 15 / gap 21 / pending 30 / non-goal 2（L0–L4 44 条全部已判定；
L5–L8 有证据的已判定，其余 pending 带负责阶段；v1.1：L2-2 翻 met，GAP-01 关闭）。
下一版（v2）：每轮 B/C 切片 GREEN 后更新对应行。
