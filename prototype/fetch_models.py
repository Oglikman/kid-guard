"""Downloads the YuNet and SFace ONNX models from the OpenCV Zoo into ./models and verifies pinned SHA-256 hashes."""
import hashlib
import sys
import urllib.request
from pathlib import Path

from kidguard.config import MODELS_DIR

BASE = "https://github.com/opencv/opencv_zoo/raw/main/models"
MODELS = {
    "face_detection_yunet_2023mar.onnx": (
        f"{BASE}/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
    ),
    "face_recognition_sface_2021dec.onnx": (
        f"{BASE}/face_recognition_sface/face_recognition_sface_2021dec.onnx",
        "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
    ),
    # Anti-spoofing (liveness) models: MiniFASNet ONNX exports from github.com/yakhyo/face-anti-spoofing (repo licence Apache-2.0;
    # the weights' own licence is not stated there; confirm before any commercial use).
    "MiniFASNetV2.onnx": (
        "https://github.com/yakhyo/face-anti-spoofing/releases/download/weights/MiniFASNetV2.onnx",
        "b32929adc2d9c34b9486f8c4c7bc97c1b69bc0ea9befefc380e4faae4e463907",
    ),
    "MiniFASNetV1SE.onnx": (
        "https://github.com/yakhyo/face-anti-spoofing/releases/download/weights/MiniFASNetV1SE.onnx",
        "ebab7f90c7833fbccd46d3a555410e78d969db5438e169b6524be444862b3676",
    ),
}


def sha256_of(path: Path) -> str:
    """Returns the SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(name: str, url: str, expected: str | None) -> bool:
    """Downloads one model if missing; returns True if its hash matches the pinned value, or (with a printed notice) if no hash is pinned yet."""
    dest = MODELS_DIR / name
    if not dest.exists():
        print(f"Downloading {name} ...")
        urllib.request.urlretrieve(url, dest)
    digest = sha256_of(dest)
    if expected is None:
        print(f"{name}: {dest.stat().st_size} bytes, UNPINNED sha256={digest}")
        return True
    ok = digest == expected
    print(f"{name}: {dest.stat().st_size // 1024} KB, hash {'OK' if ok else 'MISMATCH ' + digest}")
    return ok


def main() -> int:
    """Fetches and verifies all required models and returns a process exit code."""
    MODELS_DIR.mkdir(exist_ok=True)
    return 0 if all([fetch(n, u, h) for n, (u, h) in MODELS.items()]) else 1


if __name__ == "__main__":
    sys.exit(main())
