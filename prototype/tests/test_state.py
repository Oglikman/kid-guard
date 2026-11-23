"""Unit tests for the shared state file and its fail-safe reading rules."""
from kidguard.state import read_state, write_state


def test_round_trip_fresh(tmp_path):
    """A freshly written label reads back as itself with reason 'ok'."""
    p = tmp_path / "s.json"
    write_state("adult", p, now=1000.0)
    r = read_state(p, now=1001.0)
    assert (r.label, r.reason) == ("adult", "ok")


def test_missing_file_is_none(tmp_path):
    """No state file means nobody confirmed present, so the label is 'none'."""
    r = read_state(tmp_path / "nope.json")
    assert (r.label, r.reason) == ("none", "missing")


def test_stale_state_is_none(tmp_path):
    """A label older than the max age is replaced by 'none' (e.g. the camera app crashed)."""
    p = tmp_path / "s.json"
    write_state("adult", p, now=1000.0)
    r = read_state(p, now=1010.0, max_age=5.0)
    assert (r.label, r.reason) == ("none", "stale")


def test_future_timestamp_is_none(tmp_path):
    """A timestamp far in the future is rejected as stale rather than trusted."""
    p = tmp_path / "s.json"
    write_state("adult", p, now=5000.0)
    assert read_state(p, now=1000.0).label == "none"


def test_corrupt_file_is_none(tmp_path):
    """Garbage in the state file gives 'none' with reason 'corrupt'."""
    p = tmp_path / "s.json"
    p.write_text("{not json")
    assert (read_state(p).label, read_state(p).reason) == ("none", "corrupt")


def test_invalid_label_is_none(tmp_path):
    """A label outside the allowed set (e.g. a tampered 'admin') is rejected."""
    p = tmp_path / "s.json"
    write_state("admin", p, now=1000.0)
    r = read_state(p, now=1000.5)
    assert (r.label, r.reason) == ("none", "invalid")


def test_write_retries_when_replace_is_denied(tmp_path, monkeypatch):
    """If Windows denies the replace a few times (a reader has the file open), the write still succeeds."""
    import os
    real, calls = os.replace, {"n": 0}

    def flaky(src, dst):
        """Raises PermissionError for the first three calls, then behaves normally."""
        calls["n"] += 1
        if calls["n"] <= 3:
            raise PermissionError(5, "Access is denied")
        return real(src, dst)

    monkeypatch.setattr(os, "replace", flaky)
    p = tmp_path / "s.json"
    assert write_state("child", p, now=1000.0) is True and read_state(p, now=1000.5).label == "child" and calls["n"] == 4


def test_write_falls_back_to_direct_write_and_never_raises(tmp_path, monkeypatch):
    """If replace is always denied, the writer falls back to a direct write instead of raising."""
    import os

    def always_denied(src, dst):
        """Always raises PermissionError."""
        raise PermissionError(5, "Access is denied")

    monkeypatch.setattr(os, "replace", always_denied)
    p = tmp_path / "s.json"
    assert write_state("adult", p, now=1000.0) is True and read_state(p, now=1000.5).label == "adult"


def test_write_to_unwritable_location_returns_false(tmp_path):
    """Writing into a directory that does not exist returns False rather than raising."""
    assert write_state("adult", tmp_path / "no_such_dir" / "s.json") is False


def test_missing_keys_is_corrupt(tmp_path):
    """JSON without the expected keys is treated as corrupt."""
    p = tmp_path / "s.json"
    p.write_text('{"label": "adult"}')
    assert read_state(p).reason == "corrupt"
