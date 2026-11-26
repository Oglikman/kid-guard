"""Unit tests for the head-turn challenge (PRD F14): yaw maths, the state machine, cooldown/lockout, expiry and the per-person bank."""
import numpy as np
import pytest

from kidguard import config
from kidguard.challenge import ChallengeBank, HeadTurnChallenge, prompt_text, turn_progress, yaw_ratio


def landmarks(yaw: float) -> list:
    """Builds YuNet-style landmarks (right eye, left eye, nose, mouth corners) for a face whose nose is offset by `yaw` eye-distances."""
    return [80, 100, 120, 100, 100 + 40 * yaw, 120, 85, 140, 115, 140]


LEFT = lambda: "left"      # noqa: E731  (fixed direction for tests)
RIGHT = lambda: "right"    # noqa: E731


def feed(ch, yaws, t0=0.0, dt=0.1):
    """Feeds a list of yaw ratios at dt-second spacing and returns (list of results, time after the last frame)."""
    out, t = [], t0
    for y in yaws:
        out.append(ch.update(y, t))
        t += dt
    return out, t


def test_yaw_ratio_zero_when_nose_centred_and_signed_otherwise():
    """A centred nose gives about 0, and moving the nose right or left of centre gives a positive or negative ratio."""
    assert yaw_ratio(landmarks(0.0)) == pytest.approx(0.0)
    assert yaw_ratio(landmarks(0.3)) == pytest.approx(0.3)
    assert yaw_ratio(landmarks(-0.3)) == pytest.approx(-0.3)


@pytest.mark.parametrize("bad", [None, [], [1, 2, 3], [float("nan")] * 10, [120, 100, 80, 100, 100, 120], "abc"])
def test_yaw_ratio_none_for_unusable_landmarks(bad):
    """Missing, short, non-finite or wrongly ordered landmarks give None rather than a made-up number."""
    assert yaw_ratio(bad) is None


def test_turn_progress_direction_and_sign_setting():
    """Turning left counts as progress toward 'left' (and against 'right'), and the sign argument flips it for a mirrored camera."""
    assert turn_progress(0.3, "left", 1.0) == pytest.approx(0.3) and turn_progress(0.3, "right", 1.0) == pytest.approx(-0.3)
    assert turn_progress(0.3, "left", -1.0) == pytest.approx(-0.3)


def test_real_turn_passes_after_neutral_then_turn_frames():
    """Facing the camera and then turning the requested way for 3 frames passes, and not before."""
    ch = HeadTurnChallenge(LEFT)
    res, _ = feed(ch, [0.0] * 3 + [0.4] * 3)
    assert res == [False] * 5 + [True] and ch.state == "passed"


def test_still_photo_never_passes_and_times_out():
    """A face that never moves (a photo) stays in the neutral phase, then fails on timeout and enters cooldown."""
    ch = HeadTurnChallenge(LEFT)
    res, t = feed(ch, [0.0] * 80)                      # 8 s of perfect stillness
    assert not any(res) and ch.state == "cooldown"


def test_wrong_direction_does_not_pass():
    """Turning the opposite way from the request never counts as the turn."""
    ch = HeadTurnChallenge(LEFT)
    res, _ = feed(ch, [0.0] * 3 + [-0.5] * 20)
    assert not any(res) and ch.state != "passed"


def test_already_turned_at_start_must_come_back_to_neutral_first():
    """Starting turned the right way does not skip the neutral phase: neutral frames are needed before a turn counts."""
    ch = HeadTurnChallenge(LEFT)
    res, _ = feed(ch, [0.5] * 20)
    assert not any(res)


def test_single_neutral_frame_while_sweeping_through_centre_is_enough():
    """A head sweeping from one side to the other with only one centred frame can still pass with 3 turned frames."""
    ch = HeadTurnChallenge(LEFT)
    res, _ = feed(ch, [-0.8, -0.4, 0.0, 0.4, 0.5, 0.56])
    assert res == [False] * 5 + [True]


def test_swinging_from_other_side_without_a_centred_frame_does_not_pass():
    """Jumping from one side to the other with no frame inside the neutral zone never starts the turn phase."""
    ch = HeadTurnChallenge(LEFT)
    res, _ = feed(ch, [-0.5, -0.2] + [0.4] * 10)
    assert not any(res) and ch.phase == "neutral"


def test_frames_must_be_consecutive_in_each_phase():
    """A frame back in the neutral zone in the middle of the turn phase resets the turn count."""
    ch = HeadTurnChallenge(LEFT)
    res, _ = feed(ch, [0.0] * 3 + [0.4, 0.4, 0.0, 0.4, 0.4])
    assert not any(res)
    res, _ = feed(ch, [0.4], t0=1.0)
    assert res == [True]             # the count restarted at the neutral frame; two turned frames since, so one more is the third


def test_unusable_frames_do_not_count_or_break_progress():
    """Frames with no usable yaw neither advance nor reset the counters, so a brief detection gap during the turn does not fail the person."""
    ch = HeadTurnChallenge(LEFT)
    res, _ = feed(ch, [0.0] * 3 + [0.4, None, None, 0.4, 0.4])
    assert res[-1] is True


def test_cooldown_blocks_then_new_attempt_after_it():
    """After a failure the challenge refuses for the cooldown, then starts a fresh attempt."""
    ch = HeadTurnChallenge(LEFT)
    _, t = feed(ch, [0.0] * 70)                        # fails at ~6 s
    assert ch.state == "cooldown"
    assert ch.update(0.0, t + 1.0) is False and ch.state == "cooldown"
    ch.update(0.0, t + config.CHALLENGE_COOLDOWN_S + 0.1)
    assert ch.state == "prompting"


def test_repeated_failures_trigger_lockout_that_survives_leaving_view():
    """Three failures in the window lock the person out, and release() (leaving view) does not clear the lockout."""
    ch = HeadTurnChallenge(LEFT)
    t = 0.0
    for _ in range(config.CHALLENGE_MAX_FAILS):
        _, t = feed(ch, [0.0] * 3, t0=t)
        t += config.CHALLENGE_TIMEOUT_S + 0.5
        ch.update(0.0, t)                              # timeout -> fail
        t += config.CHALLENGE_COOLDOWN_S + 0.5
    assert ch.state == "locked"
    ch.release()
    assert ch.state == "locked"
    res, _ = feed(ch, [0.0] * 3 + [0.4] * 5, t0=t)    # even a perfect turn is refused while locked
    assert not any(res)


def test_pass_persists_then_expires_after_reverify_interval():
    """A pass stays valid while the adult remains in view, and expires after the re-verify interval, requiring a new challenge."""
    ch = HeadTurnChallenge(LEFT)
    feed(ch, [0.0] * 3 + [0.4] * 3)
    assert ch.update(0.0, 100.0) is True
    assert ch.update(0.0, config.CHALLENGE_REVERIFY_S + 100.0) is False and ch.state == "prompting"


def test_release_drops_pass():
    """Leaving view drops a pass so the adult has to do the challenge again."""
    ch = HeadTurnChallenge(LEFT)
    feed(ch, [0.0] * 3 + [0.4] * 3)
    ch.release()
    assert ch.state == "idle"


def test_direction_comes_from_chooser_and_default_is_left_or_right():
    """The requested direction is whatever the chooser returns, and the default chooser only ever yields 'left' or 'right'."""
    ch = HeadTurnChallenge(RIGHT)
    ch.update(0.0, 0.0)
    assert ch.direction == "right"
    seen = set()
    for _ in range(60):
        d = HeadTurnChallenge()
        d.update(0.0, 0.0)
        seen.add(d.direction)
    assert seen == {"left", "right"}


def test_bank_grace_period_keeps_pass_for_short_gaps_only():
    """A short gap in detection keeps the pass; a gap longer than the grace period drops it."""
    bank = ChallengeBank(LEFT)
    t = 0.0
    for y in [0.0] * 3 + [0.4] * 3:
        bank.update("Oran", y, t)
        t += 0.1
    bank.keep_only([], t + 1.0)
    assert bank.update("Oran", 0.0, t + 1.1) is True
    bank.keep_only([], t + 1.2 + config.CHALLENGE_GRACE_S + 0.5)
    assert bank.update("Oran", 0.0, t + 1.3 + config.CHALLENGE_GRACE_S + 0.5) is False


def test_bank_release_all_and_people_are_independent():
    """Each person has their own challenge, and release_all drops everyone's pass."""
    bank = ChallengeBank(LEFT)
    for y in [0.0] * 3 + [0.4] * 3:
        bank.update("A", y, 0.0)
    assert bank.update("B", 0.0, 0.0) is False
    bank.release_all()
    assert bank.prompts(0.0)["A"]["state"] == "idle"


def test_prompt_text_covers_each_state():
    """The on-screen text names the direction while prompting and mentions cooldown and lockout when they apply."""
    ch = HeadTurnChallenge(LEFT)
    ch.update(0.5, 0.0)              # starts off-centre, so the person is first asked to face the camera
    assert "Look at the camera" in prompt_text(ch.prompt(0.0))
    ch.update(0.0, 0.1)              # one centred frame is enough to move on to the turn
    assert "LEFT" in prompt_text(ch.prompt(0.2))
    assert prompt_text({"state": "idle", "direction": None, "phase": "neutral", "seconds_left": None}) == ""
