from __future__ import annotations

from app.parsers.text_normalizer import (
    PAGE_SEPARATOR,
    count_characters,
    count_words,
    join_pages,
    normalize_inline,
    normalize_text,
)


def test_normalize_text_standardizes_breaks_spaces_and_preserves_unicode() -> None:
    raw = "  João\x00   da  Silva \r\n\r\n\r\nEngenharia   de   Dados — São Paulo (€) \r"
    cleaned = normalize_text(raw)
    assert cleaned == "João da Silva\n\nEngenharia de Dados — São Paulo (€)"


def test_normalize_inline_collapses_newlines_and_spaces() -> None:
    assert normalize_inline("  Python\n  3.13 \t FastAPI  ") == "Python 3.13 FastAPI"


def test_join_pages_preserves_non_empty_pages_with_form_feed() -> None:
    joined = join_pages(["Page 1\r\nLine 2", "   ", "Page 3"])
    assert joined == f"Page 1\nLine 2{PAGE_SEPARATOR}Page 3"


def test_word_and_character_counts() -> None:
    text = "Ana Souza\nBackend Engineer"
    assert count_words(text) == 4
    assert count_characters(text) == len(text)
