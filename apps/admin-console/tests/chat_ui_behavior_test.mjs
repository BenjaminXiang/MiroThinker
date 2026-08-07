import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

class FakeNode {
  constructor(tagName, ownText = "") {
    this.tagName = tagName.toUpperCase();
    this.children = [];
    this.className = "";
    this.parentNode = null;
    this.attributes = new Map();
    this._listeners = new Map();
    this._ownText = ownText;
  }

  append(...nodes) {
    for (const value of nodes) {
      const node = typeof value === "string" ? new FakeNode("#text", value) : value;
      node.parentNode = this;
      this.children.push(node);
    }
  }

  replaceChildren(...nodes) {
    for (const child of this.children) child.parentNode = null;
    this.children = [];
    this._ownText = "";
    this.append(...nodes);
  }

  setAttribute(name, value) {
    this.attributes.set(String(name), String(value));
  }

  getAttribute(name) {
    const key = String(name);
    return this.attributes.has(key) ? this.attributes.get(key) : null;
  }

  addEventListener(type, listener, options = {}) {
    const key = String(type);
    const listeners = this._listeners.get(key) || [];
    listeners.push({
      listener,
      once: typeof options === "object" && options !== null && options.once === true,
    });
    this._listeners.set(key, listeners);
  }

  dispatchEvent(event) {
    const key = String(event.type);
    const listeners = [...(this._listeners.get(key) || [])];
    for (const entry of listeners) {
      entry.listener.call(this, event);
      if (entry.once) {
        const registered = this._listeners.get(key) || [];
        const index = registered.indexOf(entry);
        if (index >= 0) registered.splice(index, 1);
      }
    }
    return true;
  }

  remove() {
    if (!this.parentNode) return;
    const index = this.parentNode.children.indexOf(this);
    if (index >= 0) this.parentNode.children.splice(index, 1);
    this.parentNode = null;
  }

  set textContent(value) {
    for (const child of this.children) child.parentNode = null;
    this.children = [];
    this._ownText = String(value);
  }

  get textContent() {
    return this._ownText + this.children.map((child) => child.textContent).join("");
  }
}

const document = {
  createElement(tagName) {
    return new FakeNode(tagName);
  },
  createTextNode(text) {
    return new FakeNode("#text", String(text));
  },
};

const chatPath = new URL("../backend/static/chat.html", import.meta.url);
const html = readFileSync(chatPath, "utf8");
const styleMatch = html.match(/<style>([\s\S]*?)<\/style>/);
assert.ok(styleMatch, "chat.html must contain one inline style");
const styles = styleMatch[1];

function productionCssRule(selector) {
  const escapedSelector = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = styles.match(new RegExp(`^\\s*${escapedSelector}\\s*\\{([^{}]*)\\}`, "m"));
  assert.ok(match, `production CSS rule must exist: ${selector}`);
  return match[1];
}

test("Task 6 textarea keeps a 44px touch target in every layout state", () => {
  assert.match(
    productionCssRule(".input-row textarea"),
    /(?:^|;)\s*min-height\s*:\s*44px\s*(?:;|$)/,
    "the universal textarea rule must preserve the 44px touch target",
  );
});

const scriptMatch = html.match(/<script>([\s\S]*?)<\/script>/);
assert.ok(scriptMatch, "chat.html must contain one inline script");
const script = scriptMatch[1];
const seamStart = script.indexOf("const unsafePublicTextPatterns");
const seamEnd = script.indexOf("async function fetchJson", seamStart);
assert.ok(seamStart >= 0 && seamEnd > seamStart, "production sanitizer seam must exist");
const messageShellStart = script.indexOf("function messageShell(kind)");
const messageShellEnd = script.indexOf("function renderUser(query)", messageShellStart);
assert.ok(
  messageShellStart >= 0 && messageShellEnd > messageShellStart,
  "production messageShell seam must exist",
);

const context = vm.createContext({ document });
vm.runInContext(
  `${script.slice(seamStart, seamEnd)}\n` +
    "globalThis.__chatSeam = { create, createPublicTextStreamSanitizer, safePublicText, renderMarkdown, renderStreamingMarkdown };",
  context,
  { filename: chatPath.pathname },
);
vm.runInContext(
  `${script.slice(messageShellStart, messageShellEnd)}\n` +
    "globalThis.__chatSeam.messageShell = messageShell;",
  context,
  { filename: chatPath.pathname },
);
const {
  createPublicTextStreamSanitizer,
  messageShell,
  safePublicText,
  renderMarkdown,
  renderStreamingMarkdown,
} = context.__chatSeam;

function snapshot(node) {
  return {
    tagName: node.tagName,
    ownText: node._ownText,
    children: node.children.map(snapshot),
  };
}

function descendants(node, tagName) {
  const normalized = tagName.toUpperCase();
  return [
    ...(node.tagName === normalized ? [node] : []),
    ...node.children.flatMap((child) => descendants(child, normalized)),
  ];
}

const internalMarkers = [
  "PROF-8000C9F994C3",
  "COMP-012345abcdef",
  "COMP-3B95F48EB687",
  "company-c-0123456789abcdef01234567",
  `web-object:sha256:${"a".repeat(64)}`,
  `web-handle:sha256:${"b".repeat(64)}`,
  "web-object:s12g-private",
  "source_nature=current_web",
];

const normalPublicText = [
  "source:github",
  "paper:arxiv",
  "query:python",
  "paper-based",
  "https://example.test/company:overview?ref=public",
  "a".repeat(64),
  "COMP-3B95F48EB68",
  "COMP-3B95F48EB6870",
  "COMP-3B95F48EB68G",
  "xCOMP-3B95F48EB687",
  "COMP-3B95F48EB687x",
  "PROF-DING-WENBO",
  `evidence:sha256:${"b".repeat(64)}`,
  "current_web",
];

function streamSanitize(chunks) {
  const sanitizer = createPublicTextStreamSanitizer();
  return chunks.map((chunk) => sanitizer.feed(chunk)).join("") + sanitizer.flush();
}

function assertStreamMatchesBatchAtEverySplit(input, expected, label) {
  assert.equal(safePublicText(input), expected, `${label} batch`);
  assert.equal(streamSanitize([input]), expected, `${label} single feed`);
  for (let split = 1; split < input.length; split++) {
    assert.equal(
      streamSanitize([input.slice(0, split), input.slice(split)]),
      expected,
      `${label} split ${split}`,
    );
  }
}

test("safePublicText removes producer markers and preserves normal text", () => {
  for (const marker of internalMarkers) {
    assert.equal(safePublicText(marker), null, marker);
    assert.equal(
      safePublicText(`公开前文。${marker}；公开后文。`),
      "公开前文。；公开后文。",
      marker,
    );
  }
  for (const text of normalPublicText) {
    assert.equal(safePublicText(text), text);
  }
  assert.equal(
    safePublicText("公开\u0000文\u001f本\n\t保留"),
    "公开文本\n\t保留",
  );
});

test("browser raw Markdown uses the idempotent canonical public projection", () => {
  const rawMarkdown =
    "# 深圳科创\n\n" +
    "普通文本保持。web-object:s12g-privateCOMP-012345abcdef；结尾公开。";
  const expected = "# 深圳科创\n\n普通文本保持。；结尾公开。";

  assert.equal(safePublicText("普通文本保持。"), "普通文本保持。");

  const projected = safePublicText(rawMarkdown);
  assert.equal(safePublicText(projected), projected);
  assert.equal(projected, expected);

  const streamed = document.createElement("div");
  const renderer = renderStreamingMarkdown(streamed);
  renderer.append(
    "# 深圳科创\n\n普通文本保持。web-object:s12g-private",
  );
  renderer.append("COMP-012345abcdef；结尾公开。");
  renderer.flush();

  const complete = document.createElement("div");
  renderMarkdown(complete, expected);
  assert.deepEqual(snapshot(streamed), snapshot(complete));
});

test("stream sanitizer matches batch output for every web namespace split", () => {
  const input = "公开前文。web-object:s12g-private；公开后文。";
  assertStreamMatchesBatchAtEverySplit(
    input,
    "公开前文。；公开后文。",
    "web namespace marker",
  );
});

test("stream sanitizer preserves marker lookalikes after fixed-tail release", () => {
  const lookalike = "PROF-8000C9F994C3";
  const input = `前x${lookalike}${"后".repeat(20)}`;
  assertStreamMatchesBatchAtEverySplit(input, input, "fixed-tail left boundary");
});

test("stream sanitizer reuses the visible boundary after namespace removal", () => {
  const marker = "PROF-8000C9F994C3";
  const input = `前web-object:public${marker}后`;
  assertStreamMatchesBatchAtEverySplit(
    input,
    "前后",
    "namespace-removal visible boundary",
  );
});

test("stream sanitizer removes uppercase COMP markers at every split", () => {
  assertStreamMatchesBatchAtEverySplit(
    "公开前。COMP-3B95F48EB687；公开后。",
    "公开前。；公开后。",
    "uppercase COMP marker",
  );
});

test("streaming Markdown sanitizes markers split across chunks without losing public text", () => {
  const safeMarkdown =
    "# 深圳科创\n\n" +
    "这是 **公开回答**，详情见 [官网](https://example.com/product?q=robot)。\n\n" +
    "- 第一项\n- 第二项\n\n";
  const longText = "长正文：" + "深圳科创持续创新。".repeat(64);
  const streamedMarkers = [
    "PROF-8000C9F994C3",
    "web-object:s12g-private",
    "source_nature=current_web",
  ];
  const chunks = [
    "PROF-8000",
    "C9F994C3\n",
    safeMarkdown,
    "中段前文 web-object:s12g-",
    "private 后文继续公开。\n\n",
    longText,
    "\n\n结尾公开说明：source_",
    "nature=current_web",
  ];
  let expectedPublicText = chunks.join("");
  for (const marker of streamedMarkers) {
    expectedPublicText = expectedPublicText.replace(marker, "");
  }

  const streamed = document.createElement("div");
  const renderer = renderStreamingMarkdown(streamed);
  for (const chunk of chunks) renderer.append(chunk);
  renderer.flush();

  const complete = document.createElement("div");
  renderMarkdown(complete, expectedPublicText);
  assert.deepEqual(snapshot(streamed), snapshot(complete));

  for (const unsafeFragment of streamedMarkers) {
    assert.ok(!streamed.textContent.includes(unsafeFragment), unsafeFragment);
  }
  for (const publicFragment of [
    "深圳科创",
    "公开回答",
    "https://example.com/product?q=robot",
    "第一项",
    "第二项",
    "中段前文 ",
    " 后文继续公开。",
    longText,
    "结尾公开说明：",
  ]) {
    assert.ok(streamed.textContent.includes(publicFragment), publicFragment);
  }
  assert.equal(descendants(streamed, "h1").length, 1);
  assert.equal(descendants(streamed, "strong").length, 1);
  assert.equal(descendants(streamed, "ul").length, 1);
  assert.equal(descendants(streamed, "li").length, 2);
});

const readSseEventsStart = script.indexOf("function parseSseBlock(");
const readSseEventsEnd = script.indexOf("function laneSummary(", readSseEventsStart);
assert.ok(
  readSseEventsStart >= 0 && readSseEventsEnd > readSseEventsStart,
  "production readSseEvents seam must exist",
);
const sseParserContext = vm.createContext({ TextDecoder });
vm.runInContext(
  `${script.slice(readSseEventsStart, readSseEventsEnd)}\n` +
    "globalThis.__readSseEvents = readSseEvents;",
  sseParserContext,
  { filename: chatPath.pathname },
);
const utf8Encoder = new TextEncoder();

async function parseProductionSseChunks(chunks) {
  let chunkIndex = 0;
  const stream = {
    getReader() {
      return {
        async read() {
          if (chunkIndex >= chunks.length) return { done: true, value: undefined };
          const value = chunks[chunkIndex];
          chunkIndex += 1;
          return { done: false, value };
        },
        releaseLock() {},
      };
    },
  };
  const events = [];
  await sseParserContext.__readSseEvents(stream, (eventName, data) => {
    events.push([String(eventName), JSON.parse(JSON.stringify(data))]);
  });
  return events;
}

function utf8Chunk(text) {
  return utf8Encoder.encode(text);
}

test("production readSseEvents parses CRLF blocks split inside the delimiter", async () => {
  const events = await parseProductionSseChunks([
    utf8Chunk('event: answer\r\ndata: {\r\ndata: "answer_text": "CRLF"\r\ndata: }\r\n\r'),
    utf8Chunk("\n"),
  ]);
  assert.deepEqual(events, [["answer", { answer_text: "CRLF" }]]);
});

test("production readSseEvents preserves JSON split across byte chunks", async () => {
  const events = await parseProductionSseChunks([
    utf8Chunk('event: answer\ndata: {"answer_'),
    utf8Chunk('text":"跨块"}\n\n'),
  ]);
  assert.deepEqual(events, [["answer", { answer_text: "跨块" }]]);
});

test("production readSseEvents preserves UTF-8 characters split across byte chunks", async () => {
  const text = 'event: answer\ndata: {"answer_text":"深圳"}\n\n';
  const encoded = utf8Chunk(text);
  const chineseStart = utf8Chunk('event: answer\ndata: {"answer_text":"').length;
  const events = await parseProductionSseChunks([
    encoded.slice(0, chineseStart + 1),
    encoded.slice(chineseStart + 1, chineseStart + 4),
    encoded.slice(chineseStart + 4),
  ]);
  assert.deepEqual(events, [["answer", { answer_text: "深圳" }]]);
});

test("production readSseEvents parses a valid residual block at EOF", async () => {
  const events = await parseProductionSseChunks([
    utf8Chunk('event: done\ndata: {"ok":true}'),
  ]);
  assert.deepEqual(events, [["done", { ok: true }]]);
});

test("production readSseEvents cancels, unlocks, and preserves event handler failures", async () => {
  let cancelCalls = 0;
  const handlerError = new Error("event handler failed");
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(utf8Chunk('event: answer\ndata: {"answer_text":"公开回答"}\n\n'));
    },
    cancel() {
      cancelCalls += 1;
    },
  });

  await assert.rejects(
    sseParserContext.__readSseEvents(stream, () => {
      throw handlerError;
    }),
    (error) => {
      assert.equal(error, handlerError, "cleanup must preserve the original callback error");
      return true;
    },
  );
  assert.deepEqual(
    { cancelCalls, locked: stream.locked },
    { cancelCalls: 1, locked: false },
  );
});

test("production readSseEvents releases its reader after normal EOF without cancelling", async () => {
  let cancelCalls = 0;
  const events = [];
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(utf8Chunk('event: done\ndata: {"ok":true}\n\n'));
      controller.close();
    },
    cancel() {
      cancelCalls += 1;
    },
  });

  await sseParserContext.__readSseEvents(stream, (eventName, data) => {
    events.push([String(eventName), JSON.parse(JSON.stringify(data))]);
  });

  assert.deepEqual(
    { events, cancelCalls, locked: stream.locked },
    { events: [["done", { ok: true }]], cancelCalls: 0, locked: false },
  );
});

const sendQueryStart = script.indexOf("async function sendQuery(");
const sendQueryEnd = script.indexOf("function runDemoQuery(", sendQueryStart);
assert.ok(sendQueryStart >= 0 && sendQueryEnd > sendQueryStart, "production sendQuery seam must exist");

Object.assign(context, {
  beginContinuationRequest() {
    return { previous: null, optionFollowUp: false };
  },
  settleContinuationOwners() {},
  input: { value: "", focus() {} },
  submit: { disabled: false, textContent: "" },
  messages: { append() {} },
  removeWelcome() {},
  startFollowingTurn() {},
  notifyContentUpdate() {},
  renderUser() {},
  scrollToLatest() {},
  messageShell() {
    return { row: {}, bubble: document.createElement("div") };
  },
  renderProcess() {
    return {
      set() {},
      addAction(_label, callback) {
        context.__stopAction = callback;
      },
      finish(label) {
        context.__terminalFinishes.push(label);
      },
    };
  },
  async fetch() {
    if (context.__terminalFetchError) throw context.__terminalFetchError;
    return context.__terminalResponse || { ok: true, body: {}, status: 200 };
  },
  async readSseEvents(_body, onEvent) {
    for (const [eventName, data] of context.__terminalEvents) {
      onEvent(eventName, data);
      if (context.__stopAfterEvent === eventName && context.__stopAction) {
        context.__stopAfterEvent = null;
        context.__stopAction();
      }
    }
  },
  renderAssistant(data) {
    context.__assistantRenders.push(String(data.answer_text));
  },
  renderContinuation() {},
  renderError(detail) {
    context.__errorRenders.push(String(detail));
  },
  renderStreamingMarkdown() {
    return {
      append(text) {
        context.__streamedChunks.push(String(text));
      },
      flush() {},
    };
  },
  resetInputHeight() {},
  restoreInputFocus() {},
  queueMicrotask,
});
vm.runInContext(
  `${script.slice(sendQueryStart, sendQueryEnd)}\n` +
    "globalThis.__sendQuery = sendQuery;",
  context,
  { filename: chatPath.pathname },
);

function descendantsWithClass(node, className) {
  const ownClasses = String(node.className || "").split(/\s+/).filter(Boolean);
  return [
    ...(ownClasses.includes(className) ? [node] : []),
    ...node.children.flatMap((child) => descendantsWithClass(child, className)),
  ];
}

function clarificationTurnDescriptor(turn) {
  if (turn && (turn.response || turn.events || turn.run)) return turn;
  return {
    events: [
      ["answer", turn],
      ["done", {}],
    ],
  };
}

function createClarificationHarness(turns) {
  const continuationStart = script.indexOf("function continuationText(option)");
  const continuationEnd = script.indexOf("function renderProcess(", continuationStart);
  assert.ok(
    continuationStart >= 0 && continuationEnd > continuationStart,
    "production clarification rendering seam must exist",
  );

  const errorMessages = [];
  const fetchCalls = [];
  const userMessages = [];
  const renderedMessages = document.createElement("main");
  let responseIndex = 0;
  const clarificationContext = vm.createContext({
    URL,
    document,
    input: { value: "", focus() {} },
    submit: { disabled: false, textContent: "" },
    messages: renderedMessages,
    removeWelcome() {},
    startFollowingTurn() {},
    notifyContentUpdate() {},
    renderUser(query) {
      userMessages.push(String(query));
    },
    scrollToLatest() {},
    messageShell() {
      const row = document.createElement("article");
      row.className = "message assistant";
      const bubble = document.createElement("div");
      bubble.className = "bubble";
      row.append(bubble);
      return { row, bubble };
    },
    renderProcess() {
      return {
        set() {},
        addAction() {},
        finish() {},
      };
    },
    async fetch(url, options) {
      const rawTurn = turns[responseIndex];
      assert.ok(rawTurn, `missing turn descriptor for request ${responseIndex + 1}`);
      responseIndex += 1;
      fetchCalls.push({ url, body: JSON.parse(options.body) });
      const turn = clarificationTurnDescriptor(rawTurn);
      if (turn.response) return turn.response;
      return { ok: true, status: 200, body: turn };
    },
    async readSseEvents(body, onEvent) {
      if (typeof body.run === "function") {
        await body.run(onEvent);
        return;
      }
      for (const [eventName, data] of body.events || []) onEvent(eventName, data);
    },
    renderError(detail) {
      errorMessages.push(String(detail));
    },
    maintainFollowingScroll() {},
    resetInputHeight() {},
    restoreInputFocus() {},
    queueMicrotask,
  });
  vm.runInContext(
    `${script.slice(seamStart, seamEnd)}\n` +
      `${script.slice(continuationStart, continuationEnd)}\n` +
      `${script.slice(sendQueryStart, sendQueryEnd)}\n` +
      "globalThis.__clarificationSeam = { sendQuery };",
    clarificationContext,
    { filename: chatPath.pathname },
  );

  return {
    errorMessages,
    fetchCalls,
    renderedMessages,
    sendQuery: clarificationContext.__clarificationSeam.sendQuery,
    userMessages,
  };
}

function answerWithClarification(clarification, answerText = "公开回答") {
  return {
    answer_text: answerText,
    citations: [],
    clarification,
  };
}

function deferred() {
  let resolve;
  const promise = new Promise((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

function callClickListener(button) {
  const [entry] = button._listeners.get("click") || [];
  assert.ok(entry, "option button must register a click listener");
  return entry.listener.call(button, { type: "click" });
}

async function invokeClickListener(button) {
  await callClickListener(button);
}

test("public clarification options normalize, dedupe, and send only the public id", async () => {
  const clarification = {
    prompt: "请选择下一步",
    options: [
      {
        id: "  option:public:1  ",
        domain: "paper",
        label: "  继续核对论文  ",
        hint: "补充消歧上下文，不是按钮标签",
        operation: "targeted_evidence_search",
        title: "旧私有标题",
      },
      { id: "option:public:1", label: "重复项" },
      { id: "   ", label: "空白 ID" },
      { id: "option:public:2", label: "   " },
      { id: "option:public:3" },
    ],
    default_id: "option:public:1",
    omitted: 0,
  };
  const withOptions = createClarificationHarness([
    answerWithClarification(clarification),
    answerWithClarification(null),
  ]);
  assert.deepEqual(plainOutcome(await withOptions.sendQuery("原问题")), { status: "succeeded" });
  const buttons = descendantsWithClass(withOptions.renderedMessages, "option-button");
  assert.equal(buttons.length, 1);
  assert.equal(buttons[0].textContent, "继续核对论文");
  assert.equal(buttons[0].disabled, false);

  await invokeClickListener(buttons[0]);
  assert.deepEqual(
    withOptions.fetchCalls.map((call) => call.body),
    [
      { query: "原问题" },
      { query: "原问题", entity_id_hint: "option:public:1" },
    ],
  );
  assert.deepEqual(withOptions.userMessages, ["原问题", "选择：继续核对论文"]);

  const withoutClarification = createClarificationHarness([
    answerWithClarification(null),
  ]);
  await withoutClarification.sendQuery("没有澄清的问题");
  assert.equal(
    descendantsWithClass(withoutClarification.renderedMessages, "option-button").length,
    0,
  );

  const withoutOptions = createClarificationHarness([
    answerWithClarification({
      prompt: "没有候选项",
      options: [],
      default_id: null,
      omitted: 0,
    }),
  ]);
  await withoutOptions.sendQuery("没有候选项的问题");
  assert.equal(descendantsWithClass(withoutOptions.renderedMessages, "option-button").length, 0);

  const optionButtonRule = productionCssRule(".option-button");
  assert.match(optionButtonRule, /(?:^|;)\s*min-width\s*:\s*44px\s*(?:;|$)/);
  assert.match(optionButtonRule, /(?:^|;)\s*min-height\s*:\s*44px\s*(?:;|$)/);
});

test("continuation lifecycle activates new options only after done and reader settlement", async () => {
  const answerSeen = deferred();
  const allowDone = deferred();
  const doneSeen = deferred();
  const allowReaderReturn = deferred();
  const payload = answerWithClarification({
    prompt: "请选择下一步",
    options: [{ id: "option:public:gated", label: "继续核对" }],
  });
  const harness = createClarificationHarness([{
    async run(onEvent) {
      onEvent("answer", payload);
      answerSeen.resolve();
      await allowDone.promise;
      onEvent("done", {});
      doneSeen.resolve();
      await allowReaderReturn.promise;
    },
  }]);

  const pendingTurn = harness.sendQuery("原问题");
  await answerSeen.promise;
  const [button] = descendantsWithClass(harness.renderedMessages, "option-button");
  const disabledAfterAnswer = button.disabled;
  await callClickListener(button);
  const fetchCountAfterEarlyClick = harness.fetchCalls.length;

  allowDone.resolve();
  await doneSeen.promise;
  const disabledAfterDone = button.disabled;
  allowReaderReturn.resolve();
  const outcome = await pendingTurn;

  assert.equal(disabledAfterAnswer, true);
  assert.equal(fetchCountAfterEarlyClick, 1, "an inactive candidate must not start a request");
  assert.equal(disabledAfterDone, true, "done alone must not activate before reader/finally settle");
  assert.deepEqual(plainOutcome(outcome), { status: "succeeded" });
  assert.equal(button.disabled, false);
});

test("continuation lifecycle rotates owners on success and retires options without a successor", async () => {
  const firstClarification = {
    prompt: "第一轮",
    options: [{ id: "option:public:first", label: "第一选项" }],
  };
  const secondClarification = {
    prompt: "第二轮",
    options: [{ id: "option:public:second", label: "第二选项" }],
  };
  const harness = createClarificationHarness([
    answerWithClarification(firstClarification),
    answerWithClarification(secondClarification),
    answerWithClarification(null),
  ]);

  await harness.sendQuery("第一问题");
  const [firstButton] = descendantsWithClass(harness.renderedMessages, "option-button");
  assert.equal(firstButton.disabled, false);

  const secondTurn = harness.sendQuery("第二问题");
  const firstDisabledDuringSecondTurn = firstButton.disabled;
  assert.deepEqual(plainOutcome(await secondTurn), { status: "succeeded" });
  const [, secondButton] = descendantsWithClass(harness.renderedMessages, "option-button");
  assert.equal(firstDisabledDuringSecondTurn, true);
  assert.equal(firstButton.disabled, true);
  assert.equal(secondButton.disabled, false);

  const thirdTurn = harness.sendQuery("第三问题");
  const secondDisabledDuringThirdTurn = secondButton.disabled;
  assert.deepEqual(plainOutcome(await thirdTurn), { status: "succeeded" });
  assert.equal(secondDisabledDuringThirdTurn, true);
  assert.equal(secondButton.disabled, true, "success without options must retire the old owner");
});

test("continuation lifecycle restores the previous owner after explicit failure", async (t) => {
  const failures = [
    {
      name: "SSE error",
      turn: { events: [["error", { detail: "查询失败" }]] },
      reason: "sse_error",
    },
    {
      name: "HTTP error",
      turn: {
        response: {
          ok: false,
          body: null,
          status: 503,
          async json() {
            return { detail: "服务不可用" };
          },
        },
      },
      reason: "http_error",
    },
  ];
  for (const failure of failures) {
    await t.test(failure.name, async () => {
      const harness = createClarificationHarness([
        answerWithClarification({
          prompt: "请选择下一步",
          options: [{ id: "option:public:retry", label: "可重试选项" }],
        }),
        failure.turn,
      ]);
      await harness.sendQuery("原问题");
      const [button] = descendantsWithClass(harness.renderedMessages, "option-button");

      const failedTurn = harness.sendQuery("新问题");
      const disabledWhilePending = button.disabled;
      const outcome = await failedTurn;

      assert.equal(disabledWhilePending, true);
      assert.deepEqual(plainOutcome(outcome), { status: "failed", reason: failure.reason });
      assert.equal(button.disabled, false, "an explicit pre-commit failure must restore the owner");
    });
  }
});

test("continuation lifecycle quarantines old and candidate owners after uncertainty", async (t) => {
  const uncertainTurns = [
    {
      name: "bare EOF",
      turn: { events: [] },
      expectedReason: "eof",
      expectsCandidate: false,
    },
    {
      name: "network throw",
      turn: {
        async run() {
          throw new Error("连接断开");
        },
      },
      expectedReason: "network_error",
      expectsCandidate: false,
    },
    {
      name: "answer without done",
      turn: {
        events: [["answer", answerWithClarification({
          prompt: "未提交候选",
          options: [{ id: "option:public:uncertain", label: "未提交选项" }],
        })]],
      },
      expectedReason: "missing_done",
      expectsCandidate: true,
    },
  ];
  for (const scenario of uncertainTurns) {
    await t.test(scenario.name, async () => {
      const harness = createClarificationHarness([
        answerWithClarification({
          prompt: "原 owner",
          options: [{ id: "option:public:old", label: "原选项" }],
        }),
        scenario.turn,
      ]);
      await harness.sendQuery("原问题");
      const [oldButton] = descendantsWithClass(harness.renderedMessages, "option-button");

      const uncertainTurn = harness.sendQuery("不确定问题");
      const disabledWhilePending = oldButton.disabled;
      const outcome = await uncertainTurn;
      const buttons = descendantsWithClass(harness.renderedMessages, "option-button");

      assert.equal(disabledWhilePending, true);
      assert.equal(outcome.status, "uncertain");
      assert.equal(outcome.reason, scenario.expectedReason);
      assert.equal(oldButton.disabled, true, "uncertainty must not restore the previous owner");
      if (scenario.expectsCandidate) {
        assert.equal(buttons.length, 2);
        assert.equal(buttons[1].disabled, true, "an uncommitted candidate must remain disabled");
      }
    });
  }
});

test("continuation option retries after explicit failure and becomes consumed only on success", async () => {
  const harness = createClarificationHarness([
    answerWithClarification({
      prompt: "请选择下一步",
      options: [{ id: "option:public:retry", label: "重试此选项" }],
    }),
    { events: [["error", { detail: "第一次失败" }]] },
    answerWithClarification(null),
  ]);
  await harness.sendQuery("原问题");
  const [button] = descendantsWithClass(harness.renderedMessages, "option-button");

  const firstAttempt = callClickListener(button);
  const disabledWhilePending = button.disabled;
  await callClickListener(button);
  const fetchCountAfterRapidRepeat = harness.fetchCalls.length;
  const firstOutcome = await firstAttempt;

  assert.equal(disabledWhilePending, true);
  assert.equal(fetchCountAfterRapidRepeat, 2, "pending owner must reject a rapid repeated listener");
  assert.deepEqual(plainOutcome(firstOutcome), { status: "failed", reason: "sse_error" });
  assert.equal(button.disabled, false, "explicit failure must make the same option retryable");

  const retryOutcome = await callClickListener(button);
  assert.deepEqual(plainOutcome(retryOutcome), { status: "succeeded" });
  assert.deepEqual(
    harness.fetchCalls.map((call) => call.body),
    [
      { query: "原问题" },
      { query: "原问题", entity_id_hint: "option:public:retry" },
      { query: "原问题", entity_id_hint: "option:public:retry" },
    ],
  );
  assert.equal(button.disabled, true);
  await callClickListener(button);
  assert.equal(harness.fetchCalls.length, 3, "a consumed option must not be sent again");
});

test("continuation option invalid option rejection retires the stale owner", async () => {
  const harness = createClarificationHarness([
    answerWithClarification({
      prompt: "请选择下一步",
      options: [{ id: "option:public:expired", label: "已失效选项" }],
    }),
    { events: [["error", { detail: "canonical_v2_invalid_option" }]] },
    answerWithClarification(null),
  ]);
  await harness.sendQuery("原问题");
  const [button] = descendantsWithClass(harness.renderedMessages, "option-button");

  const outcome = await callClickListener(button);
  const disabledAfterRejection = button.disabled;
  const repeatedAttempt = callClickListener(button);
  if (repeatedAttempt) await repeatedAttempt;

  assert.deepEqual(
    {
      outcome: plainOutcome(outcome),
      errors: harness.errorMessages,
      machineCodeShown: harness.errorMessages.some((message) =>
        message.includes("canonical_v2_invalid_option"),
      ),
      disabledAfterRejection,
      fetchCount: harness.fetchCalls.length,
    },
    {
      outcome: { status: "failed", reason: "invalid_option" },
      errors: ["该继续选项已失效，请重新提问。"],
      machineCodeShown: false,
      disabledAfterRejection: true,
      fetchCount: 2,
    },
  );
});

test("continuation option quarantines its owner when catch settles a post-error conflict", async () => {
  const harness = createClarificationHarness([
    answerWithClarification({
      prompt: "请选择下一步",
      options: [{ id: "option:public:conflict", label: "冲突选项" }],
    }),
    {
      async run(onEvent) {
        onEvent("error", { detail: "第一错误" });
        onEvent("stage", { name: "retrieval" });
        throw new Error("reader failed after protocol conflict");
      },
    },
    answerWithClarification(null),
  ]);
  await harness.sendQuery("原问题");
  const [button] = descendantsWithClass(harness.renderedMessages, "option-button");

  const outcome = await callClickListener(button);
  const disabledAfterConflict = button.disabled;
  const repeatedAttempt = callClickListener(button);
  if (repeatedAttempt) await repeatedAttempt;

  assert.deepEqual(
    {
      outcome: plainOutcome(outcome),
      errors: harness.errorMessages,
      disabledAfterConflict,
      fetchCount: harness.fetchCalls.length,
    },
    {
      outcome: { status: "uncertain", reason: "protocol_conflict" },
      errors: ["第一错误"],
      disabledAfterConflict: true,
      fetchCount: 2,
    },
  );
});

test("continuation option remains disabled after an uncertain follow-up", async () => {
  const harness = createClarificationHarness([
    answerWithClarification({
      prompt: "请选择下一步",
      options: [{ id: "option:public:uncertain", label: "不确定选项" }],
    }),
    { events: [] },
  ]);
  await harness.sendQuery("原问题");
  const [button] = descendantsWithClass(harness.renderedMessages, "option-button");

  const outcome = await callClickListener(button);
  assert.deepEqual(plainOutcome(outcome), { status: "uncertain", reason: "eof" });
  assert.equal(button.disabled, true);
  await callClickListener(button);
  assert.equal(harness.fetchCalls.length, 2, "an uncertain option must not retry automatically");
});

test("continuation option code consumes only the public clarification contract", () => {
  assert.doesNotMatch(script, /trace\.continuation_offer/);
  assert.doesNotMatch(script, /option\.option_id/);
  assert.doesNotMatch(script, /option\?\.operation/);
  assert.doesNotMatch(script, /option\?\.title/);
});

const postDoneConflictCases = [
  ["error", ["error", { detail: "迟到错误" }]],
  ["answer_chunk", ["answer_chunk", { text: "迟到片段" }]],
  ["answer", ["answer", { answer_text: "迟到回答" }]],
  ["duplicate done", ["done", {}]],
  ["stage", ["stage", { name: "retrieval" }]],
];

const postErrorConflictCases = [
  ["duplicate error", [["error", { detail: "第二错误" }]]],
  ["answer_chunk", [["answer_chunk", { text: "迟到片段" }]]],
  [
    "answer then done",
    [
      ["answer", { answer_text: "迟到回答" }],
      ["done", {}],
    ],
  ],
  ["done", [["done", {}]]],
  ["stage", [["stage", { name: "retrieval" }]]],
  ["plan_done", [["plan_done", { views: [{ domain: "paper" }] }]]],
  [
    "retrieval_done",
    [["retrieval_done", { lanes: [{ lane: "vector", status: "succeeded", candidates: 1 }] }]],
  ],
];

const terminalFsmCases = [
  {
    name: "answer then done succeeds",
    events: [
      ["answer", { answer_text: "第一回答" }],
      ["done", {}],
    ],
    outcome: { status: "succeeded" },
    finishes: ["查看检索过程"],
    answers: ["第一回答"],
    errors: [],
    chunks: [],
  },
  {
    name: "duplicate answer stays on the first answer and is uncertain",
    events: [
      ["answer", { answer_text: "第一回答" }],
      ["answer", { answer_text: "第二回答" }],
      ["done", {}],
    ],
    outcome: { status: "uncertain", reason: "protocol_conflict" },
    finishes: ["查看检索过程"],
    answers: ["第一回答"],
    errors: [],
    chunks: [],
  },
  {
    name: "error after answer cannot overwrite the answer",
    events: [
      ["answer", { answer_text: "第一回答" }],
      ["error", { detail: "迟到错误" }],
    ],
    outcome: { status: "uncertain", reason: "protocol_conflict" },
    finishes: ["查看检索过程"],
    answers: ["第一回答"],
    errors: [],
    chunks: [],
  },
  ...postErrorConflictCases.map(([eventName, trailingEvents]) => ({
    name: `${eventName} after error preserves the first error and is uncertain`,
    events: [["error", { detail: "第一错误" }], ...trailingEvents],
    outcome: { status: "uncertain", reason: "protocol_conflict" },
    finishes: ["查询失败"],
    answers: [],
    errors: ["第一错误"],
    chunks: [],
  })),
  ...postDoneConflictCases.map(([eventName, event]) => ({
    name: `${eventName} after done preserves the first answer and is uncertain`,
    events: [
      ["answer", { answer_text: "第一回答" }],
      ["done", {}],
      event,
    ],
    outcome: { status: "uncertain", reason: "protocol_conflict" },
    finishes: ["查看检索过程"],
    answers: ["第一回答"],
    errors: [],
    chunks: [],
  })),
  {
    name: "bare EOF is uncertain and visibly interrupted",
    events: [],
    outcome: { status: "uncertain", reason: "eof" },
    finishes: ["生成中断"],
    answers: [],
    errors: [],
    chunks: [],
  },
  {
    name: "answer without done is uncertain but keeps the answer",
    events: [["answer", { answer_text: "第一回答" }]],
    outcome: { status: "uncertain", reason: "missing_done" },
    finishes: ["查看检索过程"],
    answers: ["第一回答"],
    errors: [],
    chunks: [],
  },
  {
    name: "answer after done is a protocol conflict and remains visibly interrupted",
    events: [
      ["done", {}],
      ["answer", { answer_text: "迟到回答" }],
    ],
    outcome: { status: "uncertain", reason: "protocol_conflict" },
    finishes: ["生成中断"],
    answers: [],
    errors: [],
    chunks: [],
  },
  {
    name: "user stop is uncertain and preserves the stopped state",
    events: [["stage", { name: "synthesis" }]],
    stopAfterEvent: "stage",
    outcome: { status: "uncertain", reason: "stopped" },
    finishes: ["已停止生成"],
    answers: [],
    errors: [],
    chunks: [],
  },
];

function resetTerminalFsmHarness({
  events = [],
  response = null,
  fetchError = null,
  stopAfterEvent = null,
} = {}) {
  context.__terminalEvents = events;
  context.__terminalResponse = response;
  context.__terminalFetchError = fetchError;
  context.__stopAfterEvent = stopAfterEvent;
  context.__stopAction = null;
  context.__terminalFinishes = [];
  context.__assistantRenders = [];
  context.__errorRenders = [];
  context.__streamedChunks = [];
}

function plainOutcome(outcome) {
  return outcome ? JSON.parse(JSON.stringify(outcome)) : outcome;
}

test("production sendQuery stop cancels the locked SSE reader", async () => {
  let streamController;
  let sourceCancelCalls = 0;
  const stopSeen = deferred();
  const stream = new ReadableStream({
    start(controller) {
      streamController = controller;
      controller.enqueue(utf8Chunk('event: stage\ndata: {"name":"synthesis"}\n\n'));
    },
    cancel() {
      sourceCancelCalls += 1;
    },
  });
  const stopContext = vm.createContext({
    TextDecoder,
    beginContinuationRequest() {
      return { previous: null, optionFollowUp: false };
    },
    settleContinuationOwners() {},
    create() {
      return {};
    },
    input: { value: "" },
    messages: { append() {} },
    messageShell() {
      return { row: {}, bubble: { append() {} } };
    },
    queueMicrotask,
    queuedDemoQuery: null,
    removeWelcome() {},
    startFollowingTurn() {},
    notifyContentUpdate() {},
    renderAssistant() {},
    renderContinuation() {
      return null;
    },
    renderError() {},
    renderProcess() {
      return {
        set() {},
        finish() {},
        addAction(_label, callback) {
          callback();
          stopSeen.resolve();
        },
      };
    },
    renderStreamingMarkdown() {
      return { append() {}, flush() {} };
    },
    renderUser() {},
    requestPending: false,
    resetInputHeight() {},
    restoreInputFocus() {},
    submit: { disabled: false, textContent: "" },
    async fetch() {
      return { body: stream, ok: true, status: 200 };
    },
  });
  vm.runInContext(
    `${script.slice(readSseEventsStart, readSseEventsEnd)}\n` +
      `${script.slice(sendQueryStart, sendQueryEnd)}\n` +
      "globalThis.__stopSendQuery = sendQuery;",
    stopContext,
    { filename: chatPath.pathname },
  );

  const pendingTurn = stopContext.__stopSendQuery("公开问题");
  await stopSeen.promise;
  await Promise.resolve();
  const cancelCallsAfterStop = sourceCancelCalls;
  if (!sourceCancelCalls) streamController.close();
  const outcome = await pendingTurn;

  assert.equal(cancelCallsAfterStop, 1, "stop must cancel the reader that owns the stream lock");
  assert.deepEqual(plainOutcome(outcome), { status: "uncertain", reason: "stopped" });
  assert.equal(stream.locked, false, "stop settlement must release the reader lock");
});

test("terminal FSM preserves first terminal UI and returns one structured outcome", async (t) => {
  for (const scenario of terminalFsmCases) {
    await t.test(scenario.name, async () => {
      resetTerminalFsmHarness(scenario);

      const outcome = await context.__sendQuery("公开问题");

      assert.deepEqual(context.__terminalFinishes, scenario.finishes);
      assert.deepEqual(context.__assistantRenders, scenario.answers);
      assert.deepEqual(context.__errorRenders, scenario.errors);
      assert.deepEqual(context.__streamedChunks, scenario.chunks);
      assert.deepEqual(plainOutcome(outcome), scenario.outcome);
    });
  }
});

test("terminal FSM classifies HTTP failure and network uncertainty", async () => {
  resetTerminalFsmHarness({
    response: {
      ok: false,
      body: null,
      status: 503,
      async json() {
        return { detail: "服务不可用" };
      },
    },
  });
  const httpOutcome = await context.__sendQuery("HTTP 问题");
  assert.deepEqual(plainOutcome(httpOutcome), { status: "failed", reason: "http_error" });
  assert.deepEqual(context.__errorRenders, ["服务不可用"]);

  resetTerminalFsmHarness({ fetchError: new Error("连接断开") });
  const networkOutcome = await context.__sendQuery("网络问题");
  assert.deepEqual(plainOutcome(networkOutcome), {
    status: "uncertain",
    reason: "network_error",
  });
  assert.deepEqual(context.__errorRenders, ["连接失败：连接断开"]);
});

test("terminal FSM rejects empty and concurrently busy requests", async () => {
  resetTerminalFsmHarness();
  const emptyOutcome = await context.__sendQuery(" \n\t ");
  assert.deepEqual(plainOutcome(emptyOutcome), { status: "rejected", reason: "empty" });

  resetTerminalFsmHarness({
    events: [
      ["answer", { answer_text: "第一回答" }],
      ["done", {}],
    ],
  });
  const inFlight = context.__sendQuery("第一问题");
  const busyOutcome = await context.__sendQuery("第二问题");
  assert.deepEqual(plainOutcome(busyOutcome), { status: "rejected", reason: "busy" });
  assert.deepEqual(plainOutcome(await inFlight), { status: "succeeded" });
});

test("production messageShell preserves avatar identities and logo fallback", () => {
  const assistantView = messageShell("assistant");
  const assistantAvatar = assistantView.row.children[0];
  assert.equal(assistantAvatar.textContent, "国先");
  assert.equal(assistantAvatar.getAttribute("role"), "img");
  assert.equal(assistantAvatar.getAttribute("aria-label"), "国先检索助手");

  const assistantImages = descendants(assistantAvatar, "img");
  assert.equal(assistantImages.length, 1);
  const [image] = assistantImages;
  assert.equal(image.parentNode, assistantAvatar);
  assert.equal(image.src, "/static/assets/guoxian-logo.jpg");
  assert.equal(image.alt, "");
  assert.equal(image.width, 32);
  assert.equal(image.height, 32);

  image.dispatchEvent({ type: "error" });
  assert.equal(descendants(assistantAvatar, "img").length, 0);
  assert.equal(image.parentNode, null);
  assert.equal(assistantAvatar.textContent, "国先");

  const userAvatar = messageShell("user").row.children[0];
  assert.equal(descendants(userAvatar, "img").length, 0);
  assert.equal(userAvatar.textContent, "我");

  const errorAvatar = messageShell("error").row.children[0];
  assert.equal(descendants(errorAvatar, "img").length, 0);
  assert.equal(errorAvatar.textContent, "!");
});

class FakeEventTarget {
  constructor() {
    this._listeners = new Map();
  }

  addEventListener(type, listener) {
    const key = String(type);
    const listeners = this._listeners.get(key) || [];
    listeners.push(listener);
    this._listeners.set(key, listeners);
  }

  dispatchEvent(event) {
    for (const listener of [...(this._listeners.get(String(event.type)) || [])]) {
      listener.call(this, event);
    }
    return true;
  }
}

function productionViewportGeometrySource() {
  const start = script.indexOf("function installViewportGeometry()");
  const declarationLength = "function installViewportGeometry()".length;
  const end = start < 0
    ? -1
    : script.indexOf("installViewportGeometry();", start + declarationLength);
  assert.ok(start >= 0 && end > start, "production viewport geometry seam must exist");
  return script.slice(start, end);
}

function createViewportGeometryHarness({
  innerHeight,
  visualViewportHeight,
  withVisualViewport,
}) {
  const frames = [];
  const writes = [];
  const rootClasses = new Set();
  let frameId = 0;
  let sendQueryCalls = 0;
  const root = {
    classList: {
      toggle(name, force) {
        const key = String(name);
        const shouldContain = force === undefined ? !rootClasses.has(key) : Boolean(force);
        if (shouldContain) rootClasses.add(key);
        else rootClasses.delete(key);
        return shouldContain;
      },
      contains(name) {
        return rootClasses.has(String(name));
      },
    },
    style: {
      setProperty(name, value) {
        writes.push([String(name), String(value)]);
      },
    },
  };
  const fakeWindow = new FakeEventTarget();
  fakeWindow.innerHeight = innerHeight;
  fakeWindow.requestAnimationFrame = (callback) => {
    frames.push(callback);
    frameId += 1;
    return frameId;
  };

  let viewport;
  if (withVisualViewport) {
    viewport = new FakeEventTarget();
    viewport.height = visualViewportHeight;
    fakeWindow.visualViewport = viewport;
  }

  const geometryContext = vm.createContext({
    document: { documentElement: root },
    maintainFollowingScroll() {},
    sendQuery() {
      sendQueryCalls += 1;
    },
    window: fakeWindow,
  });
  vm.runInContext(
    `${productionViewportGeometrySource()}\n` +
      "globalThis.__installViewportGeometry = installViewportGeometry;",
    geometryContext,
    { filename: chatPath.pathname },
  );
  geometryContext.__installViewportGeometry();

  return {
    fakeWindow,
    frames,
    root,
    viewport,
    writes,
    flushFrame() {
      assert.ok(frames.length > 0, "a viewport geometry frame must be pending");
      const callback = frames.shift();
      callback();
    },
    get sendQueryCalls() {
      return sendQueryCalls;
    },
  };
}

test("viewport geometry coalesces all visual viewport and window events per frame", () => {
  const harness = createViewportGeometryHarness({
    innerHeight: 900,
    visualViewportHeight: 700,
    withVisualViewport: true,
  });
  assert.equal(harness.frames.length, 1);

  harness.viewport.height = 612.4;
  harness.viewport.dispatchEvent({ type: "resize" });
  harness.viewport.dispatchEvent({ type: "scroll" });
  harness.fakeWindow.dispatchEvent({ type: "resize" });
  harness.fakeWindow.dispatchEvent({ type: "orientationchange" });
  assert.equal(harness.frames.length, 1);
  harness.flushFrame();
  assert.deepEqual(harness.writes, [["--app-height", "612px"]]);

  harness.viewport.height = 613.2;
  harness.viewport.dispatchEvent({ type: "resize" });
  assert.equal(harness.frames.length, 1);
  harness.flushFrame();
  assert.deepEqual(harness.writes, [
    ["--app-height", "612px"],
    ["--app-height", "613px"],
  ]);

  harness.viewport.height = 613.4;
  harness.viewport.dispatchEvent({ type: "scroll" });
  harness.fakeWindow.dispatchEvent({ type: "resize" });
  assert.equal(harness.frames.length, 1);
  harness.flushFrame();
  assert.equal(harness.frames.length, 0);
  assert.equal(harness.writes.length, 2);
  assert.equal(harness.sendQueryCalls, 0);
});

test("viewport geometry marks short visual viewports within the coalesced frame", () => {
  const harness = createViewportGeometryHarness({
    innerHeight: 900,
    visualViewportHeight: 700,
    withVisualViewport: true,
  });
  assert.equal(harness.frames.length, 1);
  harness.flushFrame();
  assert.equal(harness.root.classList.contains("visual-viewport-short"), false);
  assert.deepEqual(harness.writes, [["--app-height", "700px"]]);
  assert.equal(harness.sendQueryCalls, 0);

  harness.viewport.height = 300;
  harness.viewport.dispatchEvent({ type: "resize" });
  harness.viewport.dispatchEvent({ type: "scroll" });
  harness.fakeWindow.dispatchEvent({ type: "resize" });
  harness.fakeWindow.dispatchEvent({ type: "orientationchange" });
  assert.equal(harness.frames.length, 1);
  harness.flushFrame();
  assert.equal(harness.root.classList.contains("visual-viewport-short"), true);
  assert.deepEqual(harness.writes, [
    ["--app-height", "700px"],
    ["--app-height", "300px"],
  ]);
  assert.equal(harness.sendQueryCalls, 0);

  harness.viewport.height = 640;
  harness.viewport.dispatchEvent({ type: "scroll" });
  harness.viewport.dispatchEvent({ type: "resize" });
  harness.fakeWindow.dispatchEvent({ type: "orientationchange" });
  harness.fakeWindow.dispatchEvent({ type: "resize" });
  assert.equal(harness.frames.length, 1);
  harness.flushFrame();
  assert.equal(harness.root.classList.contains("visual-viewport-short"), false);
  assert.deepEqual(harness.writes, [
    ["--app-height", "700px"],
    ["--app-height", "300px"],
    ["--app-height", "640px"],
  ]);
  assert.equal(harness.sendQueryCalls, 0);
});

test("viewport geometry leaves CSS fallback untouched without VisualViewport", () => {
  const harness = createViewportGeometryHarness({
    innerHeight: 640,
    visualViewportHeight: 0,
    withVisualViewport: false,
  });
  assert.equal(harness.viewport, undefined);
  assert.equal(harness.frames.length, 0);
  assert.equal(harness.root.classList.contains("visual-viewport-short"), false);
  assert.deepEqual(harness.writes, []);

  harness.fakeWindow.innerHeight = 568.2;
  harness.fakeWindow.dispatchEvent({ type: "resize" });
  harness.fakeWindow.dispatchEvent({ type: "orientationchange" });
  assert.equal(harness.frames.length, 0);
  assert.equal(harness.root.classList.contains("visual-viewport-short"), false);
  assert.deepEqual(harness.writes, []);
  assert.equal(harness.sendQueryCalls, 0);
});

const task6SeamStart = script.indexOf("const presentationStateValues");
const task6SeamEnd = script.indexOf("const unsafePublicTextPatterns", task6SeamStart);
assert.ok(
  task6SeamStart >= 0 && task6SeamEnd > task6SeamStart,
  "production presentation/input seam must exist",
);
const task6SeamSource = script.slice(task6SeamStart, task6SeamEnd);
const runDemoQueryStart = script.indexOf("function runDemoQuery(");
const runDemoQueryEnd = script.indexOf("async function loadDemoQuestions", runDemoQueryStart);
assert.ok(
  runDemoQueryStart >= 0 && runDemoQueryEnd > runDemoQueryStart,
  "production runDemoQuery seam must exist",
);
const runDemoQuerySource = script.slice(runDemoQueryStart, runDemoQueryEnd);

function createTask6Harness({
  fine = true,
  coarse = false,
  anyPointerCoarse = coarse,
  activeInput = true,
  requestPending = false,
  value = "",
  scrollHeight = 30,
} = {}) {
  const sendCalls = [];
  const focusCalls = [];
  const timers = [];
  const shell = { dataset: { presentationState: "landing" } };
  const demoToggle = {
    attributes: new Map(),
    textContent: "收起示例问题",
    setAttribute(name, nextValue) {
      this.attributes.set(String(name), String(nextValue));
    },
    getAttribute(name) {
      return this.attributes.get(String(name)) ?? null;
    },
  };
  const input = {
    value,
    scrollHeight,
    style: {
      height: "",
      maxHeight: "",
      overflowY: "hidden",
    },
    focus(options) {
      focusCalls.push(options);
    },
  };
  const form = {
    requestSubmitCalls: 0,
    requestSubmit() {
      this.requestSubmitCalls += 1;
    },
  };
  const fakeDocument = {
    activeElement: activeInput ? input : { id: "elsewhere" },
  };
  const fakeWindow = {
    getComputedStyle() {
      return {
        lineHeight: "20px",
        paddingTop: "4px",
        paddingBottom: "4px",
        borderTopWidth: "1px",
        borderBottomWidth: "1px",
      };
    },
    matchMedia(query) {
      if (query === "(pointer: fine)") return { matches: fine };
      if (query === "(pointer: coarse)") return { matches: coarse };
      if (query === "(any-pointer: coarse)") return { matches: anyPointerCoarse };
      return { matches: false };
    },
  };
  const taskContext = vm.createContext({
    clearTimeout() {},
    demoToggle,
    document: fakeDocument,
    form,
    input,
    maintainFollowingScroll() {},
    requestPending,
    queuedDemoQuery: null,
    sendQuery(...args) {
      sendCalls.push(args);
    },
    setTimeout(callback) {
      timers.push(callback);
      return timers.length;
    },
    shell,
    window: fakeWindow,
  });
  vm.runInContext(
    `${task6SeamSource}\n` +
      "globalThis.__task6Seam = { setPresentationState, toggleDemoQuestions, usesFinePointer, shouldRestoreInputFocus, restoreInputFocus, resizeInputHeight, resetInputHeight, submitInputQuery, handleInputKeydown, handleCompositionStart, handleCompositionEnd };",
    taskContext,
    { filename: chatPath.pathname },
  );
  vm.runInContext(
    `${runDemoQuerySource}\n` +
      "globalThis.__runDemoQuery = runDemoQuery;",
    taskContext,
    { filename: chatPath.pathname },
  );

  return {
    context: taskContext,
    demoToggle,
    focusCalls,
    form,
    input,
    seam: taskContext.__task6Seam,
    sendCalls,
    shell,
    flushTimers() {
      for (const callback of timers.splice(0)) callback();
    },
    runDemoQuery(query) {
      taskContext.__runDemoQuery(query);
    },
  };
}

function enterEvent(overrides = {}) {
  return {
    isComposing: false,
    key: "Enter",
    preventDefaultCalls: 0,
    shiftKey: false,
    preventDefault() {
      this.preventDefaultCalls += 1;
    },
    ...overrides,
  };
}

function createTask6SendQueryHarness({
  fine = true,
  coarse = false,
  anyPointerCoarse = coarse,
  activeInput = true,
  terminal = "answer",
} = {}) {
  const fetchCalls = [];
  const focusCalls = [];
  const shell = { dataset: { presentationState: "conversation" } };
  const demoToggle = {
    setAttribute() {},
    textContent: "",
  };
  const input = {
    value: "待清空",
    scrollHeight: 72,
    style: {
      height: "72px",
      maxHeight: "90px",
      overflowY: "auto",
    },
    focus(options) {
      focusCalls.push(options);
    },
  };
  let stopAction = null;
  let cancelCalls = 0;
  const responseBody = {};
  const responseReader = {
    cancel() {
      cancelCalls += 1;
      return Promise.resolve();
    },
  };
  const events = terminal === "answer"
    ? [
        ["answer", { answer_text: "公开回答" }],
        ["done", {}],
      ]
    : terminal === "error"
      ? [["error", { detail: "查询失败" }]]
      : [["stage", { name: "synthesis" }]];
  const sendContext = vm.createContext({
    beginContinuationRequest() {
      return { previous: null, optionFollowUp: false };
    },
    settleContinuationOwners() {},
    clearTimeout() {},
    create() {
      return {};
    },
    demoToggle,
    document: {
      activeElement: activeInput ? input : { id: "elsewhere" },
    },
    form: { requestSubmit() {} },
    input,
    messages: { append() {} },
    messageShell() {
      return {
        row: {},
        bubble: { append() {} },
      };
    },
    queueMicrotask,
    queuedDemoQuery: null,
    removeWelcome() {},
    startFollowingTurn() {},
    notifyContentUpdate() {},
    renderAssistant() {},
    renderContinuation() {
      return null;
    },
    renderError() {},
    renderProcess() {
      return {
        addAction(_label, callback) {
          stopAction = callback;
        },
        finish() {},
        set() {},
      };
    },
    renderStreamingMarkdown() {
      return { append() {}, flush() {} };
    },
    renderUser() {},
    requestPending: false,
    async fetch(url, options) {
      fetchCalls.push([url, options]);
      return { body: responseBody, ok: true, status: 200 };
    },
    async readSseEvents(_body, onEvent, onReader) {
      if (onReader) onReader(responseReader);
      for (const [eventName, data] of events) {
        onEvent(eventName, data);
        if (terminal === "stop" && stopAction) stopAction();
      }
    },
    scrollToLatest() {},
    setTimeout() {
      return 1;
    },
    shell,
    submit: { disabled: false, textContent: "发送" },
    window: {
      getComputedStyle() {
        return {
          lineHeight: "20px",
          paddingTop: "4px",
          paddingBottom: "4px",
          borderTopWidth: "1px",
          borderBottomWidth: "1px",
        };
      },
      matchMedia(query) {
        if (query === "(pointer: fine)") return { matches: fine };
        if (query === "(pointer: coarse)") return { matches: coarse };
        if (query === "(any-pointer: coarse)") return { matches: anyPointerCoarse };
        return { matches: false };
      },
    },
  });
  vm.runInContext(
    `${task6SeamSource}\n` +
      "globalThis.__task6Seam = { shouldRestoreInputFocus, restoreInputFocus };",
    sendContext,
    { filename: chatPath.pathname },
  );
  vm.runInContext(
    `${script.slice(sendQueryStart, sendQueryEnd)}\n` +
      "globalThis.__task6SendQuery = sendQuery;",
    sendContext,
    { filename: chatPath.pathname },
  );

  return {
    context: sendContext,
    fetchCalls,
    focusCalls,
    input,
    shell,
    get cancelCalls() {
      return cancelCalls;
    },
  };
}

test("Task 6 submits once, leaves whitespace inert, and enters conversation", () => {
  const accepted = createTask6Harness({ activeInput: false, value: "  深圳科创  " });
  assert.equal(accepted.seam.submitInputQuery(), true);
  assert.equal(accepted.shell.dataset.presentationState, "conversation");
  assert.equal(accepted.demoToggle.getAttribute("aria-expanded"), "false");
  assert.equal(accepted.demoToggle.textContent, "展开示例问题");
  assert.deepEqual(accepted.sendCalls, [["深圳科创", null, null, false]]);

  const blank = createTask6Harness({ value: " \n\t " });
  assert.equal(blank.seam.submitInputQuery(), false);
  assert.equal(blank.shell.dataset.presentationState, "landing");
  assert.equal(blank.sendCalls.length, 0);
});

test("Task 6 toggles demo presentation and demo selection returns to conversation", () => {
  const harness = createTask6Harness();
  harness.seam.setPresentationState("conversation");
  harness.seam.toggleDemoQuestions();
  assert.equal(harness.shell.dataset.presentationState, "demo-expanded");
  assert.equal(harness.demoToggle.getAttribute("aria-expanded"), "true");
  assert.equal(harness.demoToggle.textContent, "收起示例问题");

  harness.seam.toggleDemoQuestions();
  assert.equal(harness.shell.dataset.presentationState, "conversation");
  harness.seam.toggleDemoQuestions();
  harness.runDemoQuery("  示例查询  ");
  assert.equal(harness.shell.dataset.presentationState, "conversation");
  assert.equal(harness.input.value, "示例查询");
  assert.deepEqual(harness.sendCalls, [["示例查询"]]);

  const pending = createTask6Harness({ requestPending: true });
  pending.runDemoQuery("排队示例");
  assert.equal(pending.shell.dataset.presentationState, "conversation");
  assert.equal(pending.sendCalls.length, 0);
  assert.equal(pending.context.queuedDemoQuery, "排队示例");
  assert.equal(pending.focusCalls.length, 0);
});

test("Task 6 uses fine-pointer Enter only and preserves Shift+Enter and coarse Enter", () => {
  const fine = createTask6Harness({ fine: true, coarse: false });
  const plainEnter = enterEvent();
  fine.seam.handleInputKeydown(plainEnter);
  assert.equal(plainEnter.preventDefaultCalls, 1);
  assert.equal(fine.form.requestSubmitCalls, 1);

  const shiftedEnter = enterEvent({ shiftKey: true });
  fine.seam.handleInputKeydown(shiftedEnter);
  assert.equal(shiftedEnter.preventDefaultCalls, 0);
  assert.equal(fine.form.requestSubmitCalls, 1);

  const coarse = createTask6Harness({ fine: true, coarse: true });
  const coarseEnter = enterEvent();
  coarse.seam.handleInputKeydown(coarseEnter);
  assert.equal(coarseEnter.preventDefaultCalls, 0);
  assert.equal(coarse.form.requestSubmitCalls, 0);
});

test("Task 6 preserves Enter on a fine-primary device with any coarse pointer", () => {
  const hybrid = createTask6Harness({
    fine: true,
    coarse: false,
    anyPointerCoarse: true,
  });
  const hybridEnter = enterEvent();

  hybrid.seam.handleInputKeydown(hybridEnter);

  assert.equal(hybridEnter.preventDefaultCalls, 0);
  assert.equal(hybrid.form.requestSubmitCalls, 0);
});

test("Task 6 suppresses composing and compositionend-adjacent Enter", () => {
  const composing = createTask6Harness();
  composing.seam.handleCompositionStart();
  composing.seam.handleInputKeydown(enterEvent());
  assert.equal(composing.form.requestSubmitCalls, 0);

  const browserComposing = createTask6Harness();
  browserComposing.seam.handleInputKeydown(enterEvent({ isComposing: true }));
  assert.equal(browserComposing.form.requestSubmitCalls, 0);

  const ended = createTask6Harness();
  ended.seam.handleCompositionStart();
  ended.seam.handleCompositionEnd();
  ended.seam.handleInputKeydown(enterEvent());
  assert.equal(ended.form.requestSubmitCalls, 0);
  ended.flushTimers();
  ended.seam.handleInputKeydown(enterEvent());
  assert.equal(ended.form.requestSubmitCalls, 1);
});

test("Task 6 bounds textarea autogrowth at four lines and resets accepted input", () => {
  const harness = createTask6Harness({ scrollHeight: 30 });
  harness.seam.resizeInputHeight();
  assert.equal(harness.input.style.height, "30px");
  assert.equal(harness.input.style.maxHeight, "90px");
  assert.equal(harness.input.style.overflowY, "hidden");

  harness.input.scrollHeight = 90;
  harness.seam.resizeInputHeight();
  assert.equal(harness.input.style.height, "90px");
  assert.equal(harness.input.style.overflowY, "hidden");

  harness.input.scrollHeight = 130;
  harness.seam.resizeInputHeight();
  assert.equal(harness.input.style.height, "90px");
  assert.equal(harness.input.style.overflowY, "auto");

  harness.seam.resetInputHeight();
  assert.equal(harness.input.style.height, "auto");
  assert.equal(harness.input.style.overflowY, "hidden");
});

test("Task 6 restores focus only for an active fine-pointer composer", () => {
  const fineActive = createTask6Harness({ fine: true, coarse: false, activeInput: true });
  const restoreFine = fineActive.seam.shouldRestoreInputFocus();
  assert.equal(restoreFine, true);
  fineActive.seam.restoreInputFocus(restoreFine);
  assert.equal(fineActive.focusCalls.length, 1);
  assert.equal(fineActive.focusCalls[0].preventScroll, true);
  assert.deepEqual(Object.keys(fineActive.focusCalls[0]), ["preventScroll"]);

  const fineInactive = createTask6Harness({ fine: true, coarse: false, activeInput: false });
  const restoreInactive = fineInactive.seam.shouldRestoreInputFocus();
  assert.equal(restoreInactive, false);
  fineInactive.seam.restoreInputFocus(restoreInactive);
  assert.equal(fineInactive.focusCalls.length, 0);

  const coarseActive = createTask6Harness({ fine: true, coarse: true, activeInput: true });
  assert.equal(coarseActive.seam.shouldRestoreInputFocus(), false);
  coarseActive.seam.restoreInputFocus(true);
  assert.equal(coarseActive.focusCalls.length, 0);
});

test("Task 6 accepted send clears textarea, preserves body, and restores fine focus once", async () => {
  const harness = createTask6SendQueryHarness();
  await harness.context.__task6SendQuery("  公开问题  ", null, null, true);

  assert.equal(harness.input.value, "");
  assert.equal(harness.input.style.height, "auto");
  assert.equal(harness.input.style.overflowY, "hidden");
  assert.equal(harness.fetchCalls.length, 1);
  const [url, options] = harness.fetchCalls[0];
  assert.equal(url, "/api/chat/stream");
  assert.deepEqual(JSON.parse(options.body), { query: "公开问题" });
  assert.equal(harness.focusCalls.length, 1);
  assert.equal(harness.focusCalls[0].preventScroll, true);
  assert.deepEqual(Object.keys(harness.focusCalls[0]), ["preventScroll"]);
});

test("Task 6 never restores hybrid-pointer focus or presentation state after terminal paths", async (t) => {
  for (const terminal of ["answer", "error", "stop"]) {
    await t.test(terminal, async () => {
      const harness = createTask6SendQueryHarness({
        activeInput: true,
        fine: true,
        coarse: false,
        anyPointerCoarse: true,
        terminal,
      });
      await harness.context.__task6SendQuery("公开问题", null, null, true);
      assert.equal(harness.focusCalls.length, 0);
      assert.equal(harness.shell.dataset.presentationState, "conversation");
      if (terminal === "stop") assert.equal(harness.cancelCalls, 1);
    });
  }
});

test("Task 6 registers one composer and demo listener per event", () => {
  const counts = new Map([
    ["form submit", /form\.addEventListener\("submit"/g],
    ["input keydown", /input\.addEventListener\("keydown"/g],
    ["input resize", /input\.addEventListener\("input"/g],
    ["compositionstart", /input\.addEventListener\("compositionstart"/g],
    ["compositionend", /input\.addEventListener\("compositionend"/g],
    ["demo toggle", /demoToggle\.addEventListener\("click"/g],
    ["demo grid", /demoGrid\.addEventListener\("click"/g],
  ]);
  for (const [label, pattern] of counts) {
    assert.equal([...script.matchAll(pattern)].length, 1, label);
  }
  assert.equal(script.includes("input.focus();"), false);
});

function productionTask7ScrollSource() {
  const start = script.indexOf("const scrollIntentValues");
  const end = script.indexOf("function messageShell(kind)", start);
  assert.ok(
    start >= 0 && end > start,
    "Task 7 production scroll-intent seam must exist",
  );
  return script.slice(start, end);
}

function productionPresentationLayoutSource() {
  const start = script.indexOf("const presentationStateValues");
  const end = script.indexOf("function usesFinePointer()", start);
  assert.ok(
    start >= 0 && end > start,
    "Task 7 production presentation-layout seam must exist",
  );
  return script.slice(start, end);
}

function createTask7LayoutHarness({
  appHeight = 700,
  demoHeight = 100,
  messagesChrome = 300,
  scrollHeight = 1000,
  scrollTop = 600,
} = {}) {
  const frames = [];
  let currentAppHeight = appHeight;
  let currentPresentationState = "conversation";
  let currentScrollTop = scrollTop;
  let scrollTopWrites = 0;

  const currentClientHeight = () => (
    currentAppHeight
    - messagesChrome
    - (currentPresentationState === "demo-expanded" ? demoHeight : 0)
  );
  const messages = new FakeEventTarget();
  messages.dataset = {};
  Object.defineProperties(messages, {
    clientHeight: { get: currentClientHeight },
    scrollHeight: { get: () => scrollHeight },
    scrollTop: {
      get: () => currentScrollTop,
      set(value) {
        scrollTopWrites += 1;
        const maxScrollTop = Math.max(0, scrollHeight - currentClientHeight());
        currentScrollTop = Math.max(0, Math.min(Number(value), maxScrollTop));
      },
    },
  });
  messages.focus = () => {};

  const backToLatest = new FakeEventTarget();
  backToLatest.hidden = true;
  const demoToggle = {
    setAttribute() {},
    textContent: "展开示例问题",
  };
  const shell = { dataset: {} };
  Object.defineProperty(shell.dataset, "presentationState", {
    get: () => currentPresentationState,
    set(value) {
      currentPresentationState = String(value);
    },
  });

  const rootClasses = new Set();
  const root = {
    classList: {
      toggle(name, force) {
        const key = String(name);
        if (force) rootClasses.add(key);
        else rootClasses.delete(key);
      },
    },
    style: {
      setProperty(name, value) {
        if (name === "--app-height") currentAppHeight = Number.parseFloat(value);
      },
    },
  };
  const viewport = new FakeEventTarget();
  viewport.height = appHeight;
  const fakeWindow = new FakeEventTarget();
  fakeWindow.visualViewport = viewport;
  fakeWindow.requestAnimationFrame = (callback) => {
    frames.push(callback);
    return frames.length;
  };
  const fakeDocument = {
    activeElement: { id: "elsewhere" },
    documentElement: root,
  };
  const layoutContext = vm.createContext({
    backToLatest,
    demoToggle,
    document: fakeDocument,
    messages,
    shell,
    window: fakeWindow,
  });
  vm.runInContext(
    `${productionViewportGeometrySource()}\n` +
      `${productionPresentationLayoutSource()}\n` +
      `${productionTask7ScrollSource()}\n` +
      "globalThis.__task7LayoutSeam = { installViewportGeometry, setPresentationState, getScrollIntent: () => scrollIntent };",
    layoutContext,
    { filename: chatPath.pathname },
  );
  layoutContext.__task7LayoutSeam.installViewportGeometry();
  while (frames.length) frames.shift()();
  scrollTopWrites = 0;

  return {
    backToLatest,
    frames,
    messages,
    seam: layoutContext.__task7LayoutSeam,
    changeViewportHeight(nextHeight) {
      viewport.height = nextHeight;
      viewport.dispatchEvent({ type: "resize" });
    },
    flushFrame() {
      assert.ok(frames.length > 0, "an animation frame must be pending");
      frames.shift()();
    },
    userDetach(nextScrollTop = 320) {
      currentScrollTop = nextScrollTop;
      messages.dispatchEvent({ type: "scroll" });
      scrollTopWrites = 0;
    },
    get clientHeight() {
      return currentClientHeight();
    },
    get scrollTop() {
      return currentScrollTop;
    },
    get scrollTopWrites() {
      return scrollTopWrites;
    },
  };
}

function createTask7ScrollHarness({
  clientHeight = 400,
  scrollHeight = 1000,
  scrollTop = 600,
} = {}) {
  const focusCalls = [];
  const frames = [];
  const reads = { clientHeight: 0, scrollHeight: 0, scrollTop: 0 };
  const writes = { scrollTop: 0 };
  const fakeDocument = { activeElement: { id: "elsewhere" } };
  let currentScrollTop = scrollTop;
  const messages = new FakeEventTarget();
  messages.dataset = {};
  messages.focus = (options) => {
    focusCalls.push(options);
    fakeDocument.activeElement = messages;
  };
  Object.defineProperties(messages, {
    clientHeight: {
      get() {
        reads.clientHeight += 1;
        return clientHeight;
      },
    },
    scrollHeight: {
      get() {
        reads.scrollHeight += 1;
        return scrollHeight;
      },
    },
    scrollTop: {
      get() {
        reads.scrollTop += 1;
        return currentScrollTop;
      },
      set(value) {
        writes.scrollTop += 1;
        currentScrollTop = Number(value);
      },
    },
  });
  const backToLatest = new FakeEventTarget();
  backToLatest.hidden = true;
  const fakeWindow = {
    requestAnimationFrame(callback) {
      frames.push(callback);
      return frames.length;
    },
  };
  const scrollContext = vm.createContext({
    backToLatest,
    document: fakeDocument,
    messages,
    window: fakeWindow,
  });
  vm.runInContext(
    `${productionTask7ScrollSource()}\n` +
      "globalThis.__task7ScrollSeam = { notifyContentUpdate, getScrollIntent: () => scrollIntent, getHasUnreadContent: () => hasUnreadContent };",
    scrollContext,
    { filename: chatPath.pathname },
  );

  return {
    backToLatest,
    context: scrollContext,
    focusCalls,
    frames,
    messages,
    reads,
    seam: scrollContext.__task7ScrollSeam,
    writes,
    flushFrame() {
      assert.ok(frames.length > 0, "a following-scroll frame must be pending");
      frames.shift()();
    },
    focusBackToLatest() {
      fakeDocument.activeElement = backToLatest;
    },
    resetMeasurements() {
      reads.clientHeight = 0;
      reads.scrollHeight = 0;
      reads.scrollTop = 0;
      writes.scrollTop = 0;
    },
    userScroll(nextScrollTop) {
      currentScrollTop = nextScrollTop;
      messages.dispatchEvent({ type: "scroll" });
    },
    get activeElement() {
      return fakeDocument.activeElement;
    },
    get scrollTop() {
      return currentScrollTop;
    },
    get totalLayoutReads() {
      return reads.clientHeight + reads.scrollHeight + reads.scrollTop;
    },
  };
}

test("Task 7 layout changes maintain the bottom only while following", () => {
  const presentationFollowing = createTask7LayoutHarness();
  assert.equal(presentationFollowing.clientHeight, 400);
  presentationFollowing.seam.setPresentationState("demo-expanded");
  assert.equal(presentationFollowing.clientHeight, 300);
  assert.equal(
    presentationFollowing.frames.length,
    1,
    "presentation layout changes must use the existing following-scroll frame",
  );
  assert.equal(presentationFollowing.scrollTop, 600);
  presentationFollowing.flushFrame();
  assert.equal(presentationFollowing.scrollTop, 700);
  assert.equal(presentationFollowing.scrollTopWrites, 1);

  const presentationDetached = createTask7LayoutHarness();
  presentationDetached.userDetach();
  presentationDetached.seam.setPresentationState("demo-expanded");
  assert.equal(presentationDetached.clientHeight, 300);
  assert.equal(presentationDetached.frames.length, 0);
  assert.equal(presentationDetached.scrollTop, 320);
  assert.equal(presentationDetached.scrollTopWrites, 0);
  assert.equal(presentationDetached.seam.getScrollIntent(), "detached");

  const viewportFollowing = createTask7LayoutHarness();
  viewportFollowing.changeViewportHeight(600);
  assert.equal(viewportFollowing.frames.length, 1, "viewport geometry keeps its own frame");
  viewportFollowing.flushFrame();
  assert.equal(viewportFollowing.clientHeight, 300);
  assert.equal(
    viewportFollowing.frames.length,
    1,
    "the geometry write must request the existing following-scroll frame",
  );
  assert.equal(viewportFollowing.scrollTop, 600);
  viewportFollowing.flushFrame();
  assert.equal(viewportFollowing.scrollTop, 700);
  assert.equal(viewportFollowing.scrollTopWrites, 1);

  const viewportDetached = createTask7LayoutHarness();
  viewportDetached.userDetach();
  viewportDetached.changeViewportHeight(600);
  assert.equal(viewportDetached.frames.length, 1);
  viewportDetached.flushFrame();
  assert.equal(viewportDetached.clientHeight, 300);
  assert.equal(viewportDetached.frames.length, 0);
  assert.equal(viewportDetached.scrollTop, 320);
  assert.equal(viewportDetached.scrollTopWrites, 0);
  assert.equal(viewportDetached.seam.getScrollIntent(), "detached");
});

test("Task 7 detaches on upward scroll and returns to latest only on request", () => {
  const harness = createTask7ScrollHarness();
  assert.equal(harness.messages.dataset.scrollIntent, "following");
  assert.equal(harness.seam.getScrollIntent(), "following");
  assert.equal(harness.backToLatest.hidden, true);

  harness.userScroll(598);
  assert.equal(harness.seam.getScrollIntent(), "following", "2px is still latest");
  harness.userScroll(500);
  assert.equal(harness.messages.dataset.scrollIntent, "detached");
  assert.equal(harness.backToLatest.hidden, true);

  harness.resetMeasurements();
  harness.seam.notifyContentUpdate();
  assert.equal(harness.scrollTop, 500);
  assert.equal(harness.frames.length, 0);
  assert.equal(harness.totalLayoutReads, 0);
  assert.equal(harness.writes.scrollTop, 0);
  assert.equal(harness.seam.getHasUnreadContent(), true);
  assert.equal(harness.backToLatest.hidden, false);

  harness.backToLatest.dispatchEvent({ type: "click" });
  assert.equal(harness.messages.dataset.scrollIntent, "following");
  assert.equal(harness.seam.getHasUnreadContent(), false);
  assert.equal(harness.backToLatest.hidden, true);
  assert.equal(harness.scrollTop, 1000);
  assert.equal(harness.writes.scrollTop, 1);
});

test("Task 7 returns keyboard focus to messages without stealing pointer focus", () => {
  const keyboard = createTask7ScrollHarness();
  keyboard.userScroll(500);
  keyboard.seam.notifyContentUpdate();
  keyboard.focusBackToLatest();
  assert.equal(keyboard.activeElement, keyboard.backToLatest);

  keyboard.backToLatest.dispatchEvent({ type: "click" });
  assert.equal(keyboard.seam.getScrollIntent(), "following");
  assert.equal(keyboard.seam.getHasUnreadContent(), false);
  assert.equal(keyboard.backToLatest.hidden, true);
  assert.equal(keyboard.scrollTop, 1000);
  assert.equal(keyboard.activeElement, keyboard.messages);
  assert.equal(keyboard.focusCalls.length, 1);
  assert.equal(keyboard.focusCalls[0].preventScroll, true);

  const pointer = createTask7ScrollHarness();
  const pointerFocus = pointer.activeElement;
  pointer.userScroll(500);
  pointer.seam.notifyContentUpdate();
  pointer.backToLatest.dispatchEvent({ type: "click" });
  assert.equal(pointer.backToLatest.hidden, true);
  assert.equal(pointer.activeElement, pointerFocus);
  assert.equal(pointer.focusCalls.length, 0);

  const flowUpdate = createTask7ScrollHarness();
  const flowFocus = flowUpdate.activeElement;
  flowUpdate.seam.notifyContentUpdate();
  assert.equal(flowUpdate.activeElement, flowFocus);
  assert.equal(flowUpdate.focusCalls.length, 0);
});

test("Task 7 coalesces following updates and cancels a stale frame after detaching", () => {
  const harness = createTask7ScrollHarness();
  harness.resetMeasurements();

  harness.seam.notifyContentUpdate();
  harness.seam.notifyContentUpdate();
  harness.seam.notifyContentUpdate();
  assert.equal(harness.frames.length, 1);
  assert.equal(harness.totalLayoutReads, 0);
  assert.equal(harness.writes.scrollTop, 0);

  harness.flushFrame();
  assert.equal(harness.frames.length, 0);
  assert.equal(harness.scrollTop, 1000);
  assert.equal(harness.reads.scrollHeight, 1);
  assert.equal(harness.writes.scrollTop, 1);

  harness.resetMeasurements();
  harness.seam.notifyContentUpdate();
  assert.equal(harness.frames.length, 1);
  harness.userScroll(400);
  assert.equal(harness.seam.getScrollIntent(), "detached");
  harness.resetMeasurements();
  harness.flushFrame();
  assert.equal(harness.frames.length, 0);
  assert.equal(harness.scrollTop, 400);
  assert.equal(harness.totalLayoutReads, 0);
  assert.equal(harness.writes.scrollTop, 0);
});

function createTask7TurnHarness({ terminal = "answer", initiallyDetached = false } = {}) {
  const frames = [];
  let currentScrollHeight = 1000;
  let currentScrollTop = 600;
  let detachedForTerminal = false;
  let didAutoDetach = false;
  let writesAfterDetach = 0;
  let stopAction = null;
  let cancelCalls = 0;
  let intentAtFetch = null;
  let backToLatestHiddenAtFetch = null;

  const messages = new FakeEventTarget();
  messages.dataset = {};
  messages.children = [];
  messages.append = (...nodes) => {
    messages.children.push(...nodes);
    currentScrollHeight += 40;
  };
  Object.defineProperties(messages, {
    clientHeight: { get: () => 400 },
    scrollHeight: { get: () => currentScrollHeight },
    scrollTop: {
      get: () => currentScrollTop,
      set(value) {
        currentScrollTop = Number(value);
        if (detachedForTerminal) writesAfterDetach += 1;
      },
    },
  });

  const backToLatest = new FakeEventTarget();
  backToLatest.hidden = true;
  const input = { value: "待清空" };
  const submit = { disabled: false, textContent: "发送" };
  const responseBody = {};
  const responseReader = {
    cancel() {
      cancelCalls += 1;
      return Promise.resolve();
    },
  };
  const mutateContent = () => {
    currentScrollHeight += 20;
  };
  const view = {
    bubble: { append: mutateContent },
    row: {},
  };
  const terminalEvents = {
    answer: [
      ["answer_chunk", { text: "流式片段" }],
      ["answer", { answer_text: "完整回答", citations: [] }],
      ["done", {}],
    ],
    error: [
      ["answer_chunk", { text: "流式片段" }],
      ["error", { detail: "查询失败" }],
    ],
    stop: [["stage", { name: "synthesis" }]],
    bareEof: [["answer_chunk", { text: "流式片段" }]],
  };
  const events = terminalEvents[terminal];
  assert.ok(events, `unsupported Task 7 terminal: ${terminal}`);

  const fakeWindow = {
    requestAnimationFrame(callback) {
      frames.push(callback);
      return frames.length;
    },
  };
  const turnContext = vm.createContext({
    beginContinuationRequest() {
      return { previous: null, optionFollowUp: false };
    },
    settleContinuationOwners() {},
    backToLatest,
    create() {
      return {};
    },
    input,
    messages,
    messageShell() {
      return view;
    },
    queueMicrotask,
    queuedDemoQuery: null,
    removeWelcome() {},
    renderAssistant() {
      mutateContent();
    },
    renderContinuation() {
      return null;
    },
    renderError() {
      mutateContent();
    },
    renderProcess() {
      return {
        addAction(_label, callback) {
          stopAction = callback;
        },
        finish() {
          mutateContent();
        },
        set() {
          mutateContent();
        },
      };
    },
    renderStreamingMarkdown() {
      return {
        append() {
          mutateContent();
        },
        flush() {
          mutateContent();
        },
      };
    },
    renderUser() {
      mutateContent();
    },
    requestPending: false,
    resetInputHeight() {},
    restoreInputFocus() {},
    async fetch() {
      intentAtFetch = messages.dataset.scrollIntent;
      backToLatestHiddenAtFetch = backToLatest.hidden;
      return { body: responseBody, ok: true, status: 200 };
    },
    async readSseEvents(_body, onEvent, onReader) {
      if (onReader) onReader(responseReader);
      for (const [eventName, data] of events) {
        onEvent(eventName, data);
        if (!didAutoDetach) {
          didAutoDetach = true;
          currentScrollTop = 300;
          messages.dispatchEvent({ type: "scroll" });
          detachedForTerminal = true;
          writesAfterDetach = 0;
        }
        if (terminal === "stop" && stopAction) stopAction();
      }
    },
    submit,
    window: fakeWindow,
  });
  vm.runInContext(
    `${productionTask7ScrollSource()}\n` +
      "globalThis.__task7TurnScroll = { notifyContentUpdate, maintainFollowingScroll: typeof maintainFollowingScroll === 'function' ? maintainFollowingScroll : null, startFollowingTurn: typeof startFollowingTurn === 'function' ? startFollowingTurn : null, getScrollIntent: () => scrollIntent };",
    turnContext,
    { filename: chatPath.pathname },
  );
  vm.runInContext(
    `${script.slice(sendQueryStart, sendQueryEnd)}\n` +
      "globalThis.__task7SendQuery = sendQuery;",
    turnContext,
    { filename: chatPath.pathname },
  );

  const userDetach = () => {
    currentScrollTop = 300;
    messages.dispatchEvent({ type: "scroll" });
    detachedForTerminal = true;
    writesAfterDetach = 0;
  };
  if (initiallyDetached) {
    userDetach();
    turnContext.__task7TurnScroll.notifyContentUpdate();
  }

  return {
    backToLatest,
    frames,
    messages,
    seam: turnContext.__task7TurnScroll,
    async send() {
      await turnContext.__task7SendQuery("公开问题");
    },
    flushFrames() {
      while (frames.length) frames.shift()();
    },
    userDetach,
    get backToLatestHiddenAtFetch() {
      return backToLatestHiddenAtFetch;
    },
    get cancelCalls() {
      return cancelCalls;
    },
    get didAutoDetach() {
      return didAutoDetach;
    },
    get intentAtFetch() {
      return intentAtFetch;
    },
    get scrollTop() {
      return currentScrollTop;
    },
    get writesAfterDetach() {
      return writesAfterDetach;
    },
  };
}

test("Task 7 terminal paths preserve a detached reading position", async (t) => {
  for (const terminal of ["answer", "error", "stop", "bareEof"]) {
    await t.test(terminal, async () => {
      const harness = createTask7TurnHarness({ terminal });
      await harness.send();

      assert.equal(harness.didAutoDetach, true);
      assert.equal(harness.seam.getScrollIntent(), "detached");
      assert.equal(harness.messages.dataset.scrollIntent, "detached");
      assert.equal(harness.scrollTop, 300);
      assert.equal(harness.writesAfterDetach, 0);
      assert.equal(harness.backToLatest.hidden, false);
      if (terminal === "stop") assert.equal(harness.cancelCalls, 1);

      harness.flushFrames();
      assert.equal(harness.scrollTop, 300);
      assert.equal(harness.writesAfterDetach, 0);
      assert.equal(harness.seam.getScrollIntent(), "detached");
    });
  }
});

test("Task 7 a new turn explicitly resumes following before fetch", async () => {
  const harness = createTask7TurnHarness({ initiallyDetached: true });
  assert.equal(typeof harness.seam.startFollowingTurn, "function");
  assert.equal(harness.backToLatest.hidden, false);

  await harness.send();

  assert.equal(harness.intentAtFetch, "following");
  assert.equal(harness.backToLatestHiddenAtFetch, true);
});

test("Task 7 disclosure toggles maintain scrolling only while following", () => {
  const harness = createTask7TurnHarness();
  assert.equal(typeof harness.seam.maintainFollowingScroll, "function");
  assert.equal(
    [...script.matchAll(/\.addEventListener\("toggle", maintainFollowingScroll\)/g)].length,
    2,
    "evidence and process disclosures must share the following-only helper",
  );

  harness.seam.maintainFollowingScroll();
  assert.equal(harness.frames.length, 1);
  harness.flushFrames();

  harness.userDetach();
  harness.seam.maintainFollowingScroll();
  assert.equal(harness.frames.length, 0);
  assert.equal(harness.seam.getScrollIntent(), "detached");
  assert.equal(harness.backToLatest.hidden, true);
});

test("Task 7 content renderers delegate scrolling to the turn coordinator", () => {
  const userRenderer = script.slice(
    script.indexOf("function renderUser("),
    script.indexOf("function safeCitationUrl("),
  );
  const assistantRenderers = script.slice(
    script.indexOf("function renderAssistant("),
    script.indexOf("async function readSseEvents("),
  );
  const turnCoordinator = script.slice(sendQueryStart, sendQueryEnd);

  assert.equal(userRenderer.includes("scrollToLatest()"), false);
  assert.equal(assistantRenderers.includes("scrollToLatest()"), false);
  assert.equal(turnCoordinator.includes("scrollToLatest()"), false);
});
