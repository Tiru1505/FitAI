# FitAI — review demo script (one page)

## Before the reviewer arrives

```powershell
cd C:\Users\tirup\OneDrive\Desktop\fitai
backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --port 8000   # terminal 1
cd frontend; npm run dev                                                                 # terminal 2
```

- [ ] Backend log says `exercise classifier: loaded` · app opens at http://localhost:5173 (**Chrome or Edge**, not a preview pane)
- [ ] Account created, profile filled, plan generated, safety notice accepted — **do not do this live**
- [ ] Camera tested: whole body in frame, side-on, 1280×720 selected in the Camera card
- [ ] Open in tabs: `ml/results/pipeline_demo_20260918_230557/execution_log.txt`, `RESULTS.md`, the 4 confusion-matrix PNGs, `docs/EVALUATION_REPORT.md`
- [ ] Backup screen recording ready in case the live demo fails
- [ ] Terminal already `cd`-ed into the project folder

---

## Running order (~10 min)

**1 · The data — 1 min.** Open `ml/data/landmarks/mmfit.csv`.
> "Every row is one video frame: 33 body points, each with x, y and a visibility score. This is MM-Fit, a public gym dataset — 21 workouts, 310 exercise sets, 197,862 frames, covering the five exercises FitAI supports."

**2 · Run the pipeline — 2 min.** (Short run; say so.)
```powershell
ml\.venv\Scripts\python.exe ml/scripts/run_pipeline_demo.py --landmarks ml/data/landmarks/mmfit.csv --val-participants w14 w15 w19 --test-participants w00 w05 w12 w13 w20 --models baseline bilstm --epochs 3 --batch-size 64
```
> "Three epochs so it finishes while we talk. The numbers I'll report come from the full 30-epoch run."

While it runs, explain preprocessing: **centre on the hips** (position stops mattering) → **divide by body size** (height stops mattering) → **cut into 2-second windows** → each window is 60 frames × 99 numbers.

**3 · The real log — 2 min.** `execution_log.txt`. Point at the split table:
> "7,786 training windows, 1,862 validation, 2,472 test. The test workouts are people the model never trained on."

**4 · Results — 2 min.** `RESULTS.md` + confusion matrices.

**5 · The app — 3 min.** Live session → camera → 3–5 squats → reps climb, feedback appears → finish → rate difficulty → **show the plan adapting with its written reason** → Progress page charts.

---

## The numbers (test = 5 unseen-subject workouts, 2,472 windows)

| Model | Test macro F1 | Latency |
|---|---|---|
| Logistic regression (baseline) | 0.9915 | 0.16 ms |
| BiLSTM | 0.9883 | 4.0 ms |
| GRU | 0.9993 | 7.9 ms |
| **BiLSTM + augmentation** | **1.0000** | 10.5 ms |

Rep counter vs ground truth, 310 sets: **MAE 1.80, 71.9% within ±1**. Backend tests: **68 passing**.

---

## Say these three before you are asked

1. **The benchmark is easy.** Logistic regression on simple statistics reaches 0.9915, so the deep models are not proven necessary here — studio footage, fixed camera, posturally distinct exercises.
2. **We caught a subject leak.** MM-Fit's 21 workouts come from ~10 people, so splitting by workout ID is not subject-independent. The first results were discarded and re-run on the authors' unseen-subject split.
3. **Squat counting fails head-on.** 17 of 64 squat sets counted zero: a frontal view foreshortens the knee angle. The app already tells users to stand side-on.

---

## Answers ready

| Question | Answer |
|---|---|
| Why a BiLSTM? | Exercise identity is a movement over time, not one frame. Bidirectional so the descent is read together with the ascent. |
| Why not count reps with the network? | Geometry is explainable and debuggable. A wrong angle threshold can be found and fixed; a wrong count from a black box cannot. |
| What did augmentation do? | Mirror, time-warp, scale, rotate, jitter → 7,786 to 23,358 windows; BiLSTM went 0.9883 → 1.0000, at 15× training time. |
| A perfect score? | Augmentation touched only training windows, and no test subject is in training. It means the benchmark is easy, not that the model is flawless. |
| Form classification results? | None yet — the public dataset has only correct-form examples. Next step: record deliberate errors, or use the FMS dataset (CC0, expert-graded). |
| Will it work on any webcam? | Expect worse. It learned from studio poses via a different tracker than the browser uses. |
| What's the confidence number? | The model's probability for the exercise it named. Below 60% the app shows "Not sure". It never affects the rep count. |

---

## If something breaks

- **Camera won't start** → check the browser tab has permission; use http://localhost:5173, not 127.0.0.1; close other apps using the camera. Fall back to manual rep entry, which is a designed feature.
- **Model misnames the exercise live** → say it out loud: domain shift, trained on a different pose tracker. Reps still count, because they never depended on the model.
- **Anything else** → switch to the backup recording and keep talking through the log.
- **Need the model gone fast** → rename `backend/trained_models/exercise_classifier.keras` and restart the backend; the app reports the model as unavailable and uses the rule-based path.
