"""Tests for the dependency-free hashing TF-IDF backend.

These tests must pass in a minimal installation, i.e. with numpy and
scikit-learn absent. They therefore assert pure-Python behaviour only.
"""

import math

from issuedoctor.embedding.hashing_tfidf import (
    DEFAULT_DIMENSIONS,
    SparseVector,
    cosine_similarity,
    encode_texts,
    similarity_pairs,
)


def test_encode_empty_input_returns_empty_list():
    assert encode_texts([]) == []


def test_vectors_are_l2_normalised():
    vectors = encode_texts(["server crashes when configuration is empty"])
    assert len(vectors) == 1
    norm = math.sqrt(sum(value * value for value in vectors[0].values.values()))
    assert math.isclose(norm, 1.0, rel_tol=1e-6)


def test_identical_texts_produce_identical_vectors():
    vectors = encode_texts(["same text", "same text"])
    assert vectors[0].values == vectors[1].values
    assert cosine_similarity(vectors[0], vectors[1]) == 1.0


def test_results_are_deterministic_across_calls():
    texts = ["server crash", "server crashes", "unrelated topic entirely"]
    first = encode_texts(texts)
    second = encode_texts(texts)
    assert [v.values for v in first] == [v.values for v in second]


def test_similar_texts_score_higher_than_unrelated_ones():
    texts = [
        "server crashes when configuration is empty",
        "server crash when config is empty",
        "add dark mode to documentation",
    ]
    vectors = encode_texts(texts)
    related = cosine_similarity(vectors[0], vectors[1])
    unrelated = cosine_similarity(vectors[0], vectors[2])
    assert related > unrelated
    assert 0.0 <= unrelated <= 1.0


def test_similarity_pairs_finds_expected_cluster():
    texts = [
        "server crashes when configuration is empty",
        "server crash when config is empty",
        "add dark mode to documentation",
    ]
    vectors = encode_texts(texts)
    pairs = similarity_pairs([1, 2, 3], vectors, threshold=0.45)

    assert pairs
    found = {(a, b) for a, b, _score in pairs}
    assert (1, 2) in found
    assert (1, 3) not in found and (2, 3) not in found


def test_similarity_pairs_is_sorted_and_deduplicated():
    vectors = encode_texts(["alpha beta", "alpha beta", "alpha beta"])
    pairs = similarity_pairs([1, 2, 3], vectors, threshold=0.5)

    # Every unordered pair appears at most once.
    assert len(pairs) == len({(a, b) for a, b, _ in pairs})
    scores = [score for _a, _b, score in pairs]
    assert scores == sorted(scores, reverse=True)


def test_similarity_pairs_returns_empty_for_single_issue():
    vectors = encode_texts(["only one issue"])
    assert similarity_pairs([1], vectors, threshold=0.1) == []


def test_similarity_pairs_validates_length_mismatch():
    vectors = encode_texts(["a b c"])
    try:
        similarity_pairs([1, 2], vectors, threshold=0.5)
    except ValueError as exc:
        assert "长度" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")


def test_empty_and_whitespace_texts_are_handled():
    vectors = encode_texts(["", "   ", "real text here"])
    assert vectors[0].values == {}
    assert vectors[1].values == {}
    assert cosine_similarity(vectors[0], vectors[2]) == 0.0


def test_short_text_below_ngram_minimum_still_vectorises():
    vectors = encode_texts(["a"])
    assert vectors[0].values  # single character still yields a bucket


def test_cosine_similarity_of_empty_vector_is_zero():
    assert cosine_similarity(SparseVector({}), SparseVector({1: 1.0})) == 0.0


def test_custom_dimensions_are_respected():
    vectors = encode_texts(["some text"], dimensions=64)
    assert all(0 <= bucket < 64 for bucket in vectors[0].values)


def test_default_dimensions_constant_is_positive():
    assert DEFAULT_DIMENSIONS > 0
