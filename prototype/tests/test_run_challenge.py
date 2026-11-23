"""Tests for how run.label_frame combines identity, liveness and the head-turn challenge (PRD F13, F14), using stand-ins for camera and models."""
import numpy as np

from kidguard.challenge import ChallengeBank
from kidguard.liveness import SmootherBank
from run import label_frame

TEMPLATES = {"Oran": {"role": "adult", "embeddings": [[1.0, 0.0]]}, "Sam": {"role": "child", "embeddings": [[0.0, 1.0]]}}


def face_row(yaw: float) -> np.ndarray:
    """Builds a 15-value YuNet-style row (box, 5 landmarks, score) whose nose is offset by `yaw` eye-distances."""
    return np.array([10, 10, 50, 50, 80, 100, 120, 100, 100 + 40 * yaw, 120, 85, 140, 115, 140, 0.99], dtype=np.float64)


class FakeEngine:
    """Shows a scripted list of (embedding, yaw) faces each frame and returns the embedding that belongs to each row."""

    def __init__(self):
        """Starts with no faces in view."""
        self.faces = []

    def show(self, *faces):
        """Sets the faces in view for the next frame, each as (embedding, yaw)."""
        self.faces = list(faces)

    def detect(self, frame):
        """Returns one landmark row per face in view, tagging each row with its index in an extra attribute list."""
        return [face_row(y) for _, y in self.faces]

    def embed(self, frame, row):
        """Returns the embedding of the face whose yaw matches this row's nose position."""
        yaw = (row[8] - 100) / 40
        return next(np.array(e, dtype=np.float32) for e, y in self.faces if abs(y - yaw) < 1e-6)


class FakeLiveness:
    """Always reports a high 'real' score, as a good photo would."""

    def score(self, frame, face):
        """Returns a high fused score."""
        return {"fused": 0.95, "per_model": [0.95]}


ADULT, CHILD = [1, 0], [0, 1]


def setup():
    """Returns a fresh engine, liveness stand-in, liveness bank and challenge bank that always asks for a left turn."""
    return FakeEngine(), FakeLiveness(), SmootherBank(0.5), ChallengeBank(lambda: "left")


def run(engine, live, bank, ch, yaws, t0=0.0):
    """Shows a lone adult with each yaw in turn and returns the raw labels (frames 0.1 s apart)."""
    out = []
    for i, y in enumerate(yaws):
        engine.show((ADULT, y))
        out.append(label_frame(engine, None, TEMPLATES, 0.5, live, bank, ch, t0 + 0.1 * i)[0])
    return out


def test_still_photo_that_fools_liveness_stays_unknown():
    """A face with high liveness and high identity match but no head movement is never labelled adult."""
    engine, live, bank, ch = setup()
    assert set(run(engine, live, bank, ch, [0.0] * 100)) == {"unknown"}


def test_adult_who_turns_the_requested_way_unlocks():
    """An adult who faces the camera and then turns left is labelled unknown until the challenge completes, then adult."""
    engine, live, bank, ch = setup()
    labels = run(engine, live, bank, ch, [0.0] * 4 + [0.4] * 4)
    assert labels[:5] == ["unknown"] * 5 and labels[-1] == "adult"


def test_child_present_drops_the_adult_pass():
    """After an adult has passed, a frame with a child also in view releases the pass, so the adult must do the challenge again."""
    engine, live, bank, ch = setup()
    assert run(engine, live, bank, ch, [0.0] * 4 + [0.4] * 4)[-1] == "adult"
    engine.show((ADULT, 0.0), (CHILD, 0.05))
    raw, _ = label_frame(engine, None, TEMPLATES, 0.5, live, bank, ch, 1.0)
    assert raw == "child"
    assert run(engine, live, bank, ch, [0.0], t0=1.1) == ["unknown"]


def test_two_adults_do_not_release_each_other():
    """Two enrolled adults in view together do not drop each other's challenge progress."""
    engine, live, bank, ch = setup()
    templates = dict(TEMPLATES, Dana={"role": "adult", "embeddings": [[0.0, -1.0]]})
    for i, (y1, y2) in enumerate([(0.0, 0.02)] * 4 + [(0.4, 0.42)] * 4):
        engine.show((ADULT, y1), ([0, -1], y2))
        raw, _ = label_frame(engine, None, templates, 0.5, live, bank, ch, 0.1 * i)
    assert raw == "adult"


def test_no_challenge_object_keeps_the_old_behaviour():
    """With challenge=None (development flag) an adult who passes liveness is labelled adult without any head turn."""
    engine, live, bank, _ = setup()
    labels = [label_frame((engine.show((ADULT, 0.0)), engine)[1], None, TEMPLATES, 0.5, live, bank, None)[0] for _ in range(5)]
    assert labels[-1] == "adult"
