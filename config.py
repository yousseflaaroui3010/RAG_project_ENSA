"""Sanad configuration: the single source of truth for every tunable.

Hard technical rule (docs/phase2/CLAUDE.md): all tunables live in
config.py and .env (documented in .env.example). No magic literals in
module code -- import Settings/get_settings() instead of hardcoding a
value a second time.

Reads from a .env file via pydantic-settings (architecture §8, §12.1).
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Model provider selection (ADR-06: provider-agnostic, two modes) ---
    # "cloud" uses Google Gemini (free tier); "strict_local" runs a free local
    # model (Mistral, Llama, ...) through Ollama, the offline demo fallback
    # (LD-06 locality). One config point, no code branch elsewhere; swap the
    # provider by changing these values, never by editing module code.
    model_mode: str = "cloud"
    # Cloud: any Gemini model available on the free tier (Google AI Studio).
    #
    # A PINNED MODEL NAME ROTS, and this one did. The default here was
    # `gemini-2.0-flash` from 2026-07-20 until 2026-08-27, when the first
    # real call ever made from this project came back
    # `404 NOT_FOUND: This model models/gemini-2.0-flash is no longer
    # available`. Nothing in the repo could have caught that: it was a
    # correct value when it was written, no test invokes a real provider
    # (docs/phase2/CLAUDE.md forbids keys in tests, rightly), and a dead
    # model name is invisible to ruff, to pytest and to the typechecker.
    # The only check that finds it is a live call. Re-verify this value
    # whenever an agent story is picked up, not from memory.
    #
    # Pinned to a specific stable version rather than the moving
    # `gemini-flash-latest` alias: the evaluation gate (G1-G3) compares
    # scores across releases, and a model that changes underneath a
    # threshold makes those numbers meaningless.
    #
    # WHY THIS ONE. It is the successor Google's own 404 names: "Please
    # update your code to use models/gemini-3.6-flash". Following the
    # vendor's stated migration path beats picking by taste, and the
    # value was then verified by a live call rather than trusted. The
    # account also offers 2.5-flash, 3.5-flash, 3.7-flash and lite
    # variants, all free tier; 2.5 and 3.5 were both confirmed working
    # too, so there is a fallback if this one is retired next.
    #
    # Which model FINALLY ships is still not settled here: that belongs
    # to the golden-set evaluation (ST-32/ST-36), which compares them on
    # real questions with real numbers. ADR-06 exists precisely so that
    # choice stays one line in this file.
    chat_model_cloud: str = "gemini-3.6-flash"
    # Local: any Ollama-served instruct model >= 7B (ADR-06 floor).
    chat_model_local: str = "mistral"
    # Gemini / Google AI Studio API key; read in cloud mode only.
    cloud_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    # Per-call ceiling, both providers (PRD section 11: "answering service
    # unreachable -> clear error and a retry action"). Without this, one
    # stalled network call hangs a question indefinitely and Cancel has
    # nothing to cancel. Default 60 is the G4 p95 ceiling (ST-18/ST-36): a
    # call already past that budget is not going to produce an answer
    # worth waiting for.
    model_call_timeout_seconds: float = 60.0
    # How many RETRIES one failed cloud call gets after its first try. The
    # Gemini client counts total attempts (it builds HttpRetryOptions(
    # attempts=max_retries)), so agent/chat.py passes this + 1 -- verified
    # against the installed client with a silent socket (review of 7ebc552).
    # Worst case per call is therefore (retries + 1) x the timeout above, not
    # the timeout alone. Its own default (6 attempts) is too patient for an
    # interactive question. ChatOllama (langchain-ollama 1.1.0) has no retry
    # field, so this applies to cloud mode only.
    model_call_max_retries: int = 2

    # --- Embeddings (ADR-05) ---
    # Dense multilingual model; every embedded chunk MUST carry the
    # "passage: " prefix and every query the "query: " prefix (model card
    # requirement, unit-test enforced -- never delete or weaken that test).
    embedding_model: str = "intfloat/multilingual-e5-base"
    embedding_dense_dim: int = 768
    embedding_sparse_model: str = "Qdrant/bm25"
    embedding_passage_prefix: str = "passage: "
    embedding_query_prefix: str = "query: "

    # --- Agent behavior (F-03 to F-07) ---
    # Retry ceiling default 2, operator-configurable (F-04). Never hardcode
    # this in agent/nodes.py; read it from here.
    retry_ceiling: int = 2
    # Retrieval depth: number of child chunks pulled per hybrid search.
    retrieval_depth_k: int = 5
    # Mirrors docs/phase2/openapi.yaml AskRequest `question`
    # (minLength/maxLength). Checked in agent/graph.py's `ask`, because
    # ADR-13 has the UI calling the same service functions IN-PROCESS --
    # so the HTTP layer's validation is not in that path and a question
    # that never passes through a route is otherwise unchecked.
    question_min_length: int = 1
    question_max_length: int = 2000
    # Rolling session memory has two separate limits: what one consolidation
    # call may send, and what may survive for the next question. Raising either
    # increases every later model request in a long conversation.
    session_memory_input_max_chars: int = 16000
    session_summary_max_chars: int = 2000
    # How many sub-queries architecture 5.2's "rewrite and split" may
    # produce for one question. The retry ceiling bounds how many ROUNDS
    # run; this bounds how wide a round is, and without it a misbehaving
    # rewrite returning forty phrases costs (ceiling + 1) x 40 real model
    # and store calls for one question -- each one also disclosed back to
    # the user in an honest refusal (F-05). ST-22 owns the splitting and
    # may tune this; it is a guard rail, not a target.
    max_sub_queries: int = 5

    # --- Chunking (architecture §7.5) ---
    # Parents split on markdown headings H1-H3, merged below
    # parent_merge_below_chars, split above parent_split_above_chars.
    # Children are chunk_child_size_chars with chunk_child_overlap_chars
    # overlap, sized to stay well under the E5 512-token input ceiling.
    chunk_child_size_chars: int = 500
    chunk_child_overlap_chars: int = 100
    parent_merge_below_chars: int = 2000
    parent_split_above_chars: int = 4000
    # Regex for the unit a document is actually CITED by, used to label a
    # parent or child more precisely than its enclosing heading can.
    #
    # Architecture §7.5 fixes where parents are SPLIT (markdown headings
    # H1-H3) and names `section_label` as a field, but never says how the
    # label is computed -- so this refines the label without deviating
    # from the signed spec.
    #
    # It exists because heading-based labels are wrong on real legal text,
    # measured rather than assumed: the Moroccan labour code is 313,255
    # characters with 588 distinct "Article N" and only 22 markdown
    # headings, so splitting on headings gives many parents that all carry
    # one heading and a passage from Article 235 gets cited as
    # "Titre II : Definitions" (PRD F-03).
    #
    # CASE-SENSITIVE on purpose, and that is the whole trick: in the same
    # document, capital "Article 42" starts an article (588 of them, every
    # one distinct) while lowercase "l'article 26" is a cross-reference
    # (234 of them, only 163 distinct). Lower-casing the match would label
    # parents by the articles they merely MENTION.
    #
    # Set to "" to switch the behaviour off and fall back to headings
    # alone, which is the right setting for a corpus with no numbered
    # citable unit.
    #
    # "Slide N" is F-11's citable unit: conversion.py stamps a "Slide N"
    # line at the top of every slide's text, so a child cut from a deck
    # whose short slides merged into one parent is cited by ITS slide, not
    # by the parent's "Slide 1 ... Slide 20" range. Adding it changes no
    # existing citation: zero of the 187 stored parents and zero of the
    # manuals contained a capital "Slide" plus a number (checked
    # 2026-09-13), and the match stays case-sensitive like "Article".
    parent_citation_marker_pattern: str = r"Article\s+\d+|Slide\s+\d+"

    # --- Change detection (ST-12, PRD F-02, architecture §5.1) ---
    # File extensions Sync fingerprints and hands to the conversion ladder.
    # PRD F-02 scopes V1 to PDF, DOCX, TXT, MD; PPTX joined for V1.1's F-11
    # (ST-48), converted the same way DOCX is (ADR-07: markitdown), cited
    # by slide number (conversion.py's `_read_pptx`). Lower-case, no dot.
    supported_document_extensions: tuple[str, ...] = (
        "pdf",
        "docx",
        "txt",
        "md",
        "pptx",
    )
    # Bytes read per hashing iteration. Files are hashed incrementally so a
    # 500 MB PDF never lands in memory whole.
    hash_read_chunk_bytes: int = 1024 * 1024

    # --- Conversion ladder (ST-13, ADR-07, PRD F-02) ---
    # Minimum non-whitespace characters a converted document must yield
    # before Sync accepts it as having a readable text layer. Below this it
    # is reported Skipped, which is the binding V1 behaviour for a scanned
    # PDF (PRD F-16: "reported as Skipped with the reason stated").
    # Default 1 = "any real character at all", the strictly honest reading;
    # raise it only if scanner junk (stray page numbers on image-only pages)
    # starts passing as a text layer on a real corpus.
    conversion_min_text_chars: int = 1
    # Codec for the TXT / MD passthrough rung. "utf-8-sig" reads plain UTF-8
    # unchanged AND strips the byte-order mark Windows editors prepend, which
    # would otherwise become an invisible first character of the first
    # heading and break the chunker's heading match (architecture §7.5).
    # Decoding is strict on purpose: a file that is not this encoding is
    # reported Failed rather than silently mojibaked into the index.
    text_file_encoding: str = "utf-8-sig"

    # --- Store paths (architecture §7.5, LD-06 data locality) ---
    # All under data/, git-ignored, operator-controlled disk.
    qdrant_storage_path: str = "data/qdrant/"
    parent_store_path: str = "data/parents/"
    sqlite_db_path: str = "data/sanad.db"
    reports_path: str = "data/reports/"
    # Seconds a connection waits for a writer lock before raising
    # "database is locked". SQLite's own default is 5.0, which is too short
    # once ST-17's sync writes while the UI reads on another connection.
    sqlite_busy_timeout_seconds: float = 30.0

    # --- Evaluation (ST-32, F-08, architecture 5.3/9) ---
    # G1: at least 90% of in-scope rows must be fully grounded. A score of
    # A score of 1.0 means every factual claim is supported; the 0.90
    # value is the required share of rows, not an average-score threshold.
    eval_groundedness_threshold: float = 0.90

    # --- Server (ADR-13) ---
    # Single-user, no authentication, localhost only (LD-07).
    server_host: str = "127.0.0.1"
    server_port: int = 8000

    # Shared password in front of every route, for a PUBLISHED container
    # only (ST-05, Railway hosting). Empty is the default and means NO
    # GATE, so the local-first behaviour ADR-13 describes is exactly
    # unchanged; see ui/access_gate.py for what this does and, more
    # importantly, what it does not do. Set it whenever `server_host` is
    # not a loopback address, because at that point "no authentication"
    # stops being a design decision and becomes an open door.
    access_password: str = ""

    # Turns an instance into a READ-ONLY window on work done elsewhere:
    # the Reports screen, the workspace list and the passage viewer still
    # serve, while Sync and Chat decline with a sentence instead of
    # trying. Empty/False is the default, so a laptop run is exactly
    # unchanged.
    #
    # WHY THIS EXISTS, measured rather than assumed. Both Sync and Chat
    # load `embedding_model` -- Chat too, via `vector_store`'s
    # `embed_query`, so this is not a Sync-only limit. That model is
    # intfloat/multilingual-e5-base: 278M parameters, which is 1,112 MB at
    # float32. A small trial-plan container cannot load it at all, and the
    # failure is the worst kind -- the platform kills the process mid-load
    # and restarts it, the browser sees a spinner that never ends, and
    # nothing anywhere says why.
    #
    # Setting this makes the limit HONEST instead of silent. It is not a
    # workaround for the memory cap and it does not make answering work;
    # the fix for that is a bigger box or a smaller model, and the second
    # one would change every stored vector and invalidate the evaluation
    # this release is gated on (docs/evals/ST-36-triage.md).
    evidence_only: bool = False

    # --- Workspace validation (ST-11) ---
    # Mirrors docs/phase2/openapi.yaml WorkspaceCreate/WorkspaceUpdate
    # `name` constraints (minLength/maxLength). Read from here in
    # workspaces.py; never hardcode these limits a second time.
    workspace_name_min_length: int = 1
    workspace_name_max_length: int = 100
    # PRD section 10: warning only. Sync remains allowed above either limit.
    workspace_soft_cap_pages: int = 1500
    workspace_soft_cap_files: int = 50
    # Mirrors docs/phase2/openapi.yaml WorkspaceCreate `folder_path`
    # minLength. Checked against the stripped value so whitespace-only
    # paths are rejected too (openapi's raw minLength alone would not
    # catch "   ").
    workspace_folder_path_min_length: int = 1

    # --- Live folder watching (F-13, V2 Low) ---
    # Architecture p.97/387: "the watcher wraps ingestion.sync" (today's
    # sync.py -- the module was flattened out of an `ingestion` package
    # since that line was written; same seam, `Runtime.start_sync`) and
    # `watchdog` is EXCLUDED ON PURPOSE ("F-13 is V2"), so watcher.py polls
    # with os.stat snapshots instead of a new dependency. Off by default:
    # F-02's manual Sync stays the only V1 behaviour until an operator
    # opts in. Never started when `evidence_only` is on, even if this is
    # true -- see watcher.start_if_enabled.
    watch_folders: bool = False
    # Seconds between two folder polls. watcher.py treats a file as fully
    # written only once its (size, mtime) is identical across two
    # consecutive polls, so this is also roughly the minimum extra delay
    # before a dropped file starts a Sync on its own. Must be > 0 -- see
    # the validator below.
    watch_interval_seconds: float = 5.0

    @field_validator("watch_interval_seconds")
    @classmethod
    def _watch_interval_must_be_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("watch_interval_seconds must be greater than 0")
        return value

    # --- Answer feedback (F-15, V2 Low) ---
    # Mirrors question_max_length's role for AskRequest: the one bound both
    # `ui/feedback.py` (validating a POST /chat/feedback) and the S1
    # textarea's `maxlength` attribute read from. A comment is free text
    # typed by the operator, not a document, so this is a generous UI
    # guard rail rather than a security boundary -- LD-07/ADR-13 apply here
    # exactly as they do to a question.
    feedback_comment_max_chars: int = 2000


@lru_cache
def get_settings() -> Settings:
    """Cached Settings instance; import and call this, never instantiate
    Settings() directly in module code, so every module shares one config
    read of .env."""
    return Settings()
