# Datasets

FitAI uses three data sources. Nothing in this repository is real participant data.

## A. Public exercise-movement data (initial experimentation)

| Dataset | Use in FitAI | Before using |
|---|---|---|
| UI-PRMD | Posture and movement-quality experiments | Verify licence, access terms and whether its motion-capture/Kinect format can be mapped to the 33-landmark schema |
| KIMORE | Exercise-quality and movement-assessment research | Inspect access terms and annotation format |
| **MM-Fit** (used) | Exercise recognition + rep-count ground truth | 2D/3D pose of 10 gym exercises from 10 participants; 5 overlap with FitAI (squat, push-up, lunge, dumbbell shoulder press, bicep curl). No incorrect-form labels, so it cannot train the form classifier. Cite Strömbäck, Huang & Radu (2020). |
| Other public exercise-video datasets | Initial exercise recognition | Use only datasets with clear research/educational usage terms |

Do not download or redistribute a dataset without checking its licence, consent terms and intended use.
For each dataset used, record: URL, participants, exercise classes, recording conditions, labels,
licence.

## B. Custom pose-landmark dataset (primary)

Collected from consenting volunteers with the in-app tool or `ml/scripts/extract_landmarks.py`.
Store numerical landmarks, not raw video.

| Dimension | Minimum target |
|---|---|
| Participants | 10–20 consenting volunteers (start with 8–10) |
| Exercises | 5 |
| Form classes | Correct plus ≥ 2 common error types per exercise |
| Camera views | Front plus side or three-quarter view |
| Conditions | Different heights, clothing, lighting, backgrounds, distances |
| Sequence length | 30–60 frames per window |
| Labels | Exercise, form status, error type, manual rep count |

Suggested error types (these match the rule-based messages in `backend/app/services/form_feedback.py`):

| Exercise | Error types |
|---|---|
| Squat | `knees_caving`, `forward_lean`, `insufficient_range` |
| Lunge | `torso_lean`, `insufficient_range` |
| Push-up | `hip_sag`, `hip_pike`, `insufficient_range` |
| Biceps curl | `elbow_drift`, `torso_swing` |
| Shoulder press | `torso_lean`, `uneven_arms`, `insufficient_range` |

**Split by participant, never randomly by frame.** Test participants must not appear in training.

Consent checklist: information sheet, signed consent, right to withdraw (delete that participant's
rows), pseudonymous IDs, secure storage, and no video retention unless consented and necessary.

## C. Nutrition data

`backend/app/data/foods.csv` contains 147 foods from **USDA FoodData Central, SR Legacy (April 2018)**,
which is public domain. It was built with `backend/scripts/build_foods_from_usda.py`, and every row
keeps its USDA FDC ID and description. Energy, protein, carbohydrate, fat and fibre come from USDA,
scaled to a USDA household portion. Meal categories and diet/allergen labels are assigned by FitAI,
because SR Legacy has none. See `backend/app/data/README.md`. It is used for filtering only and is
not a deep-learning training dataset.
