# FitAI ML pipeline

Scripts to build the custom pose-landmark dataset, train the BiLSTM (primary) and GRU (comparison)
classifiers, evaluate them on **unseen participants**, evaluate the rep counter, and export models to
the API. Feature construction is imported from `backend/app/services/pose_service.py`, so training
and live inference share identical normalisation (hip-centre origin, body-scale units, aspect-ratio
correction; 33 × [x, y, visibility] = 99 features per frame).

## Setup

```bash
cd ml
python -m venv .venv
.venv\Scripts\activate                # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

Run all commands below from the repository root (`fitai/`).

## 0. Quick path for a review demo: one command, full evidence

`run_pipeline_demo.py` runs every stage and saves the evidence a reviewer asks for: a timestamped
execution log, a comparison of all three models on held-out participants, confusion matrices, and
`RESULTS.md` with a limitations section.

```bash
python ml/scripts/run_pipeline_demo.py --landmarks "ml/data/landmarks/*.csv" \
    --val-participants P04 --test-participants P05 P06 --epochs 40 --export-best
```

Stages: build windows (participant split) -> dataset summary -> logistic-regression baseline ->
BiLSTM -> GRU -> evaluate each on the test participants -> comparison table. Add
`--rep-counts ml/data/rep_counts.csv` to also evaluate the repetition counter, `--form-exercise squat`
to train a form classifier, and `--export-best` to load the winner into the live app.

Output lands in `ml/results/pipeline_demo_<timestamp>/`.

## 0b. Public dataset: MM-Fit

MM-Fit (Strömbäck, Huang & Radu, 2020) provides 2D/3D pose for gym workouts from 10 participants.
Five of its exercises match FitAI: squats, push-ups, lunges, dumbbell shoulder press and bicep curls.
It also gives ground-truth repetition counts per set. It has **no incorrect-form labels**, so it
trains exercise recognition but not the form classifier.

```bash
# download mm-fit.zip (1.7 GB) from https://mmfit.github.io/ and extract it, then:
python ml/scripts/convert_mmfit.py --mmfit-dir data_sources/mmfit/mm-fit \
    --out ml/data/landmarks/mmfit.csv --rep-counts-out ml/data/mmfit_rep_counts.csv
python ml/scripts/run_pipeline_demo.py --landmarks ml/data/landmarks/mmfit.csv --rep-counts ml/data/mmfit_rep_counts.csv
```

MM-Fit joints are mapped into the matching MediaPipe slots; unmapped slots get visibility 0. Its
poses come from a different estimator than the live app's MediaPipe, so a model trained on MM-Fit
alone may transfer imperfectly to webcam use: record your own data for the final model, and say so
in the report.

## 1. Collect data (Dataset B: custom, consent-based)

Either:

- **In the app:** Settings, then *Dataset collection tool*. Record each sample with a pseudonymous
  participant ID, exercise, form label, error type and the manually counted reps. Download the
  landmarks CSV and the rep-counts CSV. No video is recorded.
- **From consented videos:** download `pose_landmarker_full.task` from the
  [MediaPipe Pose Landmarker page](https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker),
  fill a manifest (`ml/data/templates/videos_manifest_template.csv`), then run:

  ```bash
  python ml/scripts/extract_landmarks.py --manifest ml/data/videos_manifest.csv --model ml/models/pose_landmarker_full.task --out ml/data/landmarks/videos.csv
  ```

Recommended collection design: 10–20 volunteers (start with 8–10), all 5 exercises, correct form plus at
least 2 error types per exercise, front and side or three-quarter views, and varied height, clothing,
lighting, background and distance.

CSV schema (`ml/data/templates/landmarks_template.csv`): `sample_id, participant_id, exercise_label,
form_label, error_label, frame_index, visibility_score, image_width, image_height,
landmark_{0..32}_{x,y,visibility}`. Parquet with the same columns also works.

Public datasets (Dataset A) such as UI-PRMD or KIMORE use different sensors and formats. Convert them
to this schema only after checking their licence, access terms and task compatibility, and document the
URL, participants, classes, recording conditions, labels and licence in `docs/DATASETS.md`.

## 2. Build windows with a participant-independent split

```bash
python ml/scripts/build_sequences.py --inputs "ml/data/landmarks/*.csv" --out ml/data/sequences.npz --sequence-length 60 --stride 15 --val-participants P07 P08 --test-participants P09 P10
```

Frames with low visibility of the shoulders or hips are flagged, and windows with more than 20% flagged
frames are dropped. Each participant goes to exactly one of train, val or test. The manifest
`ml/data/sequences.json` lists participants per split and window counts.

## 3. Train

```bash
# baseline (logistic regression on window statistics)
python ml/scripts/train.py --data ml/data/sequences.npz --task exercise --model baseline
# primary model
python ml/scripts/train.py --data ml/data/sequences.npz --task exercise --model bilstm --export
# comparison
python ml/scripts/train.py --data ml/data/sequences.npz --task exercise --model gru
# form classifiers (one per exercise); --focal-loss if incorrect examples are rare
python ml/scripts/train.py --data ml/data/sequences.npz --task form --exercise squat --model bilstm --export
```

Architecture: BiLSTM(64) → Dropout(0.3) → BiLSTM(32) → Dropout(0.3) → Dense(32, ReLU) → Softmax,
trained with categorical cross-entropy (integer labels), class weights, and early stopping on validation
loss. Tune `--sequence-length` (in step 2), `--dropout`, `--lr`, and class weighting or focal loss.
Each run writes `ml/results/<name>_<model>_<timestamp>/` with config, history, validation metrics
and the model.

`--export` copies `<name>.keras` and `<name>.meta.json` into `backend/trained_models/`. Restart the API
with TensorFlow installed (`pip install -r backend/requirements-ml.txt`) to load them.

## 4. Evaluate on unseen participants

```bash
python ml/scripts/evaluate.py --data ml/data/sequences.npz --run ml/results/exercise_classifier_bilstm_YYYYMMDD_HHMMSS
```

This reports accuracy, macro precision, recall and F1, per-class metrics, a confusion matrix
(`confusion_matrix.png`) and per-window inference latency. Choose the final model by **validation macro
F1, generalisation to unseen participants, and latency**, not by accuracy alone.

Live inference metrics (server processing time, dropped-frame ratio, low-visibility ratio) are stored
per session in `workout_sessions.inference_stats` and returned by `GET /api/progress/history`.

## 5. Evaluate the repetition counter

```bash
python ml/scripts/evaluate_rep_counter.py --landmarks "ml/data/landmarks/*.csv" --labels ml/data/rep_counts.csv
```

This reports mean absolute counting error and the percentage of samples within one count, overall and per exercise.

## 6. Optional: ML recommender comparison

```bash
python ml/scripts/train_recommender.py --data ml/data/recommender.csv
```

This compares gradient boosting and an MLP against the rule baseline. It is an experimental comparison
only.

## Pipeline smoke test (synthetic data)

`make_synthetic_smoke_data.py` generates procedurally animated stick figures so you can check that
every script runs. **Its metrics are meaningless. Never report them.**

```bash
python ml/scripts/make_synthetic_smoke_data.py --out ml/data/smoke/synthetic.csv
python ml/scripts/build_sequences.py --inputs ml/data/smoke/synthetic.csv --out ml/data/smoke/sequences.npz --val-participants SYN04 --test-participants SYN05
python ml/scripts/train.py --data ml/data/smoke/sequences.npz --task exercise --model bilstm --epochs 3
```
