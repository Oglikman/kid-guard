"""Unit tests for accuracy metrics, threshold suggestion and settings persistence."""
from kidguard import config
from kidguard.metrics import percentile, predicted_role, suggest_threshold, summarize


def rec(kind, score, who=None, exp_role=None, name=None, role=None):
    """Builds one evaluation record."""
    return {"kind": kind, "who": who, "expected_role": exp_role, "matched_name": name, "matched_role": role, "score": score}


def test_predicted_role_respects_threshold():
    """A record below the threshold is unknown (None); at or above it takes the matched role."""
    r = rec("impostor", 0.4, name="dad", role="adult")
    assert predicted_role(r, 0.5) is None and predicted_role(r, 0.4) == "adult"


def test_far_counts_impostors_accepted():
    """False-accept rate is the share of impostor frames that clear the threshold."""
    recs = [rec("impostor", 0.6, name="dad", role="adult"), rec("impostor", 0.1, name="dad", role="adult")]
    s = summarize(recs, 0.5)
    assert s["far"] == 0.5 and s["far_as_adult"] == 0.5


def test_frr_counts_wrong_or_low_genuine():
    """False-reject rate counts genuine frames that are below threshold or matched to the wrong person."""
    recs = [rec("genuine", 0.9, "dad", "adult", "dad", "adult"), rec("genuine", 0.2, "dad", "adult", "dad", "adult"),
            rec("genuine", 0.9, "dad", "adult", "mum", "adult"), rec("genuine", 0.8, "dad", "adult", "dad", "adult")]
    assert summarize(recs, 0.5)["frr"] == 0.5


def test_child_as_adult_is_flagged():
    """A genuine child frame identified as an adult is counted as a dangerous swap."""
    recs = [rec("genuine", 0.9, "kid", "child", "dad", "adult")]
    assert summarize(recs, 0.5)["child_as_adult"] == 1


def test_no_data_gives_none():
    """Rates are None when there is no data for them."""
    s = summarize([], 0.5)
    assert s["far"] is None and s["frr"] is None


def test_suggest_threshold_above_highest_impostor():
    """The suggested threshold sits just above the highest impostor score."""
    recs = [rec("impostor", 0.2), rec("impostor", 0.31)]
    assert suggest_threshold(recs, margin=0.02) == 0.33


def test_suggest_threshold_needs_impostors():
    """Without impostor data no threshold is suggested."""
    assert suggest_threshold([rec("genuine", 0.9)]) is None


def test_percentile_basic():
    """Nearest-rank percentile returns min, median and max correctly."""
    v = [1, 2, 3, 4, 5]
    assert percentile(v, 0) == 1 and percentile(v, 50) == 3 and percentile(v, 100) == 5 and percentile([], 50) is None


def test_threshold_settings_round_trip(tmp_path):
    """A saved threshold loads back, and a missing file falls back to the default."""
    p = tmp_path / "s.json"
    assert config.load_threshold(p) == config.DEFAULT_THRESHOLD
    config.save_threshold(0.42, p)
    assert config.load_threshold(p) == 0.42
