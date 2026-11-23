# KidGuard face-match prototype (step 1)

Local webcam -> detect face -> match against enrolled family members -> adult / child / unknown / none -> normal or strict profile.
Uses OpenCV YuNet (detect) + SFace (recognise). Everything runs on this PC; frames are never saved or uploaded.

## Run (Windows; use `py`, not `python`, on this machine)
```
py -m pip install -r requirements.txt
py fetch_models.py                 # downloads + hash-checks the two ONNX models
py -m pytest -q                    # unit tests, no camera needed
py enroll.py Oran adult            # consent prompt, then ~8 samples; press q to cancel
py enroll.py Sam child
py run.py                          # live window; q to quit
py benchmark.py --frames 60        # latency + score stats
```

## Behaviour
- Fail-safe: no face, unknown face, camera error -> **strict** profile. A child in frame with an adult -> strict.
- Unlock needs 5 consecutive "adult" frames; locking is immediate.
- Templates: embeddings only, encrypted with Windows DPAPI (this Windows user only) in `templates.bin`. Delete the file to erase everyone.
- Match threshold defaults to SFace's documented cosine 0.363; tune it from `benchmark.py` output.

## Honest limits
- **No liveness check yet:** a photo or video of an enrolled adult can fool it.
- Accuracy depends on lighting, angle and distance; very similar-looking relatives (siblings, parent/child) may need a higher threshold.
- Prototype only: not a security product, no legal/privacy review done.
