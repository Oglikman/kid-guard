"""Liveness (anti-spoofing): two MiniFASNet models judge whether a face is a real person or a photo/screen (PRD F13).

Preprocessing and output convention follow github.com/yakhyo/face-anti-spoofing (onnx_inference.py / utils.py):
crop the face box enlarged by a per-model scale, resize to 80x80, keep BGR and 0-255 values, softmax over 3 classes, index 1 = real.
"""
from __future__ import annotations

from collections import deque
from pathlib import Path

import numpy as np

from . import config

MODEL_SPECS = (("MiniFASNetV2.onnx", 2.7), ("MiniFASNetV1SE.onnx", 4.0))   # (file, crop scale)
INPUT_SIZE = 80
REAL_INDEX = 1


def crop_face(image, bbox, scale: float, out_w: int, out_h: int):
    """Crops the face box (x, y, w, h) enlarged by `scale` (limited so it fits the image), clamps it to the image and resizes it."""
    import cv2

    x, y, box_w, box_h = (float(v) for v in bbox)
    if box_w <= 0 or box_h <= 0:
        raise ValueError("face box must have positive width and height")
    src_h, src_w = image.shape[:2]
    scale = min((src_h - 1) / box_h, (src_w - 1) / box_w, scale)
    new_w, new_h = box_w * scale, box_h * scale
    cx, cy = x + box_w / 2, y + box_h / 2
    x1, y1 = max(0, int(cx - new_w / 2)), max(0, int(cy - new_h / 2))
    x2, y2 = min(src_w - 1, int(cx + new_w / 2)), min(src_h - 1, int(cy + new_h / 2))
    return cv2.resize(image[y1:y2 + 1, x1:x2 + 1], (out_w, out_h))


def preprocess(face_bgr) -> np.ndarray:
    """Converts a cropped BGR face (H, W, 3) to a float32 blob (1, 3, H, W) in the 0-255 range, with no normalisation."""
    return np.expand_dims(np.transpose(face_bgr.astype(np.float32), (2, 0, 1)), axis=0)


def softmax(logits) -> np.ndarray:
    """Returns the softmax of a logits array along its last axis."""
    z = np.asarray(logits, dtype=np.float64)
    e = np.exp(z - z.max(axis=-1, keepdims=True))
    return e / e.sum(axis=-1, keepdims=True)


def real_probability(logits) -> float:
    """Returns the probability that the model's output means a real face (class index 1)."""
    return float(softmax(logits).reshape(-1)[REAL_INDEX])


class LivenessModel:
    """Runs both MiniFASNet models on a detected face and fuses their 'real' probabilities by averaging."""

    def __init__(self, models_dir: Path = config.MODELS_DIR) -> None:
        """Loads both ONNX models with OpenCV, raising a clear error if they have not been downloaded."""
        import cv2

        self.nets = []
        for fname, scale in MODEL_SPECS:
            path = Path(models_dir) / fname
            if not path.exists():
                raise FileNotFoundError(f"{fname} missing; run: py fetch_models.py")
            self.nets.append((cv2.dnn.readNetFromONNX(str(path)), scale))

    def score(self, frame, face_row) -> dict:
        """Returns {'fused': mean real probability, 'per_model': [..]} for one detected face (YuNet row: x, y, w, h, ...)."""
        bbox = tuple(float(v) for v in face_row[:4])
        per_model = []
        for net, scale in self.nets:
            net.setInput(preprocess(crop_face(frame, bbox, scale, INPUT_SIZE, INPUT_SIZE)))
            per_model.append(real_probability(net.forward()))
        return {"fused": float(np.mean(per_model)), "per_model": per_model}


class LivenessSmoother:
    """Averages recent liveness scores so a single noisy frame cannot unlock or lock the adult profile."""

    def __init__(self, threshold: float, window: int = config.LIVENESS_WINDOW, min_frames: int = config.LIVENESS_MIN_FRAMES) -> None:
        """Creates an empty smoother that needs `min_frames` scores before it can ever say 'live'."""
        self.threshold, self.min_frames = threshold, min_frames
        self.scores: deque = deque(maxlen=window)

    def update(self, score: float) -> bool:
        """Adds one frame's score and returns True only if enough frames have been seen and their mean reaches the threshold."""
        self.scores.append(score)
        return len(self.scores) >= self.min_frames and float(np.mean(self.scores)) >= self.threshold

    def mean(self):
        """Returns the current mean score, or None if no frames have been seen."""
        return float(np.mean(self.scores)) if self.scores else None


class SmootherBank:
    """Keeps one LivenessSmoother per enrolled person and forgets people who are no longer in view (so liveness must be re-proven)."""

    def __init__(self, threshold: float) -> None:
        """Creates an empty bank using the given liveness threshold."""
        self.threshold = threshold
        self._by_name: dict = {}

    def update(self, name: str, score: float) -> bool:
        """Feeds one frame's score for a person and returns whether they currently count as live."""
        return self._by_name.setdefault(name, LivenessSmoother(self.threshold)).update(score)

    def keep_only(self, names) -> None:
        """Drops the history of everyone not in `names`, so a person who left view must pass liveness again."""
        for n in [n for n in self._by_name if n not in set(names)]:
            del self._by_name[n]
