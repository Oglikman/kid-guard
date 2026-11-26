"""Unit tests for the head-turn challenge (PRD F14): yaw maths, the 3-turn state machine, the wrong-way rule, abandonment and the per-person bank."""
import numpy as np
import pytest

from kidguard import config
from kidguard.challenge import ChallengeBank, HeadTurnChallenge, LockedChallenge, prompt_text, turn_progress, yaw_ratio


def landmarks(yaw: float) -> list:
    """Builds YuNet-style landmarks (right eye, left eye, nose, mouth corners) for a face whose nose is offset by `yaw` eye-distances."""
    return [80, 100, 120, 100, 100 + 40 * yaw, 120, 85, 140, 115, 140]


LEFT = lambda: "left"      # noqa: E731  (fixed direction for tests)
RIGHT = lambda: "right"    # noqa: E731
ONE_TURN = [0.0, 0.4, 0.4, 0.4]                 # face the camera, then 3 turned frames (left)
PASS = ONE_TURN * config.CHALLENGE_STEPS


def scripted(*sides):
    """Returns a chooser that hands out the given sides in order."""
    it = iter(sides)
    return lambda: next(it)


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


def test_passes_only_after_all_three_turns():
    """The pass comes on the last frame of the third turn and not after one or two turns."""
    ch = HeadTurnChallenge(LEFT)
    res, _ = feed(ch, PASS)
    assert res == [False] * (len(PASS) - 1) + [True] and ch.state == "passed"
    ch = HeadTurnChallenge(LEFT)
    res, _ = feed(ch, ONE_TURN * (config.CHALLENGE_STEPS - 1))
    assert not any(res) and ch.step == config.CHALLENGE_STEPS - 1


def test_each_step_follows_its_own_random_side():
    """With sides left, right, left the person must turn each of those ways in turn."""
    ch = HeadTurnChallenge(scripted("left", "right", "left"))
    res, _ = feed(ch, [0.0, 0.4, 0.4, 0.4, 0.0, -0.4, -0.4, -0.4, 0.0, 0.4, 0.4, 0.4])
    assert res[-1] is True


def test_each_step_needs_the_camera_faced_first():
    """Holding the head turned does not carry over into the next step without facing the camera again."""
    ch = HeadTurnChallenge(LEFT)
    feed(ch, ONE_TURN + [0.4] * 10)
    assert ch.step == 1 and ch.phase == "neutral"


def test_wrong_way_turn_fails_at_once():
    """Three frames turned to the wrong side fail the attempt, even if the right side follows."""
    ch = HeadTurnChallenge(LEFT)
    res, _ = feed(ch, [0.0, -0.4, -0.4])
    assert ch.state == "prompting"
    ch.update(-0.4, 0.3)
    assert ch.state == "failed" and ch.fail_reason == "wrong_way" and not any(res)


def test_short_wrong_way_spike_does_not_fail():
    """One or two wrong-side frames, as in a landmark glitch, are tolerated."""
    ch = HeadTurnChallenge(LEFT)
    res, _ = feed(ch, [0.0, -0.4, -0.4, 0.0, -0.4, 0.4, 0.4, 0.4])
    assert ch.step == 1 and ch.fail_reason is None


def test_looped_video_showing_the_wrong_side_on_the_second_turn_fails():
    """A video that turns left then right fails when both requests are 'left'."""
    ch = HeadTurnChallenge(LEFT)
    feed(ch, ONE_TURN + [0.0, -0.5, -0.5, -0.5])
    assert ch.state == "failed" and ch.fail_reason == "wrong_way"


def test_still_photo_never_passes_and_times_out():
    """A face that never moves fails on the step timeout."""
    ch = HeadTurnChallenge(LEFT)
    res, _ = feed(ch, [0.0] * 62)
    assert not any(res) and ch.fail_reason == "timeout"


def test_each_step_gets_its_own_timeout():
    """Three slow but in-time steps pass even though together they take longer than one step's limit."""
    ch = HeadTurnChallenge(LEFT)
    t, passed = 0.0, False
    for _ in range(config.CHALLENGE_STEPS):
        for y in ONE_TURN:
            passed = ch.update(y, t)
            t += config.CHALLENGE_TIMEOUT_S / 5
    assert passed and t > config.CHALLENGE_TIMEOUT_S


def test_single_neutral_frame_while_sweeping_through_centre_is_enough():
    """A head sweeping from one side to the other with only one centred frame can still complete a turn."""
    ch = HeadTurnChallenge(LEFT)
    feed(ch, [-0.8, -0.4, 0.0, 0.4, 0.5, 0.56])
    assert ch.step == 1


def test_swinging_from_other_side_without_a_centred_frame_does_not_count():
    """Jumping from one side to the other with no frame inside the neutral zone never starts the turn phase."""
    ch = HeadTurnChallenge(LEFT)
    feed(ch, [-0.5, -0.2] + [0.4] * 10)
    assert ch.step == 0 and ch.phase == "neutral"


def test_turned_frames_must_be_consecutive():
    """A frame back at centre in the middle of a turn resets the turn count."""
    ch = HeadTurnChallenge(LEFT)
    feed(ch, [0.0, 0.4, 0.4, 0.0, 0.4, 0.4])
    assert ch.step == 0
    ch.update(0.4, 1.0)
    assert ch.step == 1


def test_unusable_frames_do_not_count_or_break_progress():
    """Frames with no usable yaw neither advance nor reset the counters."""
    ch = HeadTurnChallenge(LEFT)
    feed(ch, [0.0, 0.4, None, None, 0.4, 0.4])
    assert ch.step == 1


def test_release_before_first_turn_is_free_but_after_it_is_a_failure():
    """Leaving before any side is shown costs nothing; leaving afterwards fails the attempt."""
    ch = HeadTurnChallenge(LEFT)
    ch.update(0.5, 0.0)
    ch.release()
    assert ch.state == "idle" and ch.fail_reason is None
    ch.update(0.0, 1.0)
    ch.release()
    assert ch.state == "failed" and ch.fail_reason == "abandoned"


def test_pass_persists_then_expires_after_reverify_interval():
    """A pass stays valid while the adult remains in view and expires after the re-verify interval."""
    ch = HeadTurnChallenge(LEFT)
    feed(ch, PASS)
    assert ch.update(0.5, 100.0) is True
    assert ch.update(0.5, config.CHALLENGE_REVERIFY_S + 100.0) is False and ch.state == "prompting" and ch.step == 0


def test_release_drops_pass_without_penalty():
    """Leaving view after a pass drops it without recording a failure."""
    ch = HeadTurnChallenge(LEFT)
    feed(ch, PASS)
    ch.release()
    assert ch.state == "idle" and ch.fail_reason is None


def test_direction_comes_from_chooser_and_default_is_left_or_right():
    """The requested side is whatever the chooser returns, and the default chooser only ever yields 'left' or 'right'."""
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
    bank, t = ChallengeBank(LEFT), 0.0
    for y in PASS:
        bank.update("Oran", y, t)
        t += 0.1
    bank.keep_only([], t + 1.0)
    assert bank.update("Oran", 0.5, t + 1.1) is True
    later = t + 1.2 + config.CHALLENGE_GRACE_S + 0.5
    bank.keep_only([], later)
    assert bank.update("Oran", 0.5, later + 0.1) is False


def test_bank_fails_an_attempt_when_another_face_replaces_the_adult():
    """Several frames in a row showing only another face fail an attempt that is under way."""
    bank = ChallengeBank(LEFT)
    bank.update("Oran", 0.0, 0.0)
    for i in range(config.CHALLENGE_FRAMES - 1):
        bank.keep_only([], 0.1 * (i + 1), face_in_view=True)
    assert bank.prompts(0.3)["Oran"]["state"] == "prompting"
    bank.keep_only([], 0.4, face_in_view=True)
    assert bank.prompts(0.4)["Oran"]["fail_reason"] == "other_face"


def test_bank_release_all_and_people_are_independent():
    """Each person has their own challenge, and release_all drops everyone's pass."""
    bank = ChallengeBank(LEFT)
    for y in PASS:
        bank.update("A", y, 0.0)
    assert bank.update("B", 0.5, 0.0) is False
    bank.release_all()
    assert bank.prompts(0.0)["A"]["state"] == "idle"


def test_locked_challenge_never_passes_or_starts_an_attempt():
    """The no-window stand-in refuses everyone and creates no attempt that could fail."""
    bank = LockedChallenge()
    assert not any(bank.update("Oran", y, 0.0) for y in PASS) and bank.prompts() == {}


def test_prompt_text_covers_each_state():
    """The on-screen text shows the step number and side while prompting and says when an attempt failed."""
    ch = HeadTurnChallenge(LEFT)
    ch.update(0.5, 0.0)
    assert "1/3" in prompt_text(ch.prompt(0.0)) and "look at the camera" in prompt_text(ch.prompt(0.0))
    ch.update(0.0, 0.1)
    assert "LEFT" in prompt_text(ch.prompt(0.2))
    ch.release()
    assert prompt_text(ch.prompt(0.3)) == "Challenge failed"
    assert prompt_text({"state": "idle"}) == ""
