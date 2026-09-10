# C2.1r(v2) 官方信封封印阻塞 — 数据线在 IndexProjectionRequest 上领先 serving 线一个字段（2026-09-10）

## 结论（一句话）

run14 真身信封由数据线 `a226bd8`（2026-09-07，multi-value-enrichment）之后的代码封印，
其 `consumer_handoff.index_projection_request` 携带 **`supplementary_field_values`**
（`dict[str, dict[str, list[str]]]`，把每个 canonical 实体的未选中断言值写进
embedded_content/lookup_content 以加宽检索面）；**serving 线的 `IndexProjectionRequest`
模型没有这个字段**，官方封印器在信封校验第一步即 fail-closed。禁止修 loader/信封/索引，
按纪律停下汇报。

## 原始报错（c2-seal.log，原样）

```
serving pack build failed: ValidationError: 1 validation error for CompleteCandidateBuildEnvelope
consumer_handoff.index_projection_request.supplementary_field_values
  Extra inputs are not permitted [type=extra_forbidden, input_value={'company-c-6fad9b9cbf96b...tle': ['客座教授']}}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.11/v/extra_forbidden
```

失败点：`s12c/build_serving_pack.py:172-175` 的
`CompleteCandidateBuildEnvelope.model_validate_json(...)`——封印器第一步，未触碰任何文件
（半成品目录不存在，已确认；信封/索引全程只读）。

## 证据链

1. **字段只在数据线存在**：
   - 数据线（`.worktrees/data-rebuild`）`index_projection.py:277`：
     `supplementary_field_values: dict[str, dict[str, list[str]]] = {}`，并在
     `_vector_points`/`_lookup_documents`（:482/:488）以 `supplementary_by_canonical`
     消费——即该字段**实际改变了 run14 索引 points/documents 的内容**（加宽检索面）。
   - 引入提交：`a226bd8 09-07 22:59 feat(multi-value-enrichment): all valid assertion
     values widen search surface`（git -S 定位）。data-rebuild HEAD：`7d67d79 09-09 15:40`。
   - serving 线（`.worktrees/canonical-v2-s11-consolidation`）全 canonical_v2 目录
     **零命中**——从未移植该提交。
2. **信封确实携带该字段**：报错 input_value 显示 `{'company-c-6fad9b9cbf96b…':
   {…'title': ['客座教授']}}`——非空 dict。
3. **这不是"换个代码跑封印器"能绕过的**：即使用数据线代码跑官方封印器——
   - 封印器把**完整** request dump（含该字段）哈希进 `index_projection_request_sha256`
     （build_serving_pack.py:274-275）；
   - 但写 `index_projection_scalars` 时只抄 6 个命名字段（:302-311），**不含**该字段；
   - serving loader 从 scalars 重建 request（serving_pack_loader.py:769-798，
     `model_construct` 无此字段 → 默认 `{}`），重算哈希必然不符 → 启动在
     serving_pack_loader.py:799-805 再次 fail-closed。
   即：**该信封与 serving 线的请求契约不兼容是结构性的**，封印器/loader/scalars 三处
   都要认识这个字段才能闭环。

## 修复选项（归主上下文决定，本切片未执行）

- **(a)（建议）serving 线移植 `supplementary_field_values`**：`IndexProjectionRequest`
  加字段（默认 `{}`，与数据线逐字一致）+ 官方封印器 `index_projection_scalars` 透传 +
  loader 769-798 重建透传。三处小改但触及检索关键契约——需要挂在 OpenSpec 变更下
  （可并入 close-workbook-gaps 或新切片），语义对齐数据线 `a226bd8`。
- (b) 数据线剥掉该字段重导信封：请求绑定会说"无补充值"而索引内容实含补充值——
  绑定链语义失真，且仍需数据线动手。不推荐。
- (c) 数据线用与 serving 契约完全一致的代码重跑 run14 全流程：最重，且丢弃
  multi-value-enrichment 的检索加宽（run14 数据的一部分价值）。不推荐。

## 时间线回顾（三个阻塞的关系）

1. 半封印包 manifest 索引绑定陈旧（p4 vs run14）→ 已被 C2.1r 重封印器覆盖（可修）。
2. 半封印包 relationships.json candidate 段旧契约（单数组世代）→ 引出了真身信封路径。
3. **真身信封 `supplementary_field_values` 代际超前 serving 线**（本阻塞）——
   信封路径与重封印路径都不通：重封印器受阻于旧契约 relationships.json，官方封印器
   受阻于新字段信封。两条路汇合到同一个根因：**serving 线代码与 run14 数据世代脱节**，
   需要先完成 (a) 的移植，之后官方信封封印器即可直通（重封印器保留备用）。

## 现场状态

- 官方封印器日志：主仓 `.agents/runs/close-workbook-gaps/c2-seal.log`（含原始报错）。
- 无半成品目录；信封（data-rebuild，只读）、索引、半封印包全程未动；18188 未动。
- 重封印器保留在 worktree `9a99ca2`（未删除、未扩展，按要求）。
- C2.1b–e 阻塞待 (a) 或等效决策。C2.1c 已备好的对照基线：s12f lookup 四域
  company 1,737 / paper 563 / patent 1,931 / professor 1,428 = 5,659；run14 侧
  7,089 / 24,520 / 11,504 / 3,958 = 47,071；25 轮门 = after-s18 基线 21 PASS + g17-t1。
