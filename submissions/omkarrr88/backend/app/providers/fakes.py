"""Offline stand-ins for the providers.

Used by the tests and selectable with EMBEDDING_PROVIDER=fake / LLM_PROVIDER=fake, so the whole
stack (including CI's docker compose smoke test) runs without an API key.
"""

import hashlib
import math
import re
from collections.abc import Sequence

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
