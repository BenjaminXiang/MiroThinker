"use strict";

/* Drives /seeds' own inline script in a DOM stub: what does a click actually POST?
 *
 * Run from `apps/admin-console`:
 *     node ../../.agents/runs/connect-collection-line/seeds-page-harness/render_check.cjs
 * Environment: SEEDS_HARNESS_REPO (repo root).
 */

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const REPO = process.env.SEEDS_HARNESS_REPO || path.resolve(process.cwd(), "..", "..");
const PAGE = path.join(REPO, "apps/admin-console/backend/static/seeds.html");
const html = fs.readFileSync(PAGE, "utf8");
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

const API = "/api/canonical-v2/admin";
const SEEDS = [
  { id: 3, school: "南方科技大学", department: "计算机科学与工程系", seed_url: "https://www.sustech.edu.cn/szdw.htm", last_run_status: "never_run", last_run_at: null },
  { id: 4, school: "深圳大学", department: null, seed_url: "https://www.szu.edu.cn/teachers.htm", last_run_status: "success", last_run_at: "2026-09-18T02:31:00Z" },
];

const banner = { className: "", textContent: "", scrollIntoView() {} };
const runBody = { innerHTML: "" };
const runHint = { textContent: "" };
const runsCard = { scrollIntoView() {} };
const scopeSelect = { value: "sample:20" };
const plain = (id) => ({ id, innerHTML: "", textContent: "", className: "", value: "", hidden: false, scrollIntoView() {}, addEventListener() {}, querySelectorAll: () => [] });

/* row markup → the buttons the page just wired: same tags, parsed instead of rendered */
function parseButtons(markup) {
  return (markup.match(/<button\b[^>]*data-action="[^"]+"[^>]*>[^<]*<\/button>/g) || []).map((tag) => {
    const listener = {};
    return {
      label: tag.replace(/^[^>]*>/, "").replace(/<\/button>$/, ""),
      title: (tag.match(/title="([^"]*)"/) || [])[1] || "",
      dataset: { action: tag.match(/data-action="([^"]+)"/)[1], id: tag.match(/data-id="(\d+)"/)[1] },
      addEventListener(type, handler) { (listener[type] = listener[type] || []).push(handler); },
      click() { (listener.click || []).forEach((handler) => handler()); },
    };
  });
}

/* rows.innerHTML is the page's only handle on the table: every write re-parses the buttons,
 * so the listeners renderSeeds registers land on the objects the harness clicks. */
let rowButtons = [];
const rows = {
  hidden: false,
  get innerHTML() { return this.markup; },
  set innerHTML(value) { this.markup = value; rowButtons = parseButtons(value); },
  markup: "",
  querySelector: () => null,
  querySelectorAll: (selector) => (selector === "button[data-action]" ? rowButtons : []),
};

const nodes = {
  banner, seedRows: rows, runBody, runHint, runsCard, scopeSelect,
  createCard: plain("createCard"), createBtn: plain("createBtn"), degraded: plain("degraded"),
  pgHint: plain("pgHint"), listHint: plain("listHint"), refresh: plain("refresh"),
};

const calls = [];
let confirmMessage = null;
let confirmAnswer = true;
let triggerStatus = 202;

function jsonResponse(data, status) {
  return { ok: status >= 200 && status < 300, status, json: async () => data };
}

async function fetchStub(url, options = {}) {
  const method = options.method || "GET";
  calls.push({ url, method, body: options.body === undefined ? undefined : JSON.parse(options.body) });
  if (url === `${API}/seeds`) return jsonResponse(SEEDS);
  if (/\/seeds\/\d+\/trigger$/.test(url)) {
    return triggerStatus === 202
      ? jsonResponse({ run_id: "run-abc123", seed_id: 3, status: "running", task_id: "admin-seed-refresh", mode: "preview", skip_reason: null }, 202)
      : jsonResponse({ detail: "console_database_not_configured" }, triggerStatus);
  }
  if (/\/seeds\/\d+\/runs$/.test(url)) {
    return jsonResponse({ seed_id: 3, total: 1, runs: [{ run_id: "run-abc123", task_id: "admin-seed-refresh", status: "running", trigger_source: "manual", operator: "ops", started_at: "2026-09-19T02:00:00Z", summary: { job_summary: { trigger_mode: "preview" } } }] });
  }
  throw new Error("unexpected url " + url);
}

const context = {
  document: { getElementById: (id) => nodes[id] || plain(id) },
  window: { confirm: (message) => { confirmMessage = message; return confirmAnswer; } },
  fetch: fetchStub,
  console,
};
vm.createContext(context);
vm.runInContext(script, context, { filename: "seeds.html#inline" });

const tick = () => new Promise((resolve) => setImmediate(resolve));

async function settle() {
  for (let i = 0; i < 50; i += 1) {
    await tick();
    if (rows.innerHTML.includes("<tr>") && !runBody.innerHTML.startsWith("<p class='footnote'>")) return;
  }
}

function triggerCalls() {
  return calls.filter((call) => call.url.endsWith("/trigger"));
}

function lastBanner() {
  return banner.textContent;
}

async function clickRowButton(action, id) {
  const button = rowButtons.filter((item) => item.dataset.action === action && Number(item.dataset.id) === id)[0];
  assert.ok(button, `no ${action} button for seed ${id}`);
  const before = triggerCalls().length;
  button.click();
  for (let i = 0; i < 40; i += 1) {
    await tick();
    if (triggerCalls().length > before || confirmMessage !== null) break;
  }
  for (let i = 0; i < 40; i += 1) await tick();
}

(async () => {
  await settle();

  // 1. the row carries the two outcome actions, in front of the three untouched ones
  assert.equal(rowButtons.length, SEEDS.length * 5, "five buttons per row");
  assert.deepEqual(
    rowButtons.slice(0, 5).map((button) => button.label),
    ["检查名册", "开始抓取", "修改", "运行记录", "删除"],
    "row order: check, collect, edit, runs, delete"
  );
  assert.equal(rowButtons[0].dataset.action, "check");
  assert.equal(rowButtons[1].dataset.action, "collect");
  assert.equal(rowButtons[0].title, "只访问名册页确认能不能解析，不写入任何数据（约 1 分钟）");
  assert.equal(rowButtons[1].title, "抓取该名册下的教授主页并写入数据（会真实访问学校网站）");
  ["预览抓取", "抽样抓取"].forEach((gone) => assert.equal(rows.innerHTML.includes(gone), false, gone));

  // 2. the scope control above the table holds exactly the four legal options, first one default
  const select = html.match(/<select id="scopeSelect"[^>]*>([\s\S]*?)<\/select>/)[1];
  const options = Array.from(select.matchAll(/<option value="([^"]+)"( selected)?>([^<]+)<\/option>/g))
    .map((match) => ({ value: match[1], selected: Boolean(match[2]), label: match[3] }));
  assert.deepEqual(options, [
    { value: "sample:20", selected: true, label: "前 20 条" },
    { value: "sample:50", selected: false, label: "前 50 条" },
    { value: "sample:100", selected: false, label: "前 100 条" },
    { value: "full", selected: false, label: "全部" },
  ]);

  // 3. 检查名册: no confirm, one preview POST, banner names the action, history reloaded
  await clickRowButton("check", 3);
  assert.equal(confirmMessage, null, "检查名册 asks nothing");
  assert.deepEqual(triggerCalls().map((call) => call.body), [{ mode: "preview" }]);
  assert.equal(triggerCalls()[0].url, `${API}/seeds/3/trigger`);
  assert.equal(triggerCalls()[0].method, "POST");
  assert.equal(lastBanner(), "已开始：南方科技大学 · 检查名册");
  assert.ok(calls.some((call) => call.url === `${API}/seeds/3/runs`), "run history reloaded");
  assert.ok(calls.filter((call) => call.url === `${API}/seeds`).length >= 2, "list reloaded");

  // 4. 开始抓取 under each scope: the confirm states school + scope, the POST states mode + limit
  const scopes = [
    { value: "sample:20", label: "前 20 条", body: { mode: "sample", limit: 20 }, banner: "抓取前 20 条" },
    { value: "sample:50", label: "前 50 条", body: { mode: "sample", limit: 50 }, banner: "抓取前 50 条" },
    { value: "sample:100", label: "前 100 条", body: { mode: "sample", limit: 100 }, banner: "抓取前 100 条" },
    { value: "full", label: "全部", body: { mode: "full" }, banner: "全部抓取" },
  ];
  for (const scope of scopes) {
    scopeSelect.value = scope.value;
    confirmMessage = null;
    const before = triggerCalls().length;
    await clickRowButton("collect", 3);
    const expected = `确认抓取「南方科技大学」的${scope.label}教授主页？会真实访问学校网站。`
      + (scope.body.mode === "full" ? "\n全部抓取可能耗时较长（上千条时可能超过任务上限）。" : "");
    assert.equal(confirmMessage, expected, `${scope.value} confirm`);
    const posted = triggerCalls().slice(before);
    assert.equal(posted.length, 1, `${scope.value} posts once`);
    assert.deepEqual(posted[0].body, scope.body, `${scope.value} body`);
    assert.equal(lastBanner(), `已开始：南方科技大学 · ${scope.banner}`, `${scope.value} banner`);
  }

  // 5. cancelling the confirm writes nothing at all
  scopeSelect.value = "full";
  confirmMessage = null;
  confirmAnswer = false;
  const beforeCancel = triggerCalls().length;
  const bannerBefore = banner.textContent;
  await clickRowButton("collect", 4);
  assert.ok(confirmMessage.startsWith("确认抓取「深圳大学」的"), "the confirm still states the school");
  assert.equal(triggerCalls().length, beforeCancel, "cancel means no POST");
  assert.equal(banner.textContent, bannerBefore, "cancel leaves the banner alone");
  confirmAnswer = true;

  // 6. the row with an unsaved scope still names its own school, and a refusal keeps the reason
  confirmMessage = null;
  await clickRowButton("collect", 4);
  assert.ok(confirmMessage.startsWith("确认抓取「深圳大学」的全部教授主页？"), "second row's own school");
  assert.equal(calls[calls.length - 1].url === `${API}/seeds`, true, "list reloaded after the write");

  triggerStatus = 503;
  await clickRowButton("check", 3);
  assert.equal(lastBanner(), "控制台没有配置数据库（DATABASE_URL）：seed 管理不可用。");
  triggerStatus = 202;

  // 7. the page copy states the scope once, without the old gate sentence
  const toolbar = html.match(/<div class="toolbar">([\s\S]*?)<\/div>/)[1];
  assert.ok(toolbar.includes("「检查名册」只验证能不能解析，不写入数据"), "toolbar copy");
  assert.ok(toolbar.includes("「开始抓取」按上面选的抓取范围真实抓取并写入（同样受系统安全限制）"), "toolbar copy");
  assert.deepEqual(["触发抓取走闸门", "预览 = 只跑发现阶段", "抽样 = 抓取上限 20 条画像"].filter((gone) => toolbar.includes(gone)), []);

  console.log("OK — all /seeds render assertions passed");
  console.log("buttons per row: " + rowButtons.slice(0, 5).map((button) => button.label).join(" | "));
  console.log("scopes: " + options.map((option) => `${option.label} → ${option.value}`).join(" | "));
  console.log("bodies: " + triggerCalls().map((call) => JSON.stringify(call.body)).join(" "));
  console.log("confirm (全部): " + JSON.stringify(`确认抓取「南方科技大学」的全部教授主页？会真实访问学校网站。\n全部抓取可能耗时较长（上千条时可能超过任务上限）。`));
})().catch((error) => {
  console.error("FAILED: " + error.message);
  process.exit(1);
});
