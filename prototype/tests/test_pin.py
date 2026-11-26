"""Tests for the PIN step-up (PRD F15): storage, lockout, restart persistence, fail-safe file errors and use with the challenge."""
import pytest

import set_pin
from kidguard import config, pin
from kidguard.challenge import ChallengeBank, HeadTurnChallenge
from kidguard.pin import PinEntry, PinGate

PIN, BAD = "482913", "000000"
ONE_TURN = [0.0, 0.4, 0.4, 0.4]
PASS = ONE_TURN * config.CHALLENGE_STEPS
LEFT = lambda: "left"      # noqa: E731


class Clock:
    """A clock that only moves when a test moves it."""

    def __init__(self, t=1000.0):
        """Starts at the given time."""
        self.t = t

    def __call__(self):
        """Returns the current fake time."""
        return self.t


def flip(data: bytes) -> bytes:
    """A reversible stand-in for encryption that keeps the plain text out of the file."""
    return bytes(b ^ 0x5A for b in data)


@pytest.fixture
def env(tmp_path):
    """Returns a factory that opens a gate on one shared file with shared fake clocks (calling it again simulates a restart)."""
    mono, wall, path = Clock(), Clock(1_800_000_000.0), tmp_path / "security.bin"

    def make():
        """Opens a new gate on the shared file."""
        return PinGate(path, encrypt=flip, decrypt=flip, clock=mono, wall=wall)

    make.mono, make.wall, make.path = mono, wall, path
    return make


@pytest.fixture
def gate(env):
    """Returns a gate with a PIN already set."""
    g = env()
    assert g.set_pin(PIN) == "ok"
    return g


def run(ch, yaws, t0=0.0):
    """Feeds yaws 0.1 s apart and returns the last result."""
    out = False
    for i, y in enumerate(yaws):
        out = ch.update(y, t0 + 0.1 * i)
    return out


def wrong(gate, n):
    """Types the wrong PIN n times and returns the results."""
    return [gate.try_pin(BAD) for _ in range(n)]


def test_no_pin_means_strict(env):
    """With no PIN set no attempt can start, so even perfect turns never pass."""
    ch = HeadTurnChallenge(LEFT, env())
    assert run(ch, PASS) is False and ch.state == "no_pin"


def test_pin_is_not_stored_in_plain_text(gate, env):
    """Neither the file nor its decrypted record contains the PIN."""
    assert PIN.encode() not in env.path.read_bytes() and PIN.encode() not in flip(env.path.read_bytes())


@pytest.mark.parametrize("bad", ["", "12345", "1234567", "abcdef", "12345a", "١٢٣٤٥٦"])
def test_new_pin_must_be_long_enough_digits(env, bad):
    """PINs that are not exactly 6 digits are refused and nothing is written."""
    assert env().set_pin(bad) == "invalid" and not env.path.exists()


def test_first_attempt_needs_no_pin(gate):
    """With nothing failed, 3 correct turns pass without a PIN."""
    assert run(HeadTurnChallenge(LEFT, gate), PASS) is True and gate.status() == "ok" and not gate.failed


def test_failure_requires_pin_and_pin_alone_never_unlocks(gate):
    """After a failure perfect turns are refused until the PIN, and after the PIN all 3 turns are still needed."""
    ch = HeadTurnChallenge(LEFT, gate)
    run(ch, [0.0, -0.4, -0.4, -0.4])
    assert run(ch, PASS, 10.0) is False and ch.state == "pin"
    assert gate.try_pin(PIN) == "ok"
    assert run(ch, ONE_TURN * 2, 20.0) is False
    assert run(ch, ONE_TURN, 21.0) is True and not gate.failed


def test_second_failure_after_pin_needs_pin_again(gate):
    """A correct PIN allows only one new attempt."""
    ch = HeadTurnChallenge(LEFT, gate)
    run(ch, [0.0, -0.4, -0.4, -0.4])
    gate.try_pin(PIN)
    run(ch, [0.0, -0.4, -0.4, -0.4], 10.0)
    assert run(ch, PASS, 20.0) is False and ch.state == "pin"


def test_pin_required_survives_restart(gate, env):
    """Restarting the app after a failure does not give a free attempt."""
    run(HeadTurnChallenge(LEFT, gate), [0.0, -0.4, -0.4, -0.4])
    assert env().status() == "pin"


def test_killing_the_app_mid_attempt_counts(gate, env):
    """Once the first turn has been shown, a restart with no clean shutdown still needs the PIN."""
    HeadTurnChallenge(LEFT, gate).update(0.0, 0.0)
    assert env().status() == "pin"


def test_restart_before_first_turn_is_free(gate, env):
    """If no side was shown yet, a restart needs no PIN."""
    HeadTurnChallenge(LEFT, gate).update(0.5, 0.0)
    assert env().status() == "ok"


def test_leaving_view_mid_attempt_requires_pin(gate):
    """Taking the face away after a side is shown cannot be used to drop a bad attempt."""
    bank = ChallengeBank(LEFT, gate)
    bank.update("Oran", 0.0, 0.0)
    bank.keep_only([], 0.1 + config.CHALLENGE_GRACE_S)
    assert gate.status() == "pin"


def test_passed_then_left_view_needs_turns_but_no_pin(gate):
    """Dropping an earned pass is not a failure."""
    ch = HeadTurnChallenge(LEFT, gate)
    run(ch, PASS)
    ch.release()
    assert gate.status() == "ok"


def test_grant_expires(gate, env):
    """A correct PIN that is not used soon stops allowing an attempt."""
    gate.fail(object())
    gate.try_pin(PIN)
    env.mono.t += config.PIN_GRANT_S + 1
    assert gate.status() == "pin"


def test_lockout_grows_and_the_last_step_repeats(gate, env):
    """Every 3 wrong PINs lock entry for 1, 5, 15, 60 and then 60 minutes, and the right PIN is refused while locked."""
    gate.fail(object())
    for expected in (60, 300, 900, 3600, 3600):
        assert wrong(gate, 3) == ["wrong", "wrong", "locked"]
        assert gate.lock_left() == pytest.approx(expected) and gate.try_pin(PIN) == "locked" and gate.status() == "locked"
        env.mono.t += expected + 1
        env.wall.t += expected + 1


def test_correct_pin_resets_the_count(gate, env):
    """After a correct PIN the next lockout starts again from 3 tries and 1 minute."""
    wrong(gate, 3)
    env.mono.t += 61
    wrong(gate, 2)
    assert gate.try_pin(PIN) == "ok"
    assert wrong(gate, 3) == ["wrong", "wrong", "locked"] and gate.lock_left() == pytest.approx(60)


def test_lockout_and_wrong_count_survive_restart(gate, env):
    """Restarting neither clears a lockout nor resets the wrong tries."""
    wrong(gate, 2)
    again = env()
    assert again.try_pin(BAD) == "locked"
    assert env().lock_left() == pytest.approx(60)


def test_changing_the_computer_clock(gate, env):
    """While running, the wall clock has no effect; after a restart a clock set backwards cannot stretch the lock past its step."""
    wrong(gate, 3)
    env.wall.t += 10_000
    assert gate.lock_left() == pytest.approx(60)
    env.wall.t -= 100_000
    assert env().lock_left() == pytest.approx(60)


@pytest.mark.parametrize("junk", [b"", b"garbage", flip(b'{"salt": "00"}'), flip(b"[1, 2]")])
def test_damaged_file_stays_strict_and_is_not_overwritten(env, junk):
    """An unreadable record refuses everything, including setting a new PIN, and is left as it was."""
    env.path.write_bytes(junk)
    g = env()
    assert g.status() == "error" and g.try_pin(PIN) == "error" and g.set_pin(PIN) == "error"
    assert run(HeadTurnChallenge(LEFT, g), PASS) is False and env.path.read_bytes() == junk


def test_unwritable_file_shows_no_turn_and_stays_strict(gate):
    """If the attempt cannot be recorded, no side is revealed and nothing passes."""
    def refuse(data):
        """Fails like a full or protected disk."""
        raise OSError("no")

    gate.encrypt = refuse
    ch = HeadTurnChallenge(LEFT, gate)
    assert run(ch, PASS) is False and ch.state == "error" and ch.revealed is False


def test_deleted_file_means_no_pin(gate, env):
    """Deleting the file leaves the next start with no PIN, which is strict, rather than a cleared lockout."""
    env.path.unlink()
    assert env().status() == "no_pin"


def test_second_adult_cannot_pass_away_a_failure(gate):
    """An attempt that started without a PIN does not clear a failure that happens while it runs."""
    first, second = HeadTurnChallenge(LEFT, gate), HeadTurnChallenge(LEFT, gate)
    first.update(0.0, 0.0)
    second.state = "prompting"
    gate.fail(second)
    assert run(first, [0.4] * 3 + ONE_TURN * 2, 0.1) is True and gate.failed


def test_pin_entry_hides_digits_and_submits(gate):
    """Typed digits show as stars, Backspace removes one, and Enter submits."""
    gate.fail(object())
    entry = PinEntry(gate)
    for c in PIN[:5] + "9":
        entry.key(ord(c))
    entry.key(8)               # remove the mistyped sixth digit
    entry.key(ord(PIN[5]))
    assert "******" in entry.text() and not any(c in entry.text() for c in PIN)
    entry.key(13)
    assert gate.status() == "ok" and entry.digits == ""


def test_pin_entry_asks_for_six_digits_and_short_entry_costs_nothing(gate):
    """The window asks for a 6-digit PIN, takes no seventh digit, and a short entry is not counted as a wrong PIN."""
    gate.fail(object())
    entry = PinEntry(gate)
    assert "6-digit PIN" in entry.text()
    for c in "123":
        entry.key(ord(c))
    entry.key(13)
    assert entry.text().startswith("Too short") and gate.record["wrong"] == 0 and entry.digits == "123"
    for c in "456789":
        entry.key(ord(c))
    assert entry.digits == "123456"


def test_pin_entry_ignores_keys_when_no_pin_is_wanted(gate):
    """Keys typed when nothing has failed are not collected or counted."""
    entry = PinEntry(gate)
    for c in BAD:
        entry.key(ord(c))
    entry.key(13)
    assert entry.digits == "" and gate.record["wrong"] == 0


def test_set_pin_script_needs_the_old_pin_and_keeps_pin_required(gate, env):
    """Changing the PIN with a wrong current PIN is refused, and a successful change does not clear a pending failure."""
    gate.fail(object())
    answers = iter([BAD, "135790", "135790"])
    assert set_pin.main(env(), lambda _: next(answers)) == 1
    answers = iter([PIN, "135790", "135790"])
    assert set_pin.main(env(), lambda _: next(answers)) == 0
    again = env()
    assert again.status() == "pin" and again.try_pin(PIN) == "wrong" and again.try_pin("135790") == "ok"


def test_lock_seconds_levels():
    """Levels map to the configured steps."""
    assert [pin.lock_seconds(n) for n in (1, 2, 3, 4, 9)] == [60, 300, 900, 3600, 3600]


def test_real_windows_encryption_round_trip(tmp_path):
    """The default Windows encryption saves and reloads the record."""
    path = tmp_path / "security.bin"
    assert PinGate(path).set_pin(PIN) == "ok"
    assert PinGate(path).try_pin(PIN) == "ok"
