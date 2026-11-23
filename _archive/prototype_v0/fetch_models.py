"""Downloads the YuNet and SFace ONNX models from the OpenCV Zoo into ./models."""
import hashlib
import sys
import urllib.request
from pathlib import Path

MODELS_DIR = Path(__file__).parent / "models"
BASE = "https://github.com/opencv/opencv_zoo/raw/main/models"

# name -> (url, expected sha256 or None until first verified download is pinned)
MODELS = {
    "face_detection_yunet_2023mar.onnx": (
        f"{BASE}/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
    ),
    "face_recognition_sface_2021dec.onnx": (
        f"{BASE}/face_recognition_sface/face_recognition_sface_2021dec.onnx",
        "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
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
    """Downloads one model if missing and checks its hash when a pinned hash exists."""
    dest = MODELS_DIR / name
    if not dest.exists():
        print(f"Downloading {name} ...")
        urllib.request.urlretrieve(url, dest)
    digest = sha256_of(dest)
    size_kb = dest.stat().st_size // 1024
    print(f"{name}: {size_kb} KB, sha256={digest}")
    if expected and digest != expected:
        print(f"HASH MISMATCH for {name}", file=sys.stderr)
        return False
    return True


def main() -> int:
    """Fetches all required models and returns a process exit code."""
    MODELS_DIR.mkdir(exist_ok=True)
    ok = all(fetch(n, u, h) for n, (u, h) in MODELS.items())
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
