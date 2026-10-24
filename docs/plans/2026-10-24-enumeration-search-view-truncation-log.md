# “深圳哪些公司做激光雷达”答偏：检索文本被截断（执行日志）

> 对应变更：`fix-enumeration-search-view-company-truncation`
> 日期：2026-10-24 ｜ 客户现场线

## 症状

用户提问 **“深圳哪些公司做激光雷达”**，答案说“现有公开信息中没有直接列出深圳从事
激光雷达业务的公司名单”，转而介绍华为、中兴、比亚迪、腾讯、平安、招行、万科，
最后追加 114 家不相关本地企业清单。用户评价：“不结构化，重点不突出。”

同一句话在 15 分钟前的另一次会话里却答出了镭神智能、云创传感等 7 家厂商。差异不在
数据，而在**检索文本**。

## 根因

`_search_view`（`src/data_agents/canonical_v2/followup_referents.py`）负责在
“没有已显示实体”时生成检索文本。它的公司名分支只要 `COMPANY_NAME_PATTERN` 匹配到
“深圳哪些公司”，就直接把这一段当作公司名返回，**把后面的“做激光雷达”整段丢掉**。
同模块的 `_has_explicit_company_name` 早就有疑问词拒绝表（哪些/什么/几/多少…），
但 `_search_view` 这个分支没用它——同一规则两处不一致。

复现：

```text
'深圳哪些公司做激光雷达'   -> '深圳哪些公司'
'深圳有哪些公司做激光雷达' -> '深圳有哪些公司'
'深圳什么公司做激光雷达'   -> '深圳什么公司'
```

后果链条（2026-10-23 01:51 会话 `C4XrUsD91G4LegDYgkoomeezYIllcZ9d` 的 trace）：

- lexical/exact/structured 三条本地车道全是 0，vector 128 条也是按“深圳哪些公司”
  召回的泛公司；
- web 只发了 **一个** 视图“深圳哪些公司”，命中缓存的 CSDN《深圳有哪些大型公司
  (2014年数据)》；
- 答案主体变成这个网页标题，于是写成“没有激光雷达名单”+ 大公司罗列 + 114 家清单。

服务包里其实有 **61 家深圳企业**的结构化字段提到激光雷达（镭神、览沃、海伯森、
砝石激光雷达、速腾聚创……），所以不是数据缺口。

## 修复

在 `_search_view` 的公司名分支复用同模块的 `_EXPLICIT_COMPANY_REJECT_MARKERS`：
匹配文本里含疑问/指代词的，不当公司名，落回完整查询文本。

```python
company = COMPANY_NAME_PATTERN.search(search_value)
if company is not None and not any(
    marker in company.group(1) for marker in _EXPLICIT_COMPANY_REJECT_MARKERS
):
    return company.group(1)
```

具名公司问法不受影响：`深圳市优必选科技股份有限公司有哪些专利` 仍然只取公司名。

## 怎么验证

- 新增 6 个参数化用例：三种“哪些/有哪些/什么公司”问法保留完整查询；三个具名/指代
  对照（优必选全名、优必选这家公司、深圳激光雷达公司有哪些）保持原压缩行为。
- `test_followup_referents.py` **152 passed**；
  `test_knowledge_query_planning_contract.py` + `test_enumeration_deep_fetch.py`
  **11 passed**；`test_knowledge_serving_isolated.py` **312 passed**。
- 部署到客户机（md5 `c82ac86f…`）并重启；`/api/health` 200（本次冷启动因机器换页
  偏慢：RSS 19.5GB + swap 2.1GB）。
- 线上复测“深圳哪些公司做激光雷达”（trace `2026-10-24T14:29:33Z`）：
  - web 视图 8 个，全部含“激光雷达”，不再出现单独的“深圳哪些公司”；
  - lexical 车道 **0 → 128**，vector 128；
  - 答案主体从 CSDN 网页标题变成 **深圳市砝石激光雷达有限公司**；
  - 答案给出 12 家厂商的结构化清单（速腾聚创、镭神、览沃、力策、砝石、煜炜、
    玩智商、机智人、锐驰、大族锐波、海伯森、迈测），每家一句产品说明；
  - 引用 12 条：**11 条本地 company + 1 条 web**。
- 对照“深圳市优必选科技股份有限公司有哪些专利”：12 条专利引用，按技术方向分组，
  无回归。

## 残留（本次未改）

- 答案尾部仍有“此外，本次检索还召回以下相关本地企业：……”清单（最多 64 家）。
  现在列出的都是真正相关的激光雷达企业，不再是无关名单；但长清单仍然影响观感。
  这句话在 **commit 之前** 追加，作用是让这些企业名进入会话实体集合，支持后续
  “其中哪些做车载”这类收窄追问；要缩短它属于产品/呈现决策，不是检索缺陷。
- indexed lexical 车道（`CANONICAL_V2_LEXICAL_INDEX`）仍关闭；本次是 substring
  lexical 车道因内容词恢复而命中。客户机 bundle venv 没有 `jieba`，无法就地构建
  FTS 索引。

## 影响哪些问题

- 枚举型“某地哪些公司做 X”问法不再丢失技术词；本地 lexical/vector 车道能按 X 召回。
- `focused_entity` 判定随检索文本恢复而变为“非聚焦实体”，答案选择器不再走
  只保留单一网页主体的分支。
- 具名公司、指代追问的检索文本保持原行为。
