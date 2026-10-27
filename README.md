# FitAI: An Adaptive Deep-Learning-Based Fitness Assistant for Personalized Workouts and Real-Time Exercise Analysis

FitAI is a full-stack college-project prototype. It collects a fitness profile, generates an
explainable weekly workout plan with general nutrition guidance, analyses five exercises live through
the webcam (rep counting, form feedback), stores sessions, and adapts the next workout based on
performance and consistency.

> **Health boundary:** FitAI is an educational fitness-support prototype. It does not diagnose medical
> conditions, prescribe treatment, guarantee injury prevention, or provide clinical nutrition
> prescriptions. Users with injuries, chronic conditions, pregnancy, eating-disorder history, or
> special dietary requirements are directed to qualified professionals.

## Architecture

```
Browser (React + TypeScript)                              FastAPI backend
───────────────────────────                              ───────────────
webcam ─► MediaPipe Pose Landmarker (WASM, local)
          │ 33 landmarks/frame (no video leaves device)
          └─► WebSocket /api/inference/live ─────────►  aspect correction + normalisation
                                                        ├─ joint angle ─► moving average ─► FSM rep counter
                                                        ├─ rule-based form checks (geometric)
                                                        └─ BiLSTM exercise / form classifier (if trained)
          ◄── {exercise, confidence, repetition_count, form_status, feedback, visible, ...}

REST: auth · profile · rule-based recommender · sessions · adaptive coach · progress · nutrition
DB:   SQLAlchemy + Alembic (SQLite by default, PostgreSQL supported)
```

| Task | Method | Where |
|---|---|---|
| Pose extraction | MediaPipe Pose Landmarker (in browser; Python Tasks API for recorded videos) | `frontend/src/lib/pose.ts`, `ml/scripts/extract_landmarks.py` |
| Exercise recognition | **Bidirectional LSTM** on 60-frame landmark windows (GRU as comparison) | `ml/scripts/train.py`, `backend/app/services/exercise_classifier.py` |
| Form classification | BiLSTM/GRU per exercise + transparent geometric rules | `backend/app/services/form_feedback.py` |
| Repetition counting | Joint angles + moving average + finite-state machine, with per-session threshold calibration | `backend/app/services/rep_counter.py` |
| Workout recommendation | Rule-based baseline (optional ML comparison) | `backend/app/services/recommender_service.py`, `ml/scripts/train_recommender.py` |
| Adaptive coaching | Configurable score-based policy | `backend/app/services/adaptive_coach.py` |

**The frontend never makes predictions.** Every exercise label, rep count, form status, plan, score and
progress value comes from FastAPI. Until a BiLSTM model is trained and exported, the API reports
`recognition_source: "user_selected"` and `confidence: null` and analyses the exercise the user
selected with the rule-based pipeline. It does not invent a recognition result.

## Repository layout

```
fitai/
├── backend/            FastAPI app (app/api, app/services, app/models, app/schemas, app/db/migrations), tests/
│   └── trained_models/ exported .keras models + .meta.json are loaded from here
├── frontend/           React + TypeScript + Vite + Tailwind + TanStack Query + Recharts
├── ml/                 dataset pipeline, training and evaluation scripts (see ml/README.md)
└── docs/               DATASETS.md, EVALUATION_REPORT.md (template)
```

## Installation

Requirements: Python 3.10+, Node.js 20+, a webcam, and a Chromium-based browser or Firefox.

### 1. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env          # macOS/Linux: cp .env.example .env  (set FITAI_JWT_SECRET)
uvicorn app.main:app --reload --port 8000
```

On startup the API runs Alembic migrations (`alembic upgrade head`), seeds the five exercises and the
food table, and tries to load models from `trained_models/`. Interactive API docs:
http://127.0.0.1:8000/docs

To let the API use trained models: `pip install -r requirements-ml.txt` (TensorFlow).

PostgreSQL: set `FITAI_DATABASE_URL=postgresql+psycopg://user:pass@host:5432/fitai` and
`pip install "psycopg[binary]"`.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev                     # http://localhost:5173 (proxies /api and the WebSocket to :8000)
```

`npm run dev` / `npm run build` copy the MediaPipe WASM runtime into `public/`. The pose model file
(`pose_landmarker_lite.task`) is downloaded by the browser from Google's MediaPipe model storage; set
`VITE_POSE_MODEL_URL` to self-host it. Camera access requires `localhost` or HTTPS.

### 3. Tests

```bash
cd backend
.venv\Scripts\python -m pytest -q
```

The suite covers the repetition counter (phase order, partial reps, jitter, occlusion reset, mirrored
shoulder press), form rules, adaptation rules and score weighting, the recommender's constraint
satisfaction, nutrition safety limits, API validation and authorization, a full WebSocket session with
adaptation, and data deletion.

Frontend type-check and build: `cd frontend && npm run build`.

## Using the app

1. **Register** and complete the **profile** (goal, experience, equipment, schedule, exclusions,
   dietary preferences, allergies, optional health considerations). A plan is generated with a
   "Why this plan?" explanation.
2. **Live session:** read and acknowledge the safety and privacy notice (first time only), start the
   session, enable the camera, pick an exercise, then **Start set** and **End set**. **Stop session**
   ends everything immediately and turns the camera off. Without a camera, finish the workout and
   enter reps manually.
3. **Finish:** rate difficulty. The server computes completion, form score, consistency and the session
   score, then applies the adaptation rules and creates a new plan version if anything changed.
4. **Progress:** charts for session scores, reps per exercise, form issue frequency, optional weight
   log, adaptation history and session history.
5. **Nutrition:** approximate calorie range (withheld for minors and sensitive health flags), protein
   guidance, meal ideas filtered by diet and allergens, and a food explorer.
6. **Settings & privacy:** privacy notice, model status, and **delete data** (keep the login or delete
   the account too). The researcher **dataset collection tool** records landmarks from consenting
   volunteers and downloads them as CSV, entirely in the browser.

## Adaptive coaching

```
session_score = 0.35 × completion_rate + 0.35 × form_score + 0.15 × consistency_score + 0.15 × difficulty_adjustment
```

Weights and thresholds are configurable (`FITAI_SCORE_WEIGHT_*`, `FITAI_COACH_*` in
`backend/app/core/config.py`). They are project parameters to validate through testing, not medically
optimal values. If a session has no live form data, the remaining weights are renormalised.

| Session result | Next-plan action |
|---|---|
| Completion ≥ 90% and form ≥ 80% | +2 reps (capped) |
| Completion ≥ 90% and form < 60% | Keep difficulty; technique guidance |
| Completion < 60% and difficulty ≥ 4 | −2 reps (floor), +15 s rest |
| ≥ 2 missed planned sessions in 7 days | −1 set per exercise (at most once per week) + consistency reminder |
| Same form error in the last 3 results | Practice mode (slow tempo, technique focus) |

## Model training and evaluation

One command runs the whole deep-learning pipeline and saves an execution log, a model comparison
and confusion matrices for review:

```bash
python ml/scripts/run_pipeline_demo.py --landmarks "ml/data/landmarks/*.csv" --export-best
```

See **[ml/README.md](ml/README.md)** for the full workflow: record or extract landmarks, then build
participant-split windows, train the baseline, BiLSTM and GRU models, evaluate on unseen participants,
evaluate the rep counter, and export to `backend/trained_models/`. Record measured results in
**[docs/EVALUATION_REPORT.md](docs/EVALUATION_REPORT.md)**. That file is a template with placeholders.
No performance figures in this repository are real until you produce them.

## Security and privacy

- Passwords are hashed with bcrypt, auth uses JWT bearer tokens, and all private endpoints and the
  WebSocket require authentication. Users can only access their own records.
- All inputs are validated with Pydantic on the backend and Zod on the frontend. Landmark payloads are
  checked for shape and range.
- Raw video is never uploaded or stored. The server receives landmark coordinates and stores only
  aggregate results.
- Sensitive values (tokens, passwords) are redacted by a logging filter. Request bodies are not logged.
- `DELETE /api/users/me/data` removes all user data. Live set summaries are kept in memory only until
  the session is completed.
- Known prototype limitations: tokens live in `localStorage`; there is no rate limiting on login; pending
  live results are lost if the API restarts mid-session; the in-memory live store assumes a single
  API process.

## Limitations

- Rule-based form checks are 2D heuristics and depend on camera angle. Some apply only to front or
  side views, and thresholds need tuning against labelled recordings.
- Recognition and form models need a real, consenting, multi-participant dataset. None is included.
- Nutrition values come from USDA FoodData Central SR Legacy (147 generic foods). Diet and allergen
  labels are assigned by FitAI, not USDA, and are not allergy-safety guarantees. Indian prepared
  dishes are represented by their base ingredients.
- Only the five v1 exercises are supported: squat, lunge, push-up, biceps curl, shoulder press.

## References

1. Google AI Edge, MediaPipe Pose Landmarker: https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker
2. FastAPI documentation: https://fastapi.tiangolo.com/
3. React documentation: https://react.dev/
4. TensorFlow Keras documentation: https://www.tensorflow.org/guide/keras
5. UI-PRMD dataset (Vakanski et al., 2018): check access and licence before use
6. KIMORE dataset (Capecci et al., 2019): check access and licence before use
7. USDA FoodData Central: https://fdc.nal.usda.gov/
