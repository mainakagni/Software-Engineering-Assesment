import re
from itertools import pairwise

import pytest

from app.ingestion.chunking import Chunk, chunk_document, embedding_text
from app.ingestion.extract import PageText

SIZE, OVERLAP = 300, 60


def _words(text: str) -> set[str]:
    return set(re.findall(r"\w+", text))


def _sentences(count: int, prefix: str = "Rule") -> str:
    return " ".join(
        f"{prefix} number {i} says something specific about expenses." for i in range(count)
    )


def test_short_text_is_one_chunk() -> None:
    chunks = chunk_document(
        [PageText(None, "Just one line.")], markdown=False, size=SIZE, overlap=OVERLAP
    )
    assert chunks == [
        Chunk(index=0, text="Just one line.", page_start=None, page_end=None, section=None)
    ]


def test_chunks_respect_the_size_and_keep_every_word() -> None:
    text = "\n\n".join(_sentences(4, prefix=f"Para{p}") for p in range(10))
    chunks = chunk_document([PageText(None, text)], markdown=False, size=SIZE, overlap=OVERLAP)
    assert len(chunks) > 3
    assert all(len(chunk.text) <= SIZE for chunk in chunks)
    assert [chunk.index for chunk in chunks] == list(range(len(chunks)))
    assert set().union(*(_words(chunk.text) for chunk in chunks)) == _words(text)


def test_consecutive_chunks_overlap_by_whole_sentences() -> None:
    chunks = chunk_document(
        [PageText(None, _sentences(30))], markdown=False, size=SIZE, overlap=OVERLAP
    )
    for previous, current in pairwise(chunks):
        last_sentence = previous.text.split(". ")[-1]
        assert current.text.startswith(last_sentence)
        assert len(last_sentence) <= OVERLAP


def test_no_overlap_when_disabled() -> None:
    chunks = chunk_document([PageText(None, _sentences(30))], markdown=False, size=SIZE, overlap=0)
    joined = " ".join(chunk.text for chunk in chunks)
    assert joined.count("Rule number 5 ") == 1


def test_pdf_chunks_record_their_page_range() -> None:
    pages = [PageText(1, _sentences(3, "Alpha")), PageText(2, _sentences(3, "Beta"))]
    chunks = chunk_document(pages, markdown=False, size=2000, overlap=OVERLAP)
    assert (chunks[0].page_start, chunks[0].page_end) == (1, 2)

    small = chunk_document(pages, markdown=False, size=SIZE, overlap=OVERLAP)
    assert small[0].page_start == 1
    assert small[-1].page_end == 2
    assert all(c.page_start is not None and c.page_start <= c.page_end for c in small)  # type: ignore[operator]


def test_pdf_line_wraps_are_joined_but_paragraphs_are_kept() -> None:
    text = "The policy applies\nto all staff.\n\nA second paragraph."
    [chunk] = chunk_document([PageText(1, text)], markdown=False, size=SIZE, overlap=OVERLAP)
    assert chunk.text == "The policy applies to all staff.\n\nA second paragraph."


def test_markdown_headings_become_the_section_path() -> None:
    text = "\n".join(
        [
            "# Travel",
            "Intro text.",
            "## Per diem",
            "Meals are covered up to $75.",
            "### Alcohol",
            "Never reimbursed.",
            "## Lodging",
            "Hotels up to $180 a night.",
        ]
    )
    chunks = chunk_document([PageText(None, text)], markdown=True, size=SIZE, overlap=OVERLAP)
    assert [(c.section, c.text) for c in chunks] == [
        ("Travel", "Intro text."),
        ("Travel > Per diem", "Meals are covered up to $75."),
        ("Travel > Per diem > Alcohol", "Never reimbursed."),
        ("Travel > Lodging", "Hotels up to $180 a night."),
    ]


def test_markdown_sections_are_never_mixed_and_overlap_stays_inside_one() -> None:
    text = f"# A\n{_sentences(12, 'Apple')}\n# B\n{_sentences(12, 'Berry')}"
    chunks = chunk_document([PageText(None, text)], markdown=True, size=SIZE, overlap=OVERLAP)
    for chunk in chunks:
        assert ("Apple" in chunk.text) != ("Berry" in chunk.text)
        assert chunk.section == ("A" if "Apple" in chunk.text else "B")


def test_hashes_inside_code_fences_are_not_headings() -> None:
    text = "# Setup\n```bash\n# install it\npip install x\n```\nDone."
    chunks = chunk_document([PageText(None, text)], markdown=True, size=SIZE, overlap=OVERLAP)
    assert {c.section for c in chunks} == {"Setup"}
    assert "# install it" in chunks[0].text


def test_markdown_keeps_list_line_breaks() -> None:
    text = "# Rules\n- first\n- second"
    [chunk] = chunk_document([PageText(None, text)], markdown=True, size=SIZE, overlap=OVERLAP)
    assert chunk.text == "- first\n- second"


def test_a_huge_word_is_cut_to_fit() -> None:
    url = "https://example.com/" + "x" * 700
    chunks = chunk_document(
        [PageText(None, f"See {url} for details.")], markdown=False, size=SIZE, overlap=OVERLAP
    )
    assert all(len(chunk.text) <= SIZE for chunk in chunks)
    assert "".join(chunk.text for chunk in chunks).count("x") >= 700


def test_embedding_text_starts_with_the_section() -> None:
    chunk = Chunk(
        index=0, text="Meals up to $75.", page_start=None, page_end=None, section="Travel"
    )
    assert embedding_text(chunk) == "Travel\n\nMeals up to $75."
    assert embedding_text(Chunk(0, "Plain.", 1, 1, None)) == "Plain."


@pytest.mark.parametrize(("size", "overlap"), [(50, 10), (300, 150), (300, -1)])
def test_rejects_nonsense_settings(size: int, overlap: int) -> None:
    with pytest.raises(ValueError, match="chunk size"):
        chunk_document([PageText(None, "x")], markdown=False, size=size, overlap=overlap)


def test_empty_input_gives_no_chunks() -> None:
    assert chunk_document([], markdown=False, size=SIZE, overlap=OVERLAP) == []
