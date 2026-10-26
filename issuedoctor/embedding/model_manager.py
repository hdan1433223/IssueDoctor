"""Loading of the optional local embedding model.

``sentence-transformers`` is imported lazily inside :meth:`EmbeddingModelManager.load`
so that this module can be imported without PyTorch installed. Callers that
require the model should first check :func:`issuedoctor.capabilities.is_available`
for the ``vector`` capability, or be prepared to handle
:class:`issuedoctor.capabilities.OptionalDependencyError`.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from issuedoctor.capabilities import OptionalDependencyError, is_available


class EmbeddingModelManager:
    def __init__(
        self,
        model_name: str,
        cache_dir: str | Path,
        *,
        loader: Callable[..., Any] | None = None,
    ) -> None:
        self.model_name = model_name
        self.cache_dir = Path(cache_dir)
        self._loader = loader
        self._model = None

    def load(self):
        if self._model is not None:
            return self._model
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        if self._loader is None:
            if not is_available("vector"):
                raise OptionalDependencyError("vector")
            from sentence_transformers import SentenceTransformer

            self._loader = SentenceTransformer
        self._model = self._loader(self.model_name, cache_folder=str(self.cache_dir))
        return self._model
