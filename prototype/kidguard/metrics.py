"""Accuracy metrics and threshold suggestion from collected evaluation scores (PRD section 6)."""
from __future__ import annotations

# A record is: {"kind": "genuine"|"impostor", "who": str|None, "expected_role": str|None,
#               "matched_name": str|None, "matched_role": str|None, "score": float}


def predicted_role(rec: dict, threshold: float):
    """Returns the role the system would assign to this record at the threshold, or None if it would call the face unknown."""
    return rec["matched_role"] if rec["score"] >= threshold else None


def summarize(records: list, threshold: float) -> dict:
    """Computes false-accept rate, false-reject rate and dangerous child->adult swaps for the records at a threshold."""
    gen = [r for r in records if r["kind"] == "genuine"]
    imp = [r for r in records if r["kind"] == "impostor"]
    false_accepts = [r for r in imp if predicted_role(r, threshold) is not None]
    false_accept_adult = [r for r in imp if predicted_role(r, threshold) == "adult"]
    false_rejects = [r for r in gen if not (r["score"] >= threshold and r["matched_name"] == r["who"])]
    role_swaps = [r for r in gen if predicted_role(r, threshold) == "adult" and r["expected_role"] == "child"]
    return {
        "n_genuine": len(gen),
        "n_impostor": len(imp),
        "far": len(false_accepts) / len(imp) if imp else None,
        "far_as_adult": len(false_accept_adult) / len(imp) if imp else None,
        "frr": len(false_rejects) / len(gen) if gen else None,
        "child_as_adult": len(role_swaps),
        "threshold": threshold,
    }


def suggest_threshold(records: list, margin: float = 0.02):
    """Returns a threshold just above the highest impostor score (so no impostor frame is accepted), or None without impostor data."""
    imp = [r["score"] for r in records if r["kind"] == "impostor"]
    return round(max(imp) + margin, 3) if imp else None


def liveness_summary(records: list, threshold: float) -> dict:
    """Computes the share of spoof frames wrongly accepted as live and of live frames wrongly rejected, per frame, at a threshold."""
    live = [r["fused"] for r in records if r["kind"] == "live"]
    spoof = [r["fused"] for r in records if r["kind"] == "spoof"]
    return {
        "n_live": len(live), "n_spoof": len(spoof), "threshold": threshold,
        "spoof_accepted": sum(s >= threshold for s in spoof) / len(spoof) if spoof else None,
        "live_rejected": sum(s < threshold for s in live) / len(live) if live else None,
    }


def suggest_liveness_threshold(records: list, margin: float = 0.02):
    """Returns a threshold just above the highest spoof score (capped at 0.99), or None without spoof data."""
    spoof = [r["fused"] for r in records if r["kind"] == "spoof"]
    return min(0.99, round(max(spoof) + margin, 3)) if spoof else None


def percentile(values: list, q: float):
    """Returns the q-th percentile (0-100) of a list by nearest rank, or None if the list is empty."""
    if not values:
        return None
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round(q / 100 * (len(s) - 1)))))
    return s[k]
