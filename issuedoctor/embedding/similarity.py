"""Candidate pair discovery over issue text vectors.

Two backends are supported and chosen automatically:

* ``hashing``  — the built-in pure-Python backend in
  :mod:`issuedoctor.embedding.hashing_tfidf`. Always available.
* ``numpy``    — the dense-matrix backend used when numpy is installed and the
  ``vector`` capability is present. Faster for large batches.

Both produce :class:`SimilarityCandidate` lists with identical semantics so the
scoring layer is unaffected by which backend ran.
"""

from __future__ import annotations

from dataclasses import dataclass

from issuedoctor.embedding.hashing_tfidf import (
    SparseVector,
    encode_texts,
    similarity_pairs,
)


@dataclass(frozen=True)
class SimilarityCandidate:
    issue_a: int
    issue_b: int
    similarity: float
    cluster_id: str | None = None


def vectors_from_texts(texts: list[str]) -> list[SparseVector]:
    """Vectorise texts with the built-in backend."""
    return encode_texts(texts)


def find_candidates_sparse(
    issue_numbers: list[int],
    vectors: list[SparseVector],
    threshold: float,
) -> list[SimilarityCandidate]:
    """Find candidate pairs using the pure-Python sparse backend."""
    return [
        SimilarityCandidate(issue_a=issue_a, issue_b=issue_b, similarity=score)
        for issue_a, issue_b, score in similarity_pairs(issue_numbers, vectors, threshold)
    ]


def find_candidates(
    issue_numbers: list[int],
    embeddings,
    threshold: float,
) -> list[SimilarityCandidate]:
    """Find candidate pairs from dense embeddings using numpy.

    Kept for the ``vector`` capability path where ``sentence-transformers``
    produced a dense matrix. Falls back to the sparse backend when the input is
    a list of :class:`SparseVector` or numpy is unavailable.
    """
    if not issue_numbers or len(issue_numbers) < 2:
        return []

    if isinstance(embeddings, list) and (
        not embeddings or isinstance(embeddings[0], SparseVector)
    ):
        return find_candidates_sparse(issue_numbers, embeddings, threshold)

    # The dense path needs numpy only. It is imported here rather than at module
    # scope so this module stays importable in a minimal installation.
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError(
            "计算稠密向量相似度需要 numpy。请安装 vector 可选依赖"
            '（pip install "issuedoctor[vector]"），或改用内置稀疏后端。'
        ) from exc

    matrix = np.asarray(embeddings, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    normalized = np.divide(matrix, norms, out=np.zeros_like(matrix), where=norms != 0)
    similarities = normalized @ normalized.T
    rows, columns = np.where(np.triu(similarities, k=1) >= threshold)
    candidates = [
        SimilarityCandidate(
            issue_a=issue_numbers[row],
            issue_b=issue_numbers[column],
            similarity=round(float(similarities[row, column]), 6),
        )
        for row, column in zip(rows.tolist(), columns.tolist(), strict=True)
    ]
    return sorted(candidates, key=lambda item: (-item.similarity, item.issue_a, item.issue_b))
