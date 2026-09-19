"use strict";

/* Drives /chat's own inline script in a DOM stub: what does the 反馈 control send, and what
 * does the operator see while it does?
 *
 * Fixture source: the shipped page's inline script plus one constructed answered turn
 * (`B_company_topic_search`, "共找到 6 个企业。") and a stubbed transport — no backend, no
 * browser. The POST body printed below is what the page hands the wire, byte for byte.
 *
 * Run from `apps/admin-console`:
 *     node ../../.agents/runs/connect-collection-line/chat-feedback-harness/render_check.cjs
 * Environment: CHAT_FEEDBACK_HARNESS_REPO (repo root).
 *
 * What it locks: one inline control per answered turn (idle → open → sending → 已反馈), the
 * body carrying the answered turn's own query/query_type/answer_text plus the typed note, an
 * empty note going out as null, a 409 reading as 本次会话已过期，无法反馈 (never the machine
 * code), a plain HTTP failure keeping a short Chinese message and a retryable row, and the
 * control reserving no space while closed.
 */

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const REPO = process.env.CHAT_FEEDBACK_HARNESS_REPO || path.resolve(process.cwd(), "..", "..");
const PAGE = path.join(REPO, "apps/admin-console/backend/static/chat.html");
const html = fs.readFileSync(PAGE, "utf8");
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const styles = html.match(/<style>([\s\S]*?)<\/style>/)[1];

const QUERY = "深圳哪些公司做激光雷达";
const ANSWER = "共找到 6 个企业。";

class Node {
  constructor(tag) {
    this.tagName = String(tag).toUpperCase();
    this.children = [];
    this.parentNode = null;
    this.className = "";
    this.dataset = {};
    this.attributes = new Map();
    this.listeners = new Map();
    this.hidden = false;
    this.disabled = false;
    this.value = "";
    this.style = { cssText: "" };
    this._text = "";
  }

  append(...nodes) {
    for (const node of nodes) {
      const child = node instanceof Node ? node : new Node("#text");
      if (!(node instanceof Node)) child._text = String(node);
      child.parentNode = this;
      this.children.push(child);
    }
  }

  replaceChildren(...nodes) {
    for (const child of this.children) child.parentNode = null;
    this.children = [];
    this._text = "";
    this.append(...nodes);
  }

  remove() {
    if (!this.parentNode) return;
    this.parentNode.children.splice(this.parentNode.children.indexOf(this), 1);
    this.parentNode = null;
  }

  setAttribute(name, value) {
    this.attributes.set(String(name), String(value));
  }

  getAttribute(name) {
    const key = String(name);
    return this.attributes.has(key) ? this.attributes.get(key) : null;
  }

  addEventListener(type, handler) {
    const key = String(type);
    this.listeners.set(key, [...(this.listeners.get(key) || []), handler]);
  }

  dispatchEvent(event) {
    for (const handler of this.listeners.get(String(event.type)) || []) handler.call(this, event);
    return true;
  }

  click() {
    return this.dispatchEvent({ type: "click" });
  }

  closest(selector) {
    let node = this;
    while (node) {
      if (node.matches(selector)) return node;
      node = node.parentNode;
    }
    return null;
  }

  matches(selector) {
    const text = String(selector);
    if (text.startsWith(".")) {
      return String(this.className || "").split(/\s+/).includes(text.slice(1));
    }
    return this.tagName === text.toUpperCase();
  }

  descendants() {
    return this.children.flatMap((child) => [child, ...child.descendants()]);
  }

  querySelectorAll(selector) {
    return this.descendants().filter((node) => node.tagName !== "#TEXT" && node.matches(selector));
  }

  querySelector(selector) {
    const found = this.querySelectorAll(selector);
    return found.length ? found[0] : null;
  }

  get classList() {
    const node = this;
    return {
      toggle(name, force) {
        const classes = String(node.className || "").split(/\s+/).filter(Boolean);
        const has = classes.includes(name);
        const wanted = force === undefined ? !has : Boolean(force);
        if (wanted && !has) classes.push(name);
        if (!wanted && has) classes.splice(classes.indexOf(name), 1);
        node.className = classes.join(" ");
      },
    };
  }

  get childElementCount() {
    return this.children.length;
  }

  get parentElement() {
    return this.parentNode;
  }

  set textContent(value) {
    for (const child of this.children) child.parentNode = null;
    this.children = [];
    this._text = String(value);
  }

  get textContent() {
    return this._text + this.children.map((child) => child.textContent).join("");
  }
}

const document = {
  createElement: (tag) => new Node(tag),
  createTextNode: (text) => {
    const node = new Node("#text");
    node._text = String(text);
    return node;
  },
};

const seamStart = script.indexOf("const unsafePublicTextPatterns");
const seamEnd = script.indexOf("function renderDemoQuestions(", seamStart);
const renderStart = script.indexOf("function continuationText(option)");
const renderEnd = script.indexOf("function renderProcess(", renderStart);
const controlStart = script.indexOf("function renderFeedbackControl(");
assert.ok(seamStart >= 0 && seamEnd > seamStart, "production sanitizer seam must exist");
assert.ok(
  controlStart > renderStart && controlStart < renderEnd,
  "the feedback control must live in the answer renderer seam",
);
for (const rule of [".feedback-row", ".feedback-form[hidden]"]) {
  const escaped = rule.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  assert.ok(new RegExp(`^\\s*${escaped}\\s*\\{`, "m").test(styles), `missing CSS rule: ${rule}`);
}

function createHarness(options = {}) {
  const calls = [];
  const errors = [];
  const context = vm.createContext({
    document,
    messages: new Node("main"),
    fetch: async (url, request) => {
      calls.push({ url: String(url), method: request.method, body: JSON.parse(request.body) });
      if (options.failure) throw options.failure;
      const status = options.status === undefined ? 200 : options.status;
      return { ok: status >= 200 && status < 300, status, json: async () => options.payload || {} };
    },
    renderError: (detail) => errors.push(String(detail)),
    notifyContentUpdate() {},
    maintainFollowingScroll() {},
  });
  vm.runInContext(
    `${script.slice(seamStart, seamEnd)}\n` +
      `${script.slice(renderStart, renderEnd)}\n` +
      "globalThis.__seam = { renderAssistant };",
    context,
    { filename: "chat.html#inline" },
  );

  const bubble = new Node("div");
  const answer = { query_type: "B_company_topic_search", answer_text: ANSWER, citations: [], ...options.answer };
  context.__seam.renderAssistant(answer, QUERY, { row: new Node("article"), bubble });
  return {
    bubble,
    calls,
    errors,
    part: (name) => bubble.querySelector("." + name),
  };
}

const settle = async () => {
  for (let index = 0; index < 8; index += 1) await new Promise((resolve) => setImmediate(resolve));
};

async function file(harness, note) {
  harness.part("feedback-toggle").click();
  harness.part("feedback-note").value = note;
  harness.part("feedback-submit").click();
  await settle();
}

(async () => {
  const states = [];

  // 1. idle: one control, closed, nothing sent
  const happy = createHarness();
  assert.ok(happy.part("feedback-toggle"), "the answered turn carries one 反馈 control");
  assert.equal(happy.bubble.querySelectorAll(".feedback-toggle").length, 1);
  assert.equal(happy.part("feedback-toggle").textContent, "反馈");
  assert.equal(happy.part("feedback-form").hidden, true);
  states.push(["idle", happy.part("feedback-toggle").textContent, "表单隐藏"]);

  // 2. open → sending → 已反馈, with the exact body the page hands the wire
  happy.part("feedback-toggle").click();
  assert.equal(happy.part("feedback-form").hidden, false);
  states.push(["open", "备注行展开", "输入框 + 提交 / 取消"]);
  happy.part("feedback-note").value = "  结果里有不相关企业  ";
  happy.part("feedback-submit").click();
  assert.equal(happy.part("feedback-submit").disabled, true);
  states.push(["sending", "提交中（提交按钮禁用）", "取消与输入框同时禁用"]);
  await settle();
  assert.equal(happy.part("feedback-toggle").textContent, "已反馈");
  assert.equal(happy.part("feedback-toggle").disabled, true);
  states.push(["sent", "已反馈（按钮变灰不可再点）", "表单收起"]);
  assert.deepEqual(happy.errors, []);
  assert.equal(happy.calls.length, 1);

  const posted = happy.calls[0];
  assert.equal(posted.method, "POST");
  assert.equal(posted.url, "api/chat/feedback");
  assert.deepEqual(posted.body, {
    query: QUERY,
    query_type: "B_company_topic_search",
    answer_text: ANSWER,
    feedback_type: "incorrect_answer",
    note: "结果里有不相关企业",
  });
  assert.equal(posted.body.feedback_type, "incorrect_answer");

  // 3. an empty note travels as null
  const blank = createHarness();
  await file(blank, "   ");
  assert.equal(blank.calls[0].body.note, null);

  // 4. a 409 reads as an expired session, never as the machine code
  const expired = createHarness({
    status: 409,
    payload: { detail: "canonical_v2_feedback_checkpoint_required" },
  });
  await file(expired, "结果里有不相关企业");
  assert.deepEqual(expired.errors, ["本次会话已过期，无法反馈"]);
  assert.equal(expired.part("feedback-submit").disabled, false);

  // 5. a plain failure keeps a short Chinese message and the row retryable
  const broken = createHarness({ status: 500 });
  await file(broken, "结果里有不相关企业");
  assert.deepEqual(broken.errors, ["反馈提交失败（HTTP 500）"]);
  assert.equal(broken.part("feedback-form").hidden, false);
  const offline = createHarness({ failure: new Error("offline") });
  await file(offline, "");
  assert.deepEqual(offline.errors, ["反馈提交失败，请稍后再试"]);

  console.log("OK — all /chat feedback assertions passed");
  console.log("states: " + states.map(([name, copy]) => `${name}=${copy}`).join(" → "));
  console.log("POST " + posted.url + " " + JSON.stringify(posted.body));
  console.log("409 → " + JSON.stringify(expired.errors[0]));
  console.log("500 → " + JSON.stringify(broken.errors[0]));
})().catch((error) => {
  console.error("FAILED: " + error.message);
  process.exit(1);
});
