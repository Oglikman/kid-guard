"""Unit tests for liveness preprocessing, scoring maths, smoothing, metrics and saved settings."""
import numpy as np
import pytest

from kidguard import config
from kidguard.liveness import (INPUT_SIZE, LivenessModel, LivenessSmoother, SmootherBank, crop_face, preprocess,
                               real_probability, softmax)
from kidguard.metrics import liveness_summary, suggest_liveness_threshold


def test_softmax_sums_to_one_and_is_stable_for_large_logits():
    """Softmax rows sum to 1 and large logits do not overflow."""
    p = softmax([[1000.0, 1001.0, 999.0]])
    assert np.isfinite(p).all() and abs(float(p.sum()) - 1.0) < 1e-9


def test_real_probability_uses_class_index_1():
    """The 'real' probability is the middle (index 1) class of the 3-way output."""
    assert real_probability([[0.0, 10.0, 0.0]]) > 0.99
    assert real_probability([[10.0, 0.0, 0.0]]) < 0.01


def test_preprocess_shape_dtype_and_no_normalisation():
    """Preprocessing gives a (1, 3, H, W) float32 blob that keeps 0-255 values in BGR channel order."""
    img = np.zeros((80, 80, 3), np.uint8)
    img[..., 0], img[..., 1], img[..., 2] = 10, 20, 255
    blob = preprocess(img)
    assert blob.shape == (1, 3, 80, 80) and blob.dtype == np.float32
    assert blob[0, 0, 0, 0] == 10 and blob[0, 1, 0, 0] == 20 and blob[0, 2, 0, 0] == 255


def test_crop_face_output_size_and_content_region():
    """The crop is resized to the requested size and is taken around the box centre."""
    img = np.zeros((200, 300, 3), np.uint8)
    img[80:120, 130:170] = 255                      # bright square exactly at the box
    out = crop_face(img, (130, 80, 40, 40), 2.0, 80, 80)
    assert out.shape == (80, 80, 3)
    assert out[40, 40].min() == 255 and out[0, 0].max() == 0     # centre bright, corner dark


def test_crop_face_near_edge_is_clamped_and_never_raises():
    """A box touching the image corner with a large scale is clamped to the image instead of failing."""
    img = np.full((100, 100, 3), 7, np.uint8)
    assert crop_face(img, (0, 0, 60, 60), 4.0, 80, 80).shape == (80, 80, 3)
    assert crop_face(img, (90, 90, 10, 10), 4.0, 80, 80).shape == (80, 80, 3)


def test_crop_face_rejects_empty_box():
    """A zero-sized box is rejected with ValueError."""
    with pytest.raises(ValueError):
        crop_face(np.zeros((50, 50, 3), np.uint8), (5, 5, 0, 10), 2.7, 80, 80)


def test_smoother_needs_min_frames():
    """No decision of 'live' is possible before the minimum number of frames."""
    s = LivenessSmoother(threshold=0.5, window=5, min_frames=3)
    assert [s.update(0.99) for _ in range(3)] == [False, False, True]


def test_smoother_one_good_frame_does_not_unlock():
    """A single high score among low ones does not make the person live."""
    s = LivenessSmoother(threshold=0.5, window=5, min_frames=3)
    assert not any(s.update(x) for x in [0.1, 0.1, 0.1, 0.99, 0.1])


def test_smoother_drops_to_not_live_when_scores_fall():
    """After enough low scores the mean falls below the threshold and the person is no longer live."""
    s = LivenessSmoother(threshold=0.5, window=3, min_frames=3)
    for _ in range(3):
        s.update(0.9)
    assert [s.update(0.0) for _ in range(3)][-1] is False


def test_bank_forgets_people_who_left_view():
    """A person who leaves view must re-prove liveness from scratch when they return."""
    b = SmootherBank(0.5)
    for _ in range(4):
        b.update("Oran", 0.95)
    assert b.update("Oran", 0.95) is True
    b.keep_only([])
    assert b.update("Oran", 0.95) is False


def test_liveness_summary_rates():
    """Spoof-accepted and live-rejected rates are computed per frame at the threshold."""
    recs = [{"kind": "live", "fused": 0.9}, {"kind": "live", "fused": 0.3}, {"kind": "spoof", "fused": 0.6}, {"kind": "spoof", "fused": 0.1}]
    s = liveness_summary(recs, 0.5)
    assert s["spoof_accepted"] == 0.5 and s["live_rejected"] == 0.5


def test_liveness_summary_no_data():
    """Rates are None when there are no frames of that kind."""
    assert liveness_summary([], 0.5)["spoof_accepted"] is None


def test_suggest_liveness_threshold():
    """The suggestion sits just above the highest spoof score, is capped at 0.99, and needs spoof data."""
    assert suggest_liveness_threshold([{"kind": "spoof", "fused": 0.4}, {"kind": "live", "fused": 0.9}]) == 0.42
    assert suggest_liveness_threshold([{"kind": "spoof", "fused": 0.995}]) == 0.99
    assert suggest_liveness_threshold([{"kind": "live", "fused": 0.9}]) is None


def test_settings_keep_both_thresholds(tmp_path):
    """Saving one threshold does not erase the other, and each falls back to its default when unset."""
    p = tmp_path / "s.json"
    assert config.load_threshold(p) == config.DEFAULT_THRESHOLD and config.load_liveness_threshold(p) == config.DEFAULT_LIVENESS_THRESHOLD
    config.save_threshold(0.45, p)
    config.save_liveness_threshold(0.8, p)
    assert config.load_threshold(p) == 0.45 and config.load_liveness_threshold(p) == 0.8
    config.save_threshold(0.5, p)
    assert config.load_liveness_threshold(p) == 0.8


@pytest.mark.skipif(not all((config.MODELS_DIR / f).exists() for f in ("MiniFASNetV2.onnx", "MiniFASNetV1SE.onnx")), reason="models not downloaded")
def test_real_models_run_and_return_probabilities():
    """The downloaded models load in OpenCV and return per-model and fused probabilities in [0, 1] for a synthetic frame."""
    frame = np.random.RandomState(1).randint(0, 255, (480, 640, 3)).astype(np.uint8)
    out = LivenessModel().score(frame, [250, 150, 120, 150, 0.99])
    assert len(out["per_model"]) == 2 and all(0.0 <= p <= 1.0 for p in out["per_model"]) and 0.0 <= out["fused"] <= 1.0
    assert INPUT_SIZE == 80
