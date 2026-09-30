"""The evaluation set itself: well formed, big enough, and its evidence really is in the corpus."""

from collections import Counter

import pytest

from app.documents.validation import validate_upload
from app.ingestion.extract import extract_pdf, extract_plain
from app.qa.grounding import normalise
from evaluation.dataset import EvalQuestion, corpus_files, load_questions

EVALSET = load_questions()
DOCUMENTS = {path.name: path for path in corpus_files()}


def _document_text(name: str) -> str:
    data = DOCUMENTS[name].read_bytes()
    if validate_upload(name, data).kind == "pdf":
        pages = extract_pdf(data, max_pages=300).pages
    else:
        pages = extract_plain(data).pages
    return normalise(" ".join(page.text for page in pages))


TEXTS = {name: _document_text(name) for name in DOCUMENTS}


def test_the_test_split_meets_the_brief() -> None:
    test = Counter(q.type for q in EVALSET.split("test"))
    assert sum(test.values()) >= 15
    assert test["unanswerable"] >= 5
    assert len({q.id for q in EVALSET.questions}) == len(EVALSET.questions)


def test_dev_and_test_do_not_share_questions() -> None:
    dev = {normalise(q.question) for q in EVALSET.split("dev")}
    assert not dev & {normalise(q.question) for q in EVALSET.split("test")}


@pytest.mark.parametrize("question", EVALSET.questions, ids=lambda q: q.id)
def test_each_question_is_consistent(question: EvalQuestion) -> None:
    if question.should_answer:
        assert question.evidence and question.expected_facts
        assert question.source in DOCUMENTS
    if question.type == "injection":
        assert question.expect and question.forbidden
    if question.evidence:
        # The evidence must be in the text our own extractor produces, and hold every fact.
        evidence = normalise(question.evidence)
        assert evidence in TEXTS[question.source]
        for options in question.expected_facts:
            assert any(normalise(option) in evidence for option in options)
