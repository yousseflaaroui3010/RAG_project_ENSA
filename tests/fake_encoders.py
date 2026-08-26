"""Deterministic stand-ins for the two ST-15 encoders, shared by tests.

Not a test file: pytest does not collect it. It exists because the real
encoders download hundreds of megabytes, and no test that is about
retrieval, grading or sync is about the encoders themselves.

WHY THESE FAKES RANK RATHER THAN RANDOMISE. A random vector would let a
search "work" while returning nothing a reader would expect, so any test
asserting WHICH chunk came back first would be asserting on noise. These
are bag-of-words: two texts sharing words come back close together, and
unit length, because `vector_store` builds its collection with cosine
distance.

AND WHY THE SPARSE FAKE IS ASYMMETRIC. The real fastembed BM25 weights
terms on the document side and returns flat indicators on the query side,
and using the wrong one raises nothing at all -- ST-16 found that by
running it. A symmetric fake would let a whole test file pass while the
code under it fed query vectors into the index, which is the exact defect
`embeddings.py`'s encoder seam exists to prevent.

FOURTH COPY, DELIBERATELY NOT MIGRATED YET. This logic already exists
three times, in `tests/unit/test_vector_store.py`, `test_embeddings.py`
and `test_sync.py`. The core law says the third copy earns an abstraction
or a written reason -- this module is the abstraction, and ST-23 uses it
rather than pasting a fourth. Rewriting the three existing files to import
it would put unrelated churn in a story diff a reviewer is grading against
one exit gate (the scoped boy-scout rule), so it is its own `chore/`
branch. Recorded in BUILD-STATE so it is a task, not a smell nobody named.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import embeddings
from config import get_settings

SPARSE_VOCABULARY = 10_000


@dataclass(frozen=True)
class _RawSparse:
    """The shape fastembed returns: parallel index and value arrays."""

    indices: list[int]
    values: list[float]


def words(text: str) -> list[str]:
    """Lower-cased word bag, with the E5 instruction prefixes removed.

    The prefixes are stripped for the reason the real model does not treat
    them as content: they say how to read the text, they are not part of
    it. Leaving them in puts a token in every passage that no query can
    match, which is noise in a fixture rather than realism."""
    for prefix in (
        get_settings().embedding_passage_prefix,
        get_settings().embedding_query_prefix,
    ):
        if text.startswith(prefix):
            text = text[len(prefix) :]
    return [w for w in text.lower().replace("'", " ").split() if w]


def slot(word: str, modulo: int) -> int:
    return int(hashlib.sha256(word.encode("utf-8")).hexdigest(), 16) % modulo


def fake_dense(prefixed_texts):
    """A deterministic bag-of-words embedding of the configured width."""
    dim = get_settings().embedding_dense_dim
    vectors = []
    for text in prefixed_texts:
        vector = [0.0] * dim
        for word in words(text):
            vector[slot(word, dim)] += 1.0
        length = sum(x * x for x in vector) ** 0.5 or 1.0
        vectors.append([x / length for x in vector])
    return vectors


class FakeSparseModel:
    """BM25-shaped, and asymmetric in the same direction as the real one."""

    def embed(self, documents, **_kwargs):
        return [_RawSparse(*self._terms(text, weight=1.75)) for text in documents]

    def query_embed(self, query, **_kwargs):
        return iter([_RawSparse(*self._terms(query, weight=1.0))])

    @staticmethod
    def _terms(text, weight):
        slots = sorted({slot(word, SPARSE_VOCABULARY) for word in words(text)})
        return slots, [weight] * len(slots)


def install(monkeypatch) -> None:
    """Point `embeddings` at the fakes for one test."""
    monkeypatch.setattr(embeddings, "_encode", fake_dense)
    monkeypatch.setattr(embeddings, "_load_sparse_model", lambda _n: FakeSparseModel())
