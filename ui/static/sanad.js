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

  // S6: the few strings this script can show come from the page's own
  // language (base.html renders them into <script id="sanad-i18n">).
  var uiStrings = {};
  try {
    var stringsBlock = document.getElementById("sanad-i18n");
    uiStrings = JSON.parse((stringsBlock && stringsBlock.textContent) || "{}");
  } catch (err) {
    uiStrings = {};
  }
  function uiString(key, fallback) {
    return typeof uiStrings[key] === "string" ? uiStrings[key] : fallback;
  }
  var toggle = document.querySelector(".theme-toggle");
  var STORED = "sanad-theme";

  var systemDark = window.matchMedia
    ? window.matchMedia("(prefers-color-scheme: dark)")
    : null;

  function isDark() {
    var explicit = root.getAttribute("data-theme");
    if (explicit === "dark" || explicit === "light") {
      return explicit === "dark";
    }
    return Boolean(systemDark && systemDark.matches);
  }

  // The label stays "Dark theme"; aria-pressed says whether it is on, and it
  // starts from what the reader actually sees -- including a dark screen
  // that came from the operating system rather than from this button.
  function syncToggle() {
    if (toggle) {
      toggle.setAttribute("aria-pressed", isDark() ? "true" : "false");
    }
  }

  function applyTheme(theme) {
    if (theme === "dark" || theme === "light") {
      root.setAttribute("data-theme", theme);
    } else {
      root.removeAttribute("data-theme");
    }
    syncToggle();
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
  } else {
    syncToggle();
  }
  if (systemDark && systemDark.addEventListener) {
    systemDark.addEventListener("change", syncToggle);
  }

  if (toggle) {
    // Revealed only now: without this script the button would do nothing,
    // and a control that does nothing is worse than an absent one.
    toggle.hidden = false;
    toggle.addEventListener("click", function () {
      var next = isDark() ? "light" : "dark";
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

  /* ---- Destructive confirmation (UX spec 7.4) ---------------------- */

  var deleteTrigger = document.querySelector("[data-delete-trigger]");
  if (
    deleteTrigger &&
    new URLSearchParams(window.location.search).get("focus") === "delete"
  ) {
    var deleteSettings = deleteTrigger.closest("details");
    if (deleteSettings) {
      deleteSettings.open = true;
    }
    deleteTrigger.focus();
  }

  var confirmDialog = document.querySelector("[data-confirm-dialog]");
  if (confirmDialog && typeof confirmDialog.showModal === "function") {
    var returnUrl = confirmDialog.getAttribute("data-return-url");
    // `open` keeps the no-script path visible. Reopen modally so the
    // browser, rather than custom key handling, owns the focus trap.
    confirmDialog.close();
    confirmDialog.showModal();
    confirmDialog.addEventListener("cancel", function (event) {
      event.preventDefault();
      window.location.assign(returnUrl);
    });
  }

  /* ---- Answer feedback, compact (F-15) ---------------------------- */

  /*
    With scripting off every feedback form shows its comment box, which is
    the complete no-script path. Here the box waits until "Not helpful" is
    pressed once: that first press opens it and moves focus into it, and the
    next press sends.
  */
  function wireFeedback(scope) {
    scope.querySelectorAll("[data-feedback]").forEach(function (block) {
      if (block.hasAttribute("data-feedback-wired")) {
        return;
      }
      block.setAttribute("data-feedback-wired", "");
      var downForm = block.querySelector(".feedback__form--down");
      var textarea = downForm && downForm.querySelector("textarea");
      var submit = downForm && downForm.querySelector("button[type=submit]");
      if (!downForm || !textarea || !submit) {
        return;
      }
      block.classList.add("is-compact");
      submit.addEventListener("click", function (event) {
        if (block.classList.contains("is-compact")) {
          event.preventDefault();
          block.classList.remove("is-compact");
          block.classList.add("is-commenting");
          textarea.focus();
        }
      });
    });
  }
  wireFeedback(document);

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

  /* ---- S3 evaluation progress: poll committed question counts ------- */

  var reportBlock = document.querySelector("[data-report-refresh]");
  if (reportBlock) {
    var REPORT_POLL_MS = 2000;

    function reportTick() {
      fetch(window.location.pathname, {
        headers: { "X-Requested-With": "fetch" }
      })
        .then(function (response) {
          return response.ok ? response.text() : null;
        })
        .then(function (html) {
          if (html === null) {
            window.setTimeout(reportTick, REPORT_POLL_MS);
            return;
          }
          var fresh = new DOMParser().parseFromString(html, "text/html");
          var freshBlock = fresh.querySelector("[aria-label='Evaluation reports'], [aria-label='Report detail']");
          if (!freshBlock) {
            window.setTimeout(reportTick, REPORT_POLL_MS);
            return;
          }
          reportBlock.querySelectorAll("[data-eval-status]").forEach(function (live) {
            var id = live.getAttribute("data-eval-status");
            var next = freshBlock.querySelector('[data-eval-status="' + id + '"]');
            var liveLabel = live.querySelector("[data-status-label]");
            var nextLabel = next && next.querySelector("[data-status-label]");
            if (liveLabel && nextLabel && liveLabel.textContent.trim() !== nextLabel.textContent.trim()) {
              liveLabel.textContent = nextLabel.textContent.trim();
            }
            var liveDot = live.querySelector(".status-dot");
            var nextDot = next && next.querySelector(".status-dot");
            if (liveDot && nextDot) {
              liveDot.className = nextDot.className;
            }
            if (liveLabel && !nextLabel && !freshBlock.hasAttribute("data-report-refresh")) {
              liveLabel.textContent = freshBlock.getAttribute("data-report-final-status") || uiString("reports.status.finished_sentence", "Evaluation finished.");
            }
          });
          reportBlock.querySelectorAll("[data-report-value]").forEach(function (live) {
            var key = live.getAttribute("data-report-value");
            var next = freshBlock.querySelector('[data-report-value="' + key + '"]');
            if (next) {
              live.textContent = next.textContent.trim();
            }
          });
          ["[data-report-scores]", "[data-report-questions]"].forEach(function (selector) {
            var liveBody = reportBlock.querySelector(selector + " tbody");
            var nextBody = freshBlock.querySelector(selector + " tbody");
            if (liveBody && nextBody) {
              liveBody.replaceWith(document.importNode(nextBody, true));
            }
          });
          if (!freshBlock.hasAttribute("data-report-refresh")) {
            var focused = reportBlock.contains(document.activeElement)
              ? document.activeElement.closest("[data-report-focus]")
              : null;
            var focusKey = focused && focused.getAttribute("data-report-focus");
            window.setTimeout(function () {
              var replacement = document.importNode(freshBlock, true);
              reportBlock.replaceWith(replacement);
              if (focusKey) {
                var returnTarget = replacement.querySelector(
                  '[data-report-focus="' + focusKey + '"]'
                );
                if (returnTarget) {
                  returnTarget.focus();
                }
              }
            }, 700);
            return;
          }
          window.setTimeout(reportTick, REPORT_POLL_MS);
        })
        .catch(function () {
          window.setTimeout(reportTick, REPORT_POLL_MS);
        });
    }
    window.setTimeout(reportTick, REPORT_POLL_MS);
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
  // S6: while the model is writing, check more often so the text arrives
  // in small steps rather than in 700ms lumps.
  var WRITING_POLL_MS = 300;

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
      wireFeedback(node);
    });

    // The run is over: drop the stage block and the draft answer (the
    // finished one was just appended above), put the composer back.
    stageBlock.remove();
    var draft = document.querySelector("[data-streaming]");
    if (draft) {
      draft.remove();
    }
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

  function paintSteps(key) {
    var steps = stageBlock.querySelectorAll("[data-step]");
    var current = -1;
    steps.forEach(function (step, index) {
      if (step.getAttribute("data-step") === key) {
        current = index;
      }
    });
    if (current < 0) {
      return;
    }
    stageBlock.setAttribute("data-stage-key", key);
    steps.forEach(function (step, index) {
      step.classList.toggle("is-done", index < current);
      step.classList.toggle("is-current", index === current);
    });
  }

  /*
    S6: the answer as the model writes it. The server renders it (escaped,
    formatted) exactly as it renders a finished answer; this only moves
    that markup into the page. Inserted just above the stage block, and
    kept out of the transcript's live region so words are not announced
    one poll at a time.
  */
  function showDraft(freshDraft) {
    if (!freshDraft) {
      return;
    }
    var live = document.querySelector("[data-streaming]");
    if (!live) {
      stageBlock.parentNode.insertBefore(document.importNode(freshDraft, true), stageBlock);
      return;
    }
    var liveText = live.querySelector("[data-streaming-text]");
    var freshText = freshDraft.querySelector("[data-streaming-text]");
    if (liveText && freshText && liveText.innerHTML !== freshText.innerHTML) {
      liveText.replaceWith(document.importNode(freshText, true));
    }
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
        // S6: move the step rail to the stage the server just reported.
        // Classes only, same as the label: the node is never replaced.
        var freshStage = fresh.querySelector("[data-stage]");
        var stageKey = freshStage && freshStage.getAttribute("data-stage-key");
        paintSteps(stageKey);
        showDraft(fresh.querySelector("[data-streaming]"));
        window.setTimeout(tick, stageKey === "writing" ? WRITING_POLL_MS : POLL_MS);
      })
      .catch(function () {
        /* A failed poll is not a failed answer: the run continues on the
           server. Try again on the next tick. */
        window.setTimeout(tick, POLL_MS);
      });
  }

  window.setTimeout(tick, POLL_MS);
})();
