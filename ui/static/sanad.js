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
  function wireSamples(root) {
    root.querySelectorAll("[data-sample]").forEach(function (button) {
      button.addEventListener("click", function (event) {
        if (!input || input.disabled) {
          return;
        }
        event.preventDefault();
        input.value = button.getAttribute("data-sample");
        input.focus();
      });
    });
  }
  wireSamples(document);

  /* ---- Passage viewer (UX spec 5, criterion 4) --------------------- */

  /*
    <dialog>.showModal() is the platform's own focus trap: it holds Tab
    inside the dialog, closes on Escape, and returns focus to the element
    that was focused when it opened. Hand-rolled focus management is where
    accessibility goes to die, so none is written here.

    A function rather than a one-off loop, because new source cards arrive
    with an answer and are appended without a page load (see the poll
    below). Anything wired only at first load would leave those cards as
    plain links to the passage page -- still usable, but not the overlay.
  */
  function wirePassages(root) {
    root.querySelectorAll("[data-passage]").forEach(function (link) {
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
  }
  wirePassages(document);

  /* ---- S2 Sync progress: poll the real count (UX spec 7.2, 7.4) ----- */

  /*
    Placed BEFORE the S1-only early return just below (this file is
    loaded on every screen, and /workspaces has no `[data-stage]` /
    `[data-transcript]` for that guard to find). Same idiom as the chat
    poll further down, and the same reason it exists: the <noscript>
    meta-refresh in base.html already keeps a no-JS page true every 2
    seconds, so this only has to stop the SAME page reloading out from
    under the reader. "Progress is announced at meaningful intervals
    rather than on every tick" (7.4) is why this polls every 2000ms rather
    than chat's 700ms -- a file count changes far less often than a token
    stream, and re-announcing an unchanged number would be noise.
  */
  var syncBlock = document.querySelector("[data-sync-progress]");
  if (syncBlock) {
    var workspaceId = syncBlock.getAttribute("data-workspace-id");
    var SYNC_POLL_MS = 2000;

    function syncTick() {
      fetch(
        "/workspaces/panel?ws=" + encodeURIComponent(workspaceId || ""),
        { headers: { "X-Requested-With": "fetch" } }
      )
        .then(function (response) {
          return response.ok ? response.text() : null;
        })
        .then(function (html) {
          if (html === null) {
            window.setTimeout(syncTick, SYNC_POLL_MS);
            return;
          }
          var fresh = new DOMParser().parseFromString(html, "text/html");
          var freshProgress = fresh.querySelector("[data-sync-progress]");
          if (!freshProgress) {
            // The run finished: the report (or an error panel) replaced
            // it server-side. Swap the whole detail region in once,
            // rather than diffing a shape that has now changed under us.
            var freshDetail = fresh.querySelector(".ws-detail");
            var liveDetail = document.querySelector(".ws-detail");
            if (freshDetail && liveDetail) {
              liveDetail.replaceWith(document.importNode(freshDetail, true));
            } else {
              window.location.reload();
            }
            return;
          }
          var freshLabel = freshProgress.querySelector(".stage__label");
          var label = syncBlock.querySelector(".stage__label");
          if (
            label &&
            freshLabel &&
            label.textContent.trim() !== freshLabel.textContent.trim()
          ) {
            label.textContent = freshLabel.textContent.trim();
          }
          window.setTimeout(syncTick, SYNC_POLL_MS);
        })
        .catch(function () {
          // A failed poll is not a failed Sync: the run continues on the
          // server regardless of whether this tab heard back.
          window.setTimeout(syncTick, SYNC_POLL_MS);
        });
    }
    window.setTimeout(syncTick, SYNC_POLL_MS);
  }

  /* ---- Loading: poll the real stage (UX spec 6.3) ------------------ */

  /*
    THE STAGE IS NEVER GUESSED HERE. This asks the server which port the
    agent is actually inside; it does not run a timer. The React reference
    advances its own stage on setTimeout at 650ms and 1300ms, which is the
    faked progress design principle 3 bans in one sentence.
  */
  var stageBlock = document.querySelector("[data-stage]");
  var transcript = document.querySelector("[data-transcript]");
  if (!stageBlock || !transcript) {
    return;
  }

  var POLL_MS = 700;

  /*
    WHY THE FINISHED ANSWER IS APPENDED RATHER THAN RELOADED, and it is an
    accessibility requirement rather than a nicety. UX spec 6.4: "New
    messages are announced through a polite live region." A live region
    only announces content INSERTED into a node the screen reader is
    already watching -- content that is simply present when a document
    loads is never announced. So `location.reload()`, which is what this
    file used to do when a run settled, left `aria-live` on the transcript
    doing nothing at all: correct markup, zero announcements.

    A cold review caught that the test could not tell the difference
    either: `assert 'role="status"' in page` passes on an attribute that
    never fires.

    The <noscript> path still reloads and still cannot announce. That cost
    is real, is accepted, and is written down in the build journal.
  */
  function absorb(fresh) {
    var freshList = fresh.querySelector("[data-transcript]");
    if (!freshList) {
      window.location.reload();
      return;
    }
    // Append only what is new, into the LIVE list that already exists.
    var existing = transcript.children.length;
    var added = Array.prototype.slice.call(freshList.children, existing);
    added.forEach(function (node) {
      transcript.appendChild(document.importNode(node, true));
      wirePassages(node);
    });

    // The run is over: drop the stage block, put the composer back.
    stageBlock.remove();
    var reason = document.getElementById("composer-reason");
    if (reason) {
      reason.remove();
    }
    if (input) {
      input.disabled = false;
      input.removeAttribute("aria-describedby");
    }
    document.querySelectorAll(".composer button[disabled]").forEach(function (b) {
      b.disabled = false;
    });
    wireSamples(document);
  }

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
        var fresh = new DOMParser().parseFromString(html, "text/html");
        var freshLabel = fresh.querySelector("[data-stage] .stage__label");
        if (!freshLabel) {
          absorb(fresh);
          return;
        }
        /*
          ONLY THE LABEL'S TEXT IS UPDATED while the run is in flight, and
          the element is never replaced: `[data-stage]` carries
          role="status" aria-live="polite", and swapping the node out each
          tick would stop it announcing for the same reason as above.
          The text is the server's, rendered from the port the agent is
          actually inside. Never computed here.
        */
        var label = stageBlock.querySelector(".stage__label");
        var next = freshLabel.textContent.trim();
        if (label && label.textContent.trim() !== next) {
          label.textContent = next;
        }
        window.setTimeout(tick, POLL_MS);
      })
      .catch(function () {
        /* A failed poll is not a failed answer: the run continues on the
           server. Try again on the next tick. */
        window.setTimeout(tick, POLL_MS);
      });
  }

  window.setTimeout(tick, POLL_MS);
})();
