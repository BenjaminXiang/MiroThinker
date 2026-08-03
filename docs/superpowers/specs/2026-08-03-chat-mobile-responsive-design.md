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
- be decorative when the adjacent message semantics already identify the assistant;
- fall back to the text `国先` if the image fails to load.

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

The responsive implementation must not worsen answer correctness or public-output safety. Investigation found two existing streaming risks that must be made explicit in the implementation plan:

1. Public-text checks currently operate on individual chunks. A sensitive token split across multiple chunks can evade a per-chunk regex and become visible after accumulation. Any partial text that becomes visible must therefore pass a stateful/cumulative public-copy gate across arbitrary chunk boundaries, including text retained after stop or network failure.
2. The structured final synthesis contract includes selected claim/entity indexes. The streaming path must preserve the same validated selection and answer-scope semantics as the synchronous path; streaming must not silently downgrade the final renderer result to plain text.

These are correctness prerequisites around the already-shipped streaming seam. They do not authorize a new event protocol or broad backend refactor. The implementation plan must first add focused reproductions, then make the smallest contract-preserving correction. If a fix would require changing the public schema or SSE protocol, implementation must stop for a revised design decision.

## 11. Error and degradation behavior

- Browsers without `VisualViewport` use `100dvh`, then `100vh`; the composer remains part of the fixed shell.
- Browsers returning zero safe-area values use ordinary padding.
- Logo load failure displays a compact text fallback without collapsing layout.
- Stream interruption preserves only partial text that has passed the public-copy gate and labels it as interrupted.
- User stop preserves only safe partial text and does not commit an incomplete answer as a successful semantic turn.
- Final-answer replacement preserves current scroll intent.
- Orientation changes require no reload and must not duplicate listeners or reset the conversation.

## 12. Contract and artifact ownership

This is a successor UI slice under the existing `rebuild-canonical-v2-knowledge-platform` OpenSpec change, not a new OpenSpec change.

Before implementation, update:

- `openspec/changes/rebuild-canonical-v2-knowledge-platform/specs/grounded-progressive-answer/spec.md` with observable viewport, focus, scroll-follow, partial-stream safety, and branding scenarios;
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/design.md` with the presentation-state boundary and streaming guardrail;
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/tasks.md` with one unchecked successor task;
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/acceptance.md` with the mobile, keyboard, scroll, branding, and cross-chunk acceptance matrix;
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification-contract.md` with the exact browser and stream-safety evidence requirements;
- a new independently reviewable slice contract under `.agents/runs/rebuild-canonical-v2-knowledge-platform/slices/`.

After implementation and verification, append evidence to the root verification ledger and `change-log.md`. Do not rewrite older S9J/S11/S12D/S12F evidence as proof of this slice.

`evidence-first-query-orchestration/spec.md` remains unchanged unless implementation unexpectedly requires cancellation, reconnection, session-commit, or transport-semantics changes.

## 13. Verification strategy

### 13.1 Deterministic tests

Add focused tests for:

- public name, browser title, header identity, static logo availability, image fallback, and absence of public `Canonical V2` branding;
- valid inline JavaScript;
- textarea growth, reset, four-line cap, IME handling, and desktop/touch Enter semantics;
- presentation-state transitions;
- VisualViewport listener setup, requestAnimationFrame coalescing, and fallback behavior;
- near-bottom detection, user detachment, no forced chunk scroll, return-to-latest, final replacement, stop, and error behavior;
- arbitrary character/chunk splitting of unsafe public tokens;
- preservation of final selected claim/entity indexes in the streaming path.

Reuse current tests where appropriate:

- `apps/admin-console/tests/test_canonical_v2_real_preview_ui.py`;
- focused SSE tests in `apps/admin-console/tests/test_canonical_v2_chat_http_adapter.py`;
- the stream-buffer harness, moved or superseded by a successor-slice test rather than treated as S12F data-rebuild evidence.

### 13.2 Browser matrix

Validate at least:

- Android/small portrait: `320×568`, `360×640`, `360×800`, `412×915`;
- iPhone portrait: `375×667`, `390×844`, `430×932`;
- phone landscape: `667×375`, `844×390`;
- tablet: `768×1024`, `1024×768`;
- desktop: `1280×720`, `1440×900`.

For each applicable viewport verify:

- no horizontal document overflow;
- document scroll position remains fixed;
- composer remains within the visual viewport;
- safe-area padding does not duplicate or clip controls;
- the keyboard-height simulation keeps the composer usable;
- Markdown, long links, code blocks, citations, and long answers stay contained;
- touch targets are at least 44 px;
- rotation/resize needs no reload;
- examples collapse and can be restored;
- the user can scroll upward during a real SSE answer without being dragged down;
- “回到最新” restores following;
- stop and interruption preserve only safe partial text.

Use Chromium with bounded concurrency to avoid browser-daemon resource exhaustion. Playwright WebKit is optional only if its browser binary can be installed in the project environment without changing global state. Otherwise record it as not run.

### 13.3 Physical-device smoke

Linux emulation is not physical Safari/Chrome validation. Before production-like rollout, perform a five-minute smoke on one recent iPhone and one recent Android device covering:

- initial load;
- first submit and keyboard dismissal;
- long streaming answer while scrolling up;
- return to latest;
- stop generation;
- orientation change;
- safe-area and Home Indicator clearance.

## 14. Rollback

The slice is reversible:

- restore the previous `chat.html` and focused tests;
- remove the new static logo derivative;
- leave backend retrieval, data, release pointers, and public response schemas untouched;
- append rollback evidence rather than rewriting prior verification records.

## 15. Acceptance summary

The design is accepted when **国先检索助手** remains fully usable across the viewport matrix, the composer survives software-keyboard changes, only the message pane scrolls, streaming respects the user’s reading position, the supplied logo identifies assistant responses, no public-output or selected-scope regression is introduced, and all changes remain within the existing Candidate chat contract.
