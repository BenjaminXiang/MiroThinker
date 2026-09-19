/* 管理配置中心（Canonical V2）：配置 · 展示 · 验证同卡。
 *
 * 渲染完全是服务端 payload 的函数：
 *   - /config 的 fields（含 label/kind/group/order/bounds/consumer/default/connection/test_arg）
 *     决定卡片 1-3 的字段与「模型与连接」各角色里的端点/模型字段；
 *   - /secrets 的 connections 与 secrets 决定各角色的运行期状态、密钥来源与掩码；
 *   - /api/…/connections/presets 决定各角色的提供方预设、档位表与冻结的嵌入端点；
 *   - /system-status 提供各域新鲜度、库计数/体积与磁盘余量。
 * 页面不持有任何字段白名单：目录加一行，字段即出现。
 *
 * 保存只提交脏字段（默认 = 显式 null，清除 override）；密钥明文只写不读，
 * 既不回显也不写日志。「保存 ≠ 测试」：保存写受管文件，测试当场发起一次最小调用；
 * 两者都要重启服务才在运行期生效。
 */
"use strict";

const API = {
  status: "api/canonical-v2/admin/system-status",
  config: "api/canonical-v2/admin/config",
  secrets: "api/canonical-v2/admin/secrets",
  connectionTest: "api/canonical-v2/admin/connections/test",
  presets: "api/canonical-v2/admin/connections/presets",
  connectionModels: (key) =>
    `api/canonical-v2/admin/connections/${encodeURIComponent(key)}/models`,
};

const RESTART_COMMAND = "systemctl --user restart canonical-v2-backend";
const CONNECTION_GROUP = "endpoints";
const CARD_GROUPS = { collection: "collectionFields", serving: "servingFields", paths: "pathsFields" };
const FRESHNESS_DOMAINS = ["company", "paper", "patent", "professor"];
const DOMAIN_LABEL = { company: "企业", paper: "论文", patent: "专利", professor: "教授" };
// 保留期预览跟随当前（含未保存）的保留天数：唯一一处按路径取值的引用。
const RETENTION_FIELD = "paths.access_log_retention_days";

const state = {
  config: null,
  secrets: null,
  status: null,
  presets: null, // 角色预设 / 档位表 / 冻结的嵌入端点
  presetsError: null, // 预设接口不可用时的一句话（角色块照常渲染，只是没有预设）
  modelLists: new Map(), // roleId -> { ids, request_url, elapsed_ms, count, truncated }
  widgets: new Map(), // path -> { field, node }
  dirty: new Map(), // path -> 待提交值（null = 回到默认）
  keys: new Map(), // connection -> 未保存的密钥明文（只写不读，不入日志）
  needsRestart: false,
};

function el(id) {
  return document.getElementById(id);
}

function text(tag, className, value) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  node.textContent = value;
  return node;
}

function notice(node, message, kind) {
  if (!node) return;
  node.textContent = message;
  node.className = `notice ${kind || ""}`.trim();
}

function hideNotice(node) {
  if (!node) return;
  node.className = "notice hidden";
  node.textContent = "";
}

function pill(label, kind) {
  return text("span", `pill ${kind || ""}`.trim(), label);
}

function humanBytes(value) {
  if (typeof value !== "number" || !isFinite(value)) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let index = 0;
  let size = value;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  return `${size.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function humanAge(seconds) {
  if (typeof seconds !== "number" || !isFinite(seconds)) return "—";
  if (seconds < 60) return `${seconds} 秒`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分钟`;
  if (seconds < 86400) return `${(seconds / 3600).toFixed(1)} 小时`;
  return `${(seconds / 86400).toFixed(1)} 天`;
}

function shortTime(value) {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return parsed.toLocaleString("zh-CN", { hour12: false });
}

function describeDetail(detail) {
  if (detail === null || detail === undefined) return "未提供原因";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => (item && item.msg ? `${(item.loc || []).join(".")}: ${item.msg}` : JSON.stringify(item)))
      .join("；");
  }
  return JSON.stringify(detail);
}

function row(key, valueNode) {
  const wrapper = text("div", "row", "");
  wrapper.append(text("div", "key", key));
  const cell = document.createElement("div");
  cell.className = "value";
  if (typeof valueNode === "string") cell.textContent = valueNode;
  else cell.append(valueNode);
  wrapper.append(cell);
  return wrapper;
}

function optionNode(value, label) {
  const option = document.createElement("option");
  option.value = value;
  option.textContent = label;
  return option;
}

function truncate(text_, limit) {
  const value = String(text_ === null || text_ === undefined ? "" : text_);
  return value.length <= limit ? value : `${value.slice(0, limit)}…`;
}

// -- 字段渲染（唯一来源：/config 的 fields） ---------------------------------

function allFields() {
  return (state.config && state.config.fields) || [];
}

function fieldsOfGroup(group) {
  return allFields()
    .filter((field) => field.group === group)
    .sort((left, right) => left.order - right.order);
}

function fieldsOfConnection(connectionKey) {
  return allFields()
    .filter((field) => field.connection === connectionKey)
    .sort((left, right) => left.order - right.order);
}

function defaultLabel(field) {
  if (field.default === null || field.default === undefined || field.default === "") return "未设置";
  if (field.kind === "bool") return field.default ? "启用" : "停用";
  return String(field.default);
}

function sourcePill(field) {
  if (field.source === "env") return pill(field.env_var ? `env 覆盖：${field.env_var}` : "env 覆盖", "warn");
  if (field.source === "file") return pill("受管文件", "ok");
  return pill("默认", "");
}

function buildInput(field) {
  let input;
  if (field.kind === "bool") {
    input = document.createElement("select");
    [["default", "默认"], ["true", "启用"], ["false", "停用"]].forEach(([value, label]) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = label;
      input.append(option);
    });
    input.value = field.source === "default" ? "default" : field.value ? "true" : "false";
  } else if (field.kind === "int" || field.kind === "float") {
    input = document.createElement("input");
    input.type = "number";
    if (field.min !== null && field.min !== undefined) input.min = String(field.min);
    if (field.max !== null && field.max !== undefined) input.max = String(field.max);
    if (field.step) input.step = String(field.step);
    input.value = field.value === null || field.value === undefined ? "" : String(field.value);
    input.placeholder = `默认 ${defaultLabel(field)}`;
  } else {
    input = document.createElement("input");
    input.type = "text";
    input.value = field.value === null || field.value === undefined ? "" : String(field.value);
    input.placeholder = field.kind === "url" ? "https://…（留空回到默认）" : "留空回到默认";
  }
  input.id = `f-${field.path}`;
  if (!field.editable) {
    input.disabled = true;
    input.title = field.readonly_reason || (field.env_var ? `被环境变量 ${field.env_var} 覆盖` : "只读");
  }
  return input;
}

function renderField(field) {
  const wrapper = document.createElement("div");
  wrapper.className = "field";
  const label = document.createElement("label");
  label.htmlFor = `f-${field.path}`;
  label.textContent = field.label;
  const meta = document.createElement("div");
  meta.className = "meta";
  meta.append(sourcePill(field), ` 影响：${field.consumer}`, ` · 默认：${defaultLabel(field)}`);
  if (field.readonly_reason) meta.append(" ", pill("只读展示", "warn"), ` ${field.readonly_reason}`);
  label.append(document.createElement("br"), meta);

  const input = buildInput(field);
  wrapper.append(label, input);
  state.widgets.set(field.path, { field, node: input });
  if (field.editable) {
    input.addEventListener("input", () => refreshDirty(field.path));
    input.addEventListener("change", () => refreshDirty(field.path));
  }
  return wrapper;
}

function renderGroup(containerId, group) {
  const container = el(containerId);
  if (!container) return;
  // 「档位」字段由「对话模型」角色用下拉渲染，其它卡片不再给它第二个入口。
  const fields = fieldsOfGroup(group).filter((field) => field.path !== ROLE_PROFILE_FIELD);
  container.replaceChildren(...fields.map(renderField));
}

function patchValueOf(path) {
  const entry = state.widgets.get(path);
  if (!entry) return null;
  const { field, node } = entry;
  if (field.kind === "bool") {
    if (node.value === "default") return null;
    return node.value === "true";
  }
  const raw = node.value.trim();
  if (raw === "") return null;
  if (field.kind === "int" || field.kind === "float") {
    const parsed = Number(raw);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return raw;
}

function initialValueOf(field) {
  if (field.source === "default" || field.value === null || field.value === undefined) return null;
  if (field.kind === "bool") return Boolean(field.value);
  if (field.kind === "int" || field.kind === "float") return Number(field.value);
  const raw = String(field.value).trim();
  return raw === "" ? null : raw;
}

function applyValueToWidget(path, value) {
  const entry = state.widgets.get(path);
  if (!entry || !entry.field.editable) return;
  if (entry.field.kind === "bool") {
    entry.node.value = value === null ? "default" : value ? "true" : "false";
    return;
  }
  entry.node.value = value === null ? "" : String(value);
}

function refreshDirty(path) {
  const entry = state.widgets.get(path);
  if (!entry) return;
  const current = patchValueOf(path);
  if (current === initialValueOf(entry.field)) state.dirty.delete(path);
  else state.dirty.set(path, current);
  const wrapper = entry.node.closest(".field");
  if (wrapper) wrapper.classList.toggle("dirty", state.dirty.has(path));
  renderBanner();
  renderRetentionPreview();
  // 角色块里的「测试将请求：…」跟着未保存的值走，否则预览会骗人。
  renderRoleUrlPreviews();
}

function dirtyPathsFor(predicate) {
  return [...state.dirty.keys()].filter((path) => {
    const entry = state.widgets.get(path);
    return entry ? predicate(entry.field) : false;
  });
}

function buildPatch(paths) {
  const body = {};
  paths.forEach((path) => {
    const parts = path.split(".");
    let cursor = body;
    for (let index = 0; index < parts.length - 1; index += 1) {
      if (!cursor[parts[index]]) cursor[parts[index]] = {};
      cursor = cursor[parts[index]];
    }
    cursor[parts[parts.length - 1]] = state.dirty.get(path);
  });
  return body;
}

// -- 生效横幅 ---------------------------------------------------------------

function renderBanner() {
  const banner = el("banner");
  if (!banner) return;
  const pending = state.dirty.size + state.keys.size;
  const parts = [];
  if (pending) parts.push(`${pending} 项未保存`);
  if (state.needsRestart) parts.push("已保存的改动需重启生效");
  const command = el("restartCommand");
  const copy = el("copyRestart");
  if (!parts.length) {
    banner.classList.add("hidden");
    el("bannerText").textContent = "";
    if (command) command.classList.add("hidden");
    if (copy) copy.classList.add("hidden");
    return;
  }
  banner.classList.remove("hidden");
  banner.classList.toggle("saved", pending === 0);
  el("bannerText").textContent = parts.join(" · ");
  if (command) command.classList.toggle("hidden", !state.needsRestart);
  if (copy) copy.classList.toggle("hidden", !state.needsRestart);
}

// -- 卡片 1：采集与构建 ------------------------------------------------------

function renderCollection() {
  const freshness = (state.status && state.status.freshness) || {};
  const perDomain = freshness.per_domain || {};
  const history = freshness.collection_history || {};
  const hint = el("collectionHint");
  if (hint) hint.textContent = freshness.pack_build_at ? `pack 构建于 ${shortTime(freshness.pack_build_at)}` : "等待系统状态…";

  const body = el("freshnessBody");
  if (body) {
    body.replaceChildren(
      ...FRESHNESS_DOMAINS.map((domain) => {
        const entry = perDomain[domain] || {};
        const tr = document.createElement("tr");
        [
          DOMAIN_LABEL[domain] || domain,
          entry.record_count === null || entry.record_count === undefined ? "—" : entry.record_count,
          shortTime(entry.pack_build_at),
          humanAge(entry.pack_build_age_seconds),
          shortTime(entry.projection_as_of),
        ].forEach((value, index) => {
          const cell = document.createElement("td");
          cell.textContent = String(value);
          if (index === 1) cell.className = "mono";
          tr.append(cell);
        });
        return tr;
      }),
    );
  }

  const rows = el("collectionState");
  if (rows) {
    rows.replaceChildren(
      row("pack 构建时间", shortTime(freshness.pack_build_at)),
      row("投影 as_of", `${shortTime(freshness.projection_as_of)}（${humanAge(freshness.projection_age_seconds)}前）`),
      row(
        "采集历史",
        history.state === "ok"
          ? "可读"
          : `不可用：${history.reason || "构建期库不在本机（仅在构建/发布机可读）"}`,
      ),
    );
  }
}

// -- 卡片 3：存储与保留 ------------------------------------------------------

function renderStorage() {
  const rows = el("storageRows");
  if (!rows) return;
  const status = state.status || {};
  const sources = (status.storage || {}).sources || {};
  const entries = [];
  ["lookup", "corrections", "access_log"].forEach((key) => {
    const entry = sources[key] || {};
    if (entry.state === "ok") {
      const tables = Object.entries(entry.tables || {})
        .map(([name, count]) => `${name}=${count}`)
        .join(" · ");
      entries.push(row(`SQLite ${key}`, `${humanBytes(entry.bytes)} · quick_check=${entry.quick_check} · ${tables}`));
    } else {
      entries.push(row(`SQLite ${key}`, `不可用：${entry.reason || "未知"}`));
    }
  });
  ((status.disk || {}).volumes || []).forEach((volume) => {
    entries.push(
      volume.state === "ok"
        ? row(
            `磁盘 ${volume.path}`,
            `剩余 ${humanBytes(volume.free_bytes)} / 共 ${humanBytes(volume.total_bytes)}（已用 ${volume.used_percent}%）`,
          )
        : row(`磁盘 ${volume.path}`, "不可用"),
    );
  });
  rows.replaceChildren(...entries);
  renderRetentionPreview();
}

function retentionValue() {
  if (state.dirty.has(RETENTION_FIELD)) return state.dirty.get(RETENTION_FIELD);
  const field = allFields().find((item) => item.path === RETENTION_FIELD);
  if (!field) return null;
  return field.source === "default" ? field.default : field.value;
}

function renderRetentionPreview() {
  const node = el("retentionPreview");
  if (!node) return;
  const days = retentionValue();
  if (typeof days !== "number" || !isFinite(days)) {
    node.textContent = "保留期预览：默认（未设置天数）";
    return;
  }
  const cutoff = new Date(Date.now() - days * 86400 * 1000);
  const text_ = cutoff.toISOString().slice(0, 10);
  node.textContent = `保留期预览：保留最近 ${days} 天，访问日志早于 ${text_} 的部分会被清理`;
}

// -- 卡片 4：模型与连接（按角色，不按文件） -----------------------------------

// 一个角色 = 一个运行期连接 + 该连接自己的目录字段。页面不持有任何端点路径：
// 字段按 connection 从 /config 的目录里取，base_url 与 model 用目录自带的 test_arg
// 分辨；唯一显式路径是「档位」字段（它是 I4 新增的目录行，下拉项来自
// presets.llm_profiles）。拉取模型列表与测试都用页面上「未保存」的值。
const ROLE_PROFILE_FIELD = "serving.chat_llm_profile";
const MODEL_PICKER_LIMIT = 200; // ≤ 200 个模型用下拉，更多用过滤框 + <datalist>
const MODELS_TIMEOUT_MS = 3000; // 客户端护栏：3 秒没有响应就按「超时」报告
const MODEL_PATH = "/v1/models";
// 与服务端 canonical_v2_connection_tests.build_request 同规则：预览必须是测试
// 真正会请求的地址，而不是页面另算一个。
const TEST_PATH_BY_KIND = {
  llm: "/chat/completions",
  rerank: "/v1/rerank",
  embedding: "/v1/embeddings",
};
const MODEL_ERROR_TEXT = {
  unauthorized: "密钥被拒绝（401/403）",
  unreachable: "连不上该地址",
  timeout: "3 秒内没有响应",
  not_supported: "该端点没有 /v1/models，请直接手填模型 ID",
  bad_response: "返回内容无法解析",
};
// 卡片头的「全部测试」：一个按钮把每个角色的连接各探一次。服务端按连接 + 按客户端
// 限频（6 次/分钟，且相邻两次 ≥1 秒），所以只能串行并留出间隔：并发会让后几个探针
// 直接吃 429。web 角色有两个提供方，各算一次，共 6 次。
const ALL_TEST_GAP_MS = 1200;
const ALL_TEST_ROLES = [
  { connection: "llm", label: "对话模型", role: "chat" },
  { connection: "llm", label: "采集模型", role: "collection" },
  { connection: "embedding", label: "嵌入模型", role: "embedding" },
  { connection: "rerank", label: "重排模型", role: "rerank" },
  { connection: "bocha", label: "Web 搜索（Bocha）" },
  { connection: "serper", label: "Web 搜索（Serper）" },
];

// 角色 → 连接。fields 是该角色自己渲染的目录字段（connection 名）；keyRow 表示
// 「写密钥」的入口在这个角色里——同一个连接只在一个角色里给密钥入口；
// fetch 表示这一块给「拉取模型列表」（对话模型不给：档位定了模型 id，选出来没有字段可写）。
const ROLES = {
  chat: { connection: "llm", keyRow: true, profiles: true, test: true },
  collection: {
    connection: "llm",
    fields: "llm",
    presets: true,
    fetch: true,
    test: true,
  },
  embedding: { connection: "embedding", fields: "embedding", keyRow: true, frozen: true, test: true },
  rerank: {
    connection: "rerank",
    fields: "rerank",
    keyRow: true,
    presets: true,
    fetch: true,
    test: true,
  },
};

function joinUrl(baseUrl, path) {
  const root = String(baseUrl || "").trim().replace(/\/+$/, "");
  if (!root) return "";
  if (root.endsWith(path)) return root;
  if (root.endsWith("/v1") && path.indexOf("/v1/") === 0) return root + path.slice(3);
  return root + path;
}

function connectionByKey(connectionKey) {
  const connections = (state.secrets && state.secrets.connections) || [];
  return connections.find((connection) => connection.key === connectionKey) || null;
}

function runtimeOf(connectionKey) {
  const connection = connectionByKey(connectionKey);
  return connection ? connection.runtime || {} : {};
}

function runtimeBadge(connection) {
  const wrapper = document.createElement("span");
  if (!connection) {
    wrapper.append(pill("运行期状态未知", "warn"));
    return wrapper;
  }
  const runtime = connection.runtime || {};
  wrapper.append(pill(runtime.enabled ? "运行期已启用" : "运行期未启用", runtime.enabled ? "ok" : "warn"));
  if (runtime.pending_restart) wrapper.append(" ", pill("待重启生效", "warn"));
  return wrapper;
}

function roleFields(roleId) {
  const role = ROLES[roleId] || {};
  if (!role.fields) return [];
  // 档位字段由「对话模型」的下拉渲染，不出现在字段列表里（一个字段一个入口）。
  return fieldsOfConnection(role.fields).filter((field) => field.path !== ROLE_PROFILE_FIELD);
}

function roleFieldFor(roleId, testArg) {
  return roleFields(roleId).find((field) => field.test_arg === testArg) || null;
}

function currentValueOf(path) {
  const entry = state.widgets.get(path);
  if (!entry) return null;
  const current = patchValueOf(path);
  return current === null ? initialValueOf(entry.field) : current;
}

function sourceText(field) {
  if (!field) return "未知";
  if (field.source === "env") return field.env_var ? `env 覆盖（${field.env_var}）` : "env 覆盖";
  if (field.source === "file") return "受管文件";
  return "默认值";
}

function presetPayload() {
  return state.presets || {};
}

function profileField() {
  return allFields().find((field) => field.path === ROLE_PROFILE_FIELD) || null;
}

function profileList() {
  return presetPayload().llm_profiles || [];
}

function selectedProfileName() {
  const entry = state.widgets.get(ROLE_PROFILE_FIELD);
  if (entry && entry.node.value) return String(entry.node.value);
  const field = profileField();
  if (field && field.value) return String(field.value);
  return String(presetPayload().chat_profile || "");
}

function selectedProfile() {
  const name = selectedProfileName();
  return profileList().find((profile) => profile.name === name) || null;
}

function embeddingFrozen() {
  const frozen = presetPayload().embedding_frozen;
  const runtime = runtimeOf("embedding");
  if (frozen && (frozen.base_url || frozen.model)) {
    return {
      base_url: frozen.base_url || null,
      model: frozen.model || null,
      note: frozen.note || "",
      source_text: "发布包冻结（presets.embedding_frozen）",
    };
  }
  return {
    base_url: runtime.base_url || null,
    model: runtime.model || null,
    note: runtime.runtime_note || "",
    source_text: runtime.base_url
      ? "运行期解析（release embedding bundle）"
      : "服务端未返回冻结的嵌入端点",
  };
}

function keyStatusRow(connectionKey, roleId) {
  const wrapper = document.createElement("div");
  wrapper.className = "keyrow";
  const entry = secretFor(connectionKey);
  wrapper.append(pill(keyStatusText(entry), entry && entry.configured ? "ok" : ""));
  const input = document.createElement("input");
  input.type = "password";
  input.autocomplete = "new-password";
  input.id = `role-${roleId}-key`;
  input.placeholder = "新密钥（留空 = 不改动；明文既不回显也不入日志）";
  input.addEventListener("input", () => {
    const value = input.value.trim();
    if (value) state.keys.set(connectionKey, value);
    else state.keys.delete(connectionKey);
    renderBanner();
  });
  const clearButton = document.createElement("button");
  clearButton.type = "button";
  clearButton.textContent = "清除密钥";
  clearButton.addEventListener("click", () =>
    clearSecret(connectionKey, el(`role-${roleId}-key-result`)),
  );
  const result = text("span", "result", "");
  result.id = `role-${roleId}-key-result`;
  wrapper.append(input, clearButton, result);
  if (entry && entry.env_var) {
    wrapper.append(text("span", "meta", `写入受管文件，重启后由环境变量 ${entry.env_var} 读取`));
  }
  return wrapper;
}

function pinnedBaseUrl(connectionKey) {
  const runtime = runtimeOf(connectionKey);
  return runtime.base_url || "";
}

function roleBaseUrl(roleId) {
  const role = ROLES[roleId] || {};
  if (roleId === "chat") {
    const profile = selectedProfile();
    return (profile && profile.base_url) || "";
  }
  if (role.frozen) return embeddingFrozen().base_url || "";
  const baseField = roleFieldFor(roleId, "base_url");
  // 字段为空不等于没有端点：端点可能来自环境变量或运行期默认（页面「生效端点」那一行）。
  // 真机实测发现：只认表单值会让「拉取模型列表 / 测试连通性」对 env 提供的端点直接拒绝。
  if (baseField) return currentValueOf(baseField.path) || pinnedBaseUrl(role.connection);
  return pinnedBaseUrl(role.connection);
}

function roleTestUrl(roleId) {
  const role = ROLES[roleId] || {};
  const base = roleBaseUrl(roleId);
  const path = TEST_PATH_BY_KIND[role.connection];
  return base && path ? joinUrl(base, path) : base;
}

function modelsUrlFor(roleId) {
  return joinUrl(roleBaseUrl(roleId), MODEL_PATH);
}

function setUrlPreview(node, url, note) {
  if (!node) return;
  const parts = [text("span", "", url ? "测试将请求：" : "测试将请求：—")];
  parts.push(
    url
      ? text("code", "", url)
      : text("span", "", "（端点未配置/未启用，运行期不会发起调用）"),
  );
  if (note) parts.push(text("span", "", note));
  node.replaceChildren(...parts);
}

function renderRoleUrlPreviews() {
  ["chat", "collection", "embedding", "rerank"].forEach((roleId) => {
    const node = el(`role-${roleId}-url`);
    if (node) {
      setUrlPreview(node, roleTestUrl(roleId), roleId === "embedding" ? "（服务线冻结端点）" : "");
    }
    // 模型列表是另一个地址（{base_url}/v1/models）：这里给的是页面按同一套拼接
    // 规则算出的预期值，服务端返回的 request_url 才是权威，成功后一并展示。
    const modelsNode = el(`role-${roleId}-models-url`);
    if (modelsNode) {
      const url = modelsUrlFor(roleId);
      modelsNode.textContent = url
        ? `模型列表将请求：${url}（页面推算；服务端会在结果里给出 request_url）`
        : "模型列表将请求：—（先填 Base URL 或选档位）";
    }
  });
  ((state.secrets || {}).connections || [])
    .filter((connection) => connection.kind === "web_search")
    .forEach((connection) => {
      const node = el(`role-web-${connection.key}-url`);
      if (node) {
        setUrlPreview(node, (connection.runtime || {}).base_url, "（provider 固定主机，页面不改写）");
      }
    });
}

function renderRoleState(roleId, nodes) {
  const node = el(`role-${roleId}-state`);
  if (!node) return;
  node.replaceChildren(...(nodes || []));
}

function renderRoleEffectiveRows(roleId, rows) {
  const node = el(`${roleId}Effective`);
  if (node) node.replaceChildren(...rows);
}

function secretFor(connectionKey) {
  const secrets = (state.secrets && state.secrets.secrets) || [];
  return secrets.find((entry) => entry.connection === connectionKey) || null;
}

function keyStatusText(entry) {
  if (!entry) return "服务端未返回该连接的密钥状态";
  if (!entry.configured) return "未设置";
  const origin = entry.origin === "managed-file" ? "受管文件" : entry.origin || "未知来源";
  return `已设置 · ${entry.mask || ""} · 来源 ${origin}${entry.applied_to_process_env ? "（本进程已读取）" : ""}`;
}

function renderRoles() {
  const path = el("secretsPath");
  if (path && state.secrets) {
    path.textContent = `${state.secrets.path}（${state.secrets.exists ? "已存在" : "尚未创建"}）`;
  }
  if (state.secrets && state.secrets.permissions_ok === false) {
    notice(el("secretsNotice"), "警告：受管密钥文件权限不是 0600，请检查（页面不会回显其内容）", "bad");
  } else {
    hideNotice(el("secretsNotice"));
  }
  renderChatRole();
  renderCollectionRole();
  renderEmbeddingRole();
  renderRerankRole();
  renderWebRole();
  // 重渲染后把已拉取到的模型列表还原（列表跟随角色块，不进 fetch 结果节点）。
  ["collection", "rerank"].forEach((roleId) => renderModelPicker(roleId));
  applyDirtyToWidgets();
  renderRoleUrlPreviews();
  if (state.keys.size) renderBanner();
}

function renderChatRole() {
  const field = profileField();
  const profiles = profileList();
  const current = selectedProfileName();
  const profile = selectedProfile();
  renderRoleState("chat", [runtimeBadge(connectionByKey("llm"))]);
  const chatRuntime = runtimeOf("llm");
  const runningProfile = String(presetPayload().chat_profile || "");
  const pendingSwitch =
    runningProfile && current && runningProfile !== current
      ? `本进程仍跑 ${runningProfile}；重启后切到 ${current}`
      : "与保存值一致";
  renderRoleEffectiveRows("chat", [
    row("档位（保存值）", current || "—"),
    row("档位（运行期）", runningProfile ? `${runningProfile} · ${pendingSwitch}` : pendingSwitch),
    row("该档位的模型", profile ? profile.model || "—" : "档位不在档位表里（模型/端点未知）"),
    row("该档位的端点", profile ? profile.base_url || "—" : "—"),
    row(
      "该档位的密钥变量",
      profile && profile.key_env ? `${profile.key_env}（写在下面的密钥框，重启后生效）` : "—",
    ),
    row(
      "运行期端点",
      chatRuntime.base_url
        ? `${chatRuntime.base_url} · 来源：${chatRuntime.endpoint_origin || "未标注"}`
        : "未解析",
    ),
    row("运行期说明", chatRuntime.runtime_note || "服务端未返回该连接的运行期说明"),
  ]);

  const body = el("chatBody");
  if (body) {
    const line = document.createElement("div");
    line.className = "roleline";
    line.append(text("label", "", "档位（profile）"));
    const select = document.createElement("select");
    select.id = "chat-profile";
    const names = new Set(profiles.map((item) => item.name));
    profiles.forEach((item) =>
      select.append(optionNode(item.name, `${item.label || item.name}（${item.name}）`)),
    );
    if (current && !names.has(current)) {
      select.append(optionNode(current, `${current}（当前生效，不在档位表里）`));
    }
    if (!profiles.length) {
      select.append(
        optionNode(
          "",
          state.presetsError ? `档位表不可用（${state.presetsError}）` : "档位表加载中…",
        ),
      );
      select.disabled = true;
    } else {
      select.value = current;
    }
    const detail = text("span", "meta", "");
    detail.id = "chat-profile-detail";
    detail.textContent = profile
      ? `模型 ${profile.model || "—"} · 端点 ${profile.base_url || "—"}`
      : "该档位不在档位表里：模型/端点未知";
    if (field && field.editable && !select.disabled) {
      state.widgets.set(field.path, { field, node: select });
      select.addEventListener("change", () => {
        refreshDirty(field.path);
        const picked = selectedProfile();
        detail.textContent = picked
          ? `模型 ${picked.model || "—"} · 端点 ${picked.base_url || "—"}`
          : "该档位不在档位表里：模型/端点未知";
      });
    } else {
      select.disabled = true;
    }
    line.append(select, detail);
    const notes = [];
    if (!profiles.length) {
      notes.push(
        text(
          "p",
          "meta",
          state.presetsError
            ? `档位表不可用：${state.presetsError}（仍然展示运行期档位；拉取模型列表需要预设接口）`
            : "档位表加载中…",
        ),
      );
    }
    if (!field) {
      notes.push(
        text(
          "p",
          "meta",
          `配置目录暂未提供档位字段（${ROLE_PROFILE_FIELD}）：这里只展示运行期档位，保存档位需要目录先支持该字段。`,
        ),
      );
    } else if (!field.editable) {
      notes.push(
        text(
          "p",
          "meta",
          `档位字段不可写：${field.readonly_reason || (field.env_var ? `被环境变量 ${field.env_var} 覆盖` : "服务端标记为只读")}`,
        ),
      );
    }
    body.replaceChildren(line, ...notes, keyStatusRow("llm", "chat"));
  }
  roleActions("chat", { connection: "llm", paths: [ROLE_PROFILE_FIELD], save: true, test: true });
}

function renderCollectionRole() {
  const fields = roleFields("collection");
  const baseField = roleFieldFor("collection", "base_url");
  const modelField = roleFieldFor("collection", "model");
  renderRoleState("collection", [
    fields.length
      ? pill(
          `端点来源：${sourceText(baseField)}`,
          baseField && baseField.source === "env" ? "warn" : "ok",
        )
      : pill("目录里没有采集端点字段", "warn"),
  ]);
  const llmRuntime = runtimeOf("llm");
  renderRoleEffectiveRows("collection", [
    row(
      "生效端点",
      baseField ? `${baseField.value || "未设置"} · 来源：${sourceText(baseField)}` : "—",
    ),
    row(
      "生效模型",
      modelField
        ? `${modelField.value || "未设置"} · 来源：${sourceText(modelField)}`
        : "—",
    ),
    row("凭据来源", llmRuntime.api_key_origin || "未配置（与「对话模型」档位同一份凭据）"),
    row("说明", "采集与构建用它做摘要与富化；改动要重启服务才生效。"),
  ]);

  const body = el("collectionBody");
  if (body) {
    body.replaceChildren(
      presetRow("collection"),
      ...fields.map(renderField),
      text("p", "meta", "凭据与「对话模型」档位共用一份（llm）：在那块填写，这里不设第二个入口。"),
      fetchRow("collection"),
    );
  }
  roleActions("collection", {
    connection: "llm",
    paths: fields.map((field) => field.path),
    save: true,
    test: true,
  });
}

function renderEmbeddingRole() {
  const frozen = embeddingFrozen();
  const fields = roleFields("embedding");
  const readonly = fields.find((field) => !field.editable && field.readonly_reason);
  renderRoleState("embedding", [
    runtimeBadge(connectionByKey("embedding")),
    pill("只读：服务线冻结值", "warn"),
  ]);
  const rows = [
    row("生效端点（服务线）", frozen.base_url || "—"),
    row("生效模型（服务线）", frozen.model || "—"),
    row("来源", frozen.source_text),
  ];
  if (frozen.note) rows.push(row("服务端说明", frozen.note));
  if (readonly) rows.push(row("只读原因", readonly.readonly_reason));
  renderRoleEffectiveRows("embedding", rows);

  const body = el("embeddingBody");
  if (body) {
    const details = document.createElement("details");
    details.className = "advanced";
    details.append(text("summary", "", "高级：采集侧覆盖"));
    const note = readonly
      ? `只影响后续采集/构建，不改服务线索引；服务端只读原因见上：${readonly.readonly_reason}`
      : "只影响后续采集/构建，不改服务线索引：上面那两行才是检索向量真正在用的端点与模型。";
    details.append(text("p", "note", note));
    if (fields.length) details.append(...fields.map(renderField));
    else details.append(text("p", "note", "目录里没有采集侧覆盖字段。"));
    body.replaceChildren(keyStatusRow("embedding", "embedding"), details);
  }
  roleActions("embedding", {
    connection: "embedding",
    paths: fields.map((field) => field.path),
    save: true,
    test: true,
  });
}

function renderRerankRole() {
  const fields = roleFields("rerank");
  const runtime = runtimeOf("rerank");
  const baseField = roleFieldFor("rerank", "base_url");
  const modelField = roleFieldFor("rerank", "model");
  renderRoleState("rerank", [runtimeBadge(connectionByKey("rerank"))]);
  renderRoleEffectiveRows("rerank", [
    row(
      "生效端点",
      (baseField && baseField.value) || runtime.base_url || "未配置（未配置则 rerank 不启用）",
    ),
    row(
      "生效模型",
      modelField ? `${modelField.value || "未设置"} · 来源：${sourceText(modelField)}` : runtime.model || "—",
    ),
    row("运行期说明", runtime.runtime_note || "服务端未返回该连接的运行期说明"),
  ]);

  const body = el("rerankBody");
  if (body) {
    body.replaceChildren(
      presetRow("rerank"),
      ...fields.map(renderField),
      keyStatusRow("rerank", "rerank"),
      fetchRow("rerank"),
    );
  }
  roleActions("rerank", {
    connection: "rerank",
    paths: fields.map((field) => field.path),
    save: true,
    test: true,
  });
}

function renderWebRole() {
  const body = el("webBody");
  if (!body) return;
  const connections = ((state.secrets || {}).connections || []).filter(
    (connection) => connection.kind === "web_search",
  );
  renderRoleState("web", [pill(`${connections.length} 个搜索提供方`, "")]);
  if (!connections.length) {
    body.textContent = state.secrets ? "服务端未返回 Web 搜索连接" : "等待密钥状态…";
    return;
  }
  body.replaceChildren(...connections.map(renderWebConnection));
}

function renderWebConnection(connection) {
  const card = document.createElement("section");
  card.className = "subconn";

  const header = document.createElement("header");
  header.append(text("h4", "", connection.label || connection.key), runtimeBadge(connection));
  card.append(header);
  card.append(text("p", "meta", (connection.runtime || {}).runtime_note || ""));
  card.append(
    text(
      "p",
      "meta",
      `端点由 provider 固定：${pinnedBaseUrl(connection.key) || "未解析"}（页面不改写）`,
    ),
  );
  card.append(keyStatusRow(connection.key, `web-${connection.key}`));

  const actions = document.createElement("div");
  actions.className = "actions";
  const testButton = document.createElement("button");
  testButton.type = "button";
  testButton.textContent = "测试连通性";
  testButton.id = `role-web-${connection.key}-test`;
  const testResult = text("span", "result", "未测试");
  testResult.id = `role-web-${connection.key}-test-result`;
  testButton.addEventListener("click", () => testConnection(connection.key, testButton, testResult));
  const saveButton = document.createElement("button");
  saveButton.type = "button";
  saveButton.className = "primary";
  saveButton.textContent = "保存本卡";
  saveButton.id = `role-web-${connection.key}-save`;
  const saveResult = text("span", "result", "");
  saveResult.id = `role-web-${connection.key}-save-result`;
  saveButton.addEventListener("click", () =>
    saveRoleBlock({
      connectionKey: connection.key,
      paths: [],
      writeKey: true,
      button: saveButton,
      resultNode: saveResult,
    }),
  );
  const preview = text("div", "url-preview", "");
  preview.id = `role-web-${connection.key}-url`;
  actions.append(testButton, saveButton, testResult, saveResult, preview);
  card.append(actions);
  return card;
}

function presetRow(roleId) {
  const line = document.createElement("div");
  line.className = "roleline";
  line.append(text("label", "", "提供方预设"));
  const select = document.createElement("select");
  select.id = `role-${roleId}-preset`;
  const presets = presetPayload().presets || [];
  const baseField = roleFieldFor(roleId, "base_url");
  const meta = text("span", "meta", "");
  const docs = document.createElement("a");
  docs.className = "meta";
  docs.target = "_blank";
  docs.rel = "noopener";
  docs.hidden = true;
  docs.textContent = "提供方文档";
  if (!presets.length) {
    select.disabled = true;
    select.append(optionNode("", state.presetsError ? "预设接口不可用" : "预设加载中…"));
    meta.textContent = state.presetsError
      ? `预设不可用：${state.presetsError}（仍可直接手填 Base URL）`
      : "预设只是填值：选一个会把它的默认 Base URL 填进下面的字段";
  } else {
    select.append(optionNode("", "选择预设填入 Base URL…"));
    presets.forEach((preset) =>
      select.append(optionNode(preset.id, preset.label || preset.id)),
    );
    select.addEventListener("change", () => {
      const preset = presets.find((item) => item.id === select.value);
      if (!preset) return;
      if (preset.base_url && baseField) {
        applyValueToWidget(baseField.path, preset.base_url);
        refreshDirty(baseField.path);
      }
      const parts = [`已填入 ${preset.base_url || "（该预设没有默认地址）"}`];
      if (!preset.base_url) parts.push("直接手填 Base URL");
      if (preset.needs_key === false) parts.push("该预设不需要密钥");
      if (preset.note) parts.push(preset.note);
      meta.textContent = parts.join(" · ");
      if (preset.docs_url) {
        docs.href = preset.docs_url;
        docs.hidden = false;
      } else {
        docs.hidden = true;
      }
      select.value = "";
      renderRoleUrlPreviews();
    });
    meta.textContent = "预设只是填值：选一个会把它的默认 Base URL 填进下面的字段";
  }
  line.append(select, meta, docs);
  return line;
}

function fetchRow(roleId) {
  const wrap = document.createElement("div");
  const line = document.createElement("div");
  line.className = "roleline";
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = "拉取模型列表";
  button.id = `role-${roleId}-fetch`;
  const spinner = text("span", "spinner hidden", "");
  spinner.id = `role-${roleId}-spinner`;
  spinner.setAttribute("aria-hidden", "true");
  const result = text("span", "result", "未拉取");
  result.id = `role-${roleId}-models-result`;
  button.addEventListener("click", () => fetchModels(roleId, button));
  line.append(button, spinner, result);
  const url = text("div", "url-preview", "");
  url.id = `role-${roleId}-models-url`;
  const box = document.createElement("div");
  box.className = "model-picker";
  box.id = `role-${roleId}-models-picker`;
  box.hidden = true;
  wrap.append(line, url, box);
  return wrap;
}

async function fetchModels(roleId, button) {
  const role = ROLES[roleId];
  const result = el(`role-${roleId}-models-result`);
  const spinner = el(`role-${roleId}-spinner`);
  const preview = modelsUrlFor(roleId);
  // 未保存的值也发：base_url 取页面上的当前值，密钥取刚敲进去的那个（若有）。
  const request = { connection: role.connection };
  const base = roleBaseUrl(roleId);
  if (!base) {
    // 本地拦下：没有端点就不发请求（服务端也会回 unreachable，但那是一次白跑）。
    renderModelPicker(roleId);
    if (result) {
      result.textContent =
        "还没有可用端点：先填 Base URL（或选一个预设/档位），再拉取模型列表。";
    }
    return;
  }
  request.base_url = base;
  const typed = (state.keys.get(role.connection) || "").trim();
  if (typed) request.api_key = typed;
  state.modelLists.delete(roleId);
  renderModelPicker(roleId);
  button.disabled = true;
  if (spinner) spinner.classList.remove("hidden");
  if (result) result.textContent = `拉取中…（页面最多等 ${MODELS_TIMEOUT_MS / 1000} 秒）`;
  const controller = typeof AbortController === "function" ? new AbortController() : null;
  const timer = controller ? setTimeout(() => controller.abort(), MODELS_TIMEOUT_MS) : null;
  try {
    const options = {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(request),
    };
    if (controller) options.signal = controller.signal;
    const response = await fetch(API.connectionModels(role.connection), options);
    const payload = await response.json().catch(() => null);
    if (result) result.textContent = describeModelOutcome(roleId, response, payload, preview);
  } catch (error) {
    if (result) {
      result.textContent =
        error && error.name === "AbortError"
          ? `${MODEL_ERROR_TEXT.timeout}（页面在 ${MODELS_TIMEOUT_MS / 1000} 秒后放弃等待） · 请求 ${preview || "—"}`
          : `拉取失败：${error} · 请求 ${preview || "—"}`;
    }
  } finally {
    if (timer) clearTimeout(timer);
    if (spinner) spinner.classList.add("hidden");
    button.disabled = false;
    renderModelPicker(roleId);
  }
}

function describeModelOutcome(roleId, response, payload, preview) {
  if (payload === null || typeof payload !== "object") {
    return `返回内容无法解析（HTTP ${response.status}） · 请求 ${preview || "—"}`;
  }
  if (response.status === 429) {
    const detail = payload.detail || {};
    return `限频：请 ${detail.retry_after_seconds || "稍后"} 秒后再试（服务端已拦截，未发起调用）`;
  }
  if (payload.error) {
    const message = MODEL_ERROR_TEXT[payload.error] || `拉取失败（${payload.error}）`;
    const status =
      payload.status === null || payload.status === undefined ? "" : ` · HTTP ${payload.status}`;
    const excerpt = payload.body_excerpt
      ? ` · 响应片段：${truncate(payload.body_excerpt, 120)}`
      : "";
    return `${message}${status} · 请求 ${payload.request_url || preview || "—"} · ${payload.elapsed_ms} ms${excerpt}`;
  }
  if (!response.ok) {
    return `拉取被拒绝（HTTP ${response.status}）：${describeDetail(payload.detail)} · 请求 ${preview || "—"}`;
  }
  const ids = (payload.models || [])
    .map((item) => (typeof item === "string" ? item : item && item.id))
    .filter(Boolean);
  const count = typeof payload.count === "number" ? payload.count : ids.length;
  state.modelLists.set(roleId, {
    ids,
    request_url: payload.request_url || preview,
    elapsed_ms: payload.elapsed_ms,
    count,
    truncated: Boolean(payload.truncated),
  });
  return [
    `拉取到 ${count} 个模型`,
    payload.elapsed_ms === null || payload.elapsed_ms === undefined ? "" : `· HTTP 耗时 ${payload.elapsed_ms} ms`,
    `· 请求 ${payload.request_url || preview || "—"}`,
    payload.truncated ? "· 服务端只返回了前面一部分" : "",
  ]
    .filter(Boolean)
    .join(" ");
}

function renderModelPicker(roleId) {
  const box = el(`role-${roleId}-models-picker`);
  if (!box) return;
  const modelField = roleFieldFor(roleId, "model");
  const entry = state.modelLists.get(roleId);
  if (!entry || !entry.ids.length || !modelField) {
    box.hidden = true;
    box.replaceChildren();
    return;
  }
  const ids = entry.ids;
  const apply = (id) => {
    applyValueToWidget(modelField.path, id);
    refreshDirty(modelField.path);
  };
  if (ids.length <= MODEL_PICKER_LIMIT) {
    const select = document.createElement("select");
    select.id = `role-${roleId}-model-picker`;
    select.append(optionNode("", `从 ${ids.length} 个模型里选一个…`));
    ids.forEach((id) => select.append(optionNode(id, id)));
    select.append(optionNode("__manual__", "手填模型 ID（保留上面输入框里的值）"));
    select.addEventListener("change", () => {
      if (select.value === "__manual__") {
        select.value = "";
        const input = el(`f-${modelField.path}`);
        if (input) input.focus();
        return;
      }
      if (select.value) apply(select.value);
    });
    box.replaceChildren(
      select,
      text("span", "", `共 ${ids.length} 个：选中即填入上面的模型 ID 框；也可以直接手填。`),
    );
  } else {
    const datalistId = `role-${roleId}-model-ids`;
    const filter = document.createElement("input");
    filter.type = "text";
    filter.id = `role-${roleId}-model-filter`;
    filter.setAttribute("list", datalistId);
    filter.placeholder = `共 ${ids.length} 个模型：输入过滤，选中后自动填入`;
    const datalist = document.createElement("datalist");
    datalist.id = datalistId;
    ids.forEach((id) => datalist.append(optionNode(id, id)));
    const commit = () => {
      const value = filter.value.trim();
      if (ids.indexOf(value) >= 0) apply(value);
    };
    filter.addEventListener("input", commit);
    filter.addEventListener("change", commit);
    box.replaceChildren(
      text("label", "", "过滤模型 ID"),
      filter,
      datalist,
      text("span", "", `共 ${ids.length} 个：用过滤框搜索；也可以直接手填模型 ID。`),
    );
  }
  box.hidden = false;
}

function roleActions(roleId, options) {
  const actions = el(`${roleId}Actions`);
  if (!actions) return;
  const nodes = [];
  if (options.test) {
    const testButton = document.createElement("button");
    testButton.type = "button";
    testButton.textContent = "测试连通性";
    testButton.id = `role-${roleId}-test`;
    const testResult = text("span", "result", "未测试");
    testResult.id = `role-${roleId}-test-result`;
    testButton.addEventListener("click", () =>
      testConnection(options.connection, testButton, testResult, roleTestBody(roleId)),
    );
    nodes.push(testButton, testResult);
  }
  if (options.save) {
    const saveButton = document.createElement("button");
    saveButton.type = "button";
    saveButton.className = "primary";
    saveButton.textContent = "保存本卡";
    saveButton.id = `role-${roleId}-save`;
    const saveResult = text("span", "result", "");
    saveResult.id = `role-${roleId}-save-result`;
    saveButton.addEventListener("click", () =>
      saveRoleBlock({
        connectionKey: options.connection,
        paths: (options.paths || []).filter((path) => state.dirty.has(path)),
        writeKey: Boolean((ROLES[roleId] || {}).keyRow),
        button: saveButton,
        resultNode: saveResult,
      }),
    );
    nodes.push(saveButton, saveResult);
  }
  const preview = text("div", "url-preview", "");
  preview.id = `role-${roleId}-url`;
  actions.replaceChildren(...nodes, preview);
}

// 测试体：本角色的字段值（未保存的也算）优先，缺的由服务端按运行期解析。
// 密钥只在拥有密钥入口的角色里带上（否则会替另一块把别人的改动发出去）。
function roleTestBody(roleId) {
  const role = ROLES[roleId];
  const overrides = roleId === "collection" || roleId === "rerank" ? roleFields(roleId) : [];
  const body = connectionTestBody(role.connection, overrides, {
    includeKey: Boolean(role.keyRow),
  });
  if (roleId === "chat") {
    const profile = selectedProfile();
    if (profile) {
      if (profile.base_url) body.base_url = profile.base_url;
      if (profile.model) body.model = profile.model;
    }
  }
  return body;
}

function connectionTestBody(connectionKey, fields, options) {
  const body = { connection: connectionKey };
  const includeKey = !options || options.includeKey !== false;
  const pending = (state.keys.get(connectionKey) || "").trim();
  if (includeKey && pending) body.api_key = pending;
  const list = fields === undefined ? fieldsOfConnection(connectionKey) : fields;
  list.forEach((field) => {
    if (!field.test_arg) return;
    const value = currentValueOf(field.path);
    if (typeof value === "string" && value) body[field.test_arg] = value;
  });
  return body;
}

async function testConnection(connectionKey, button, resultNode, body) {
  const node = resultNode;
  button.disabled = true;
  if (node) node.textContent = "测试中…（一次最小调用）";
  try {
    const { response, payload } = await probeConnection(connectionKey, body);
    if (node) node.textContent = describeConnectionTest(response, payload).text;
  } catch (error) {
    if (node) node.textContent = `测试失败：${error}`;
  } finally {
    button.disabled = false;
  }
}

// 单点测试与「全部测试」共用一个请求与一份结果映射：措辞只在这里决定，
// 两条路径不会对同一次失败给出两种说法。
async function probeConnection(connectionKey, body) {
  const response = await fetch(API.connectionTest, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body || connectionTestBody(connectionKey)),
  });
  return { response, payload: await response.json() };
}

function describeConnectionTest(response, payload) {
  if (response.status === 429) {
    const detail = payload.detail || {};
    return {
      state: "untested",
      text: `限频：请 ${detail.retry_after_seconds || "稍后"} 秒后再试（服务端已拦截，未发起调用）`,
    };
  }
  if (!response.ok) {
    return {
      state: "untested",
      text: `测试被拒绝（HTTP ${response.status}）：${describeDetail(payload.detail)}`,
    };
  }
  const remaining = (payload.rate || {}).remaining;
  const text = [
    payload.ok ? "成功" : "失败",
    payload.called === false ? "（未发起调用）" : "",
    `· ${payload.latency_ms} ms`,
    payload.http_status === null || payload.http_status === undefined ? "" : `· HTTP ${payload.http_status}`,
    `· ${payload.detail}`,
    `· 凭据来源 ${(payload.used || {}).api_key_source || "—"}`,
    (payload.runtime || {}).enabled === false ? "· 运行期未启用" : "",
    remaining === null || remaining === undefined ? "" : `· 本分钟剩余 ${remaining} 次`,
    "· 测试不改配置，保存才写文件",
  ]
    .filter(Boolean)
    .join(" ");
  return {
    state: payload.ok ? "ok" : "fail",
    latency_ms: payload.latency_ms,
    detail: payload.detail,
    text,
  };
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function attachAllTests() {
  const host = el("allTestsControls");
  if (!host) return;
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = "全部测试";
  button.id = "test-all-roles";
  const status = text("span", "result", "");
  status.id = "allTestsStatus";
  button.addEventListener("click", () => runAllConnectionTests(button, status));
  host.replaceChildren(button, status);
}

// 端点与请求体都取该角色自己的那一套（未保存的值优先，缺的由服务端按运行期解析）；
// web 没有目录字段，就是它自己那条连接。
function allTestEndpoint(entry) {
  return entry.role ? roleBaseUrl(entry.role) : pinnedBaseUrl(entry.connection);
}

function allTestBody(entry) {
  return entry.role ? roleTestBody(entry.role) : connectionTestBody(entry.connection);
}

// 一个角色 → 一行结果。没有端点就不发请求（与「拉取模型列表」同一条本地判断）：
// 这是「未配置」而不是「不可用」，不该在汇总里冒充失败。
async function probeRoleConnection(entry) {
  if (!allTestEndpoint(entry)) return { state: "skipped", text: "未配置端点，已跳过" };
  const url = entry.role ? roleTestUrl(entry.role) : pinnedBaseUrl(entry.connection);
  let outcome;
  try {
    const { response, payload } = await probeConnection(entry.connection, allTestBody(entry));
    outcome = describeConnectionTest(response, payload);
  } catch (error) {
    outcome = { state: "untested", text: `测试失败：${error}` };
  }
  if (outcome.state === "ok") return { state: "ok", text: `可用（${outcome.latency_ms} ms）` };
  if (outcome.state === "fail") {
    return { state: "fail", text: `不可用：${outcome.detail}（请求 ${url || "—"}）` };
  }
  return { state: "untested", text: `未测：${outcome.text}` };
}

async function runAllConnectionTests(button, status) {
  const panel = el("allTestsPanel");
  const lines = [];
  const counts = { ok: 0, fail: 0, untested: 0, skipped: 0 };
  button.disabled = true;
  if (panel) {
    panel.hidden = false;
    panel.replaceChildren();
  }
  try {
    for (let index = 0; index < ALL_TEST_ROLES.length; index += 1) {
      const entry = ALL_TEST_ROLES[index];
      if (status) status.textContent = `测试中 ${index + 1}/${ALL_TEST_ROLES.length}…`;
      // 串行 + 间隔：服务端要求同一连接相邻两次 ≥1 秒，且与本机其它探针共享窗口。
      if (index) await delay(ALL_TEST_GAP_MS);
      const result = await probeRoleConnection(entry);
      counts[result.state] += 1;
      lines.push(row(entry.label, result.text));
      if (panel) panel.replaceChildren(...lines);
    }
    if (status) {
      status.textContent = `测试完成：${[
        ["可用", counts.ok],
        ["不可用", counts.fail],
        ["未测", counts.untested],
        ["跳过", counts.skipped],
      ]
        .filter((entry) => entry[1])
        .map((entry) => `${entry[0]} ${entry[1]}`)
        .join(" · ")}`;
    }
  } catch (error) {
    if (status) status.textContent = `全部测试中断：${error}`;
  } finally {
    button.disabled = false;
  }
}

// 「保存本卡」：先写密钥（若这一块拥有密钥入口），再写本卡脏的字段/档位。保存 ≠ 测试。
async function saveRoleBlock(options) {
  const { connectionKey, paths, button, resultNode, writeKey } = options;
  const messages = [];
  const resultId = resultNode ? resultNode.id : "";
  if (resultNode) resultNode.textContent = "保存中…";
  button.disabled = true;
  try {
    const pending = (state.keys.get(connectionKey) || "").trim();
    const entry = secretFor(connectionKey);
    if (writeKey && pending && entry) {
      const response = await fetch(API.secrets, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ values: { [entry.field]: pending } }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(`密钥保存被拒绝（HTTP ${response.status}）：${describeDetail(payload.detail)}`);
      }
      state.secrets = payload;
      state.keys.delete(connectionKey);
      if ((payload.changed || []).length) state.needsRestart = true;
      messages.push(`密钥已写入 ${(payload.changed || []).join("、")}`);
    }
    if (paths.length) {
      const changed = await saveConfig(paths);
      messages.push(`端点/模型/档位已保存 ${changed.join("、")}`);
    }
    if (!messages.length) messages.push("没有改动（密钥留空、字段未修改）");
    const restart = state.needsRestart
      ? `。保存 ≠ 测试；重启后生效：${RESTART_COMMAND}`
      : "。保存 ≠ 测试：保存只写受管文件，测试才是当场调用。";
    renderAll();
    const node = resultId ? el(resultId) : resultNode;
    if (node) node.textContent = `${messages.join("；")}${restart}`;
  } catch (error) {
    const node = resultId ? el(resultId) : resultNode;
    if (node) node.textContent = String(error.message || error);
  } finally {
    button.disabled = false;
  }
}

async function clearSecret(connectionKey, resultNode) {
  const entry = secretFor(connectionKey);
  if (!entry) return;
  if (!window.confirm(`${entry.label}：确认清除受管文件中的密钥？（清除后需重启服务生效）`)) return;
  const node = resultNode || null;
  const resultId = node ? node.id : "";
  try {
    const response = await fetch(API.secrets, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ values: { [entry.field]: null } }),
    });
    const payload = await response.json();
    if (!response.ok) {
      if (node) node.textContent = `清除被拒绝（HTTP ${response.status}）：${describeDetail(payload.detail)}`;
      return;
    }
    state.secrets = payload;
    if ((payload.changed || []).length) state.needsRestart = true;
    renderAll();
    const fresh = resultId ? el(resultId) : node;
    if (fresh) fresh.textContent = `已清除 ${(payload.changed || []).join("、")}`;
  } catch (error) {
    if (node) node.textContent = `清除失败：${error}`;
  }
}

// -- 保存 --------------------------------------------------------------------

async function saveConfig(paths) {
  const response = await fetch(API.config, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(buildPatch(paths)),
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(`保存被拒绝（HTTP ${response.status}）：${describeDetail(payload.detail)}`);
  }
  paths.forEach((path) => state.dirty.delete(path));
  state.config = payload;
  const changed = payload.changed || [];
  if (changed.length) state.needsRestart = true;
  renderFields();
  renderRoles();
  renderBanner();
  return changed;
}

async function saveCard(group, button) {
  const resultNode = el(`${group}Result`);
  if (resultNode) resultNode.textContent = "";
  const paths = dirtyPathsFor((field) => field.group === group);
  if (!paths.length) {
    if (resultNode) resultNode.textContent = "没有改动（只提交本卡修改过的字段）";
    return;
  }
  button.disabled = true;
  try {
    const changed = await saveConfig(paths);
    if (resultNode) {
      resultNode.textContent = `已保存 ${changed.length} 项：${changed.join("、")}${
        state.needsRestart ? `。${RESTART_COMMAND} 后生效` : ""
      }`;
    }
  } catch (error) {
    if (resultNode) resultNode.textContent = String(error.message || error);
  } finally {
    button.disabled = false;
  }
}

// -- 只读快照 ---------------------------------------------------------------

function renderSnapshot() {
  const rows = el("snapshotRows");
  const config = state.config || {};
  const secrets = state.secrets || {};
  if (rows) {
    const rendered = new Set([...Object.keys(CARD_GROUPS), CONNECTION_GROUP]);
    const leftovers = allFields().filter((field) => !rendered.has(field.group));
    const envFields = allFields().filter((field) => field.source === "env");
    const entries = [
      row("受管配置文件", `${config.path || "—"}（${config.exists ? "已存在" : "尚未创建"}）`),
      row(
        "env 覆盖字段",
        envFields.length ? envFields.map((field) => `${field.path}（${field.env_var}）`).join("、") : "无",
      ),
      row(
        "密钥掩码视图",
        (secrets.secrets || [])
          .map((entry) => `${entry.field}：${entry.configured ? `${entry.mask || ""} · ${entry.origin || ""}` : "未设置"}`)
          .join("；") || "—",
      ),
      ...leftovers.map((field) => row(field.label, `${field.value} · ${field.source}`)),
    ];
    rows.replaceChildren(...entries);
  }
  const raw = el("snapshotRaw");
  if (raw) {
    raw.textContent = JSON.stringify(
      { settings: config.settings || {}, secrets: secrets.secrets || [] },
      null,
      2,
    );
  }
}

// -- 装配 --------------------------------------------------------------------

function applyDirtyToWidgets() {
  state.dirty.forEach((value, path) => {
    applyValueToWidget(path, value);
    const entry = state.widgets.get(path);
    const wrapper = entry && entry.node.closest(".field");
    if (wrapper) wrapper.classList.add("dirty");
  });
}

function renderFields() {
  renderGroup("collectionFields", "collection");
  renderGroup("servingFields", "serving");
  renderGroup("pathsFields", "paths");
  applyDirtyToWidgets();
}

function renderAll() {
  renderBanner();
  renderFields();
  renderCollection();
  renderStorage();
  renderRoles();
  renderSnapshot();
}

function attachHandlers() {
  document.querySelectorAll("[data-save-card]").forEach((button) => {
    button.addEventListener("click", () => saveCard(button.dataset.saveCard, button));
  });
  attachAllTests();
  const copyButton = el("copyRestart");
  if (copyButton) {
    copyButton.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(RESTART_COMMAND);
        copyButton.textContent = "已复制";
      } catch (error) {
        copyButton.textContent = "请手动复制";
      }
    });
  }
}

async function loadConfig() {
  try {
    const response = await fetch(API.config, { headers: { Accept: "application/json" } });
    if (!response.ok) {
      notice(el("collectionNotice"), `配置读取失败：HTTP ${response.status}`, "bad");
      return;
    }
    hideNotice(el("collectionNotice"));
    state.config = await response.json();
    renderAll();
  } catch (error) {
    notice(el("collectionNotice"), `配置读取失败：${error}`, "bad");
  }
}

async function loadSecrets() {
  try {
    const response = await fetch(API.secrets, { headers: { Accept: "application/json" } });
    if (!response.ok) {
      notice(el("secretsNotice"), `密钥状态读取失败：HTTP ${response.status}`, "bad");
      return;
    }
    state.secrets = await response.json();
    renderRoles();
    renderSnapshot();
  } catch (error) {
    notice(el("secretsNotice"), `密钥状态读取失败：${error}`, "bad");
  }
}

// 预设 / 档位 / 冻结的嵌入端点。接口不可用时角色块照常渲染（只是没有预设），
// 页面不能因为一个可选接口挂掉。
async function loadPresets() {
  try {
    const response = await fetch(API.presets, { headers: { Accept: "application/json" } });
    if (!response.ok) {
      state.presetsError = `HTTP ${response.status}`;
      state.presets = null;
      renderRoles();
      return;
    }
    state.presets = await response.json();
    state.presetsError = null;
    renderRoles();
  } catch (error) {
    state.presetsError = String(error);
    state.presets = null;
    renderRoles();
  }
}

async function loadStatus() {
  try {
    const response = await fetch(API.status, { headers: { Accept: "application/json" } });
    if (!response.ok) {
      notice(el("collectionNotice"), `系统状态读取失败：HTTP ${response.status}`, "bad");
      return;
    }
    state.status = await response.json();
    renderCollection();
    renderStorage();
  } catch (error) {
    notice(el("collectionNotice"), `系统状态读取失败：${error}`, "bad");
  }
}

attachHandlers();
renderBanner();
loadStatus();
loadPresets();
loadConfig();
loadSecrets();
