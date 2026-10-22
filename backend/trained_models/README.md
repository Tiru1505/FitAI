# trained_models

The API loads models from this folder at startup (TensorFlow required: `pip install -r requirements-ml.txt`):

- `exercise_classifier.keras` + `exercise_classifier.meta.json`
- `form_classifier_<exercise>.keras` + `form_classifier_<exercise>.meta.json` (optional, one per exercise)

Create them with `python ml/scripts/train.py ... --export`. The folder is intentionally empty in the
repository: no pre-trained model is shipped, and the app reports that recognition models are
unavailable until you train one on real data.
