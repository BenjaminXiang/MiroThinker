/* The console entry page: login, dashboard, account area. */
(function () {
  "use strict";

  const USERNAME = document.body.getAttribute("data-admin-user") || "";
  const ROLE = document.body.getAttribute("data-admin-role") || "";
  const notice = document.getElementById("notice");

  function showNotice(message, kind) {
    if (!notice) return;
    notice.textContent = message;
    notice.className = "notice" + (kind ? " " + kind : "");
  }

  function hideNotice() {
    if (notice) notice.className = "notice hidden";
  }

  async function call(path, options) {
    const response = await fetch(path, Object.assign({ credentials: "same-origin" }, options || {}));
    let payload = null;
    try {
      payload = await response.json();
    } catch (error) {
      payload = null;
    }
    return { status: response.status, ok: response.ok, payload: payload };
  }

  function messageOf(result, fallback) {
    const detail = result.payload && result.payload.detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object" && detail.error === "locked") {
      return "口令错误次数过多，请在 " + detail.retry_after_seconds + " 秒后重试";
    }
    return fallback;
  }

  function clearSecretFields() {
    ["login-password", "password-current", "password-new"].forEach(function (id) {
      const field = document.getElementById(id);
      if (field) field.value = "";
    });
  }

  const server = {
    login: function (username, password) {
      return call("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: username, password: password }),
      });
    },
    logout: function () {
      return call("/api/auth/logout", { method: "POST" });
    },
    me: function () {
      return call("/api/auth/me");
    },
    changePassword: function (currentPassword, newPassword) {
      return call("/api/auth/password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      });
    },
    accounts: function () {
      return call("/api/auth/accounts");
    },
    createAccount: function (username) {
      return call("/api/auth/accounts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: username }),
      });
    },
    deleteAccount: function (username) {
      return call("/api/auth/accounts/" + encodeURIComponent(username), { method: "DELETE" });
    },
    resetAccountPassword: function (username) {
      return call("/api/auth/accounts/" + encodeURIComponent(username) + "/password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
    },
    status: function () {
      return call("/api/canonical-v2/admin/system-status");
    },
  };

  function tile(label, value) {
    const wrapper = document.createElement("div");
    wrapper.className = "tile";
    const name = document.createElement("span");
    name.className = "tile-label";
    name.textContent = label;
    const content = document.createElement("span");
    content.className = "tile-value";
    content.textContent = String(value);
    wrapper.appendChild(name);
    wrapper.appendChild(content);
    return wrapper;
  }

  function renderStatus(payload) {
    const tiles = document.getElementById("status-tiles");
    const generated = document.getElementById("status-generated");
    if (!tiles) return;
    tiles.textContent = "";
    if (!payload || typeof payload !== "object") {
      if (generated) generated.textContent = "系统状态暂不可用";
      return;
    }
    if (generated && payload.generated_at) generated.textContent = "生成于 " + payload.generated_at;
    let rendered = 0;
    Object.keys(payload).forEach(function (key) {
      const value = payload[key];
      if (value === null || value === undefined) return;
      if (typeof value === "object") {
        const entries = Array.isArray(value) ? value.length : Object.keys(value).length;
        tiles.appendChild(tile(key, entries + (Array.isArray(value) ? " 项" : " 个字段")));
      } else {
        tiles.appendChild(tile(key, value));
      }
      rendered += 1;
    });
    if (!rendered && generated) generated.textContent = "系统状态为空";
  }

  async function loadStatus() {
    const result = await server.status();
    if (result.status === 401) {
      window.location.reload();
      return;
    }
    renderStatus(result.payload);
  }

  function accountRow(account) {
    const row = document.createElement("li");
    const name = document.createElement("span");
    name.textContent = account.username + "（" + account.role + "）";
    const actions = document.createElement("span");
    const reset = document.createElement("button");
    reset.type = "button";
    reset.textContent = "重置口令";
    reset.addEventListener("click", async function () {
      const result = await server.resetAccountPassword(account.username);
      if (!result.ok) {
        showNotice(messageOf(result, "重置失败"), "error");
        return;
      }
      showNotice(
        "已重置 " + account.username + " 的口令：" + (result.payload.password || "（已按提交值更新）"),
        "success"
      );
      clearSecretFields();
    });
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "danger";
    remove.textContent = "删除";
    remove.addEventListener("click", async function () {
      const result = await server.deleteAccount(account.username);
      if (!result.ok) {
        showNotice(messageOf(result, "删除失败"), "error");
        return;
      }
      showNotice("已删除 " + account.username, "success");
      await loadAccounts();
    });
    actions.appendChild(reset);
    actions.appendChild(remove);
    row.appendChild(name);
    row.appendChild(actions);
    return row;
  }

  async function loadAccounts() {
    const list = document.getElementById("account-list");
    if (!list) return;
    const result = await server.accounts();
    if (!result.ok) {
      showNotice(messageOf(result, "账号列表不可用"), "error");
      return;
    }
    list.textContent = "";
    (result.payload.accounts || []).forEach(function (account) {
      list.appendChild(accountRow(account));
    });
  }

  function wireLogin() {
    const form = document.getElementById("login-submit");
    if (!form) return;
    form.addEventListener("submit", async function (event) {
      event.preventDefault();
      hideNotice();
      const username = document.getElementById("login-username").value.trim();
      const password = document.getElementById("login-password").value;
      const result = await server.login(username, password);
      clearSecretFields();
      if (!result.ok) {
        showNotice(messageOf(result, "登录失败"), "error");
        return;
      }
      window.location.assign("/main");
    });
  }

  function wireLogout() {
    const button = document.getElementById("logout-button");
    if (!button) return;
    button.addEventListener("click", async function () {
      await server.logout();
      window.location.assign("/main");
    });
  }

  function wireAccountArea() {
    const create = document.getElementById("account-create");
    if (create) {
      create.addEventListener("submit", async function (event) {
        event.preventDefault();
        hideNotice();
        const field = document.getElementById("account-new-username");
        const username = field.value.trim();
        const result = await server.createAccount(username);
        const output = document.getElementById("account-create-result");
        if (!result.ok) {
          showNotice(messageOf(result, "创建失败"), "error");
          return;
        }
        field.value = "";
        if (output) {
          output.textContent = result.payload.password
            ? "新账号 " + username + " 的初始口令（仅显示一次）：" + result.payload.password
            : "已创建 " + username;
        }
        await loadAccounts();
      });
    }
    const change = document.getElementById("password-change");
    if (change) {
      change.addEventListener("submit", async function (event) {
        event.preventDefault();
        hideNotice();
        const current = document.getElementById("password-current").value;
        const replacement = document.getElementById("password-new").value;
        const result = await server.changePassword(current, replacement);
        clearSecretFields();
        showNotice(
          result.ok ? "口令已更新，其它会话已失效" : messageOf(result, "修改失败"),
          result.ok ? "success" : "error"
        );
      });
    }
  }

  async function boot() {
    wireLogin();
    wireLogout();
    if (!USERNAME) {
      hideNotice();
      return;
    }
    wireAccountArea();
    const me = await server.me();
    if (!me.ok) {
      window.location.assign("/main");
      return;
    }
    const label = document.getElementById("admin-user");
    if (label) label.textContent = me.payload.username + "（" + (me.payload.role || ROLE) + "）";
    await loadStatus();
    await loadAccounts();
  }

  boot();
})();
