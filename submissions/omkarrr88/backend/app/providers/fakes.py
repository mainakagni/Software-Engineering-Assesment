"""Offline stand-ins for the providers.

Used by the tests and selectable with EMBEDDING_PROVIDER=fake / LLM_PROVIDER=fake, so the whole
stack (including CI's docker compose smoke test) runs without an API key.
"""

import hashlib
import json
import math
import re
from collections import deque
from collections.abc import Sequence
from typing import Any

from app.providers.llm import LLMResult

TOKEN = re.compile(r"[a-z0-9]+")
STOPWORDS = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does", "for", "from",
        "how", "i", "in", "is", "it", "of", "on", "or", "should", "the", "this", "to", "what",
        "when", "where", "which", "who", "why", "will", "with", "you", "your",
    }
)  # fmt: skip


def content_words(text: str) -> list[str]:
    return [word for word in TOKEN.findall(text.lower()) if word not in STOPWORDS]


class FakeEmbedder:
    """Deterministic bag-of-words vectors: texts that share words get a high cosine similarity.

    Each word is hashed to one of `dim` positions with a random-looking sign, so unrelated texts end
    up close to orthogonal. Good enough to test retrieval end to end; not a language model.
    """

    model = "fake-embedding"

    def __init__(self, dim: int = 768) -> None:
        self.dim = dim
        self.calls = 0

    def embed_documents(self, texts: Sequence[str], title: str | None = None) -> list[list[float]]:
        self.calls += 1
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        self.calls += 1
        return self._vector(text)

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        for word in content_words(text) or ["empty"]:
            digest = hashlib.blake2b(word.encode(), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dim
            vector[index] += 1.0 if digest[4] % 2 else -1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


_SOURCE_BLOCK = re.compile(r'<source id="(S\d+)"[^>]*>\n(.*?)\n</source>', re.DOTALL)
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


class FakeLLM:
    """Answers by picking the source sentence that shares the most words with the question.

    Tests can also queue exact replies (JSON text) or exceptions, and inspect `calls`.
    """

    model = "fake-llm"

    def __init__(self) -> None:
        self.queued: deque[str | Exception] = deque()
        self.calls: list[tuple[str, str]] = []

    def queue(self, *replies: str | Exception) -> None:
        self.queued.extend(replies)

    def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> LLMResult:
        self.calls.append((system, user))
        if self.queued:
            reply = self.queued.popleft()
            if isinstance(reply, Exception):
                raise reply
            text = reply
        else:
            text = json.dumps(self._answer(user))
        return LLMResult(
            text=text,
            prompt_tokens=math.ceil(len(system + user) / 4),
            output_tokens=math.ceil(len(text) / 4),
            thinking_tokens=0,
            model=self.model,
        )

    def _answer(self, prompt: str) -> dict[str, Any]:
        question = prompt.rsplit("Question:", 1)[-1].split("\n", 1)[0]
        wanted = set(content_words(question))
        best: tuple[int, str, str] = (0, "", "")
        for source_id, body in _SOURCE_BLOCK.findall(prompt):
            for sentence in _SENTENCE.split(body.replace("\n", " ")):
                overlap = len(wanted & set(content_words(sentence)))
                if overlap > best[0]:
                    best = (overlap, source_id, sentence.strip())
        overlap, source_id, sentence = best
        if overlap < 2:
            return {"found": False, "citations": [], "answer": "The sources do not say."}
        return {
            "found": True,
            "citations": [{"source_id": source_id, "quote": sentence}],
            "answer": sentence,
        }
