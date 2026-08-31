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
docs/phase2/CLAUDE.md's hard rule is that tests use a scripted fake and
carry no API keys.

WHAT THIS THEREFORE DOES NOT PROVE: that a real model writes a good
answer. It proves that each state the specification names renders, that
the variants are distinguishable from one another, and that the stage
hints track the agent rather than a clock.
"""

from __future__ import annotations

import dataclasses
import html
import threading

import pytest
from fastapi.testclient import TestClient

import chunking
import embeddings
import parent_store
import ui.conversation
import vector_store
import workspaces
from agent.answering import NOT_COVERED
from agent.ports import AgentPorts
from app import Runtime, create_app
from config import get_settings
from db import repo
from tests.fake_chat import ScriptedChat
from tests.fake_encoders import install as install_fake_encoders
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

# Long enough to time out loudly rather than hang a CI run for ever, short
# enough that a real deadlock is noticed in one coffee rather than one
# afternoon.
WAIT = 10


class Gate:
    """Hold one port open until the test says otherwise.

    This is what makes the loading state observable: without it the run
    finishes in milliseconds and there is no in-flight page to fetch. It
    is also what makes the stage assertions DISCRIMINATING -- the same
    question is blocked at three different ports and must report three
    different stages. A timer-driven screen (which is what the React
    reference ships) would print the same label at the same elapsed time
    in all three."""

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
                    model or ScriptedChat("RELEVANT", WRITTEN_ANSWER),
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

    THE PARAMETRISATION IS THE TEST. One question is held at three
    different ports and must report three different stages. A screen that
    advanced a counter on a timer -- which is exactly what
    `designrag-main/src/components/ChatScreen.tsx:111` does -- would show
    the same label in all three rows and fail two of them."""
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
    client, runtime = build(ScriptedChat("OFF_TOPIC"))

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
    client, runtime = build(ScriptedChat("RELEVANT", NOT_COVERED))

    _ask(client, "Quel est le taux de cotisation CNSS en 2026 ?")
    page = _settled(client, runtime, workspace.id)

    assert "bubble--refusal" in page
    assert "panel--error" not in page


# --- the clarification variant (UX spec 6.2, F-06) --------------------


def test_a_clarification_renders_exactly_one_question(sanad):
    """F-06 is explicit that there is exactly one. ST-22 owns the clarify
    port and is unbuilt, so this drives the real graph with a clarify port
    written out loud -- the same move `tests/integration/
    test_ask_sourced_answer.py` makes for the ports it does not own.

    THE LIVE GAP IS STATED RATHER THAN HIDDEN: with `ui/ports.py`'s
    stub, the running app cannot produce this variant. The screen is
    proven ready for it; ST-22 is what makes it appear."""
    build, workspace, _ = sanad
    asked = "Est-ce que la duree peut etre prolongee ?"
    client, runtime = build(clarify=lambda question, summary: asked)

    _ask(client, "Et pour la duree ?")
    page = _settled(client, runtime, workspace.id)

    assert "bubble--clarification" in page
    assert asked in _visible(page)
    assert page.count("bubble--clarification") == 1


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
    client, runtime = build()
    _hold(runtime, gate, "grade")

    client.post("/chat/ask", data={"question": QUESTION}, follow_redirects=False)
    assert gate.reached.wait(WAIT), "the run never reached the grader"
    client.post("/chat/cancel", follow_redirects=False)
    gate.release.set()
    page = _settled(client, runtime, workspace.id)

    assert "msg--interrupted" in page
    assert "Incomplete" in page
    assert "msg--answer" not in page
    assert WRITTEN_ANSWER not in _visible(page)


# --- F-09, criteria 2 and 3 ------------------------------------------


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


def test_an_unflagged_workspace_shows_no_disclaimer_anywhere(sanad):
    """Criterion 3. The control half of the test above: without it,
    "the line appears" is equally true of a screen that always shows it."""
    build, workspace, _ = sanad
    client, runtime = build()

    _ask(client)
    page = _settled(client, runtime, workspace.id)

    assert "msg--answer" in page, "there must be an answer for it to be absent from"
    assert 'class="disclaimer"' not in page


# --- new conversation (UX spec 6.2) ----------------------------------


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


def test_the_lifespan_really_opens_the_one_qdrant_client(tmp_path, monkeypatch):
    """The ADR-04 line no test had ever executed.

    Every other test in this file passes a `ports_factory`, which takes
    the lifespan's early return, so `vector_store.open_store()` -- the one
    place the process's single Qdrant client is opened and closed -- was
    covered by nothing. A cold review pointed at it, and this project's
    own law is that a line which has never run is untested, not passing.

    It DID run live, twice, when the server was driven by hand; that is
    evidence, not a check. This is the check."""
    settings = get_settings().model_copy(
        update={"qdrant_storage_path": str(tmp_path / "qdrant")}
    )
    monkeypatch.setattr(vector_store, "get_settings", lambda: settings)
    runtime = Runtime(db_path=tmp_path / "sanad.db")

    assert runtime.client is None
    with TestClient(create_app(runtime)) as client:
        client.get("/")
        assert runtime.client is not None, "the lifespan must open the store"
    assert runtime.client is None, "and close it again on shutdown"


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


def test_the_legal_marker_rides_with_the_workspace_selector(sanad):
    """UX spec 4: the selector shows the name and, when the legal flag is
    set, a small persistent marker -- as TEXT, since no status in this
    interface may be carried by colour alone (criterion 10)."""
    build, workspace, _ = sanad
    client, _runtime = build(legal_flag=True)

    page = client.get("/").text

    assert 'class="marker"' in page
    assert ">Legal<" in page
