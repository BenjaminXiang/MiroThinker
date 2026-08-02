# 答案流式输出（token 级）+ 轻量提速 — 设计文档

- 日期：2026-08-02
- 状态：设计已获用户确认（范围仅候选 chat.html；停止按钮+保留部分；渐进渲染+缓冲；流式+轻量提速）
- 适用范围：Canonical V2 候选服务（18199）后端 SSE 扩展 + chat.html 前端

## 1. 背景与目标

用户实测反馈：查询期间前端"卡死"（按钮变"检索中"，结果一次性全部输出）；答案较长时还会因前端 8000 字符安全上限被拒（显示"当前版本未生成可安全展示的回答"）；偶发 prose 合成失败时 fallback 直接拼接 claims 原文（原始网页 dump），不是 LLM 整合后的答案。

核心要求：
- **答案输出改成流式**（LLM 生成过程中逐块显示，用户感知等待大幅下降）
- **总时长可以放宽**——时长靠管线/系统优化，**不限制答案长度**（含前端 8000 上限与 prose max_tokens 截断两个隐藏限长点）
- **答案必须经过 LLM 整合**——fallback 不允许展示原始 claims 列表

范围决策（用户确认）：
- 本轮仅改候选服务的 `chat.html` 前端（React 管理台不动）
- 交互：提供"停止生成"按钮；中断/失败保留已生成部分
- 渲染：渐进渲染 + 行级缓冲（无闪烁）
- 本轮顺带做轻量提速（prose max_tokens 放宽），不做全面管线审计

## 2. 冻结契约约束（必须遵守）

- `CanonicalV2ChatAdapter.__init__` / `answer` 签名有 S11A seam 精确校验（不可增参）
- `ChatResponse` 等 Pydantic 模型 schema 冻结（`CHAT_SCHEMA_SHA256`）
- 会话状态由 `_CommittedSession.answer` 实例承载（copy-on-write），流式不得更换 answer 实例
- `create_ephemeral_knowledge_answer` / prose renderer 的同步接口（测试大量注入普通函数 renderer）必须保持可用

## 3. 后端设计：Token 通道（方案 A：渲染器鸭子类型流式）

### 3.1 `_OpenAIProseRenderer.stream(result, on_chunk) -> str`（新增方法，`__call__` 不动）

- `chat.completions.create(..., stream=True)`，逐 delta 调 `on_chunk(delta_text)`，同时累积全文
- 流式模式 `max_tokens=3000`（轻量提速项：解除 1200 token 对答案长度的隐藏截断）

### 3.2 `KnowledgeAnswer.prose_progress: Callable[[str], None] | None`（实例属性）

- 构造默认 None；answer() 内 prose 调用改为鸭子类型分流：

```python
stream_fn = getattr(self._prose_renderer, "stream", None)
if stream_fn is not None and self.prose_progress is not None:
    rendered = stream_fn(result, on_chunk=self.prose_progress)
else:
    rendered = self._prose_renderer(result)   # 测试注入的同步 renderer 走这里，零影响
```

- 失败语义保持：首 token 超时（30s）→ 重试一次 → `_prose_fallback_message`（降级提示，不 dump claims——8d1930c 已实现）

### 3.3 `adapter.answer_stream` 接线（session lock 内）

```python
base_answer = factory() if committed is None else committed.answer
base_answer.prose_progress = lambda t: progress("answer_chunk", {"text": t})
try:
    return self._answer_locked(...)
finally:
    base_answer.prose_progress = None
```

- 新会话/既有会话共用同一 answer 实例 → 会话状态不破坏；session lock 串行 → 无竞态

### 3.4 SSE 事件协议扩展

```
event: stage     {"name":"synthesis"}
event: answer_chunk {"text":"……"}      ← 新增，多次
event: answer     {完整 ChatResponse}   ← 保持（citations + 最终文本，整体对齐用）
event: done
```

- chunk 是原文块，服务端不做内容过滤（前端逐块过滤 + answer 事件整体校验兜底）

## 4. 前端设计：渐进渲染（chat.html）

### 4.1 行级缓冲渲染器（复用现有 renderMarkdown，新增流式模式）

```
streamBuffer 状态：
  - answer_chunk → 追加 buffer
  - 未闭合的 ``` 代码块 → 整体留 buffer（直到闭合）
  - 行内 ** 未配对（奇数个）→ 该行留 buffer
  - 完整行（\n 结尾且行内语法闭合）→ 立即增量渲染（只 append 新元素，不清空 → 无闪烁）
  - answer 事件 → 用最终文本整体重渲染一次（消除缓冲差异 + 对齐 citations）
```

### 4.2 停止生成按钮

- synthesis 阶段过程面板显示"停止生成"
- 点击 → `reader.cancel()` 中断 fetch 流；已渲染部分保留；状态行"已停止生成（已保留当前内容）"

### 4.3 中断/失败处理

- 流意外中断（无 answer 事件）→ 保留已渲染部分 + "生成中断，可重新提问"
- `error` 事件 → 保留部分 + 显示错误详情
- `safePublicText` 模式过滤（hex64/内部 ID 正则）逐块执行；**长度上限移除**（不再 8000 截断）

## 5. 轻量提速项

| 项 | 改动 |
|---|---|
| prose max_tokens | 1200 → 3000（解除答案长度隐藏截断） |
| prose 超时 | 默认 30s（已改）；流式下仅对**首 token** 计时，有持续输出则不设全量超时 |
| 其余管线 | 探针并发 8 / 视图并发 / fetch 并发已是优化态，不动 |

## 6. 错误处理矩阵

| 场景 | 行为 |
|---|---|
| 首 token 30s 无输出 | 重试一次；仍失败 → `_prose_fallback_message` 降级提示 |
| 流中途断（chunk 中断） | 后端补发 `error` 事件；前端保留已渲染部分 + "生成中断" |
| 用户点停止 | `reader.cancel()` + 保留部分 + "已停止" |
| answer 事件后整体重渲染 | 与 citations 对齐 |
| 连接断开（网络） | fetch 异常 → 保留部分 + 提示重试 |

## 7. 测试

| 层 | 用例 |
|---|---|
| 后端 | SSE 事件含 `answer_chunk` 序列（注入带 stream() 的假 renderer + prose_progress）；chunk 中断 → error 事件；无 stream 方法的 renderer 走同步路径（现有测试不破）；max_tokens=3000 生效 |
| 前端 | 行缓冲逻辑 node 单测：未闭合 `**`/``` 不渲染、闭合后渲染、完整行即时渲染；停止按钮 → cancel；整体重渲染一致性 |
| 集成 | curl 验证 chunk 流；18199 冒烟：枚举查询（长答案）+ 停止操作 + 中断场景 |

## 8. 明确不做（边界）

- 冻结契约（adapter `__init__`/`answer` 签名、ChatResponse 模型）零改动
- `_deterministic_answer_text` 的 fallback 截断保留（降级路径质量控制，不是答案长度限制）
- React 管理台前端不动（本轮范围仅 chat.html）
- 全面管线性能审计不在本轮（单独规划）

## 9. 相关前置改动

- `8d1930c`（已提交）：deterministic fallback 截断（10 条/2000 字符）+ safePublicText 超长降级
- `acd56c0`（已提交）：SSE 阶段事件流（stage/plan_done/retrieval_done/answer/done）+ answer_stream per-call progress
- prose 超时 12→30s + fallback 降级文案 `_prose_fallback_message`（工作区未提交，随本轮一起）
