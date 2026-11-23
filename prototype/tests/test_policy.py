"""Unit tests for the fail-safe policy (PRD F3, F4, F5)."""
from kidguard.policy import StableLabel, classify, profile_for


def test_no_face_is_none():
    """No faces in frame gives 'none'."""
    assert classify([]) == "none"


def test_unknown_wins_over_adult():
    """An unknown face next to an adult still gives 'unknown' (fail-safe)."""
    assert classify(["adult", None]) == "unknown"


def test_child_wins_over_adult():
    """A child next to an adult gives 'child' (PRD F4)."""
    assert classify(["adult", "child"]) == "child"


def test_adult_only():
    """Only adults in frame gives 'adult'."""
    assert classify(["adult", "adult"]) == "adult"


def test_only_adult_gets_normal_profile():
    """Only the 'adult' label maps to the normal profile; all others are strict (PRD F3)."""
    assert profile_for("adult") == "normal"
    assert all(profile_for(x) == "strict" for x in ("child", "unknown", "none", "error", ""))


def test_smoother_starts_locked_and_needs_a_run_to_unlock():
    """The smoother stays strict until enough consecutive adult frames arrive (PRD F5)."""
    s = StableLabel(unlock_frames=3)
    assert [s.update("adult") for _ in range(3)] == ["none", "none", "adult"]


def test_smoother_locks_immediately():
    """Any non-adult frame locks instantly and resets the unlock counter."""
    s = StableLabel(unlock_frames=2)
    s.update("adult")
    s.update("adult")
    assert s.update("unknown") == "unknown"
    assert s.update("adult") == "unknown"
    assert s.update("adult") == "adult"


def test_flicker_does_not_unlock():
    """Alternating adult and none frames never unlocks the normal profile."""
    s = StableLabel(unlock_frames=3)
    assert all(s.update(x) != "adult" for x in ["adult", "none"] * 10)
