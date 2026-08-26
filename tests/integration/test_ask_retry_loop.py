"""ST-23 exit gate, end to end: "retry count never exceeds config; an
off-topic fixture triggers exactly one reword".

Reference: PRD F-04, architecture 5.2, BUILD-PLAN line 77.

WHY THIS FILE EXISTS WHEN ST-21 ALREADY TESTED THE CEILING. ST-21 proved
the ROUTER obeys `retry_ceiling`, with fake ports. It could not prove
anything about the real ones, and from the router's side a port that
retries internally is invisible: one model call and three model calls look
identical to a graph that asked once. So the tests here count MODEL CALLS
and SEARCHES, not routing decisions.

Everything below the agent is real: a real embedded Qdrant under
`tmp_path`, real `vector_store` writes and hybrid searches, real parent
JSON on disk, and the real `retrieve` / `grade` / `reword` ports. Two
things are faked, both for reasons the project has already written down:
the two ENCODERS, because they download hundreds of megabytes and are not
what this file is about (`tests/fake_encoders.py`), and the CHAT MODEL,
because docs/phase2/CLAUDE.md's hard rule is that tests use a scripted
fake and carry no API keys. The five ports ST-22, ST-24 and ST-25 own are
stubbed here, in the open.

WHAT THIS FILE THEREFORE DOES NOT PROVE, stated plainly rather than left
for a reader to assume: that a real language model grades French legal
passages correctly. Nothing on this machine can prove that -- there is no
cloud key and no Ollama (see the blocker in BUILD-STATE). What it proves
is that the loop, the ceiling, the reworded query and the isolation are
right, given a model that answers.
"""

from __future__ import annotations

import pytest

import agent.nodes
import chunking
import embeddings
import parent_store
import vector_store
from agent.graph import ask
from agent.ports import AgentPorts
from agent.retrieval import build_retrieve
from agent.state import AnswerKind
from config import get_settings
from tests.fake_encoders import install as install_fake_encoders

WS_HR = "11111111-1111-1111-1111-111111111111"
WS_MANUALS = "22222222-2222-2222-2222-222222222222"

# The two corpora SHARE vocabulary on purpose -- "mois", "trois", "jours"
# -- so a workspace leak would score highly rather than merely appear.
# A fixture whose two halves have nothing in common cannot fail an
# isolation test even when isolation is broken.
HR_DOCUMENT = """# Article 13 : Periode d'essai

La periode d'essai est de trois mois pour les cadres, renouvelable une
seule fois. Elle est de un mois et demi pour les employes et de quinze
jours pour les ouvriers. Pendant cette periode, chacune des parties peut
rompre le contrat sans preavis et sans indemnite. Toutefois, apres au
moins une semaine de travail, la rupture du contrat non motivee par la
faute grave du salarie ne peut avoir lieu qu'en donnant un delai de
preavis de deux jours avant la rupture si le salarie est paye a la
journee, a la semaine ou a la quinzaine, et de huit jours si le salarie
est paye au mois. La periode d'essai peut etre renouvelee une seule fois
et son renouvellement doit etre notifie par ecrit au salarie avant le
terme de la periode initiale.

# Article 43 : Preavis de licenciement

Le delai de preavis est d'un mois pour les employes ayant moins de cinq
ans d'anciennete, et de trois mois au-dela. Pendant le delai de preavis,
le salarie a droit a des permissions d'absence remunerees pour chercher
un autre emploi, a raison de deux heures par jour sans que ces absences
puissent depasser huit heures dans une meme semaine ou trente heures
dans une periode de trente jours consecutifs. L'employeur qui n'observe
pas le delai de preavis doit verser au salarie une indemnite egale a la
remuneration qu'aurait percue le salarie s'il etait demeure a son poste.

# Article 52 : Indemnite de licenciement

Le salarie lie par un contrat de travail a duree indeterminee a droit a
une indemnite de licenciement apres six mois de travail continu dans la
meme entreprise, quel que soit le mode de remuneration et la periodicite
du paiement du salaire. Le montant de l'indemnite pour chaque annee ou
fraction d'annee de travail effectif est egal a quatre-vingt-seize
heures de salaire pour les cinq premieres annees d'anciennete.
"""

MANUALS_DOCUMENT = """# Entretien de la pompe

Vidanger le circuit tous les trois mois. Remplacer le joint tous les
quinze jours en usage intensif.

# Calibrage du capteur

Le capteur se recalibre en un mois de service continu.
"""


class _FakeChat:
    """The scripted fake chat model, counting every call it receives."""

    def __init__(self, *replies: str):
        self.replies = list(replies)
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self.replies[min(len(self.calls) - 1, len(self.replies) - 1)]


def _index(client, workspace_id: str, markdown: str, source_file: str, base_path):
    """Chunk, store parents, embed and upsert -- the real pipeline.

    The dense vectors are passed in and the sparse ones are not, which is
    `upsert_children`'s own design: the document-side sparse encoding has
    exactly one route into the store, so a caller cannot hand it a
    query-side vector by mistake."""
    result = chunking.chunk_document(markdown, source_file=source_file)
    parent_store.save_parents(
        parents=result.parents, workspace_id=workspace_id, base_path=base_path
    )
    vector_store.upsert_children(
        client,
        workspace_id=workspace_id,
        children=result.children,
        dense_vectors=embeddings.embed_passages([c.text for c in result.children]),
    )
    return result


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    """Two real workspaces in one real embedded Qdrant.

    The HR document is deliberately long enough to produce SEVERAL child
    chunks, and the assertion below keeps it that way. That is not
    padding: with a single child in the collection, a search depth of 1
    and a search depth of 3 both return one hit, so the test that proves
    the operator's setting governs would pass while proving nothing. This
    project has shipped that exact defect twice (ST-14 and ST-16, both
    recorded in BUILD-STATE as "the fixture was too small for the
    property"), and it shipped here too until a run caught it."""
    install_fake_encoders(monkeypatch)
    parents = tmp_path / "parents"
    with vector_store.open_store(tmp_path / "qdrant") as client:
        hr = _index(client, WS_HR, HR_DOCUMENT, "code-du-travail.pdf", parents)
        _index(client, WS_MANUALS, MANUALS_DOCUMENT, "manuel-pompe.txt", parents)
        assert len(hr.children) >= 3, (
            "the HR fixture must produce at least 3 child chunks, or the "
            "search-depth test cannot tell one depth from another"
        )
        yield client, parents


def _ports(client, parents, model, **overrides) -> AgentPorts:
    """The three real ST-23 ports; the other five stubbed in the open."""
    import dataclasses

    from agent.grading import build_grade, build_reword
    from agent.stores import parent_texts

    base = AgentPorts(
        # ST-25's, stubbed: no session memory in this story.
        summarize=lambda history: "",
        # ST-22's, stubbed: never ambiguous here.
        clarify=lambda question, summary: None,
        rewrite=lambda question, summary: (question,),
        # --- the three ST-23 owns, all real ---
        retrieve=build_retrieve(client),
        grade=build_grade(model),
        reword=build_reword(model),
        # ST-24's, stubbed, but reading the real parent text it was given.
        fetch_parents=lambda ws, ids: parent_texts(ws, ids, base_path=parents),
        write_answer=lambda q, passages, parent_map: (
            f"D'apres {len(parent_map)} section(s): {next(iter(parent_map.values()))[:60]}"
        ),
    )
    return dataclasses.replace(base, **overrides)


def _with_ceiling(monkeypatch, ceiling: int):
    settings = get_settings().model_copy(update={"retry_ceiling": ceiling})
    monkeypatch.setattr(agent.nodes, "get_settings", lambda: settings)
    return settings


# --- the exit gate ----------------------------------------------------


def test_an_off_topic_first_search_triggers_exactly_one_reword(corpus, monkeypatch):
    """The gate's second half, on real retrieval.

    The grader says OFF_TOPIC once and RELEVANT after, so the loop must
    reword ONCE and answer. Three assertions, and the third is the one
    with teeth: the second search must carry the REWORDED text. A loop
    that reworded and then searched the original string again would still
    report one retry, still answer, and be quietly useless."""
    client, parents = corpus
    _with_ceiling(monkeypatch, 2)
    model = _FakeChat("OFF_TOPIC", "duree essai cadres", "RELEVANT")

    answer = ask(
        workspace_id=WS_HR,
        question="Combien de temps dure la periode d'essai ?",
        ports=_ports(client, parents, model),
    )

    assert answer.kind is AnswerKind.ANSWER
    assert answer.retries == 1
    assert answer.searched == (
        "Combien de temps dure la periode d'essai ?",
        "duree essai cadres",
    )


@pytest.mark.parametrize("ceiling", [0, 1, 3])
def test_the_model_is_asked_to_grade_exactly_ceiling_plus_one_times(
    corpus, monkeypatch, ceiling
):
    """The gate's first half, counted where ST-21 structurally could not
    count it: at the model.

    ST-21 proved the router stops at the ceiling. It could not see a retry
    hidden INSIDE an adapter -- from the graph's side, one model call and
    three look the same. Counting calls is what catches that.

    Grading calls are `ceiling + 1`; rewording calls are `ceiling`. Run at
    0, 1 and 3 so a hardcoded default of 2 has nowhere to hide."""
    client, parents = corpus
    _with_ceiling(monkeypatch, ceiling)
    # Always off-topic, and every reword returns a usable new query.
    # The model is asked to grade, then to reword, then to grade again,
    # and so on. Scripting the alternation explicitly keeps the fake
    # honest: a fake that answered "OFF_TOPIC" to a reword request would
    # feed the literal string "OFF_TOPIC" back in as a search query.
    replies = ["OFF_TOPIC"]
    for _ in range(ceiling):
        replies += ["essai reformule", "OFF_TOPIC"]
    model = _FakeChat(*replies)

    answer = ask(
        workspace_id=WS_HR,
        question="Comment cuisiner un tajine ?",
        ports=_ports(client, parents, model),
    )

    assert answer.kind is AnswerKind.REFUSAL
    assert answer.retries == ceiling
    assert len(answer.searched) == ceiling + 1
    grading_calls = sum(1 for _s, user in model.calls if "RELEVANT or OFF_TOPIC" in user)
    assert grading_calls == ceiling + 1


def test_the_grader_is_shown_the_passages_the_store_actually_returned(corpus, monkeypatch):
    """The seam between real retrieval and the grader, which no unit test
    covers: the text the grader judges must be text that came out of
    Qdrant, not a placeholder."""
    client, parents = corpus
    _with_ceiling(monkeypatch, 0)
    model = _FakeChat("RELEVANT")

    ask(
        workspace_id=WS_HR,
        question="periode d'essai cadres",
        ports=_ports(client, parents, model),
    )

    _system, user = model.calls[0]
    assert "periode d'essai" in user.lower()
    assert "code-du-travail.pdf" in user


def test_the_answer_is_written_from_the_real_parent_sections(corpus, monkeypatch):
    """Box P against the real store: the section handed to the answer
    writer is the full article, longer than the 500-character child that
    matched."""
    client, parents = corpus
    _with_ceiling(monkeypatch, 0)
    seen: dict = {}

    def capture(question, passages, parent_map):
        seen.update(parent_map)
        return "reponse"

    answer = ask(
        workspace_id=WS_HR,
        question="periode d'essai",
        ports=_ports(client, parents, _FakeChat("RELEVANT"), write_answer=capture),
    )

    assert answer.kind is AnswerKind.ANSWER
    assert seen, "no parent section reached the answer writer"
    assert any("renouvelable" in text for text in seen.values())


def test_an_hr_question_never_reaches_the_manuals_workspace(corpus, monkeypatch):
    """PRD F-01, through the whole agent rather than at the store.

    Both corpora talk about "trois mois" and "quinze jours", so a leak
    would rank highly rather than merely appear. Asserted on the file
    names in the trace, which is what a user would see cited."""
    client, parents = corpus
    _with_ceiling(monkeypatch, 0)

    answer = ask(
        workspace_id=WS_HR,
        question="trois mois quinze jours",
        ports=_ports(client, parents, _FakeChat("RELEVANT")),
    )

    assert answer.trace.files_consulted == ("code-du-travail.pdf",)
    assert all(source.file_name == "code-du-travail.pdf" for source in answer.sources)


def test_the_operator_s_search_depth_is_what_governs_the_hit_count(corpus, monkeypatch):
    """`retrieval_depth_k` reaches the real search, proven by changing it.

    The retrieve port deliberately passes no limit, letting
    `vector_store.search` resolve the setting -- so this is the test that
    shows the setting still governs. Two values, because one proves
    nothing: a hardcoded number would match one of them by luck."""
    client, parents = corpus
    counts = []

    for depth in (1, 3):
        settings = get_settings().model_copy(
            update={"retry_ceiling": 0, "retrieval_depth_k": depth}
        )
        monkeypatch.setattr(agent.nodes, "get_settings", lambda s=settings: s)
        monkeypatch.setattr(vector_store, "get_settings", lambda s=settings: s)
        captured: list = []

        def capture(question, passages, parent_map, sink=captured):
            sink.append(len(passages))
            return "reponse"

        ask(
            workspace_id=WS_HR,
            question="periode d'essai preavis",
            ports=_ports(client, parents, _FakeChat("RELEVANT"), write_answer=capture),
        )
        counts.append(captured[0])

    assert counts == [1, 3]


def test_a_workspace_that_was_never_synced_says_so_rather_than_refusing(
    corpus, monkeypatch
):
    """"Never synced" and "your documents do not cover this" are different
    facts with different next steps. The store's error carries the right
    sentence and must reach the caller intact."""
    client, parents = corpus
    _with_ceiling(monkeypatch, 0)

    with pytest.raises(vector_store.CollectionNotFoundError, match="Sync"):
        ask(
            workspace_id="33333333-3333-3333-3333-333333333333",
            question="periode d'essai",
            ports=_ports(client, parents, _FakeChat("RELEVANT")),
        )
