/* 管理配置中心（Canonical V2）：配置 · 展示 · 验证同卡。
 *
 * 渲染完全是服务端 payload 的函数：
 *   - /config 的 fields（含 label/kind/group/order/bounds/consumer/default/connection/test_arg）
 *     决定卡片 1-3 的字段与各连接卡里的端点/模型字段；
 *   - /secrets 的 connections 与 secrets 决定连接卡的运行期状态、密钥来源与掩码；
 *   - /system-status 提供各域新鲜度、库计数/体积与磁盘余量。
 * 页面不持有任何字段白名单：目录加一行，字段即出现。
 *
 * 保存只提交脏字段（默认 = 显式 null，清除 override）；密钥明文只写不读，
 * 既不回显也不写日志。保存后需重启服务生效（服务启动时读取受管文件）。
 */
"use strict";

const API = {
  status: "api/canonical-v2/admin/system-status",
  config: "api/canonical-v2/admin/config",
  secrets: "api/canonical-v2/admin/secrets",
  connectionTest: "api/canonical-v2/admin/connections/test",
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
  if (typeof valueNode === "string") cell.textContent = valueNode;
  else cell.append(valueNode);
  wrapper.append(cell);
  return wrapper;
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
  input.dataset.path = field.path;
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
  container.replaceChildren(...fieldsOfGroup(group).map(renderField));
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

// -- 卡片 2：检索与回答 ------------------------------------------------------

function connectionByKind(kind) {
  const connections = (state.secrets && state.secrets.connections) || [];
  return connections.find((connection) => connection.kind === kind) || null;
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

function renderServing() {
  const rerank = connectionByKind("rerank");
  const badge = el("rerankRuntime");
  if (badge) badge.replaceChildren(runtimeBadge(rerank));
  const note = el("rerankRuntimeNote");
  if (note) note.textContent = rerank ? (rerank.runtime || {}).runtime_note || "" : "服务端未返回 rerank 连接";
  const button = el("testRerank");
  if (button) button.disabled = !rerank;
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

// -- 卡片 4：连接与密钥 ------------------------------------------------------

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

function renderConnections() {
  const container = el("connectionCards");
  if (!container) return;
  if (!state.secrets) {
    container.textContent = "等待密钥状态…";
    return;
  }
  const path = el("secretsPath");
  if (path) path.textContent = `${state.secrets.path}（${state.secrets.exists ? "已存在" : "尚未创建"}）`;
  if (state.secrets.permissions_ok === false) {
    notice(el("secretsNotice"), "警告：受管密钥文件权限不是 0600，请检查（页面不会回显其内容）", "bad");
  } else {
    hideNotice(el("secretsNotice"));
  }
  container.replaceChildren(...((state.secrets.connections || []).map(renderConnectionCard)));
  applyDirtyToWidgets();
  if (state.keys.size) renderBanner();
}

function renderConnectionCard(connection) {
  const card = document.createElement("section");
  card.className = "connection";
  card.dataset.connection = connection.key;

  const header = document.createElement("header");
  header.append(text("h3", "", connection.label || connection.key), runtimeBadge(connection));
  card.append(header);
  card.append(text("p", "meta", (connection.runtime || {}).runtime_note || ""));

  const entry = secretFor(connection.key);
  const keyRow = document.createElement("div");
  keyRow.className = "keyrow";
  keyRow.append(pill(keyStatusText(entry), entry && entry.configured ? "ok" : ""));
  const keyInput = document.createElement("input");
  keyInput.type = "password";
  keyInput.autocomplete = "new-password";
  keyInput.placeholder = "新密钥（留空 = 不改动；明文既不回显也不入日志）";
  keyInput.dataset.secretInput = connection.key;
  keyInput.addEventListener("input", () => {
    const value = keyInput.value.trim();
    if (value) state.keys.set(connection.key, value);
    else state.keys.delete(connection.key);
    renderBanner();
  });
  const clearButton = document.createElement("button");
  clearButton.type = "button";
  clearButton.textContent = "清除密钥";
  clearButton.dataset.clearSecret = connection.key;
  clearButton.addEventListener("click", () => clearSecret(connection.key));
  keyRow.append(keyInput, clearButton);
  card.append(keyRow);

  const endpointFields = fieldsOfConnection(connection.key);
  if (endpointFields.length) {
    card.append(...endpointFields.map(renderField));
  } else {
    card.append(
      text(
        "p",
        "meta",
        connection.runtime && connection.runtime.base_url
          ? `端点由运行期固定：${connection.runtime.base_url}`
          : "端点由运行期/发布物固定，不可在此改写",
      ),
    );
  }

  const actions = document.createElement("div");
  actions.className = "actions";
  const testButton = document.createElement("button");
  testButton.type = "button";
  testButton.textContent = "测试连通性";
  testButton.id = `test-${connection.key}`;
  testButton.dataset.testConnection = connection.key;
  const result = text("span", "result", "未测试");
  result.dataset.connectionResult = connection.key;
  testButton.addEventListener("click", () => testConnection(connection.key, testButton, result));
  const saveButton = document.createElement("button");
  saveButton.type = "button";
  saveButton.className = "primary";
  saveButton.textContent = "保存本卡";
  saveButton.id = `save-${connection.key}`;
  saveButton.dataset.saveConnection = connection.key;
  saveButton.addEventListener("click", () => saveConnection(connection.key, saveButton));
  actions.append(testButton, saveButton, result);
  card.append(actions);
  return card;
}

function connectionTestBody(connectionKey) {
  const body = { connection: connectionKey };
  const pending = (state.keys.get(connectionKey) || "").trim();
  if (pending) body.api_key = pending;
  fieldsOfConnection(connectionKey).forEach((field) => {
    if (!field.test_arg) return;
    const value = patchValueOf(field.path);
    if (typeof value === "string" && value) body[field.test_arg] = value;
  });
  return body;
}

async function testConnection(connectionKey, button, resultNode) {
  const node = resultNode || document.querySelector(`[data-connection-result="${connectionKey}"]`);
  button.disabled = true;
  if (node) node.textContent = "测试中…（一次最小调用）";
  try {
    const response = await fetch(API.connectionTest, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(connectionTestBody(connectionKey)),
    });
    const payload = await response.json();
    if (!node) return;
    if (response.status === 429) {
      const detail = payload.detail || {};
      node.textContent = `限频：请 ${detail.retry_after_seconds || "稍后"} 秒后再试（服务端已拦截，未发起调用）`;
      return;
    }
    if (!response.ok) {
      node.textContent = `测试被拒绝（HTTP ${response.status}）：${describeDetail(payload.detail)}`;
      return;
    }
    const remaining = (payload.rate || {}).remaining;
    node.textContent = [
      payload.ok ? "成功" : "失败",
      payload.called === false ? "（未发起调用）" : "",
      `· ${payload.latency_ms} ms`,
      payload.http_status === null || payload.http_status === undefined ? "" : `· HTTP ${payload.http_status}`,
      `· ${payload.detail}`,
      `· 凭据来源 ${(payload.used || {}).api_key_source || "—"}`,
      (payload.runtime || {}).enabled === false ? "· 运行期未启用" : "",
      remaining === null || remaining === undefined ? "" : `· 本分钟剩余 ${remaining} 次`,
    ]
      .filter(Boolean)
      .join(" ");
  } catch (error) {
    if (node) node.textContent = `测试失败：${error}`;
  } finally {
    button.disabled = false;
  }
}

async function saveConnection(connectionKey, button) {
  const messages = [];
  button.disabled = true;
  try {
    const pending = (state.keys.get(connectionKey) || "").trim();
    const entry = secretFor(connectionKey);
    if (pending && entry) {
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
    const paths = dirtyPathsFor((field) => field.connection === connectionKey);
    if (paths.length) {
      const changed = await saveConfig(paths);
      messages.push(`端点/模型已保存 ${changed.join("、")}`);
    }
    if (!messages.length) messages.push("没有改动（密钥留空、端点/模型未修改）");
    const restart = state.needsRestart ? `。${RESTART_COMMAND} 后生效` : "";
    renderAll();
    const node = document.querySelector(`[data-connection-result="${connectionKey}"]`);
    if (node) node.textContent = `${messages.join("；")}${restart}`;
  } catch (error) {
    const node = document.querySelector(`[data-connection-result="${connectionKey}"]`);
    if (node) node.textContent = String(error.message || error);
  } finally {
    button.disabled = false;
  }
}

async function clearSecret(connectionKey) {
  const entry = secretFor(connectionKey);
  if (!entry) return;
  if (!window.confirm(`${entry.label}：确认清除受管文件中的密钥？（清除后需重启服务生效）`)) return;
  const node = document.querySelector(`[data-connection-result="${connectionKey}"]`);
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
    const fresh = document.querySelector(`[data-connection-result="${connectionKey}"]`);
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
  renderConnections();
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
  renderServing();
  renderConnections();
  renderSnapshot();
}

function attachHandlers() {
  document.querySelectorAll("[data-save-card]").forEach((button) => {
    button.addEventListener("click", () => saveCard(button.dataset.saveCard, button));
  });
  const rerankButton = el("testRerank");
  if (rerankButton) {
    rerankButton.addEventListener("click", () => {
      const connection = connectionByKind("rerank");
      if (connection) testConnection(connection.key, rerankButton, el("rerankTestResult"));
    });
  }
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
    renderServing();
    renderConnections();
    renderSnapshot();
  } catch (error) {
    notice(el("secretsNotice"), `密钥状态读取失败：${error}`, "bad");
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
loadConfig();
loadSecrets();
