"""ST-27 exit gate: every S1 state from PRD section 8, demonstrated.

BUILD-PLAN line 81: "Every S1 state (empty/loading/error) from PRD section
8 demonstrated live". This file demonstrates them through the real app --
real routes, real templates, real agent graph -- and the hand-run against
a real corpus and a real model is recorded in the build journal beside it.
A test is repeatable and a hand-run is not; a hand-run meets a real model
and a test cannot. Both, for different reasons.

WHAT IS REAL HERE: the FastAPI app, the Jinja templates, an embedded
Qdrant under `tmp_path`, real chunking, real parent JSON on disk, real
hybrid search, real SQLite, and the real `retrieve`, `grade`,
`fetch_parents` and `write_answer` ports.

WHAT IS FAKED, both for reasons already settled on this project: the two
ENCODERS, because the real ones download hundreds of megabytes
(`tests/fake_encoders.py`), and the CHAT MODEL, because
docs/phase2/ENGINEERING-RULES.md's hard rule is that tests use a scripted fake and
carry no API keys.

WHAT THIS THEREFORE DOES NOT PROVE: that a real model writes a good
answer. It proves that each state the specification names renders, that
the variants are distinguishable from one another, and that the stage
hints track the agent rather than a clock.
"""

from __future__ import annotations

import dataclasses
import html
import json
import re
import threading

import pytest
from fastapi.testclient import TestClient

import app as app_module
import chunking
import embeddings
import parent_store
import ui.conversation
import vector_store
import workspaces
from agent.answering import NOT_COVERED
from agent.ports import AgentPorts
from agent.state import Answer, AnswerKind
from agent.trace import StepKind, Trace, TraceStep
from app import Runtime, create_app
from config import get_settings
from db import repo
from tests.fake_chat import ScriptedChat
from tests.fake_encoders import install as install_fake_encoders
from ui.conversation import Message, MessageKind, message_for
from ui.ports import build_ports

# Two articles, each well over `parent_merge_below_chars` (2,000) so it
# survives as its OWN parent, and several times `chunk_child_size_chars`
# (500) so the chunk that matches is visibly smaller than the section
# shown in the passage viewer. The fixture asserts both rather than
# trusting them: this project has shipped a fixture too small for its own
# property four times.
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
"""

SOURCE_FILE = "code-du-travail.pdf"
WRITTEN_ANSWER = (
    "La periode d'essai est de trois mois pour les cadres, renouvelable "
    "une seule fois."
)
QUESTION = "Quelle est la duree de la periode d'essai pour un cadre ?"
QUERY_PLAN = (
    '{"clarification":null,"queries":'
    '["duree periode essai cadre renouvellement"]}'
)

# Long enough to time out loudly rather than hang a CI run for ever, short
# enough that a real deadlock is noticed in one coffee rather than one
# afternoon.
WAIT = 10


class Gate:
    """Hold one port open until the test says otherwise.

    This is what makes the loading state observable: without it the run
    finishes in milliseconds and there is no in-flight page to fetch. It
    is also what makes the stage assertions DISCRIMINATING -- the same
    question is blocked at four different ports and must report four
    different stages. A timer-driven screen (which is what the React
    reference ships) would print the same label at the same elapsed time
    in all four."""

    def __init__(self) -> None:
        self.reached = threading.Event()
        self.release = threading.Event()

    def wrap(self, port):
        def wrapped(*args, **kwargs):
            self.reached.set()
            self.release.wait(timeout=WAIT)
            return port(*args, **kwargs)

        return wrapped


@pytest.fixture
def sanad(tmp_path, monkeypatch):
    """A real workspace, really indexed, behind a real app.

    Yields a factory so each test builds its own client with its own
    scripted model and its own port overrides."""
    install_fake_encoders(monkeypatch)
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    workspace = workspaces.create_workspace(
        name="HR", folder_path=str(tmp_path / "corpus"), db_path=db_path
    )
    parents_dir = tmp_path / "parents"

    with vector_store.open_store(tmp_path / "qdrant") as client:
        result = chunking.chunk_document(HR_DOCUMENT, source_file=SOURCE_FILE)
        assert len(result.parents) >= 2, (
            "each article must survive as its own parent, or the label a "
            "source card cites is a merged label and the passage viewer "
            "proves nothing about what was read"
        )
        assert len(result.children) > len(result.parents), (
            "an article must split into several children, or the "
            "highlighted span and the whole section are the same text and "
            "'cited span highlighted' becomes untestable"
        )
        parent_store.save_parents(
            parents=result.parents, workspace_id=workspace.id, base_path=parents_dir
        )
        vector_store.upsert_children(
            client,
            workspace_id=workspace.id,
            children=result.children,
            dense_vectors=embeddings.embed_passages(
                [child.text for child in result.children]
            ),
        )

        def build(
            model=None,
            *,
            legal_flag: bool = False,
            documents: bool = True,
            **overrides,
        ):
            if legal_flag:
                workspaces.set_legal_flag(
                    workspace_id=workspace.id, legal_flag=True, db_path=db_path
                )
            if documents:
                with repo.session(db_path) as conn:
                    if not repo.list_documents(conn, workspace.id):
                        repo.insert_document(
                            conn,
                            workspace_id=workspace.id,
                            file_name=SOURCE_FILE,
                            file_type="pdf",
                            content_hash="hash",
                            status="active",
                        )

            def ports() -> AgentPorts:
                base = build_ports(
                    client,
                    model or ScriptedChat(QUERY_PLAN, "RELEVANT", WRITTEN_ANSWER),
                    parents_path=parents_dir,
                )
                return dataclasses.replace(base, **overrides)

            runtime = Runtime(ports_factory=ports, db_path=db_path)
            return TestClient(create_app(runtime)), runtime

        yield build, workspace, db_path


def _visible(page: str) -> str:
    """The page's prose, with HTML entities decoded.

    Needed because the corpus is French: Jinja escapes the apostrophe in
    "periode d'essai" to `&#39;`, so a raw `in page` check on any real
    sentence fails. Markup assertions stay on the raw page; only text
    comparisons come through here.

    That escaping is a feature, not an obstacle, and
    `test_a_question_containing_markup_is_shown_as_text` pins it."""
    return html.unescape(page)


def _hold(runtime, gate: Gate, port: str) -> None:
    """Make one port block, so the in-flight page can be fetched.

    Wraps whatever the runtime's factory already builds, once per run, so
    the gate always sits on the REAL port rather than on a second set of
    ports built alongside it."""
    original = runtime.ports_factory

    def gated() -> AgentPorts:
        ports = original()
        return dataclasses.replace(ports, **{port: gate.wrap(getattr(ports, port))})

    runtime.ports_factory = gated


def _ask(client, question: str = QUESTION):
    """Ask, and come back with the page that resulted."""
    client.post("/chat/ask", data={"question": question}, follow_redirects=False)
    return client.get("/").text


def _settled(client, runtime, workspace_id: str) -> str:
    """Wait for the in-flight run, then render.

    Polls the runtime object rather than sleeping a fixed time: a fixed
    sleep is the flaky-test generator this project has already paid for
    elsewhere."""
    conversation = runtime.conversation(workspace_id)
    for _ in range(WAIT * 100):
        if not conversation.busy:
            break
        threading.Event().wait(0.01)
    assert not conversation.busy, "the run never finished"
    return client.get("/").text


# --- the shell with nothing in it (UX spec 4, criterion 1) ------------


def test_a_machine_with_no_database_at_all_still_renders_the_first_screen(tmp_path):
    """Found by running it, not by reading it.

    On a machine where `data/sanad.db` does not exist yet -- which is
    every machine on its first start -- `GET /` raised
    `RegistryNotFoundError` and served a stack trace. That is acceptance
    criterion 1's screen, the FIRST thing a new operator ever sees. The
    app now creates its own registry in the lifespan.

    Note the fixture: no `ensure_schema`, and the path points at a
    database that has never existed. Calling `ensure_schema` here would
    make this test pass against the very bug it exists to catch."""
    missing = tmp_path / "not-created-yet" / "sanad.db"
    runtime = Runtime(ports_factory=lambda: None, db_path=missing)

    with TestClient(create_app(runtime)) as client:
        page = client.get("/")

    assert page.status_code == 200
    assert "No workspace yet" in page.text
    assert missing.exists(), "the app must create the registry it needs"


def test_with_no_workspace_the_chat_navigation_is_disabled_with_a_reason(tmp_path):
    """Criterion 1: "navigation to S1 is disabled with a stated reason"
    and the selector reads "No workspace yet"."""
    db_path = tmp_path / "empty.db"
    repo.ensure_schema(db_path)
    client = TestClient(create_app(Runtime(ports_factory=lambda: None, db_path=db_path)))

    page = client.get("/").text

    assert "No workspace yet" in page
    assert 'aria-disabled="true"' in page
    assert "Create a workspace before asking questions" in page
    # And the composer is not on the page at all -- a disabled input would
    # still invite a question there is no workspace to answer it in.
    assert 'id="question"' not in page


# --- the empty states (UX spec 6.3, PRD section 8) --------------------


def test_the_empty_state_offers_sample_questions_and_promises_sources(sanad):
    """UX spec 6.3: three sample questions drawn from the active
    workspace, plus "one line stating that every answer carries its
    sources"."""
    build, workspace, _ = sanad
    client, _runtime = build()

    page = client.get("/").text

    assert SOURCE_FILE in page, "a sample question must name a real file"
    assert "Every answer carries the sources it was written from." in page
    assert 'id="question"' in page
    assert "disabled" not in page.split('id="question"')[1].split(">")[0]


def test_the_empty_state_shows_how_sanad_answers_in_three_steps(sanad):
    """v2.1: before the first question, the promise is spelled out as the
    three things the agent really does, in order -- search, check, answer or
    refuse. The refusal half must be there: it is the honest path."""
    build, _workspace, _ = sanad
    client, _runtime = build()

    page = client.get("/").text
    steps = page.split('aria-label="How Sanad answers"')[1].split("</ol>")[0]

    assert steps.count('class="steps__item"') == 3
    assert steps.index("Searches") < steps.index("Checks") < steps.index("Answers")
    assert "or says it cannot" in steps


def test_a_workspace_with_no_documents_disables_the_input_and_says_why(sanad):
    """UX spec 6.3 and section 11's "Empty workspace" row: the sample
    questions are replaced by a pointer to S2 and the input is disabled
    with the reason shown inline."""
    build, workspace, _ = sanad
    client, _runtime = build(documents=False)

    page = client.get("/").text

    assert "Nothing to answer from yet" in page
    assert "no synced documents" in page
    composer = page.split('id="question"')[1].split(">")[0]
    assert "disabled" in composer
    assert 'id="composer-reason"' in page


# --- loading (UX spec 6.3), and the stage is real ---------------------


@pytest.mark.parametrize(
    ("port", "expected"),
    [
        ("summarize", "Preparing the question"),
        ("retrieve", "Searching the workspace"),
        ("grade", "Checking the answer"),
        ("write_answer", "Writing"),
    ],
)
def test_the_loading_state_names_the_stage_the_agent_is_really_in(
    sanad, port, expected
):
    """UX spec 6.3's three stage hints, and design principle 3's rule
    about them: "Never fake progress. Stage hints during a long operation
    say what is actually happening."

    THE PARAMETRISATION IS THE TEST. One question is held at four
    different ports and must report four different stages. A screen that
    advanced a counter on a timer -- which is exactly what
    `designrag-main/src/components/ChatScreen.tsx:111` does -- would show
    the same label in all four rows and fail three of them."""
    build, workspace, _ = sanad
    gate = Gate()
    client, runtime = build()
    _hold(runtime, gate, port)

    client.post("/chat/ask", data={"question": QUESTION}, follow_redirects=False)
    assert gate.reached.wait(WAIT), f"the run never entered {port}"
    page = client.get("/").text

    assert expected in page
    assert 'role="status"' in page
    # UX spec 6.3: the input is disabled and shows why, and a cancel
    # action is available.
    assert "Sanad is answering your last question." in page
    assert "/chat/cancel" in page

    gate.release.set()
    _settled(client, runtime, workspace.id)


def test_the_question_appears_before_any_answer_does(sanad):
    """The user variant (UX spec 6.2), and the reason it is appended by
    the route rather than by the worker: the transcript must show what was
    asked the instant the page comes back, even if the run then fails on
    its first call."""
    build, workspace, _ = sanad
    gate = Gate()
    client, runtime = build()
    _hold(runtime, gate, "retrieve")

    client.post("/chat/ask", data={"question": QUESTION}, follow_redirects=False)
    assert gate.reached.wait(WAIT)
    page = client.get("/").text

    assert "msg--user" in page
    assert QUESTION in _visible(page)

    gate.release.set()
    _settled(client, runtime, workspace.id)


# --- the answer variant, its sources, and the passage viewer ----------


def test_an_answer_renders_with_its_source_cards_and_a_passage_behind_each(sanad):
    """UX spec 6.2's answer variant and 5's `SourceCard`, on the real
    pipeline. F-03: "at least one source reference is visible together
    with the answer"."""
    build, workspace, _ = sanad
    client, runtime = build()

    _ask(client)
    page = _settled(client, runtime, workspace.id)

    assert "msg--answer" in page
    assert WRITTEN_ANSWER in _visible(page)
    assert SOURCE_FILE in page
    assert "Article" in page
    # A real link, not a clickable div: UX spec 6.4 requires a complete
    # keyboard path across "each source card".
    assert "/chat/passage/" in page
    assert "Open passage" in page


def test_a_source_card_opens_the_whole_section_with_the_cited_span_marked(sanad):
    """UX spec 5's `PassageViewer`: "cited span highlighted".

    Asserted on the marker sentence at the END of Article 13, which no
    opening chunk contains -- so this proves the viewer shows the SECTION,
    not the 500-character chunk that matched. And the <mark> proves the
    span inside it was located."""
    build, workspace, _ = sanad
    client, runtime = build()

    _ask(client)
    _settled(client, runtime, workspace.id)
    page = client.get("/").text
    # Follow the first source card's own link, exactly as a reader with
    # scripting off would.
    href = page.split('href="/chat/passage/')[1].split('"')[0]
    passage = client.get(f"/chat/passage/{href}").text

    assert "MARQUEUR-FIN-ARTICLE-13" in passage
    assert "<mark" in passage
    assert "Sanad could not locate the exact" not in passage


def test_the_overlay_and_the_passage_page_show_the_same_section(sanad):
    """One macro renders both (`_passage.html`), and this is what stops
    that claim from being a comment. Two descriptions of one passage is
    the shape where the overlay quietly shows a stale section."""
    build, workspace, _ = sanad
    client, runtime = build()

    _ask(client)
    page = _settled(client, runtime, workspace.id)
    href = page.split('href="/chat/passage/')[1].split('"')[0]
    standalone = client.get(f"/chat/passage/{href}").text

    marked = standalone.split("<mark")[1].split("</mark>")[0]
    assert marked in page, "the overlay in the page must carry the same marked span"


# --- the refusal variant (UX spec 6.2, F-05) --------------------------


def test_a_refusal_is_styled_as_an_outcome_and_never_as_an_error(sanad):
    """Design principle 2: "A refusal is a first-class answer ... If
    refusals look like errors, users learn to distrust the honest path,
    which is the behaviour the product exists to demonstrate."

    So this asserts the refusal class IS present and the error class is
    NOT. Half of it would pass on a screen that rendered every refusal in
    the danger panel."""
    build, workspace, _ = sanad
    client, runtime = build(
        ScriptedChat(
            '{"clarification":null,"queries":["tajine pruneaux cuisine"]}',
            "OFF_TOPIC",
        )
    )

    _ask(client, "Comment cuisiner un tajine aux pruneaux ?")
    page = _settled(client, runtime, workspace.id)

    assert "bubble--refusal" in page
    assert "panel--error" not in page
    # F-05: it states what was searched.
    assert "What Sanad searched for" in page
    assert "tajine" in page


def test_a_writer_that_declines_also_refuses_rather_than_erroring(sanad):
    """The second door into F-05 (ST-24's): the sections were read and
    they do not answer. It must land in the same refusal variant, not in
    the error panel -- a decline is the product working, not breaking."""
    build, workspace, _ = sanad
    client, runtime = build(ScriptedChat(QUERY_PLAN, "RELEVANT", NOT_COVERED))

    _ask(client, "Quel est le taux de cotisation CNSS en 2026 ?")
    page = _settled(client, runtime, workspace.id)

    assert "bubble--refusal" in page
    assert "panel--error" not in page


# --- the clarification variant (UX spec 6.2, F-06) --------------------


def test_an_ambiguous_question_asks_once_then_resumes_after_the_reply(sanad):
    """ST-22's full exit gate through the shipping composition."""
    build, workspace, _ = sanad
    original = "Parlez-moi de cette procedure."
    asked = "De quelle procedure parlez-vous ?"
    reply = "La procedure de la periode d'essai."
    model = ScriptedChat(
        '{"clarification":"De quelle procedure parlez-vous ?","queries":[]}',
        QUERY_PLAN,
        "RELEVANT",
        WRITTEN_ANSWER,
    )
    client, runtime = build(model)

    _ask(client, original)
    page = _settled(client, runtime, workspace.id)
    assert "bubble--clarification" in page
    assert asked in _visible(page)
    assert page.count("bubble--clarification") == 1

    _ask(client, reply)
    page = _settled(client, runtime, workspace.id)
    visible = _visible(page)
    assert page.count("bubble--clarification") == 1
    assert WRITTEN_ANSWER in visible
    assert visible.index(original) < visible.index(asked) < visible.index(reply)
    assert original in model.calls[1][1]
    assert asked in model.calls[1][1]
    assert reply in model.calls[1][1]
    assert len(model.calls) == 4


# --- the error state (PRD section 8, UX spec 11) ----------------------


def test_an_unreachable_answering_service_renders_the_error_panel(sanad):
    """Section 11: "Answering service unreachable | S1 | `ErrorPanel` with
    retry, no fabricated fallback". UX spec 5: the panel shows the exact
    failing value."""
    build, workspace, _ = sanad
    client, runtime = build()

    def broken() -> AgentPorts:
        raise RuntimeError("cloud mode needs SANAD_CLOUD_API_KEY; it is empty")

    runtime.ports_factory = broken

    _ask(client)
    page = _settled(client, runtime, workspace.id)

    assert "panel--error" in page
    assert "SANAD_CLOUD_API_KEY" in page, "the panel must name the failing value"
    assert 'role="alert"' in page
    # "No fabricated fallback": nothing that looks like an answer.
    assert "msg--answer" not in page
    assert WRITTEN_ANSWER not in _visible(page)


def test_a_model_that_breaks_mid_run_also_lands_in_the_error_panel(sanad):
    """The other half: the ports built fine and the call failed. Both
    reach the same panel, because to the reader they are one failure."""
    build, workspace, _ = sanad

    class Exploding:
        def complete(self, system: str, user: str) -> str:
            raise ConnectionError("connection refused by 127.0.0.1:11434")

    client, runtime = build(Exploding())

    _ask(client)
    page = _settled(client, runtime, workspace.id)

    assert "panel--error" in page
    assert "11434" in page


# --- cancel, and criterion 8 -----------------------------------------


def test_cancelling_leaves_something_marked_incomplete_and_never_final(sanad):
    """UX spec 6.3: "A cancel action is available and stops after the
    current stage." Criterion 8: whatever settles is visibly marked
    incomplete and no control presents it as a finished answer."""
    build, workspace, _ = sanad
    gate = Gate()
    clarification = "Which procedure do you mean?"
    client, runtime = build(
        ScriptedChat(
            '{"clarification":"Which procedure do you mean?","queries":[]}'
        )
    )
    _hold(runtime, gate, "clarify")

    client.post("/chat/ask", data={"question": QUESTION}, follow_redirects=False)
    assert gate.reached.wait(WAIT), "the run never reached query planning"
    client.post("/chat/cancel", follow_redirects=False)
    gate.release.set()
    page = _settled(client, runtime, workspace.id)

    assert "msg--interrupted" in page
    assert "Incomplete" in page
    assert "msg--answer" not in page
    assert "bubble--clarification" not in page
    assert clarification not in _visible(page)
    assert WRITTEN_ANSWER not in _visible(page)


def test_cancelling_a_resumed_query_plan_discards_its_result(sanad):
    build, workspace, _ = sanad
    original = "Parlez-moi de cette procedure."
    asked = "De quelle procedure parlez-vous ?"
    model = ScriptedChat(
        '{"clarification":"De quelle procedure parlez-vous ?","queries":[]}',
        QUERY_PLAN,
    )
    client, runtime = build(model)

    _ask(client, original)
    first_page = _settled(client, runtime, workspace.id)
    assert asked in _visible(first_page)

    gate = Gate()
    _hold(runtime, gate, "rewrite")
    client.post(
        "/chat/ask",
        data={"question": "La procedure de la periode d'essai."},
        follow_redirects=False,
    )
    assert gate.reached.wait(WAIT), "the resumed run never reached query planning"
    client.post("/chat/cancel", follow_redirects=False)
    gate.release.set()
    page = _settled(client, runtime, workspace.id)

    assert "msg--interrupted" in page
    assert "Incomplete" in page
    assert "msg--answer" not in page
    assert len(model.calls) == 2


# --- F-09, criteria 2 and 3 ------------------------------------------


def test_every_evidence_seal_links_to_a_real_source_card_in_order(sanad):
    """v2.1 evidence strip: each seal under the answer must land on the card
    it names. A seal pointing at an id no card carries is a citation that
    goes nowhere, which is worse than no seal. Numbering starts at 1 and
    matches the card's own seal, in the same order."""
    build, workspace, _ = sanad
    client, runtime = build()

    _ask(client)
    page = _settled(client, runtime, workspace.id)

    strip = page.split('class="evidence"')[1].split("</ul>")[0]
    targets = re.findall(r'href="#(source-\d+-\d+)"', strip)
    assert targets, "the answer carries sources but no evidence seals"
    for target in targets:
        assert page.count(f'id="{target}"') == 1, f"seal #{target} has no card"
    strip_numbers = re.findall(r'<span class="seal">(\d+)</span>', strip)
    assert strip_numbers == [str(n) for n in range(1, len(targets) + 1)]
    card_ids = re.findall(r'<li class="source" id="(source-\d+-\d+)"', page)
    assert card_ids[: len(targets)] == targets


def test_a_legal_workspace_shows_the_disclaimer_between_answer_and_sources(sanad):
    """Criterion 2, and UX spec 6.2's placement: "directly under the
    answer body, above the source cards"."""
    build, workspace, _ = sanad
    client, runtime = build(legal_flag=True)

    _ask(client)
    page = _settled(client, runtime, workspace.id)

    assert 'class="disclaimer"' in page
    assert page.index("answer__text") < page.index('class="disclaimer"')
    assert page.index('class="disclaimer"') < page.index('class="sources"')


def test_the_f10_trace_sits_after_sources_so_the_disclaimer_stays_under_the_answer(
    sanad,
):
    """UX spec 6.2 puts the disclaimer "directly under the answer body";
    F-10's trace disclosure must not wedge itself in between."""
    build, workspace, _ = sanad
    client, runtime = build(legal_flag=True)

    _ask(client)
    page = _settled(client, runtime, workspace.id)

    assert page.count('class="trace"') == 1
    assert page.index('class="sources"') < page.index('class="trace"')


def test_an_unflagged_workspace_shows_no_disclaimer_anywhere(sanad):
    """Criterion 3. The control half of the test above: without it,
    "the line appears" is equally true of a screen that always shows it."""
    build, workspace, _ = sanad
    client, runtime = build()

    _ask(client)
    page = _settled(client, runtime, workspace.id)

    assert "msg--answer" in page, "there must be an answer for it to be absent from"
    assert 'class="disclaimer"' not in page


def test_a_legal_workspace_also_disclaims_an_honest_refusal(sanad):
    """OpenAPI Answer.disclaimer is true for every response kind from a
    legal workspace, including the first-class refusal outcome."""
    build, workspace, _ = sanad
    client, runtime = build(
        ScriptedChat(
            '{"clarification":null,"queries":["tajine pruneaux cuisine"]}',
            "OFF_TOPIC",
        ),
        legal_flag=True,
    )

    _ask(client, "Comment cuisiner un tajine aux pruneaux ?")
    page = _settled(client, runtime, workspace.id)

    assert "bubble--refusal" in page
    assert 'class="disclaimer"' in page


# --- new conversation (UX spec 6.2) ----------------------------------


def test_a_follow_up_uses_the_completed_trial_period_exchange(sanad):
    """F-07: follow-up resolves, then compact memory replaces old raw turns."""
    build, workspace, _ = sanad
    summary = "La conversation porte sur la periode d'essai des cadres."
    rolled_summary = (
        "La periode d'essai des cadres dure trois mois et se renouvelle une fois."
    )
    renewal_answer = "La periode d'essai peut etre renouvelee une seule fois."
    notice_answer = "Le renouvellement doit etre notifie par ecrit."
    model = ScriptedChat(
        QUERY_PLAN,
        "RELEVANT",
        WRITTEN_ANSWER,
        summary,
        '{"clarification":null,"queries":["renouvellement periode essai"]}',
        "RELEVANT",
        renewal_answer,
        rolled_summary,
        '{"clarification":null,"queries":["notification renouvellement essai"]}',
        "RELEVANT",
        notice_answer,
    )
    client, runtime = build(model)

    _ask(client)
    _settled(client, runtime, workspace.id)
    _ask(client, "Et combien de renouvellements ?")
    page = _settled(client, runtime, workspace.id)

    assert renewal_answer in _visible(page)
    assert summary in model.calls[4][1]
    assert runtime.conversation(workspace.id).messages[-1].searched == (
        "renouvellement periode essai",
    )

    _ask(client, "Et comment est-il notifie ?")
    page = _settled(client, runtime, workspace.id)

    assert notice_answer in _visible(page)
    payload = json.loads(model.calls[7][1].split("Session memory as JSON:\n", 1)[1])
    assert payload == {
        "previous_summary": summary,
        "new_completed_turns": [
            {
                "question": "Et combien de renouvellements ?",
                "answer": renewal_answer,
            }
        ],
    }
    assert QUESTION not in model.calls[7][1], "the first raw turn was already folded"
    assert len(model.calls) == 11


def test_a_follow_up_after_new_conversation_gets_no_earlier_context(sanad):
    """F-07: New conversation removes both the transcript and its memory."""
    build, workspace, _ = sanad
    clarification = "De quel sujet demandez-vous le nombre de renouvellements ?"
    model = ScriptedChat(
        QUERY_PLAN,
        "RELEVANT",
        WRITTEN_ANSWER,
        '{"clarification":"De quel sujet demandez-vous le nombre de '
        'renouvellements ?","queries":[]}',
    )
    client, runtime = build(model)

    _ask(client)
    _settled(client, runtime, workspace.id)
    client.post("/chat/new", follow_redirects=False)
    _ask(client, "Et combien de renouvellements ?")
    page = _settled(client, runtime, workspace.id)

    assert clarification in _visible(page)
    assert "Earlier conversation summary:\n(none)" in model.calls[3][1]
    assert len(model.calls) == 4, "a cleared conversation must not call the summarizer"


def test_a_new_conversation_clears_the_transcript(sanad):
    build, workspace, _ = sanad
    client, runtime = build()

    _ask(client)
    _settled(client, runtime, workspace.id)
    client.post("/chat/new", follow_redirects=False)
    page = client.get("/").text

    assert WRITTEN_ANSWER not in _visible(page)
    assert "Every answer carries the sources it was written from." in page


# --- the shell (UX spec 4) -------------------------------------------


def test_the_app_does_not_hold_qdrant_while_serving_reports(tmp_path, monkeypatch):
    """The evaluator can own embedded Qdrant while S3 remains available."""
    settings = get_settings().model_copy(
        update={"qdrant_storage_path": str(tmp_path / "qdrant")}
    )
    monkeypatch.setattr(vector_store, "get_settings", lambda: settings)
    runtime = Runtime(db_path=tmp_path / "sanad.db")

    assert runtime.client is None
    with TestClient(create_app(runtime)) as client:
        with vector_store.open_store() as external_client:
            assert external_client is not None
            assert client.get("/reports").status_code == 200
        assert runtime.client is None
    assert runtime.client is None


def test_default_chat_ports_hold_qdrant_for_the_whole_context(tmp_path, monkeypatch):
    settings = get_settings().model_copy(
        update={"qdrant_storage_path": str(tmp_path / "qdrant")}
    )
    monkeypatch.setattr(vector_store, "get_settings", lambda: settings)
    monkeypatch.setattr(app_module, "build_default_ports", lambda client: client)
    runtime = Runtime(db_path=tmp_path / "sanad.db")

    with runtime.ports() as client:
        assert client is not None
        with pytest.raises(vector_store.StoreAlreadyOpenError):
            with vector_store.open_store():
                pass

    with vector_store.open_store() as reopened:
        assert reopened is not None


def test_a_passage_link_never_resolves_against_another_workspace(sanad):
    """F-01 isolation, at the URL.

    Addressed by message and index alone, the link resolved against
    whatever workspace happened to be ACTIVE when it was followed -- so
    switching workspace and pressing Back served message 3, card 1 of a
    different conversation, looking entirely correct.

    The second workspace here holds no conversation at all, so its
    message index cannot exist: the page must say the passage is gone
    rather than quietly serve the other workspace's section."""
    build, workspace, db_path = sanad
    client, runtime = build()
    _ask(client)
    page = _settled(client, runtime, workspace.id)
    href = page.split('href="/chat/passage/')[1].split('"')[0]
    assert workspace.id in href, "the link must name its own workspace"

    other = workspaces.create_workspace(
        name="Manuals", folder_path="/tmp/manuals", db_path=db_path
    )
    # Follow the SAME message/card coordinates against the other workspace.
    _ws, message, index = href.split("/")
    served = client.get(f"/chat/passage/{other.id}/{message}/{index}").text

    assert "no longer on screen" in served
    assert "MARQUEUR" not in served
    assert "<mark" not in served


def test_the_error_panel_cannot_print_the_configured_api_key(sanad, monkeypatch):
    """Core law: never log a secret.

    UX spec 5 requires the panel to show "the exact failing value", and
    provider SDKs put the request URL in exception text -- for Google AI
    Studio that URL carries `?key=...`. Verbatim is the requirement;
    verbatim enough to print the key is not.

    The key is redacted by exact value rather than by looking for
    something key-shaped, so this test sets a real one in config and
    raises an exception carrying it."""
    secret = "AIzaSyTHIS-IS-THE-KEY-0000000000000000000"
    settings = get_settings().model_copy(update={"cloud_api_key": secret})
    monkeypatch.setattr(ui.conversation, "get_settings", lambda: settings)

    build, workspace, _ = sanad
    client, runtime = build()

    def leaky() -> AgentPorts:
        raise RuntimeError(
            f"400 from https://generativelanguage.googleapis.com/v1/models?key={secret}"
        )

    runtime.ports_factory = leaky
    _ask(client)
    page = _settled(client, runtime, workspace.id)

    assert "panel--error" in page
    assert secret not in page, "the API key must never reach the screen"
    assert "[redacted]" in page
    # The rest of the message must survive, or the panel stops naming the
    # failing value and becomes the bare "something went wrong" UX spec 5
    # forbids.
    assert "generativelanguage.googleapis.com" in page


def test_switching_workspace_says_the_conversation_context_has_moved(sanad):
    """UX spec 4, the half of that sentence an earlier version missed:
    changing the workspace "clears nothing and interrupts nothing, but the
    chat area shows a one-line notice that the conversation context has
    moved"."""
    build, workspace, db_path = sanad
    client, runtime = build()
    other = workspaces.create_workspace(
        name="Manuals", folder_path="/tmp/manuals", db_path=db_path
    )

    moved = client.post(
        "/workspace", data={"workspace_id": other.id}, follow_redirects=True
    ).text
    assert "conversation context has moved" in moved
    assert "Manuals" in moved

    # And it is a notice about ONE navigation, not a banner that sticks:
    # a plain visit afterwards must not still be announcing the move.
    assert "conversation context has moved" not in client.get("/").text


def test_the_rtl_preview_flips_the_document_direction(sanad):
    """UX spec 6.5: "Verify with an RTL preview even though V1 ships LTR."

    The preview is the whole mechanism -- there is no locale switch and no
    Arabic copy (UX spec 14, assumption 3). It exists so acceptance
    criterion 11 can be looked at, and so open risk 3's "specified but
    never exercised" stops being true for the layout half.

    The hostile value is checked in the same test because `dir` is written
    straight onto the document element: anything that is not "rtl" must
    come back "ltr", never the caller's string."""
    build, workspace, _ = sanad
    client, _runtime = build()

    assert 'dir="ltr"' in client.get("/").text
    assert 'dir="rtl"' in client.get("/?dir=rtl").text
    assert 'dir="ltr"' in client.get('/?dir="><script>').text


def test_an_arabic_workspace_auto_mirrors_the_whole_screen(sanad, monkeypatch, tmp_path):
    """F-14's real trigger (not the `?dir=` preview above): PRD acceptance
    criterion "the surrounding screen mirrors" needs to happen with NO
    query parameter, purely because the active workspace's own stored
    text is Arabic (DECISIONS.md, 2026-09-13).

    Builds real parent JSON files (`parent_store.save_parents`, the exact
    shape ST-16's Sync writes) holding majority-Arabic text, and points
    `ui.rtl`'s settings read at them -- the same `get_settings.cache_
    clear()` pattern `tests/unit/test_workspaces.py` uses to override a
    setting for one test."""
    import ui.rtl as rtl_module
    from chunking import Parent
    from config import get_settings

    build, workspace, db_path = sanad
    client, runtime = build()

    arabic_dir = tmp_path / "arabic-parents"
    parent_store.save_parents(
        parents=[
            Parent(
                id="p1",
                text=(
                    "المادة 13: مدة التجربة ثلاثة أشهر للأطر وللأجير الحق "
                    "في المغادرة بدون إخطار مسبق في جميع الأحوال."
                ),
                source_file=SOURCE_FILE,
                section_label="المادة 13",
            )
        ],
        workspace_id=workspace.id,
        base_path=arabic_dir,
    )
    fake_settings = get_settings().model_copy(update={"parent_store_path": str(arabic_dir)})
    monkeypatch.setattr(rtl_module, "get_settings", lambda: fake_settings)

    page = client.get("/").text

    # S6 (2026-09-13): <html lang> follows the INTERFACE language (English
    # in this suite) so the screen reader reads the copy correctly; Arabic
    # CONTENT still mirrors the screen, and each Arabic block carries its
    # own lang="ar". Asserted on the <html> tag itself: a bare 'lang="ar"'
    # anywhere on the page is always true (the brand seal carries it).
    assert '<html lang="en" dir="rtl">' in page
    # And it is the CONTENT, not a side effect of the fixture's db/config --
    # the same client, workspace and settings override with an EMPTY
    # arabic_dir (nothing written to it) must stay LTR/English, or this
    # test would pass for any reason at all.
    empty_dir = tmp_path / "empty-parents"
    empty_settings = get_settings().model_copy(update={"parent_store_path": str(empty_dir)})
    monkeypatch.setattr(rtl_module, "get_settings", lambda: empty_settings)
    control_page = client.get("/").text
    assert '<html lang="en" dir="ltr">' in control_page


def test_a_french_workspace_does_not_auto_mirror(sanad):
    """The companion negative: the `sanad` fixture's own HR_DOCUMENT is
    French, stored under its own tmp `parents_dir` (not the settings
    default `ui.rtl.workspace_is_arabic` reads with no override), so this
    also doubles as proof that a workspace `ui.rtl` cannot see at all
    reads as the honest "not Arabic" rather than erroring."""
    build, _workspace, _ = sanad
    client, _runtime = build()

    page = client.get("/").text

    assert '<html lang="en" dir="ltr">' in page


def test_the_rtl_preview_override_does_not_force_lang_ar(sanad):
    """`_lang` is deliberately NOT driven by the `?dir=` preview override
    (app.py's `_lang` docstring): the preview carries no Arabic copy, so
    forcing `lang="ar"` on English preview text would misinform a screen
    reader rather than test anything. Only real detected Arabic content
    sets `lang="ar"` -- proven together so a future change that makes
    `_lang` reuse `_direction`'s post-override value cannot pass by
    accident."""
    build, _workspace, _ = sanad
    client, _runtime = build()

    page = client.get("/?dir=rtl").text

    assert '<html lang="en" dir="rtl">' in page


def test_an_arabic_answer_gets_dir_auto_and_lang_ar_while_the_french_question_does_not(
    sanad,
):
    """Per-element direction (task brief item 1), independent of whatever
    the whole page's `dir`/`lang` end up being: the FRENCH question
    bubble and the ARABIC answer bubble sit in the same transcript and
    must read in their own scripts, not the page's."""
    build, workspace, _ = sanad
    arabic_answer = (
        "مدة التجربة ثلاثة "
        "أشهر للأطر."
    )
    client, runtime = build(model=ScriptedChat(QUERY_PLAN, "RELEVANT", arabic_answer))

    _ask(client)
    page = _settled(client, runtime, workspace.id)

    assert 'class="bubble bubble--user" dir="auto">' in page, (
        "the French user bubble must still carry dir=auto (item 1), just not lang=ar"
    )
    assert f'class="answer__text" dir="auto" lang="ar">{arabic_answer}' in _visible(page)


def test_a_question_containing_markup_is_shown_as_text_not_run_as_markup(sanad):
    """The escaping `_visible` works around, asserted directly.

    The transcript, the source cards and the passage viewer all render
    text that came from outside the product -- what the operator typed,
    and what is inside their PDFs. `ui/conversation.py` cuts a passage
    into segments and lets Jinja escape each one rather than splicing
    `<mark>` into a string and marking it safe, and this is the check that
    the decision holds end to end."""
    build, workspace, _ = sanad
    client, runtime = build()
    hostile = "<script>alert('x')</script> periode d'essai"

    _ask(client, hostile)
    page = _settled(client, runtime, workspace.id)

    assert "<script>alert" not in page
    assert "&lt;script&gt;" in page
    assert hostile in _visible(page)


def test_the_skip_link_is_the_first_focusable_element(sanad):
    """UX spec 4, verbatim. Asserted on position, because a skip link that
    is on the page but third in the tab order does not do its job."""
    build, workspace, _ = sanad
    client, _runtime = build()

    page = client.get("/").text
    body = page.split("<body>")[1]

    assert body.index("skip-link") < body.index("<header")


def test_shared_shell_keyboard_order_starts_with_skip_name_and_workspace(sanad):
    build, _workspace, _ = sanad
    client, _runtime = build()

    body = client.get("/").text.split("<body>")[1]

    assert body.index("skip-link") < body.index('class="shell__name"')
    assert body.index('class="shell__name"') < body.index('id="workspace-select"')
    assert body.index('id="workspace-select"') < body.index(">Chat</a>")


def test_the_legal_marker_rides_with_the_workspace_selector(sanad):
    """UX spec 4: the selector shows the name and, when the legal flag is
    set, a small persistent marker -- as TEXT, since no status in this
    interface may be carried by colour alone (criterion 10)."""
    build, workspace, _ = sanad
    client, _runtime = build(legal_flag=True)

    page = client.get("/").text

    assert 'class="marker"' in page
    assert ">Legal<" in page


# --- F-10: the trace disclosure ----------------------------------------
#
# PRD acceptance criterion: "for each answer, the user can open a trace
# that lists the searches run, the files consulted, and the retries
# used." `ui.conversation.message_for` reads this straight off the real
# `Answer.trace` (agent/trace.py); these tests push a `Message` built from
# a hand-shaped `Trace` straight onto the transcript and fetch the page,
# rather than driving the real agent's retry loop to produce one --
# that loop already has its own tests (test_ask_retry_loop.py), and what
# F-10 adds is how a trace RENDERS, not how one gets filled in.


def _trace_answer(
    kind: AnswerKind,
    text: str,
    steps: tuple[TraceStep, ...],
) -> Answer:
    return Answer(
        kind=kind,
        text=text,
        sources=(),
        session_id="session-f10",
        trace=Trace(trace_id="trace-f10", steps=steps),
    )


def _show(client, runtime, workspace_id: str, message: Message) -> str:
    runtime.conversation(workspace_id).messages.append(message)
    return client.get("/").text


def test_the_trace_discloses_every_search_file_and_retry_and_escapes_them(sanad):
    """The full shape in one go: two searches (so the query TEXT of each
    must appear, not merely a count), the first file name repeated in the
    second search (de-dup has something to fail), one reword between them,
    and a REFUSAL variant (F-05's own "what Sanad searched for" list is a
    different component; this proves the new one appears there too). A
    hostile search string AND a hostile file name stand in for anything
    typed by a person or read out of a document's own metadata -- both
    loops in the disclosure must escape, not just one."""
    build, workspace, _ = sanad
    client, runtime = build()
    hostile_search = "<script>alert('x')</script> essai"
    hostile_file = "<img src=x onerror=alert(1)>.pdf"
    message = message_for(
        _trace_answer(
            AnswerKind.REFUSAL,
            "I could not find this in the workspace.",
            (
                TraceStep(StepKind.SEARCH, hostile_search, (SOURCE_FILE,)),
                TraceStep(StepKind.REWORD, "reworded"),
                TraceStep(
                    StepKind.SEARCH,
                    "duree periode essai cadre",
                    (SOURCE_FILE, hostile_file),
                ),
            ),
        )
    )
    page = _show(client, runtime, workspace.id, message)

    assert "How this answer was found" in page
    assert "<script>alert" not in page
    assert "<img src=x" not in page
    assert "&lt;script&gt;" in page
    assert "&lt;img src=x" in page
    assert hostile_search in _visible(page)
    assert hostile_file in _visible(page)
    assert "duree periode essai cadre" in page
    assert "Retries: 1" in page

    trace_html = page.split("Files consulted")[1].split("</details>")[0]
    assert trace_html.count(SOURCE_FILE) == 1, "the repeated file must be de-duplicated"
    assert trace_html.index(SOURCE_FILE) < trace_html.index("&lt;img src=x"), (
        "first-seen order: the file the FIRST search found comes first"
    )


def test_a_real_answer_with_no_retries_says_none(sanad):
    """A real run through the whole pipeline (real chunking, real search,
    real trace), not a hand-built one: the scripted model accepts the
    first search, so there is exactly one search and zero rewords. 'none'
    is the acceptance criterion's own word for a zero count, and a bare
    '0' or a missing line would both be wrong."""
    build, workspace, _ = sanad
    client, runtime = build()

    _ask(client)
    page = _settled(client, runtime, workspace.id)

    assert "How this answer was found" in page
    assert "duree periode essai cadre renouvellement" in page
    assert SOURCE_FILE in page
    assert "Retries: none" in page


def test_a_message_with_no_trace_renders_no_disclosure(sanad):
    """Design note: "If an answer has no trace ... render nothing, not an
    empty box." A message that never went through `message_for` -- the
    shape a message restored without its trace would take -- must not
    grow an empty disclosure."""
    build, workspace, _ = sanad
    client, runtime = build()

    page = _show(
        client,
        runtime,
        workspace.id,
        Message(kind=MessageKind.ANSWER, text="Restored without a trace."),
    )

    assert "Restored without a trace." in page
    assert "How this answer was found" not in page
    assert "trace__body" not in page


# --- F-15 answer feedback (V2, Low) -----------------------------------------
#
# PRD F-15 / UX spec S1+S3: thumbs up/down plus an optional comment on one
# answer or refusal, idempotent per answer, reviewable on Reports. These
# tests exercise the real POST /chat/feedback route and read the real
# `answer_feedback` table back -- the same shape test_evidence_only_mode.py
# uses to prove a claim by what is IN THE DATABASE, not only by the page.


def _feedback_rows(db_path):
    with repo.session(db_path) as conn:
        return conn.execute(
            "SELECT * FROM answer_feedback ORDER BY created_at"
        ).fetchall()


def _answer_id(runtime, workspace_id: str, index: int = -1) -> str:
    return runtime.conversation(workspace_id).messages[index].id


def test_thumbs_down_with_a_comment_is_saved_and_shown_as_the_current_verdict(sanad):
    """The acceptance criterion itself: mark an answer down, add a
    comment, and the pair is stored -- plus the S1 half of "reviewable",
    which is the saved state re-rendering as the CURRENT verdict rather
    than a fresh, unanswered form."""
    build, workspace, db_path = sanad
    client, runtime = build()
    _ask(client)
    _settled(client, runtime, workspace.id)
    message_id = _answer_id(runtime, workspace.id)

    response = client.post(
        "/chat/feedback",
        data={
            "workspace_id": workspace.id,
            "message_id": message_id,
            "verdict": "down",
            "comment": "Cited the wrong article.",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    rows = _feedback_rows(db_path)
    assert len(rows) == 1
    assert rows[0]["workspace_id"] == workspace.id
    assert rows[0]["answer_key"] == message_id
    assert rows[0]["verdict"] == "down"
    assert rows[0]["comment"] == "Cited the wrong article."
    assert rows[0]["question"] == QUESTION
    assert rows[0]["answer_text"] == WRITTEN_ANSWER

    page = client.get("/").text
    assert "Thanks" in page and "feedback saved" in page
    assert "Helpful" in page and "Not helpful" in page
    # The CHOSEN button, specifically, carries aria-pressed="true" -- not
    # merely a true SOMEWHERE on the page, which a copy-paste of the wrong
    # attribute onto the Helpful button would still satisfy.
    down_button = page.split('name="verdict" value="down">')[1].split("</form>")[0]
    assert 'aria-pressed="true"' in down_button
    up_button = page.split('name="verdict" value="up">')[1].split("</form>")[0]
    assert 'aria-pressed="false"' in up_button


def test_giving_feedback_on_the_same_answer_twice_keeps_one_row_with_the_latest_verdict(
    sanad,
):
    """Idempotency (task brief): thumbs up then thumbs down on the SAME
    answer must settle on one row, carrying the second verdict, never
    two rows and never the first verdict surviving."""
    build, workspace, db_path = sanad
    client, runtime = build()
    _ask(client)
    _settled(client, runtime, workspace.id)
    message_id = _answer_id(runtime, workspace.id)

    client.post(
        "/chat/feedback",
        data={"workspace_id": workspace.id, "message_id": message_id, "verdict": "up"},
        follow_redirects=False,
    )
    client.post(
        "/chat/feedback",
        data={
            "workspace_id": workspace.id,
            "message_id": message_id,
            "verdict": "down",
            "comment": "Changed my mind.",
        },
        follow_redirects=False,
    )

    rows = _feedback_rows(db_path)
    assert len(rows) == 1, "one click after another must update, never duplicate"
    assert rows[0]["verdict"] == "down"
    assert rows[0]["comment"] == "Changed my mind."


def test_feedback_lands_on_the_right_answer_not_a_neighboring_one(sanad):
    """With two real answers in one conversation, feedback posted against
    the SECOND must attach to the second, not silently fall back onto the
    first -- the failure a single-answer fixture cannot expose, and the
    one a lookup that ignored the posted id and always returned the
    first eligible message would still pass if this test targeted the
    first answer instead."""
    build, workspace, db_path = sanad
    renewal_answer = "La periode d'essai peut etre renouvelee une seule fois."
    model = ScriptedChat(
        QUERY_PLAN,
        "RELEVANT",
        WRITTEN_ANSWER,
        "resume de la conversation",
        '{"clarification":null,"queries":["renouvellement periode essai"]}',
        "RELEVANT",
        renewal_answer,
    )
    client, runtime = build(model)
    _ask(client)
    _settled(client, runtime, workspace.id)
    _ask(client, "Et combien de renouvellements ?")
    _settled(client, runtime, workspace.id)

    messages = runtime.conversation(workspace.id).messages
    assert [m.kind for m in messages] == [
        MessageKind.USER,
        MessageKind.ANSWER,
        MessageKind.USER,
        MessageKind.ANSWER,
    ]
    first_id, second_id = messages[1].id, messages[3].id
    assert first_id != second_id

    client.post(
        "/chat/feedback",
        data={
            "workspace_id": workspace.id,
            "message_id": second_id,
            "verdict": "down",
            "comment": "Only the second answer was wrong.",
        },
        follow_redirects=False,
    )

    rows = _feedback_rows(db_path)
    assert len(rows) == 1
    assert rows[0]["answer_key"] == second_id
    assert rows[0]["answer_text"] == renewal_answer
    assert rows[0]["question"] == "Et combien de renouvellements ?"

    page = client.get("/").text
    # The first answer's own button must still read unset -- only one
    # aria-pressed="true" on the whole page, on the SECOND answer's
    # button, never a state that leaked onto its neighbor.
    assert page.count('aria-pressed="true"') == 1


def test_a_bad_verdict_is_rejected_with_no_row_written(sanad):
    build, workspace, db_path = sanad
    client, runtime = build()
    _ask(client)
    _settled(client, runtime, workspace.id)
    message_id = _answer_id(runtime, workspace.id)

    response = client.post(
        "/chat/feedback",
        data={
            "workspace_id": workspace.id,
            "message_id": message_id,
            "verdict": "sideways",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303, "refused cleanly, never a 500"
    assert _feedback_rows(db_path) == []
    page = client.get("/").text
    assert "could not be saved" in page


def test_an_over_long_comment_is_rejected_with_no_row_written(sanad):
    build, workspace, db_path = sanad
    client, runtime = build()
    _ask(client)
    _settled(client, runtime, workspace.id)
    message_id = _answer_id(runtime, workspace.id)
    too_long = "x" * (get_settings().feedback_comment_max_chars + 1)

    response = client.post(
        "/chat/feedback",
        data={
            "workspace_id": workspace.id,
            "message_id": message_id,
            "verdict": "down",
            "comment": too_long,
        },
        follow_redirects=False,
    )

    assert response.status_code == 303, "refused cleanly, never a 500"
    assert _feedback_rows(db_path) == []
    page = client.get("/").text
    assert "could not be saved" in page


def test_an_unknown_answer_id_is_a_clear_error_not_a_500(sanad):
    build, workspace, db_path = sanad
    client, runtime = build()
    _ask(client)
    _settled(client, runtime, workspace.id)

    response = client.post(
        "/chat/feedback",
        data={
            "workspace_id": workspace.id,
            "message_id": "no-such-message-id",
            "verdict": "up",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303, "refused cleanly, never a 500"
    assert _feedback_rows(db_path) == []
    page = client.get("/").text
    assert "no longer on screen" in page


def test_feedback_is_declined_harmlessly_in_evidence_only_mode(tmp_path, monkeypatch):
    """ST-05: no ANSWER/REFUSAL can exist in evidence-only mode (Chat
    itself refuses before a question is ever asked), so the controls this
    posts from never render there -- but the route itself must still
    refuse cleanly rather than trust that coincidence, per the task
    brief's explicit decide-and-test instruction."""
    install_fake_encoders(monkeypatch)
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    workspace = workspaces.create_workspace(
        name="HR", folder_path=str(tmp_path / "corpus"), db_path=db_path
    )
    runtime = Runtime(db_path=db_path)
    client = TestClient(create_app(runtime))
    settings = get_settings().model_copy(update={"evidence_only": True})
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)

    response = client.post(
        "/chat/feedback",
        data={
            "workspace_id": workspace.id,
            "message_id": "whatever",
            "verdict": "up",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert _feedback_rows(db_path) == []


def test_feedback_route_is_behind_the_access_gate_when_a_password_is_set(
    sanad, monkeypatch
):
    """`AccessGate` is installed app-wide (app.py::create_app); this pins
    that `/chat/feedback` was never added to its narrow exemption list
    (only GET /api/v1/health and /static/* are open)."""
    build, workspace, db_path = sanad
    client, runtime = build()
    _ask(client)
    _settled(client, runtime, workspace.id)
    message_id = _answer_id(runtime, workspace.id)

    settings = get_settings().model_copy(update={"access_password": "secret"})
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)
    gated_client = TestClient(create_app(runtime))

    response = gated_client.post(
        "/chat/feedback",
        data={"workspace_id": workspace.id, "message_id": message_id, "verdict": "up"},
        follow_redirects=False,
    )

    assert response.status_code == 401
    assert _feedback_rows(db_path) == []
