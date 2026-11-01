from app.utils.chunker import chunk_text, extract_text_from_plain


def test_extract_text_from_plain():
    text_data = b"Hello world! This is a test document."
    pages = extract_text_from_plain(text_data)
    assert len(pages) == 1
    assert pages[0]["page_number"] == 1
    assert pages[0]["text"] == "Hello world! This is a test document."


def test_chunk_text_small_document():
    pages = [{"page_number": 1, "text": "Short document."}]
    chunks = chunk_text(pages, chunk_size=500, chunk_overlap=100)
    assert len(chunks) == 1
    assert chunks[0]["content"] == "Short document."
    assert chunks[0]["page_number"] == 1
    assert chunks[0]["chunk_index"] == 0


def test_chunk_text_sliding_window_overlap():
  
    # Use a text with proper sentence endings so the sentence splitter fires
    sentences = ["This is sentence number {:03d}.".format(i) for i in range(50)]
    long_text = " ".join(sentences)  # ~1 750 characters
    pages = [{"page_number": 1, "text": long_text}]
    chunks = chunk_text(pages, chunk_size=300, chunk_overlap=50)

    assert len(chunks) > 1, "Expected multiple chunks from a long text"
    for i, c in enumerate(chunks):
        assert c["chunk_index"] == i, f"chunk_index mismatch at position {i}"
        assert c["page_number"] == 1
  
        assert len(c["content"]) <= 350, (
            f"Chunk {i} too long: {len(c['content'])} chars"
        )

