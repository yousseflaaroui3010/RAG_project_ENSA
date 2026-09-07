# Corpus v1 (ST-07) -- provenance record

GENERATED FILE. Do not edit: it is written by
`uv run python scripts/corpus.py sources` from the manifest in
`scripts/corpus.py`, which is the tracked source of truth. Editing
this copy changes nothing and will be overwritten.

## Workspace: hr (`data/corpus/hr/`)

### `code-travail-consolide-2011-justice.pdf`

- **Title:** Code du travail, loi n° 65-99, version consolidée au 26 octobre 2011
- **Publisher:** Royaume du Maroc, Ministère de la Justice -- portail Adala (adala.justice.gov.ma), Direction de la Législation
- **Published:** 2011-10-26 (consolidation)
- **Retrieved:** 2026-08-29
- **Authority:** primary -- official consolidated legal text
- **URL:** https://adala.justice.gov.ma/api/uploads/2024/04/30/code%20du%20travail-1714463246806.pdf
- **On disk:** 1,515,526 bytes, sha256 `91c67dd23c5a2d9a` (recorded, NOT pinned -- see the note at the top of `scripts/corpus.py`)

The flagship document. CONSOLIDATED, so it carries the amendments through 2011 and lists them by dahir on its own first pages. Chosen over the ILO's 2004 Bulletin Officiel edition that this corpus previously used: both are named as verified sources in PRD section 17, but the 2004 edition is the text as first promulgated, and an HR generalist answering a question in 2026 from the unamended 2004 wording is the exact failure this product exists to prevent. Only ONE edition of the code is in the corpus on purpose -- two near-identical copies would compete for the same retrieval hit and make the ST-19 golden set score noise.

### `dahir-1-72-184-securite-sociale-acaps.pdf`

- **Title:** Dahir portant loi n° 1-72-184 du 27 juillet 1972 relatif au régime de sécurité sociale, tel que modifié et complété
- **Publisher:** Autorité de Contrôle des Assurances et de la Prévoyance Sociale (ACAPS), the Moroccan state regulator
- **Published:** 1972-07-27, as amended
- **Retrieved:** 2026-08-29
- **Authority:** primary -- official legal text, regulator's own copy
- **URL:** https://www.acaps.ma/fr/files/dahir1-72-184pdf
- **On disk:** 122,626 bytes, sha256 `9618aa36950ed0ff` (recorded, NOT pinned -- see the note at the top of `scripts/corpus.py`)

The law the CNSS runs on, which is the other half of the HR generalist's daily question: the labour code says what an employee is owed, this says what is declared and contributed for them. Sourced from ACAPS rather than from a summary site because it is the regulator publishing the text it enforces.

### `cnss-regime-securite-sociale-cleiss.pdf`

- **Title:** Le régime marocain de sécurité sociale (salariés)
- **Publisher:** CLEISS, Centre des liaisons européennes et internationales de sécurité sociale (French public body), via Université Toulouse 2
- **Published:** undated edition, 'version n2'
- **Retrieved:** 2026-08-23
- **Authority:** secondary -- explanatory guide from a public body
- **URL:** https://www.univ-tlse2.fr/medias/fichier/maroc-regime-de-securite-sociale-pour-salaries-version-n2
- **On disk:** 208,172 bytes, sha256 `80ee2b2d58dbebd6` (recorded, NOT pinned -- see the note at the top of `scripts/corpus.py`)

The one deliberately SECONDARY document, and it earns its place: the two texts above are law, written as law, and a corpus of nothing but statute cannot answer 'how does this work in practice'. CLEISS is a French public body, not a commercial publisher. Labelled secondary here so nobody cites it in the report as if it were Moroccan law.

## Workspace: manuals (`data/corpus/manuals/`)

### `tutorial-introduction.txt`

- **Title:** Documentation Python 3.14 en français -- tutorial/introduction
- **Publisher:** Python Software Foundation, docs.python.org (French translation)
- **Published:** Python 3.14 documentation
- **Retrieved:** 2026-08-23
- **Authority:** primary -- the project's own official manual
- **URL:** https://docs.python.org/fr/3/archives/python-3.14-docs-text.zip
- **On disk:** 21,077 bytes, sha256 `cb8e206b00a2f818` (recorded, NOT pinned -- see the note at the top of `scripts/corpus.py`)
- **Archive member:** `python-3.14-docs-text/tutorial/introduction.txt`

French on purpose, and this is the reason the workspace is these files rather than any ten manuals. It shares ordinary French vocabulary with the labour code -- 'durée', 'conditions', 'article', 'obligations' -- so F-01's isolation claim ('an HR question never pulls passages from the technical manuals') has to be earned on similar text. ST-16 recorded the opposite failure: its first isolation corpus was so different that isolation passed by accident. It also exercises the TXT rung of the conversion ladder while the hr workspace exercises the PDF rung, so one sync covers both.

### `tutorial-controlflow.txt`

- **Title:** Documentation Python 3.14 en français -- tutorial/controlflow
- **Publisher:** Python Software Foundation, docs.python.org (French translation)
- **Published:** Python 3.14 documentation
- **Retrieved:** 2026-08-23
- **Authority:** primary -- the project's own official manual
- **URL:** https://docs.python.org/fr/3/archives/python-3.14-docs-text.zip
- **On disk:** 44,505 bytes, sha256 `20554651798a28c5` (recorded, NOT pinned -- see the note at the top of `scripts/corpus.py`)
- **Archive member:** `python-3.14-docs-text/tutorial/controlflow.txt`

French on purpose, and this is the reason the workspace is these files rather than any ten manuals. It shares ordinary French vocabulary with the labour code -- 'durée', 'conditions', 'article', 'obligations' -- so F-01's isolation claim ('an HR question never pulls passages from the technical manuals') has to be earned on similar text. ST-16 recorded the opposite failure: its first isolation corpus was so different that isolation passed by accident. It also exercises the TXT rung of the conversion ladder while the hr workspace exercises the PDF rung, so one sync covers both.

### `tutorial-datastructures.txt`

- **Title:** Documentation Python 3.14 en français -- tutorial/datastructures
- **Publisher:** Python Software Foundation, docs.python.org (French translation)
- **Published:** Python 3.14 documentation
- **Retrieved:** 2026-08-23
- **Authority:** primary -- the project's own official manual
- **URL:** https://docs.python.org/fr/3/archives/python-3.14-docs-text.zip
- **On disk:** 27,588 bytes, sha256 `8f6cc8afbdbdef56` (recorded, NOT pinned -- see the note at the top of `scripts/corpus.py`)
- **Archive member:** `python-3.14-docs-text/tutorial/datastructures.txt`

French on purpose, and this is the reason the workspace is these files rather than any ten manuals. It shares ordinary French vocabulary with the labour code -- 'durée', 'conditions', 'article', 'obligations' -- so F-01's isolation claim ('an HR question never pulls passages from the technical manuals') has to be earned on similar text. ST-16 recorded the opposite failure: its first isolation corpus was so different that isolation passed by accident. It also exercises the TXT rung of the conversion ladder while the hr workspace exercises the PDF rung, so one sync covers both.

### `tutorial-modules.txt`

- **Title:** Documentation Python 3.14 en français -- tutorial/modules
- **Publisher:** Python Software Foundation, docs.python.org (French translation)
- **Published:** Python 3.14 documentation
- **Retrieved:** 2026-08-23
- **Authority:** primary -- the project's own official manual
- **URL:** https://docs.python.org/fr/3/archives/python-3.14-docs-text.zip
- **On disk:** 26,600 bytes, sha256 `f8c8de71dc40fa2e` (recorded, NOT pinned -- see the note at the top of `scripts/corpus.py`)
- **Archive member:** `python-3.14-docs-text/tutorial/modules.txt`

French on purpose, and this is the reason the workspace is these files rather than any ten manuals. It shares ordinary French vocabulary with the labour code -- 'durée', 'conditions', 'article', 'obligations' -- so F-01's isolation claim ('an HR question never pulls passages from the technical manuals') has to be earned on similar text. ST-16 recorded the opposite failure: its first isolation corpus was so different that isolation passed by accident. It also exercises the TXT rung of the conversion ladder while the hr workspace exercises the PDF rung, so one sync covers both.

### `tutorial-inputoutput.txt`

- **Title:** Documentation Python 3.14 en français -- tutorial/inputoutput
- **Publisher:** Python Software Foundation, docs.python.org (French translation)
- **Published:** Python 3.14 documentation
- **Retrieved:** 2026-08-23
- **Authority:** primary -- the project's own official manual
- **URL:** https://docs.python.org/fr/3/archives/python-3.14-docs-text.zip
- **On disk:** 22,247 bytes, sha256 `b71ded900d49b1ae` (recorded, NOT pinned -- see the note at the top of `scripts/corpus.py`)
- **Archive member:** `python-3.14-docs-text/tutorial/inputoutput.txt`

French on purpose, and this is the reason the workspace is these files rather than any ten manuals. It shares ordinary French vocabulary with the labour code -- 'durée', 'conditions', 'article', 'obligations' -- so F-01's isolation claim ('an HR question never pulls passages from the technical manuals') has to be earned on similar text. ST-16 recorded the opposite failure: its first isolation corpus was so different that isolation passed by accident. It also exercises the TXT rung of the conversion ladder while the hr workspace exercises the PDF rung, so one sync covers both.

### `tutorial-errors.txt`

- **Title:** Documentation Python 3.14 en français -- tutorial/errors
- **Publisher:** Python Software Foundation, docs.python.org (French translation)
- **Published:** Python 3.14 documentation
- **Retrieved:** 2026-08-23
- **Authority:** primary -- the project's own official manual
- **URL:** https://docs.python.org/fr/3/archives/python-3.14-docs-text.zip
- **On disk:** 26,296 bytes, sha256 `5ae9129ccb049503` (recorded, NOT pinned -- see the note at the top of `scripts/corpus.py`)
- **Archive member:** `python-3.14-docs-text/tutorial/errors.txt`

French on purpose, and this is the reason the workspace is these files rather than any ten manuals. It shares ordinary French vocabulary with the labour code -- 'durée', 'conditions', 'article', 'obligations' -- so F-01's isolation claim ('an HR question never pulls passages from the technical manuals') has to be earned on similar text. ST-16 recorded the opposite failure: its first isolation corpus was so different that isolation passed by accident. It also exercises the TXT rung of the conversion ladder while the hr workspace exercises the PDF rung, so one sync covers both.

### `tutorial-classes.txt`

- **Title:** Documentation Python 3.14 en français -- tutorial/classes
- **Publisher:** Python Software Foundation, docs.python.org (French translation)
- **Published:** Python 3.14 documentation
- **Retrieved:** 2026-08-23
- **Authority:** primary -- the project's own official manual
- **URL:** https://docs.python.org/fr/3/archives/python-3.14-docs-text.zip
- **On disk:** 41,897 bytes, sha256 `33028e01c6c878a5` (recorded, NOT pinned -- see the note at the top of `scripts/corpus.py`)
- **Archive member:** `python-3.14-docs-text/tutorial/classes.txt`

French on purpose, and this is the reason the workspace is these files rather than any ten manuals. It shares ordinary French vocabulary with the labour code -- 'durée', 'conditions', 'article', 'obligations' -- so F-01's isolation claim ('an HR question never pulls passages from the technical manuals') has to be earned on similar text. ST-16 recorded the opposite failure: its first isolation corpus was so different that isolation passed by accident. It also exercises the TXT rung of the conversion ladder while the hr workspace exercises the PDF rung, so one sync covers both.

### `howto-logging.txt`

- **Title:** Documentation Python 3.14 en français -- howto/logging
- **Publisher:** Python Software Foundation, docs.python.org (French translation)
- **Published:** Python 3.14 documentation
- **Retrieved:** 2026-08-23
- **Authority:** primary -- the project's own official manual
- **URL:** https://docs.python.org/fr/3/archives/python-3.14-docs-text.zip
- **On disk:** 56,097 bytes, sha256 `d97138149de4717d` (recorded, NOT pinned -- see the note at the top of `scripts/corpus.py`)
- **Archive member:** `python-3.14-docs-text/howto/logging.txt`

French on purpose, and this is the reason the workspace is these files rather than any ten manuals. It shares ordinary French vocabulary with the labour code -- 'durée', 'conditions', 'article', 'obligations' -- so F-01's isolation claim ('an HR question never pulls passages from the technical manuals') has to be earned on similar text. ST-16 recorded the opposite failure: its first isolation corpus was so different that isolation passed by accident. It also exercises the TXT rung of the conversion ladder while the hr workspace exercises the PDF rung, so one sync covers both.

### `howto-sockets.txt`

- **Title:** Documentation Python 3.14 en français -- howto/sockets
- **Publisher:** Python Software Foundation, docs.python.org (French translation)
- **Published:** Python 3.14 documentation
- **Retrieved:** 2026-08-23
- **Authority:** primary -- the project's own official manual
- **URL:** https://docs.python.org/fr/3/archives/python-3.14-docs-text.zip
- **On disk:** 22,757 bytes, sha256 `312e4f8cb4f0fe0f` (recorded, NOT pinned -- see the note at the top of `scripts/corpus.py`)
- **Archive member:** `python-3.14-docs-text/howto/sockets.txt`

French on purpose, and this is the reason the workspace is these files rather than any ten manuals. It shares ordinary French vocabulary with the labour code -- 'durée', 'conditions', 'article', 'obligations' -- so F-01's isolation claim ('an HR question never pulls passages from the technical manuals') has to be earned on similar text. ST-16 recorded the opposite failure: its first isolation corpus was so different that isolation passed by accident. It also exercises the TXT rung of the conversion ladder while the hr workspace exercises the PDF rung, so one sync covers both.

### `faq-programming.txt`

- **Title:** Documentation Python 3.14 en français -- faq/programming
- **Publisher:** Python Software Foundation, docs.python.org (French translation)
- **Published:** Python 3.14 documentation
- **Retrieved:** 2026-08-23
- **Authority:** primary -- the project's own official manual
- **URL:** https://docs.python.org/fr/3/archives/python-3.14-docs-text.zip
- **On disk:** 86,607 bytes, sha256 `0979db295ff5c9c1` (recorded, NOT pinned -- see the note at the top of `scripts/corpus.py`)
- **Archive member:** `python-3.14-docs-text/faq/programming.txt`

French on purpose, and this is the reason the workspace is these files rather than any ten manuals. It shares ordinary French vocabulary with the labour code -- 'durée', 'conditions', 'article', 'obligations' -- so F-01's isolation claim ('an HR question never pulls passages from the technical manuals') has to be earned on similar text. ST-16 recorded the opposite failure: its first isolation corpus was so different that isolation passed by accident. It also exercises the TXT rung of the conversion ladder while the hr workspace exercises the PDF rung, so one sync covers both.
