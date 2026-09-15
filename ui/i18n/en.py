"""English catalog. The wording is the V1/V2 interface copy exactly as it
shipped, so the existing test suite (which pins English) keeps asserting
the same sentences it always did.

Keys ending in `_html` are fixed markup: their `{params}` are escaped by
`ui.i18n.translate_markup` before insertion, so a workspace name can never
inject tags. Plain keys are escaped by Jinja like any other expression.
Plural keys carry `.one` / `.other` (Arabic adds zero/two/few/many).
"""

MESSAGES: dict[str, str] = {
    # ---- Shell (base.html) ----
    "title.app": "Sanad",
    "title.chat": "Chat — Sanad",
    "title.workspaces": "Workspaces — Sanad",
    "title.reports": "Reports — Sanad",
    "title.report_detail": "Report detail — Sanad",
    "title.passage": "Passage — Sanad",
    "title.delete": "Delete {name} — Sanad",
    "shell.skip": "Skip to content",
    "phr.activity.uploaded": "uploaded a document",
    "phr.activity.removed_doc": "removed a document",
    "ws.none_shared.title": "No workspace shared with you",
    "ws.none_shared.body": (
        "No workspace has been given to you yet. "
        "Ask an administrator for access."
    ),
    "shell.nav.admin": "Admin",
    "admin.title": "Administration",
    "admin.lead": "Who may use Sanad, in which workspaces, and what has been done.",
    "admin.people": "People",
    "admin.people_caption": "Known accounts",
    "admin.col.person": "Person",
    "admin.col.roles": "Roles",
    "admin.col.last_seen": "Last sign-in",
    "admin.col.workspaces": "Allowed workspaces",
    "admin.col.actions": "Actions",
    "admin.all_workspaces": "Every workspace (admin role)",
    "admin.no_workspaces": "No workspaces yet.",
    "admin.save_grants": "Save access",
    "admin.sign_out_everywhere": "Sign out everywhere",
    "admin.no_people": "Nobody has signed in yet.",
    "admin.activity": "Activity log",
    "admin.activity_lead": "What was done and by whom. Never the content of a question.",
    "admin.activity_caption": "Last {count} events",
    "admin.col.when": "When",
    "admin.col.who": "Who",
    "admin.col.what": "What",
    "admin.col.where": "Workspace",
    "admin.no_activity": "No activity recorded.",
    "phr.activity.signed_in": "signed in",
    "phr.activity.signed_out": "signed out",
    "phr.activity.started_sync": "started a sync",
    "phr.activity.granted": "granted access",
    "phr.activity.revoked": "revoked access",
    "phr.activity.refused": "refused",
    "phr.activity.signed_out_everywhere": "signed a person out everywhere",
    "auth.title": "Sign in to Sanad",
    "auth.lead": (
        "Sanad never asks for your password: signing in happens at your identity "
        "provider."
    ),
    "auth.sign_in": "Sign in",
    "auth.sign_out": "Sign out",
    "auth.failed": "Signing in did not complete.",
    "auth.roles": "Roles: {roles}",
    "auth.no_roles": "none",
    "auth.no_role.title": "Access not granted yet",
    "auth.no_role.body": (
        "Your account is recognised, but it holds no Sanad role. Ask an "
        "administrator to grant one for this account:"
    ),
    "docs.error.forbidden": "you are not allowed to do that in this workspace.",
    "shell.brand": "Sanad",
    "shell.active_workspace": "Active workspace",
    "shell.let_sanad_choose": "Let Sanad choose",
    "shell.legal_option": "legal",
    "shell.switch": "Switch",
    "shell.legal_marker": "Legal",
    "shell.legal_marker_title": "This workspace is flagged as legal content",
    "shell.no_workspace": "No workspace yet",
    "shell.nav_label": "Screens",
    "shell.nav.chat": "Chat",
    "shell.nav.chat_disabled_title": "Create a workspace before asking questions",
    "shell.nav.chat_disabled_title_no_access": (
        "No workspace is shared with you: ask an administrator for access"
    ),
    "shell.nav.workspaces": "Workspaces",
    "shell.nav.reports": "Reports",
    "shell.dark_theme": "Dark theme",
    "shell.language": "Language",
    "shell.desktop_only": (
        "Sanad is built for a desktop browser. This window is too narrow to show "
        "a document, its sources and the passage behind them at once. Widen the "
        "window to carry on."
    ),
    # ---- S1 Chat (chat.html) ----
    "chat.no_workspace.title": "No workspace yet",
    "chat.no_workspace.body": (
        "Sanad answers from documents you have grouped into a workspace, so there "
        "is nothing to ask about until one exists."
    ),
    "chat.no_workspace.link": "Create one on the Workspaces screen",
    "chat.title": "Chat",
    "chat.answering_from": "Answering from",
    "chat.will_pick": "Sanad will pick the workspace once you ask.",
    "chat.new_conversation": "New conversation",
    "chat.your_question": "Your question",
    "chat.placeholder": "Ask a question about this workspace",
    "chat.send": "Send",
    "chat.hint": "Press Enter to send. Every answer names the passages it rests on.",
    # ---- Conversation (_conversation.html) ----
    "conv.aria": "Conversation",
    "conv.feedback.helpful": "Helpful",
    "conv.feedback.what_wrong": "What went wrong? (optional)",
    "conv.feedback.not_helpful": "Not helpful",
    "conv.feedback.saved": "Thanks — feedback saved.",
    "conv.trace.summary": "How this answer was found",
    "conv.trace.searches": "Searches run",
    "conv.trace.none": "None.",
    "conv.trace.files": "Files consulted",
    "conv.trace.retries": "Retries: {value}",
    "conv.trace.retries_none": "none",
    "conv.moved.before": "The conversation context has moved to",
    "conv.moved.after": "Earlier answers on this screen came from a different workspace.",
    "conv.moved.routing": (
        "The conversation context has moved. Ask a question and Sanad will propose "
        "a workspace before answering."
    ),
    "conv.no_docs.title": "Nothing to answer from yet",
    "conv.no_docs.body_html": (
        "<bdi>{name}</bdi> has no synced documents, so Sanad has nothing to read. "
        "Point the workspace at a folder and run Sync."
    ),
    "conv.no_docs.link": "Run Sync on the Workspaces screen",
    "conv.empty.title_html": "Ask a question about <bdi>{name}</bdi>",
    "conv.steps.aria": "How Sanad answers",
    "conv.steps.1_html": "<strong>Searches</strong> this workspace's documents",
    "conv.steps.2_html": "<strong>Checks</strong> each passage is really relevant",
    "conv.steps.3_html": "<strong>Answers</strong> with its sources, or says it cannot",
    "conv.routing.title": "Ask a question, and Sanad will pick the workspace",
    "conv.routing.body": (
        "Sanad checks every workspace for the best match before answering, and asks "
        "you to confirm before it writes anything."
    ),
    "conv.answer.head": "Answer",
    "conv.answer.sources.one": "{count} source",
    "conv.answer.sources.other": "{count} sources",
    "conv.evidence.aria": "Sources this answer rests on",
    "conv.evidence.label": "Based on",
    "conv.retries.title": "Sanad reworded the search {count} time(s) before answering",
    "conv.retries.label.one": "{count} retry",
    "conv.retries.label.other": "{count} retries",
    "conv.refusal.head": "Not found in this workspace",
    "conv.refusal.searched": "What Sanad searched for:",
    "conv.refusal.reworded": "Reworded {count} time(s) before stopping.",
    "conv.clarify.head": "One detail first",
    "conv.route.yes_html": "Yes, use <bdi>{name}</bdi>",
    "conv.incomplete": "Incomplete — not an answer",
    "conv.partial.note": (
        "You stopped the writing. The text above is unfinished and is not tied to any source."
    ),
    "conv.streaming.head": "Writing",
    "conv.disclaimer": "Informational only, not legal advice. Consult a qualified professional.",
    "conv.cancel": "Cancel",
    # ---- Sources and passages ----
    "sources.aria": "Sources for this answer",
    "sources.title": "Sources ({count})",
    "sources.open": "Open passage",
    "sources.close": "Close",
    "docs.title": "Documents",
    "docs.drop.title": "Drop your documents here",
    "docs.drop.hint": (
        "PDF, DOCX, PPTX, TXT or MD, up to {size}. Sync starts on its own afterwards."
    ),
    "docs.drop.choose": "Choose files",
    "docs.upload.sending": "Sending {name}…",
    "docs.upload.saved": "{name} added.",
    "docs.upload.replaced": "{name} replaced.",
    "docs.upload.failed": "{name}: {reason}",
    "docs.upload.syncing": "Sync started.",
    "docs.error.name": "this file name cannot be used.",
    "docs.error.type": "unsupported type (accepted: {types}).",
    "docs.error.size": "{name} is over the size limit.",
    "docs.error.empty": "{name} is empty.",
    "docs.error.missing": "No document named {name} in this workspace.",
    "docs.error.folder": "the workspace folder is missing.",
    "docs.error.evidence": "this published instance is read-only.",
    "docs.error.workspace": "this workspace no longer exists.",
    "docs.download": "Download",
    "docs.download_aria": "Download {name}",
    "docs.delete": "Remove",
    "docs.delete_aria": "Remove {name} from the folder",
    "docs.del.title_html": "Remove <bdi>{name}</bdi>?",
    "docs.del.body": (
        "The file is deleted from the workspace folder on disk. The Sync that follows "
        "removes it from answers."
    ),
    "docs.del.yes": "Yes, remove this document",
    "docs.del.cancel": "Cancel, keep this document",
    "docs.removed": "{name} was removed from the folder.",
    "files.col.actions": "Actions",
    "sources.download": "Download original",
    "passage.not_located": (
        "Showing the whole section. Sanad could not locate the exact retrieved span "
        "inside it, so nothing here is marked as the cited text."
    ),
    "passage.back": "Back to the conversation",
    "passage.gone.title": "That passage is no longer on screen",
    "passage.gone.body": (
        "The conversation it belonged to has been replaced or cleared, so the section "
        "behind that citation is not loaded any more."
    ),
    "passage.gone.hint": "Ask the question again to get a fresh citation.",
    # ---- S2 Workspaces ----
    "files.caption": "Last sync report",
    "files.col.name": "Name",
    "files.col.type": "Type",
    "files.col.size": "Size",
    "files.col.status": "Status",
    "files.col.reason": "Reason",
    "ws.form.name": "Workspace name",
    "ws.form.name_placeholder": "e.g. HR policies",
    "ws.form.folder": "Folder path",
    "ws.form.folder_placeholder": "e.g. C:\\Documents\\HR",
    "ws.form.legal": "This workspace holds legal content",
    "ws.form.legal_help": (
        "Adds a disclaimer line to every answer from this workspace. It does not "
        "restrict access or block deletion."
    ),
    "ws.form.create": "Create workspace",
    "ws.detail.aria": "Workspace detail",
    "ws.detail.pick": "Pick a workspace from the list to see its detail.",
    "ws.detail.settings": "Rename, legal flag, delete",
    "ws.detail.rename": "Rename",
    "ws.detail.save": "Save",
    "ws.detail.delete": "Delete workspace…",
    "ws.sync.blocked": (
        "A Sync is already running for this workspace; it keeps going, and this new "
        "request was not started."
    ),
    "ws.sync.processed.one": "{count} file processed so far",
    "ws.sync.processed.other": "{count} files processed so far",
    "ws.sync.scanning": "Scanning the workspace folder…",
    "ws.sync.started": "Started {when}.",
    "ws.sync.cancel": "Cancel after current file",
    "ws.sync.run": "Run Sync",
    "ws.sync.error": "Sync could not run.",
    "ws.sync.pending_report": "The last sync report will appear here once this run finishes.",
    "ws.sync.finished": "Last Sync finished {when}.",
    "ws.sync.never": "This workspace has not been synced yet.",
    "ws.first.title": "Create your first workspace",
    "ws.first.body": (
        "Sanad answers from documents grouped into a workspace. There is nothing to "
        "sync or ask about until one exists."
    ),
    "ws.list.aria": "Workspaces",
    "ws.list.title": "Workspaces",
    "ws.watch.on": "Watching for new files: on",
    "ws.watch.off": "Watching for new files: off",
    "ws.list.new": "New workspace",
    "del.title_html": "Delete \"<bdi>{name}</bdi>\"?",
    "del.body_html": (
        "This removes <bdi>{name}</bdi>'s synced index -- every passage Sanad can "
        "currently answer from -- and its sync history. It does <strong>not</strong> "
        "touch the files in"
    ),
    "del.body_after": (
        "They stay on disk exactly as they are; only Sanad's copy of what it read "
        "from them is removed."
    ),
    "del.yes_html": "Yes, delete <bdi>{name}</bdi>",
    "del.cancel": "Cancel, keep this workspace",
    # ---- S3 Reports ----
    "rep.empty.title": "No evaluation reports yet",
    "rep.empty.body": (
        "Reports appear here once the golden-set evaluation has run at least once. "
        "Run it from a terminal:"
    ),
    "rep.aria": "Evaluation reports",
    "rep.title": "Reports",
    "rep.lead": "Golden-set evaluation runs and the release gates each one met.",
    "rep.caption": "Evaluation runs",
    "rep.col.date": "Date",
    "rep.col.workspace": "Workspace",
    "rep.col.groundedness": "Groundedness",
    "rep.col.refusals": "Refusals",
    "rep.col.sources": "Sources",
    "rep.col.outcome": "Outcome",
    "rep.open_aria": "Open the {when} report for {name}",
    "fb.aria": "Answer feedback",
    "fb.title": "Answer feedback",
    "fb.caption": "Feedback on answers",
    "fb.col.date": "Date",
    "fb.col.workspace": "Workspace",
    "fb.col.verdict": "Verdict",
    "fb.col.question": "Question",
    "fb.col.comment": "Comment",
    "fb.none": "No feedback yet.",
    "rd.missing": "No such report.",
    "rd.back_all": "Back to all reports",
    "rd.aria": "Report detail",
    "rd.final.partial": "Evaluation stopped with partial results.",
    "rd.final.completed": "Evaluation completed.",
    "rd.all": "All reports",
    "rd.running": "Evaluation running: {done}/{total} questions completed.",
    "rd.partial": "Partial: stopped at question {number} of {total} ({qid}).",
    "rd.kept.one": "{count} completed question kept.",
    "rd.kept.other": "{count} completed questions kept.",
    "rd.not_final": "Not final",
    "rd.not_judged": "Not judged",
    "rd.pass": "Pass",
    "rd.fail": "Fail",
    "rd.gates": "Release gates",
    "rd.col.metric": "Metric",
    "rd.col.value": "Value",
    "rd.col.threshold": "Threshold",
    "rd.col.outcome": "Outcome",
    "rd.file_unavailable": "The full per-question report file is unavailable.",
    "rd.questions": "Per-question results",
    "rd.col.question": "Question",
    "rd.col.kind": "Kind",
    "rd.col.groundedness": "Groundedness",
    "rd.col.relevancy": "Relevancy",
    "rd.col.sources": "Sources",
    "rd.col.error": "Error",
    "rd.export": "Export as Markdown for the report annex",
    "dash.aria": "Quality dashboard",
    "dash.title": "Latest completed evaluation",
    "dash.lead_html": "<bdi>{name}</bdi>, {when}",
    "dash.threshold": "Threshold {value}",
    "dash.no_counts": "Counts not available for this run.",
    "dash.trend_aria": "Trend over {count} completed evaluations",
    "dash.feedback": "Reader feedback",
    "dash.feedback_value": "{helpful} helpful of {total}",
    "dash.feedback_none": "No feedback yet.",
    "heat.title": "Question map",
    "heat.lead": "One square per question, in table order. Select one to jump to its row.",
    "heat.group": "{label}: {passed}/{total} passed",
    "heat.cell_aria": "{qid}: {outcome}",
    "reports.status.finished_sentence": "Evaluation finished.",
    # ---- Sentences built in Python (ui.i18n.phrases maps them here) ----
    "phr.sources_promise": "Every answer carries the sources it was written from.",
    "phr.sample": "What does \"{name}\" cover?",
    "phr.no_documents_reason": (
        "This workspace has no synced documents yet, so there is nothing to answer "
        "from. Add a folder and run Sync on the Workspaces screen."
    ),
    "phr.busy_reason": "Sanad is answering your last question.",
    "phr.stage.preparing": "Preparing the question",
    "phr.stage.searching": "Searching the workspace",
    "phr.stage.checking": "Checking the answer",
    "phr.stage.writing": "Writing",
    "phr.route.no_match": (
        "None of your workspaces look like a match for this question. Pick one from "
        "the selector above and ask again."
    ),
    "phr.route.proposal": "This looks like a question for {name}. Answer from there?",
    "phr.error.sentence": "Sanad could not answer this question.",
    "phr.error.asked": "Asked: {question}",
    "phr.error.hint": (
        "Nothing was fabricated in place of an answer. Check the model settings in "
        ".env, then use Retry."
    ),
    "phr.interrupted": (
        "You stopped this answer. Nothing was written, so there is no partial text to "
        "show, and nothing here is a finished answer. Ask again to retry."
    ),
    "phr.capacity": (
        "This workspace has {files} files and {pages} measured PDF pages, above the "
        "recommended limit of {max_files} files or {max_pages} pages. Split it into "
        "smaller workspace folders before the next large Sync."
    ),
    "phr.status.added": "Added",
    "phr.status.changed": "Changed",
    "phr.status.unchanged": "Unchanged",
    "phr.status.failed": "Failed",
    "phr.status.removed": "Removed",
    "phr.status.skipped": "Skipped",
    "phr.report.running": "Running {done}/{total}",
    "phr.report.partial": "Partial {done}/{total}",
    "phr.report.pass": "Pass",
    "phr.report.fail": "Fail",
    "phr.report.grounded": "{passed}/{total} fully grounded",
    "phr.report.g1": "G1 Groundedness",
    "phr.report.g2": "G2 Honest refusals",
    "phr.report.g3": "G3 Sources on every answer",
    "phr.report.in_scope": "In scope",
    "phr.report.out_of_scope": "Out of scope",
    "phr.report.not_judged": "Not judged",
    "phr.report.not_final": "Not final",
    "phr.report.yes": "Yes",
    "phr.report.no": "No",
    "phr.report.file_error": (
        "The full report file is missing, unreadable, or out of date at {path}. "
        "Showing the durable database copy below instead. Older runs may not carry "
        "answer kind, sources-present, or error detail; any gate without enough "
        "stored evidence is labelled not judged."
    ),
    "phr.feedback.helpful": "Helpful",
    "phr.feedback.not_helpful": "Not helpful",
    "phr.feedback.gone": "This answer is no longer on screen, so feedback could not be saved.",
    "phr.feedback.too_long": (
        "Feedback could not be saved: the comment is longer than {max} characters."
    ),
    "phr.feedback.invalid": "Feedback could not be saved: invalid response.",
    "phr.delete.sync_running": (
        "This workspace cannot be deleted while a Sync of it is running. Cancel the "
        "Sync or wait for it to finish, then try again."
    ),
    "phr.delete.store_busy": (
        "This workspace cannot be deleted while its document index is in use by the "
        "evaluation command. Wait for it to finish, then try again."
    ),
    "phr.evidence_only": (
        "This published instance is read-only: it shows evaluation reports and "
        "workspace details, but cannot answer questions or run a Sync. Both need the "
        "embedding model, which is larger than this container's memory limit. Run "
        "Sanad locally to ask questions or index documents."
    ),
    "phr.folder_missing": (
        "workspace folder does not exist or is not a directory: {path}. Check the "
        "path, or reconnect the drive if it is on removable or network storage."
    ),
    "phr.sync_running": (
        "a sync started at {started} is still running for workspace {workspace}; it "
        "keeps going and this request was not started"
    ),
    "phr.name_in_use": "workspace name already in use: {name}",
    "phr.name_length": "workspace name must be between {min} and {max} characters: {name}",
    "phr.folder_empty": "folder_path must not be empty or whitespace-only: {path}",
    "phr.reason.unsupported": "unsupported file type",
    "phr.reason.uninspectable": (
        "the file could not be inspected ({error}), so it was left untouched and its "
        "existing passages still answer questions"
    ),
    "phr.reason.pdf_damaged": (
        "the PDF is damaged or is not really a PDF file. Open it in a PDF reader to "
        "check it, then sync again"
    ),
    "phr.reason.pdf_locked": (
        "the PDF is password-protected. Remove the password, save a copy without it, "
        "then sync again"
    ),
    "phr.reason.pdf_no_text": (
        "this PDF has no text layer, so it is a scan or images only. Sanad cannot read "
        "text from pictures yet, so nothing was indexed"
    ),
    "phr.reason.ocr_no_text": (
        "this PDF was scanned, and OCR could not find any readable text on it. Check the "
        "pages are not blank or upside down, then sync again"
    ),
    "phr.reason.ocr_too_long": (
        "this scanned PDF has {pages} pages, over the {limit}-page OCR limit, so it was "
        "not processed. Split it into smaller files, then sync again"
    ),
    "phr.reason.docx_damaged": (
        "the DOCX is damaged or is not really a Word file. Open it in Word to check it, "
        "then sync again"
    ),
    "phr.reason.pptx_damaged": (
        "the PPTX is damaged or is not really a PowerPoint file. Open it in PowerPoint "
        "to check it, then sync again"
    ),
    "phr.reason.empty": "the file has no text in it",
    "phr.reason.undecodable": (
        "this file is not valid UTF-8 text, so it could not be read. Open it and re-save "
        "it with UTF-8 encoding, then sync again"
    ),
    "phr.reason.unreadable": "the file could not be read: {detail}",
    "phr.reason.removed": (
        "the file is no longer in the workspace folder, so its passages were removed "
        "from answers"
    ),
    "phr.reason.index_failed": "the file could not be indexed: {detail}",
    "phr.reason.cancelled": "Sync was cancelled before this file was processed",
}
