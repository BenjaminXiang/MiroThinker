# 丁文伯单轮问题修复日志（2026-10-23）

关联计划：[丁文伯类单轮问题：公司/专利答错](./2026-10-23-professor-standalone-answer-fix.md)

## 第 1 轮 · 复现与根因

- 单轮“丁文伯创办的公司是哪家”：plan `domains=[company]`，
  lanes `exact/structured/lexical/vector/web`；无 relationship 车道。
  web 返回丁文波/广州文伯化工；答案据此答成丁文波/千信科技。
- 单轮“丁文伯有哪些专利”：plan `domains=[patent]`；本地 lexical 128 条
  多为无发明人的通用专利；web 返回丁文博/丁文胜；答案说“没有专利”。
- 对照：先问“介绍清华的丁文伯”再问“他参与创立了哪些企业”，可答出
  深圳无界智航。根因定位为“单轮命名主体未锚定 + web 主体一致性无锚”。
- 直连测试：Bocha 对“丁文伯 创办的公司”返回丁文波/广州文伯；
  DeepSeek 搜索 API 对同一问题返回 Xspark AI/无界智航，对“丁文伯 专利”
  返回清华成果专利页与“授权或公开发明专利15项”的报道。

## 第 2 轮 · 修复

- 新增 `create_local_entity_resolver`（pack lookup 精确名称匹配；
  同名多实体不锚定）。
- chat 层新增 `_standalone_anchor`：单轮关系问句解析出教授/企业后，
  作为 planning request 的 displayed anchor；runner 在构造 chat adapter 后
  注入 resolver。
- web lane 增加 DeepSeek 第二通道：`CHAT_LLM_PROFILE=deepseek*` 且 key 可用时
  以 DeepSeek 替代 Serper（Serper 余额已透支），保留 Bocha 摘要召回；
  provider 顺序、查询、合并、trace 由 `_provider_order` 驱动。
- 专利答案过滤：`<人名>有哪些专利` 查询中，本地专利证据必须包含该人名
  才可成为 claim；避免无发明人的通用专利把 handle 泄漏到引用里。

## 第 3 轮 · 验证

- 单元：新增 7 个测试（chat anchor 3、DeepSeek provider 2、
  web lane DeepSeek 1、专利人名过滤 1）全部通过；
  serving/web 三文件 324 passed；chat adapter 138 passed + 1 个既有措辞失败
  （已在 HEAD 复现，与本改动无关）。
- 客户机实测（最终重启后 `/api/health` 200）：
  - “丁文伯创办的公司是哪家” → 深圳无界智航科技有限公司，citation
    `local-source-08f0d53d00dda3a8`，无丁文波/千信科技；
  - “丁文伯有哪些专利” → 申请号 202410612834.1《一种基于无线光通信的
    目标检测与识别系统和方法》，发明人含丁文伯；并引用清华官网
    “授权或公开发明专利15项”；citation 全为 web-source，无无关本地专利；
  - “无界智航的创始人是谁” → 丁文伯；
  - “介绍清华的丁文伯”+“他参与创立了哪些企业” → 无界智航（多轮不回归）；
  - “深圳有哪些机器人公司”“丁文伯教授的研究方向” → 行为不变。

## 第 4 轮 · 边界

- 专利域仍没有 `professor_has_patent` 关系类型；单轮专利回答依赖 web 检索，
  本地专利只在证据文本含人名时参与。
- Bocha 对中文人名召回弱是既有问题；本次用 DeepSeek 作为第二通道缓解，
  未替换 Bocha。
- 专利答案目前能确认到 1 件完整著录 + “15 项”数量披露；公开数据没有
  完整清单，不能逐项列出。

## 第 5 轮 · 本地专利计数

- “本地知识库收录了优必选多少专利”原走 patent 普通检索，答“没有统计口径”。
- 关系车道候选在 `request.max_candidates` 处截到 128，真实 450 条拿不到。
- 包内公司短名“优必选”是名称索引派生形式；resolver 原先要求原始名称字面
  出现在 query，导致无法锚定公司；已改为信任索引匹配。
- 新增 full-projection 计数器 + chat 计数快路径：
  - `本地知识库收录了优必选多少专利` → 450 件，
    citation `local-source-5ac2eb76475da877`；
  - `优必选有多少专利` → 450；
  - `优必选有哪些专利` → 仍走列表路径（12 条本地专利 citation）。
- 首次计数请求需构建 audited lookup view（约 3.5 分钟），之后秒级。
