/* Shared nav for the admin pages: who am I, how do I leave, and which entries
   the console database gates. */
(function () {
  "use strict";

  const ENTRY_PAGE = "/main";
  const POSTGRES_SIGNAL = "/api/canonical-v2/admin/jobs";
  const GATED_ENTRIES = "[data-requires-postgres]";

  const label = document.getElementById("admin-user");
  const button = document.getElementById("logout-button");
  /* `/main` renders the login form and main.js fills its session box, so the
     identity half stays off the entry page — its quick links still need the gate. */
  const entryPage = window.location.pathname === ENTRY_PAGE;

  /* Hide the entries that need the console database — and only those. Every other
     outcome (offline, signed out, a 302 back to /main, a payload without the flag)
     leaves the entries visible. */
  function gatePostgresEntries() {
    const entries = document.querySelectorAll(GATED_ENTRIES);
    if (!entries.length) return;
    fetch(POSTGRES_SIGNAL, { credentials: "same-origin" })
      .then(function (response) {
        if (!response.ok || response.redirected) return null;
        return response.json().catch(function () {
          return null;
        });
      })
      .then(function (payload) {
        const postgres = payload && payload.postgres;
        if (!postgres || postgres.available !== false) return;
        Array.prototype.forEach.call(entries, function (entry) {
          entry.hidden = true;
        });
      })
      .catch(function () {
        /* a page that cannot read the signal keeps its entries */
      });
  }

  async function load() {
    let response;
    try {
      response = await fetch("/api/auth/me", { credentials: "same-origin" });
    } catch (error) {
      window.location.assign(ENTRY_PAGE);
      return;
    }
    if (!response.ok) {
      window.location.assign(ENTRY_PAGE);
      return;
    }
    const payload = await response.json();
    if (label) label.textContent = payload.username || "";
  }

  if (button && !entryPage) {
    button.addEventListener("click", async function (event) {
      event.preventDefault();
      try {
        await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" });
      } catch (error) {
        /* a failed logout still lands the browser back on the entry page */
      }
      window.location.assign(ENTRY_PAGE);
    });
  }

  if (!entryPage) load();
  gatePostgresEntries();
})();
