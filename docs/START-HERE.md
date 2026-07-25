# Sanad — Start Here (Team Handbook, Sprints 0 → 1)

A friendly, click-by-click guide for **both of you**. No prior experience assumed.
By the end you'll have Sanad running on your laptop and be building its first
real features together.

**What Sanad is (one picture):** an *honest librarian*. You hand it a folder of
documents. It reads them. When you ask a question, it answers **only** from those
documents and always shows you the exact page it used. If the answer isn't in
the folder, it says "I don't have that" instead of making something up.

> Throughout: 🖱️ = what to click, ⌨️ = what to type, 📍 = where to find it.

---

## ⚠️ Before you begin — the 3 things that trip EVERYONE up

1. **Type commands *inside the project folder*.** Every `uv` and `git` command
   only works if your terminal is "standing inside" the `RAG_project_ENSA`
   folder. The easiest way: open the project in VS Code and use **its** terminal
   (Terminal → New Terminal) — it's always in the right place. 🧠 Like needing to
   be *in the kitchen* to use the oven.
2. **When GitHub asks you to sign in, do it.** The first time you download or
   upload code, a **browser window pops up** asking you to log into GitHub. Log
   in with your GitHub account (YL with yours, MB with hers). This is normal and
   happens once per laptop.
3. **After installing a new tool, close and reopen the terminal.** New tools only
   "wake up" in a fresh terminal window. If a command says "not recognized,"
   that's almost always the fix.

---

## 0. Who does what (you are BOTH coders now)

- **YL — "Engine builder":** owns the parts that **store and search** documents.
- **MB — "Reader builder":** owns the parts that **read and cut up** documents,
  plus the quality checks. (Before, MB only tested; now MB also writes code.)
- **The golden rule:** *one person = one task = one branch.* Think of two people
  editing **different chapters** of the same book — you never type over each
  other's work.
- **You still pair up:** whoever *doesn't* own a task is the one who **reviews**
  it before it's merged. Four eyes, always.

---

## 1. Get your computer ready (do ONCE, on BOTH laptops)

Install these tools. For each: what it is → how to get it → how to check it.

- **Git** — the "save history / time machine" for code.
  - 🖱️ Download from **git-scm.com** → run installer → click **Next** on every
    screen (defaults are fine).
  - ✅ Check: open **PowerShell** (Windows key → type "PowerShell" → Enter),
    ⌨️ `git --version` → you should see a version number.
- **Tell Git who you are (once, so your saves are signed):**
  - ⌨️ `git config --global user.name "Your Name"`
  - ⌨️ `git config --global user.email "your-github-email@example.com"`
  - (Use the same email as your GitHub account.)
- **uv** — installs everything the project needs (like a butler fetching all the
  ingredients). *(Your Python version doesn't matter, even 3.11 — uv brings its
  own Python 3.12 just for the project.)*
  - ⌨️ In PowerShell: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
  - 🔁 **Fully close and reopen the terminal** (and VS Code), then check:
    ⌨️ `uv --version` → should print a version. New tools only "wake up" in a
    fresh window.
  - 🩹 **If it still says `uv` is "not recognized":**
    - First test in a **Start-menu PowerShell** (not VS Code's terminal):
      ⌨️ `uv --version`. If it works there, just **fully quit and reopen VS Code**.
    - If it fails everywhere, install uv through your Python instead:
      ⌨️ `python -m pip install uv` → reopen the terminal → `uv --version`.
- **VS Code** — the editor where you read and write code (like Word, but for code).
  - 🖱️ Download from **code.visualstudio.com** → install.
  - 🖱️ Open VS Code → left **Extensions** icon (four squares) → search **"Python"**
    (by Microsoft) → **Install**.
- **Ollama** — runs **free AI models on your own computer**, no internet, no key.
  - 🖱️ Download from **ollama.com/download** → install.
  - ⌨️ In PowerShell: `ollama pull mistral` (downloads the free Mistral model —
    a few minutes; like downloading one big movie).
- **GitHub sign-in** — make sure you're both logged in at **github.com** and can
  open **github.com/yousseflaaroui3010/RAG_project_ENSA**. (MB: if you can't see
  it, tell YL — he adds you as a collaborator; then check your email for the
  invite and click **Accept**.)

---

## 2. Get Sanad onto your laptop (ONCE, on BOTH laptops)

- **Pick a home for it first** (so you can find it later):
  - ⌨️ `cd ~/Documents` (this "walks into" your Documents folder).
- **Copy the project down ("clone"):**
  - 📍 On the GitHub repo page, click the green **"< > Code"** button → copy the
    **HTTPS** link.
  - ⌨️ `git clone https://github.com/yousseflaaroui3010/RAG_project_ENSA.git`
  - 🔐 A browser window may pop up → **sign in to GitHub** (see gotcha #2). This
    creates a `RAG_project_ENSA` folder inside Documents.
  - 🧠 Analogy: cloning = downloading your own working copy of the shared folder.
- **Open it in VS Code:**
  - 🖱️ VS Code → **File → Open Folder** → pick the `RAG_project_ENSA` folder.
- **Install everything:**
  - 🖱️ VS Code menu **Terminal → New Terminal** (a command box opens at the bottom,
    already standing inside the project — see gotcha #1).
  - ⌨️ `uv sync` → reads the project's shopping list and installs it all (first
    time is slow — it downloads big AI libraries; grab a coffee ☕).
- **Confirm it's healthy:**
  - ⌨️ `uv run pytest -q` → you should see **"2 passed"** in green. That's Sanad's
    heartbeat — if it beats, your setup is good.

---

## 3. Turn on the AI brain (set it up now, used fully in Sprint 2)

Sanad can use a **free local** model or a **free cloud** model. Set up at least one.

- **Make your settings file:**
  - 📍 In VS Code's file list (left), find **`.env.example`**.
  - 🖱️ Right-click it → **Copy**, right-click empty space → **Paste**, then **Rename** the copy to exactly **`.env`** (no `.txt` on the end! If Windows hides file endings, turn on **View → File name extensions** in File Explorer so you can see it's really `.env`).
  - This is your **private** settings file — it's never uploaded to GitHub.
- **To edit it:** 🖱️ click `.env` in VS Code to open it, change the line, then
  **save with ⌨️ Ctrl+S** (unsaved files show a dot • in the tab).
- **Option A — Free & local (recommended to start):**
  - Set the line to ⌨️ `MODEL_MODE=strict_local` (uses your Ollama Mistral —
    works offline, zero cost).
- **Option B — Free & cloud (Gemini):**
  - 🖱️ Go to **aistudio.google.com** → **"Get API key"** → **Create API key** →
    copy it.
  - Set ⌨️ `MODEL_MODE=cloud`, and on the `CLOUD_API_KEY=` line paste your key
    right after the `=`. Save (Ctrl+S).
- **Note:** the chat AI isn't actually called until **Sprint 2**. In Sprint 1 we
  build the reading/searching engine. (The *search* AI — a small model that
  understands French — downloads by itself the first time you Sync.)

---

## 4. The daily rhythm (how EVERY task goes) — memorize this loop

Same seven steps every time. Analogy: a branch is **your own workbench**; a Pull
Request (PR) is **showing your partner before the piece goes in the display case**.

1. **Get the latest:** ⌨️ `git checkout main` then `git pull`.
2. **Start your task on its own branch:** ⌨️ `git checkout -b feat/S1-ST-10-db`
   (the name = the task you're doing).
3. **Do the work.** Either write it, or ask **Claude Code** to build it: in the
   Claude Code chat box (in your terminal or the VS Code panel), type plainly,
   e.g. *"Build ST-10 following the architecture in docs/phase2."* Watch it work.
4. **Test it:** ⌨️ `uv run pytest -q` (tests pass?) and `uv run ruff check .`
   (code tidy?). Both green = good.
5. **Save a checkpoint:** ⌨️ `git add -A` then
   `git commit -m "feat: ST-10 filing cabinet"` (commit = save your game).
6. **Send it up:** ⌨️ `git push`.
7. **Open a PR:** 📍 GitHub shows a yellow **"Compare & pull request"** button →
   click it → **Create pull request** → your **partner reviews** and clicks
   **Approve** → then **Merge pull request**.

- **Where do the task names (ST-10, ST-11 …) come from?** They're the official
  story list in **`docs/build/BUILD-PLAN.md`** — each row says what it is, what it
  needs first, and what "done" looks like.
- **Two unbreakable habits:** never type code directly on `main`; commit every
  time the tests are green (save often, like a video game).

---

## 5. Finish Sprint 0 — get Sanad "alive" (do this together, first)

- **Merge the skeleton that's already built:**
  - 📍 Open the PR: **github.com/yousseflaaroui3010/RAG_project_ENSA/pull/2**.
  - ✅ Wait for the green check (automatic tests) → if a review is required, one of
    you clicks **Files changed → Review changes → Approve** → then 🖱️ **"Merge
    pull request" → "Confirm merge"**. This puts the foundation into `main`.
- **Both of you refresh your copy:** ⌨️ `git checkout main` then `git pull`. Now
  both laptops have the latest.
  - **MB, getting the project the first time:** just do Section 2 (clone) once;
    after that, `git pull` is how you receive everything new.
- **See it in the browser (starter screen):** we'll add a tiny opening screen so
  Sanad literally opens in your browser. Once it's in:
  - ⌨️ `uv run python app.py` → then 🖱️ open **http://127.0.0.1:8000**. (Ask
    Claude Code to add this starter screen — a 5-minute step that makes "the app
    runs!" true today.)

---

## 6. Sprint 1 — Build the document-reading engine (the heart of Sanad)

**The goal in one line:** teach Sanad to take a folder of documents and turn it
into something it can search — so that later it can answer with sources.

Think of an **assembly line**: a raw PDF goes in one end, and out the other end
come tidy, searchable "index cards." Here are the stations. Each shows: **owner**,
a plain explanation, an analogy, and **what "done" looks like**. Start them **top
to bottom** — each one needs the one before it.

- **ST-10 — The filing cabinet (SQLite).** *(Owner: YL)*
  - Stores the *list* of workspaces and documents (not the documents themselves).
  - 🧠 The library's index-card catalog.
  - ✅ Done: tests pass for adding a workspace, and deleting one also cleans up its
    documents (no orphans).
- **ST-11 — Workspaces.** *(Owner: MB)*
  - A **named folder** you point Sanad at, e.g. "HR-Law" or "Manuals" — kept
    totally separate.
  - 🧠 Separate labeled **drawers** — an HR question never pulls from the Manuals
    drawer.
  - ✅ Done: create, rename, delete a workspace; deleting removes its data but
    **never** touches your real files on disk.
- **ST-12 — Change detection (hashing).** *(Owner: YL)*
  - Notices which files are **new, changed, or unchanged**, so it never re-reads
    an unchanged file.
  - 🧠 A **fingerprint** for each file.
  - ✅ Done: tests show new/changed/unchanged/removed each detected correctly.
- **ST-13 — Reading many file types (PDF, Word, Text).** *(Owner: MB)*
  - Turns each document into clean text. Broken or locked files are skipped with a
    reason.
  - 🧠 A **translator** making every document speak the same language.
  - ✅ Done: a test PDF/Word/Text converts; a corrupt file reports "Failed" without
    crashing the rest.
- **ST-14 — Cutting into pieces (chunking).** *(Owner: MB)*
  - Splits long documents into small searchable pieces (with slight overlap so
    ideas aren't cut in half).
  - 🧠 Cutting a long article into **index cards**.
  - ✅ Done: tests confirm the pieces are the right size and overlap.
- **ST-15 — Understanding meaning (embeddings).** *(Owner: YL)*
  - Turns each piece into numbers that capture its **meaning** ("holiday" lands
    near "leave").
  - 🧠 Giving each index card a **GPS coordinate** of what it's about.
  - ⚠️ Rule: every piece gets a `passage:` label and every question a `query:`
    label — a test guards this; never remove it.
  - ✅ Done: the test passes and the small French model downloads once and caches.
- **ST-16 — The search shelf (Qdrant).** *(Owner: YL)*
  - Stores those number-coordinates so similar pieces are found instantly — **one
    shelf per workspace**.
  - 🧠 A **magnetic shelf** where related cards snap together; HR and Manuals get
    separate shelves.
  - ✅ Done: a search in the HR shelf never returns a Manuals card.
- **ST-17 — The Sync button (ties it all together).** *(Owner: YL + MB, pair on it)*
  - Press **Sync** → Sanad scans the folder, runs the whole assembly line, and
    gives a **per-file report** (Added / Changed / Unchanged / Failed / Skipped).
  - 🧠 Pressing **"refresh"** and getting a printed **receipt** for each file.
  - ✅ Done: syncing a test folder shows the right status for every file, and
    pressing Sync twice at once is blocked.

**Running alongside (MB's quality stream — a bit each week):**
- **ST-19 — Golden questions:** write ~15 real HR/labor-law questions *with the
  correct answers and the article they come from*, plus ~8 "trick" questions the
  documents **can't** answer. 📍 Save in `evaluation/golden/`. 🧠 An **exam answer
  key** to grade Sanad against later.
- **ST-20 — Test checklist:** one simple checklist of every "what if it goes wrong"
  case (broken file, empty folder, etc.).

---

## 7. When you get stuck (normal — everyone does)

- **A command turned red?** Copy the red text exactly and ask Claude Code / your
  partner. Red text is a clue, not a disaster.
- **"Command not recognized"?** Close and reopen the terminal (gotcha #3).
- **Lost your place?** ⌨️ `git status` shows your branch and what changed.
- **Afraid you broke something?** You committed often — you can always go back to
  the last green save.
- **Rules of thumb:** one task each at a time · never work on `main` · test before
  you push · if a task needs three sentences to explain, it's two tasks.

---

## Quick reference (stick this on the wall)

| I want to… | Type this |
|---|---|
| Walk into the project | `cd ~/Documents/RAG_project_ENSA` |
| Get the latest code | `git checkout main` then `git pull` |
| Start a task | `git checkout -b feat/S1-ST-10-db` |
| Install/update tools | `uv sync` |
| Run the tests | `uv run pytest -q` |
| Check code is tidy | `uv run ruff check .` |
| Save a checkpoint | `git add -A` then `git commit -m "feat: ..."` |
| Send it up | `git push` |
| See where I am | `git status` |
| Start the app (after the starter screen exists) | `uv run python app.py` → open http://127.0.0.1:8000 |

You're set. Merge PR #2, ask for the starter screen, then take **ST-10** (YL) and
**ST-11** (MB) — Sprint 1 is underway.
