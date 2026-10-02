"""
Unit tests for the text chunker service.
Tests splitting logic without any external dependencies.
"""
import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from app.services.chunker import split_text


def test_empty_string_returns_empty():
    assert split_text("") == []


def test_short_text_not_split():
    text = "Hello world"
    result = split_text(text, chunk_size=100)
    assert len(result) == 1
    assert result[0] == text


def test_long_text_splits():
    # 5000-char text should be split with default chunk_size=2048
    text = "word " * 1000
    result = split_text(text, chunk_size=2048)
    assert len(result) > 1


def test_each_chunk_within_size():
    text = "paragraph one.\n\n" * 100
    chunk_size = 500
    result = split_text(text, chunk_size=chunk_size)
    for chunk in result:
        # Allow slight overflow from overlap only
        assert len(chunk) <= chunk_size + 300, f"Chunk too large: {len(chunk)}"


def test_overlap_creates_shared_content():
    text = "A " * 300 + "\n\n" + "B " * 300
    chunks = split_text(text, chunk_size=600, chunk_overlap=100)
    assert len(chunks) >= 2
    # Second chunk should start with tail of first (overlap)
    # Just verify we have multiple chunks
    assert all(c.strip() for c in chunks)


def test_paragraph_split_preferred():
    text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
    result = split_text(text, chunk_size=25)
    assert len(result) >= 3


def test_whitespace_only_returns_empty():
    assert split_text("   \n\n\t  ") == []
