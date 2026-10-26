from datetime import datetime
from pathlib import Path

import pytest

from issuedoctor.compat import UTC
from issuedoctor.embedding.clustering import assign_clusters
from issuedoctor.embedding.encoder import CachedEncoder
from issuedoctor.embedding.hashing_tfidf import encode_texts
from issuedoctor.embedding.model_manager import EmbeddingModelManager
from issuedoctor.embedding.similarity import find_candidates, find_candidates_sparse
from issuedoctor.extensions import db
from issuedoctor.models import AnalysisRun, IssueSnapshot, Repository
from issuedoctor.services.embedding_service import EmbeddingService


def _require_numpy():
    """Skip tests for the dense model path when numpy is absent.

    Only numpy is required: the model path converts dense vectors to the shared
    sparse representation, which does not need scikit-learn.
    """
    pytest.importorskip("numpy", reason="稠密模型后端需要 numpy")


def _pretend_vector_capability_is_installed(monkeypatch):
    """Force capability detection to report the vector backend as available.

    Without this the encoder correctly falls back to the built-in backend
    whenever ``sentence-transformers`` is not installed, so the dense path could
    never be exercised in a minimal install.
    """
    monkeypatch.setattr("issuedoctor.capabilities._module_exists", lambda _name: True)


class FakeModel:
    """Stand-in for a sentence-transformers model returning dense vectors.

    numpy is imported lazily so the module still collects in a minimal install;
    the tests that use this fixture skip themselves when numpy is absent.
    """

    def __init__(self):
        self.calls = 0

    def encode(self, texts, **_kwargs):
        import numpy as np

        self.calls += 1
        return np.asarray([[len(text), text.count("a") + 1] for text in texts], dtype=np.float32)


def test_model_manager_loads_only_once(tmp_path: Path):
    calls = []

    def loader(model_name, cache_folder):
        calls.append((model_name, cache_folder))
        return FakeModel()

    manager = EmbeddingModelManager("test/model", tmp_path, loader=loader)

    assert manager.load() is manager.load()
    assert calls == [("test/model", str(tmp_path))]


def test_model_manager_reports_missing_capability_without_loader(monkeypatch):
    from issuedoctor import capabilities

    monkeypatch.setattr(capabilities, "_module_exists", lambda _name: False)
    manager = EmbeddingModelManager("test/model", "unused")
    try:
        manager.load()
    except capabilities.OptionalDependencyError as exc:
        assert exc.capability == "vector"
    else:  # pragma: no cover - only when sentence-transformers is installed
        pass


def test_cached_encoder_skips_model_on_second_run(app, tmp_path: Path, monkeypatch):
    _require_numpy()
    _pretend_vector_capability_is_installed(monkeypatch)
    model = FakeModel()
    manager = EmbeddingModelManager("test/model", tmp_path, loader=lambda *_a, **_k: model)

    with app.app_context():
        db.create_all()
        first = CachedEncoder(manager, "test/model", prefer_model=True).encode(["alpha", "beta"])
        second_manager = EmbeddingModelManager(
            "test/model",
            tmp_path,
            loader=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("downloaded")),
        )
        second = CachedEncoder(second_manager, "test/model", prefer_model=True).encode(
            ["alpha", "beta"]
        )

    assert model.calls == 1
    assert [v.values for v in first] == [v.values for v in second]


def test_cached_encoder_deduplicates_identical_text_within_batch(app, tmp_path: Path, monkeypatch):
    _require_numpy()
    _pretend_vector_capability_is_installed(monkeypatch)
    model = FakeModel()
    manager = EmbeddingModelManager("test/model", tmp_path, loader=lambda *_a, **_k: model)

    with app.app_context():
        db.create_all()
        vectors = CachedEncoder(manager, "test/model", prefer_model=True).encode(
            ["same", "same", "different"]
        )

    assert model.calls == 1
    assert len(vectors) == 3
    assert vectors[0].values == vectors[1].values


def test_encoder_defaults_to_builtin_backend_without_optional_dependency(tmp_path: Path):
    """The default path must not need a model at all."""
    manager = EmbeddingModelManager(
        "test/model",
        tmp_path,
        loader=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("model loaded")),
    )

    vectors = CachedEncoder(manager, "test/model").encode(["alpha", "beta"])

    assert len(vectors) == 2
    assert all(vector.values for vector in vectors)


def test_builtin_tfidf_similarity_fixture_is_stable_and_clustered():
    texts = [
        "server crashes when configuration is empty",
        "server crash when config is empty",
        "add dark mode to documentation",
    ]
    vectors = encode_texts(texts)
    first = assign_clusters(find_candidates_sparse([1, 2, 3], vectors, threshold=0.45))
    second = assign_clusters(find_candidates_sparse([1, 2, 3], vectors, threshold=0.45))

    assert first == second
    assert [(item.issue_a, item.issue_b) for item in first] == [(1, 2)]
    assert first[0].cluster_id == "cluster-1"


def test_similarity_accepts_sparse_vectors_through_generic_entry_point():
    vectors = encode_texts(["same crash text", "same crash text", "different matter"])

    result = find_candidates([10, 11, 12], vectors, threshold=0.9)

    assert len(result) == 1
    assert result[0].issue_a == 10
    assert result[0].issue_b == 11
    assert result[0].similarity == 1.0


def test_similarity_uses_upper_triangle_without_self_pairs():
    np = pytest.importorskip("numpy", reason="稠密后端需要 numpy")

    vectors = np.asarray([[1, 0], [1, 0], [0, 1]], dtype=np.float32)

    result = find_candidates([10, 11, 12], vectors, threshold=0.9)

    assert len(result) == 1
    assert result[0].issue_a == 10
    assert result[0].issue_b == 11
    assert result[0].similarity == 1.0


def test_candidate_threshold_is_backend_specific():
    """The two backends score on different scales and must not share a threshold."""
    from issuedoctor.services.embedding_service import _candidate_threshold

    config = {
        "dimensions": {
            "D6": {"metrics": {"M6.1": {"candidate_threshold": 0.82,
                                        "candidate_threshold_hashing": 0.28}}}
        }
    }
    assert _candidate_threshold(config, "embedding") == 0.82
    assert _candidate_threshold(config, "hashing") == 0.28


def test_candidate_threshold_falls_back_when_hashing_key_absent():
    from issuedoctor.services.embedding_service import _candidate_threshold

    config = {"dimensions": {"D6": {"metrics": {"M6.1": {"candidate_threshold": 0.82}}}}}
    assert _candidate_threshold(config, "hashing") == 0.82


def _seed_run(app, run_id: str, texts: list[str]):
    now = datetime.now(UTC)
    repository = Repository(
        owner="example",
        name="embedding",
        full_name="example/embedding",
        html_url="https://github.com/example/embedding",
    )
    db.session.add(repository)
    db.session.flush()
    run = AnalysisRun(
        id=run_id,
        repository_id=repository.id,
        status="RUNNING",
        mode="BASIC",
        progress_percent=65,
        current_stage="CALCULATING_METRICS",
        created_at=now,
        window_start=now,
        window_end=now,
        issue_limit=500,
        pr_limit=500,
        scoring_config_json={},
        analysis_config_json={},
    )
    db.session.add(run)
    for index, text in enumerate(texts, start=1):
        db.session.add(
            IssueSnapshot(
                analysis_run_id=run.id,
                issue_number=index,
                title=text,
                body_excerpt=text,
                body_hash=str(index) * 64,
                state="open",
                html_url=f"https://github.com/example/embedding/issues/{index}",
                author_login="user",
                author_association="NONE",
                created_at=now,
                updated_at=now,
                comments_count=0,
                labels_json=[],
                maintainer_response_found=False,
                linked_pr_numbers_json=[],
            )
        )
    db.session.commit()
    return run


def test_model_failure_degrades_to_builtin_backend_without_failing_analysis(app, monkeypatch):
    def fail_load(_self):
        raise OSError("offline")

    monkeypatch.setattr(EmbeddingModelManager, "load", fail_load)
    monkeypatch.setattr(
        "issuedoctor.capabilities._module_exists", lambda _name: True
    )  # pretend the capability is installed so the failure path is exercised
    with app.app_context():
        db.create_all()
        run = _seed_run(
            app,
            "00000000-0000-0000-0000-000000000003",
            ["server crashes with empty configuration", "server crashes with empty configuration"],
        )
        result = EmbeddingService().analyze(run)

    assert result.mode == "hashing"
    assert result.warning is not None
    assert len(result.candidates) == 1


def test_analysis_uses_builtin_backend_when_capability_absent(app, monkeypatch):
    """Without the vector capability the audit still detects duplicates.

    The texts below are near-identical, so they must be paired once the
    backend-specific threshold is applied.
    """
    monkeypatch.setattr("issuedoctor.capabilities._module_exists", lambda _name: False)
    with app.app_context():
        db.create_all()
        run = _seed_run(
            app,
            "00000000-0000-0000-0000-000000000004",
            [
                "server crashes when configuration is empty",
                "server crash when config is empty",
                "add dark mode to documentation",
            ],
        )
        result = EmbeddingService().analyze(run)

    assert result.mode == "hashing"
    assert result.warning is None
    assert result.threshold == 0.28
    assert [(item.issue_a, item.issue_b) for item in result.candidates] == [(1, 2)]


def test_identical_texts_are_detected_as_duplicates_in_minimal_install(app, monkeypatch):
    monkeypatch.setattr("issuedoctor.capabilities._module_exists", lambda _name: False)
    with app.app_context():
        db.create_all()
        run = _seed_run(
            app,
            "00000000-0000-0000-0000-000000000005",
            ["identical issue text about a crash"] * 2 + ["another unrelated issue"],
        )
        result = EmbeddingService().analyze(run)

    assert result.mode == "hashing"
    assert [(item.issue_a, item.issue_b) for item in result.candidates] == [(1, 2)]


# --------------------------------------------------------------------------
# Vector cache persistence
#
# The cache stores dense model vectors. Its previous implementation used
# numpy.save, which made this module unimportable without numpy. It now uses a
# self-describing binary format, so these tests run in a minimal install.
# --------------------------------------------------------------------------


def test_embedding_cache_round_trips_through_the_database(app):
    from issuedoctor.repositories.cache_repo import EmbeddingCacheRepository

    vector = [0.1, -0.25, 0.0, 0.3333333, 1.0]
    with app.app_context():
        db.create_all()
        assert EmbeddingCacheRepository.get("hash-a", "test/model") is None
        EmbeddingCacheRepository.set("hash-a", "test/model", vector)
        restored = EmbeddingCacheRepository.get("hash-a", "test/model")

    assert restored is not None
    assert len(restored) == len(vector)
    for expected, actual in zip(vector, restored, strict=True):
        assert abs(expected - actual) < 1e-6


def test_embedding_cache_is_keyed_by_model_name(app):
    from issuedoctor.repositories.cache_repo import EmbeddingCacheRepository

    with app.app_context():
        db.create_all()
        EmbeddingCacheRepository.set("same-hash", "model-a", [1.0, 2.0])
        EmbeddingCacheRepository.set("same-hash", "model-b", [3.0, 4.0])

        first = EmbeddingCacheRepository.get("same-hash", "model-a")
        second = EmbeddingCacheRepository.get("same-hash", "model-b")

    assert [round(v, 3) for v in first] == [1.0, 2.0]
    assert [round(v, 3) for v in second] == [3.0, 4.0]


def test_embedding_cache_overwrites_existing_entry(app):
    from issuedoctor.repositories.cache_repo import EmbeddingCacheRepository

    with app.app_context():
        db.create_all()
        EmbeddingCacheRepository.set("hash-b", "test/model", [1.0, 1.0])
        EmbeddingCacheRepository.set("hash-b", "test/model", [9.0, 9.0])
        restored = EmbeddingCacheRepository.get("hash-b", "test/model")

    assert [round(v, 3) for v in restored] == [9.0, 9.0]


def test_embedding_cache_handles_empty_vector(app):
    from issuedoctor.repositories.cache_repo import EmbeddingCacheRepository

    with app.app_context():
        db.create_all()
        EmbeddingCacheRepository.set("hash-empty", "test/model", [])
        restored = EmbeddingCacheRepository.get("hash-empty", "test/model")

    assert restored == []


def test_embedding_cache_returns_none_for_unknown_key(app):
    from issuedoctor.repositories.cache_repo import EmbeddingCacheRepository

    with app.app_context():
        db.create_all()
        assert EmbeddingCacheRepository.get("missing", "test/model") is None


def test_embedding_cache_ignores_corrupt_payload(app):
    """A truncated or foreign blob must not raise; the entry is treated as a miss."""
    from issuedoctor.extensions import db as _db
    from issuedoctor.models import EmbeddingCache
    from issuedoctor.repositories.cache_repo import EmbeddingCacheRepository

    with app.app_context():
        db.create_all()
        _db.session.add(
            EmbeddingCache(
                text_hash="corrupt",
                model_name="test/model",
                vector=b"\x00\x01\x02",
                metadata_json={},
            )
        )
        _db.session.commit()

        assert EmbeddingCacheRepository.get("corrupt", "test/model") is None


def test_legacy_numpy_vectors_remain_readable(app):
    """Vectors written by the previous numpy-based implementation still load."""
    np = pytest.importorskip("numpy", reason="读取旧格式需要 numpy")

    import io

    from issuedoctor.extensions import db as _db
    from issuedoctor.models import EmbeddingCache
    from issuedoctor.repositories.cache_repo import EmbeddingCacheRepository

    buffer = io.BytesIO()
    np.save(buffer, np.asarray([0.5, 0.25, 0.125], dtype=np.float32), allow_pickle=False)

    with app.app_context():
        db.create_all()
        _db.session.add(
            EmbeddingCache(
                text_hash="legacy",
                model_name="test/model",
                vector=buffer.getvalue(),
                metadata_json={},
            )
        )
        _db.session.commit()

        restored = EmbeddingCacheRepository.get("legacy", "test/model")

    assert restored is not None
    assert [round(v, 3) for v in restored] == [0.5, 0.25, 0.125]
