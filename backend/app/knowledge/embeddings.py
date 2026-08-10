"""Text embeddings.

**What this is, plainly:** a deterministic *lexical* embedder built from hashed word and
character n-grams, L2-normalised to 384 dimensions. It captures vocabulary overlap,
morphology and phrasing. It does not capture meaning the way a trained neural encoder
does — "the moon turned to blood" and "lunar eclipse" are close for a human and far apart
here.

**Why it is the default:** it needs no model download, no GPU and no API call, so search,
tests and the whole platform work identically offline and in CI. It is genuinely useful
for the retrieval job it does here — matching a quoted passage to a corpus entry is
largely a lexical problem.

**How to do better:** implement `Embedder` with a real encoder (e.g. a sentence-transformer
served locally, or a hosted embedding API) and set `EMBEDDING_PROVIDER`. The RAG layer,
the pgvector column and the search API all go through this interface and need no changes.
The retrieved chunk's `score` is reported to the user either way, so nobody is misled
about how strong a match is.
"""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from typing import Protocol

from app.db.models.knowledge import EMBEDDING_DIM

MODEL_NAME = "starcode-lexical-hash-v1"

_TOKEN_RE = re.compile(r"[\wͰ-῿Ⲁ-ⷿ]+", re.UNICODE)

#: Ignored for retrieval: they carry no discriminating signal and dominate short queries.
_STOPWORDS = frozenset(
    """a an and are as at be by for from has have he her his i in is it its of on or
    she that the their them there they this to was were what when which who will with
    you your not but if then than so such have had do does did shall may can""".split()
)


class Embedder(Protocol):
    model_name: str
    dimensions: int

    def embed(self, text: str) -> list[float]: ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


def normalize_text(text: str) -> str:
    """NFKC-fold, lowercase and collapse whitespace.

    NFKC matters here more than in most applications: the corpus mixes Greek, Hebrew and
    transliterations, and unnormalised Unicode would make identical words hash differently.
    """
    text = unicodedata.normalize("NFKC", text).lower()
    return re.sub(r"\s+", " ", text).strip()


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(normalize_text(text)) if t not in _STOPWORDS]


def _hash_index(feature: str, dimensions: int) -> tuple[int, float]:
    """Feature hashing with a signed hash, which keeps collisions from systematically
    inflating similarity."""
    digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
    value = int.from_bytes(digest, "big")
    return value % dimensions, 1.0 if (value >> 63) & 1 else -1.0


class LexicalHashEmbedder:
    """Hashed bag of unigrams, bigrams and character 4-grams with sublinear term scaling."""

    model_name = MODEL_NAME

    def __init__(self, dimensions: int = EMBEDDING_DIM) -> None:
        self.dimensions = dimensions

    def _features(self, text: str) -> dict[str, float]:
        tokens = tokenize(text)
        counts: dict[str, float] = {}

        for token in tokens:
            counts[f"w:{token}"] = counts.get(f"w:{token}", 0.0) + 1.0

        # Deliberately ragged: the tail token has no successor to pair with.
        for first, second in zip(tokens, tokens[1:], strict=False):
            key = f"b:{first}_{second}"
            counts[key] = counts.get(key, 0.0) + 1.0

        # Character n-grams give partial credit for inflected and transliterated forms
        # ("Nebuchadnezzar" / "Nebuchadrezzar"), which matters a great deal in this corpus.
        for token in tokens:
            if len(token) >= 5:
                padded = f"^{token}$"
                for i in range(len(padded) - 3):
                    key = f"c:{padded[i : i + 4]}"
                    counts[key] = counts.get(key, 0.0) + 0.5

        # Sublinear scaling: a word repeated twenty times is not twenty times as relevant.
        return {k: 1.0 + math.log(v) for k, v in counts.items()}

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        if not text or not text.strip():
            return vector

        for feature, weight in self._features(text).items():
            index, sign = _hash_index(feature, self.dimensions)
            vector[index] += sign * weight

        norm = math.sqrt(sum(v * v for v in vector))
        if norm == 0:
            return vector
        return [v / norm for v in vector]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


_embedder: Embedder = LexicalHashEmbedder()


def get_embedder() -> Embedder:
    return _embedder


def set_embedder(embedder: Embedder) -> None:
    """Swap the implementation (used by tests and by any future neural provider)."""
    global _embedder
    _embedder = embedder


def embed(text: str) -> list[float]:
    return _embedder.embed(text)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Both sides are pre-normalised, so this is a dot product; the guard is for safety
    if a caller supplies a raw vector."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    if abs(na - 1.0) < 1e-6 and abs(nb - 1.0) < 1e-6:
        return max(-1.0, min(1.0, dot))
    return max(-1.0, min(1.0, dot / (na * nb)))


def jaccard_overlap(a: str, b: str) -> float:
    """Plain token overlap, used to sanity-check a vector hit before it is presented as
    a source match. Two texts with a high cosine but near-zero token overlap are a hash
    artefact, not a real match."""
    sa, sb = set(tokenize(a)), set(tokenize(b))
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


__all__ = [
    "MODEL_NAME",
    "EMBEDDING_DIM",
    "Embedder",
    "LexicalHashEmbedder",
    "get_embedder",
    "set_embedder",
    "embed",
    "cosine_similarity",
    "jaccard_overlap",
    "normalize_text",
    "tokenize",
]
