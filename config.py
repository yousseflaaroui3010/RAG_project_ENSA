"""Sanad configuration: the single source of truth for every tunable.

Hard technical rule (docs/phase2/CLAUDE.md): all tunables live in
config.py and .env (documented in .env.example). No magic literals in
module code -- import Settings/get_settings() instead of hardcoding a
value a second time.

Reads from a .env file via pydantic-settings (architecture §8, §12.1).
"""

from __future__ import annotations

from functools import lru_cache

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
    chat_model_cloud: str = "gemini-2.0-flash"
    # Local: any Ollama-served instruct model >= 7B (ADR-06 floor).
    chat_model_local: str = "mistral"
    # Gemini / Google AI Studio API key; read in cloud mode only.
    cloud_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"

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
    parent_citation_marker_pattern: str = r"Article\s+\d+"

    # --- Change detection (ST-12, PRD F-02, architecture §5.1) ---
    # File extensions Sync fingerprints and hands to the conversion ladder.
    # PRD F-02 scopes V1 to PDF, DOCX, TXT, MD; PPTX is V1.1 (F-11 / ST-48)
    # and is deliberately absent, so a deck in the folder is reported
    # Skipped-unsupported rather than silently ingested. Lower-case, no dot.
    supported_document_extensions: tuple[str, ...] = ("pdf", "docx", "txt", "md")
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

    # --- Server (ADR-13) ---
    # Single-user, no authentication, localhost only (LD-07).
    server_host: str = "127.0.0.1"
    server_port: int = 8000

    # --- Workspace validation (ST-11) ---
    # Mirrors docs/phase2/openapi.yaml WorkspaceCreate/WorkspaceUpdate
    # `name` constraints (minLength/maxLength). Read from here in
    # workspaces.py; never hardcode these limits a second time.
    workspace_name_min_length: int = 1
    workspace_name_max_length: int = 100
    # Mirrors docs/phase2/openapi.yaml WorkspaceCreate `folder_path`
    # minLength. Checked against the stripped value so whitespace-only
    # paths are rejected too (openapi's raw minLength alone would not
    # catch "   ").
    workspace_folder_path_min_length: int = 1


@lru_cache
def get_settings() -> Settings:
    """Cached Settings instance; import and call this, never instantiate
    Settings() directly in module code, so every module shares one config
    read of .env."""
    return Settings()
