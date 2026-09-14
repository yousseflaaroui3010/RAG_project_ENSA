"""الفهرس العربي للواجهة (العربية الفصحى، بصياغة مألوفة لدى المهنيين في المغرب).

Same keys as `en.py`. Arabic plural keys may carry the extra CLDR
categories (zero/two/few/many) beside `.one`/`.other`; the parity test
compares base keys, not plural suffixes.
"""

MESSAGES: dict[str, str] = {
    # ---- الإطار العام (base.html) ----
    "title.app": "سند",
    "title.chat": "المساعد — سند",
    "title.workspaces": "فضاءات العمل — سند",
    "title.reports": "التقارير — سند",
    "title.report_detail": "تفاصيل التقرير — سند",
    "title.passage": "مقتطف — سند",
    "title.delete": "حذف {name} — سند",
    "shell.skip": "الانتقال إلى المحتوى",
    "ws.none_shared.title": "لا يوجد فضاء مشترك معك",
    "ws.none_shared.body": "لم يُمنح لك أي فضاء عمل بعد. اطلب من المسؤول منحك الوصول.",
    "shell.nav.admin": "الإدارة",
    "admin.title": "الإدارة",
    "admin.lead": "من يمكنه استعمال سند، وفي أي فضاءات، وما الذي تم.",
    "admin.people": "الأشخاص",
    "admin.people_caption": "الحسابات المعروفة",
    "admin.col.person": "الشخص",
    "admin.col.roles": "الأدوار",
    "admin.col.last_seen": "آخر دخول",
    "admin.col.workspaces": "الفضاءات المسموح بها",
    "admin.col.actions": "إجراءات",
    "admin.all_workspaces": "كل الفضاءات (دور المسؤول)",
    "admin.no_workspaces": "لا توجد فضاءات بعد.",
    "admin.save_grants": "حفظ الصلاحيات",
    "admin.sign_out_everywhere": "إنهاء كل الجلسات",
    "admin.no_people": "لم يدخل أحد بعد.",
    "admin.activity": "سجل النشاط",
    "admin.activity_lead": "ما الذي تم ومن قام به. لا يُسجَّل محتوى أي سؤال.",
    "admin.activity_caption": "آخر {count} حدثًا",
    "admin.col.when": "متى",
    "admin.col.who": "من",
    "admin.col.what": "ماذا",
    "admin.col.where": "الفضاء",
    "admin.no_activity": "لا نشاط مسجل.",
    "phr.activity.signed_in": "تسجيل الدخول",
    "phr.activity.signed_out": "تسجيل الخروج",
    "phr.activity.started_sync": "بدء المزامنة",
    "phr.activity.granted": "منح الوصول",
    "phr.activity.revoked": "سحب الوصول",
    "phr.activity.refused": "إجراء مرفوض",
    "phr.activity.signed_out_everywhere": "إنهاء جلسات شخص",
    "auth.title": "الدخول إلى سند",
    "auth.lead": "سند لا يطلب كلمة المرور أبدًا: يتم الدخول عبر مزوّد الهوية.",
    "auth.sign_in": "تسجيل الدخول",
    "auth.sign_out": "تسجيل الخروج",
    "auth.failed": "تعذّر تسجيل الدخول.",
    "auth.roles": "الأدوار: {roles}",
    "auth.no_roles": "لا شيء",
    "auth.no_role.title": "لم يُمنح الوصول بعد",
    "auth.no_role.body": "حسابك معروف، لكن لا دور له في سند. اطلب من المسؤول منح دور لهذا الحساب:",
    "docs.error.forbidden": "ليست لديك صلاحية القيام بذلك في هذا الفضاء.",
    "shell.brand": "سند",
    "shell.active_workspace": "فضاء العمل النشط",
    "shell.let_sanad_choose": "دع سند يختار",
    "shell.legal_option": "قانوني",
    "shell.switch": "تغيير",
    "shell.legal_marker": "قانوني",
    "shell.legal_marker_title": "هذا الفضاء يضم نصوصًا قانونية",
    "shell.no_workspace": "لا يوجد فضاء عمل بعد",
    "shell.nav_label": "الشاشات",
    "shell.nav.chat": "المساعد",
    "shell.nav.chat_disabled_title": "أنشئ فضاء عمل قبل طرح الأسئلة",
    "shell.nav.workspaces": "الفضاءات",
    "shell.nav.reports": "التقارير",
    "shell.dark_theme": "الوضع الداكن",
    "shell.language": "اللغة",
    "shell.desktop_only": (
        "صُمّم سند لمتصفح الحاسوب. هذه النافذة ضيقة جدًا لعرض الوثيقة ومصادرها "
        "والمقتطف المستشهد به في آن واحد. وسّع النافذة للمتابعة."
    ),
    # ---- المساعد (chat.html) ----
    "chat.no_workspace.title": "لا يوجد فضاء عمل بعد",
    "chat.no_workspace.body": (
        "يجيب سند انطلاقًا من الوثائق المجمّعة في فضاء عمل، لذلك لا يوجد ما يمكن "
        "السؤال عنه قبل إنشاء فضاء."
    ),
    "chat.no_workspace.link": "أنشئ فضاءً من شاشة الفضاءات",
    "chat.title": "المساعد",
    "chat.answering_from": "الإجابة من",
    "chat.will_pick": "سيختار سند الفضاء المناسب بمجرد طرح سؤالك.",
    "chat.new_conversation": "محادثة جديدة",
    "chat.your_question": "سؤالك",
    "chat.placeholder": "اطرح سؤالًا حول هذا الفضاء",
    "chat.send": "إرسال",
    "chat.hint": "اضغط Enter للإرسال. كل إجابة تذكر المقاطع التي تستند إليها.",
    # ---- المحادثة (_conversation.html) ----
    "conv.aria": "المحادثة",
    "conv.feedback.helpful": "مفيدة",
    "conv.feedback.what_wrong": "ما الذي لم يكن صحيحًا؟ (اختياري)",
    "conv.feedback.not_helpful": "غير مفيدة",
    "conv.feedback.saved": "شكرًا — تم حفظ ملاحظتك.",
    "conv.trace.summary": "كيف تم التوصل إلى هذه الإجابة",
    "conv.trace.searches": "عمليات البحث المنجزة",
    "conv.trace.none": "لا شيء.",
    "conv.trace.files": "الملفات التي تمت مراجعتها",
    "conv.trace.retries": "إعادة المحاولة: {value}",
    "conv.trace.retries_none": "لا توجد",
    "conv.moved.before": "انتقل سياق المحادثة إلى",
    "conv.moved.after": "الإجابات السابقة في هذه الشاشة جاءت من فضاء عمل آخر.",
    "conv.moved.routing": "تغيّر سياق المحادثة. اطرح سؤالًا وسيقترح سند فضاءً قبل الإجابة.",
    "conv.no_docs.title": "لا يوجد ما يمكن الإجابة منه بعد",
    "conv.no_docs.body_html": (
        "لا يحتوي <bdi>{name}</bdi> على أي وثائق متزامنة، لذلك لا يجد سند ما يقرؤه. "
        "اربط الفضاء بمجلد ثم شغّل المزامنة."
    ),
    "conv.no_docs.link": "شغّل المزامنة من شاشة الفضاءات",
    "conv.empty.title_html": "اطرح سؤالًا حول <bdi>{name}</bdi>",
    "conv.steps.aria": "كيف يجيب سند",
    "conv.steps.1_html": "<strong>يبحث</strong> في وثائق هذا الفضاء",
    "conv.steps.2_html": "<strong>يتحقق</strong> من صلة كل مقطع بالسؤال",
    "conv.steps.3_html": "<strong>يجيب</strong> مع ذكر مصادره، أو يقول إنه لا يعرف",
    "conv.routing.title": "اطرح سؤالك وسيختار سند الفضاء",
    "conv.routing.body": (
        "يبحث سند في كل الفضاءات عن أفضل تطابق، ثم يطلب تأكيدك قبل كتابة أي إجابة."
    ),
    "conv.answer.head": "الإجابة",
    "conv.answer.sources.zero": "بلا مصادر",
    "conv.answer.sources.one": "مصدر واحد",
    "conv.answer.sources.two": "مصدران",
    "conv.answer.sources.few": "{count} مصادر",
    "conv.answer.sources.many": "{count} مصدرًا",
    "conv.answer.sources.other": "{count} مصدر",
    "conv.evidence.aria": "المصادر التي تستند إليها هذه الإجابة",
    "conv.evidence.label": "بالاستناد إلى",
    "conv.retries.title": "أعاد سند صياغة البحث {count} مرة قبل الإجابة",
    "conv.retries.label.one": "إعادة صياغة واحدة",
    "conv.retries.label.two": "إعادتا صياغة",
    "conv.retries.label.few": "{count} إعادات صياغة",
    "conv.retries.label.many": "{count} إعادة صياغة",
    "conv.retries.label.other": "{count} إعادة صياغة",
    "conv.refusal.head": "غير موجود في هذا الفضاء",
    "conv.refusal.searched": "ما بحث عنه سند:",
    "conv.refusal.reworded": "أُعيدت الصياغة {count} مرة قبل التوقف.",
    "conv.clarify.head": "توضيح واحد أولًا",
    "conv.route.yes_html": "نعم، استخدم <bdi>{name}</bdi>",
    "conv.incomplete": "غير مكتملة — ليست إجابة",
    "conv.partial.note": "أوقفت الكتابة. النص أعلاه غير مكتمل ولا يستند إلى أي مصدر.",
    "conv.streaming.head": "جارٍ الكتابة",
    "conv.disclaimer": "معلومات للاستئناس فقط، ولا تُعدّ استشارة قانونية. استشر مختصًا مؤهلًا.",
    "conv.cancel": "إلغاء",
    # ---- المصادر والمقتطفات ----
    "sources.aria": "مصادر هذه الإجابة",
    "sources.title": "المصادر ({count})",
    "sources.open": "فتح المقتطف",
    "sources.close": "إغلاق",
    "docs.title": "الوثائق",
    "docs.drop.title": "أفلت وثائقك هنا",
    "docs.drop.hint": (
        "PDF أو DOCX أو PPTX أو TXT أو MD، حتى {size}. تبدأ المزامنة تلقائيًا بعد ذلك."
    ),
    "docs.drop.choose": "اختيار ملفات",
    "docs.upload.sending": "جارٍ إرسال {name}…",
    "docs.upload.saved": "أُضيف {name}.",
    "docs.upload.replaced": "استُبدل {name}.",
    "docs.upload.failed": "{name}: {reason}",
    "docs.upload.syncing": "بدأت المزامنة.",
    "docs.error.name": "اسم الملف هذا غير صالح.",
    "docs.error.type": "نوع غير مدعوم (المقبول: {types}).",
    "docs.error.size": "{name} يتجاوز الحجم الأقصى.",
    "docs.error.empty": "{name} فارغ.",
    "docs.error.missing": "لا توجد وثيقة باسم {name} في هذا الفضاء.",
    "docs.error.folder": "مجلد الفضاء غير موجود.",
    "docs.error.evidence": "هذه النسخة المنشورة للقراءة فقط.",
    "docs.error.workspace": "هذا الفضاء لم يعد موجودًا.",
    "docs.download": "تنزيل",
    "docs.download_aria": "تنزيل {name}",
    "docs.delete": "إزالة",
    "docs.delete_aria": "إزالة {name} من المجلد",
    "docs.del.title_html": "إزالة <bdi>{name}</bdi>؟",
    "docs.del.body": "يُحذف الملف من مجلد الفضاء على القرص، وتزيله المزامنة التالية من الإجابات.",
    "docs.del.yes": "نعم، أزل هذه الوثيقة",
    "docs.del.cancel": "إلغاء، الإبقاء على الوثيقة",
    "docs.removed": "أُزيل {name} من المجلد.",
    "files.col.actions": "إجراءات",
    "sources.download": "تنزيل الأصل",
    "passage.not_located": (
        "يُعرض القسم كاملًا. لم يتمكن سند من تحديد المقطع المسترجع بدقة، لذلك لا يوجد "
        "نص مظلَّل بوصفه اقتباسًا."
    ),
    "passage.back": "العودة إلى المحادثة",
    "passage.gone.title": "هذا المقتطف لم يعد معروضًا",
    "passage.gone.body": (
        "استُبدلت المحادثة التي ينتمي إليها أو مُسحت، لذلك لم يعد القسم المستشهد به محمّلًا."
    ),
    "passage.gone.hint": "اطرح السؤال مجددًا للحصول على استشهاد محدَّث.",
    # ---- فضاءات العمل ----
    "files.caption": "آخر تقرير مزامنة",
    "files.col.name": "الاسم",
    "files.col.type": "النوع",
    "files.col.size": "الحجم",
    "files.col.status": "الحالة",
    "files.col.reason": "السبب",
    "ws.form.name": "اسم الفضاء",
    "ws.form.name_placeholder": "مثال: سياسات الموارد البشرية",
    "ws.form.folder": "مسار المجلد",
    "ws.form.folder_placeholder": "مثال: C:\\Documents\\RH",
    "ws.form.legal": "هذا الفضاء يضم نصوصًا قانونية",
    "ws.form.legal_help": (
        "يضيف تنبيهًا إلى كل إجابة من هذا الفضاء. لا يقيّد الوصول ولا يمنع الحذف."
    ),
    "ws.form.create": "إنشاء الفضاء",
    "ws.detail.aria": "تفاصيل الفضاء",
    "ws.detail.pick": "اختر فضاءً من القائمة لعرض تفاصيله.",
    "ws.detail.settings": "إعادة التسمية، التنبيه القانوني، الحذف",
    "ws.detail.rename": "إعادة التسمية",
    "ws.detail.save": "حفظ",
    "ws.detail.delete": "حذف الفضاء…",
    "ws.sync.blocked": "هناك مزامنة جارية لهذا الفضاء؛ ستستمر، ولم يتم بدء هذا الطلب الجديد.",
    "ws.sync.processed.zero": "لم تتم معالجة أي ملف بعد",
    "ws.sync.processed.one": "تمت معالجة ملف واحد حتى الآن",
    "ws.sync.processed.two": "تمت معالجة ملفين حتى الآن",
    "ws.sync.processed.few": "تمت معالجة {count} ملفات حتى الآن",
    "ws.sync.processed.many": "تمت معالجة {count} ملفًا حتى الآن",
    "ws.sync.processed.other": "تمت معالجة {count} ملف حتى الآن",
    "ws.sync.scanning": "جارٍ فحص مجلد الفضاء…",
    "ws.sync.started": "بدأت في {when}.",
    "ws.sync.cancel": "إلغاء بعد الملف الحالي",
    "ws.sync.run": "مزامنة",
    "ws.sync.error": "تعذّر تشغيل المزامنة.",
    "ws.sync.pending_report": "سيظهر تقرير المزامنة هنا فور انتهاء هذه العملية.",
    "ws.sync.finished": "انتهت آخر مزامنة في {when}.",
    "ws.sync.never": "لم تتم مزامنة هذا الفضاء بعد.",
    "ws.first.title": "أنشئ فضاء العمل الأول",
    "ws.first.body": (
        "يجيب سند انطلاقًا من الوثائق المجمّعة في فضاء عمل. لا يوجد ما تتم مزامنته أو "
        "السؤال عنه قبل إنشاء فضاء."
    ),
    "ws.list.aria": "فضاءات العمل",
    "ws.list.title": "فضاءات العمل",
    "ws.watch.on": "مراقبة الملفات الجديدة: مفعّلة",
    "ws.watch.off": "مراقبة الملفات الجديدة: معطّلة",
    "ws.list.new": "فضاء جديد",
    "del.title_html": "حذف «<bdi>{name}</bdi>»؟",
    "del.body_html": (
        "يحذف هذا الإجراء الفهرس المتزامن لـ<bdi>{name}</bdi> — أي كل المقاطع التي يمكن "
        "لسند الإجابة منها — وسجل مزامنته. <strong>لا يمسّ</strong> الملفات الموجودة في"
    ),
    "del.body_after": "تبقى الملفات على القرص كما هي؛ تُحذف فقط النسخة التي قرأها سند.",
    "del.yes_html": "نعم، احذف <bdi>{name}</bdi>",
    "del.cancel": "إلغاء، الاحتفاظ بهذا الفضاء",
    # ---- التقارير ----
    "rep.empty.title": "لا توجد تقارير تقييم بعد",
    "rep.empty.body": (
        "تظهر التقارير هنا بعد تشغيل التقييم على مجموعة الأسئلة "
        "المرجعية مرة واحدة على الأقل. شغّله من الطرفية:"
    ),
    "rep.aria": "تقارير التقييم",
    "rep.title": "التقارير",
    "rep.lead": "عمليات التقييم على المجموعة المرجعية ومعايير الإصدار التي حققتها كل عملية.",
    "rep.caption": "عمليات التقييم",
    "rep.col.date": "التاريخ",
    "rep.col.workspace": "الفضاء",
    "rep.col.groundedness": "الاستناد إلى المصادر",
    "rep.col.refusals": "الرفض",
    "rep.col.sources": "المصادر",
    "rep.col.outcome": "النتيجة",
    "rep.open_aria": "فتح تقرير {when} الخاص بـ{name}",
    "fb.aria": "ملاحظات على الإجابات",
    "fb.title": "ملاحظات على الإجابات",
    "fb.caption": "الملاحظات المسجلة على الإجابات",
    "fb.col.date": "التاريخ",
    "fb.col.workspace": "الفضاء",
    "fb.col.verdict": "التقييم",
    "fb.col.question": "السؤال",
    "fb.col.comment": "التعليق",
    "fb.none": "لا توجد ملاحظات بعد.",
    "rd.missing": "هذا التقرير غير موجود.",
    "rd.back_all": "العودة إلى كل التقارير",
    "rd.aria": "تفاصيل التقرير",
    "rd.final.partial": "توقف التقييم بنتائج جزئية.",
    "rd.final.completed": "اكتمل التقييم.",
    "rd.all": "كل التقارير",
    "rd.running": "التقييم جارٍ: {done}/{total} سؤالًا مكتملًا.",
    "rd.partial": "جزئي: توقف عند السؤال {number} من {total} ({qid}).",
    "rd.kept.one": "تم الاحتفاظ بسؤال مكتمل واحد.",
    "rd.kept.two": "تم الاحتفاظ بسؤالين مكتملين.",
    "rd.kept.few": "تم الاحتفاظ بـ{count} أسئلة مكتملة.",
    "rd.kept.many": "تم الاحتفاظ بـ{count} سؤالًا مكتملًا.",
    "rd.kept.other": "تم الاحتفاظ بـ{count} سؤال مكتمل.",
    "rd.not_final": "غير نهائي",
    "rd.not_judged": "لم يُقيَّم",
    "rd.pass": "ناجح",
    "rd.fail": "راسب",
    "rd.gates": "معايير الإصدار",
    "rd.col.metric": "المعيار",
    "rd.col.value": "القيمة",
    "rd.col.threshold": "العتبة",
    "rd.col.outcome": "النتيجة",
    "rd.file_unavailable": "ملف النتائج التفصيلية لكل سؤال غير متاح.",
    "rd.questions": "النتائج حسب السؤال",
    "rd.col.question": "السؤال",
    "rd.col.kind": "النوع",
    "rd.col.groundedness": "الاستناد إلى المصادر",
    "rd.col.relevancy": "الملاءمة",
    "rd.col.sources": "المصادر",
    "rd.col.error": "الخطأ",
    "rd.export": "تصدير بصيغة Markdown لملحق التقرير",
    "dash.aria": "لوحة الجودة",
    "dash.title": "آخر تقييم مكتمل",
    "dash.lead_html": "<bdi>{name}</bdi>، {when}",
    "dash.threshold": "العتبة {value}",
    "dash.no_counts": "العدد غير متوفر لهذا التقييم.",
    "dash.trend_aria": "التطور عبر {count} تقييمات مكتملة",
    "dash.feedback": "آراء القراء",
    "dash.feedback_value": "{helpful} مفيدة من أصل {total}",
    "dash.feedback_none": "لا توجد آراء بعد.",
    "heat.title": "خريطة الأسئلة",
    "heat.lead": "مربع لكل سؤال، بترتيب الجدول. انقر لعرض السطر.",
    "heat.group": "{label}: {passed}/{total} ناجحة",
    "heat.cell_aria": "{qid}: {outcome}",
    "reports.status.finished_sentence": "انتهى التقييم.",
    # ---- عبارات تُبنى في Python ----
    "phr.sources_promise": "كل إجابة تذكر المصادر التي كُتبت انطلاقًا منها.",
    "phr.sample": "ماذا يتضمن «{name}»؟",
    "phr.no_documents_reason": (
        "لا يحتوي هذا الفضاء على وثائق متزامنة بعد، لذلك لا يوجد ما يمكن الإجابة منه. "
        "أضف مجلدًا ثم شغّل المزامنة من شاشة الفضاءات."
    ),
    "phr.busy_reason": "سند يجيب عن سؤالك الأخير.",
    "phr.stage.preparing": "تهيئة السؤال",
    "phr.stage.searching": "البحث في الفضاء",
    "phr.stage.checking": "التحقق من الإجابة",
    "phr.stage.writing": "الكتابة",
    "phr.route.no_match": (
        "لا يبدو أن أيًّا من فضاءاتك يناسب هذا السؤال. اختر فضاءً من القائمة أعلاه ثم "
        "اطرح السؤال مجددًا."
    ),
    "phr.route.proposal": "يبدو أن هذا السؤال يخص {name}. هل تريد الإجابة منه؟",
    "phr.error.sentence": "تعذّر على سند الإجابة عن هذا السؤال.",
    "phr.error.asked": "السؤال المطروح: {question}",
    "phr.error.hint": (
        "لم يُختلق أي شيء بدل الإجابة. تحقّق من إعدادات "
        "النموذج في ملف .env ثم أعد المحاولة."
    ),
    "phr.interrupted": (
        "أوقفت هذه الإجابة. لم يُكتب أي شيء، فلا يوجد نص جزئي للعرض ولا شيء هنا يُعدّ "
        "إجابة نهائية. اطرح السؤال مجددًا لإعادة المحاولة."
    ),
    "phr.capacity": (
        "يضم هذا الفضاء {files} ملفًا و{pages} صفحة PDF مقيسة، وهو ما يتجاوز الحد "
        "الموصى به ({max_files} ملفًا أو {max_pages} صفحة). قسّمه إلى مجلدات أصغر قبل "
        "المزامنة الكبيرة المقبلة."
    ),
    "phr.status.added": "مُضاف",
    "phr.status.changed": "مُعدَّل",
    "phr.status.unchanged": "دون تغيير",
    "phr.status.failed": "فشل",
    "phr.status.removed": "محذوف",
    "phr.status.skipped": "متجاوَز",
    "phr.report.running": "جارٍ {done}/{total}",
    "phr.report.partial": "جزئي {done}/{total}",
    "phr.report.pass": "ناجح",
    "phr.report.fail": "راسب",
    "phr.report.grounded": "{passed}/{total} مستندة كليًا إلى المصادر",
    "phr.report.g1": "G1 الاستناد إلى المصادر",
    "phr.report.g2": "G2 الرفض الصادق",
    "phr.report.g3": "G3 المصادر في كل إجابة",
    "phr.report.in_scope": "ضمن النطاق",
    "phr.report.out_of_scope": "خارج النطاق",
    "phr.report.not_judged": "لم يُقيَّم",
    "phr.report.not_final": "غير نهائي",
    "phr.report.yes": "نعم",
    "phr.report.no": "لا",
    "phr.report.file_error": (
        "ملف التقرير الكامل مفقود أو غير مقروء أو قديم ({path}). تُعرض أدناه النسخة "
        "المحفوظة في قاعدة البيانات. قد لا تتضمن عمليات التقييم القديمة نوع الإجابة أو "
        "وجود المصادر أو تفاصيل الأخطاء؛ وكل معيار لا تتوفر له أدلة كافية يوسم بأنه لم يُقيَّم."
    ),
    "phr.feedback.helpful": "مفيدة",
    "phr.feedback.not_helpful": "غير مفيدة",
    "phr.feedback.gone": "لم تعد هذه الإجابة معروضة، لذلك تعذّر حفظ ملاحظتك.",
    "phr.feedback.too_long": "تعذّر حفظ الملاحظة: يتجاوز التعليق {max} حرفًا.",
    "phr.feedback.invalid": "تعذّر حفظ الملاحظة: قيمة غير صالحة.",
    "phr.delete.sync_running": (
        "لا يمكن حذف هذا الفضاء أثناء مزامنته. ألغِ المزامنة أو انتظر انتهاءها، ثم أعد المحاولة."
    ),
    "phr.delete.store_busy": (
        "لا يمكن حذف هذا الفضاء ما دام فهرسه مستخدمًا من طرف أمر التقييم. انتظر انتهاءه، "
        "ثم أعد المحاولة."
    ),
    "phr.evidence_only": (
        "هذه النسخة المنشورة للقراءة فقط: تعرض تقارير التقييم وتفاصيل الفضاءات، لكنها لا "
        "تستطيع الإجابة عن الأسئلة ولا تشغيل المزامنة، لأن كليهما يحتاج نموذج الفهرسة الذي "
        "يتجاوز ذاكرة هذه الحاوية. شغّل سند محليًا لطرح الأسئلة أو فهرسة الوثائق."
    ),
    "phr.folder_missing": (
        "مجلد الفضاء غير موجود أو ليس مجلدًا: {path}. تحقّق من المسار، أو أعد توصيل القرص "
        "إن كان قابلًا للإزالة أو على الشبكة."
    ),
    "phr.sync_running": (
        "مزامنة بدأت في {started} ما تزال جارية للفضاء {workspace}؛ ستستمر ولم يتم بدء هذا الطلب"
    ),
    "phr.name_in_use": "اسم الفضاء مستخدم مسبقًا: {name}",
    "phr.name_length": "يجب أن يتراوح طول اسم الفضاء بين {min} و{max} حرفًا: {name}",
    "phr.folder_empty": "لا يمكن أن يكون مسار المجلد فارغًا: {path}",
    "phr.reason.unsupported": "نوع ملف غير مدعوم",
    "phr.reason.uninspectable": (
        "تعذّر فحص الملف ({error})، فتُرك دون تغيير وما تزال مقاطعه السابقة تُستعمل في الإجابات"
    ),
    "phr.reason.pdf_damaged": (
        "ملف PDF تالف أو ليس PDF حقيقيًا. افتحه بقارئ "
        "PDF للتحقق، ثم أعد المزامنة"
    ),
    "phr.reason.pdf_locked": (
        "ملف PDF محمي بكلمة مرور. أزل كلمة المرور واحفظ "
        "نسخة دونها، ثم أعد المزامنة"
    ),
    "phr.reason.pdf_no_text": (
        "لا يحتوي ملف PDF هذا على طبقة نصية، فهو ممسوح ضوئيًا أو صور فقط. لا يستطيع سند "
        "بعدُ قراءة النص من الصور، لذلك لم تتم فهرسة أي شيء"
    ),
    "phr.reason.ocr_no_text": (
        "هذا الملف ممسوح ضوئيًا ولم يعثر التعرف الضوئي على أي نص مقروء فيه. تحقّق من أن "
        "الصفحات ليست فارغة أو مقلوبة، ثم أعد المزامنة"
    ),
    "phr.reason.ocr_too_long": (
        "يضم ملف PDF الممسوح {pages} صفحة، أي أكثر من حد التعرف الضوئي البالغ {limit} صفحة، "
        "فلم تتم معالجته. قسّمه إلى ملفات أصغر، ثم أعد المزامنة"
    ),
    "phr.reason.docx_damaged": (
        "ملف DOCX تالف أو ليس ملف Word حقيقيًا. افتحه في "
        "Word للتحقق، ثم أعد المزامنة"
    ),
    "phr.reason.pptx_damaged": (
        "ملف PPTX تالف أو ليس ملف PowerPoint حقيقيًا. افتحه في PowerPoint للتحقق، ثم أعد المزامنة"
    ),
    "phr.reason.empty": "لا يحتوي الملف على أي نص",
    "phr.reason.undecodable": (
        "هذا الملف ليس نصًا صالحًا بترميز UTF-8 فتعذّرت قراءته. افتحه وأعد حفظه بترميز "
        "UTF-8، ثم أعد المزامنة"
    ),
    "phr.reason.unreadable": "تعذّرت قراءة الملف: {detail}",
    "phr.reason.removed": "لم يعد الملف موجودًا في مجلد الفضاء، لذلك أُزيلت مقاطعه من الإجابات",
    "phr.reason.index_failed": "تعذّرت فهرسة الملف: {detail}",
    "phr.reason.cancelled": "أُلغيت المزامنة قبل معالجة هذا الملف",
}
