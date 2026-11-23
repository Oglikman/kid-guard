"""Tests for how run.label_frame combines identity and liveness (PRD F13), using stand-ins for the camera and models."""
import numpy as np

from kidguard.liveness import SmootherBank
from run import label_frame

TEMPLATES = {"Oran": {"role": "adult", "embeddings": [[1.0, 0.0]]}, "Sam": {"role": "child", "embeddings": [[0.0, 1.0]]}}


class FakeEngine:
    """Detects one fixed face per frame and returns a chosen embedding."""

    def __init__(self, embedding, faces=1):
        """Stores the embedding to return and how many faces to pretend to see."""
        self.embedding, self.faces = np.array(embedding, dtype=np.float32), faces

    def detect(self, frame):
        """Returns the configured number of identical face rows."""
        return [np.array([10, 10, 50, 50, 0.99])] * self.faces

    def embed(self, frame, face):
        """Returns the configured embedding."""
        return self.embedding


class FakeLiveness:
    """Returns a scripted liveness score per call and counts how many times it was asked."""

    def __init__(self, score):
        """Stores the score to report."""
        self.s, self.calls = score, 0

    def score(self, frame, face):
        """Returns the scripted fused score."""
        self.calls += 1
        return {"fused": self.s, "per_model": [self.s]}


def run_frames(engine, liveness, n, bank=None):
    """Runs n frames through label_frame and returns the list of raw labels."""
    bank = bank or (SmootherBank(0.5) if liveness is not None else None)
    return [label_frame(engine, None, TEMPLATES, 0.5, liveness, bank)[0] for _ in range(n)]


def test_adult_who_fails_liveness_is_unknown():
    """A photo-like adult (high identity match, low liveness) is never labelled adult."""
    labels = run_frames(FakeEngine([1, 0]), FakeLiveness(0.05), 6)
    assert set(labels) == {"unknown"}


def test_adult_who_passes_liveness_becomes_adult_after_min_frames():
    """A live adult is labelled unknown for the first frames, then adult once enough live frames are seen."""
    labels = run_frames(FakeEngine([1, 0]), FakeLiveness(0.95), 5)
    assert labels[:2] == ["unknown", "unknown"] and labels[2:] == ["adult", "adult", "adult"]


def test_child_is_child_and_liveness_is_not_run():
    """A child needs no liveness (strict applies anyway), so the model is not even called."""
    fake = FakeLiveness(0.0)
    assert set(run_frames(FakeEngine([0, 1]), fake, 3)) == {"child"} and fake.calls == 0


def test_without_liveness_adult_unlocks_immediately():
    """With liveness disabled (development flag) an adult is labelled adult at once."""
    assert run_frames(FakeEngine([1, 0]), None, 1) == ["adult"]


def test_stranger_is_unknown_and_skips_liveness():
    """An unmatched face is unknown and does not trigger the liveness model."""
    fake = FakeLiveness(0.95)
    assert set(run_frames(FakeEngine([-1, -1]), fake, 3)) == {"unknown"} and fake.calls == 0


def test_adult_leaving_view_must_prove_liveness_again():
    """After the adult disappears for a frame, their liveness history is cleared and they start from unknown again."""
    bank, fake = SmootherBank(0.5), FakeLiveness(0.95)
    assert run_frames(FakeEngine([1, 0]), fake, 4, bank)[-1] == "adult"
    label_frame(FakeEngine([1, 0], faces=0), None, TEMPLATES, 0.5, fake, bank)   # nobody in view for one frame
    assert run_frames(FakeEngine([1, 0]), fake, 1, bank) == ["unknown"]


def test_results_carry_live_score_for_overlay():
    """Each result includes the liveness score for adults, and None otherwise."""
    _, res = label_frame(FakeEngine([1, 0]), None, TEMPLATES, 0.5, FakeLiveness(0.9), SmootherBank(0.5))
    assert res[0][3] == 0.9
    _, res = label_frame(FakeEngine([0, 1]), None, TEMPLATES, 0.5, FakeLiveness(0.9), SmootherBank(0.5))
    assert res[0][3] is None
