/* Shared nav for the six admin pages: who am I, and how do I leave. */
(function () {
  "use strict";

  const label = document.getElementById("admin-user");
  const button = document.getElementById("logout-button");

  async function load() {
    let response;
    try {
      response = await fetch("/api/auth/me", { credentials: "same-origin" });
    } catch (error) {
      window.location.assign("/main");
      return;
    }
    if (!response.ok) {
      window.location.assign("/main");
      return;
    }
    const payload = await response.json();
    if (label) label.textContent = payload.username || "";
  }

  if (button) {
    button.addEventListener("click", async function (event) {
      event.preventDefault();
      try {
        await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" });
      } catch (error) {
        /* a failed logout still lands the browser back on the entry page */
      }
      window.location.assign("/main");
    });
  }

  load();
})();
