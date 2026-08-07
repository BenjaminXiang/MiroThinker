# 国先检索助手移动端响应式与会话交互设计

- Date: 2026-08-03
- Status: Approved for implementation planning
- Scope: Canonical V2 public `/chat` page served from `apps/admin-console/backend/static/chat.html`
- Related design: `docs/superpowers/specs/2026-08-02-chat-streaming-answer-design.md`
- Governing change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`

## 1. Context

The public chat page works at common portrait widths, but it is not yet a seamless mobile experience across iPhone, Android, landscape, short viewports, and software-keyboard transitions.

Observed behavior in the current implementation:

- The root shell uses `min-height: 100vh` and `minmax(320px, 1fr)`, so a short visual viewport forces the document itself to scroll.
- There is no `viewport-fit=cover`, dynamic viewport unit, safe-area padding, or `VisualViewport` enhancement.
- At `844×390`, the page grows to about 634 px and browser autofocus scrolls the header and example area off-screen.
- At a `390×500` keyboard-height simulation, the page grows to about 628 px and the composer is not reliably contained in the visible viewport.
- Every streaming chunk unconditionally scrolls the message pane to the bottom, so a user who scrolls upward cannot keep their reading position.
- The page focuses the input on load and after a turn, which may unexpectedly open or reopen the software keyboard.
- The composer uses a single-line input, which is unsuitable for longer mobile questions.
- There is only one width breakpoint and no explicit short-height or landscape behavior.

The redesign must improve perceived responsiveness without shortening answers or reducing retrieval and answer quality. The page should expose useful progress while keeping internal traces private, and it must continue using the existing SSE transport.

## 2. Product goals

1. Make `/chat` work predictably on modern iPhone, Android, tablet, laptop, and desktop viewports.
2. Keep the composer visible and usable when the software keyboard opens, closes, or changes size.
3. Keep document scrolling disabled; only the message pane may scroll during a conversation.
4. Preserve user reading intent during streaming instead of forcing every chunk to the bottom.
5. Improve the mobile information hierarchy after the first turn without degrading the desktop layout.
6. Preserve complete, high-quality answers and the existing progressive retrieval display.
7. Rename the public assistant to **国先检索助手** and use the provided 国先 logo as the assistant identity.
8. Keep the implementation local, reversible, framework-free, and compatible with the current static page.

## 3. Non-goals

- No retrieval, reranking, data, database, index, or LLM-prompt redesign.
- No React admin-console redesign.
- No public `ChatResponse` schema change.
- No adapter `answer` signature change.
- No SSE event-name or payload-shape change.
- No user-agent or phone-model allowlist.
- No claim that Linux browser emulation equals validation on a physical iPhone or Android device.
- No production promotion, active-pointer change, archive, or destructive cleanup.

## 4. User-facing identity

### 4.1 Name and copy

The public browser title and primary heading become **国先检索助手**. Public supporting copy should describe the user benefit rather than internal implementation policy:

- Header subtitle: technology-information retrieval, continuous follow-up, and current-Web supplementation.
- Welcome message: invite questions about companies, professors, papers, patents, technologies, and industries.
- Composer note: briefly state that answers combine the current knowledge base and public Web information, and that important facts can be checked through the displayed sources.

Internal names such as `Canonical V2`, release IDs, evidence IDs, or selector traces must remain absent from the public presentation.

### 4.2 Logo asset

The supplied source image is `/home/longxiang/MiroThinker/国先 logo.jpg`. A browser cannot use that local absolute path, so implementation must copy a stable derivative into the served static tree, using an ASCII filename such as:

`apps/admin-console/backend/static/assets/guoxian-logo.jpg`

For legibility at avatar size, implementation may create a square avatar derivative from the same supplied image that emphasizes the colored visual mark while retaining the original logo source as the design input. The rendered assistant avatar must:

- use an actual `<img>` with fixed dimensions and intrinsic width/height;
- have a neutral white tile, subtle border, and `object-fit` behavior that does not distort the mark;
- be decorative (`alt=""` or semantic equivalent) when the adjacent message semantics already identify the assistant;
- fall back to the readable text `国先` if the image fails to load.

The same asset may replace the current header `V2` mark for visual consistency. User and error avatars remain distinct.

## 5. Layout architecture

### 5.1 Root viewport contract

The document itself must not scroll. The shell owns exactly the visible viewport and uses four logical rows:

1. header;
2. example area or compact example toggle;
3. `minmax(0, 1fr)` message pane;
4. composer.

The fallback chain is:

1. `100vh` for old browsers;
2. `100dvh` for browsers with dynamic viewport units;
3. a throttled `VisualViewport`-derived CSS variable when available.

Representative shape:

```css
html,
body {
  width: 100%;
  height: 100%;
  overflow: hidden;
}

.shell {
  height: 100vh;
  height: 100dvh;
  height: var(--app-height, 100dvh);
  min-height: 0;
  overflow: hidden;
  grid-template-rows: auto auto minmax(0, 1fr) auto;
}

.messages {
  min-height: 0;
  overflow-y: auto;
}
```

`VisualViewport` is progressive enhancement, not the only keyboard strategy. Its `resize` and `scroll` events, plus window `resize` and `orientationchange`, update `--app-height` and any required top offset through one `requestAnimationFrame` scheduler. This prevents synchronous layout work for every browser event.

### 5.2 Safe areas

Use `env(safe-area-inset-top)`, `env(safe-area-inset-right)`, `env(safe-area-inset-bottom)`, and `env(safe-area-inset-left)` on the outer header/composer surfaces. Base padding and safe-area padding must be combined once rather than applied at nested levels.

The composer must remain above the iPhone Home Indicator. Header content must not enter a notch or dynamic-island area. Android browsers that return zero insets follow the ordinary base padding.

### 5.3 Geometry-first adaptation

Responsive behavior is selected by available width, height, orientation, hover capability, and pointer precision. It must not inspect the browser user agent or maintain device-specific branches.

- Desktop and tablet keep the current centered, spacious composition.
- Phone portrait uses edge-to-edge surfaces and smaller spacing.
- Phone landscape and short-height viewports use a compact header and collapsed example area.
- Width rules prevent horizontal document overflow at 320 px.
- Height rules protect the message pane and composer when vertical space is scarce.

## 6. Conversation presentation state

Use one small explicit presentation state machine, separate from semantic chat-session state:

- `landing`: no user turn has been submitted; examples are expanded.
- `conversation`: at least one user turn exists; examples are collapsed and the header is compact on small screens.
- `demo-expanded`: the user explicitly reopens examples during a conversation.

Transitions:

- initial load → `landing`;
- first successful submit attempt → `conversation` immediately, before network completion;
- “示例问题” toggle → `demo-expanded`;
- selecting an example or closing examples → `conversation`;
- short landscape or very short viewport → compact visual treatment regardless of semantic session state.

This state is DOM-only. It must not modify the backend session, displayed entity set, referent binding, constraints, or multi-turn traversal semantics.

## 7. Composer and keyboard behavior

### 7.1 Textarea

Replace the single-line input with an auto-growing `<textarea>`:

- one line initially;
- grow up to four visible lines;
- after four lines, scroll internally rather than pushing the message pane away;
- preserve the existing 500-character limit;
- reset height after send;
- remain usable at 320 px width.

Keyboard semantics:

- desktop/fine-pointer environment: `Enter` sends and `Shift+Enter` inserts a newline;
- touch/coarse-pointer environment: the send button is always the reliable send action, and Enter may insert a newline;
- IME composition must never trigger an accidental send;
- disabled and pending states remain accessible.

### 7.2 Focus lifecycle

Remove unconditional focus on page load. Do not automatically reopen the mobile software keyboard after an answer, stop, or error.

On desktop, focus may be restored after sending only when that is consistent with the user’s previous focus and pointer mode. On touch devices, focus remains under explicit user control. Orientation or viewport changes must not steal focus.

## 8. Streaming scroll behavior

Replace unconditional `scrollToLatest()` calls with a scroll-follow controller.

State:

- `following`: the message pane is within a small threshold of the bottom;
- `detached`: the user has intentionally scrolled above that threshold.

Rules:

1. Submitting a new user message explicitly returns to `following` and reveals the new turn.
2. Streaming chunks auto-follow only if the pane was already following before the DOM update.
3. User wheel, touch, keyboard, or scrollbar movement away from the bottom switches to `detached`.
4. While detached, new content does not move the reading position.
5. A visible “回到最新” control appears while detached and new content exists.
6. Pressing the control scrolls to the bottom and restores `following`.
7. Final-answer reconciliation, stop, error, citation insertion, and example collapse must preserve the same intent rule and must not steal the scroll position.
8. Use `requestAnimationFrame` to batch streaming scroll updates.

The control must be reachable by keyboard and have a touch target of at least 44×44 CSS pixels.

## 9. Content containment and touch targets

- Assistant bubbles may use the available width but must not exceed the message pane.
- Long URLs and unbroken text wrap without widening the document.
- Code blocks and wide tables scroll inside their own content region.
- Images, preformatted content, citations, and details elements use `max-width: 100%`.
- “查看检索过程”, “查看依据”, “停止生成”, “示例问题”, “回到最新”, and the send button have touch targets of at least 44×44 CSS pixels.
- Hover styling is supplementary; all actions remain understandable without hover.
- Focus-visible styling covers the new textarea and controls.

## 10. Streaming correctness guardrail

Responsive work must preserve the existing answer contract while making the same final synthesis visible progressively:

- when the provider is healthy and safe streamable content exists, at least one safe answer chunk must become public before the complete final result is available and before `done` is emitted; chunking must not be simulated after the complete answer is already available;
- incremental text and the successful final DOM must represent the same complete synthesis as the existing final result;
- selected scope, citations, and next-turn context continue to be accepted by the existing final parser;
- neither raw SSE nor the rendered DOM may expose internal identifiers or structural fields;
- the server reuses or extends deterministic public-output sanitization, with browser handling retained as defense in depth;
- focused regressions cover representative beginning, middle, and end cross-chunk boundaries plus ordinary Chinese and Markdown;
- answers are not shortened, no additional LLM call is introduced, and public SSE event names and payload schemas remain unchanged.

## 11. Error, retry, cancellation, and degradation behavior

- Browsers without `VisualViewport` use `100dvh`, then `100vh`; zero safe-area values fall back to ordinary padding.
- Logo load failure displays a compact text fallback without collapsing layout.
- A failure before any answer text is public may use the existing bounded retry behavior.
- Once answer text is public, a later failure preserves that text but never appends text from another attempt.
- If the server observes stop, disconnect, or cancellation before commit, that turn is not committed as a successful session turn or used as next-turn context; previously committed context is unchanged. A client disconnect that the server does not observe before commit carries no non-commit guarantee.
- Final reconciliation, stop, error, resize, and orientation changes preserve scroll intent and do not reset the conversation.

## 12. Contract and artifact ownership

This is a successor UI slice under the existing `rebuild-canonical-v2-knowledge-platform` OpenSpec change. The grounded-answer contract records progressive completeness and public-output safety; the evidence-first contract records the observable non-commit result when the server observes stop, disconnect, or cancellation before commit, without guaranteeing non-commit for a client disconnect the server does not observe before commit. The design, task, acceptance, verification contract, and slice contract describe those outcomes without prescribing private classes, interfaces, locking, or chunk algorithms.

After implementation and verification, append fresh evidence to the root verification ledger and `change-log.md`; older evidence is not proof of this slice.

## 13. Verification strategy

### 13.1 Focused deterministic checks

Verify observable behavior through existing public paths:

- identity, logo fallback, viewport containment, textarea growth, IME submission, and touch/desktop Enter behavior;
- scroll detachment, “回到最新”, final reconciliation, stop, error, resize, and orientation recovery;
- when the provider is healthy and safe streamable content exists, at least one safe answer chunk becomes public before the complete final result is available and before `done`; streaming is not simulated after completion and preserves final-result consistency, representative cross-chunk public-output safety, normal Chinese/Markdown, and retry non-mixing;
- non-commit when the server observes stop, disconnect, or cancellation before commit, with no non-commit guarantee for a client disconnect the server does not observe before commit;
- unchanged public SSE names and payload shapes, no answer truncation, and no additional LLM call.

### 13.2 Browser matrix

Validate at least:

- Android/small portrait: `320×568`, `360×640`, `360×800`, `412×915`;
- iPhone portrait: `375×667`, `390×844`, `430×932`;
- phone landscape: `667×375`, `844×390`;
- tablet: `768×1024`, `1024×768`;
- desktop: `1280×720`, `1440×900`.

For each applicable viewport verify:

- no horizontal document overflow and no document-level scrolling;
- the composer remains usable within the visual viewport and safe area during keyboard and rotation simulations;
- long answers, links, Markdown, code, citations, and media remain contained;
- controls remain keyboard accessible and touch targets are at least 44 px;
- examples collapse and can be restored;
- users can read earlier content during streaming and “回到最新” restores following;
- when the server observes stop, disconnect, or cancellation before commit, the interrupted turn does not enter successful session context; no non-commit guarantee applies to an unobserved client disconnect.

Run every browser-runner invocation from the repository root through `uv run --project apps/miroflow-agent python`; that uv-managed project declares Playwright.

Before the production-like pass, record lightweight provenance that the service on `127.0.0.1:18188` was launched from the current worktree and is serving its current Candidate code. An HTTP response from a pre-existing process is not sufficient. If establishing that provenance requires starting or restarting the service, first obtain explicit user authorization for that one action; after authorization, reuse the existing Candidate serving command from the current worktree and wait until `GET /api/health` returns HTTP 200. If provenance cannot be confirmed or authorization is not granted, record the production browser gate as blocked/skipped and do not count results from the old process as Candidate evidence.

On that confirmed current Candidate, preflight candidate real queries through the existing public chat SSE path. Select and record a query only after it returns HTTP 200 and exposes at least one progressive `answer_chunk` before the final result and `done`, then pass that exact query to the runner. Non-binding candidates may include `请介绍丁文伯教授的研究方向` and `深圳无界智航科技有限公司是做什么的`; the observed preflight result, not either example, is authoritative. A known business badcase is not the fixed S12G UI query or an S12G UI blocker. If no candidate passes, record the gate as blocked/skipped rather than running against an old service or reporting a UI-runner failure.

Use the single repository-owned Chromium runner for the production-like pass:

```bash
: "${S12G_REAL_SSE_QUERY:?export the query recorded by the current-Candidate preflight}"
uv run --project apps/miroflow-agent python .agents/runs/rebuild-canonical-v2-knowledge-platform/s12g/browser_acceptance.py \
  --url http://127.0.0.1:18188/chat \
  --browser chromium \
  --real-sse-query "$S12G_REAL_SSE_QUERY" \
  --output-dir .agents/runs/rebuild-canonical-v2-knowledge-platform/s12g/artifacts
```

Playwright WebKit is optional only when its browser binary is already available in the project environment; otherwise record it as not run.

### Rollout-conditional native-device gate (not required for Candidate)

Linux emulation is not physical Safari/Chrome validation. Before production-like rollout, perform a short smoke on one recent iPhone and one recent Android device covering initial load, keyboard dismissal, long-answer scrolling, return to latest, stop, orientation change, and safe-area clearance.

## 14. Rollback

Restore the previous chat page, focused tests, logo derivative, and streaming changes as one reviewable slice. Backend retrieval, stored data, release pointers, public response schemas, and SSE event vocabulary remain unchanged; record rollback evidence without rewriting earlier verification history.

## 15. Acceptance summary

The design is accepted when **国先检索助手** is responsive across the viewport matrix, IME submission is reliable, streaming respects reading position, the supplied brand is visible, at least one safe answer chunk becomes public before the complete final result and `done` when the provider is healthy and safe streamable content exists, streaming is not simulated after completion, and the same complete safe answer reaches the successful final DOM without retry mixing. A turn is not committed when the server observes stop, disconnect, or cancellation before commit; no non-commit guarantee applies to an unobserved client disconnect.
