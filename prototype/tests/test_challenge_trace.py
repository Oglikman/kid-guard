"""Tests that a measured head-turn attempt records the head position of every frame, using a fake camera and engine."""
import numpy as np

import evaluate
from kidguard import config


class FakeCamera:
    """Returns a blank frame every time it is read."""

    def read(self):
        """Returns a successful read of a black image."""
        return True, np.zeros((240, 320, 3), dtype=np.uint8)


class FakeEngine:
    """Reports one scripted face per frame, where None means no face was found."""

    def __init__(self, yaws):
        """Stores the yaw values to show, one per detect call."""
        self.yaws = iter(yaws)

    def detect(self, frame):
        """Returns a YuNet-style row for the next scripted yaw, or no faces."""
        y = next(self.yaws)
        if y is None:
            return []
        return [np.array([10, 10, 50, 50, 80, 100, 120, 100, 100 + 40 * y, 120, 85, 140, 115, 140, 0.99], dtype=np.float64)]


def test_attempt_record_keeps_every_frame(monkeypatch):
    """The record holds time, yaw (None when no face) and phase for each frame, plus the neutral-frame rule it was measured under."""
    monkeypatch.setattr(evaluate.cv2, "imshow", lambda *a: None)
    monkeypatch.setattr(evaluate.cv2, "waitKey", lambda *a: -1)
    monkeypatch.setattr(evaluate, "HeadTurnChallenge", lambda: __import__("kidguard.challenge").challenge.HeadTurnChallenge(lambda: "left"))
    rec = evaluate.run_one_challenge_attempt(FakeEngine([0.0, None, 0.4, 0.4, 0.4]), FakeCamera(), {}, None, 0.0, "1/1")
    assert rec["passed"] is True
    assert [row[1] for row in rec["trace"]] == [0.0, None, 0.4, 0.4, 0.4]
    assert [row[2] for row in rec["trace"]] == ["turn"] * 5
    times = [row[0] for row in rec["trace"]]
    assert times == sorted(times)
    assert rec["neutral_frames_required"] == config.CHALLENGE_NEUTRAL_FRAMES
