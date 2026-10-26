"""Dependency-free text vectorisation and similarity.

This is the built-in backend for the ``vector`` capability. It replaces the
previous numpy + scikit-learn TF-IDF fallback so that semantic similarity keeps
working in a minimal installation.

The algorithm is a deterministic character n-gram hashing TF-IDF:

1. Each text is normalised to lowercase and split into overlapping character
   n-grams, which is robust for Chinese input where whitespace tokenisation
   does not apply.
2. n-grams are hashed into a fixed-width vector (the hashing trick), so no
   vocabulary needs to be stored and results are reproducible across runs.
3. Sub-linear term frequency dampens repeated n-grams.
4. Document frequency weighting is applied by counting how many documents each
   hash bucket appears in.
5. Vectors are L2-normalised so that cosine similarity is a plain dot product.

Everything is pure Python: no numpy, no scikit-learn. Performance is adequate
for the audit scale targeted here (up to 1000 issues), and the results are
deterministic, which matters because duplicate detection feeds a scored metric.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

#: Vector width. Larger reduces hash collisions but costs memory and time.
DEFAULT_DIMENSIONS = 4096

#: Character n-gram sizes. Bigrams to 5-grams mirror the previous sklearn
#: configuration (``analyzer="char_wb"``, ``ngram_range=(2, 5)``).
_NGRAM_RANGE = (2, 5)


@dataclass(frozen=True)
class SparseVector:
    """A sparse vector keyed by hashed n-gram bucket."""

    values: dict[int, float]

    def dot(self, other: SparseVector) -> float:
        """Dot product, iterating the smaller vector for efficiency."""
        if len(self.values) > len(other.values):
            return other.dot(self)
        return sum(value * other.values.get(key, 0.0) for key, value in self.values.items())


def _normalise_text(text: str) -> str:
    return " ".join((text or "").lower().split())


def _ngrams(text: str):
    """Yield character n-grams for the supported ranges.

    Short texts (length < 2) fall back to yielding the text itself so that even
    minimal input produces a usable vector rather than an empty one.
    """
    length = len(text)
    if length < _NGRAM_RANGE[0]:
        if text:
            yield text
        return
    for size in _NGRAM_RANGE:
        if size > length:
            continue
        for start in range(length - size + 1):
            yield text[start : start + size]


def _bucket(gram: str, dimensions: int) -> int:
    """Stable hash of an n-gram into ``[0, dimensions)``.

    ``hashlib`` is used instead of the built-in ``hash`` because the latter is
    salted per process, which would make results non-reproducible.
    """
    digest = hashlib.blake2b(gram.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") % dimensions


def _term_counts(text: str, dimensions: int) -> dict[int, float]:
    counts: dict[int, float] = {}
    for gram in _ngrams(text):
        key = _bucket(gram, dimensions)
        counts[key] = counts.get(key, 0.0) + 1.0
    return counts


def encode_texts(
    texts: list[str],
    dimensions: int = DEFAULT_DIMENSIONS,
) -> list[SparseVector]:
    """Vectorise texts with hashing TF-IDF, L2-normalised.

    Args:
        texts: Raw issue texts. Empty strings produce empty vectors.
        dimensions: Hash space width.

    Returns:
        One :class:`SparseVector` per input text, in input order. Every
        non-empty, non-degenerate vector has L2 norm 1 (or is empty).
    """
    if not texts:
        return []

    counts_per_document = [_term_counts(_normalise_text(text), dimensions) for text in texts]
    document_count = len(counts_per_document)

    document_frequency: dict[int, int] = {}
    for counts in counts_per_document:
        for key in counts:
            document_frequency[key] = document_frequency.get(key, 0) + 1

    # Smoothed inverse document frequency. Documents containing every term get a
    # small positive weight rather than zero, avoiding degenerate all-zero
    # vectors when only one distinct text exists.
    idf = {
        key: math.log((1.0 + document_count) / (1.0 + frequency)) + 1.0
        for key, frequency in document_frequency.items()
    }

    vectors: list[SparseVector] = []
    for counts in counts_per_document:
        weighted = {
            key: (1.0 + math.log(count)) * idf.get(key, 1.0)
            for key, count in counts.items()
        }
        norm = math.sqrt(sum(value * value for value in weighted.values()))
        if norm:
            weighted = {key: value / norm for key, value in weighted.items()}
        else:
            weighted = {}
        vectors.append(SparseVector(weighted))
    return vectors


def cosine_similarity(left: SparseVector, right: SparseVector) -> float:
    """Cosine similarity of two L2-normalised vectors, clamped to [0, 1]."""
    if not left.values or not right.values:
        return 0.0
    return max(0.0, min(1.0, left.dot(right)))


def similarity_pairs(
    issue_numbers: list[int],
    vectors: list[SparseVector],
    threshold: float,
) -> list[tuple[int, int, float]]:
    """Find candidate pairs at or above ``threshold``.

    Uses the inverted index of hash buckets so that only pairs sharing at least
    one bucket are compared, keeping this near-linear for sparse vectors. The
    result is sorted for reproducibility.
    """
    if len(issue_numbers) != len(vectors):
        raise ValueError("issue_numbers 与 vectors 长度必须一致")
    if len(issue_numbers) < 2:
        return []

    inverted: dict[int, list[int]] = {}
    for position, vector in enumerate(vectors):
        for key in vector.values:
            inverted.setdefault(key, []).append(position)

    seen: set[tuple[int, int]] = set()
    candidates: list[tuple[int, int, float]] = []
    for positions in inverted.values():
        if len(positions) < 2:
            continue
        for index, left in enumerate(positions):
            for right in positions[index + 1 :]:
                pair = (left, right) if left < right else (right, left)
                if pair in seen:
                    continue
                seen.add(pair)
                score = cosine_similarity(vectors[pair[0]], vectors[pair[1]])
                if score >= threshold:
                    candidates.append(
                        (issue_numbers[pair[0]], issue_numbers[pair[1]], round(score, 6))
                    )
    return sorted(candidates, key=lambda item: (-item[2], item[0], item[1]))
