"use strict";

/* Renders /admin's own admin.js in a DOM stub against **real** payloads.
 *
 * Fixture source: `.agents/runs/connect-collection-line/model-roles-harness/fixtures.json`,
 * produced by `dump_fixtures.py` — the live route handlers in-process (FastAPI
 * TestClient, temporary managed settings/secrets stores, ambient credential
 * variables removed, fake keys written through the real store) plus
 * `fetch_model_list()` itself with an injected transport for the success,
 * oversize, 401, and read-timeout cases. Nothing here is hand-copied.
 *
 * Run from `apps/admin-console`:
 *     node ../../.agents/runs/connect-collection-line/model-roles-harness/render_check.cjs
 * Environment: MODEL_HARNESS_REPO (repo root, default ../../ from cwd).
 *
 * What it locks: the five role blocks render from the payloads (not from a page
 * whitelist), the embedding block is read-only, the model picker switches shape at
 * 200 ids, every failure code has Chinese copy that carries the request URL, and a
 * typed key never appears as rendered text.
 */

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const REPO = process.env.MODEL_HARNESS_REPO || path.resolve(process.cwd(), "..", "..");
const HTML = fs.readFileSync(
  path.join(REPO, "apps/admin-console/backend/static/admin.html"),
  "utf8",
);
const SCRIPT = fs.readFileSync(
  path.join(REPO, "apps/admin-console/backend/static/admin.js"),
  "utf8",
);
const FIXTURES = JSON.parse(
  fs.readFileSync(path.join(__dirname, "fixtures.json"), "utf8"),
);

const CONFIG = FIXTURES.config;
const SECRETS = FIXTURES.secrets;
const PRESETS = FIXTURES.presets;
const MODELS_OK = FIXTURES.modelsOk;
const MODELS_MANY = FIXTURES.modelsMany;
const MODELS_UNAUTHORIZED = FIXTURES.modelsUnauthorized;

// -- helpers over the payloads -----------------------------------------------

const fieldByPath = (path_) => CONFIG.fields.find((field) => field.path === path_);
const fieldsOfConnection = (connection) =>
  CONFIG.fields
    .filter((field) => field.connection === connection)
    .sort((left, right) => left.order - right.order);
const connectionByKey = (key) =>
  SECRETS.connections.find((connection) => connection.key === key);
const secretFor = (key) =>
  SECRETS.secrets.find((entry) => entry.connection === key) || {};
const profile = (name) => PRESETS.llm_profiles.find((item) => item.name === name);
const joinUrl = (base, suffix) => {
  const root = String(base || "").replace(/\/+$/, "");
  if (root.endsWith(suffix)) return root;
  if (root.endsWith("/v1") && suffix.indexOf("/v1/") === 0) return root + suffix.slice(3);
  return root + suffix;
};

const PROFILE_FIELD = "serving.chat_llm_profile";
const savedProfileName = fieldByPath(PROFILE_FIELD).value;
const savedProfile = profile(savedProfileName);
const runningProfileName = PRESETS.chat_profile;
const profileLabel = (item) => `${item.label || item.name}（${item.name}）`;

// -- DOM stub ----------------------------------------------------------------

function makeDom() {
  const shellIds = [...HTML.matchAll(/id="([^"]+)"/g)].map((match) => match[1]);
  const duplicateShellIds = shellIds.filter((id, index) => shellIds.indexOf(id) !== index);
  const shellNodes = new Map(); // shell id -> first node in document order
  const liveNodes = new Map(); // script-created id -> newest node

  function makeNode(tag) {
    const node = {
      tagName: String(tag).toUpperCase(),
      id: "",
      className: "",
      textContent: "",
      children: [],
      parent: null,
      attributes: {},
      dataset: {},
      listeners: {},
      value: "",
      type: "",
      placeholder: "",
      disabled: false,
      hidden: false,
      href: "",
      target: "",
      rel: "",
      autocomplete: "",
      append(...items) {
        items.forEach((item) => {
          if (item === null || item === undefined) return;
          if (typeof item === "string") {
            const textNode = makeNode("#text");
            textNode.textContent = item;
            textNode.parent = node;
            node.children.push(textNode);
            return;
          }
          item.parent = node;
          node.children.push(item);
        });
      },
      replaceChildren(...items) {
        node.children = [];
        node.append(...items);
      },
      addEventListener(type, handler) {
        (node.listeners[type] = node.listeners[type] || []).push(handler);
      },
      setAttribute(name, value) {
        node.attributes[name] = String(value);
        if (name === "hidden") node.hidden = true;
      },
      removeAttribute(name) {
        delete node.attributes[name];
      },
      closest(selector) {
        const wanted = selector.replace(/^\./, "");
        let cursor = node;
        while (cursor) {
          if (cursor.className && String(cursor.className).split(/\s+/).indexOf(wanted) >= 0) {
            return cursor;
          }
          cursor = cursor.parent;
        }
        return null;
      },
      focus() {
        node.focused = true;
      },
      click() {
        (node.listeners.click || []).forEach((handler) => handler({ target: node }));
      },
    };
    node.classList = {
      add: (name) => {
        const parts = new Set(String(node.className).split(/\s+/).filter(Boolean));
        parts.add(name);
        node.className = [...parts].join(" ");
      },
      remove: (name) => {
        node.className = String(node.className)
          .split(/\s+/)
          .filter((part) => part && part !== name)
          .join(" ");
      },
      contains: (name) => String(node.className).split(/\s+/).indexOf(name) >= 0,
      toggle: (name, force) => {
        const has = String(node.className).split(/\s+/).indexOf(name) >= 0;
        const next = force === undefined ? !has : Boolean(force);
        if (next) node.classList.add(name);
        else node.classList.remove(name);
        return next;
      },
    };
    return node;
  }

  const all = [];
  shellIds.forEach((id) => {
    const node = makeNode("div");
    if (!shellNodes.has(id)) shellNodes.set(id, node);
    node.id = id;
    all.push(node);
  });

  const saveButtons = ["collection", "serving", "paths"].map((group) => {
    const node = makeNode("button");
    node.dataset.saveCard = group;
    node.id = `save-${group}`;
    liveNodes.set(node.id, node);
    all.push(node);
    return node;
  });

  const document = {
    createElement: (tag) => {
      const node = makeNode(tag);
      Object.defineProperty(node, "id", {
        get: () => node._id || "",
        set: (value) => {
          node._id = value;
          if (value) liveNodes.set(value, node);
        },
        configurable: true,
      });
      all.push(node);
      return node;
    },
    getElementById: (id) => {
      if (shellNodes.has(id)) return shellNodes.get(id);
      return liveNodes.get(id) || null;
    },
    querySelectorAll: (selector) =>
      selector === "[data-save-card]" ? saveButtons : [],
    querySelector: (selector) => {
      const match = /^\[data-([a-z-]+)="([^"]*)"\]$/.exec(selector);
      if (!match) return null;
      const key = match[1].replace(/-([a-z])/g, (unused, letter) => letter.toUpperCase());
      return all.find((node) => node.dataset[key] === match[2]) || null;
    },
  };
  return { document, all, saveButtons, duplicateShellIds };
}

function textOf(node) {
  if (!node) return "";
  if (node.children && node.children.length) {
    return node.children.map(textOf).join(" ") + (node.textContent ? ` ${node.textContent}` : "");
  }
  return String(node.textContent || "");
}

function descendants(node) {
  const out = [];
  (node.children || []).forEach((child) => {
    out.push(child, ...descendants(child));
  });
  return out;
}

function findById(document, id) {
  return document.getElementById(id);
}

function findButton(node, label) {
  return descendants(node).find((child) => child.textContent === label) || null;
}

// -- 全部测试 helpers --------------------------------------------------------

// One ok probe response, shaped like `POST /connections/test` (route overrides for the
// aggregate scenarios need a real body, not a hand-written partial one).
function okTestRoute(latency = 12) {
  return (call) => {
    const body = JSON.parse(call.body);
    return {
      body: {
        connection: body.connection,
        ok: true,
        latency_ms: latency,
        http_status: 200,
        detail: "HTTP 200",
        called: true,
        runtime: { enabled: true },
        used: { api_key_source: "managed-file" },
        rate: { per_minute_limit: 6, min_interval_seconds: 1, remaining: 5 },
      },
    };
  };
}

// The per-role result lines the aggregate run leaves on the card ("label value").
function summaryLines(document) {
  return descendants(findById(document, "allTestsPanel"))
    .filter((node) => node.className === "row")
    .map((node) => textOf(node).replace(/\s+/g, " ").trim());
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// -- page boot ---------------------------------------------------------------

function bootPage(routes) {
  const dom = makeDom();
  const apiCalls = [];

  function jsonResponse(data, status = 200) {
    return {
      ok: status >= 200 && status < 300,
      status,
      json: async () => data,
      text: async () => JSON.stringify(data),
    };
  }

  const context = {
    document: dom.document,
    console,
    JSON,
    Set,
    Map,
    Number,
    String,
    Boolean,
    Object,
    Array,
    Date,
    Math,
    isFinite,
    encodeURIComponent,
    setTimeout,
    clearTimeout,
    AbortController,
    window: { confirm: () => true },
    navigator: { clipboard: { writeText: async () => undefined } },
    fetch: async (url, options = {}) => {
      const call = { url, method: options.method || "GET", body: options.body };
      apiCalls.push(call);
      const route = routes[url];
      if (!route) throw new Error(`unexpected url ${url}`);
      const outcome = typeof route === "function" ? route(call, options) : route;
      if (outcome && outcome.hang) {
        return new Promise((resolve, reject) => {
          if (options.signal) {
            options.signal.addEventListener("abort", () => {
              const error = new Error("aborted");
              error.name = "AbortError";
              reject(error);
            });
          }
        });
      }
      return jsonResponse(outcome.body, outcome.status === undefined ? 200 : outcome.status);
    },
  };
  vm.createContext(context);
  vm.runInContext(SCRIPT, context, { filename: "admin.js" });
  return {
    context,
    document: dom.document,
    apiCalls,
    all: dom.all,
    duplicateShellIds: dom.duplicateShellIds,
  };
}

async function settle(ms = 60) {
  for (let index = 0; index < 40; index += 1) {
    await new Promise((resolve) => setTimeout(resolve, ms / 40));
  }
}

function defaultRoutes(overrides = {}) {
  return {
    "api/canonical-v2/admin/config": { body: CONFIG },
    "api/canonical-v2/admin/secrets": { body: SECRETS },
    "api/canonical-v2/admin/system-status": {
      body: { state: "ok", freshness: {}, storage: {}, disk: {} },
    },
    "api/canonical-v2/admin/connections/presets": { body: PRESETS },
    "api/canonical-v2/admin/connections/llm/models": { body: MODELS_OK },
    "api/canonical-v2/admin/connections/rerank/models": { body: MODELS_MANY },
    ...overrides,
  };
}

// -- assertions --------------------------------------------------------------

async function roleBlocksScenario() {
  const page = bootPage(defaultRoutes());
  await settle();

  // 1. the five roles exist in the shell, in the required order and with the required titles
  const titles = [
    "对话模型（回答与改写用它）",
    "采集模型（摘要与富化用它）",
    "嵌入模型（检索向量用它）",
    "重排模型",
    "Web 搜索",
  ];
  let cursor = -1;
  titles.forEach((title) => {
    const at = HTML.indexOf(`>${title}<`);
    assert.ok(at > cursor, `${title} missing or out of order`);
    cursor = at;
  });
  ["chat", "collection", "embedding", "rerank", "web"].forEach((roleId) => {
    assert.ok(HTML.includes(`data-role="${roleId}"`), `${roleId} role block`);
    assert.ok(
      textOf(findById(page.document, `role-${roleId}-state`)).trim().length > 0,
      `${roleId} state node is filled`,
    );
  });
  assert.deepEqual(
    page.duplicateShellIds,
    [],
    "no duplicate ids in the shell (a duplicate makes one node unreachable and lets a role overwrite another card's rows)",
  );
  assert.ok(
    !textOf(findById(page.document, "collectionState")).includes("端点来源"),
    "card 1's own rows are not overwritten by the collection role's state node",
  );

  // 2. chat role: profile dropdown, its model/base_url beside it, key row, fetch + test
  const chatBody = textOf(findById(page.document, "chatBody"));
  PRESETS.llm_profiles.forEach((item) => {
    assert.ok(chatBody.includes(profileLabel(item)), `chat option ${item.name}`);
  });
  assert.ok(
    chatBody.includes(`模型 ${savedProfile.model} · 端点 ${savedProfile.base_url}`),
    `chat static model+base_url beside the dropdown: ${chatBody}`,
  );
  const llmSecret = secretFor("llm");
  assert.ok(chatBody.includes(llmSecret.mask), "chat key mask rendered");
  assert.ok(
    !descendants(findById(page.document, "chatBody")).some(
      (node) => node.value && node.value.indexOf("sk-fake") === 0 && node.type !== "password",
    ),
    "the fake key is only inside the password input",
  );
  const chatEffective = textOf(findById(page.document, "chatEffective"));
  assert.ok(chatEffective.includes("档位（保存值）"), "saved profile row");
  assert.ok(chatEffective.includes(savedProfileName), "saved profile name");
  assert.ok(
    chatEffective.includes(savedProfile.key_env),
    "the profile's own credential variable is named",
  );
  assert.ok(
    chatEffective.includes(runningProfileName) && chatEffective.includes("本进程仍跑"),
    `running profile is distinguished from the saved one: ${chatEffective}`,
  );
  assert.ok(
    textOf(findById(page.document, "role-chat-url")).includes(
      joinUrl(savedProfile.base_url, "/chat/completions"),
    ),
    `chat request preview: ${textOf(findById(page.document, "role-chat-url"))}`,
  );
  assert.equal(
    findButton(findById(page.document, "chatBody"), "拉取模型列表"),
    null,
    "no model list on the chat role: the profile owns the model id (nothing to pick into)",
  );
  assert.ok(
    textOf(findById(page.document, "servingFields")).indexOf(fieldByPath(PROFILE_FIELD).label) < 0,
    "the profile field is not rendered a second time in card 2",
  );
  // 后续批次: card 2 points at the role block instead of copying the runtime facts.
  const servingCard = HTML.slice(
    HTML.indexOf('id="card-serving"'),
    HTML.indexOf('id="card-paths"'),
  );
  assert.ok(
    !findById(page.document, "rerankRuntime"),
    "card 2 no longer renders the rerank runtime badge: its role block owns it",
  );
  assert.ok(
    servingCard.includes("Rerank 的运行期状态") &&
      servingCard.includes("「模型与连接 › 重排模型」"),
    "card 2 names where the rerank runtime facts live",
  );
  assert.ok(
    textOf(findById(page.document, "role-rerank-state")).includes("运行期"),
    "the rerank role still renders the runtime state (delegated, not dropped)",
  );

  // 3. collection role: catalogue fields + preset + key pointer + fetch, no second key input
  const collectionBody = findById(page.document, "collectionBody");
  const collectionText = textOf(collectionBody);
  fieldsOfConnection("llm").forEach((field) => {
    assert.ok(collectionText.includes(field.label), `collection field ${field.path}`);
  });
  PRESETS.presets.forEach((preset) => {
    assert.ok(collectionText.includes(preset.label), `preset ${preset.id}`);
  });
  assert.ok(collectionText.includes("凭据与「对话模型」档位共用一份"), "key pointer, not a second entry");
  assert.equal(
    descendants(collectionBody).filter(
      (node) => node.tagName === "INPUT" && node.type === "password",
    ).length,
    0,
    "collection role has no key input",
  );
  assert.ok(
    textOf(findById(page.document, "role-collection-url")).includes(
      joinUrl(fieldByPath("extraction_endpoints.llm_base_url").value, "/chat/completions"),
    ),
    `collection request preview: ${textOf(findById(page.document, "role-collection-url"))}`,
  );
  assert.ok(
    findButton(collectionBody, "拉取模型列表"),
    "collection role offers 拉取模型列表",
  );

  // 4. embedding role: frozen value read-only, consequence spelled out, override collapsed
  const embeddingEffective = textOf(findById(page.document, "embeddingEffective"));
  assert.ok(embeddingEffective.includes(PRESETS.embedding_frozen.base_url), "frozen base_url");
  assert.ok(embeddingEffective.includes(PRESETS.embedding_frozen.model), "frozen model");
  assert.ok(embeddingEffective.includes("发布包冻结"), "frozen origin");
  assert.ok(
    HTML.includes("服务线索引由发布包冻结：改它需要重建全部向量"),
    "warning line in the shell",
  );
  const embeddingBody = findById(page.document, "embeddingBody");
  const details = descendants(embeddingBody).find((node) => node.tagName === "DETAILS");
  assert.ok(details, "collapsed advanced block");
  const detailsText = textOf(details);
  assert.ok(detailsText.includes("高级：采集侧覆盖"), "advanced summary");
  assert.ok(detailsText.includes("只影响后续采集/构建，不改服务线索引"), "advanced note");
  fieldsOfConnection("embedding").forEach((field) => {
    assert.ok(detailsText.includes(field.label), `override field ${field.path}`);
  });
  assert.ok(
    descendants(details)
      .filter((node) => node.tagName === "INPUT")
      .every((node) => node.disabled === true),
    "embedding override inputs are disabled by the catalogue",
  );
  assert.ok(
    findButton(findById(page.document, "embeddingActions"), "测试连通性"),
    "embedding keeps a connectivity probe for the frozen endpoint",
  );
  assert.equal(
    findButton(embeddingBody, "拉取模型列表"),
    null,
    "no model list for a frozen endpoint (nothing to pick)",
  );
  assert.equal(
    descendants(embeddingBody).filter((node) => node.tagName === "SELECT").length,
    0,
    "no preset dropdown for a frozen endpoint",
  );
  assert.ok(
    textOf(findById(page.document, "role-embedding-url")).includes(
      joinUrl(PRESETS.embedding_frozen.base_url, "/v1/embeddings"),
    ),
    `embedding request preview: ${textOf(findById(page.document, "role-embedding-url"))}`,
  );

  // 5. rerank role: fields + preset + key + fetch + preview
  const rerankText = textOf(findById(page.document, "rerankBody"));
  fieldsOfConnection("rerank").forEach((field) => {
    assert.ok(rerankText.includes(field.label), `rerank field ${field.path}`);
  });
  assert.ok(
    descendants(findById(page.document, "rerankBody")).some(
      (node) => node.tagName === "INPUT" && node.type === "password",
    ),
    "rerank key row",
  );
  assert.ok(
    textOf(findById(page.document, "rerankEffective")).includes(
      connectionByKey("rerank").runtime.enabled ? "已启用" : "未启用",
    ),
    "rerank runtime state",
  );
  assert.ok(
    textOf(findById(page.document, "role-rerank-url")).includes(
      joinUrl(fieldByPath("extraction_endpoints.rerank_base_url").value, "/v1/rerank"),
    ),
    `rerank request preview: ${textOf(findById(page.document, "role-rerank-url"))}`,
  );

  // 6. web role: one block per provider, pinned endpoints, no editable base URL
  const webText = textOf(findById(page.document, "webBody"));
  SECRETS.connections
    .filter((connection) => connection.kind === "web_search")
    .forEach((connection) => {
      assert.ok(webText.includes(connection.label), `${connection.key} block`);
      assert.ok(
        textOf(findById(page.document, `role-web-${connection.key}-url`)).includes(
          connection.runtime.base_url,
        ),
        `${connection.key} preview`,
      );
      assert.ok(
        descendants(findById(page.document, `role-web-${connection.key}-url`)).length > 0,
        `${connection.key} preview node`,
      );
    });
  assert.ok(webText.includes("端点由 provider 固定"), "pinned endpoint copy");
  const bochaSecret = secretFor("bocha");
  assert.ok(webText.includes(bochaSecret.mask), "bocha mask rendered");

  console.log("OK — role blocks render from the real payloads");
}

async function modelPickerScenario() {
  // success, ≤ 200 ids → <select>; picking writes the model field and marks it dirty
  const page = bootPage(defaultRoutes());
  await settle();
  findById(page.document, "role-collection-fetch").click();
  await settle();
  const picker = findById(page.document, "role-collection-models-picker");
  const pickerText = textOf(picker);
  const modelField = fieldsOfConnection("llm").find((field) => field.test_arg === "model");
  assert.ok(pickerText.includes(`共 ${MODELS_OK.count} 个`), `picker count: ${pickerText}`);
  const select = descendants(picker).find((node) => node.tagName === "SELECT");
  assert.ok(select, "select picker for ≤ 200 ids");
  MODELS_OK.models.forEach((model) => {
    assert.ok(select.children.some((option) => option.value === model.id), `option ${model.id}`);
  });
  assert.ok(
    descendants(picker).some((node) => node.textContent.includes("手填模型 ID")),
    "manual entry stays a first-class option",
  );
  const okResult = textOf(findById(page.document, "role-collection-models-result"));
  assert.ok(okResult.includes(`拉取到 ${MODELS_OK.count} 个模型`), `fetch copy: ${okResult}`);
  assert.ok(okResult.includes(`${MODELS_OK.elapsed_ms} ms`), "elapsed shown");
  assert.ok(okResult.includes(MODELS_OK.request_url), "server request_url shown");
  // Page-vs-server parity on the URL join rule: the fixture's request_url was
  // produced by the live `_join`, so the page's own preview must agree with it.
  assert.equal(
    joinUrl(fieldByPath("extraction_endpoints.llm_base_url").value, "/v1/models"),
    MODELS_OK.request_url,
    `the page's preview must equal the URL the server called (${MODELS_OK.request_url})`,
  );
  assert.ok(
    textOf(findById(page.document, "role-collection-models-url")).includes(MODELS_OK.request_url),
    "the pre-flight preview names the same URL",
  );
  const currentModel = fieldByPath(modelField.path).value;
  const target = MODELS_OK.models.map((model) => model.id).find((id) => id !== currentModel);
  assert.ok(target, "the dumped model list contains an id other than the current value");
  select.value = target;
  (select.listeners.change || []).forEach((handler) => handler());
  if (process.env.MODEL_HARNESS_DEBUG) {
    console.log(
      "DEBUG:",
      vm.runInContext(
        `(() => {
          const live = document.getElementById('f-extraction_endpoints.llm_model');
          const widget = state.widgets.get('extraction_endpoints.llm_model');
          live.__probe = 'live';
          return JSON.stringify({
            banner: document.getElementById('bannerText').textContent,
            dirty: [...state.dirty.keys()],
            liveValue: live ? live.value : null,
            widgetValue: widget ? widget.node.value : null,
            widgetIsLive: widget ? widget.node.__probe === 'live' : null,
            initial: widget ? initialValueOf(widget.field) : null,
            patch: widget ? patchValueOf('extraction_endpoints.llm_model') : null,
          });
        })()`,
        page.context,
      ),
    );
  }
  assert.equal(
    findById(page.document, `f-${modelField.path}`).value,
    target,
    "picking fills the model field",
  );
  assert.ok(
    textOf(findById(page.document, "bannerText")).includes("1 项未保存"),
    "picking marks the field dirty",
  );
  const fetchCall = page.apiCalls.find((call) => call.url.endsWith("/models"));
  assert.deepEqual(
    JSON.parse(fetchCall.body),
    {
      connection: "llm",
      base_url: fieldByPath("extraction_endpoints.llm_base_url").value,
    },
    "the fetch posts the unsaved base_url and no invented key",
  );

  // oversize → filter input over a <datalist>, and the server's truncation is surfaced
  const many = bootPage(defaultRoutes());
  await settle();
  findById(many.document, "role-rerank-fetch").click();
  await settle();
  const manyPicker = findById(many.document, "role-rerank-models-picker");
  const manyText = textOf(manyPicker);
  assert.ok(manyText.includes(`共 ${MODELS_MANY.count} 个`), `oversize note: ${manyText}`);
  const filter = descendants(manyPicker).find((node) => node.tagName === "INPUT");
  const datalist = descendants(manyPicker).find((node) => node.tagName === "DATALIST");
  assert.ok(filter && datalist, "filter input + datalist past 200 ids");
  assert.equal(filter.attributes.list, datalist.id, "filter references the datalist");
  assert.equal(datalist.children.length, MODELS_MANY.count, "datalist carries every id");
  assert.equal(
    descendants(manyPicker).filter((node) => node.tagName === "SELECT").length,
    0,
    "no select past 200 ids",
  );
  if (MODELS_MANY.truncated) {
    assert.ok(
      textOf(findById(many.document, "role-rerank-models-result")).includes("服务端只返回了前面一部分"),
      "truncated flag surfaced",
    );
  }
  const rerankModel = fieldsOfConnection("rerank").find((field) => field.test_arg === "model");
  const sampleId = MODELS_MANY.models[9].id;
  filter.value = sampleId;
  (filter.listeners.change || []).forEach((handler) => handler());
  assert.equal(
    findById(many.document, `f-${rerankModel.path}`).value,
    sampleId,
    "filter selection fills the model field",
  );

  // failure → mapped Chinese copy + request url + elapsed + the redacted excerpt
  const failing = bootPage(
    defaultRoutes({
      "api/canonical-v2/admin/connections/rerank/models": {
        body: MODELS_UNAUTHORIZED,
        status: 200,
      },
    }),
  );
  await settle();
  findById(failing.document, "role-rerank-fetch").click();
  await settle();
  const failureText = textOf(findById(failing.document, "role-rerank-models-result"));
  assert.ok(failureText.includes("密钥被拒绝（401/403）"), `mapped message: ${failureText}`);
  assert.ok(failureText.includes(MODELS_UNAUTHORIZED.request_url), "request url shown");
  assert.ok(failureText.includes("401"), "status shown");
  assert.ok(failureText.includes("[redacted]"), "the credential-free excerpt is what the page shows");
  assert.ok(failureText.indexOf("sk-fake") < 0, "no key material in the failure copy");
  assert.equal(
    findById(failing.document, "role-rerank-models-picker").hidden,
    true,
    "no picker after a failure",
  );

  // client guard: a hanging endpoint is reported as the 3 s timeout with the URL
  const hanging = bootPage(
    defaultRoutes({ "api/canonical-v2/admin/connections/rerank/models": { hang: true } }),
  );
  await settle();
  findById(hanging.document, "role-rerank-fetch").click();
  await new Promise((resolve) => setTimeout(resolve, 3300));
  const timeoutText = textOf(findById(hanging.document, "role-rerank-models-result"));
  assert.ok(timeoutText.includes("3 秒内没有响应"), `timeout copy: ${timeoutText}`);
  assert.ok(timeoutText.includes(MODELS_MANY.request_url), "timeout keeps the url");
  assert.equal(
    findById(hanging.document, "role-rerank-fetch").disabled,
    false,
    "the button is usable again after the guard fires",
  );

  console.log("OK — model picker: select ≤200, filter+datalist >200, failure and timeout copy");
}

async function saveAndTestScenario() {
  const calls = [];
  const savedModel = { ...fieldsOfConnection("llm").find((field) => field.test_arg === "model") };
  const NEW_MODEL = "qwen3.6-plus";
  assert.notEqual(NEW_MODEL, savedModel.value, "the scenario needs a value different from the fixture");
  const page = bootPage(
    defaultRoutes({
      "api/canonical-v2/admin/config": (call) => {
        calls.push(call);
        if (call.method === "PATCH") {
          const updated = JSON.parse(JSON.stringify(CONFIG));
          updated.fields = updated.fields.map((field) =>
            field.path === savedModel.path ? { ...field, value: NEW_MODEL } : field,
          );
          updated.changed = [savedModel.path];
          return { body: updated };
        }
        return { body: CONFIG };
      },
      "api/canonical-v2/admin/secrets": (call) => {
        calls.push(call);
        if (call.method === "PATCH") {
          return {
            body: { ...SECRETS, changed: ["llm.api_key"], audit_written: true },
          };
        }
        return { body: SECRETS };
      },
      "api/canonical-v2/admin/connections/test": (call) => {
        calls.push(call);
        return {
          body: {
            connection: "llm",
            ok: true,
            latency_ms: 88,
            http_status: 200,
            detail: "HTTP 200",
            called: true,
            runtime: { enabled: true },
            used: { api_key_source: "request", effective_api_key_source: "managed-file" },
            rate: { remaining: 5 },
          },
        };
      },
    }),
  );
  await settle();

  // typing a key into the chat role keeps it write-only
  const chatKey = findById(page.document, "role-chat-key");
  chatKey.value = "sk-live-plaintext-0000";
  (chatKey.listeners.input || []).forEach((handler) => handler());
  assert.ok(
    textOf(findById(page.document, "bannerText")).includes("1 项未保存"),
    "a typed key shows up in the banner",
  );
  assert.ok(
    !textOf(findById(page.document, "roleBlocks")).includes("sk-live-plaintext-0000"),
    "the typed key is never rendered as text",
  );

  // 保存本卡 on the collection role: that role has no key box, so it writes only its field
  const modelInput = findById(page.document, `f-${savedModel.path}`);
  modelInput.value = "qwen3.6-plus";
  (modelInput.listeners.input || []).forEach((handler) => handler());
  findById(page.document, "role-collection-save").click();
  await settle();
  const patch = calls.find((call) => call.method === "PATCH" && call.url.endsWith("/config"));
  assert.ok(patch, "config PATCH issued");
  const body = JSON.parse(patch.body);
  assert.deepEqual(
    body,
    { extraction_endpoints: { llm_model: "qwen3.6-plus" } },
    `the collection save posts its own field only: ${patch.body}`,
  );
  assert.equal(
    calls.filter((call) => call.method === "PATCH" && call.url.endsWith("/secrets")).length,
    0,
    "saving the collection role does not write the chat key",
  );
  const saveCopy = textOf(findById(page.document, "role-collection-save-result"));
  assert.ok(saveCopy.includes("已保存"), `save copy: ${saveCopy}`);
  assert.ok(saveCopy.includes("保存 ≠ 测试"), "save copy states save ≠ test");
  assert.ok(saveCopy.includes("systemctl --user restart canonical-v2-backend"), "restart command");

  // 测试 uses the unsaved values and never writes
  findById(page.document, "role-collection-test").click();
  await settle();
  const testCall = calls.find((call) => call.url.endsWith("/connections/test"));
  assert.deepEqual(JSON.parse(testCall.body), {
    connection: "llm",
    base_url: fieldByPath("extraction_endpoints.llm_base_url").value,
    model: "qwen3.6-plus",
  });
  assert.ok(
    textOf(findById(page.document, "role-collection-test-result")).includes("测试不改配置"),
    "test copy says it does not write",
  );
  assert.equal(
    calls.filter((call) => call.method === "PATCH").length,
    1,
    "testing writes nothing",
  );

  // the chat role's test uses the selected profile's endpoint + the typed key
  findById(page.document, "role-chat-test").click();
  await settle();
  const chatCall = calls.filter((call) => call.url.endsWith("/connections/test")).pop();
  assert.deepEqual(JSON.parse(chatCall.body), {
    connection: "llm",
    api_key: "sk-live-plaintext-0000",
    base_url: savedProfile.base_url,
    model: savedProfile.model,
  });

  // 保存本卡 on the chat role writes the profile through the existing config PATCH
  const switchTo = PRESETS.llm_profiles.find((item) => item.name !== savedProfileName);
  const profileSelect = findById(page.document, "chat-profile");
  profileSelect.value = switchTo.name;
  (profileSelect.listeners.change || []).forEach((handler) => handler());
  findById(page.document, "role-chat-save").click();
  await settle();
  const chatPatch = calls
    .filter((call) => call.method === "PATCH" && call.url.endsWith("/config"))
    .pop();
  assert.deepEqual(JSON.parse(chatPatch.body), {
    serving: { chat_llm_profile: switchTo.name },
  });
  assert.equal(
    JSON.parse(
      calls.filter((call) => call.method === "PATCH" && call.url.endsWith("/secrets")).pop().body,
    ).values["llm.api_key"],
    "sk-live-plaintext-0000",
    "the chat role writes the key it was given",
  );

  console.log("OK — save ≠ test, per-role writes, keys stay write-only");
}

async function allRolesProbeScenario() {
  const bodies = [];
  const startedAt = [];
  const page = bootPage(
    defaultRoutes({
      "api/canonical-v2/admin/connections/test": (call) => {
        const body = JSON.parse(call.body);
        bodies.push(body);
        startedAt.push(Date.now());
        const index = bodies.length;
        if (index === 4) {
          // 重排模型: endpoint reachable, credential rejected — a real failure line
          return {
            body: {
              connection: "rerank",
              ok: false,
              latency_ms: 12,
              http_status: 401,
              detail: "HTTP 401：端点可达，凭据被拒绝",
              called: true,
              runtime: { enabled: true },
              used: { api_key_source: "none" },
              rate: { per_minute_limit: 6, min_interval_seconds: 1, remaining: 2 },
            },
          };
        }
        if (index === 6) {
          // the shared 6/min budget is already spent (e.g. a model-list fetch)
          return {
            body: {
              detail: {
                error: "rate_limited",
                connection: "serper",
                retry_after_seconds: 43,
              },
            },
            status: 429,
          };
        }
        return okTestRoute(12 + index)(call);
      },
    }),
  );
  await settle();

  const button = findById(page.document, "test-all-roles");
  const status = findById(page.document, "allTestsStatus");
  assert.ok(button, "the aggregate control is script-built into the card header");
  assert.ok(
    HTML.includes('id="allTestsPanel" hidden'),
    "the summary panel ships hidden and is revealed by the run",
  );
  assert.equal(textOf(status), "", "no status before the run");

  button.click();
  await wait(200);
  assert.equal(button.disabled, true, "disabled while running");
  assert.ok(textOf(status).startsWith("测试中"), `progress while running: ${textOf(status)}`);

  await wait(7000);
  assert.equal(button.disabled, false, "usable again after the run (never left disabled)");
  assert.equal(
    textOf(status),
    "测试完成：可用 4 · 不可用 1 · 未测 1",
    `run summary: ${textOf(status)}`,
  );
  assert.deepEqual(
    summaryLines(page.document),
    [
      "对话模型 可用（13 ms）",
      "采集模型 可用（14 ms）",
      "嵌入模型 可用（15 ms）",
      "重排模型 不可用：HTTP 401：端点可达，凭据被拒绝（请求 http://127.0.0.1:9000/v1/rerank）",
      "Web 搜索（Bocha） 可用（17 ms）",
      "Web 搜索（Serper） 未测：限频：请 43 秒后再试（服务端已拦截，未发起调用）",
    ],
    `one compact line per role: ${summaryLines(page.document).join(" | ")}`,
  );
  assert.deepEqual(
    bodies,
    [
      { connection: "llm", base_url: savedProfile.base_url, model: savedProfile.model },
      {
        connection: "llm",
        base_url: fieldByPath("extraction_endpoints.llm_base_url").value,
        model: fieldByPath("extraction_endpoints.llm_model").value,
      },
      { connection: "embedding" },
      {
        connection: "rerank",
        base_url: fieldByPath("extraction_endpoints.rerank_base_url").value,
        model: fieldByPath("extraction_endpoints.rerank_model").value,
      },
      { connection: "bocha" },
      { connection: "serper" },
    ],
    "each role posts its own body (the same one its single-role button builds)",
  );
  assert.equal(bodies.length, 6, "six probes: llm twice, then embedding, rerank, bocha, serper");
  for (let index = 1; index < startedAt.length; index += 1) {
    assert.ok(
      startedAt[index] - startedAt[index - 1] >= 1000,
      `probe ${index + 1} must start ≥1 s after probe ${index} (server min_interval_seconds=1), ` +
        `measured ${startedAt[index] - startedAt[index - 1]} ms`,
    );
  }

  console.log("OK — 全部测试: six sequential probes, per-role lines, 429 and skip copy");
}

async function degradedPresetScenario() {
  // the presets endpoint is not live: the role blocks still render
  const emptyRerank = JSON.parse(JSON.stringify(CONFIG));
  emptyRerank.fields = emptyRerank.fields.map((item) =>
    item.path === "extraction_endpoints.rerank_base_url"
      ? { ...item, value: null, source: "default" }
      : item,
  );
  const page = bootPage(
    defaultRoutes({
      "api/canonical-v2/admin/connections/presets": { body: { detail: "Not Found" }, status: 404 },
      "api/canonical-v2/admin/config": { body: emptyRerank },
    }),
  );
  await settle();
  const chatText = textOf(findById(page.document, "chatBody"));
  assert.ok(chatText.includes("档位表不可用"), `chat degrades: ${chatText}`);
  const collectionText = textOf(findById(page.document, "collectionBody"));
  assert.ok(collectionText.includes("预设不可用"), `collection degrades: ${collectionText}`);
  assert.ok(collectionText.includes("仍可直接手填 Base URL"), "manual entry stays available");
  const embeddingEffective = textOf(findById(page.document, "embeddingEffective"));
  assert.ok(
    embeddingEffective.includes(connectionByKey("embedding").runtime.base_url),
    "embedding falls back to the runtime-resolved frozen endpoint",
  );
  assert.ok(embeddingEffective.includes("运行期解析"), "fallback origin is named");

  // An empty *field* is not "no endpoint": the card falls back to the runtime-resolved
  // endpoint it already displays (round 9), so the fetch goes out against that one.
  const runtimeRerank = connectionByKey("rerank").runtime.base_url;
  const callsBefore = page.apiCalls.length;
  findById(page.document, "role-rerank-fetch").click();
  await settle();
  const rerankCall = page.apiCalls
    .slice(callsBefore)
    .find((call) => call.url.endsWith("/rerank/models"));
  assert.ok(rerankCall, "an empty field still uses the runtime endpoint instead of refusing");
  assert.deepEqual(
    JSON.parse(rerankCall.body),
    { connection: "rerank", base_url: runtimeRerank },
    "the fetch posts the runtime-resolved endpoint the card displays",
  );

  // Neither a field nor a runtime endpoint ⇒ the page refuses locally, and the
  // aggregate run reports that role as skipped (not as a failure).
  const noRuntimeEndpoint = JSON.parse(JSON.stringify(SECRETS));
  noRuntimeEndpoint.connections = noRuntimeEndpoint.connections.map((connection) =>
    connection.key === "rerank"
      ? { ...connection, runtime: { ...connection.runtime, enabled: false, base_url: null } }
      : connection,
  );
  const bare = bootPage(
    defaultRoutes({
      "api/canonical-v2/admin/config": { body: emptyRerank },
      "api/canonical-v2/admin/secrets": { body: noRuntimeEndpoint },
      "api/canonical-v2/admin/connections/test": okTestRoute(),
    }),
  );
  await settle();
  const bareBefore = bare.apiCalls.length;
  findById(bare.document, "role-rerank-fetch").click();
  await settle(30);
  assert.equal(
    bare.apiCalls.length,
    bareBefore,
    "with no usable endpoint the page reports locally instead of calling",
  );
  assert.ok(
    textOf(findById(bare.document, "role-rerank-models-result")).includes("还没有可用端点"),
    "the local refusal names the missing endpoint",
  );

  findById(bare.document, "test-all-roles").click();
  await new Promise((resolve) => setTimeout(resolve, 7000));
  const bareLines = summaryLines(bare.document);
  assert.deepEqual(
    bareLines,
    [
      "对话模型 可用（12 ms）",
      "采集模型 可用（12 ms）",
      "嵌入模型 可用（12 ms）",
      "重排模型 未配置端点，已跳过",
      "Web 搜索（Bocha） 可用（12 ms）",
      "Web 搜索（Serper） 可用（12 ms）",
    ],
    `a role without an endpoint is skipped, not failed: ${bareLines.join(" | ")}`,
  );
  assert.ok(
    textOf(bare.document.getElementById("allTestsStatus")).includes("跳过 1"),
    "the run summary counts the skipped role separately",
  );
  assert.equal(
    bare.apiCalls.filter(
      (call) => call.url.endsWith("/connections/test") && JSON.parse(call.body).connection === "rerank",
    ).length,
    0,
    "the skipped role is never probed",
  );

  console.log("OK — a missing presets endpoint degrades without breaking the page");
}

(async () => {
  if (process.argv.includes("--dump-fixtures")) {
    console.log("fixtures.json is produced by dump_fixtures.py (real payloads); nothing to dump here");
    return;
  }
  await roleBlocksScenario();
  await modelPickerScenario();
  await saveAndTestScenario();
  await allRolesProbeScenario();
  await degradedPresetScenario();
  console.log("OK — all /admin 模型与连接 render assertions passed");
})().catch((error) => {
  console.error("FAILED:", error && error.message ? error.message : error);
  console.error(error && error.stack ? error.stack : "");
  process.exit(1);
});
