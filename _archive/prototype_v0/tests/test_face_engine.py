"""Unit tests for matching math, threshold logic and the fail-safe classifier (no camera needed)."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
from face_engine import StableLabel, best_match, classify, cosine_similarity, profile_for  # noqa: E402


def test_stable_label_starts_locked_and_needs_run_to_unlock():
    """The smoother stays strict until enough consecutive adult frames arrive."""
    s = StableLabel(unlock_frames=3)
    assert [s.update("adult") for _ in range(3)] == ["none", "none", "adult"]


def test_stable_label_locks_immediately():
    """Any non-adult frame locks instantly and resets the unlock counter."""
    s = StableLabel(unlock_frames=2)
    s.update("adult"), s.update("adult")
    assert s.update("unknown") == "unknown"
    assert s.update("adult") == "unknown"


def vec(*vals):
    """Builds a float32 vector from the given values."""
    return np.array(vals, dtype=np.float32)


def test_cosine_identical_is_one():
    """Identical vectors have similarity 1."""
    assert abs(cosine_similarity(vec(1, 2, 3), vec(1, 2, 3)) - 1.0) < 1e-6


def test_cosine_orthogonal_is_zero():
    """Orthogonal vectors have similarity 0."""
    assert abs(cosine_similarity(vec(1, 0), vec(0, 1))) < 1e-6


def test_cosine_zero_vector_is_zero():
    """A zero vector never divides by zero and scores 0."""
    assert cosine_similarity(vec(0, 0), vec(1, 1)) == 0.0


def test_best_match_picks_closest_above_threshold():
    """The closest enrolled template wins when it clears the threshold."""
    t = {"dad": {"role": "adult", "embeddings": [vec(1, 0)]}, "kid": {"role": "child", "embeddings": [vec(0, 1)]}}
    name, role, score = best_match(vec(0.1, 1), t, threshold=0.5)
    assert (name, role) == ("kid", "child") and score > 0.9


def test_best_match_below_threshold_is_unknown():
    """A face that matches nobody well returns no name and no role."""
    t = {"dad": {"role": "adult", "embeddings": [vec(1, 0)]}}
    name, role, _ = best_match(vec(0, 1), t, threshold=0.5)
    assert name is None and role is None


def test_best_match_no_templates_is_unknown():
    """With nobody enrolled, every face is unknown."""
    assert best_match(vec(1, 0), {}, 0.5)[0] is None


def test_classify_no_face_is_none():
    """No faces in frame gives 'none'."""
    assert classify([]) == "none"


def test_classify_unknown_wins_over_adult():
    """An unknown face next to an adult still gives 'unknown' (fail-safe)."""
    assert classify(["adult", None]) == "unknown"


def test_classify_child_wins_over_adult():
    """A child next to an adult gives 'child' (strictest known role)."""
    assert classify(["adult", "child"]) == "child"


def test_classify_adult_only():
    """Only adults in frame gives 'adult'."""
    assert classify(["adult"]) == "adult"


def test_profile_only_adult_is_normal():
    """Only the 'adult' label gets the normal profile; all others are strict."""
    assert profile_for("adult") == "normal"
    assert all(profile_for(x) == "strict" for x in ("child", "unknown", "none"))
