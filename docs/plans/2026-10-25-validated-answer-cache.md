# 高频问题缓存（带校验）：设计与当前状态

> 对应变更：`add-validated-answer-cache`
> 日期：2026-10-25 ｜ 客户现场线

## 目标

对“新会话、无指代、纯本地、通过校验”的高频问题，直接返回已验证答案，
省掉检索 + 合成两次开销，降低 TTFT；绝不能把过期、错主体或带网页会话 ID 的
答案缓存后重放。

## 缓存范围（刻意收窄）

- 只缓存新会话第一轮（`committed=None`、无选择项、无 `option_id`）。
- 查询不含指代词（他/她/它/这家/该/其中/上述）与时间敏感词（今天/最新/近/
  目前/本周/今年/新闻/股价）。
- 答案必须**纯本地**：引用类型为教授/论文/专利/企业，且 ID 以
  `local-source-` 开头；含网页引用的答案一律不缓存（网页 handle 的 ID 带原
  会话 ID，跨会话重放会污染上下文）。

## 写入校验（全过才写）

1. 查询合格（长度 2–120、无指代、无时间敏感）；
2. `response_mode=answer`、`render_mode=prose_renderer`；
3. 无 `fallback_sha256`、无 conflicts；
4. 引用非空、全本地、且每个引用 ID 能在 `citation_map` 的 key/value 中解析；
5. 无协议符、无“此外，本次检索还召回…”名单墙；
6. 答案长度 40–1200 字。

校验结果随缓存行保存；被拒的候选只记日志，不写入。

## 失效

- key = `sha256(normalized_query)`；
- 行内绑定 `release_id` 与 `data_epoch`（manual-recall 文件 + corrections 库的
  mtime/size 指纹）；任一变化即 miss；
- TTL 默认 24 小时，`CANONICAL_V2_ANSWER_CACHE_TTL_SECONDS` 可调；
- `CANONICAL_V2_ANSWER_CACHE=0` 可关闭。

## 命中路径

在 `selection` 之后、检索之前查缓存。命中时反序列化 `TurnResult` /
`ChatResponse` / checkpoint，重绑 session/turn id，重建
`_CommittedSession`（context receipt、displayed ids、continuation offer），
再返回缓存响应——保证下一轮“它/其中哪些…”仍能绑定同一实体集合。

## 当前状态（2026-10-25 23:20）

- 代码、单测（9 passed）、部署、`run.sh` 开关、缓存库建表均已完成；
- **线上写入 0 行**：一条看起来完全合格的本地答案（1 条本地引用、141 字、
  无降级、citation_map 正常）没有落库；
- 第二次相同提问 2.72s、答案与第一次不同，**没有命中**；
- 命中后的上下文重建也因此未获线上验证。

## 阻塞点与下一步

写入条件里还有若干 TurnResult 字段在 HTTP 响应中不可见
（`render_mode`、`response_mode`、`fallback_sha256`、`conflicts`）。下一步：
1. 在 `_store_cached_turn` 把 `validate_candidate` 的 checks 以 warning 级别
   打日志；
2. 重启后重放同一条查询，定位被拒的字段；
3. 若只是 relationship 答案带 conflicts，决定“允许 conflicts 但引用仍须
   全本地”是否可接受；
4. 命中后再验证：第二次同问 <1s、缓存行 hit_count+1、下一轮指代仍绑定。

## 附带发现的上下文缺陷（与缓存无关）

公司答案之后问“它有哪些专利”，系统答成了一件无关专利
（`内窥镜光学系统和内窥镜` / 深圳康诺思腾），而不是公司上下文的专利。
这是指代绑定缺陷，需单独修，不能因为缓存未命中而忽略。

## 2026-10-26 校验门定位与调整（客户机实测）

**根因（写日志 `answer cache skip`）**：

- `local_only=False`：原规则要求所有引用都是 `local-source-*`；真实答案几乎都是
  “本地 + 当前网页”混合，因此没有任何一条能过。
- `citation_map=False`：原规则拿 `TurnResult.citations` 去对 HTTP 信封的
  `citation_map`；信封只保留公开引用并重建 map，内部引用（manual 等）永远对不上。
- `length=False`：上限 1200 字，而 1–3k 字的正常答案很常见。

**调整**：

- 校验对象改为将要重放的 HTTP 信封（`response.citations` +
  `response.citation_map` + `response.answer_text`）。
- `local_only` → `local_grounding`：至少一条本地引用（`local-source-*` 或
  `official-source-*`）即可；允许本地 + 网页混合。
  纯网页答案仍不缓存（避免网页时效性/会话 handle 污染）。
- 长度上限 8000 字；移除“名单墙”拒绝项（枚举答案的 8 家 + 计数尾巴是正常内容）。
- 协议符拒绝列表增加 `<|end_of_answer|>` / `<|end_of_turn|>` / `<|endoftext|>` /
  `<|eot_id|>` / `<|im_end|>`。
- `answer_text` 的最终信封清洗增加 `</br>`/`<br>` 与上述终止符，防止合成层漏出。

**离线校验**：构造“1 条本地 + 1 条网页”引用、`citation_map` 完整的信封，
`validate_candidate` 返回 `True`（`local_grounding=True`、`citation_map=True`、
`length=True`）。纯网页信封仍返回 `False`（`local_grounding=False`）。

**待线上复测**：重启后同一新会话问题连问两次，检查
`answer_cache` rows / `hit_count`、两次耗时、命中后追问是否仍绑定实体。
