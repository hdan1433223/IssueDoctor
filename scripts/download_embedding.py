import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from issuedoctor.config import Config  # noqa: E402
from issuedoctor.embedding.model_manager import EmbeddingModelManager  # noqa: E402
from issuedoctor.services.config_service import load_yaml  # noqa: E402


def main() -> None:
    config = load_yaml(Config.ANALYSIS_CONFIG_PATH)
    model_name = config["embedding_model"]
    model_dir = Path(Config.DATA_DIR) / "models"
    EmbeddingModelManager(model_name, model_dir).load()
    print(f"Embedding 已缓存：{model_name} -> {model_dir}")


if __name__ == "__main__":
    main()
