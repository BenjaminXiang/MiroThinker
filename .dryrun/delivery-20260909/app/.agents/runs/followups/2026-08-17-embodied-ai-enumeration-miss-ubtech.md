# Follow-up: domain enumeration misses the flagship company (优必选 absent from 具身智能 company list)

Status: **Open — recorded only, attribution deferred** (user test-and-record mode,
2026-08-17). User grade: 回答还行 (quality-level defect, not a hard failure).
Date: 2026-08-17. Found by: user hands-on test on production (HEAD ≥ `438300a`).
Related: round-1 findings P8 + `transcripts.md` group 7; legacy-line recall-gap
family (`fix-chat-retrieval-recall-gaps`, FM1a "6 absent entities = 67% of
misses"); golden-set backlog T19/T22/T23 (concept KEY coverage).

## Problem (verbatim in transcripts.md group 7)

- Query `深圳有哪些做具身智能的公司` → on-topic, structured, no drift/refusal —
  the first basically-usable answer of the day — but the list omits the flagship
  优必选 (UBTECH), named by the user as a basic expectation.
- List members are mostly newer/smaller startups (诺因 est. 2025, 知有无界, 赛博格…);
  content shape suggests web listicle sourcing dominating the enumeration.

## Established fact (same-day internal evidence, no new probe needed)

UBTECH IS in the serving pack: group 4 T1 (`优必选科技怎么样`) returned its
canonical profile correctly. Therefore the miss is an **enumeration-path /
ranking / fusion defect**, not data absence.

## Attribution questions parked for the chain audit

1. Vocabulary mismatch: does UBTECH's canonical profile text embed strongly for
   "具身智能", or does it speak mostly 人形机器人/教育机器人? (query-side term
   view exists — did it fire and where did it rank?)
2. Enumeration candidate window / merge rank: was UBTECH retrieved-but-buried
   (the widened `_ENUMERATION_CANDIDATE_WINDOW` machinery exists for exactly this
   class — did this query qualify for the widened window?)
3. Web-lane dominance: did web listicle results (fresher, keyword-exact 具身智能)
   crowd the canonical candidates in fusion?
4. Are the listed startups canonical records at all, or web-minted entities?

## Expected behavior (for the future fix contract)

A domain enumeration of Shenzhen embodied-AI companies must surface the canonical
flagships (优必选 at minimum; plausibly 越疆/普渡-class peers), with long-tail
startups as supplement — missing the flagship is an acceptance-line failure even
when the answer is otherwise well-formed.

## User-provided reference answer (2026-08-17, verbatim — golden sample for this query)

用户手工检索后给出的同题参考清单（结构：整机与本体 / 核心零部件与感知、AI 技术）：

> 深圳具身智能代表企业整机与本体企业：深圳市优必选科技股份有限公司：人形机器人第一股，布局消费级、服务级及工业人形机器人。深圳逐际动力科技有限公司：专注于通用足式与人形机器人研发，具备领先的运动控制能力。乐聚智能（深圳）股份有限公司：人形机器人骨干企业，推出多款开源及商业化人形机器人。深圳市众擎机器人科技有限公司：聚焦高动态人形机器人和足式机器人研发。智平方（深圳）科技股份有限公司：专注于具身大模型与通用智能机器人系统。深圳市越疆科技股份有限公司：以智能机械臂起家，延伸布局机器狗及具身智能场景。跨维（深圳）智能数字科技有限公司：专注3D视觉与具身智能算法的高新企业。核心零部件与感知、AI技术：奥比中光科技集团股份有限公司：为智能终端和机器人提供"3D智慧之眼"的感知芯片与方案。帕西尼感知科技（深圳）有限公司：深耕多维触觉数字化与触感灵巧手技术。戴盟（深圳）机器人科技有限公司：研发高分辨率多模态触觉感知及视触觉夹爪产品。

对照：系统答案与参考清单的重合度极低（优必选/越疆缺席；逐际动力、乐聚、众擎、
智平方、奥比中光、帕西尼、戴盟均未出现），系统清单以 2025 年新创公司为主。

## User design direction (2026-08-17, recorded)

> "web search，投两页的内容再 fetch 一下，应该比现在好的多。目前这个质量有点差。"

即：枚举类查询应抓取检索结果**前两页的正文内容**参与合成，而不是只靠
标题/摘要。重要事实：**正文抓取能力已存在**——phase-2 Task 7 的分级抓取器
（tiered fetcher，带反回声守卫），但当前被限制在**纠错路径、最多一页、仅
权威页**（`followup-subject-consistency` Task 7）。本方向 = 把既有抓取器
按"枚举路径"做受限扩展（top-2 结果页、预算与延迟护栏），不是从零造轮子。
归因与方案设计均押后，随链路审计一起做。

## Hypothesis VERIFIED end-to-end (2026-08-17, recorder)

用户进一步给出具体应抓取页面 `https://www.aibangbots.com/a/2005`，三个环节
逐一定证：

1. **页面内容实抓验证**：该页为艾邦机器人《深圳70+人形机器人产业链企业一览》
   （2025-07-01）：本体企业 9 家（优必选、逐际动力、乐聚、帕西尼、众擎、普渡、
   数字华夏、鹿明、越疆）+ 供应链数十家（奥比中光、戴盟、森云智能、速腾聚创、
   汇川……）。与用户参考清单 10 家中 8 家直接重合。
2. **搜索可达性验证**：以同族查询搜索，前排结果（新华网"八大金刚"、21财经、
   深圳发改委专文）均列出同一龙头集合（优必选、众擎、帕西尼、越疆、智平方、
   逐际动力、跨维、数字华夏、普渡）——**此类策展清单页在普通 web 检索中
   排名靠前，极易获得**。
3. **系统侧旁证**：系统答案中唯一与该页重合的公司是**森云智能**（该页供应链
   名单成员）——web 通道疑似已在摘要层擦到此类内容，但从未抓取正文。

结论：**"抓取 top-2 结果页正文 ⇒ 枚举质量达到参考清单水准"从推测升级为实证**
（一次抓取即可补齐 8-10 家缺失龙头）；当前 snippet-only 证据是枚举质量的
结构性上限。
