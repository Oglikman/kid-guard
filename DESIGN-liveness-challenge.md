# Design: active liveness challenge (head turn)

Status: DRAFT for owner approval. No code written. Not yet reflected in PRD.md (see "PRD changes needed").
Date: 2026-11-23 · Owner: Oran

## 1. Why

Measured on this webcam today (`prototype/liveness_scores.json`, 364 scored frames): the MiniFASNet check accepts **76% of phone-photo frames** at the current 0.5 threshold. The best single threshold found (0.99) still accepts 9% of photo frames and rejects 42% of real frames. Results on photos also vary run to run (median 0.00 to 0.99). A threshold cannot fix this. Video replay is not yet measured.
A passive single-frame score is not a reliable defence against a photo of an enrolled adult. A still photo cannot respond to a request, so we ask for one.

## 2. Idea

Before an adult can unlock the normal profile, they must turn their head to a randomly chosen side (left or right) within a time limit. We estimate head yaw from the 5 YuNet landmarks every frame and require a clear turn in the requested direction and a return to centre.

**Why a flat photo fails.** The nose tip sits in front of the eye plane on a real head, so when the head turns the nose moves sideways relative to the eyes. On a flat photo (even tilted or moved), eyes and nose stay in the same plane, so the ratio below barely changes, except for perspective effects.

Yaw proxy, per frame, from landmarks (right eye `re`, left eye `le`, nose `n`, image x coordinates):

    yaw_ratio = (n.x - (re.x + le.x) / 2) / (le.x - re.x)      # ~0 facing camera, sign gives direction

## 3. Flow

1. Identity match says "adult X" (existing F2). MiniFASNet score is kept as a cheap first gate but is no longer trusted alone.
2. If X is not currently "challenge-passed": state becomes `challenge` (still **strict**), and a random direction is chosen with a CSPRNG (`secrets`).
3. The user is prompted ("Turn your head to the LEFT"). Within `CHALLENGE_TIMEOUT_S` (default 6 s) we need:
   a. a neutral phase: |yaw_ratio| < 0.10 for at least 1 frame (originally 3; lowered 2026-11-26 because a quick pass through the centre may have caused live failures, not confirmed),
   b. then a turn: yaw_ratio beyond +/-0.25 in the **requested** direction for at least 3 frames,
   c. the same face identity (SFace match to X) on those frames, so the face cannot be swapped mid-challenge.
4. Pass -> X is "challenge-passed" -> normal unlock rules continue (5 consecutive adult frames, F5).
5. Fail or timeout -> stays strict; new challenge allowed after a short cooldown (5 s); after 3 fails in 60 s, a 60 s lockout. Failing never makes anything less strict.
6. "Challenge-passed" is dropped when the adult leaves view (existing `keep_only` behaviour), or after `REVERIFY_MINUTES` (default off, proposed 30) while still in view, and whenever any other face appears with the adult (child + adult -> strict already, F4).

The numbers (0.10, 0.25, 6 s, 1 and 3 frames) are starting guesses; they are tuned in section 6, not claimed.

## 4. Where it fits in the code

- `kidguard/challenge.py` (new): yaw proxy, challenge state machine (`idle -> prompting -> passed / failed`), cooldown and lockout. Pure functions plus one small class, unit-testable with synthetic landmark sequences, no camera needed.
- `kidguard/liveness.py`: unchanged. `SmootherBank` stays as the first gate.
- `run.py` `label_frame`: an adult who has not passed the challenge counts as unknown (same pattern as the existing "not live" rule). Passes `face_row[4:14]` landmarks to the challenge object.
- `kidguard/config.py`: new constants (`CHALLENGE_TIMEOUT_S`, `YAW_NEUTRAL`, `YAW_TURN`, `CHALLENGE_FRAMES`, cooldown, lockout) and a `--no-challenge` development flag mirroring `--no-liveness`.
- `kidguard/state.py` / `state.json`: add `challenge: {"state": ..., "direction": ...}` so other components can show the prompt. Old readers ignore it.
- `evaluate.py`: new `ccollect` / `creport` commands (see section 6). Scores only, no images.
- Every new function gets a one-sentence description (standing rule).

## 5. Open decisions for the owner

1. **Where the prompt is shown.** `run.py --seconds N` (used for browser tests) has no window. Options: (a) show the prompt in the existing camera window only, (b) also show it in the browser via the extension (reads `challenge` from state.json through the native host), (c) a Windows toast notification. Recommendation: (a) now, (b) later.
2. **Re-verification interval** while the adult stays in view: never (convenient) vs every 30 min (safer). Recommendation: every 30 min.
3. **Accessibility.** A head-turn is hard for some adults. Proposed fallback: none in v1 (they stay in the strict profile, which is the safe failure). Parent PIN (F9) could later be the alternative path. Needs your decision.
4. **Blink as a second challenge** would need a facial-landmark model with eyelid points (e.g. MediaPipe Face Mesh). That is an ML library choice, so it is not in this design; ask before adding.

## 6. How we will measure it (acceptance)

Same style as the liveness data already collected: `py evaluate.py ccollect --kind {live,photo,video} --note ...` runs the challenge N times and logs pass/fail plus the yaw-ratio range reached.

Proposed acceptance (for you to approve or change):
- Live adult: passes the challenge in >= 95% of attempts in normal, dim and angled conditions (at least 20 attempts each).
- Phone photo (bright and dim, held still, tilted, moved side to side): **0 passes in 50 attempts** per setup. Note: 0 in 50 only supports a pass-rate below ~6% with 95% confidence; it does not prove it is zero.
- Video replay of the owner turning left and right: measured and reported, no target set yet because we expect it may pass (see limits).
- Time to unlock for a real adult: reported (target under 4 s of added delay, to be confirmed).
Thresholds in section 3 are tuned on one set of data and then checked on a second, separate session, otherwise the numbers look better than reality.

## 7. Honest limits (what this does not stop)

- **Video replay.** A video of the enrolled adult turning left then right, played on a phone, could pass. Randomising the direction and the time limit makes it harder (the attacker needs the right clip ready), but does not make it impossible. Not measured yet.
- **3D masks, deepfakes, live face-swap software:** not addressed.
- **A person who is actually there** (a child with the parent's cooperation, or an adult who leaves the room right after unlocking): out of scope, same as before.
- Yaw from 5 landmarks is coarse; glasses, hair or odd head shapes can shift thresholds. Real false-reject rates are unknown until measured.
- This is a prototype, not a security product; no legal or privacy review done. The challenge uses no new data beyond landmarks already computed per frame; nothing is stored beyond pass/fail and scores.

## 8. PRD changes needed (NOT applied; awaiting approval)

- F13: reword to "an active head-turn challenge must be passed before the normal profile unlocks" and record the measured MiniFASNet result (76% of photo frames accepted at 0.5) as the reason.
- New F14 (challenge timeout, cooldown and lockout are fail-safe) and updated section 6 (measured liveness data) and section 7 (video replay limit).
- Regenerate `PRD.docx` from `PRD.md` afterwards, and keep `SPEC.md` and `prompt.md` consistent (standing rule).

## 9. Build order

1. Approve this design and the PRD wording.
2. Update PRD.md + docx.
3. `challenge.py` + unit tests with synthetic landmark sequences.
4. Wire into `run.py`; manual test in the camera window.
5. `ccollect` / `creport`, collect data, tune, then verify on a separate session.
6. Update READMEs with measured results.
