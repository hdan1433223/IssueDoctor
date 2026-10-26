"""Issue text vectorisation with optional caching.

The encoder has two modes:

* ``hashing`` (default) — pure-Python hashing TF-IDF from
  :mod:`issuedoctor.embedding.hashing_tfidf`. No optional dependency, no cache
  needed because it is fast and deterministic.
* ``model`` — a ``sentence-transformers`` model, used only when the ``vector``
  capability is installed. Encoded vectors are cached in SQLite so repeated
  audits of the same text do not re-run the model.

numpy is imported lazily inside the model path only.
"""

from __future__ import annotations

import hashlib

from issuedoctor.capabilities import is_available
from issuedoctor.embedding.hashing_tfidf import SparseVector, encode_texts
from issuedoctor.embedding.model_manager import EmbeddingModelManager


def issue_text(issue, maximum_characters: int) -> str:
    text = f"{issue.title.strip()}\n{(issue.body_excerpt or '').strip()}"
    return " ".join(text.split())[:maximum_characters]


class CachedEncoder:
    """Encoder preferring the local model backend, falling back to hashing.

    ``prefer_model`` is False by default so that a minimal installation never
    attempts to load a multi-hundred-megabyte model. The embedding service
    enables it only when the capability is present.
    """

    def __init__(
        self,
        manager: EmbeddingModelManager,
        model_name: str,
        *,
        prefer_model: bool = False,
    ) -> None:
        self.manager = manager
        self.model_name = model_name
        self.prefer_model = prefer_model

    def encode(self, texts: list[str]) -> list[SparseVector]:
        """Vectorise ``texts``, returning sparse vectors.

        The model backend's dense output is converted to :class:`SparseVector`
        so downstream code is uniform.
        """
        if not self.prefer_model or not is_available("vector"):
            return encode_texts(texts)
        return self._encode_with_model(texts)

    def _encode_with_model(self, texts: list[str]) -> list[SparseVector]:
        import numpy as np

        from issuedoctor.repositories.cache_repo import EmbeddingCacheRepository

        hashes = [hashlib.sha256(text.encode("utf-8")).hexdigest() for text in texts]
        first_text_by_hash: dict[str, str] = {}
        for text_hash, text in zip(hashes, texts, strict=True):
            first_text_by_hash.setdefault(text_hash, text)

        vectors_by_hash: dict[str, SparseVector] = {}
        missing: list[str] = []
        for text_hash in first_text_by_hash:
            cached = EmbeddingCacheRepository.get(text_hash, self.model_name)
            if cached is None:
                missing.append(text_hash)
            else:
                vectors_by_hash[text_hash] = _to_sparse(np.asarray(cached, dtype=np.float32))

        if missing:
            encoded = self.manager.load().encode(
                [first_text_by_hash[text_hash] for text_hash in missing],
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            for text_hash, vector in zip(missing, encoded, strict=True):
                normalized = _normalize(np.asarray(vector, dtype=np.float32))
                sparse = _to_sparse(normalized)
                vectors_by_hash[text_hash] = sparse
                EmbeddingCacheRepository.set(text_hash, self.model_name, normalized)

        return [vectors_by_hash[text_hash] for text_hash in hashes]


def _to_sparse(vector) -> SparseVector:
    """Convert a dense numpy vector into the shared sparse representation."""
    indices = (vector != 0).nonzero()[0]
    return SparseVector({int(index): float(vector[index]) for index in indices})


def _normalize(vector):
    import numpy as np

    norm = np.linalg.norm(vector)
    return vector / norm if norm else vector
