"use strict";

/* Renders /jobs' own inline script against a real API payload in a DOM stub.
 *
 * Run from `apps/admin-console` (after make_payload.py):
 *     node ../../.agents/runs/connect-collection-line/jobs-page-harness/render_check.cjs
 * Environment: JOBS_HARNESS_REPO (repo root), JOBS_HARNESS_OUT (scratch dir).
 */

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const REPO = process.env.JOBS_HARNESS_REPO || path.resolve(process.cwd(), "..", "..");
const OUT = process.env.JOBS_HARNESS_OUT || "/tmp/jobs-harness";
const html = fs.readFileSync(path.join(REPO, "apps/admin-console/backend/static/jobs.html"), "utf8");
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const fixture = JSON.parse(fs.readFileSync(path.join(OUT, "payload.json"), "utf8"));
const payload = fixture.payload;
const runsByTask = fixture.runs;

function makeNode(id) {
  return {
    id,
    innerHTML: "",
    textContent: "",
    className: "",
    value: "",
    dataset: {},
    listeners: {},
    classList: { add() {}, remove() {}, contains: () => false },
    addEventListener(type, handler) {
      (this.listeners[type] = this.listeners[type] || []).push(handler);
    },
    scrollIntoView() {},
    querySelectorAll: () => [],
  };
}

const nodes = {};
const ids = ["banner", "taskGroups", "listHint", "historyTask", "historyStatus", "historyHint",
  "runRows", "detailCard", "detailBody", "detailRunId", "detailClose", "historyRefresh"];
ids.forEach((id) => { nodes[id] = makeNode(id); });
nodes.historyStatus.value = "";
nodes.historyTask.value = "";

const apiCalls = [];
let pickers = [];

function jsonResponse(data, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => data,
    text: async () => JSON.stringify(data),
  };
}

async function fetchStub(url, options = {}) {
  apiCalls.push({ url, method: (options.method || "GET"), body: options.body });
  const base = "/api/canonical-v2/admin/jobs";
  if (url === base) return jsonResponse(payload);
  const runMatch = url.match(/^\/api\/canonical-v2\/admin\/jobs\/([^/]+)\/run$/);
  if (runMatch) return jsonResponse({ task_id: runMatch[1], run_id: "run-abc", status: "running", skip_reason: null });
  const resetMatch = url.match(/^\/api\/canonical-v2\/admin\/jobs\/([^/]+)\/reset$/);
  if (resetMatch) return jsonResponse({ task_id: resetMatch[1], breaker_open: false, consecutive_failures: 0 });
  const listMatch = url.match(/^\/api\/canonical-v2\/admin\/jobs\/([^/?]+)\/runs\?/);
  if (listMatch) {
    const runs = (runsByTask[decodeURIComponent(listMatch[1])] || []).slice();
    runs.sort((a, b) => (a.started_at < b.started_at ? 1 : -1));
    return jsonResponse({ task_id: listMatch[1], runs });
  }
  const detailMatch = url.match(/^\/api\/canonical-v2\/admin\/jobs\/runs\/(.+)$/);
  if (detailMatch) return jsonResponse({ run_id: detailMatch[1], status: "failed", command: ["uv"], stderr_excerpt: "x" });
  throw new Error("unexpected url " + url);
}

class HTMLElement {}

const context = {
  document: {
    getElementById: (id) => nodes[id] || makeNode(id),
    querySelectorAll: () => pickers,
  },
  fetch: fetchStub,
  HTMLElement,
  CSS: { escape: (value) => String(value).replace(/[^A-Za-z0-9_-]/g, (c) => "\\" + c) },
  setInterval: () => 0,
  console,
  URLSearchParams,
};
vm.createContext(context);
vm.runInContext(script, context, { filename: "jobs.html#inline" });

async function settle() {
  for (let i = 0; i < 50; i += 1) {
    await new Promise((resolve) => setImmediate(resolve));
    if (nodes.runRows.innerHTML && nodes.taskGroups.innerHTML) return;
  }
}

function count(haystack, needle) {
  return haystack.split(needle).length - 1;
}

(async () => {
  await settle();
  const tasks = nodes.taskGroups.innerHTML;
  const runs = nodes.runRows.innerHTML;
  const byId = {};
  payload.tasks.forEach((task) => { byId[task.task_id] = task; });

  // 1. groups render in the designed order, each with its purpose line; the ops group is the
  //    collapsed 高级操作 block that carries its own one-line status
  const titles = ["日常采集", "数据导入", "教授采集源"];
  let cursor = -1;
  titles.forEach((title) => {
    const at = tasks.indexOf("<h3>" + title + "</h3>");
    assert.ok(at > cursor, title + " missing or out of order");
    cursor = at;
  });
  assert.equal(count(tasks, "<h3>"), 3, "the three everyday groups keep their heading");
  assert.ok(tasks.indexOf('<details class="group-advanced"><summary>') > cursor, "advanced group last");
  assert.ok(tasks.includes("高级操作：数据更新与检索自检（一般不需要手动执行）"), "collapsed summary");
  assert.ok(tasks.includes('<details class="group-advanced" open') === false, "collapsed by default");
  assert.ok(tasks.includes("最近一次：尚未运行"), "summary carries the group status");
  assert.ok(tasks.includes("按周期把四个数据域的新数据抓回来"), "collection purpose");
  assert.ok(tasks.includes("上传后的表格由这些任务真正写库"), "import purpose");
  assert.ok(tasks.includes("逐条采集源的抓取在「Seed 管理」页操作"), "seed purpose");
  assert.ok(tasks.includes("你导入了新数据或刚跑完采集后，用下面三步让检索能看到新内容"), "ops purpose");
  assert.ok(tasks.includes("建议顺序：① 预演（看影响范围）→ ② 更新检索索引 → ③ 检索自检。"), "ops step guide");
  assert.ok(tasks.includes("<th>运行安排</th>"), "schedule column header");

  // 2. every task shows its Chinese label and its operator hint, never the raw description
  payload.tasks.forEach((task) => {
    assert.ok(tasks.includes(">" + task.label + "<"), task.task_id + " label");
    assert.ok(tasks.includes(task.operator_hint), task.task_id + " operator_hint");
    assert.ok(tasks.includes("任务 ID：" + task.task_id), task.task_id + " id inside 技术细节");
    assert.ok(tasks.includes("超时：" + task.timeout_seconds + " 秒"), task.task_id + " timeout");
    assert.ok(tasks.includes("命令：" + task.command_display), task.task_id + " command");
    if (task.schedule_cron) assert.ok(tasks.includes("cron：" + task.schedule_cron), task.task_id + " cron");
    assert.equal(count(tasks, ">" + task.description + "<"), 0, task.task_id + " description stays hidden");
  });

  // 3. status badges, tags, cadence
  const news = byId["company-news-ingest"];
  const newsRow = tasks.slice(tasks.indexOf(">" + news.label + "<"), tasks.indexOf(">" + byId["company-official-product-capture"].label + "<"));
  assert.ok(newsRow.includes('<span class="pill ok">成功</span>'), "成功 badge");
  assert.ok(/<span class="when">2026-\d\d-\d\d \d\d:\d\d<\/span>/.test(newsRow), "local timestamp");
  assert.ok(newsRow.includes("下周") || newsRow.includes("每周一 02:00"), "schedule_display");
  assert.ok(newsRow.includes("下次 2026-"), "next_run_at local");
  assert.ok(newsRow.includes("会消耗网络检索额度（本轮上限 " + news.quota_limit + "）"), "web-search quota tag");
  assert.ok(newsRow.includes("受采集开关控制"), "switch tag");
  assert.ok(newsRow.includes("仅在允许的时间段运行"), "window tag");
  assert.ok(newsRow.includes('data-run="company-news-ingest"'), "trigger button");
  assert.ok(newsRow.includes("人工触发") === false, "scheduled rows keep their cadence wording");

  const doiRow = tasks.slice(tasks.indexOf(">" + byId["paper-doi-verify"].label + "<"));
  assert.ok(doiRow.includes("失败 · 连续失败 2 次 · 已熔断"), "breaker + consecutive failures badge");
  assert.ok(doiRow.includes('data-reset="paper-doi-verify"'), "复位熔断 button");
  assert.ok(tasks.includes('<span class="pill warn">跳过（窗口外）</span>'), "skip reason badge");

  // 4. ops tasks: 人工触发, the plain-word tags, a disabled trigger with the Chinese reason, and
  //    no requires_postgres tag while the reason next to the button already says it
  const opsRow = tasks.slice(tasks.indexOf('<details class="group-advanced"><summary>'));
  assert.ok(opsRow.includes("人工触发"), "manual cadence reads 人工触发");
  assert.equal(count(tasks, "手动触发"), 0, "the payload wording 手动触发 never reaches the page");
  byId["ops-milvus-backfill"].quota_limit !== undefined &&
    assert.ok(tasks.includes("会消耗大模型调用额度（本轮上限 " + byId["ops-milvus-backfill"].quota_limit + "）"), "llm tag");
  assert.equal(count(tasks, "需构建库"), 0, "no postgres tag on the page");
  assert.equal(count(tasks, "需要构建期数据库"), 0, "the old reason is gone");
  assert.equal(count(tasks, '<button type="button" disabled>立即运行</button>'), 3, "three disabled buttons");
  assert.equal(
    count(tasks, '<button type="button" disabled>立即运行</button> <span class="hint">当前不可用：需要本机数据库</span>'),
    3,
    "reason next to each disabled button"
  );
  assert.ok(tasks.includes('data-run="ops-milvus-backfill"') === false, "no trigger for unavailable task");
  assert.ok(tasks.includes('>企业</option>') && tasks.includes('>论文</option>'), "Chinese domain options");
  assert.ok(tasks.includes('>专利</option>') && tasks.includes('>教授</option>'), "all four domains");
  // mode/limit are declared only by the two seed tasks, which render no trigger: the labels stay
  // declared for a future non-token task, but no picker for them is reachable today.
  assert.ok(html.includes('mode: { preview: "预览", full: "全量" }'), "mode labels declared");
  assert.ok(html.includes('limit: { "5": "5 条", "20": "20 条", "50": "50 条", "100": "100 条" }'),
    "limit labels declared");
  assert.equal(count(tasks, 'data-param="mode"'), 0, "no inert picker for a token task");

  // 4b. a requires_postgres task that *is* available renders no tag at all (the reason explains
  //     the disabled state, nothing else), and the summary line follows the group's newest run
  const validation = byId["ops-retrieval-validation"];
  validation.available = true;
  validation.unavailable_reason = null;
  await context.loadTasks();
  const availablePg = nodes.taskGroups.innerHTML;
  const validationRow = availablePg.slice(availablePg.indexOf(">" + validation.label + "<"));
  assert.equal(validationRow.includes("需要本机数据库"), false, "no reason for an available task");
  assert.equal(validationRow.includes("需构建库"), false, "no postgres tag for an available task");
  assert.ok(validationRow.includes('data-run="ops-retrieval-validation"'), "trigger for an available task");
  validation.available = false;
  validation.unavailable_reason = "postgres_unavailable";

  const backfill = byId["ops-milvus-backfill"];
  backfill.last_run = {
    run_id: "run-ops", task_id: "ops-milvus-backfill", trigger_source: "manual", operator: "ops",
    status: "succeeded", skip_reason: null, started_at: "2026-09-19T03:10:00+00:00",
    finished_at: "2026-09-19T03:11:00+00:00", duration_ms: 60000, exit_code: 0, items_processed: 3,
  };
  await context.loadTasks();
  const withRun = nodes.taskGroups.innerHTML;
  assert.ok(/最近一次：更新检索索引 成功 2026-\d\d-\d\d \d\d:\d\d/.test(withRun),
    "summary names the newest run: " + (withRun.match(/最近一次：[^<]*/) || [""])[0]);
  delete backfill.last_run;
  await context.loadTasks();
  assert.ok(nodes.taskGroups.innerHTML.includes("最近一次：尚未运行"), "summary back to 尚未运行");

  // 5. token tasks: no trigger, link to the page that issues the token
  ["admin-seed-refresh", "admin-seed-refresh-sample", "upload-company-import",
    "upload-patent-import", "upload-professor-import"].forEach((taskId) => {
    assert.ok(tasks.includes('data-run="' + taskId + '"') === false, taskId + " has no trigger");
  });
  assert.equal(count(tasks, '<a class="link" href="/seeds">去 Seed 管理页</a>'), 2, "two seed links");
  assert.equal(count(tasks, '<a class="link" href="/upload">去上传导入页</a>'), 3, "three upload links");
  assert.ok(tasks.includes('data-run="upload-company-import"') === false, "upload has no trigger");

  // 6. history table: Chinese status, local time, human duration, escaped failure reason
  assert.ok(runs.includes('<span class="pill bad">失败</span>'), "history 失败");
  assert.ok(runs.includes('<span class="pill ok">成功</span>'), "history 成功");
  assert.ok(runs.includes("跳过（窗口外）"), "history skip reason");
  assert.ok(runs.includes("企业新闻采集"), "history Chinese task label");
  assert.ok(runs.includes('title="company-news-ingest"'), "history keeps the id in the tooltip");
  assert.ok(runs.includes("exit_code 1"), "exit code inline");
  assert.ok(runs.includes("<img") === false, "no unescaped injection anywhere");
  // The list payload (as_dict without samples) carries no stderr excerpt; the row renders it when
  // present, so feed one in and check the truncate + escape path.
  runsByTask["ops-milvus-backfill"] = [{
    run_id: "run-with-stderr",
    task_id: "ops-milvus-backfill",
    trigger_source: "manual",
    operator: "ops",
    status: "failed",
    skip_reason: null,
    started_at: "2026-09-19T02:03:04+00:00",
    duration_ms: 90500,
    exit_code: 2,
    items_processed: null,
    stderr_excerpt: '<img src=x onerror=alert(1)>\n' + "x".repeat(400),
  }];
  await context.loadHistory();
  const enriched = nodes.runRows.innerHTML;
  assert.ok(enriched.includes("exit_code 2"), "exit code inline");
  assert.ok(enriched.includes("stderr：&lt;img src=x onerror=alert(1)&gt;"), "stderr escaped");
  assert.ok(enriched.includes("…"), "stderr truncated");
  assert.ok(enriched.includes("<img") === false, "no unescaped injection from stderr");
  assert.ok(enriched.includes("1.5 分"), "duration in minutes: " + enriched.match(/\d+(\.\d)? 分/));
  assert.ok(runs.includes("45 秒") || runs.includes("45.1 秒"), "duration in seconds: " + runs.match(/\d+(\.\d+)? 秒/));
  assert.ok(/1[0-9](\.\d)? 分/.test(runs), "duration in minutes");
  assert.ok(/\d{4}-\d\d-\d\dT\d\d:/.test(runs) === false, "no raw ISO in history");
  assert.ok(/<td>\d{4}-\d\d-\d\d \d\d:\d\d<\/td>/.test(runs), "local YYYY-MM-DD HH:mm start time");

  // 7. the trigger still posts the declared params only
  const before = apiCalls.length;
  pickers = [{ dataset: { param: "domain" }, value: "professor" }];
  await context.trigger("ops-milvus-backfill");
  const posted = apiCalls.slice(before).find((call) => call.url.endsWith("/run") && call.method === "POST");
  assert.equal(posted.url, "/api/canonical-v2/admin/jobs/ops-milvus-backfill/run");
  assert.deepEqual(JSON.parse(posted.body), { params: { domain: "professor" } });
  pickers = [];
  const before2 = apiCalls.length;
  await context.trigger("company-news-ingest");
  const posted2 = apiCalls.slice(before2).find((call) => call.url.endsWith("/run") && call.method === "POST");
  assert.deepEqual(JSON.parse(posted2.body), { params: {} });
  const resetCall = apiCalls.find((call) => call.url.endsWith("/reset"));
  assert.ok(nodes.banner.textContent.includes("已触发：企业新闻采集"), "banner names the label: " + nodes.banner.textContent);

  function detailOfHistory() {
    return runs.includes("<tr class=\"run-row");
  }

  console.log("OK — all /jobs render assertions passed");
  console.log("groups:", (tasks.match(/<h3>([^<]+)<\/h3>/g) || []).join(" | "),
    "| <summary>高级操作…</summary>");
  const advancedAt = tasks.indexOf('<details class="group-advanced">');
  console.log("rows per group:", titles.map((title, index) => {
    const start = tasks.indexOf("<h3>" + title + "</h3>");
    const end = index + 1 < titles.length ? tasks.indexOf("<h3>" + titles[index + 1] + "</h3>") : advancedAt;
    return title + "=" + count(tasks.slice(start, end), "<tr>");
  }).concat(
    "高级操作=" + count(tasks.slice(advancedAt), "<tr>")
  ).join(", "));
  console.log("history rows:", count(runs, "class=\"run-row"));
  console.log("ops button sample:", (tasks.match(/<div class="actions">[^]*?<\/div>/) || [""])[0].slice(0, 220));
})().catch((error) => {
  console.error("FAILED:", error.message);
  process.exit(1);
});
