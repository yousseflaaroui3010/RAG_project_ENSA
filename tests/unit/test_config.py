"""Smoke test for config.py: the settings object loads with the documented
defaults and every knob referenced in the architecture is present.

ST-02 acceptance: uv sync green, every config var documented; this test is
the executable half of that check (defaults match section 7.5 / 8 / ADR-06).
"""

from config import Settings, get_settings


def test_defaults_match_architecture_pins():
    settings = Settings(_env_file=None)

    # F-04 retry ceiling default (architecture §5.2).
    assert settings.retry_ceiling == 2
    # Chunking knobs (architecture §7.5).
    assert settings.chunk_child_size_chars == 500
    assert settings.chunk_child_overlap_chars == 100
    assert settings.parent_merge_below_chars == 2000
    assert settings.parent_split_above_chars == 4000
    # Server binds localhost only (LD-07, ADR-13).
    assert settings.server_host == "127.0.0.1"
    assert settings.server_port == 8000
    # Embedding prefixes (ADR-05 binding rule).
    assert settings.embedding_passage_prefix == "passage: "
    assert settings.embedding_query_prefix == "query: "
    assert settings.embedding_model == "intfloat/multilingual-e5-base"


def test_get_settings_is_cached_singleton():
    assert get_settings() is get_settings()
