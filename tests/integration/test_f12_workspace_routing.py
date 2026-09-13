"""F-12: with no workspace selected, Sanad proposes one and asks first.

PRD acceptance criterion (verbatim): "Given no workspace is selected, when
the user asks a clearly technical question, then the system proposes the
workspace it judges most relevant and asks for confirmation before
answering."

WHAT IS REAL HERE, same choice `test_s1_chat_screen.py` makes: the FastAPI
app, the Jinja templates, an embedded Qdrant under `tmp_path`, real
chunking and real hybrid search across THREE separate workspaces. WHAT IS
FAKED: the two encoders (`tests/fake_encoders.py`, bag-of-words, so a
question's match is deterministic) and the chat model
(`tests.fake_chat.ScriptedChat`) -- and the chat model's call count is
exactly how "no answer was generated before confirmation" is proven,
because a graph-level assertion cannot see that from the outside.
"""

from __future__ import annotations

import threading

import pytest
from fastapi.testclient import TestClient

import app as app_module
import chunking
import embeddings
import parent_store
import vector_store
import workspaces
from agent.ports import AgentPorts
from app import Runtime, create_app
from config import get_settings
from db import repo
from tests.fake_chat import ScriptedChat
from tests.fake_encoders import install as install_fake_encoders
from ui.ports import build_ports

WAIT = 10

# Three distinct vocabularies, none sharing content words, so the fake
# bag-of-words dense encoder can tell them apart. Long enough (repeated)
# to clear `chunk_child_size_chars` (500) and produce at least one child.
_HR_TEXT = (
    "Les conges payes annuels des salaries sont fixes par accord collectif. "
    "Chaque salarie beneficie de jours de repos hebdomadaire et de jours "
    "feries chomes payes selon l'anciennete dans l'entreprise. "
) * 4
_PYTHON_TEXT = (
    "En python, une boucle for permet d'iterer sur une liste ou une "
    "sequence. La fonction range genere des nombres, et une variable "
    "stocke une valeur que la boucle peut modifier a chaque iteration. "
) * 4
_PRINTER_TEXT = (
    "L'imprimante laser reclame un remplacement de cartouche tous les "
    "deux mille pages environ. Le bac a papier accepte le format A4 et "
    "il faut verifier le niveau d'encre avant une longue impression. "
) * 4

QUESTION_PYTHON = "Comment fonctionne une boucle for en python ?"
WRITTEN_ANSWER = "Une boucle for en python repete un bloc pour chaque element."
QUERY_PLAN = '{"clarification":null,"queries":["boucle for python iteration"]}'


def _index(client, workspace_id: str, text: str, source_file: str, parents_dir) -> None:
    """Chunk, save parents, and upsert children for one workspace -- the
    same three calls `test_s1_chat_screen.py`'s `sanad` fixture makes,
    pulled out because this file repeats them three times."""
    result = chunking.chunk_document(text, source_file=source_file)
    parent_store.save_parents(
        parents=result.parents, workspace_id=workspace_id, base_path=parents_dir
    )
    vector_store.upsert_children(
        client,
        workspace_id=workspace_id,
        children=result.children,
        dense_vectors=embeddings.embed_passages([c.text for c in result.children]),
    )


@pytest.fixture
def three_workspaces(tmp_path, monkeypatch):
    """Three real, indexed workspaces behind a real app.

    ORDER MATTERS AND IS DELIBERATE: "Zebra HR" is created FIRST and comes
    LAST alphabetically; "Manuals" (the one a Python question should
    match) is created SECOND; "Apple Support" is created THIRD and comes
    FIRST alphabetically. A routing rule that secretly picked "the first
    created" or "the alphabetically first" workspace would propose the
    wrong one for every test below, rather than passing by accident."""
    install_fake_encoders(monkeypatch)
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    parents_dir = tmp_path / "parents"

    hr = workspaces.create_workspace(
        name="Zebra HR", folder_path=str(tmp_path / "hr"), db_path=db_path
    )
    manuals = workspaces.create_workspace(
        name="Manuals", folder_path=str(tmp_path / "manuals"), db_path=db_path
    )
    apple = workspaces.create_workspace(
        name="Apple Support", folder_path=str(tmp_path / "apple"), db_path=db_path
    )

    with vector_store.open_store(tmp_path / "qdrant") as client:
        _index(client, hr.id, _HR_TEXT, "conges.pdf", parents_dir)
        _index(client, manuals.id, _PYTHON_TEXT, "python-guide.pdf", parents_dir)
        _index(client, apple.id, _PRINTER_TEXT, "imprimante.pdf", parents_dir)

        def build(model=None, **overrides):
            def ports() -> AgentPorts:
                import dataclasses

                base = build_ports(
                    client,
                    model or ScriptedChat(QUERY_PLAN, "RELEVANT", WRITTEN_ANSWER),
                    parents_path=parents_dir,
                )
                return dataclasses.replace(base, **overrides)

            # `client=client` (not just `ports_factory`) is what F-12
            # routing needs: `Runtime.routing_client` goes through
            # `Runtime.store()`, never `ports_factory` (routing has no
            # chat model), and `store()` only reuses THIS test's embedded
            # Qdrant instead of opening the real configured path when
            # `Runtime.client` is set -- the same seam
            # `test_evidence_only_mode.py` uses for the same reason.
            runtime = Runtime(ports_factory=ports, db_path=db_path, client=client)
            return TestClient(create_app(runtime)), runtime

        yield build, {"hr": hr, "manuals": manuals, "apple": apple}, db_path


def _choose_routing(client) -> None:
    """Select "let Sanad choose" on the shell selector, the way a real
    browser posting the new `<option>` would."""
    resp = client.post(
        "/workspace", data={"workspace_id": "__route__"}, follow_redirects=False
    )
    assert resp.status_code == 303


# --- the selector option itself ----------------------------------------


def test_the_no_selection_option_is_absent_with_a_single_workspace(tmp_path, monkeypatch):
    install_fake_encoders(monkeypatch)
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    workspaces.create_workspace(name="Solo", folder_path=str(tmp_path / "solo"), db_path=db_path)
    client = TestClient(create_app(Runtime(ports_factory=lambda: None, db_path=db_path)))

    page = client.get("/").text

    assert "Let Sanad choose" not in page


def test_the_no_selection_option_is_offered_with_two_or_more_workspaces(three_workspaces):
    build, _ws, _db = three_workspaces
    client, _runtime = build()

    page = client.get("/").text

    assert "Let Sanad choose" in page
    assert 'value="__route__"' in page


# --- the proposal itself: not first-created, not alphabetically-first --


def test_routing_proposes_the_matching_workspace_not_the_first_or_alphabetical(
    three_workspaces,
):
    build, ws, _db = three_workspaces
    client, _runtime = build()
    _choose_routing(client)

    page = client.post(
        "/chat/ask", data={"question": QUESTION_PYTHON}, follow_redirects=True
    ).text

    assert "This looks like a question for Manuals" in page
    # The proposal names Manuals as the PRIMARY suggestion; the other two
    # workspaces, if present at all, are secondary candidates further down
    # -- never the lead sentence.
    lead_sentence = page.split("This looks like a question for ")[1].split("?")[0]
    assert lead_sentence.startswith("Manuals")


def test_no_answer_is_generated_before_confirmation(three_workspaces):
    """The model must not be called at all while a proposal is pending --
    routing is local search, never an LLM call, and the graph must not
    have run yet either way."""
    build, ws, _db = three_workspaces
    model = ScriptedChat(QUERY_PLAN, "RELEVANT", WRITTEN_ANSWER)
    client, _runtime = build(model)
    _choose_routing(client)

    client.post("/chat/ask", data={"question": QUESTION_PYTHON}, follow_redirects=True)

    assert model.calls == [], "no model call may happen before the operator confirms"


def test_an_over_long_question_is_refused_before_any_proposal(three_workspaces, monkeypatch):
    """The graph enforces `question_max_length` when a run starts, but
    routing never starts one: without its own check an over-long question
    was proposed a workspace and failed only after confirmation. It must be
    refused up front, with no proposal and no embedding call."""
    build, _ws, _db = three_workspaces
    client, _runtime = build()
    _choose_routing(client)
    embedded: list[str] = []
    real_embed = embeddings.embed_query
    monkeypatch.setattr(
        embeddings, "embed_query", lambda text: embedded.append(text) or real_embed(text)
    )
    too_long = "boucle " * (get_settings().question_max_length // 7 + 10)

    page = client.post("/chat/ask", data={"question": too_long}, follow_redirects=True).text

    assert "This looks like a question for" not in page
    assert "a question may be at most" in page
    assert embedded == [], "an over-long question must not be embedded for routing"


def test_proposal_buttons_isolate_each_workspace_name(three_workspaces):
    """F-14 x F-12: a workspace name may be Arabic inside an English button
    label, so each one is wrapped in <bdi> to keep its own direction."""
    build, _ws, _db = three_workspaces
    client, _runtime = build()
    _choose_routing(client)

    page = client.post(
        "/chat/ask", data={"question": QUESTION_PYTHON}, follow_redirects=True
    ).text

    assert "Yes, use <bdi>Manuals</bdi>" in page


def test_confirming_answers_from_the_proposed_workspace_and_selects_it(three_workspaces):
    build, ws, _db = three_workspaces
    client, runtime = build()
    _choose_routing(client)
    client.post("/chat/ask", data={"question": QUESTION_PYTHON}, follow_redirects=True)

    confirm = client.post(
        "/chat/ask",
        data={"question": QUESTION_PYTHON, "workspace_id": ws["manuals"].id},
        follow_redirects=False,
    )
    assert confirm.status_code == 303

    conversation = runtime.conversation(ws["manuals"].id)
    for _ in range(WAIT * 100):
        if not conversation.busy:
            break
        threading.Event().wait(0.01)
    assert not conversation.busy, "the run never finished"

    page = client.get("/").text
    assert WRITTEN_ANSWER in page
    assert "Answering from" in page and "Manuals" in page.split("Answering from")[1]


def test_a_secondary_candidate_button_answers_from_that_workspace_instead(three_workspaces):
    """Design: the confirmation offers the other candidates too, ranked,
    as secondary buttons. Confirming a SECONDARY one must still work and
    must select THAT workspace, not the primary one."""
    build, ws, _db = three_workspaces
    client, runtime = build()
    _choose_routing(client)
    page = client.post(
        "/chat/ask", data={"question": QUESTION_PYTHON}, follow_redirects=True
    ).text
    # Every synced workspace has SOME hit for any question with this fake
    # encoder (bag-of-words never returns a literal zero unless there is no
    # word overlap at all), so all three should appear as candidates.
    assert "Zebra HR" in page or "Apple Support" in page, (
        "expected at least one secondary candidate in the proposal"
    )
    secondary_id = ws["hr"].id if "Zebra HR" in page else ws["apple"].id

    client.post(
        "/chat/ask",
        data={"question": QUESTION_PYTHON, "workspace_id": secondary_id},
        follow_redirects=False,
    )
    conversation = runtime.conversation(secondary_id)
    for _ in range(WAIT * 100):
        if not conversation.busy:
            break
        threading.Event().wait(0.01)

    settled_page = client.get("/").text
    assert "Answering from" in settled_page
    grounding = settled_page.split("Answering from")[1]
    expected_name = "Zebra HR" if secondary_id == ws["hr"].id else "Apple Support"
    assert expected_name in grounding


# --- no hit at all: say so, never guess ---------------------------------


def test_no_hit_shows_a_plain_message_and_never_guesses(tmp_path, monkeypatch):
    """Two workspaces exist so routing is even offered, but NEITHER has a
    synced collection with anything in it: one was never synced at all,
    the other was synced with zero documents (an empty collection).
    `vector_store.search` already proves an empty collection returns no
    hits rather than raising (`test_an_empty_collection_returns_no_hits_
    rather_than_raising`), so this is the natural "nothing matched" case,
    with no threshold invented to manufacture it."""
    install_fake_encoders(monkeypatch)
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    never_synced = workspaces.create_workspace(
        name="Never Synced", folder_path=str(tmp_path / "a"), db_path=db_path
    )
    empty = workspaces.create_workspace(
        name="Empty", folder_path=str(tmp_path / "b"), db_path=db_path
    )

    with vector_store.open_store(tmp_path / "qdrant") as client:
        vector_store.ensure_collection(client, workspace_id=empty.id)

        def ports() -> AgentPorts:
            raise AssertionError("no model call is expected on this path")

        runtime = Runtime(ports_factory=ports, db_path=db_path)
        client_app = TestClient(create_app(runtime))
        client_app.post("/workspace", data={"workspace_id": "__route__"})

        page = client_app.post(
            "/chat/ask", data={"question": "n'importe quoi"}, follow_redirects=True
        ).text

    assert "None of your workspaces look like a match" in page
    assert "Pick one from the selector" in page
    assert "This looks like a question for" not in page, (
        "a no-hit question must never dress up as a proposal"
    )
    del never_synced  # named only to document the fixture's shape


# --- evidence-only: same refusal path, model never loads ----------------


def _set_evidence_only(monkeypatch, value: bool) -> None:
    settings = get_settings().model_copy(update={"evidence_only": value})
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)


def test_evidence_only_refuses_routing_with_the_same_sentence_and_never_loads_the_model(
    three_workspaces, monkeypatch
):
    build, _ws, _db = three_workspaces
    client, _runtime = build()
    _choose_routing(client)

    def _must_not_load(*_a, **_k):
        raise AssertionError("the embedding model must not load in evidence-only mode")

    monkeypatch.setattr(embeddings, "embed_query", _must_not_load)
    monkeypatch.setattr(embeddings, "embed_sparse_query", _must_not_load)
    _set_evidence_only(monkeypatch, True)

    page = client.post(
        "/chat/ask", data={"question": QUESTION_PYTHON}, follow_redirects=True
    ).text

    assert "read-only" in page
    assert "cannot answer questions or run a Sync" in page


def test_evidence_only_control_probe_routing_works_with_the_flag_off(three_workspaces, monkeypatch):
    """Prove the FLAG is what stops routing, not something else -- the
    same control-probe shape `test_evidence_only_mode.py` uses for Sync
    and Chat."""
    build, ws, _db = three_workspaces
    client, _runtime = build()
    _choose_routing(client)
    _set_evidence_only(monkeypatch, False)

    page = client.post(
        "/chat/ask", data={"question": QUESTION_PYTHON}, follow_redirects=True
    ).text

    assert "This looks like a question for Manuals" in page


# --- no leaking passages across workspaces -------------------------------


def test_the_confirmation_contains_no_passage_text_from_any_workspace(three_workspaces):
    build, ws, _db = three_workspaces
    client, _runtime = build()
    _choose_routing(client)

    page = client.post(
        "/chat/ask", data={"question": QUESTION_PYTHON}, follow_redirects=True
    ).text

    # Distinctive substrings from each document's actual TEXT (not its
    # workspace name) must never reach the confirmation bubble.
    for leak in ("boucle for permet", "conges payes annuels", "cartouche tous les"):
        assert leak not in page, f"a passage leaked into the routing confirmation: {leak!r}"
