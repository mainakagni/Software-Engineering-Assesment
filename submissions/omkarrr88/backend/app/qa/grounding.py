"""The second refusal gate: an answer stands only if it cites a passage that was really sent and at
least one of its quotes can be found in that passage."""

import re
from collections.abc import Collection
from dataclasses import dataclass
from difflib import SequenceMatcher

from pydantic import BaseModel, ValidationError

from app.providers.errors import ProviderError
from app.qa.retrieval import RetrievedChunk

NOT_FOUND_ANSWER = "I couldn't find this in your documents."
MIN_QUOTE_CHARS = 12  # shorter quotes ("the policy") would match almost any passage
MIN_MATCH_SHARE = 0.8  # a quote may differ slightly (e.g. a dropped word) from its source
MAX_CITATIONS = 6

# Curly quotes, dashes and the minus sign become plain ASCII; soft hyphens (from PDFs) are dropped.
_TRANSLATE = str.maketrans(
    {
        "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
        "\u2013": "-", "\u2014": "-", "\u2212": "-", "\u00ad": None,
    }
)  # fmt: skip
_WHITESPACE = re.compile(r"\s+")
# "(S1)", "[S2]" or "(S1, S3)" in the answer text: the citations already name the sources.
_SOURCE_MARKER = re.compile(r"\s*[(\[]\s*(S\d+(?:\s*[,;]\s*S\d+)*)\s*[)\]]")
_MARKER_SEPARATOR = re.compile(r"\s*[,;]\s*")


class ModelCitation(BaseModel):
    source_id: str
    quote: str


class ModelReply(BaseModel):
    found: bool
    answer: str
    citations: list[ModelCitation]


@dataclass(frozen=True)
class GroundedCitation:
    source_id: str
    chunk: RetrievedChunk
    quote: str
    quote_verified: bool


@dataclass(frozen=True)
class GroundedAnswer:
    found: bool
    answer: str
    citations: list[GroundedCitation]


def parse_reply(text: str) -> ModelReply:
    try:
        return ModelReply.model_validate_json(text)
    except ValidationError as exc:
        # Usually a reply cut short; asking again normally fixes it.
        raise ProviderError(
            "llm", "bad_response", "The reply did not match the schema.", retryable=True
        ) from exc


def normalise(text: str) -> str:
    return _WHITESPACE.sub(" ", text.translate(_TRANSLATE)).strip().casefold()


def _normalise_quote(quote: str) -> str:
    """A quote without the quotation marks or final full stop a model may wrap it in."""
    return normalise(quote).strip(" .\"'")


def verify_quote(quote: str, source_text: str) -> bool:
    """True if the quote (after normalising case, spaces, quotes and dashes) is in the source."""
    needle, haystack = _normalise_quote(quote), normalise(source_text)
    if len(needle) < MIN_QUOTE_CHARS:
        return False
    if needle in haystack:
        return True
    match = SequenceMatcher(None, haystack, needle, autojunk=False).find_longest_match(
        0, len(haystack), 0, len(needle)
    )
    return match.size / len(needle) >= MIN_MATCH_SHARE


def ground(reply: ModelReply, sources: dict[str, RetrievedChunk]) -> GroundedAnswer:
    citations: list[GroundedCitation] = []
    seen: set[tuple[str, str]] = set()
    for citation in reply.citations:
        source_id = citation.source_id.strip()
        chunk = sources.get(source_id)
        key = (source_id, _normalise_quote(citation.quote))
        if chunk is None or key in seen:  # a source that was never sent, or a repeat
            continue
        seen.add(key)
        citations.append(
            GroundedCitation(
                source_id=source_id,
                chunk=chunk,
                quote=citation.quote.strip(),
                quote_verified=verify_quote(citation.quote, chunk.text),
            )
        )
    citations = citations[:MAX_CITATIONS]
    answer = strip_source_markers(reply.answer, sources.keys())
    if reply.found and answer and any(c.quote_verified for c in citations):
        return GroundedAnswer(found=True, answer=answer, citations=citations)
    return GroundedAnswer(found=False, answer=NOT_FOUND_ANSWER, citations=[])


def strip_source_markers(answer: str, source_ids: Collection[str]) -> str:
    """The answer without source markers such as "(S1)", which mean nothing to the reader.

    Only markers made entirely of IDs that were sent are removed, so text that merely looks like
    a marker stays.
    """

    def replace(match: re.Match[str]) -> str:
        ids = _MARKER_SEPARATOR.split(match.group(1))
        return "" if all(source_id in source_ids for source_id in ids) else match.group(0)

    return _SOURCE_MARKER.sub(replace, answer).strip()
