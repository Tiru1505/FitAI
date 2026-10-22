# Results

Metrics, execution logs and plots from the training runs. The bulky intermediates each run also
produces — the windowed dataset (`sequences.npz`, ~31 MB) and duplicate model weights — are not
committed; regenerate them with the command in each run's `RESULTS.md`.

| Run | What it is |
|---|---|
| `pipeline_demo_20260918_230557/` | **The run the report quotes.** Full six-stage pipeline on MM-Fit's unseen-subject split (test = w00, w05, w12, w13, w20). Baseline, BiLSTM and GRU, plus the repetition-counter evaluation. |
| `exercise_classifier_bilstm_20260918_231247/` | The augmentation + regularisation ablation on that same split; this is the model exported to `backend/trained_models/`. |
| `pipeline_demo_20260918_221431/` | **Withdrawn — kept on purpose.** An earlier run whose test split (w18–w20) was not subject-independent, because MM-Fit's 21 workouts come from only ~10 people. Its numbers (0.865 / 0.551 / 0.794 macro F1) are not valid and are reported as withdrawn in `docs/EVALUATION_REPORT.md`. Kept so the correction is auditable. |

Each run directory contains:

- `execution_log.txt` — every stage with timings, the split table and the final comparison
- `RESULTS.md` — the comparison table, per-class metrics, limitations and the reproduce command
- `*_test_metrics.json` / `*_val_metrics.json` — raw numbers including confusion matrices
- `*_config.json` — the exact hyperparameters used
- `*_confusion_matrix.png` — per-model confusion matrices on the test participants
- `rep_counter_metrics.json` — per-set repetition counts versus ground truth
