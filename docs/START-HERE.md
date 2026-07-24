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

Install these five tools. For each: what it is → how to get it → how to check it.

- **Git** — the "save history / time machine" for code.
  - 🖱️ Download from **git-scm.com** → run installer → click **Next** on every
    screen (defaults are fine).
  - ✅ Check: open **PowerShell** (press Windows key, type "PowerShell", Enter),
    ⌨️ `git --version` → you should see a version number.
- **uv** — the tool that installs everything the project needs (like a butler who
  fetches all the ingredients).
  - ⌨️ In PowerShell: `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`
  - ✅ Check: **close and reopen** PowerShell, then ⌨️ `uv --version`.
  - (uv can install Python 3.12 for you, so you don't need Python separately.)
- **VS Code** — the editor where you'll read and write code (like Word, but for
  code).
  - 🖱️ Download from **code.visualstudio.com** → install.
  - 🖱️ Open VS Code → left sidebar **Extensions** icon (four squares) → search
    **"Python"** (by Microsoft) → **Install**.
- **Ollama** — runs **free AI models on your own computer**, no internet, no key.
  - 🖱️ Download from **ollama.com/download** → install.
  - ⌨️ In PowerShell: `ollama pull mistral` (downloads the free Mistral model —
    a few minutes; like downloading one big movie).
- **GitHub access** — where the team's code lives online.
  - 🖱️ Make sure you're both signed in at **github.com** and can open
    **github.com/yousseflaaroui3010/RAG_project_ENSA**.

---

## 2. Get Sanad onto your laptop (ONCE, on BOTH laptops)

- **Copy the project down ("clone"):**
  - 📍 On the GitHub repo page, click the green **"< > Code"** button → copy the
    **HTTPS** link.
  - ⌨️ In PowerShell: `git clone https://github.com/yousseflaaroui3010/RAG_project_ENSA.git`
  - Analogy: cloning = downloading your own working copy of the shared folder.
- **Open it in VS Code:**
  - 🖱️ VS Code → **File → Open Folder** → pick the `RAG_project_ENSA` folder.
- **Install everything:**
  - 🖱️ VS Code menu **Terminal → New Terminal** (a command box opens at the bottom).
  - ⌨️ `uv sync` → this reads the project's shopping list and installs it all
    (first time is slow — it downloads big AI libraries; grab a coffee ☕).
- **Confirm it's healthy:**
  - ⌨️ `uv run pytest -q` → you should see **"2 passed"** in green. That's Sanad's
    heartbeat — if it beats, your setup is good.

---

## 3. Turn on the AI brain (set it up now, used fully in Sprint 2)

Sanad can use a **free local** model or a **free cloud** model. Set up at least one.

- **Make your settings file:**
  - 📍 In VS Code's file list (left), find **`.env.example`**.
  - 🖱️ Right-click it → **Copy**, right-click empty space → **Paste**, then
    rename the copy to **`.env`** (right-click → Rename). This is your private
    settings file (never shared).
- **Option A — Free & local (recommended to start):**
  - Open `.env`, set ⌨️ `MODEL_MODE=strict_local` (uses the Mistral model you
    pulled with Ollama — works offline, zero cost).
- **Option B — Free & cloud (Gemini):**
  - 🖱️ Go to **aistudio.google.com** → **"Get API key"** → **Create API key** →
    copy it.
  - In `.env`, set ⌨️ `MODEL_MODE=cloud` and paste the key after
    `CLOUD_API_KEY=`.
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
3. **Do the work.** Either write it, or ask **Claude Code** to build it: open the
   task, describe it plainly ("Build ST-10 following the architecture"), and let
   it work while you watch.
4. **Test it:** ⌨️ `uv run pytest -q` (tests pass?) and `uv run ruff check .`
   (code tidy?). Both green = good.
5. **Save a checkpoint:** ⌨️ `git add -A` then
   `git commit -m "feat: ST-10 filing cabinet"` (commit = save your game).
6. **Send it up:** ⌨️ `git push`.
7. **Open a PR:** 📍 GitHub shows a yellow **"Compare & pull request"** button →
   click it → **Create pull request** → your **partner reviews** → click
   **Merge**.

**Two unbreakable habits:** never type code directly on `main`; commit every time
the tests are green (save often, like a video game).

---

## 5. Finish Sprint 0 — get Sanad "alive" (do this together, first)

- **Merge the skeleton that's already built:**
  - 📍 Open the open PR: **github.com/yousseflaaroui3010/RAG_project_ENSA/pull/2**.
  - ✅ Wait for the green check (automatic tests) → 🖱️ **"Merge pull request"** →
    **"Confirm merge"**. This puts the project's foundation into `main`.
- **Both of you refresh:** ⌨️ `git checkout main` then `git pull`.
- **See it in the browser (starter screen):** we'll add a tiny opening screen so
  Sanad literally opens in your browser. Once it's in:
  - ⌨️ `uv run python app.py` → then 🖱️ open **http://127.0.0.1:8000** in your
    browser. (Ask me to add this starter screen right after this guide — it's a
    5-minute step and makes "the app runs!" true today.)

---

## 6. Sprint 1 — Build the document-reading engine (the heart of Sanad)

**The goal in one line:** teach Sanad to take a folder of documents and turn it
into something it can search — so that later it can answer with sources.

Think of an **assembly line**: a raw PDF goes in one end, and out the other end
come tidy, searchable "index cards." Here are the stations. Each shows: **owner**,
a plain explanation, an analogy, and **what "done" looks like** (how you'll know
it works). Start them **top to bottom** — each one needs the one before it.

- **ST-10 — The filing cabinet (SQLite).** *(Owner: YL)*
  - Stores the *list* of workspaces and documents (not the documents themselves).
  - 🧠 Analogy: the library's index-card catalog.
  - ✅ Done: tests pass for adding a workspace, and deleting a workspace also
    cleans up its documents (no orphans left behind).
- **ST-11 — Workspaces.** *(Owner: MB)*
  - A **named folder** you point Sanad at, e.g. "HR-Law" or "Manuals". Each is
    kept totally separate.
  - 🧠 Analogy: separate labeled **drawers** — an HR question never pulls from the
    Manuals drawer.
  - ✅ Done: you can create, rename, and delete a workspace; deleting removes its
    data but **never** touches your real files on disk.
- **ST-12 — Change detection (hashing).** *(Owner: YL)*
  - Notices which files are **new, changed, or unchanged**, so it never re-reads
    a file that didn't change.
  - 🧠 Analogy: a **fingerprint** for each file.
  - ✅ Done: tests show new/changed/unchanged/removed are each detected correctly.
- **ST-13 — Reading many file types (PDF, Word, Text).** *(Owner: MB)*
  - Turns each document into clean text Sanad can work with. Broken or
    password-locked files are politely skipped with a reason.
  - 🧠 Analogy: a **translator** making every document speak the same language.
  - ✅ Done: a test PDF/Word/Text converts; a corrupt file reports "Failed" and
    doesn't crash the rest.
- **ST-14 — Cutting into pieces (chunking).** *(Owner: MB)*
  - Splits long documents into small, searchable pieces (with a little overlap so
    ideas aren't cut in half).
  - 🧠 Analogy: cutting a long article into **index cards**.
  - ✅ Done: tests confirm the pieces are the right size and overlap.
- **ST-15 — Understanding meaning (embeddings).** *(Owner: YL)*
  - Turns each piece into numbers that capture its **meaning** (so "holiday" and
    "leave" land near each other).
  - 🧠 Analogy: giving each index card a **GPS coordinate** of what it's about.
  - ⚠️ Important rule: every piece gets a `passage:` label and every question a
    `query:` label — a test guards this; never remove it.
  - ✅ Done: the test passes and the small French-understanding model downloads
    once and is cached.
- **ST-16 — The search shelf (Qdrant).** *(Owner: YL)*
  - Stores those number-coordinates so similar pieces are found instantly — **one
    shelf per workspace**.
  - 🧠 Analogy: a **magnetic shelf** where related cards snap together; HR and
    Manuals get separate shelves.
  - ✅ Done: a search in the HR shelf never returns a Manuals card.
- **ST-17 — The Sync button (ties it all together).** *(Owner: YL + MB, pair on
  this one)*
  - Press **Sync** → Sanad scans the folder, runs the whole assembly line, and
    gives a **per-file report** (Added / Changed / Unchanged / Failed / Skipped).
  - 🧠 Analogy: pressing **"refresh"** and getting a printed **receipt** of what
    happened to each file.
  - ✅ Done: syncing a small test folder shows the right status for every file,
    and pressing Sync twice at once is blocked.

**Running alongside (MB's quality stream — do a bit each week):**
- **ST-19 — Golden questions:** write ~15 real HR/labor-law questions *with the
  correct answers and the article they come from*, plus ~8 "trick" questions the
  documents **can't** answer (to prove Sanad refuses honestly later).
  - 📍 Save them in `evaluation/golden/`. 🧠 Analogy: an **exam answer key** you'll
    grade Sanad against.
- **ST-20 — Test checklist:** one simple checklist covering every "what if it goes
  wrong" case (broken file, empty folder, etc.).

---

## 7. When you get stuck (normal — everyone does)

- **A command turned red?** Copy the red text exactly and ask Claude Code / your
  partner. Red text is a clue, not a disaster.
- **Lost your place?** ⌨️ `git status` tells you which branch you're on and what
  changed.
- **Afraid you broke something?** You committed often, remember — you can always
  go back to the last green save.
- **Rules of thumb:** one task each at a time · never work on `main` · test before
  you push · if a task feels like it needs three sentences to explain, it's two
  tasks.

---

## Quick reference (stick this on the wall)

| I want to… | Type this |
|---|---|
| Get the latest code | `git checkout main` then `git pull` |
| Start a task | `git checkout -b feat/S1-ST-10-db` |
| Install/update tools | `uv sync` |
| Run the tests | `uv run pytest -q` |
| Check code is tidy | `uv run ruff check .` |
| Save a checkpoint | `git add -A` then `git commit -m "feat: ..."` |
| Send it up | `git push` |
| See where I am | `git status` |
| Start the app (after the starter screen exists) | `uv run python app.py` → open http://127.0.0.1:8000 |

You're set. Merge PR #2, ask me to add the starter screen, then take **ST-10**
(YL) and **ST-11** (MB) — and Sprint 1 is underway.
