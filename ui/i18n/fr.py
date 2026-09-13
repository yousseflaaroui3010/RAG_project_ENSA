"""Catalogue français (langue par défaut de l'interface).

Typographie : espace fine insécable (U+202F, écrite `\\u202f`) avant « ? »,
« ! », « : » et « ; », guillemets français « … » avec espaces fines, vouvoiement.
Même jeu de clés que `en.py` ; `tests/unit/test_i18n.py` le vérifie.
"""

NNBSP = "\u202f"

MESSAGES: dict[str, str] = {
    # ---- Coquille (base.html) ----
    "title.app": "Sanad",
    "title.chat": "Assistant — Sanad",
    "title.workspaces": "Espaces de travail — Sanad",
    "title.reports": "Rapports — Sanad",
    "title.report_detail": "Détail du rapport — Sanad",
    "title.passage": "Extrait — Sanad",
    "title.delete": "Supprimer {name} — Sanad",
    "shell.skip": "Aller au contenu",
    "shell.brand": "Sanad",
    "shell.active_workspace": "Espace actif",
    "shell.let_sanad_choose": "Laisser Sanad choisir",
    "shell.legal_option": "juridique",
    "shell.switch": "Changer",
    "shell.legal_marker": "Juridique",
    "shell.legal_marker_title": "Cet espace contient des textes juridiques",
    "shell.no_workspace": "Aucun espace pour l’instant",
    "shell.nav_label": "Écrans",
    "shell.nav.chat": "Assistant",
    "shell.nav.chat_disabled_title": "Créez un espace de travail avant de poser une question",
    "shell.nav.workspaces": "Espaces",
    "shell.nav.reports": "Rapports",
    "shell.dark_theme": "Thème sombre",
    "shell.language": "Langue",
    "shell.desktop_only": (
        "Sanad est conçu pour un navigateur d’ordinateur. Cette fenêtre est trop étroite "
        "pour afficher à la fois un document, ses sources et l’extrait cité. "
        "Agrandissez la fenêtre pour continuer."
    ),
    # ---- S1 Assistant (chat.html) ----
    "chat.no_workspace.title": "Aucun espace de travail",
    "chat.no_workspace.body": (
        "Sanad répond à partir des documents regroupés dans un espace de travail. "
        "Tant qu’aucun espace n’existe, il n’y a rien à interroger."
    ),
    "chat.no_workspace.link": "Créer un espace dans l’écran Espaces",
    "chat.title": "Assistant",
    "chat.answering_from": "Réponses tirées de",
    "chat.will_pick": "Sanad choisira l’espace dès que vous poserez votre question.",
    "chat.new_conversation": "Nouvelle conversation",
    "chat.your_question": "Votre question",
    "chat.placeholder": "Posez une question sur cet espace",
    "chat.send": "Envoyer",
    "chat.hint": (
        "Appuyez sur Entrée pour envoyer. Chaque réponse cite "
        "les passages sur lesquels elle s’appuie."
    ),
    # ---- Conversation (_conversation.html) ----
    "conv.aria": "Conversation",
    "conv.feedback.helpful": "Utile",
    "conv.feedback.what_wrong": f"Qu’est-ce qui n’allait pas{NNBSP}? (facultatif)",
    "conv.feedback.not_helpful": "Pas utile",
    "conv.feedback.saved": "Merci — votre avis est enregistré.",
    "conv.trace.summary": "Comment cette réponse a été trouvée",
    "conv.trace.searches": "Recherches effectuées",
    "conv.trace.none": "Aucune.",
    "conv.trace.files": "Fichiers consultés",
    "conv.trace.retries": f"Nouvelles tentatives{NNBSP}: {{value}}",
    "conv.trace.retries_none": "aucune",
    "conv.moved.before": "Le contexte de la conversation est désormais",
    "conv.moved.after": "Les réponses précédentes de cet écran provenaient d’un autre espace.",
    "conv.moved.routing": (
        "Le contexte de la conversation a changé. Posez une question et Sanad proposera "
        "un espace avant de répondre."
    ),
    "conv.no_docs.title": "Rien à consulter pour l’instant",
    "conv.no_docs.body_html": (
        "<bdi>{name}</bdi> ne contient aucun document synchronisé, Sanad n’a donc rien à "
        "lire. Associez l’espace à un dossier puis lancez la synchronisation."
    ),
    "conv.no_docs.link": "Lancer la synchronisation dans l’écran Espaces",
    "conv.empty.title_html": "Posez une question sur <bdi>{name}</bdi>",
    "conv.steps.aria": "Comment Sanad répond",
    "conv.steps.1_html": "<strong>Recherche</strong> dans les documents de l’espace",
    "conv.steps.2_html": "<strong>Vérifie</strong> que chaque passage est pertinent",
    "conv.steps.3_html": "<strong>Répond</strong> avec ses sources, ou dit qu’il ne sait pas",
    "conv.routing.title": "Posez votre question, Sanad choisira l’espace",
    "conv.routing.body": (
        "Sanad cherche dans chaque espace la meilleure correspondance, puis vous demande "
        "de confirmer avant de rédiger quoi que ce soit."
    ),
    "conv.answer.head": "Réponse",
    "conv.answer.sources.one": "{count} source",
    "conv.answer.sources.other": "{count} sources",
    "conv.evidence.aria": "Sources sur lesquelles repose cette réponse",
    "conv.evidence.label": "Fondée sur",
    "conv.retries.title": "Sanad a reformulé la recherche {count} fois avant de répondre",
    "conv.retries.label.one": "{count} reformulation",
    "conv.retries.label.other": "{count} reformulations",
    "conv.refusal.head": "Introuvable dans cet espace",
    "conv.refusal.searched": f"Ce que Sanad a recherché{NNBSP}:",
    "conv.refusal.reworded": "Reformulée {count} fois avant d’abandonner.",
    "conv.clarify.head": "Une précision d’abord",
    "conv.route.yes_html": "Oui, utiliser <bdi>{name}</bdi>",
    "conv.incomplete": "Incomplet — ce n’est pas une réponse",
    "conv.partial.note": (
        "Vous avez arrêté la rédaction. Le texte ci-dessus est inachevé "
        "et n’est rattaché à aucune source."
    ),
    "conv.streaming.head": "Rédaction en cours",
    "conv.disclaimer": (
        "Information à titre indicatif, ne constitue pas un avis juridique. "
        "Consultez un professionnel qualifié."
    ),
    "conv.cancel": "Annuler",
    # ---- Sources et extraits ----
    "sources.aria": "Sources de cette réponse",
    "sources.title": "Sources ({count})",
    "sources.open": "Ouvrir l’extrait",
    "sources.close": "Fermer",
    "passage.not_located": (
        "Affichage de la section entière. Sanad n’a pas pu repérer précisément le passage "
        "retrouvé : rien n’est donc surligné comme texte cité."
    ),
    "passage.back": "Retour à la conversation",
    "passage.gone.title": "Cet extrait n’est plus affiché",
    "passage.gone.body": (
        "La conversation dont il faisait partie a été remplacée ou effacée : la section "
        "citée n’est plus chargée."
    ),
    "passage.gone.hint": "Posez à nouveau la question pour obtenir une citation à jour.",
    # ---- S2 Espaces ----
    "files.caption": "Dernier rapport de synchronisation",
    "files.col.name": "Nom",
    "files.col.type": "Type",
    "files.col.size": "Taille",
    "files.col.status": "État",
    "files.col.reason": "Motif",
    "ws.form.name": "Nom de l’espace",
    "ws.form.name_placeholder": "p. ex. Politiques RH",
    "ws.form.folder": "Chemin du dossier",
    "ws.form.folder_placeholder": "p. ex. C:\\Documents\\RH",
    "ws.form.legal": "Cet espace contient des textes juridiques",
    "ws.form.legal_help": (
        "Ajoute une mention d’avertissement à chaque réponse de cet espace. "
        "Cela ne restreint pas l’accès et n’empêche pas la suppression."
    ),
    "ws.form.create": "Créer l’espace",
    "ws.detail.aria": "Détail de l’espace",
    "ws.detail.pick": "Choisissez un espace dans la liste pour voir son détail.",
    "ws.detail.settings": "Renommer, mention juridique, supprimer",
    "ws.detail.rename": "Renommer",
    "ws.detail.save": "Enregistrer",
    "ws.detail.delete": "Supprimer l’espace…",
    "ws.sync.blocked": (
        "Une synchronisation est déjà en cours pour cet espace ; elle continue, "
        "et cette nouvelle demande n’a pas été lancée."
    ),
    "ws.sync.processed.one": "{count} fichier traité jusqu’ici",
    "ws.sync.processed.other": "{count} fichiers traités jusqu’ici",
    "ws.sync.scanning": "Analyse du dossier de l’espace…",
    "ws.sync.started": "Démarrée le {when}.",
    "ws.sync.cancel": "Annuler après le fichier en cours",
    "ws.sync.run": "Synchroniser",
    "ws.sync.error": "La synchronisation n’a pas pu démarrer.",
    "ws.sync.pending_report": "Le rapport s’affichera ici à la fin de cette synchronisation.",
    "ws.sync.finished": "Dernière synchronisation terminée le {when}.",
    "ws.sync.never": "Cet espace n’a pas encore été synchronisé.",
    "ws.first.title": "Créez votre premier espace",
    "ws.first.body": (
        "Sanad répond à partir des documents regroupés dans un espace de travail. "
        "Tant qu’aucun espace n’existe, il n’y a rien à synchroniser ni à interroger."
    ),
    "ws.list.aria": "Espaces de travail",
    "ws.list.title": "Espaces de travail",
    "ws.watch.on": f"Surveillance des nouveaux fichiers{NNBSP}: activée",
    "ws.watch.off": f"Surveillance des nouveaux fichiers{NNBSP}: désactivée",
    "ws.list.new": "Nouvel espace",
    "del.title_html": f"Supprimer «{NNBSP}<bdi>{{name}}</bdi>{NNBSP}»{NNBSP}?",
    "del.body_html": (
        "Cette action supprime l’index synchronisé de <bdi>{name}</bdi> — tous les "
        "passages à partir desquels Sanad peut répondre — ainsi que son historique de "
        "synchronisation. Elle <strong>ne touche pas</strong> aux fichiers du dossier"
    ),
    "del.body_after": (
        "Ils restent sur le disque tels quels ; seule la copie lue par Sanad est supprimée."
    ),
    "del.yes_html": "Oui, supprimer <bdi>{name}</bdi>",
    "del.cancel": "Annuler, conserver cet espace",
    # ---- S3 Rapports ----
    "rep.empty.title": "Aucun rapport d’évaluation pour l’instant",
    "rep.empty.body": (
        "Les rapports s’affichent ici dès que l’évaluation sur le jeu de référence a été "
        f"lancée au moins une fois. Lancez-la depuis un terminal{NNBSP}:"
    ),
    "rep.aria": "Rapports d’évaluation",
    "rep.title": "Rapports",
    "rep.lead": "Évaluations sur le jeu de référence et critères de mise en production atteints.",
    "rep.caption": "Évaluations",
    "rep.col.date": "Date",
    "rep.col.workspace": "Espace",
    "rep.col.groundedness": "Ancrage",
    "rep.col.refusals": "Refus",
    "rep.col.sources": "Sources",
    "rep.col.outcome": "Résultat",
    "rep.open_aria": "Ouvrir le rapport du {when} pour {name}",
    "fb.aria": "Avis sur les réponses",
    "fb.title": "Avis sur les réponses",
    "fb.caption": "Avis laissés sur les réponses",
    "fb.col.date": "Date",
    "fb.col.workspace": "Espace",
    "fb.col.verdict": "Avis",
    "fb.col.question": "Question",
    "fb.col.comment": "Commentaire",
    "fb.none": "Aucun avis pour l’instant.",
    "rd.missing": "Ce rapport n’existe pas.",
    "rd.back_all": "Retour à tous les rapports",
    "rd.aria": "Détail du rapport",
    "rd.final.partial": "Évaluation interrompue avec des résultats partiels.",
    "rd.final.completed": "Évaluation terminée.",
    "rd.all": "Tous les rapports",
    "rd.running": f"Évaluation en cours{NNBSP}: {{done}}/{{total}} questions traitées.",
    "rd.partial": f"Partiel{NNBSP}: arrêt à la question {{number}} sur {{total}} ({{qid}}).",
    "rd.kept.one": "{count} question traitée conservée.",
    "rd.kept.other": "{count} questions traitées conservées.",
    "rd.not_final": "Provisoire",
    "rd.not_judged": "Non évalué",
    "rd.pass": "Réussi",
    "rd.fail": "Échec",
    "rd.gates": "Critères de mise en production",
    "rd.col.metric": "Critère",
    "rd.col.value": "Valeur",
    "rd.col.threshold": "Seuil",
    "rd.col.outcome": "Résultat",
    "rd.file_unavailable": "Le fichier détaillé question par question est indisponible.",
    "rd.questions": "Résultats par question",
    "rd.col.question": "Question",
    "rd.col.kind": "Type",
    "rd.col.groundedness": "Ancrage",
    "rd.col.relevancy": "Pertinence",
    "rd.col.sources": "Sources",
    "rd.col.error": "Erreur",
    "rd.export": "Exporter en Markdown pour l’annexe du rapport",
    "reports.status.finished_sentence": "Évaluation terminée.",
    # ---- Phrases construites en Python ----
    "phr.sources_promise": (
        "Chaque réponse indique les sources à partir "
        "desquelles elle a été rédigée."
    ),
    "phr.sample": f"Que contient «{NNBSP}{{name}}{NNBSP}»{NNBSP}?",
    "phr.no_documents_reason": (
        "Cet espace ne contient encore aucun document synchronisé : il n’y a rien à "
        "consulter. Ajoutez un dossier puis lancez la synchronisation dans l’écran Espaces."
    ),
    "phr.busy_reason": "Sanad répond à votre dernière question.",
    "phr.stage.preparing": "Préparation de la question",
    "phr.stage.searching": "Recherche dans l’espace",
    "phr.stage.checking": "Vérification de la réponse",
    "phr.stage.writing": "Rédaction",
    "phr.route.no_match": (
        "Aucun de vos espaces ne semble correspondre à cette question. Choisissez-en un "
        "dans le sélecteur ci-dessus et reposez-la."
    ),
    "phr.route.proposal": (
        f"Cette question semble concerner {{name}}. "
        f"Répondre à partir de cet espace{NNBSP}?"
    ),
    "phr.error.sentence": "Sanad n’a pas pu répondre à cette question.",
    "phr.error.asked": f"Question posée{NNBSP}: {{question}}",
    "phr.error.hint": (
        "Rien n’a été inventé à la place d’une réponse. Vérifiez les paramètres du modèle "
        "dans .env, puis réessayez."
    ),
    "phr.interrupted": (
        "Vous avez arrêté cette réponse. Rien n’a été rédigé : il n’y a pas de texte "
        "partiel à afficher, et rien ici n’est une réponse finale. Reposez la question "
        "pour réessayer."
    ),
    "phr.capacity": (
        "Cet espace contient {files} fichiers et {pages} pages PDF mesurées, au-delà de la "
        "limite recommandée de {max_files} fichiers ou {max_pages} pages. Répartissez-le en "
        "dossiers plus petits avant la prochaine grosse synchronisation."
    ),
    "phr.status.added": "Ajouté",
    "phr.status.changed": "Modifié",
    "phr.status.unchanged": "Inchangé",
    "phr.status.failed": "Échec",
    "phr.status.removed": "Retiré",
    "phr.status.skipped": "Ignoré",
    "phr.report.running": "En cours {done}/{total}",
    "phr.report.partial": "Partiel {done}/{total}",
    "phr.report.pass": "Réussi",
    "phr.report.fail": "Échec",
    "phr.report.grounded": "{passed}/{total} entièrement ancrées",
    "phr.report.g1": "G1 Ancrage dans les sources",
    "phr.report.g2": "G2 Refus honnêtes",
    "phr.report.g3": "G3 Sources sur chaque réponse",
    "phr.report.in_scope": "Dans le périmètre",
    "phr.report.out_of_scope": "Hors périmètre",
    "phr.report.not_judged": "Non évalué",
    "phr.report.not_final": "Provisoire",
    "phr.report.yes": "Oui",
    "phr.report.no": "Non",
    "phr.report.file_error": (
        "Le fichier de rapport complet est absent, illisible ou périmé ({path}). La copie "
        "conservée en base est affichée ci-dessous. Les anciennes évaluations peuvent ne "
        "pas contenir le type de réponse, la présence de sources ou le détail des erreurs ; "
        "tout critère sans preuve suffisante est marqué non évalué."
    ),
    "phr.feedback.helpful": "Utile",
    "phr.feedback.not_helpful": "Pas utile",
    "phr.feedback.gone": (
        "Cette réponse n’est plus affichée : votre avis "
        "n’a pas pu être enregistré."
    ),
    "phr.feedback.too_long": (
        f"Votre avis n’a pas pu être enregistré{NNBSP}: le commentaire dépasse {{max}} caractères."
    ),
    "phr.feedback.invalid": f"Votre avis n’a pas pu être enregistré{NNBSP}: réponse invalide.",
    "phr.delete.sync_running": (
        "Impossible de supprimer cet espace pendant sa synchronisation. Annulez-la ou "
        "attendez qu’elle se termine, puis réessayez."
    ),
    "phr.delete.store_busy": (
        "Impossible de supprimer cet espace tant que son index est utilisé par la commande "
        "d’évaluation. Attendez la fin de l’évaluation, puis réessayez."
    ),
    "phr.evidence_only": (
        "Cette instance publiée est en lecture seule : elle affiche les rapports "
        "d’évaluation et le détail des espaces, mais ne peut ni répondre aux questions ni "
        "synchroniser. Ces deux fonctions nécessitent le modèle d’indexation, trop "
        "volumineux pour la mémoire de ce conteneur. Lancez Sanad en local pour poser des "
        "questions ou indexer des documents."
    ),
    "phr.folder_missing": (
        "le dossier de l’espace n’existe pas ou n’est pas un répertoire : {path}. Vérifiez "
        "le chemin, ou reconnectez le disque s’il est amovible ou en réseau."
    ),
    "phr.sync_running": (
        "une synchronisation démarrée le {started} est toujours en cours pour l’espace "
        "{workspace} ; elle continue et cette demande n’a pas été lancée"
    ),
    "phr.name_in_use": f"ce nom d’espace est déjà utilisé{NNBSP}: {{name}}",
    "phr.name_length": (
        f"le nom de l’espace doit comporter entre {{min}} et {{max}} caractères{NNBSP}: {{name}}"
    ),
    "phr.folder_empty": f"le chemin du dossier ne peut pas être vide{NNBSP}: {{path}}",
    "phr.reason.unsupported": "type de fichier non pris en charge",
    "phr.reason.uninspectable": (
        "le fichier n’a pas pu être examiné ({error}) : il a été laissé tel quel et ses "
        "passages existants continuent de servir aux réponses"
    ),
    "phr.reason.pdf_damaged": (
        "le PDF est endommagé ou n’est pas un vrai PDF. Ouvrez-le dans un lecteur PDF pour "
        "le vérifier, puis synchronisez à nouveau"
    ),
    "phr.reason.pdf_locked": (
        "le PDF est protégé par un mot de passe. Retirez le mot de passe, enregistrez une "
        "copie sans protection, puis synchronisez à nouveau"
    ),
    "phr.reason.pdf_no_text": (
        "ce PDF n’a pas de couche texte : c’est un scan ou des images. Sanad ne peut pas "
        "encore lire le texte d’une image, rien n’a donc été indexé"
    ),
    "phr.reason.ocr_no_text": (
        "ce PDF est un scan et la reconnaissance de texte n’y a trouvé aucun texte lisible. "
        "Vérifiez que les pages ne sont ni vides ni à l’envers, puis synchronisez à nouveau"
    ),
    "phr.reason.ocr_too_long": (
        "ce PDF scanné compte {pages} pages, au-delà de la limite de {limit} pages pour la "
        "reconnaissance de texte : il n’a pas été traité. Découpez-le en fichiers plus "
        "petits, puis synchronisez à nouveau"
    ),
    "phr.reason.docx_damaged": (
        "le DOCX est endommagé ou n’est pas un vrai fichier Word. Ouvrez-le dans Word pour "
        "le vérifier, puis synchronisez à nouveau"
    ),
    "phr.reason.pptx_damaged": (
        "le PPTX est endommagé ou n’est pas un vrai fichier PowerPoint. Ouvrez-le dans "
        "PowerPoint pour le vérifier, puis synchronisez à nouveau"
    ),
    "phr.reason.empty": "le fichier ne contient aucun texte",
    "phr.reason.undecodable": (
        "ce fichier n’est pas du texte UTF-8 valide et n’a pas pu être lu. Ouvrez-le et "
        "réenregistrez-le en UTF-8, puis synchronisez à nouveau"
    ),
    "phr.reason.unreadable": f"le fichier n’a pas pu être lu{NNBSP}: {{detail}}",
    "phr.reason.removed": (
        "le fichier ne se trouve plus dans le dossier de l’espace : ses passages ont été "
        "retirés des réponses"
    ),
    "phr.reason.index_failed": f"le fichier n’a pas pu être indexé{NNBSP}: {{detail}}",
    "phr.reason.cancelled": "La synchronisation a été annulée avant le traitement de ce fichier",
}


def _french_spacing(text: str) -> str:
    """Any ordinary space left before « : ; ? ! » becomes the narrow no-break
    space French typography requires, so a line never breaks before them."""
    for mark in (":", ";", "?", "!"):
        text = text.replace(f" {mark}", f"{NNBSP}{mark}")
    return text


MESSAGES = {key: _french_spacing(value) for key, value in MESSAGES.items()}
