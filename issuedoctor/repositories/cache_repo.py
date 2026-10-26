import io
import json
import struct

from issuedoctor.extensions import db
from issuedoctor.models import AICache, EmbeddingCache


class AICacheRepository:
    @staticmethod
    def get(cache_key: str) -> dict | None:
        row = db.session.get(AICache, cache_key)
        return row.response_json if row else None

    @staticmethod
    def set(cache_key: str, response: dict) -> None:
        row = db.session.get(AICache, cache_key)
        if row is None:
            db.session.add(AICache(cache_key=cache_key, response_json=response))
        else:
            row.response_json = response
        db.session.commit()


def _get_row(text_hash: str, model_name: str):
    return db.session.execute(
        db.select(EmbeddingCache).where(
            EmbeddingCache.text_hash == text_hash,
            EmbeddingCache.model_name == model_name,
        )
    ).scalar_one_or_none()


class EmbeddingCacheRepository:
    """Cache for dense embedding vectors produced by the optional model backend.

    Vectors are stored as a small self-describing binary blob (magic + float32
    payload) rather than via ``numpy.save`` so that this module imports and
    operates without numpy installed. Only the model path touches this cache.
    """

    _MAGIC = b"IDV1"

    @staticmethod
    def get(text_hash: str, model_name: str) -> list[float] | None:
        row = _get_row(text_hash, model_name)
        if row is None:
            return None
        payload = row.vector
        if not payload:
            return None
        if payload[:4] != EmbeddingCacheRepository._MAGIC:
            return EmbeddingCacheRepository._decode_legacy(payload)
        (count,) = struct.unpack("<I", payload[4:8])
        return list(struct.unpack(f"<{count}f", payload[8 : 8 + 4 * count]))

    @staticmethod
    def set(text_hash: str, model_name: str, vector) -> None:
        blob = EmbeddingCacheRepository._encode(vector)
        row = _get_row(text_hash, model_name)
        values = {
            "vector": blob,
            "metadata_json": {
                "dimensions": len(vector),
                "dtype": "float32",
                "encoding": "idv1",
            },
        }
        if row is None:
            db.session.add(
                EmbeddingCache(text_hash=text_hash, model_name=model_name, **values)
            )
        else:
            row.vector = values["vector"]
            row.metadata_json = values["metadata_json"]
        db.session.commit()

    @staticmethod
    def _encode(vector) -> bytes:
        values = [float(item) for item in vector]
        return EmbeddingCacheRepository._MAGIC + struct.pack(
            f"<I{len(values)}f", len(values), *values
        )

    @staticmethod
    def _decode_legacy(payload: bytes) -> list[float] | None:
        """Read vectors written by the previous numpy-based implementation."""
        try:
            import numpy as np
        except ImportError:
            return None
        try:
            array = np.load(io.BytesIO(payload), allow_pickle=False)
        except Exception:
            return None
        return [float(item) for item in array]


# Retained for backwards compatibility with code that imported json helpers.
def _dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False)
