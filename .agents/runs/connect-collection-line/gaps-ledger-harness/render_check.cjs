"use strict";

/* Drives /browse's own inline script in a DOM stub: what does the 知识缺口 tab render?
 *
 * Fixture source: constructed payloads shaped like the ledger contract of
 * `GET /api/canonical-v2/admin/chat-gaps` (the sibling batch's read surface, not deployed
 * on this checkout) — the page and nothing else produces the DOM under test.
 *
 * Run from `apps/admin-console`:
 *     node ../../.agents/runs/connect-collection-line/gaps-ledger-harness/render_check.cjs
 * Environment: GAPS_HARNESS_REPO (repo root).
 *
 * What it locks: the tab asks the ledger endpoint and no longer the build-line operations
 * surface; the summary line carries the ledger's total plus the per-type breakdown; each card
 * carries the Chinese type, the note when present, a local `YYYY-MM-DD HH:mm` stamp and short
 * session/turn markers (never a full uuid); an empty ledger states how rows appear; a failed
 * read still surfaces as the red error box; the header 知识缺口 tile reads the ledger total.
 */

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const REPO = process.env.GAPS_HARNESS_REPO || path.resolve(process.cwd(), "..", "..");
const PAGE = path.join(REPO, "apps/admin-console/backend/static/browse.html");
const html = fs.readFileSync(PAGE, "utf8");
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

const LEDGER = "api/canonical-v2/admin/chat-gaps";
const STATUS = "api/canonical-v2/admin/status";
const EMPTY_TEXT = "还没有用户反馈。用户在对话页点「反馈」后，会记录到这里。";

/* A fixed local wall clock, converted to the wire format the ledger stores: the rendered
   `YYYY-MM-DD HH:mm` then holds in every timezone the harness runs in. */
function wireTime(year, month, day, hour, minute) {
  return new Date(year, month - 1, day, hour, minute).toISOString();
}

const SESSION_A = "4f1c9a2e-6d3b-4a71-9c58-2b0e7d1f8a63";
const SESSION_B = "b7d3e5f1-0a92-4c68-bf31-7e5a9c2d4b80";
const ITEMS = [
  {
    signal_id: "gap-signal:chat-feedback:sha256:9c1f4e7a2b8d5f3019",
    session_id: SESSION_A,
    turn_id: "turn:log:8b7d1234c5e6f7a8",
    release_id: "candidate-v2-20260916-r1",
    feedback_type: "incorrect_answer",
    note: "结果里有不相关企业",
    query_trace_id: "query:trace:5a2b6c8d0e1f2a3b",
    answer_trace_id: "answer:trace:3f9e1d5c7b2a4860",
    observed_at: wireTime(2026, 9, 20, 14, 30),
    recorded_at: wireTime(2026, 9, 20, 14, 30),
  },
  {
    signal_id: "gap-signal:chat-feedback:sha256:1a2b3c4d5e6f7081",
    session_id: SESSION_B,
    turn_id: "turn:log:1d2e3f4a5b6c7d8e",
    release_id: "candidate-v2-20260916-r1",
    feedback_type: "evidence_gap",
    note: "",
    query_trace_id: "query:trace:0d9c8b7a6f5e4d3c",
    answer_trace_id: "answer:trace:7e6d5c4b3a291807",
    observed_at: wireTime(2026, 9, 19, 9, 5),
    recorded_at: wireTime(2026, 9, 19, 9, 5),
  },
  {
    signal_id: "gap-signal:chat-feedback:sha256:deadbeefcafe0001",
    session_id: SESSION_A,
    turn_id: "turn:log:9988776655443322",
    release_id: "candidate-v2-20260916-r1",
    feedback_type: "unreadable_vendor_code",
    note: "这台机器上还没见过的类型",
    query_trace_id: "query:trace:1122334455667788",
    answer_trace_id: "answer:trace:8877665544332211",
    observed_at: wireTime(2026, 9, 18, 23, 59),
    recorded_at: wireTime(2026, 9, 18, 23, 59),
  },
];
const LEDGER_PAYLOAD = {
  items: ITEMS,
  total: 3,
  counts: { incorrect_answer: 2, evidence_gap: 1 },
};
const STATUS_PAYLOAD = {
  as_of: wireTime(2026, 9, 20, 12, 0),
  domains: [],
  gap_summary: { total: 91 },
};

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
    this.id = "";
    this._text = "";
  }

  append(...nodes) {
    for (const node of nodes) {
      const child = typeof node === "string" ? new Node("#text") : node;
      if (typeof node === "string") child._text = node;
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
    this.listeners.set(String(type), handler);
  }

  click() {
    const handler = this.listeners.get("click");
    if (handler) handler({ target: this });
  }

  closest() {
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
    /* `setActiveTab` writes `listSearchInput.parentElement.hidden`: nodes fetched by id
       have no real parent in this stub, so give them one rather than special-casing the
       page. */
    if (!this.parentNode && !this.orphanParent) this.orphanParent = new Node("div");
    return this.parentNode || this.orphanParent;
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

const nodes = new Map();
function node(id) {
  if (!nodes.has(id)) nodes.set(id, new Node("div"));
  return nodes.get(id);
}

const context = {
  document: {
    getElementById: (id) => node(id),
    createElement: (tag) => new Node(tag),
    querySelector: () => null,
  },
  location: { pathname: "/browse", hash: "#gaps" },
  history: { replaceState() {} },
  window: { addEventListener() {} },
  URLSearchParams,
  console,
};
vm.createContext(context);

let ledgerStatus = 200;
let ledgerBody = LEDGER_PAYLOAD;
let pending = null;
const calls = [];

context.fetch = (url) => {
  calls.push(String(url));
  if (String(url) === STATUS) {
    return Promise.resolve({ ok: true, status: 200, json: async () => STATUS_PAYLOAD });
  }
  if (String(url).startsWith(LEDGER)) {
    if (pending) return pending;
    if (ledgerStatus !== 200) {
      return Promise.resolve({ ok: false, status: ledgerStatus, json: async () => ({ detail: "nope" }) });
    }
    return Promise.resolve({ ok: true, status: 200, json: async () => ledgerBody });
  }
  throw new Error("unexpected url " + url);
};

vm.runInContext(script, context, { filename: "browse.html#inline" });

const tick = () => new Promise((resolve) => setImmediate(resolve));
async function settle(rounds = 30) {
  for (let index = 0; index < rounds; index += 1) await tick();
}

function renderedCards() {
  return node("item-list").children.filter((child) => child.tagName === "A" || child.tagName === "ARTICLE");
}

function cardText(card) {
  return card.textContent;
}

function metricValue(label) {
  const card = node("summary-grid").children.find(
    (child) => child.textContent.includes(label),
  );
  assert.ok(card, `no metric card labelled ${label}`);
  const strong = card.children.find((child) => child.tagName === "STRONG");
  assert.ok(strong, `metric card ${label} has no value`);
  return strong.textContent;
}

(async () => {
  await settle();

  // 1. the tab reads the ledger, never the build-line operations surface
  const ledgerCalls = calls.filter((url) => url.startsWith(LEDGER));
  assert.ok(ledgerCalls.length >= 1, "the ledger is read on boot");
  assert.deepEqual(
    [...new Set(ledgerCalls)],
    [LEDGER],
    "every ledger read uses the bare path",
  );
  assert.deepEqual(
    calls.filter((url) => url.includes("operations")),
    [],
    "the operations surface is never called",
  );

  // 2. summary line above the list, in the page's own caption/count slots
  assert.equal(node("list-title").textContent, "知识缺口");
  assert.equal(node("list-caption").textContent, "共 3 条反馈 · 回答不对 2 · 证据不足 1");
  const happySummary = node("list-caption").textContent;
  assert.equal(node("list-count").textContent, "3 条");

  // 3. one card per ledger row: Chinese type, note, local stamp, short markers
  const cards = renderedCards();
  assert.equal(cards.length, 3, "three ledger rows render");
  const first = cardText(cards[0]);
  assert.ok(first.includes("回答不对"), "incorrect_answer reads as 回答不对");
  assert.ok(first.includes("结果里有不相关企业"), "the note is shown");
  assert.ok(first.includes("2026-09-20 14:30"), `local stamp, got: ${first}`);
  assert.ok(first.includes("4f1c9a2e"), "a short session marker is shown");
  assert.ok(first.includes("8b7d1234"), "a short turn marker is shown");
  const allCards = cards.map(cardText).join("\n");
  for (const raw of [
    SESSION_A,
    SESSION_B,
    ...ITEMS.flatMap((item) => [item.turn_id, item.query_trace_id, item.answer_trace_id]),
  ]) {
    assert.equal(allCards.includes(raw), false, `a full id reached the page: ${raw}`);
  }
  assert.equal(cards[0].tagName, "ARTICLE", "cards are not links — there is no detail view");
  assert.ok(cardText(cards[0]).includes("9c1f4e7a"), "the signal id is shown in short form");
  const second = cardText(cards[1]);
  assert.ok(second.includes("证据不足"), "evidence_gap reads as 证据不足");
  assert.ok(second.includes("2026-09-19 09:05"), `second stamp, got: ${second}`);
  const third = cardText(cards[2]);
  assert.ok(third.includes("unreadable_vendor_code"), "an unknown type is shown verbatim");
  assert.ok(third.includes("这台机器上还没见过的类型"), "the third note is shown");
  assert.ok(third.includes("2026-09-18 23:59"), `third stamp, got: ${third}`);

  // 4. the header tile reads the ledger total, not the dead build summary (91)
  assert.equal(metricValue("知识缺口"), "3", "the tile follows the ledger");
  assert.equal(node("summary-grid").textContent.includes("91"), false, "no dead surface count");

  // 5. the inspector says there is no detail view instead of inviting a click
  assert.ok(node("inspector-content").textContent.includes("没有详情"), "inspector copy");

  // 6. an empty ledger states how a row is produced
  ledgerBody = { items: [], total: 0, counts: {} };
  await context.loadGaps();
  assert.equal(node("item-list").children.length, 1, "one neutral state box");
  assert.equal(node("item-list").children[0].className, "empty");
  assert.equal(node("item-list").children[0].textContent, EMPTY_TEXT);
  assert.equal(node("list-caption").textContent, "共 0 条反馈");
  assert.equal(metricValue("知识缺口"), "0", "the tile follows an empty ledger");

  // 7. a hanging read shows the loading state, not a blank pane
  let releasePending = null;
  pending = new Promise((resolve) => { releasePending = resolve; });
  const hanging = context.loadGaps();
  await tick();
  assert.equal(node("item-list").children[0].className, "loading");
  assert.equal(node("item-list").children[0].textContent, "正在加载用户反馈");
  releasePending({ ok: true, status: 200, json: async () => ledgerBody });
  pending = null;
  await hanging;
  await settle(2);

  // 8. a failed read keeps the page's red error box
  ledgerStatus = 500;
  await context.loadGaps();
  assert.equal(node("item-list").children[0].className, "error");
  assert.ok(
    node("item-list").children[0].textContent.startsWith("用户反馈加载失败"),
    node("item-list").children[0].textContent,
  );
  ledgerStatus = 200;

  console.log("OK — all /browse gaps-tab render assertions passed");
  console.log("calls: " + [...new Set(calls)].join(" | "));
  console.log("summary: " + happySummary);
  console.log("card 1: " + JSON.stringify(cardText(cards[0])));
  console.log("empty: " + JSON.stringify(EMPTY_TEXT));
})().catch((error) => {
  console.error("FAILED: " + error.message);
  process.exit(1);
});
