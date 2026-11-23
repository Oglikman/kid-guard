"""Live loop: classifies who is at the webcam (adult/child/unknown/none) and shows the resulting filter profile."""
from __future__ import annotations

import argparse
import sys
import time

import cv2

from camera import open_camera
from face_engine import DEFAULT_THRESHOLD, FaceEngine, StableLabel, best_match, classify, profile_for
from store import load_templates


def label_frame(engine: FaceEngine, frame, templates: dict, threshold: float):
    """Returns (raw_label, per-face (name, role, score) results) for one frame."""
    results = []
    for face in engine.detect(frame):
        results.append(best_match(engine.embed(frame, face), templates, threshold))
    return classify([r[1] for r in results]), results


def main() -> int:
    """Runs the live classification loop, with a window by default or a fixed frame count in --headless mode."""
    ap = argparse.ArgumentParser(description="Live who-is-at-the-screen demo")
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    ap.add_argument("--headless", type=int, default=0, help="run N frames without a window and print a summary")
    args = ap.parse_args()

    templates = load_templates()
    if not templates:
        print("No one is enrolled yet (every face will be 'unknown'). Run enroll.py first.")
    engine, stable = FaceEngine(), StableLabel()
    try:
        cap = open_camera()
    except RuntimeError as e:
        print(f"Camera error -> strict profile. {e}")
        return 2

    counts, t0, n = {}, time.time(), 0
    try:
        while True:
            ok, frame = cap.read()
            label = "none" if not ok else None
            results = []
            if ok:
                raw, results = label_frame(engine, frame, templates, args.threshold)
                label = stable.update(raw)
            else:
                label = stable.update("none")
            n += 1
            counts[label] = counts.get(label, 0) + 1
            if args.headless:
                if n >= args.headless:
                    break
                continue
            profile = profile_for(label)
            color = (0, 200, 0) if profile == "normal" else (0, 0, 255)
            cv2.putText(frame, "CAMERA ON", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            cv2.putText(frame, f"{label.upper()}  ->  {profile.upper()} profile", (10, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
            for i, (name, _role, score) in enumerate(results):
                cv2.putText(frame, f"{name or 'unknown'} {score:.2f}", (10, 85 + 22 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
            cv2.imshow("KidGuard", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()
    dt = time.time() - t0
    print(f"{n} frames in {dt:.1f}s ({n / dt:.1f} fps). Smoothed labels: {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
