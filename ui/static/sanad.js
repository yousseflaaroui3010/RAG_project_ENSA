/*
  Sanad's only script. Hand-written, vendored nothing, loaded with one
  <script> tag.

  ADR-10 rules out a JavaScript TOOLCHAIN -- no npm, no bundler, no second
  language to maintain -- and CR-02 keeps the interface server-rendered.
  This file does not break either: it is plain ES2020 that the browser
  reads as written, and every feature below is an UPGRADE to something
  that already works without it.

  What still works with scripting off:
    * asking a question          -- the composer is a real <form> POST
    * the loading stage hints    -- <noscript> meta refresh in base.html
    * cancelling                 -- a real <form> POST
    * a sample question          -- a real <form> POST (it asks)
    * opening a passage          -- the card is a real <a> to a real page
    * the light and dark themes  -- prefers-color-scheme

  What only works with scripting on, and is therefore never rendered as a
  dead control: the theme TOGGLE (revealed here), the passage OVERLAY
  (the card link stays a link), and populating the input from a sample
  instead of asking it outright.
*/

(function () {
  "use strict";

  /* ---- Theme toggle (UX spec 3.4) ---------------------------------- */

  var root = document.documentElement;
  var toggle = document.querySelector(".theme-toggle");
  var STORED = "sanad-theme";

  function applyTheme(theme) {
    if (theme === "dark" || theme === "light") {
      root.setAttribute("data-theme", theme);
    } else {
      root.removeAttribute("data-theme");
    }
    if (toggle) {
      var dark = theme === "dark";
      toggle.setAttribute("aria-pressed", dark ? "true" : "false");
      toggle.textContent = dark ? "Light theme" : "Dark theme";
    }
  }

  var stored = null;
  try {
    stored = window.localStorage.getItem(STORED);
  } catch (err) {
    /* Private mode, or site data blocked. The OS preference still
       applies, so there is nothing to recover from. */
  }
  if (stored) {
    applyTheme(stored);
  }

  if (toggle) {
    // Revealed only now: without this script the button would do nothing,
    // and a control that does nothing is worse than an absent one.
    toggle.hidden = false;
    toggle.addEventListener("click", function () {
      var dark = root.getAttribute("data-theme") === "dark";
      var next = dark ? "light" : "dark";
      applyTheme(next);
      try {
        window.localStorage.setItem(STORED, next);
      } catch (err) {
        /* Not persisting is a smaller failure than not switching. */
      }
    });
  }

  /* ---- Workspace selector ------------------------------------------ */

  var select = document.querySelector("[data-autosubmit]");
  if (select) {
    select.addEventListener("change", function () {
      select.form.submit();
    });
    document.querySelectorAll("[data-hide-with-js]").forEach(function (el) {
      el.hidden = true;
    });
  }

  /* ---- Sample questions (UX spec 6.3) ------------------------------ */

  // "each one clickable to populate the input". With scripting off the
  // same button asks the question instead, which is a reasonable second
  // best; here it does what the spec says.
  var input = document.getElementById("question");
  document.querySelectorAll("[data-sample]").forEach(function (button) {
    button.addEventListener("click", function (event) {
      if (!input || input.disabled) {
        return;
      }
      event.preventDefault();
      input.value = button.getAttribute("data-sample");
      input.focus();
    });
  });

  /* ---- Passage viewer (UX spec 5, criterion 4) --------------------- */

  /*
    <dialog>.showModal() is the platform's own focus trap: it holds Tab
    inside the dialog, closes on Escape, and returns focus to the element
    that was focused when it opened. Hand-rolled focus management is where
    accessibility goes to die, so none is written here.
  */
  document.querySelectorAll("[data-passage]").forEach(function (link) {
    var dialog = document.getElementById(link.getAttribute("data-passage"));
    if (!dialog || typeof dialog.showModal !== "function") {
      // No <dialog> support: the link still navigates to the passage page.
      return;
    }
    link.addEventListener("click", function (event) {
      event.preventDefault();
      dialog.showModal();
    });
    dialog.querySelectorAll("[data-close-viewer]").forEach(function (close) {
      close.addEventListener("click", function () {
        dialog.close();
      });
    });
  });

  /* ---- Loading: poll the real stage (UX spec 6.3) ------------------ */

  /*
    THE STAGE IS NEVER GUESSED HERE. This asks the server which port the
    agent is actually inside; it does not run a timer. The React reference
    advances its own stage on setTimeout at 650ms and 1300ms, which is the
    faked progress design principle 3 bans in one sentence.

    Swapping only the conversation area, rather than reloading, is what
    keeps a screen reader from restarting mid-answer -- the <noscript>
    path has to reload and accepts that cost.
  */
  var area = document.querySelector("[data-conversation]");
  if (!area || !document.querySelector("[data-stage]")) {
    return;
  }

  var POLL_MS = 700;

  function tick() {
    fetch("/chat/messages", { headers: { "X-Requested-With": "fetch" } })
      .then(function (response) {
        return response.ok ? response.text() : null;
      })
      .then(function (html) {
        if (html === null) {
          window.setTimeout(tick, POLL_MS);
          return;
        }
        var parsed = new DOMParser().parseFromString(html, "text/html");
        var fresh = parsed.querySelector("[data-conversation]");
        if (!fresh) {
          window.setTimeout(tick, POLL_MS);
          return;
        }
        // ONE request per tick, and the stage label inside it is the
        // server's -- rendered from the port the agent is actually in.
        // Asking a separate status endpoint and then patching the label
        // would put a second copy of the stage on the page, which is the
        // shape where the label says one thing and the panel another.
        area.replaceWith(fresh);
        area = fresh;
        if (fresh.querySelector("[data-stage]")) {
          window.setTimeout(tick, POLL_MS);
          return;
        }
        // The run has settled. Reload rather than stop here, so the
        // composer is re-enabled and the new source cards get their
        // dialogs and their listeners.
        window.location.reload();
      })
      .catch(function () {
        /* A failed poll is not a failed answer: the run continues on the
           server. Try again on the next tick. */
        window.setTimeout(tick, POLL_MS);
      });
  }

  window.setTimeout(tick, POLL_MS);
})();
