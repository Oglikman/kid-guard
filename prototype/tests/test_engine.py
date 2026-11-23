"""Unit tests for embedding comparison and matching (no camera needed)."""
import numpy as np

from kidguard.engine import best_match, cosine_similarity, top_match


def vec(*vals):
    """Builds a float32 vector from the given values."""
    return np.array(vals, dtype=np.float32)


TEMPLATES = {"dad": {"role": "adult", "embeddings": [vec(1, 0)]}, "kid": {"role": "child", "embeddings": [vec(0, 1)]}}


def test_cosine_identical_is_one():
    """Identical vectors have similarity 1."""
    assert abs(cosine_similarity(vec(1, 2, 3), vec(1, 2, 3)) - 1.0) < 1e-6


def test_cosine_orthogonal_is_zero():
    """Orthogonal vectors have similarity 0."""
    assert abs(cosine_similarity(vec(1, 0), vec(0, 1))) < 1e-6


def test_cosine_zero_vector_is_zero():
    """A zero vector does not divide by zero and scores 0."""
    assert cosine_similarity(vec(0, 0), vec(1, 1)) == 0.0


def test_top_match_ignores_threshold():
    """top_match returns the closest person even when the score is low."""
    name, role, score = top_match(vec(1, 0.1), TEMPLATES)
    assert (name, role) == ("dad", "adult") and score > 0.9


def test_top_match_nobody_enrolled():
    """With no templates, top_match returns no name and a score of -1."""
    assert top_match(vec(1, 0), {}) == (None, None, -1.0)


def test_best_match_accepts_above_threshold():
    """The closest template wins when its score clears the threshold."""
    name, role, _ = best_match(vec(0.1, 1), TEMPLATES, 0.5)
    assert (name, role) == ("kid", "child")


def test_best_match_rejects_below_threshold():
    """A face below the threshold returns no name and no role."""
    name, role, _ = best_match(vec(1, 1), {"dad": {"role": "adult", "embeddings": [vec(1, -1)]}}, 0.5)
    assert name is None and role is None


def test_best_match_threshold_boundary_is_inclusive():
    """A score exactly equal to the threshold is accepted."""
    assert best_match(vec(1, 0), TEMPLATES, 1.0)[0] == "dad"
