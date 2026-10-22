# FitAI evaluation report (template)

> **Run 1 (MM-Fit, public dataset) is filled in with measured values** from
> `ml/results/pipeline_demo_20260918_230557/`. The custom webcam dataset rows are still `TBD`.
> Fill every remaining `TBD` with values **measured** by the scripts in `ml/scripts/` or from real test sessions.
> Do not estimate, round up or copy numbers from other papers. Leave a field as `TBD` or "not measured"
> if you did not measure it.

## 1. Datasets

| Dataset | Source / URL | Licence & consent | Participants | Exercises | Form classes | Recording conditions | Frames / windows |
|---|---|---|---|---|---|---|---|
| Custom landmarks (B) | collected via FitAI tool / extract_landmarks.py | TBD (consent process) | TBD | TBD | TBD | TBD | TBD |
| **Public (A): MM-Fit** (used) | https://mmfit.github.io/ (Strömbäck, Huang & Radu, IMWUT 2020) | Public research dataset; cite the paper | 21 workouts (w00-w20) | 5 of 10 used: squat, lunge, push-up, shoulder press, biceps curl | correct only (no error labels) | Indoor gym, single frontal RGB-D camera, 2D pose 18 joints | 310 sets / 197,862 frames / 12,120 windows |
| Nutrition (C) | USDA FoodData Central SR Legacy 2018-04, accessed 2026-09-17 | Public domain (CC0) | n/a | n/a | n/a | n/a | 147 foods |

**MM-Fit run:** the split is the one defined by the MM-Fit authors, whose test workouts come from
**subjects not present in training** (`--unseen_test_set` in their reference code):

| Split | Workouts | Windows |
|---|---|---|
| Train | w01, w02, w03, w04, w06, w07, w08, w16, w17, w18 | 7,786 |
| Validation | w14, w15, w19 | 1,862 |
| **Test (unseen subjects)** | **w00, w05, w12, w13, w20** | **2,472** |

Sequence length 60 frames, stride 15. Windows dropped for low visibility: 0.

> **Why this split matters.** MM-Fit contains 21 workouts recorded by only ~10 people, so several
> workouts share a subject. Splitting on workout ID alone does **not** guarantee subject-independent
> testing. An earlier run of this project used w18-w20 as the test set and reported macro F1 of 0.865
> (baseline), 0.551 (BiLSTM) and 0.794 (GRU); those numbers are **withdrawn** because two of those
> workouts appear in the authors' training list and their subjects therefore also occur in training.
> Always use the authors' unseen-subject split, or a grouping by subject if a workout-to-subject
> mapping is obtained.

## 2. Exercise classifier (test participants only)

**MM-Fit run** (test = 5 unseen-subject workouts, 2,472 windows), 5 classes:

| Model | Val macro F1 | Accuracy | Macro precision | Macro recall | Macro F1 | Latency p50 / p95 (ms) | Train time (epochs) |
|---|---|---|---|---|---|---|---|
| Baseline (logistic regression on window statistics) | 0.9877 | 0.9895 | 0.9901 | 0.9932 | **0.9915** | 0.159 / 0.321 | 0.2 s |
| BiLSTM (primary) | 0.9346 | 0.9879 | 0.9857 | 0.9912 | **0.9883** | 4.025 / 5.658 | 85 s (15 epochs) |
| GRU (comparison) | 0.9752 | 0.9992 | 0.9995 | 0.9991 | **0.9993** | 7.936 / 9.610 | 101 s (15 epochs) |
| BiLSTM + augmentation & regularisation | 1.0000 | 1.0000 | 1.0000 | 1.0000 | **1.0000** | 10.516 / 11.919 | 1,315 s (30 epochs) |

**Ablation — augmentation and regularisation (BiLSTM):** adding mirroring, time-warping, scaling,
rotation and jitter (2 augmented copies: 7,786 → 23,358 training windows) with dropout 0.5, recurrent
dropout 0.25 and L2 1e-4 raised test macro F1 from 0.9883 to 1.0000 (all 2,472 test windows correct;
confusion matrix is perfectly diagonal). The cost is 15x training time (85 s → 1,315 s) and ~2.6x
inference latency versus the plain BiLSTM. On a benchmark where the baseline already scores 0.9915,
this is a small absolute gain; the technique matters more for the harder, view-varied webcam data the
app will actually see.

Per-class F1 (test):

| Model | biceps curl | lunge | push-up | shoulder press | squat |
|---|---|---|---|---|---|
| Baseline | 0.9941 | 0.9827 | 1.000 | 1.000 | 0.9806 |
| BiLSTM | 0.9826 | 0.9854 | 0.9949 | 0.9890 | 0.9896 |
| GRU | 0.9976 | 0.9987 | 1.000 | 1.000 | 1.000 |
| BiLSTM + augmentation | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

Confusion matrices: `ml/results/pipeline_demo_20260918_230557/` — `baseline_confusion_matrix.png`,
`bilstm_confusion_matrix.png`, `gru_confusion_matrix.png`, `bilstm_aug_confusion_matrix.png`

**Observation to discuss — the task is easy on this dataset.** Every model exceeds 0.98 macro F1,
and plain logistic regression on per-window mean/std/min/max reaches 0.9915. MM-Fit's five exercises
are separable by static posture alone (lying vs standing, arms overhead vs at the sides), recorded in
a studio with one fixed camera and consistent framing, so temporal modelling adds little. The deep
models are **not** demonstrated to be necessary here. A harder benchmark, form-error classification
(where the difference between a correct and an incorrect squat *is* temporal), is the setting where a
recurrent model should earn its place — and that needs recordings with incorrect-form labels, which
MM-Fit does not contain.

**Selected model for the app:** BiLSTM + augmentation — highest test macro F1 (1.0000) and the variant
most likely to survive the change of camera and viewpoint, since augmentation is exactly what trains for
that. At ~10.5 ms per 60-frame window it leaves ample headroom for ~15 fps live inference. It is
exported to `backend/trained_models/`. (The scikit-learn baseline is competitive at 0.9915 but is not
served by the API.)

## 3. Form classifiers (per exercise, test participants)

| Exercise | Classes | Per-class precision / recall | Macro F1 | Notes |
|---|---|---|---|---|
| Squat | TBD | TBD | TBD | TBD |
| Lunge | TBD | TBD | TBD | TBD |
| Push-up | TBD | TBD | TBD | TBD |
| Biceps curl | TBD | TBD | TBD | TBD |
| Shoulder press | TBD | TBD | TBD | TBD |

Rule-based form checks compared on the same recordings (if measured): TBD

## 4. Repetition counter (`evaluate_rep_counter.py`)

**MM-Fit run**, all 310 sets against MM-Fit's ground-truth counts (10 reps per set):

| Exercise | Samples | MAE (reps) | % within ±1 | Sets counted as 0 | MAE excluding those |
|---|---|---|---|---|---|
| Overall | 310 | 1.80 | 71.9% | 21 | 1.21 |
| Squat | 64 | 3.73 | 57.8% | 17 | 1.49 |
| Lunge | 62 | 0.36 | 91.9% | 0 | 0.36 |
| Push-up | 65 | 3.09 | 46.2% | 3 | 2.76 |
| Biceps curl | 59 | 0.00 | 100% | 0 | 0.00 |
| Shoulder press | 60 | 1.60 | 66.7% | 1 | 1.46 |

**Failure analysis:** 21 of 310 sets counted zero repetitions, 17 of them squats. MM-Fit records from a
single frontal camera, where the knee angle is foreshortened and never crosses the depth threshold
(160° start, 100° target), so the state machine never completes a repetition. The counter never
over-counts squats (0 of 64), which is consistent with a threshold that is too strict for this view
rather than with noise. Front-facing exercises whose movement happens in the image plane (biceps curl,
lunge) are near-perfect. Fix options: view-aware thresholds, using the 3D pose, or prompting the user
to stand side-on, which is what the FitAI app already advises.

### 4b. Threshold tuning experiment (`tune_rep_counter.py`)

The counter's joint angles were set by hand from textbook ranges. A grid search over the start and
target thresholds, smoothing window and hysteresis was run **on the training workouts only**, then
scored on the five unseen-subject workouts — searching over everything and quoting the best figure
would be fitting the test set.

| Exercise | Start (hand → tuned) | Target (hand → tuned) | Test MAE | Within ±1 | Zero-count sets |
|---|---|---|---|---|---|
| Squat | 160° → 165° | 100° → **140°** | 5.53 → **2.40** | 40% → 60% | 4 → 1 |
| Lunge | 160° → 140° | 105° → 95° | 0.67 → **0.53** | 87% → 80% | 0 → 0 |
| Push-up | 150° → 145° | 95° → **115°** | 2.67 → **2.07** | 67% → 80% | 2 → 2 |
| Biceps curl | 150° → 130° | 65° → 55° | 0.00 → **0.00** | 100% → 100% | 0 → 0 |
| Shoulder press | 105° → 95° | 155° → **135°** | 3.42 → **0.25** | 25% → 100% | 0 → 0 |
| **Overall** | | | **2.49 → 1.11** (−55%) | | 6 → 3 |

**Interpretation — and why these values are not simply adopted.** Every tuned target moved toward a
*shallower* requirement: squat 100° → 140°, push-up 95° → 115°, shoulder press 155° → 135°. That is
exactly what a single head-on camera predicts, because foreshortening compresses the measured joint
angle, so a genuinely deep squat never reaches 100° on screen. The tuning has therefore measured
MM-Fit's camera geometry as much as it has measured good thresholds.

Adopting 140° for squats would make the live app count a quarter-squat as a repetition for a user
standing side-on, where the true angle *is* available. The defensible conclusion is that **the
threshold should depend on the viewpoint**, not that the hand-set values were wrong. Options, in
increasing order of merit:

1. Ship a per-dataset threshold profile (frontal vs side), selected from the detected view.
2. Calibrate per session: observe the user's own angle range over the first repetition and set the
   thresholds as a fraction of it. This removes the fixed constants entirely and adapts to body
   proportions and camera placement at once.

Raw grid-search output: `ml/results/rep_counter_tuning.json`.

## 5. Live inference (from `workout_sessions.inference_stats`)

| Metric | Value | Notes |
|---|---|---|
| Avg. server processing per frame (ms) | 0.71 | Rule-based pipeline only (no model loaded), 153 frames |
| Client dropped-frame ratio | 0.0 | Client sends at ~15 fps with back-pressure |
| Low-visibility frame ratio | 0.0 | Synthetic landmarks, always fully visible |
| Frames analysed per second | TBD | **Measure in a real webcam session** |

> These came from a scripted session that pushed synthetic landmarks through the live WebSocket to
> verify the path end to end — **not** from a webcam session, and with no model loaded. Re-measure with
> the GRU loaded and a real camera; per-window model inference alone is ~8 ms (section 2), so expect a
> higher figure. Live values are stored per session in `workout_sessions.inference_stats`.

## 6. Recommender

| Check | Result |
|---|---|
| Constraint satisfaction (equipment, exclusions, session length) | TBD (automated tests: `tests/test_recommender_and_nutrition.py`) |
| Expert review (who, how many plans) | TBD |
| User-rated relevance (n, scale, mean) | TBD |
| ML comparison (`train_recommender.py`), if data collected | TBD |

## 7. Adaptive coaching

| Metric | Result |
|---|---|
| Completion-rate trend across sessions | TBD |
| Form-score trend | TBD |
| Explanation correctness (reviewed decisions correct / total) | TBD |

## 8. System

| Metric | Result |
|---|---|
| API median response time (key endpoints) | TBD |
| API error rate during testing | TBD |
| Usability test (participants, tasks, SUS or similar) | TBD |
| Automated tests | 68 passed (`pytest -q`, backend suite) |

## 9. Error cases and limitations

**MM-Fit run:**

- The dataset is filmed from a single frontal camera, so side-view geometry is unavailable. This is the
  direct cause of the 17 squat sets counted as zero repetitions.
- MM-Fit contains **no incorrect-form examples**, so the form classifier could not be trained from it.
  Form feedback in the app remains the rule-based geometric checks.
- MM-Fit poses come from a different pose estimator (18-joint OpenPose-style) than the live app
  (33-joint MediaPipe). Unmapped MediaPipe slots are filled with visibility 0, so a model trained on
  MM-Fit sees a sparser input than webcam data. Expect degraded accuracy in the live app until a model
  is trained on recordings made through FitAI's own capture tool.
- **A perfect score is a warning sign, not a trophy.** The augmented BiLSTM classified all 2,472 test
  windows correctly. Verified: augmentation was applied only to training windows, and the test workouts
  share no subject with training. The honest explanation is that the benchmark is easy, not that the
  model is flawless — expect this number to fall on webcam data.
- **Near-perfect scores mean the benchmark is easy, not that the system is solved.** One fixed camera,
  consistent framing and five posturally distinct exercises make this close to a solved problem for any
  classifier; the logistic-regression baseline confirms it. Do not present 0.999 as evidence that FitAI
  will recognise exercises this well from a phone or laptop webcam in a bedroom.
- **A withdrawn result, kept here deliberately.** An earlier run used w18-w20 as the "held-out
  participants" and reported 0.865 / 0.551 / 0.794. That split was not subject-independent (MM-Fit's 21
  workouts come from ~10 people, and w18 is in the authors' training list), so those numbers were
  discarded and the run repeated with the authors' unseen-subject split. The lesson — verify that a
  dataset's "participants" really are distinct people before claiming participant-independent testing —
  is worth stating in the review.
- Windows overlap (stride 15 of 60 frames), so windows within a recording are correlated; splitting by
  participant is what keeps the test honest.

**Still to record (custom dataset):** incorrect-form examples for each exercise, side and
three-quarter views, and varied lighting, clothing and distance.
