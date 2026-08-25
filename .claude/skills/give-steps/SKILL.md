---
name: give-steps
description: How to write instructions a human follows by hand. Use whenever telling the user to do something themselves - install a file, run a command, click something, paste something, or any step a tool cannot do for them.
---

# Giving steps

The reader is smart and is not a developer. They should never have to work
anything out, guess a name, or read an explanation to find the action.

## The shape

1. **Numbered steps. One action each.** If a step has an "and" in it, it is
   two steps.
2. **Every literal in its own code block** - paths, file names, commands,
   text to type. Ready to copy, nothing to edit, no placeholders.
3. **Name the exact key, button or menu.** `Ctrl+P`, not "open the file".
   "Right-click the folder, choose New File", not "create a file".
4. **Say where they are before what they do.** "In VS Code", "in the file
   explorer on the left".
5. **End with how to know it worked.** One line. Never leave them guessing.

## The tone

- Say the action, not the reasoning. Why goes above the steps or nowhere.
- No hedging. "Do this", not "you might want to".
- No jargon in a step. If a step needs a term explained, the step is wrong.
- Short lines. A step should fit on one line where possible.

## Never

- **Never a placeholder** like `<your-path>` or `path/to/file`. Look up the
  real value and paste it in. If it genuinely cannot be known, that is a
  question to ask, not a gap to hand over.
- **Never a step that gets past a guard.** If a hook or a deny rule is
  blocking, the sanctioned routes are the human editing the file in an
  editor, or changing the guard in the open with the reason recorded. Never
  a shell command that routes around it.
- **Never mix explanation into the numbered list.** Context first, steps
  second, nothing after but the check.
- **Never more steps than the job needs.** Five short steps beat three long
  ones, and both beat a paragraph.

## Good and bad

Bad:

> Copy the settings file into your project's Claude config directory and
> restart so the hooks are picked up.

Good:

> **1.** Press `Ctrl+P`, paste this, press Enter:
> ```
> C:\Users\me\AppData\Local\Temp\...\settings.json
> ```
> **2.** Press `Ctrl+A` then `Ctrl+C`.
>
> **3.** In the file explorer on the left, right-click the `.claude` folder
> → **New File** → type exactly:
> ```
> settings.json
> ```
> **4.** Click inside the file, press `Ctrl+V` then `Ctrl+S`.
>
> **5.** Close Claude Code and open it again.
>
> Then send me any message and I will check it worked.

The difference is not length. It is that the second one cannot be got wrong.