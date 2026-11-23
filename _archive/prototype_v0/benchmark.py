"""Measures detection/embedding latency and match-score statistics on live webcam frames (frames are not saved)."""
from __future__ import annotations

import argparse
import sys
import time

import numpy as np

from camera import open_camera
from face_engine import DEFAULT_THRESHOLD, FaceEngine, best_match
from store import load_templates


def pct(values: list, q: float) -> float:
    """Returns the q-th percentile of a list, or NaN if it is empty."""
    return float(np.percentile(values, q)) if values else float("nan")


def main() -> int:
    """Captures N frames, then prints latency stats and best-match score stats against enrolled templates."""
    ap = argparse.ArgumentParser(description="Latency and score benchmark")
    ap.add_argument("--frames", type=int, default=60)
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    args = ap.parse_args()

    engine, templates = FaceEngine(), load_templates()
    cap = open_camera()
    det_ms, emb_ms, scores, matched, no_face, names = [], [], [], 0, 0, {}
    try:
        for _ in range(args.frames):
            ok, frame = cap.read()
            if not ok:
                continue
            t0 = time.perf_counter()
            faces = engine.detect(frame)
            t1 = time.perf_counter()
            det_ms.append((t1 - t0) * 1000)
            if not faces:
                no_face += 1
                continue
            t2 = time.perf_counter()
            emb = engine.embed(frame, faces[0])
            emb_ms.append((time.perf_counter() - t2) * 1000)
            name, _role, score = best_match(emb, templates, args.threshold)
            scores.append(score)
            if name:
                matched += 1
                names[name] = names.get(name, 0) + 1
    finally:
        cap.release()

    total_ms = [d + e for d, e in zip(det_ms, emb_ms)]
    print(f"Frames requested: {args.frames}; with a face: {len(scores)}; no face: {no_face}")
    print(f"Detect ms   mean {np.mean(det_ms):.1f}  p95 {pct(det_ms, 95):.1f}")
    print(f"Embed ms    mean {np.mean(emb_ms) if emb_ms else float('nan'):.1f}  p95 {pct(emb_ms, 95):.1f}")
    if total_ms:
        print(f"Per-frame (detect+embed) mean {np.mean(total_ms):.1f} ms  => ~{1000 / np.mean(total_ms):.0f} fps max")
    if scores:
        print(f"Best-match score  min {min(scores):.3f}  mean {np.mean(scores):.3f}  max {max(scores):.3f}  (threshold {args.threshold})")
        print(f"Matched an enrolled person in {matched}/{len(scores)} face frames: {names}")
    if not templates:
        print("Note: nobody is enrolled, so scores are meaningless. Run enroll.py first.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
