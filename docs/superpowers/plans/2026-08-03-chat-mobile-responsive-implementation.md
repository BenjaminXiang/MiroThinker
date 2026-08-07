# 国先检索助手移动端响应式与流式交互 Implementation Plan

**Goal:** 在不缩短答案、不降低检索质量、不增加 LLM 调用、不改变公开 Chat/SSE schema 的前提下，使 `/chat` 在桌面、平板、iPhone 与 Android 的常见尺寸和横竖屏下稳定呈现同一份完整 synthesis，并保证流式公开文本、重试、取消、输入与阅读体验安全一致。

**Architecture:** 复用现有最终结果解析与提交边界；服务端确定性清理公开文本，浏览器做 defense in depth。契约只描述可观察结果，不绑定 JSON 字段顺序、私有类型或方法、并发策略、分块算法和内部调度细节。

**Tech Stack:** Python 3.12、FastAPI、现有 SSE adapter、pytest、原生 HTML/CSS/JavaScript、Node.js 行为测试、Playwright Chromium、OpenSpec。

---

## 执行约束与五类结果

1. **同一完整 synthesis：** provider 正常且存在可安全流式内容时，至少一个安全 `answer_chunk` 必须在完整 final result 可用且 `done` 发出前公开，不得等完整答案可用后再模拟分块；渐进内容与最终 DOM/result 一致；不得截短答案、减少证据、降低检索质量或增加 LLM 调用。
2. **公开文本安全：** raw SSE 与 DOM 都不得暴露内部标记；代表性的开头、中间、结尾跨 chunk 边界均须覆盖，同时保留正常中文与 Markdown。
3. **轮次隔离：** 输出前失败可按既有预算重试；输出后不得混入另一 attempt；服务端在 commit 前观察到 stop、disconnect 或 cancellation 时，该轮不得提交到成功 session 或后续上下文；服务端在 commit 前未观察到的客户端断开不作 non-commit 保证。
4. **移动交互与阅读意图：** 13 个 viewport、safe area、软键盘几何、rotation、textarea、IME、focus、following/detached 与长内容约束均以用户可见行为验收。
5. **公开品牌：** 标题、header、助手头像、logo fallback 与用户文案统一为“国先检索助手”并保持可读、可访问。

以下不变量贯穿所有 Task：

- 公开 `answer_stream()`、`ChatResponse`、adapter `answer` 签名、SSE event 名称/顺序/payload 与 semantic turn order 不变。
- 不改变 query、retrieval、ranking、Web、answer-length、provider-call budget 或 typed fallback 语义。
- 只追加 S12G 契约与证据，不改写旧的 S9J/S11/S12D/S12F verification evidence。
- Task 2、3 先建立流式正确性，再进行视觉与交互改动；`chat.html` 同一时间只允许一个 writer。
- Candidate 自动门不包含真机；真机状态必须如实披露，只有 rollout 明确要求时才执行。

## Task 1：正式化 S12G 的结果契约

**Files:**
- Modify: `docs/superpowers/specs/2026-08-03-chat-mobile-responsive-design.md`
- Modify: `docs/superpowers/plans/2026-08-03-chat-mobile-responsive-implementation.md`
- Modify: `openspec/changes/rebuild-canonical-v2-knowledge-platform/specs/grounded-progressive-answer/spec.md`
- Modify: `openspec/changes/rebuild-canonical-v2-knowledge-platform/specs/evidence-first-query-orchestration/spec.md`
- Modify: `openspec/changes/rebuild-canonical-v2-knowledge-platform/design.md`
- Modify: `openspec/changes/rebuild-canonical-v2-knowledge-platform/tasks.md`
- Modify: `openspec/changes/rebuild-canonical-v2-knowledge-platform/acceptance.md`
- Modify: `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification-contract.md`
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/slices/s12g-chat-mobile-streaming-ux.md`

- [ ] 将五类结果写成可观察的 SHALL/MUST 场景，只规定 WHAT，不预选字段顺序、私有结构、切分规则或执行策略。
- [ ] 保持 `12.5j` 与所有新增 S12G acceptance 未勾选；本 Task 只 formalize 契约，不声明实现、浏览器或真机证据。
- [ ] 保留精确 rollout 标题，并明确其不阻塞 Candidate。
- [ ] 从仓库根目录运行契约检查：

  ```bash
  openspec validate rebuild-canonical-v2-knowledge-platform --strict
  git diff --check
  ```

- [ ] 自审九个文档的术语、范围和未勾选状态一致。

## Task 2：同一 synthesis 的安全渐进输出与 retry 不混流

**Files:**
- Modify: `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py`
- Modify: `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_answer.py`
- Modify: `apps/miroflow-agent/tests/canonical_v2/test_knowledge_serving_isolated.py`
- Modify: `apps/miroflow-agent/tests/canonical_v2/test_knowledge_answer_implementation_closure.py`

- [ ] 先添加 focused RED，证明 provider 正常且存在可安全流式内容时，至少一个安全 `answer_chunk` 在完整 final result 可用且 `done` 发出前公开，而不是完整答案可用后模拟分块；渐进公开内容来自同一份最终 synthesis，最终结果与累计公开内容一致，并继续满足既有 accepted grounding scope。
- [ ] 覆盖输出前失败可按既有预算重试，且用户只看到一个 attempt；一旦有公开输出，后续失败不得拼接或替换成另一 attempt，也不得形成成功结果。
- [ ] 覆盖同步、流式、timeout 与 plain-text degradation 的既有行为，确认回答不截短、没有额外 LLM 调用、公开 SSE/schema 不变。
- [ ] 在现有解析与渲染路径内选择最小实现；测试只绑定上述结果，不绑定私有函数或中间状态。
- [ ] 运行两个 focused test files，随后审查 provider budget、答案完整性和公开契约。

## Task 3：public-output sanitation 与 server-observed pre-commit interruption non-commit

**Files:**
- Create: `apps/admin-console/tests/chat_ui_behavior_test.mjs`
- Modify: `apps/admin-console/backend/services/canonical_v2_chat.py`
- Modify: `apps/admin-console/backend/api/canonical_v2_chat.py`
- Modify: `apps/admin-console/backend/static/chat.html`
- Modify: `apps/admin-console/tests/test_canonical_v2_chat_http_adapter.py`
- Modify: `apps/admin-console/tests/test_canonical_v2_real_preview_ui.py`

- [ ] 添加 focused RED，直接检查 raw SSE 和浏览器 DOM 均拒绝内部标记，同时保留普通中文、链接与 Markdown 的正常展示。
- [ ] 用代表性的开头、中间、结尾跨 chunk 边界覆盖公开文本安全；不要把验收绑定到某一种行、句子或 Markdown 切分算法。
- [ ] 服务端执行确定性清理，浏览器保留 defense in depth；两层都以最终可观察的公开 copy 为准。
- [ ] 覆盖服务端在 commit 前观察到 stop、disconnect 或 cancellation 时，该轮不进入成功 session，也不进入下一轮上下文；已经提交的上下文保持不变。服务端在 commit 前未观察到的客户端断开不作 non-commit 保证。
- [ ] 覆盖正常完成、server error、EOF，以及服务端在 commit 前观察到 stop、disconnect 或 cancellation 后的下一轮恢复，确认已观察中断的旧轮残留不进入新轮或 DOM；不对服务端在 commit 前未观察到的客户端断开作额外保证。
- [ ] 保持既有 SSE event/payload 与 answer scope；不新增 LLM 调用，也不以截短内容规避风险。
- [ ] 运行两个 focused Python test files 和生产页面 Node harness，再审查取消与成功提交的可观察边界。

## Task 4：更新国先品牌、logo、助手头像和用户文案

**Files:**
- Create: `apps/admin-console/backend/static/assets/guoxian-logo.jpg`
- Modify: `apps/admin-console/backend/static/chat.html`
- Modify: `apps/admin-console/tests/chat_ui_behavior_test.mjs`
- Modify: `apps/admin-console/tests/test_canonical_v2_real_preview_ui.py`

- [ ] 断言 `<title>`、header 和 assistant identity 统一显示“国先检索助手”。
- [ ] header logo 与 assistant avatar 使用批准的 `guoxian-logo.jpg`；相邻消息语义已表达 assistant identity 时，avatar 使用 `alt=""` 或语义等价的 decorative 处理；图片保留 intrinsic `width`/`height`，加载失败时显示可读的“国先”文字 fallback。
- [ ] welcome 与 composer note 使用面向用户的文案，不暴露内部实现术语，也不承诺未实现的阶段展示。
- [ ] 验证静态资源返回正确的 JPEG content type，窄屏、深浅背景与破图状态下品牌仍清晰可读。
- [ ] 运行品牌相关 Python/Node focused checks。

## Task 5：实现 13 个 viewport、safe area 与根级滚动约束

**Files:**
- Modify: `apps/admin-console/backend/static/chat.html`
- Modify: `apps/admin-console/tests/chat_ui_behavior_test.mjs`
- Modify: `apps/admin-console/tests/test_canonical_v2_real_preview_ui.py`

- [ ] 覆盖固定矩阵：`320×568`、`360×640`、`360×800`、`412×915`、`375×667`、`390×844`、`430×932`、`667×375`、`844×390`、`768×1024`、`1024×768`、`1280×720`、`1440×900`。
- [ ] 使用 `viewport-fit=cover`、safe-area padding 和动态可见高度，使 header、messages 与 composer 在手机、平板、桌面及两个短横屏尺寸中保持可达。
- [ ] root 保持固定，messages 区承担纵向滚动；软键盘几何变化和 portrait/landscape rotation 后 composer 仍在可见区域。
- [ ] 允许使用 CSS dynamic viewport 与 `VisualViewport` 方向实现；resize/orientation burst 后只产生一次用户可观察的有效布局响应，提交也只产生一次有效响应，不出现重复提交、重复状态转换或几何抖动。
- [ ] 覆盖 320px、短横屏和长 URL/code/table/image，确保 document 无横向溢出，局部内容可独立滚动或换行。
- [ ] 运行 viewport 的 Node/Python focused checks。

## Task 6：实现页面状态、textarea、IME 与 focus 生命周期

**Files:**
- Modify: `apps/admin-console/backend/static/chat.html`
- Modify: `apps/admin-console/tests/chat_ui_behavior_test.mjs`
- Modify: `apps/admin-console/tests/test_canonical_v2_real_preview_ui.py`

- [ ] 覆盖 `landing`、`conversation` 与 `demo-expanded`：首轮提交收起示例，用户可显式重新展开，失败或取消不重置已有 conversation。
- [ ] textarea 保留 `maxlength="500"`，空值不发送，自动增长最多四行且不遮挡消息区。
- [ ] desktop/fine pointer 使用 Enter 发送、Shift+Enter 换行；IME composition 期间 Enter 不发送；touch/coarse pointer 以发送按钮为主。
- [ ] 页面加载、流结束、stop 或 error 后不自动抢占移动端 focus；用户显式点击输入区仍可正常聚焦。
- [ ] Node harness 从生产 `chat.html` 执行公开交互行为，并由 Python 静态测试覆盖必要 markup。
- [ ] 运行 input/presentation focused checks。

## Task 7：实现 following/detached 与长内容阅读保护

**Files:**
- Modify: `apps/admin-console/backend/static/chat.html`
- Modify: `apps/admin-console/tests/chat_ui_behavior_test.mjs`
- Modify: `apps/admin-console/tests/test_canonical_v2_real_preview_ui.py`

- [ ] 用户位于底部时保持 `following`，渐进更新可继续跟随；用户上滑后进入 `detached`，后续 chunk 不把阅读位置拖回底部。
- [ ] detached 时显示“回到最新”；只有用户点击后才恢复到底部和 following。
- [ ] final replacement、citation/details、stop、error、EOF 与下一轮恢复都保留当前阅读意图，不把内容增长误判成用户操作。
- [ ] 发送、停止、示例和“回到最新”等关键交互目标至少 `44×44` CSS px，并有 accessible name。
- [ ] 长 URL、代码、表格、图片和长回答不得撑破 document；必要的横向滚动仅发生在局部容器。
- [ ] 运行 scroll/containment 的 Node/Python focused checks。

## Task 8：建立单一 Playwright runner 的响应式与真实交互验收

**Files:**
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12g/browser_acceptance.py`
- Create as generated evidence only during execution: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12g/artifacts/*`
- Modify: `apps/admin-console/tests/test_canonical_v2_real_preview_ui.py` only if a deterministic local fixture is required

- [ ] `--self-test` 使用受控 invalid/valid 页面证明 runner 能发现 document overflow、过小 target、detached 后错误滚动和 rotation/recovery 缺陷。
- [ ] 所有 browser runner Python 命令从仓库根目录使用 `uv run --project apps/miroflow-agent python`，由声明 Playwright 的项目环境执行。
- [ ] 生产模式只使用同一个 Chromium runner，覆盖全部 13 个 viewport、portrait/landscape 恢复、长内容 containment、landing/conversation/demo 和 44×44 targets；Candidate 命令不绑定 worker-count 参数。
- [ ] 以受控 viewport 高度变化模拟软件键盘 geometry；报告必须称为几何模拟，不得称为真机键盘通过。
- [ ] 真实 SSE 场景等待渐进内容，用户上滑进入 detached 后确认后续更新不改变阅读位置，点击“回到最新”才恢复 following。
- [ ] 失败时仅保存必要的 screenshot、sanitized metrics 和 console log；production gate 只使用 Task 9 中的单一命令。
- [ ] 运行 runner self-test：

  ```bash
  uv run --project apps/miroflow-agent python .agents/runs/rebuild-canonical-v2-knowledge-platform/s12g/browser_acceptance.py \
    --browser chromium \
    --self-test \
    --output-dir .agents/runs/rebuild-canonical-v2-knowledge-platform/s12g/artifacts
  ```

### Rollout-conditional native-device gate (not required for Candidate)

Linux Chromium 与软键盘几何模拟不等价于 iPhone Safari 或 Android Chrome 真机。Candidate 必须如实记录真机未运行及 confidence impact；只有 rollout 明确要求时，才分别执行短时真机 smoke，其结果不回溯阻塞已满足自动化契约的 Candidate。

## Task 9：focused regression、单一 browser gate 与 Candidate evidence 收口

**Files:**
- Modify: `openspec/changes/rebuild-canonical-v2-knowledge-platform/tasks.md`
- Modify: `openspec/changes/rebuild-canonical-v2-knowledge-platform/acceptance.md`
- Modify: `openspec/changes/rebuild-canonical-v2-knowledge-platform/change-log.md`
- Modify: `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12g/receipt.md`
- Modify: `.agents/runs/rebuild-canonical-v2-knowledge-platform/slices/s12g-chat-mobile-streaming-ux.md`

- [ ] 在任何针对 `127.0.0.1:18188` 的 production browser gate 前，记录轻量 provenance，证明该服务由当前 worktree 启动并运行当前 Candidate 代码；仅看到既有进程返回 HTTP 200 不足以作为证明。
- [ ] 若确认 provenance 需要启动或重启服务，先向用户取得该次动作的明确授权；获得授权后复用当前 worktree 的既有 Candidate serving 命令，并等待 `GET /api/health` 返回 HTTP 200。本文档不预先授权该动作。
- [ ] 只在已确认的当前 Candidate 上，通过现有 public chat SSE 路径对候选真实查询做轻量 preflight；候选必须返回 HTTP 200，并在 final result 与 `done` 前产生至少一个渐进 `answer_chunk`。记录实际通过的查询，并将它导出为 `S12G_REAL_SSE_QUERY`。
- [ ] `请介绍丁文伯教授的研究方向` 与 `深圳无界智航科技有限公司是做什么的` 仅为非绑定候选；实际 preflight 结果为准。不得固定使用已知业务 badcase，也不得把它变成 S12G UI blocker。
- [ ] 无法确认 current-worktree provenance、未获所需授权或没有候选查询通过 preflight 时，将 production browser gate 记录为 blocked/skipped；不得运行旧服务或把旧进程结果计为 Candidate 证据。
- [ ] 在 fresh shell 中 fail fast 运行 focused Python、Node、最终 `--self-test`、唯一 production browser、strict OpenSpec、diff 与 status；Task 9 必须在 production gate 紧前重新运行同一 runner 的 `--self-test`：

  ```bash
  set -euo pipefail
  ROOT=/home/longxiang/MiroThinker/.worktrees/canonical-v2-s11-consolidation

  cd "$ROOT/apps/miroflow-agent"
  uv run pytest -q -n0 \
    tests/canonical_v2/test_knowledge_serving_isolated.py \
    tests/canonical_v2/test_knowledge_answer_implementation_closure.py

  cd "$ROOT/apps/admin-console"
  uv run pytest -q -n0 \
    tests/test_canonical_v2_chat_http_adapter.py \
    tests/test_canonical_v2_real_preview_ui.py
  node tests/chat_ui_behavior_test.mjs

  cd "$ROOT"
  : "${S12G_REAL_SSE_QUERY:?export the query recorded by the current-Candidate preflight}"
  uv run --project apps/miroflow-agent python .agents/runs/rebuild-canonical-v2-knowledge-platform/s12g/browser_acceptance.py \
    --browser chromium \
    --self-test \
    --output-dir .agents/runs/rebuild-canonical-v2-knowledge-platform/s12g/artifacts
  uv run --project apps/miroflow-agent python .agents/runs/rebuild-canonical-v2-knowledge-platform/s12g/browser_acceptance.py \
    --url http://127.0.0.1:18188/chat \
    --browser chromium \
    --real-sse-query "$S12G_REAL_SSE_QUERY" \
    --output-dir .agents/runs/rebuild-canonical-v2-knowledge-platform/s12g/artifacts
  openspec validate rebuild-canonical-v2-knowledge-platform --strict
  git diff --check
  git status --short --untracked-files=all
  ```

- [ ] 任一自动门失败或 production browser gate blocked/skipped 时，保持 `12.5j`、acceptance 与 slice 状态未完成；不得用 receipt 覆盖失败、阻塞或缺失证据。
- [ ] 全部自动门通过后，才更新 `tasks.md`、`acceptance.md`、`change-log.md`、`verification.md`、receipt 与 slice 状态，逐项引用命令结果和 artifact 路径。
- [ ] 证据记录 current-worktree serving provenance、任何一次性启动/重启授权、`/api/health` readiness、preflight HTTP/SSE 结果与实际查询，并明确区分自动化、真实 SSE 与 rollout 真机状态；未运行项写明原因和 confidence impact。
- [ ] 自审答案完整性、LLM 调用预算、公开 SSE/schema、旧 evidence、旧服务隔离与工作树范围均未改变。

## 最终验收表

- [ ] provider 正常且存在可安全流式内容时，至少一个安全 `answer_chunk` 在完整 final result 可用且 `done` 发出前公开，不得等完整答案可用后模拟分块；渐进内容来自同一完整 synthesis 并与最终 DOM/result 一致；答案不截短、不减少证据、不新增 LLM 调用，公开 SSE/schema 不变。
- [ ] raw SSE 与 DOM 在代表性的开头、中间、结尾跨 chunk 边界下均安全，同时保留正常中文与 Markdown。
- [ ] 输出前 retry 只呈现一个 attempt；输出后不混流；服务端在 commit 前观察到 stop、disconnect 或 cancellation 时，该轮不提交且下一轮不继承其内容；服务端在 commit 前未观察到的客户端断开不作 non-commit 保证。
- [ ] 13 个 viewport、safe area、软件键盘 geometry、rotation、textarea、IME、focus、following/detached、44×44 target 与长内容 containment 通过。
- [ ] “国先检索助手”的 title、header、avatar、logo fallback 与用户文案清晰、可读、可访问；rollout 真机状态如实披露。

## Rollback

- 流式或 session 行为回退时，同步回退对应 focused tests，保持公开 SSE/schema、数据与既有 committed session 不变。
- 前端回退 `chat.html`、对应 Node/Python tests 与 browser runner；品牌回退时同时处理批准 logo 资源与 fallback。
- 本 slice 不包含数据库、索引、schema 或数据迁移；回退不应删除现有数据或旧 verification evidence。
