"""Face detection, embedding and matching (OpenCV YuNet + SFace)."""
from __future__ import annotations

import numpy as np

from . import config


def cosine_similarity(a, b) -> float:
    """Returns the cosine similarity between two embedding vectors (0.0 if either has zero length)."""
    a = np.asarray(a, dtype=np.float32).ravel()
    b = np.asarray(b, dtype=np.float32).ravel()
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.dot(a, b) / denom) if denom else 0.0


def top_match(embedding, templates: dict):
    """Returns (name, role, score) of the closest enrolled template with no threshold applied, or (None, None, -1.0) if nobody is enrolled."""
    best = (None, None, -1.0)
    for name, entry in templates.items():
        for tmpl in entry["embeddings"]:
            score = cosine_similarity(embedding, tmpl)
            if score > best[2]:
                best = (name, entry["role"], score)
    return best


def best_match(embedding, templates: dict, threshold: float):
    """Returns (name, role, score) if the closest template clears the threshold, otherwise (None, None, score)."""
    name, role, score = top_match(embedding, templates)
    return (name, role, score) if score >= threshold else (None, None, score)


class FaceEngine:
    """Wraps the YuNet detector and SFace recognizer behind a small interface."""

    def __init__(self) -> None:
        """Loads both ONNX models, raising a clear error if they have not been downloaded."""
        import cv2

        for m in (config.DETECTOR_MODEL, config.RECOGNIZER_MODEL):
            if not m.exists():
                raise FileNotFoundError(f"{m.name} missing; run: py fetch_models.py")
        self.detector = cv2.FaceDetectorYN.create(str(config.DETECTOR_MODEL), "", (320, 320), config.DETECT_SCORE, 0.3, 5000)
        self.recognizer = cv2.FaceRecognizerSF.create(str(config.RECOGNIZER_MODEL), "")

    def detect(self, frame) -> list:
        """Returns the detected face rows (box, landmarks, score) for a BGR frame, or an empty list."""
        h, w = frame.shape[:2]
        self.detector.setInputSize((w, h))
        _, faces = self.detector.detect(frame)
        return [] if faces is None else list(faces)

    def embed(self, frame, face_row) -> np.ndarray:
        """Returns the aligned, L2-normalised embedding for one detected face."""
        aligned = self.recognizer.alignCrop(frame, face_row)
        feat = np.asarray(self.recognizer.feature(aligned), dtype=np.float32).ravel()
        norm = np.linalg.norm(feat)
        return feat / norm if norm else feat
