"""S6: what may be written into, read from, or removed from a workspace
folder by name. The name comes from a browser, so each refusal below is a
path an attacker or an accident could otherwise take."""

from __future__ import annotations

import asyncio

import pytest

from config import get_settings
from ui import documents
from ui.documents import DocumentError, checked_name, existing_document, save_document


async def _chunks(*parts: bytes):
    for part in parts:
        yield part


def _save(folder, name, *parts, declared=None):
    return asyncio.run(save_document(folder, name, _chunks(*parts), declared_size=declared))


@pytest.mark.parametrize(
    "name",
    [
        "",
        "   ",
        ".",
        "..",
        "../escape.pdf",
        "..\\escape.pdf",
        "sub/inner.pdf",
        "C:evil.pdf",
        "nul.pdf",
        "CON.txt",
        "com1.docx",
        "lpt9.md",
        ".hidden.pdf",
        "trailing.pdf.",
        "inner space .pdf.",
        "tab\tname.pdf",
        "nul\x00byte.pdf",
        "a" * 252 + ".pdf",
    ],
)
def test_unusable_names_are_refused(name):
    with pytest.raises(DocumentError) as caught:
        checked_name(name)
    assert caught.value.status in {400, 415}


@pytest.mark.parametrize("name", ["notes.exe", "page.html", "script.js", "noext", ".pdf"])
def test_unsupported_types_are_refused(name):
    with pytest.raises(DocumentError):
        checked_name(name)


@pytest.mark.parametrize(
    "name",
    ["Code du travail.pdf", "مدونة الشغل.pdf", "rapport.v2.DOCX", "console.pdf", "slides.pptx"],
)
def test_ordinary_names_are_accepted_as_typed(name):
    assert checked_name(name) == name


def test_surrounding_whitespace_from_the_browser_is_trimmed_not_kept():
    assert checked_name("  notes.pdf ") == "notes.pdf"


def test_a_saved_file_lands_whole_in_the_folder_and_leaves_no_temp(tmp_path):
    saved = _save(tmp_path, "notes.txt", b"hello ", b"world")

    assert (tmp_path / "notes.txt").read_bytes() == b"hello world"
    assert (saved.file_name, saved.size_bytes, saved.replaced) == ("notes.txt", 11, False)
    assert [p.name for p in tmp_path.iterdir()] == ["notes.txt"]


def test_saving_the_same_name_again_replaces_it_and_says_so(tmp_path):
    _save(tmp_path, "notes.txt", b"old")
    saved = _save(tmp_path, "notes.txt", b"new text")

    assert saved.replaced
    assert (tmp_path / "notes.txt").read_bytes() == b"new text"


def test_an_oversize_body_is_refused_midway_and_nothing_is_left(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "upload_max_bytes", 10)
    (tmp_path / "keep.txt").write_bytes(b"original")

    with pytest.raises(DocumentError) as caught:
        _save(tmp_path, "keep.txt", b"123456", b"789012")

    assert caught.value.status == 413
    assert (tmp_path / "keep.txt").read_bytes() == b"original", "a failed upload replaced the file"
    assert [p.name for p in tmp_path.iterdir()] == ["keep.txt"]


def test_a_declared_size_over_the_limit_is_refused_before_writing(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "upload_max_bytes", 10)

    with pytest.raises(DocumentError) as caught:
        _save(tmp_path, "big.txt", b"x", declared=11)

    assert caught.value.status == 413
    assert list(tmp_path.iterdir()) == []


def test_an_empty_upload_is_refused_and_leaves_nothing(tmp_path):
    with pytest.raises(DocumentError):
        _save(tmp_path, "empty.txt")
    assert list(tmp_path.iterdir()) == []


def test_a_missing_folder_is_refused(tmp_path):
    with pytest.raises(DocumentError) as caught:
        _save(tmp_path / "gone", "notes.txt", b"x")
    assert caught.value.status == 409


def test_a_symlink_pointing_out_of_the_folder_is_not_served(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    folder = tmp_path / "ws"
    folder.mkdir()
    try:
        (folder / "link.txt").symlink_to(outside / "secret.txt")
    except (OSError, NotImplementedError):
        pytest.skip("this machine does not allow creating symlinks")

    with pytest.raises(DocumentError):
        existing_document(folder, "link.txt")


def test_removing_deletes_only_that_file(tmp_path):
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")

    assert documents.remove_document(tmp_path, "a.txt") == "a.txt"
    assert [p.name for p in tmp_path.iterdir()] == ["b.txt"]


def test_removing_a_missing_or_unsupported_file_is_refused(tmp_path):
    (tmp_path / ".env").write_text("KEY=1", encoding="utf-8")
    with pytest.raises(DocumentError):
        documents.remove_document(tmp_path, "nothing.txt")
    with pytest.raises(DocumentError):
        documents.remove_document(tmp_path, ".env")
    assert (tmp_path / ".env").exists()
