# Web 通道三缺陷修复（早稻田查询必现失败）

- 状态：R1 已交付（2026-08-28），验收 2/3 达标 + 1 项已知残差
- OpenSpec：`fix-web-lane-timeout-and-utf8-truncation`
- 日志：[2026-08-28-web-lane-timeout-utf8-fix-log.md](2026-08-28-web-lane-timeout-utf8-fix-log.md)

## 问题（症状）

测试集问题「毕业于早稻田，且在深圳专注在机器人行业的企业家有谁」在当前服务栈上
**8 次提问 0 次成功**（5 次 internal_error + 3 次降级话术「网络检索暂不可用…」）。
回答中从未出现期望要点（许晋诚 / 帕西尼）。

## 定责（供应商排除）

用生产 key 实测 Bocha（2026-08-28，日志 `/tmp/bocha-latency-log.json`）：
两个域名 × 4 个查询 × summary 开关共 16 次请求，全部成功，延迟 280–403ms，
UTF-8/JSON 全有效，每次 9–10 条结果。**Bocha 无责，三条失败链全在我方。**

## 根因（三条独立链，可交替出现）

1. **快照按字节截断切坏 UTF-8**：四处 `.encode("utf-8")[:16384]` 把中文三字节字符
   切断，`WebSnapshotPayload.content` 在契约往返 `model_dump(mode="json")` 时
   UnicodeDecodeError，整个 turn 崩掉（internal_error）。已最小复现。
2. **超时公式饿死 Serper 通道**：`timeout_ms × 0.00045` 给主通道每 provider 仅
   0.675s、人物探针 1.35s，而实测 Bocha 0.3–0.4s、Serper 1.7–2.8s——Serper 结构性
   必超时，3 次失败打开熔断器（60s），Bocha 偶发抖动时双通道全空 → 判
   web-lane-unavailable → 降级话术。
3. **预算超支 all-or-nothing 剥除**：人物探针批实测 11.4–29.6s（上限 10s），回执超时
   便把**已拿到手的全部 web 证据**剥掉（含 web lane 的 71 条），答案只剩降级话术。

## 修复（R1，commit 见日志）

1. `_utf8_truncated()`：截断后回退到完整字符边界，替换全部 4 处切片。
2. per-provider 超时：bocha ≥2.0s / serper ≥4.0s（随 timeout_ms 缩放），外层等待
   按 provider 分设（attempt + 0.5s 余量）。
3. 分级降级：仅 wall-time 超支 → 保留已到手的 web 证据（日志记录 late-but-valid）；
   资源类超支（调用数/重试/成本/尝试次数）→ 仍剥除。

## 验收标准与结果

| 标准 | 结果 |
|---|---|
| internal_error 0/3 | ✅ 0/3 |
| 早稻田关键点命中 ≥2/3 | ✅ 2/3（12.7s/12.4s，此栈首次答对：帕西尼创始人许晋诚） |
| 降级话术 0/3 | ❌ 1/3（冷缓存首轮） |
| demo 4 题仍全过 | ✅ 4/4（7.1/13.7/6.8/16.3s） |
| 新单测 14 项 | ✅ 14/14 |
| 既有回归 | ✅ 无新增失败（3 处失败经 stash 往返证实为 HEAD 既有） |

## 已知残差（下一切片候选）

冷缓存首轮（trace `f-xa59Ap`）：web lane 从缓存取到 71 条（provider 全
cache_hit、熔断关闭、无剥除告警），但 SSE 报「网络搜索 0 个结果」、答案仍为降级
话术——drop 发生在 read 层合并/充分性判定路径，与本 slice 三条链无关。第 2/3 轮
（全缓存命中）即正常。
