"""ST-24 exit gate: F-03 and F-05 pass on fixtures, and an answer without
sources cannot render as final.

Reference: PRD F-03 ("the answer is written only from passages found in
the active workspace, and lists its sources"), F-05 ("it never fills a gap
with invented content"), architecture 5.2 boxes A/P/SRC and 7.5, and
BUILD-PLAN line 78.

WHAT IS REAL HERE, because that is the whole reason this file exists next
to the unit tests: a real embedded Qdrant under `tmp_path`, real chunking,
real parent JSON on disk, real hybrid search, and the real `retrieve`,
`grade`, `reword`, `fetch_parents` and `write_answer` ports. This is the
first test in the project where every port on the ANSWER path is the real
one -- ST-23's integration file still stubbed `write_answer`.

TWO THINGS ARE FAKED, both for reasons already written down: the two
ENCODERS, because the real ones download hundreds of megabytes
(`tests/fake_encoders.py`), and the CHAT MODEL, because
docs/phase2/CLAUDE.md's hard rule is that tests use a scripted fake and
carry no API keys.

WHAT THIS FILE THEREFORE DOES NOT PROVE, stated rather than left to be
assumed: that a real model writes a faithful answer, or declines when it
should. Every reply is scripted. What it proves is that the sections
reaching the model are the real sections, that the citations are built
from the passages actually read, and that both refusal paths produce a
refusal object rather than prose. Whether the MODEL behaves is what the
golden-set evaluation measures (ST-32, PRD F-08), and it is the only thing
that can.

ON THE EXIT GATE'S SECOND HALF -- "an answer without sources cannot render
as final" -- there is deliberately no test here that builds a sourceless
answer and watches it fail. `Answer.__post_init__` raises, and
`tests/unit/test_agent_state.py` proves that directly. The end-to-end
statement of the same rule is
`test_a_section_the_store_lost_is_not_cited_by_the_answer` below: the
product's move when it cannot read a section is to cite less, or to
refuse, never to cite a document nothing read.
"""

from __future__ import annotations

import dataclasses

import pytest

import agent.nodes
import chunking
import embeddings
import parent_store
import vector_store
from agent.answering import NOT_COVERED, build_write_answer
from agent.grading import build_grade, build_reword
from agent.graph import ask
from agent.ports import AgentPorts
from agent.retrieval import build_retrieve
from agent.state import AnswerKind
from agent.stores import parent_texts
from config import get_settings
from tests.fake_chat import ScriptedChat
from tests.fake_encoders import install as install_fake_encoders

WS_HR = "44444444-4444-4444-4444-444444444444"

# THE ARTICLES ARE LONG ON PURPOSE, and it is the fixture's load-bearing
# property rather than padding. Two things depend on it:
#
# * each article must clear `parent_merge_below_chars` (2,000) so it stays
#   its OWN parent. Merged parents carry a merged label, and this file's
#   whole subject is that the label cited is the section read.
# * each article must be several times `chunk_child_size_chars` (500) so
#   the chunk that matches is visibly SMALLER than the section handed to
#   the model. With a one-chunk article, "the model read the section" and
#   "the model read the chunk" are the same assertion, and 7.5's whole
#   point becomes untestable.
#
# The fixture asserts both rather than trusting them. This project has
# shipped a fixture too small for its own property three times (ST-14,
# ST-16, ST-23), every time in a test that looked green.
#
# Each article ends with a DISTINCTIVE closing sentence that no opening
# chunk can contain, which is how "the whole section reached the model" is
# asserted without depending on which chunk ranked first.
HR_DOCUMENT = """# Article 13 : Periode d'essai

La periode d'essai est de trois mois pour les cadres et assimiles,
renouvelable une seule fois. Elle est de un mois et demi pour les employes
et de quinze jours pour les ouvriers. Pendant la periode d'essai, chacune
des parties peut rompre le contrat de travail sans preavis et sans
indemnite. Toutefois, apres au moins une semaine de travail, la rupture du
contrat non motivee par la faute grave du salarie ne peut avoir lieu qu'en
donnant un delai de preavis de deux jours avant la rupture si le salarie
est paye a la journee, a la semaine ou a la quinzaine, et de huit jours si
le salarie est paye au mois. Si la rupture du contrat intervient apres au
moins une semaine de travail effectif, la partie qui rompt le contrat doit
en informer l'autre partie par ecrit et conserver la preuve de cette
notification. La periode d'essai peut etre renouvelee une seule fois et
son renouvellement doit etre notifie par ecrit au salarie avant le terme
de la periode initiale, faute de quoi le contrat est repute conclu a duree
indeterminee des le premier jour de travail. Le salarie conserve pendant
la periode d'essai les memes droits en matiere de repos hebdomadaire, de
jours feries et de securite au travail que les autres salaries de
l'entreprise, sans aucune restriction liee au caractere provisoire de son
engagement. L'employeur qui souhaite mettre fin a la periode d'essai doit
remettre au salarie l'ensemble des documents de fin de contrat, y compris
le certificat de travail et le solde de tout compte, dans les memes
conditions que pour un contrat ordinaire. Toute clause du contrat qui
prevoit une periode d'essai plus longue que celles fixees au present
article est reputee non ecrite et la duree legale s'y substitue de plein
droit. Lorsque le salarie a deja occupe le meme poste dans l'entreprise au
cours des douze mois precedents, aucune nouvelle periode d'essai ne peut
lui etre imposee, et le temps deja accompli s'impute integralement sur la
duree legale. L'inspecteur du travail peut se faire communiquer a tout
moment les contrats en cours d'essai ainsi que les notifications de
renouvellement qui s'y rapportent. MARQUEUR-FIN-ARTICLE-13 : le present
article ne s'applique pas aux contrats saisonniers conclus pour les
travaux agricoles.

# Article 43 : Preavis de licenciement

Le delai de preavis est d'un mois pour les employes ayant moins de cinq
ans d'anciennete dans l'entreprise, et de trois mois au-dela de cinq ans
d'anciennete continue. Pendant le delai de preavis, le salarie a droit a
des permissions d'absence remunerees pour chercher un autre emploi, a
raison de deux heures par jour sans que ces absences puissent depasser
huit heures dans une meme semaine ou trente heures dans une periode de
trente jours consecutifs. Ces heures sont fixees d'un commun accord entre
l'employeur et le salarie, et a defaut d'accord elles sont prises un jour
sur deux a l'initiative de chacune des parties. L'employeur qui n'observe
pas le delai de preavis doit verser au salarie une indemnite egale a la
remuneration qu'aurait percue le salarie s'il etait demeure a son poste
pendant toute la duree du preavis, charges sociales comprises. Le delai de
preavis court a compter du lendemain de la notification de la decision de
rupture au salarie concerne, et il est suspendu pendant les periodes
d'incapacite temporaire de travail reconnues par un medecin. La partie qui
prend l'initiative de la rupture peut dispenser l'autre partie d'executer
le preavis, sans que cette dispense la libere du versement de l'indemnite
correspondante. Aucune disposition contractuelle ne peut reduire les
delais fixes au present article au detriment du salarie, toute clause
contraire etant nulle de plein droit. Lorsque le licenciement est motive
par une faute grave dument etablie et notifiee dans les formes prevues par
la loi, le salarie perd le benefice du delai de preavis ainsi que de
l'indemnite qui s'y rattache, sans prejudice de son droit de contester la
qualification de la faute devant le tribunal competent. En cas de rupture
a l'initiative du salarie, le delai de preavis est reduit de moitie, sauf
stipulation contractuelle plus favorable a l'employeur acceptee par ecrit
au moment de l'embauche. Les jours de preavis coincidant avec un jour
ferie chome ou avec le repos hebdomadaire ne prolongent pas le delai, mais
les jours de conge annuel deja programmes le suspendent pour leur duree
exacte. L'employeur remet au salarie, a l'issue du preavis, un certificat
de travail mentionnant les dates d'entree et de sortie ainsi que les
postes occupes. MARQUEUR-FIN-ARTICLE-43 : les delais prevus ici ne
concernent pas la rupture pendant la periode d'essai.

# Article 52 : Indemnite de licenciement

Le salarie lie par un contrat de travail a duree indeterminee a droit a
une indemnite de licenciement apres six mois de travail continu dans la
meme entreprise, quel que soit le mode de remuneration et la periodicite
du paiement du salaire. Le montant de l'indemnite pour chaque annee ou
fraction d'annee de travail effectif est egal a quatre-vingt-seize heures
de salaire pour les cinq premieres annees d'anciennete, a cent quarante-
quatre heures de salaire pour la periode d'anciennete allant de six a dix
ans, a cent quatre-vingt-douze heures de salaire pour la periode allant de
onze a quinze ans, et a deux cent quarante heures de salaire pour la
periode d'anciennete depassant quinze ans. Les periodes d'incapacite
temporaire, de conge de maternite et de conge annuel paye sont comptees
comme du travail effectif pour le calcul de cette anciennete. Le salaire
servant de base au calcul de l'indemnite est la moyenne des salaires
percus au cours des cinquante-deux semaines qui ont precede la rupture du
contrat de travail, primes et avantages en nature compris. L'indemnite de
licenciement est versee au salarie au plus tard le jour de son depart
effectif de l'entreprise, en meme temps que le certificat de travail et le
solde de tout compte. Le salarie licencie pour faute grave dument etablie
ne peut pretendre a cette indemnite, sauf decision contraire du tribunal
saisi d'une contestation portant sur la qualification de la faute retenue
contre lui. En cas de deces du salarie avant le versement, l'indemnite est
due a ses ayants droit dans les memes conditions et selon les memes
modalites de calcul, sans qu'aucune reduction puisse leur etre opposee. Le
salarie dont le contrat est transfere a un nouvel employeur a la suite
d'une fusion, d'une scission ou d'une cession de l'entreprise conserve
l'integralite de l'anciennete acquise pour le calcul de cette indemnite.
Toute somme versee au titre d'un accord amiable de rupture s'impute sur
l'indemnite legale, sans jamais pouvoir la reduire en deca du montant
minimal fixe au present article. MARQUEUR-FIN-ARTICLE-52 : cette
indemnite se cumule avec l'indemnite compensatrice de preavis lorsque
celui-ci n'a pas ete observe.
"""

SOURCE_FILE = "code-du-travail.pdf"

# A SECOND DOCUMENT IN THE SAME WORKSPACE, and it exists for one reason: a
# workspace holding a single file cannot fail a citation test. With one
# file, "every source cited names a file the trace consulted" is true
# whatever the code does, and "every label contains 'Article'" is true
# because every heading in the other document starts with that word. A
# cold review caught exactly that vacuity here.
#
# So this one is deliberately UNLIKE the labour code in both respects: a
# different file name, and headings that carry no article number, so a
# citation that leaked from it is visible in both the file name and the
# label. Its vocabulary is disjoint from the labour-law questions asked
# below -- cotisation, plafond, affiliation, immatriculation -- so a
# labour-law query does not reach it by accident, and the control probe
# below proves it IS reachable by its own question rather than merely
# absent.
CNSS_DOCUMENT = """# Affiliation et immatriculation

Tout employeur exercant une activite assujettie doit demander son
affiliation a la Caisse dans les trente jours qui suivent l'embauche de
son premier salarie. L'affiliation donne lieu a la delivrance d'un numero
qui doit figurer sur toutes les declarations ulterieures adressees a la
Caisse. L'employeur procede ensuite a l'immatriculation de chacun de ses
salaries, laquelle est personnelle et definitive : un salarie deja
immatricule chez un precedent employeur conserve son numero et il
appartient au nouvel employeur de le reprendre sur ses declarations plutot
que d'en demander un second. Toute modification de la situation juridique
de l'entreprise, changement de denomination, transfert de siege ou
cessation d'activite, doit etre signalee dans les trente jours. Le defaut
d'affiliation, comme le defaut d'immatriculation d'un salarie, expose
l'employeur a une majoration calculee sur les sommes qui auraient du etre
declarees, sans prejudice de la regularisation des droits du salarie
concerne, lesquels ne peuvent en aucun cas etre reduits du fait d'une
negligence imputable a l'employeur.

# Cotisations et plafond

Les cotisations sont assises sur l'ensemble des remunerations percues par
le salarie, y compris les primes, les gratifications et les avantages en
argent ou en nature. Une partie des cotisations est plafonnee et l'autre
est due sur la totalite de la remuneration, le plafond etant fixe par voie
reglementaire et revise periodiquement. La part salariale est precomptee
par l'employeur au moment du paiement de la remuneration ; l'employeur qui
n'a pas opere ce precompte en temps utile ne peut plus le reclamer au
salarie et en supporte definitivement la charge. Les declarations et le
versement correspondant sont adresses a la Caisse selon une periodicite
fixee par les textes, et tout retard donne lieu a des majorations
calculees par mois ou fraction de mois de retard. Un employeur qui
conteste le montant reclame doit neanmoins verser la somme non contestee
dans le delai normal, la contestation ne suspendant pas l'exigibilite.
"""

CNSS_FILE = "guide-cnss.txt"

# A short, plausible answer, scripted. What matters is that it comes back
# unchanged with the right citations attached, not what it says.
WRITTEN_ANSWER = (
    "La periode d'essai est de trois mois pour les cadres, renouvelable "
    "une seule fois."
)


def _index(client, parents_dir, markdown: str, source_file: str):
    """Chunk, store the parents and embed the children -- the real thing."""
    result = chunking.chunk_document(markdown, source_file=source_file)
    parent_store.save_parents(
        parents=result.parents, workspace_id=WS_HR, base_path=parents_dir
    )
    vector_store.upsert_children(
        client,
        workspace_id=WS_HR,
        children=result.children,
        dense_vectors=embeddings.embed_passages(
            [child.text for child in result.children]
        ),
    )
    return result


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    """One real workspace holding TWO real documents: real chunking, real
    parents on disk, real embedded Qdrant.

    Every assertion here is the fixture guarding its own preconditions.
    Three of this project's shipped defects were a fixture too small for
    the property its tests claimed (ST-14, ST-16, ST-23), and a fourth was
    found in THIS file by a cold review -- a one-document workspace, in
    which a test about citing the wrong file cannot fail."""
    install_fake_encoders(monkeypatch)
    parents_dir = tmp_path / "parents"
    with vector_store.open_store(tmp_path / "qdrant") as client:
        result = _index(client, parents_dir, HR_DOCUMENT, SOURCE_FILE)
        other = _index(client, parents_dir, CNSS_DOCUMENT, CNSS_FILE)
        assert len(result.parents) >= 3, (
            "each article must survive as its own parent, or the label a "
            "source cites is a merged label and this file proves nothing "
            "about what was read"
        )
        assert len(result.children) > len(result.parents), (
            "an article must split into several children, or 'the model "
            "read the section' and 'the model read the chunk' are the same "
            "assertion (architecture 7.5)"
        )
        assert other.parents, "the second document must really be indexed"
        assert not any(
            "Article" in (parent.section_label or "") for parent in other.parents
        ), (
            "the second document's labels must NOT look like the labour "
            "code's, or a citation that leaked from it would be invisible"
        )
        yield client, parents_dir


def _ports(client, parents_dir, model, **overrides) -> AgentPorts:
    """Every port on the answer path, real. Only ST-22's and ST-25's are
    stubbed, and they are stubbed in the open."""
    base = AgentPorts(
        # ST-25's, stubbed: no session memory in this story.
        summarize=lambda history: "",
        # ST-22's, stubbed: never ambiguous here, one query out.
        clarify=lambda question, summary: None,
        rewrite=lambda question, summary: (question,),
        retrieve=build_retrieve(client),
        grade=build_grade(model),
        reword=build_reword(model),
        fetch_parents=lambda ws, ids: parent_texts(ws, ids, base_path=parents_dir),
        write_answer=build_write_answer(model),
    )
    return dataclasses.replace(base, **overrides)


def _with_ceiling(monkeypatch, ceiling: int):
    settings = get_settings().model_copy(update={"retry_ceiling": ceiling})
    monkeypatch.setattr(agent.nodes, "get_settings", lambda: settings)
    return settings


def _answer_call(model):
    """The user message from the call that asked for an answer.

    Picked by content rather than by index: the grader is asked first, so
    a positional guess would silently read the wrong call the day a retry
    is added to a test."""
    return next(
        user for _system, user in model.calls if "Your answer, or" in user
    )


# --- F-03: sourced answers --------------------------------------------


def test_a_question_the_workspace_covers_is_answered_with_its_sources(
    corpus, monkeypatch
):
    """F-03's first two criteria, on the real pipeline: "the answer cites
    at least one source" and "at least one source reference is visible
    together with the answer".

    The label is asserted, not just the file name. F-03 says "file name
    plus section label when the document provides one", and a source that
    names a 119-page PDF and nothing else does not tell the reader where
    to look -- which is the defect the citation-marker labelling was built
    to fix."""
    client, parents_dir = corpus
    _with_ceiling(monkeypatch, 0)
    model = ScriptedChat("RELEVANT", WRITTEN_ANSWER)

    answer = ask(
        workspace_id=WS_HR,
        question="Quelle est la duree de la periode d'essai pour un cadre ?",
        ports=_ports(client, parents_dir, model),
    )

    assert answer.kind is AnswerKind.ANSWER
    assert answer.refusal is False
    assert answer.text == WRITTEN_ANSWER
    assert answer.sources, "F-03: an answer cites at least one source"
    assert all(source.file_name == SOURCE_FILE for source in answer.sources)
    assert all("Article" in (source.section_label or "") for source in answer.sources)


def test_the_model_is_shown_the_whole_article_not_the_chunk_that_matched(
    corpus, monkeypatch
):
    """Architecture 7.5 against the real store: search the small thing,
    read the big thing.

    Asserted on a marker sentence that sits at the END of the article,
    which no opening chunk can contain. Asserting merely that some article
    text reached the model would pass on a writer that pasted the matched
    500-character chunk, because the chunk IS article text."""
    client, parents_dir = corpus
    _with_ceiling(monkeypatch, 0)
    model = ScriptedChat("RELEVANT", WRITTEN_ANSWER)

    ask(
        workspace_id=WS_HR,
        question="duree de la periode d'essai",
        ports=_ports(client, parents_dir, model),
    )

    shown = _answer_call(model)
    assert "MARQUEUR-FIN-ARTICLE-13" in shown
    assert SOURCE_FILE in shown


def test_a_citation_never_names_the_other_document_in_the_workspace(
    corpus, monkeypatch
):
    """Citations track the document the question actually reached, as a
    CONTROL PROBE rather than a bare negative.

    SCOPE, stated honestly because an earlier docstring here overclaimed
    it: both documents live in the SAME workspace, so this proves that
    retrieval and the source list agree about WHICH DOCUMENT was read. It
    does NOT prove F-03's "active workspace" scoping -- that is
    cross-workspace isolation, and it is tested where it belongs, at
    `tests/unit/test_agent_stores.py::test_one_workspace_cannot_read_
    another_workspace_s_section`.

    The first version of this test lived in a one-document workspace and
    asserted that the cited files were a subset of the files consulted --
    which is true whatever the code does when there is only one file to
    cite. A cold review deleted it on those grounds, and rightly.

    Two questions now run against the SAME two-document workspace. The
    labour-law one must not cite the CNSS guide, and the CNSS one must
    cite it. The second half is what makes the first half mean anything:
    without it, "the guide was not cited" is equally true of a workspace
    where the guide was never indexed, never searchable, or where
    retrieval is broken for every question. That is the absence rule --
    prove the route works before trusting an empty result from it."""
    client, parents_dir = corpus
    _with_ceiling(monkeypatch, 0)

    labour = ask(
        workspace_id=WS_HR,
        question="periode d'essai renouvelable pour les cadres et assimiles",
        ports=_ports(client, parents_dir, ScriptedChat("RELEVANT", WRITTEN_ANSWER)),
    )
    social = ask(
        workspace_id=WS_HR,
        question="affiliation immatriculation cotisations plafond de la Caisse",
        ports=_ports(client, parents_dir, ScriptedChat("RELEVANT", WRITTEN_ANSWER)),
    )

    labour_cited = {source.file_name for source in labour.sources}
    social_cited = {source.file_name for source in social.sources}

    assert labour_cited == {SOURCE_FILE}
    assert CNSS_FILE in social_cited, (
        "the control half: the CNSS guide must be reachable by its own "
        "question, or the assertion above is true of a broken index"
    )
    assert labour_cited <= set(labour.trace.files_consulted)
    # The LABEL half of "file name plus section label" (F-03), which is a
    # separate promise: a citation can name the right file and the wrong
    # section, which is the defect the citation-marker labelling exists to
    # fix. The CNSS guide's headings carry no article number on purpose,
    # so a label pulled from the wrong document is visible here.
    assert all(
        "Article" in (source.section_label or "") for source in labour.sources
    )


# --- F-05: honest refusal, both ways in ------------------------------


def test_a_question_the_workspace_does_not_cover_is_refused_honestly(
    corpus, monkeypatch
):
    """F-05's first criterion, almost word for word: "a cooking question in
    the HR workspace ... states that no answer was found in this
    workspace, lists the search attempts, and contains no fabricated
    facts".

    "No fabricated facts" is asserted the only way it can be honestly: the
    text is a fixed string the product owns, so there is nowhere for a
    fabricated fact to come from."""
    client, parents_dir = corpus
    _with_ceiling(monkeypatch, 0)
    question = "Comment cuisiner un tajine aux pruneaux ?"
    model = ScriptedChat("OFF_TOPIC")

    answer = ask(
        workspace_id=WS_HR,
        question=question,
        ports=_ports(client, parents_dir, model),
    )

    assert answer.kind is AnswerKind.REFUSAL
    assert answer.refusal is True
    assert answer.sources == ()
    assert answer.searched == (question,)
    assert answer.text == agent.nodes.REFUSAL_TEXT


def test_a_writer_that_declines_refuses_rather_than_writing_prose_about_it(
    corpus, monkeypatch
):
    """The second door into F-05, and the one ST-24 adds: the grader
    judged 500-character CHILD chunks as relevant, the writer read the full
    sections and found they do not answer the question.

    Without this path the model has exactly two moves in that situation --
    decline, or invent -- and inventing is the failure the product exists
    to demonstrate the absence of. Prose that says "I could not find this"
    would arrive as an answer-kind object with `refusal` false and source
    cards attached, which the evaluation's out-of-scope half scores as a
    non-refusal."""
    client, parents_dir = corpus
    _with_ceiling(monkeypatch, 0)
    question = "Quel est le taux de cotisation CNSS en 2026 ?"
    model = ScriptedChat("RELEVANT", NOT_COVERED)

    answer = ask(
        workspace_id=WS_HR,
        question=question,
        ports=_ports(client, parents_dir, model),
    )

    assert answer.kind is AnswerKind.REFUSAL
    assert answer.sources == ()
    assert answer.searched == (question,)
    assert answer.text == agent.nodes.REFUSAL_TEXT


def test_the_decline_is_reached_only_after_the_sections_were_really_read(
    corpus, monkeypatch
):
    """The same run as above, seen from the trace: this refusal is NOT the
    "nothing on topic" one, and F-10 has to be able to tell them apart.

    Asserted on the trace because the user-facing text is deliberately
    identical -- the user's next step is the same either way, and inventing
    a second message for a distinction they cannot act on would be noise."""
    client, parents_dir = corpus
    _with_ceiling(monkeypatch, 0)
    model = ScriptedChat("RELEVANT", NOT_COVERED)

    answer = ask(
        workspace_id=WS_HR,
        question="Quel est le taux de cotisation CNSS en 2026 ?",
        ports=_ports(client, parents_dir, model),
    )

    assert answer.trace.steps[-1].detail == (
        "refused: sections read, none of them answers the question"
    )
    assert answer.trace.files_consulted, "the search did consult files"


# --- the source contract under a store that has drifted ---------------


def test_a_section_the_store_lost_is_not_cited_by_the_answer(corpus, monkeypatch):
    """The end-to-end form of "an answer without sources cannot render as
    final": when Sanad cannot read a section, it cites less. It never cites
    a document whose text nothing read.

    Run in two phases against the REAL store, because the point is a file
    that is genuinely gone from disk rather than a port that pretends. The
    first phase learns which sections this question actually reaches; the
    second deletes one of their JSON files and asks again."""
    client, parents_dir = corpus
    _with_ceiling(monkeypatch, 0)
    question = "periode d'essai preavis indemnite de licenciement"

    first = ask(
        workspace_id=WS_HR,
        question=question,
        ports=_ports(client, parents_dir, ScriptedChat("RELEVANT", WRITTEN_ANSWER)),
    )
    assert len(first.sources) >= 2, (
        "this question must reach at least two sections, or deleting one "
        "cannot change the citation list and the test proves nothing"
    )

    lost = first.sources[0]
    victim = next(
        path
        for path in (parents_dir / WS_HR).glob("*.json")
        if lost.section_label in path.read_text(encoding="utf-8")
    )
    victim.unlink()

    second = ask(
        workspace_id=WS_HR,
        question=question,
        ports=_ports(client, parents_dir, ScriptedChat("RELEVANT", WRITTEN_ANSWER)),
    )

    assert second.kind is AnswerKind.ANSWER
    assert second.sources, "the readable sections still answer"
    assert lost not in second.sources
    assert len(second.sources) == len(first.sources) - 1


def test_a_workspace_whose_sections_are_all_gone_says_run_a_sync(
    corpus, monkeypatch
):
    """The floor under box P, against a real store rather than a stub. All
    the sections are deleted, so the passages are still found and not one
    of them can be read.

    This refusal says something DIFFERENT on purpose: "not covered here"
    would be false, and PRD section 11 requires every failure to name a
    next step. The next step here is a Sync, not a rephrase."""
    client, parents_dir = corpus
    _with_ceiling(monkeypatch, 0)
    for path in (parents_dir / WS_HR).glob("*.json"):
        path.unlink()

    answer = ask(
        workspace_id=WS_HR,
        question="duree de la periode d'essai",
        ports=_ports(client, parents_dir, ScriptedChat("RELEVANT", WRITTEN_ANSWER)),
    )

    assert answer.kind is AnswerKind.REFUSAL
    assert answer.sources == ()
    assert "Sync" in answer.text
    assert answer.text != agent.nodes.REFUSAL_TEXT
