"""Policy engine: person profile + URL + time + parent overrides -> allow / warn / block with a reason."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import config
from .blocklist import Blocklist, host_in, parse_url
from .policy import profile_for

VALID_ACTIONS = ("allow", "warn", "block")
INTERNAL_SCHEMES = {"chrome", "edge", "about", "chrome-extension", "edge-extension", "chrome-search", "devtools"}


@dataclass
class Decision:
    """The engine's verdict for one URL, with the reason and context needed for logging and display."""

    action: str
    reason: str
    profile: str
    category: str | None = None
    host: str | None = None


def default_actions() -> dict:
    """Returns the default per-profile category actions: strict blocks adult, gambling and drugs; normal allows everything."""
    return {"strict": {"adult": "block", "gambling": "block", "drugs": "block"}, "normal": {}}


@dataclass
class Policy:
    """Parent-configurable rules: category actions per profile, always-block / always-allow domains, and an optional strict-profile curfew."""

    actions: dict = field(default_factory=default_actions)
    always_block: set = field(default_factory=set)
    always_allow: set = field(default_factory=set)
    strict_curfew: tuple | None = None  # ("22:00", "07:00"): strict profile blocks everything in this window

    def validate(self) -> None:
        """Raises ValueError if any action, profile or curfew time is invalid."""
        for profile, cats in self.actions.items():
            if profile not in ("normal", "strict"):
                raise ValueError(f"unknown profile '{profile}'")
            for cat, act in cats.items():
                if act not in VALID_ACTIONS:
                    raise ValueError(f"invalid action '{act}' for {profile}/{cat}")
        if self.strict_curfew is not None:
            for t in self.strict_curfew:
                _minutes(t)

    def to_dict(self) -> dict:
        """Returns a JSON-serialisable dict of the policy."""
        return {"actions": self.actions, "always_block": sorted(self.always_block),
                "always_allow": sorted(self.always_allow), "strict_curfew": list(self.strict_curfew) if self.strict_curfew else None}

    @classmethod
    def from_dict(cls, d: dict) -> "Policy":
        """Builds and validates a Policy from a dict, using defaults for missing keys."""
        curfew = d.get("strict_curfew")
        p = cls(actions=d.get("actions", default_actions()), always_block=set(d.get("always_block", [])),
                always_allow=set(d.get("always_allow", [])), strict_curfew=tuple(curfew) if curfew else None)
        p.validate()
        return p


def load_policy(path: Path = config.POLICY_PATH) -> Policy:
    """Loads the policy file, or returns the default policy if the file does not exist."""
    p = Path(path)
    return Policy.from_dict(json.loads(p.read_text())) if p.exists() else Policy()


def save_policy(policy: Policy, path: Path = config.POLICY_PATH) -> None:
    """Validates and writes the policy to a JSON file."""
    policy.validate()
    Path(path).write_text(json.dumps(policy.to_dict(), indent=2))


def _minutes(hhmm: str) -> int:
    """Converts 'HH:MM' to minutes after midnight, raising ValueError if malformed."""
    h, m = hhmm.split(":")
    h, m = int(h), int(m)
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError(f"bad time '{hhmm}'")
    return h * 60 + m


def in_curfew(now: datetime, curfew) -> bool:
    """Returns True if the time of day falls inside the curfew window, which may cross midnight."""
    if not curfew:
        return False
    start, end, t = _minutes(curfew[0]), _minutes(curfew[1]), now.hour * 60 + now.minute
    return start <= t < end if start <= end else (t >= start or t < end)


def decide(url: str, profile: str, now: datetime, policy: Policy, blocklist: Blocklist) -> Decision:
    """Decides allow/warn/block; order: internal pages, unparseable URLs, parent always-block, strict curfew, parent always-allow, category rule, default allow."""
    prof = profile if profile in ("normal", "strict") else "strict"  # unknown profile -> fail-safe strict
    failsafe = "" if prof == profile else f" (unknown profile '{profile}' treated as strict)"
    scheme, host = parse_url(url)
    if scheme in INTERNAL_SCHEMES:
        return Decision("allow", "browser internal page", prof)
    if host is None:
        if prof == "strict":
            return Decision("block", "unparseable or non-web URL" + failsafe, prof)
        return Decision("allow", "non-web URL", prof)
    if host_in(host, policy.always_block):
        return Decision("block", "blocked by parent", prof, host=host)
    if prof == "strict" and in_curfew(now, policy.strict_curfew):
        return Decision("block", f"curfew {policy.strict_curfew[0]}-{policy.strict_curfew[1]}", prof, host=host)
    if host_in(host, policy.always_allow):
        return Decision("allow", "allowed by parent", prof, host=host)
    cat = blocklist.category_of(host)
    if cat is not None:
        act = policy.actions.get(prof, {}).get(cat, "allow")
        if act != "allow":
            return Decision(act, f"category '{cat}' is {act} for the {prof} profile" + failsafe, prof, cat, host)
        return Decision("allow", f"category '{cat}' allowed for the {prof} profile", prof, cat, host)
    return Decision("allow", "not on any list" + failsafe, prof, None, host)


def decide_for_label(url: str, label: str, now: datetime, policy: Policy, blocklist: Blocklist) -> Decision:
    """Maps the face-match label (adult/child/unknown/none) to a profile with the fail-safe rule, then decides."""
    return decide(url, profile_for(label), now, policy, blocklist)
