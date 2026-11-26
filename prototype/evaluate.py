"""Measures accuracy and speed (PRD milestone 1): collect scores, report FAR/FRR and a data-based threshold, or time the pipeline."""
from __future__ import annotations

import argparse
import json
import sys
import time

import cv2
import numpy as np

from kidguard import config
from kidguard.camera import draw_camera_indicator, open_camera
from kidguard.challenge import HeadTurnChallenge, prompt_text, turn_progress, yaw_ratio
from kidguard.engine import FaceEngine, top_match
from kidguard.liveness import LivenessModel
from kidguard.metrics import liveness_summary, percentile, suggest_liveness_threshold, suggest_threshold, summarize
from kidguard.store import load_templates


def load_records() -> list:
    """Loads previously collected score records, or an empty list if none exist."""
    try:
        return json.loads(config.EVAL_LOG_PATH.read_text())
    except (OSError, ValueError):
        return []


def cmd_collect(args) -> int:
    """Captures frames of the person in front of the camera and appends their best-match scores (no images or embeddings are stored)."""
    templates = load_templates()
    if not templates:
        print("Nobody is enrolled. Run enroll.py first.")
        return 1
    expected_role = None
    if args.kind == "genuine":
        if args.who not in templates:
            print(f"'{args.who}' is not enrolled. Enrolled: {', '.join(templates)}")
            return 1
        expected_role = templates[args.who]["role"]
    engine, cap, new, no_face = FaceEngine(), open_camera(), [], 0
    print(f"Collecting {args.frames} frames as {args.kind}" + (f" ({args.who})" if args.who else "") + ". Press q to stop early.")
    try:
        while len(new) + no_face < args.frames:
            ok, frame = cap.read()
            if not ok:
                continue
            faces = engine.detect(frame)
            if faces:
                name, role, score = top_match(engine.embed(frame, faces[0]), templates)
                new.append({"kind": args.kind, "who": args.who, "expected_role": expected_role,
                            "matched_name": name, "matched_role": role, "score": round(score, 4),
                            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "note": args.note})
            else:
                no_face += 1
            draw_camera_indicator(frame)
            cv2.putText(frame, f"{args.kind}: {len(new) + no_face}/{args.frames}", (10, 56), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            cv2.imshow("KidGuard evaluate", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()
    config.EVAL_LOG_PATH.write_text(json.dumps(load_records() + new, indent=1))
    scores = [r["score"] for r in new]
    print(f"Saved {len(new)} scored frames ({no_face} had no face)."
          + (f" Score min {min(scores):.3f} mean {np.mean(scores):.3f} max {max(scores):.3f}." if scores else ""))
    return 0


def fmt(x) -> str:
    """Formats a rate as a percentage, or 'n/a' when there is no data."""
    return "n/a" if x is None else f"{x * 100:.1f}%"


def cmd_report(args) -> int:
    """Prints FAR/FRR at the current threshold, suggests a threshold from the data, and optionally saves it."""
    recs = load_records()
    if not recs:
        print("No evaluation data yet. Run: py evaluate.py collect --kind genuine --who <name>")
        return 1
    gen = [r["score"] for r in recs if r["kind"] == "genuine" and r["matched_name"] == r["who"]]
    imp = [r["score"] for r in recs if r["kind"] == "impostor"]
    print(f"Genuine frames: {sum(r['kind'] == 'genuine' for r in recs)}  Impostor frames: {len(imp)}")
    if gen:
        print(f"Genuine (correctly identified) scores: p5 {percentile(gen, 5):.3f}  median {percentile(gen, 50):.3f}  max {max(gen):.3f}")
    if imp:
        print(f"Impostor scores: median {percentile(imp, 50):.3f}  p95 {percentile(imp, 95):.3f}  max {max(imp):.3f}")
    cur = config.load_threshold()
    for label, thr in (("current", cur), ("suggested", suggest_threshold(recs))):
        if thr is None:
            print("Suggested threshold: need impostor data (someone NOT enrolled in front of the camera).")
            continue
        s = summarize(recs, thr)
        print(f"[{label}] threshold {thr}: false-accept {fmt(s['far'])} (as adult {fmt(s['far_as_adult'])}), "
              f"false-reject {fmt(s['frr'])}, child-classified-as-adult frames {s['child_as_adult']}")
    sug = suggest_threshold(recs)
    if sug is not None and gen and percentile(gen, 5) < sug:
        print("WARNING: the suggested threshold would reject more than 5% of genuine frames; scores overlap, so more data, better lighting, or a stronger model is needed.")
    if args.apply:
        if sug is None:
            print("Not applied: no impostor data.")
        else:
            config.save_threshold(sug)
            print(f"Saved threshold {sug} to settings.json")
    return 0


def cmd_latency(args) -> int:
    """Times detection and embedding on live frames and prints mean and 95th-percentile milliseconds."""
    engine, cap, det, emb = FaceEngine(), open_camera(), [], []
    try:
        for _ in range(args.frames):
            ok, frame = cap.read()
            if not ok:
                continue
            t0 = time.perf_counter()
            faces = engine.detect(frame)
            det.append((time.perf_counter() - t0) * 1000)
            if faces:
                t1 = time.perf_counter()
                engine.embed(frame, faces[0])
                emb.append((time.perf_counter() - t1) * 1000)
    finally:
        cap.release()
    if not det:
        print("No frames captured.")
        return 1
    print(f"Frames: {len(det)}  with a face: {len(emb)}")
    print(f"Detect ms  mean {np.mean(det):.1f}  p95 {percentile(det, 95):.1f}")
    if emb:
        print(f"Embed  ms  mean {np.mean(emb):.1f}  p95 {percentile(emb, 95):.1f}")
        print(f"Per frame (detect+embed) mean {np.mean(det) + np.mean(emb):.1f} ms (PRD target: under 100 ms)")
    return 0


def load_liveness_records() -> list:
    """Loads previously collected liveness scores, or an empty list if none exist."""
    try:
        return json.loads(config.LIVENESS_EVAL_PATH.read_text())
    except (OSError, ValueError):
        return []


def cmd_lcollect(args) -> int:
    """Captures frames of a live person or a spoof (photo/screen) in front of the camera and appends the liveness scores (no images are stored)."""
    engine, model, cap = FaceEngine(), LivenessModel(), open_camera()
    new, no_face, read_fails = [], 0, 0
    print(f"Collecting {args.frames} frames as '{args.kind}' ({args.note or 'no note'}). Press q to stop early.")
    try:
        while len(new) + no_face < args.frames and read_fails < 100:
            ok, frame = cap.read()
            if not ok:
                read_fails += 1
                continue
            faces = engine.detect(frame)
            if faces:
                s = model.score(frame, faces[0])
                new.append({"kind": args.kind, "fused": round(s["fused"], 4), "per_model": [round(p, 4) for p in s["per_model"]],
                            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "note": args.note})
            else:
                no_face += 1
            draw_camera_indicator(frame)
            cv2.putText(frame, f"{args.kind}: {len(new) + no_face}/{args.frames}", (10, 56), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            cv2.imshow("KidGuard liveness", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()
    config.LIVENESS_EVAL_PATH.write_text(json.dumps(load_liveness_records() + new, indent=1))
    scores = [r["fused"] for r in new]
    print(f"Saved {len(new)} scored frames ({no_face} had no face)."
          + (f" Real-probability min {min(scores):.3f} mean {np.mean(scores):.3f} max {max(scores):.3f}." if scores else ""))
    return 0


def cmd_lreport(args) -> int:
    """Prints liveness scores per kind and note, the per-frame spoof-accepted and live-rejected rates, a suggested threshold, and optionally saves it."""
    recs = load_liveness_records()
    if not recs:
        print("No liveness data yet. Run: py evaluate.py lcollect --kind live   and   --kind spoof --note \"phone photo\"")
        return 1
    groups: dict = {}
    for r in recs:
        groups.setdefault((r["kind"], r["note"]), []).append(r["fused"])
    for (kind, note), v in sorted(groups.items()):
        print(f"{kind:5} {note or '(no note)':28} n={len(v):3}  min {min(v):.3f}  median {percentile(v, 50):.3f}  max {max(v):.3f}")
    sug = suggest_liveness_threshold(recs)
    for label, thr in (("current", config.load_liveness_threshold()), ("suggested", sug)):
        if thr is None:
            print("Suggested threshold: need spoof data (hold a photo or video of an enrolled adult up to the camera).")
            continue
        s = liveness_summary(recs, thr)
        sa = "n/a" if s["spoof_accepted"] is None else f"{s['spoof_accepted'] * 100:.1f}%"
        lr = "n/a" if s["live_rejected"] is None else f"{s['live_rejected'] * 100:.1f}%"
        print(f"[{label}] threshold {thr}: spoof frames accepted {sa}, live frames rejected {lr} (per frame, before smoothing)")
    live = [r["fused"] for r in recs if r["kind"] == "live"]
    if sug is not None and live and percentile(live, 5) < sug:
        print("WARNING: the suggested threshold would reject more than 5% of live frames: live and spoof scores overlap, so this model may not separate them well on your camera.")
    if args.apply:
        if sug is None:
            print("Not applied: no spoof data.")
        else:
            config.save_liveness_threshold(sug)
            print(f"Saved liveness threshold {sug} to settings.json")
    return 0


def load_challenge_records() -> list:
    """Loads previously collected head-turn challenge attempts, or an empty list if none exist."""
    try:
        return json.loads(config.CHALLENGE_EVAL_PATH.read_text())
    except (OSError, ValueError):
        return []


def run_one_challenge_attempt(engine, cap, templates, who, threshold, label: str) -> dict:
    """Runs one multi-turn attempt on the live camera (first face in view, no PIN) and returns its result record (no images are stored)."""
    ch, t0 = HeadTurnChallenge(), time.monotonic()
    max_turn, lo, hi, frames, id_frames, passed = 0.0, 0.0, 0.0, 0, 0, False
    sides: list = []      # the sides actually shown, in order
    trace: list = []      # per loop: [seconds since start, yaw or None, phase, requested side, turns done] after this frame
    while True:
        ok, frame = cap.read()
        now = time.monotonic()
        yaw, faces = None, []
        if ok:
            faces = engine.detect(frame)
            if faces:
                yaw = yaw_ratio(faces[0][4:14])
        asked, turning = ch.direction, ch.state == "prompting" and ch.phase == "turn"   # what was on screen for this frame
        passed = ch.update(yaw, now)
        trace.append([round(now - t0, 3), None if yaw is None else round(yaw, 3), ch.phase, ch.direction, ch.step])
        if ch.state == "prompting" and ch.phase == "turn" and len(sides) == ch.step:
            sides.append(ch.direction)
        if yaw is not None:
            frames += 1
            lo, hi = min(lo, yaw), max(hi, yaw)
            if turning:
                max_turn = max(max_turn, turn_progress(yaw, asked))
            if who and templates:
                name, _, score = top_match(engine.embed(frame, faces[0]), templates)
                id_frames += int(name == who and score >= threshold)
        if ok:
            draw_camera_indicator(frame)
            cv2.putText(frame, f"{label}  {prompt_text(ch.prompt(now))}", (10, 56), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            cv2.imshow("KidGuard challenge", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            raise KeyboardInterrupt
        if passed or ch.state == "failed":
            return {"passed": bool(passed), "sides": sides, "steps_done": ch.step, "steps_required": config.CHALLENGE_STEPS,
                    "fail_reason": ch.fail_reason, "secs": round(now - t0, 2), "max_turn": round(max_turn, 3),
                    "yaw_min": round(lo, 3), "yaw_max": round(hi, 3), "frames_with_face": frames,
                    "id_match_frac": None if not (who and frames) else round(id_frames / frames, 3),
                    "neutral_frames_required": config.CHALLENGE_NEUTRAL_FRAMES, "trace": trace}


def cmd_ccollect(args) -> int:
    """Runs several head-turn challenge attempts in front of the camera and appends pass/fail results (kind live, photo or video)."""
    engine, cap = FaceEngine(), open_camera()
    templates = load_templates() if args.who else {}
    threshold = config.load_threshold()
    new = []
    print(f"Running {args.attempts} attempts as '{args.kind}' ({args.note or 'no note'}). Press q to stop. "
          "NOTE: this measures head movement only; identity is checked only if --who is given.")
    try:
        for i in range(args.attempts):
            end = time.monotonic() + args.gap
            while time.monotonic() < end:      # short pause so the person (or the phone) can get into position
                ok, frame = cap.read()
                if ok:
                    cv2.putText(frame, f"attempt {i + 1}/{args.attempts} starts in {max(0, end - time.monotonic()):.0f}s", (10, 56),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                    cv2.imshow("KidGuard challenge", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    raise KeyboardInterrupt
            rec = run_one_challenge_attempt(engine, cap, templates, args.who, threshold, f"{i + 1}/{args.attempts}")
            rec.update({"kind": args.kind, "note": args.note, "ts": time.strftime("%Y-%m-%dT%H:%M:%S")})
            new.append(rec)
            print(f"  attempt {i + 1}: {'PASSED' if rec['passed'] else 'failed'} in {rec['secs']}s, max turn {rec['max_turn']}, "
                  f"yaw range {rec['yaw_min']}..{rec['yaw_max']}")
    except KeyboardInterrupt:
        print("Stopped early.")
    finally:
        cap.release()
        cv2.destroyAllWindows()
        if new:
            config.CHALLENGE_EVAL_PATH.write_text(json.dumps(load_challenge_records() + new, indent=1))
    print(f"Saved {len(new)} attempts; {sum(r['passed'] for r in new)} passed.")
    return 0


def cmd_creport(args) -> int:
    """Prints head-turn pass rates per kind, rule and note; totals against the PRD targets count only attempts made under the current rule."""
    recs = load_challenge_records()
    if not recs:
        print("No challenge data yet. Run: py evaluate.py ccollect --kind live --attempts 20")
        return 1
    groups: dict = {}
    for r in recs:
        groups.setdefault((r["kind"], r.get("steps_required", 1), r.get("neutral_frames_required", 3), r["note"]), []).append(r)
    for (kind, steps, neutral, note), v in sorted(groups.items()):
        n, p = len(v), sum(r["passed"] for r in v)
        secs = [r["secs"] for r in v if r["passed"]]
        extra = f", median time to pass {percentile(secs, 50):.1f}s" if secs else ""
        bound = f", 95% upper bound on pass rate ~{3 / n * 100:.0f}% (rule of three)" if p == 0 else ""
        reasons = [r["fail_reason"] for r in v if r.get("fail_reason")]
        if reasons:
            extra += ", failures: " + ", ".join(f"{x} {reasons.count(x)}" for x in sorted(set(reasons)))
        print(f"{kind:5} [{steps} turn(s), {neutral} centred] {note or '(no note)':40} {p}/{n} passed ({p / n * 100:.0f}%), max turn median {percentile([r['max_turn'] for r in v], 50):.2f}{extra}{bound}")
    for kind, target in (("live", "target >= 95% passed"), ("photo", "target 0 passes in 50"), ("video", "no target; report only")):
        v = [r for r in recs if r["kind"] == kind and r.get("steps_required", 1) == config.CHALLENGE_STEPS
             and r.get("neutral_frames_required", 3) == config.CHALLENGE_NEUTRAL_FRAMES]
        if v:
            print(f"[{kind} total, current rule only] {sum(r['passed'] for r in v)}/{len(v)} passed ({target})")
    return 0


def main() -> int:
    """Parses the sub-command (collect, report, latency, lcollect, lreport, ccollect or creport) and runs it."""
    ap = argparse.ArgumentParser(description="KidGuard evaluation")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect", help="capture scored frames")
    c.add_argument("--kind", choices=["genuine", "impostor"], required=True)
    c.add_argument("--who", help="enrolled name (required for genuine)")
    c.add_argument("--frames", type=int, default=60)
    c.add_argument("--note", default="", help="free text, e.g. 'daylight' or 'lamp only'")
    c.set_defaults(fn=cmd_collect)
    r = sub.add_parser("report", help="print FAR/FRR and suggest a threshold")
    r.add_argument("--apply", action="store_true", help="save the suggested threshold")
    r.set_defaults(fn=cmd_report)
    lat = sub.add_parser("latency", help="time the pipeline")
    lat.add_argument("--frames", type=int, default=60)
    lat.set_defaults(fn=cmd_latency)
    lc = sub.add_parser("lcollect", help="capture liveness scores of a live face or a spoof")
    lc.add_argument("--kind", choices=["live", "spoof"], required=True)
    lc.add_argument("--note", default="", help="what is being shown, e.g. 'me, normal light' or 'phone photo of me'")
    lc.add_argument("--frames", type=int, default=60)
    lc.set_defaults(fn=cmd_lcollect)
    lr = sub.add_parser("lreport", help="report liveness separation and suggest a threshold")
    lr.add_argument("--apply", action="store_true", help="save the suggested liveness threshold")
    lr.set_defaults(fn=cmd_lreport)
    cc = sub.add_parser("ccollect", help="run head-turn challenge attempts and record pass/fail (F14)")
    cc.add_argument("--kind", choices=["live", "photo", "video"], required=True)
    cc.add_argument("--note", default="", help="conditions, e.g. 'normal light' or 'phone photo, bright, tilted'")
    cc.add_argument("--attempts", type=int, default=5)
    cc.add_argument("--gap", type=float, default=3.0, help="seconds to get into position before each attempt")
    cc.add_argument("--who", help="enrolled name: also record how often the face still matched during the attempt")
    cc.set_defaults(fn=cmd_ccollect)
    cr = sub.add_parser("creport", help="report head-turn pass rates")
    cr.set_defaults(fn=cmd_creport)
    args = ap.parse_args()
    if args.cmd == "collect" and args.kind == "genuine" and not args.who:
        ap.error("--who is required for --kind genuine")
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
