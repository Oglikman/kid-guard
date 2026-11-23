"""Unit tests for the policy engine: precedence, fail-safe behaviour, curfew, overrides and policy file handling."""
from datetime import datetime

import pytest

from kidguard.blocklist import Blocklist
from kidguard.decision import Policy, decide, decide_for_label, in_curfew, load_policy, save_policy

BL = Blocklist({"adult": ["adult.test"], "gambling": ["bet.test"], "drugs": ["drug.test"], "violence": ["gore.test"]})
NOON = datetime(2026, 11, 2, 12, 0)
NIGHT = datetime(2026, 11, 2, 23, 30)
EARLY = datetime(2026, 11, 3, 6, 0)


def test_strict_blocks_listed_categories():
    """The strict profile blocks adult, gambling and drugs sites."""
    for url in ("http://adult.test", "https://www.bet.test/x", "drug.test"):
        assert decide(url, "strict", NOON, Policy(), BL).action == "block"


def test_normal_allows_listed_categories_by_default():
    """The normal profile allows listed sites by default (adult present)."""
    assert decide("http://adult.test", "normal", NOON, Policy(), BL).action == "allow"


def test_unlisted_site_is_allowed_with_reason():
    """A site on no list is allowed and the reason says so."""
    d = decide("https://example.org", "strict", NOON, Policy(), BL)
    assert d.action == "allow" and "not on any list" in d.reason


def test_category_without_rule_is_allowed():
    """A listed category with no configured action (e.g. violence in v1) is allowed."""
    assert decide("http://gore.test", "strict", NOON, Policy(), BL).action == "allow"


def test_warn_action():
    """A category set to 'warn' yields a warn decision."""
    p = Policy(actions={"strict": {}, "normal": {"gambling": "warn"}})
    assert decide("http://bet.test", "normal", NOON, p, BL).action == "warn"


def test_unknown_profile_fails_safe_to_strict():
    """An unrecognised profile name is treated as strict and the reason says so."""
    d = decide("http://adult.test", "banana", NOON, Policy(), BL)
    assert d.action == "block" and d.profile == "strict" and "treated as strict" in d.reason


def test_unparseable_url_blocked_in_strict_allowed_in_normal():
    """A URL with no host is blocked for strict (fail-safe) and allowed for normal."""
    assert decide("javascript:alert(1)", "strict", NOON, Policy(), BL).action == "block"
    assert decide("", "strict", NOON, Policy(), BL).action == "block"
    assert decide("file:///c:/x.html", "normal", NOON, Policy(), BL).action == "allow"


def test_internal_pages_always_allowed():
    """Browser internal pages are allowed even in strict, so the browser stays usable."""
    assert decide("chrome://settings", "strict", NOON, Policy(), BL).action == "allow"


def test_parent_always_block_beats_everything_even_normal():
    """A parent's always-block domain is blocked for every profile, including normal."""
    p = Policy(always_block={"timewaster.test"})
    assert decide("http://www.timewaster.test", "normal", NOON, p, BL).action == "block"


def test_parent_always_allow_overrides_category_for_strict():
    """A parent's always-allow domain overrides a category block for the strict profile."""
    p = Policy(always_allow={"bet.test"})
    assert decide("http://bet.test", "strict", NOON, p, BL).action == "allow"


def test_always_block_beats_always_allow():
    """If a domain is in both parent lists, blocking wins (safer)."""
    p = Policy(always_block={"x.test"}, always_allow={"x.test"})
    assert decide("http://x.test", "strict", NOON, p, BL).action == "block"


def test_curfew_blocks_everything_for_strict_only():
    """During curfew strict blocks even unlisted sites, while normal is unaffected."""
    p = Policy(strict_curfew=("22:00", "07:00"))
    assert decide("https://example.org", "strict", NIGHT, p, BL).action == "block"
    assert decide("https://example.org", "normal", NIGHT, p, BL).action == "allow"
    assert decide("https://example.org", "strict", NOON, p, BL).action == "allow"


def test_curfew_beats_always_allow():
    """Curfew applies even to parent-allowed domains, per the documented precedence."""
    p = Policy(strict_curfew=("22:00", "07:00"), always_allow={"example.org"})
    assert decide("https://example.org", "strict", EARLY, p, BL).action == "block"


def test_in_curfew_same_day_and_overnight_windows():
    """Curfew windows work both within a day and across midnight, end-exclusive."""
    assert in_curfew(datetime(2026, 1, 1, 13, 0), ("12:00", "14:00"))
    assert not in_curfew(datetime(2026, 1, 1, 14, 0), ("12:00", "14:00"))
    assert in_curfew(datetime(2026, 1, 1, 23, 59), ("22:00", "07:00"))
    assert in_curfew(datetime(2026, 1, 1, 0, 0), ("22:00", "07:00"))
    assert not in_curfew(datetime(2026, 1, 1, 7, 0), ("22:00", "07:00"))
    assert not in_curfew(NOON, None)


@pytest.mark.parametrize("label,expected", [("adult", "allow"), ("child", "block"), ("unknown", "block"), ("none", "block")])
def test_labels_map_to_fail_safe_decisions(label, expected):
    """Only an adult label unlocks an adult-category site; child, unknown and none stay blocked."""
    assert decide_for_label("http://adult.test", label, NOON, Policy(), BL).action == expected


def test_policy_round_trip(tmp_path):
    """A saved policy loads back identically, and a missing file gives the default policy."""
    p = Policy(always_block={"a.test"}, always_allow={"b.test"}, strict_curfew=("21:00", "06:30"))
    f = tmp_path / "policy.json"
    save_policy(p, f)
    q = load_policy(f)
    assert q.always_block == {"a.test"} and q.always_allow == {"b.test"} and q.strict_curfew == ("21:00", "06:30")
    assert load_policy(tmp_path / "none.json").actions == Policy().actions


def test_invalid_policy_rejected():
    """Invalid actions, profiles and curfew times raise ValueError."""
    with pytest.raises(ValueError):
        Policy(actions={"strict": {"adult": "maybe"}}).validate()
    with pytest.raises(ValueError):
        Policy(actions={"kid": {}}).validate()
    with pytest.raises(ValueError):
        Policy(strict_curfew=("25:00", "07:00")).validate()
