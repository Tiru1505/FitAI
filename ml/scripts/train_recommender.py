"""Stage 2 (optional, experimental): ML plan-category recommender compared with the rule baseline.

Input CSV (collected with consent, e.g. exported profiles plus a plan category chosen or
approved by a qualified reviewer):
  goal, experience, days_per_week, session_minutes, has_equipment, has_health_flags, plan_category

Trains a gradient-boosted classifier and a small MLP with participant-level cross-validation
if a `user_id` column exists, and reports agreement with the transparent rule baseline.
A model trained on a small college dataset must not be presented as discovering medically
optimal plans; this is only an experimental comparison.

Usage:
  python ml/scripts/train_recommender.py --data ml/data/recommender.csv
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fitai_ml.data import ML_DIR  # noqa: E402

from app.services.recommender_service import GOAL_TEMPLATES  # noqa: E402

FEATURES = ["goal", "experience", "days_per_week", "session_minutes", "has_equipment", "has_health_flags"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--folds", type=int, default=5)
    args = parser.parse_args()

    from sklearn.compose import ColumnTransformer
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.metrics import accuracy_score, f1_score
    from sklearn.model_selection import GroupKFold, StratifiedKFold, cross_val_predict
    from sklearn.neural_network import MLPClassifier
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    df = pd.read_csv(args.data)
    missing = [c for c in FEATURES + ["plan_category"] if c not in df.columns]
    if missing:
        raise SystemExit(f"missing columns: {missing}")
    X, y = df[FEATURES], df["plan_category"]
    pre = ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore"), ["goal", "experience"]),
        ("num", StandardScaler(), ["days_per_week", "session_minutes", "has_equipment", "has_health_flags"]),
    ])  # fmt: skip
    if "user_id" in df.columns:
        cv, groups = GroupKFold(args.folds), df["user_id"]
    else:
        cv, groups = StratifiedKFold(args.folds, shuffle=True, random_state=42), None

    results = {"n": int(len(df)), "classes": sorted(y.unique().tolist())}
    baseline = df["goal"].map(GOAL_TEMPLATES)
    results["rule_baseline"] = {"accuracy": round(float(accuracy_score(y, baseline)), 4),
                                "macro_f1": round(float(f1_score(y, baseline, average="macro", zero_division=0)), 4)}  # fmt: skip
    for name, model in (("gradient_boosting", GradientBoostingClassifier(random_state=42)),
                        ("mlp", MLPClassifier(hidden_layer_sizes=(32,), max_iter=2000, random_state=42))):  # fmt: skip
        pred = cross_val_predict(make_pipeline(pre, model), X, y, cv=cv, groups=groups)
        results[name] = {
            "accuracy": round(float(accuracy_score(y, pred)), 4),
            "macro_f1": round(float(f1_score(y, pred, average="macro", zero_division=0)), 4),
            "agreement_with_rules": round(float(np.mean(pred == baseline)), 4),
        }
    out = ML_DIR / "results" / "recommender_comparison.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
