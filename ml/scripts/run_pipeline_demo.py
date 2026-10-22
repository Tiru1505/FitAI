"""Run the whole FitAI deep-learning pipeline end to end and record the evidence.

Stages: dataset summary -> windowing with a participant-independent split -> baseline
(logistic regression) -> BiLSTM (primary) -> GRU (comparison) -> evaluation of every model
on the held-out participants -> comparison table.

Everything printed is also written to `execution_log.txt` in the output folder, together with
the metrics, the confusion matrices and `RESULTS.md`, which is the table to paste into slides
or the report.

Example:
    python ml/scripts/run_pipeline_demo.py --landmarks "ml/data/landmarks/*.csv" \
        --test-participants P05 P06 --val-participants P04 --epochs 40 --export-best

Notes:
  * Numbers are only as good as the recordings. State the participant count in the report.
  * --export-best copies the winning model into backend/trained_models/ so the live app uses it.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fitai_ml.data import ML_DIR, TRAINED_MODELS_DIR  # noqa: E402

SCRIPTS = Path(__file__).resolve().parent


class Tee:
    """Writes to the console and the execution log at the same time."""

    def __init__(self, path: Path):
        self.file = path.open("w", encoding="utf-8")

    def write(self, text: str) -> None:
        sys.__stdout__.write(text)
        sys.__stdout__.flush()
        self.file.write(text)
        self.file.flush()

    def close(self) -> None:
        self.file.close()


def banner(log: Tee, step: str, title: str) -> None:
    log.write(f"\n{'=' * 78}\n[{step}] {title}\n{'=' * 78}\n")


def run(log: Tee, script: str, args: list[str]) -> None:
    cmd = [sys.executable, str(SCRIPTS / script), *args]
    log.write(f"$ python ml/scripts/{script} {' '.join(args)}\n\n")
    started = time.perf_counter()
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    assert process.stdout is not None
    for line in process.stdout:
        log.write(line)
    code = process.wait()
    log.write(f"\n-- finished in {time.perf_counter() - started:.1f}s (exit code {code})\n")
    if code != 0:
        log.write("\nPipeline stopped: the stage above failed.\n")
        raise SystemExit(code)


def latest_run(prefix: str) -> Path:
    runs = sorted((ML_DIR / "results").glob(f"{prefix}_*"), key=lambda p: p.stat().st_mtime)
    if not runs:
        raise SystemExit(f"no run directory found for {prefix}")
    return runs[-1]


def dataset_summary(log: Tee, manifest: dict, sequences: Path) -> None:
    import numpy as np

    data = np.load(sequences, allow_pickle=False)
    log.write(f"sequence length: {manifest['sequence_length']} frames, stride {manifest['stride']}, features {data['X_train'].shape[2]}\n")
    log.write(f"exercise labels: {', '.join(manifest['exercise_labels'])}\n")
    log.write(f"form labels:     {', '.join(manifest['form_labels'])}\n\n")
    log.write(f"{'split':<8}{'participants':<34}{'windows':>9}  class distribution\n")
    for split in ("train", "val", "test"):
        y = data[f"y_exercise_{split}"]
        counts = {label: int((y == i).sum()) for i, label in enumerate(manifest["exercise_labels"]) if (y == i).sum()}
        people = ", ".join(manifest["participants"][split]) or "(none)"
        log.write(f"{split:<8}{people[:32]:<34}{len(y):>9}  {counts}\n")
    overlap = set(manifest["participants"]["train"]) & set(manifest["participants"]["test"])
    log.write(f"\nparticipant-independent test split: {'NO - OVERLAP ' + str(overlap) if overlap else 'yes (no participant appears in two splits)'}\n")
    log.write(f"windows dropped for low visibility: {manifest['windows_dropped_low_visibility']}\n")


def collect(run_dir: Path) -> dict:
    config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
    val = json.loads((run_dir / "val_metrics.json").read_text(encoding="utf-8"))
    test = json.loads((run_dir / "test_metrics.json").read_text(encoding="utf-8"))
    return {"model": config["model"], "run_dir": run_dir, "config": config, "val": val, "test": test}


def results_markdown(results: list[dict], manifest: dict, args: argparse.Namespace, started: datetime) -> str:
    rows = [
        "| Model | Val macro F1 | Test accuracy | Test macro precision | Test macro recall | **Test macro F1** | Latency p50 / p95 (ms) | Train time (s) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lat = r["test"]["latency_ms_per_window"]
        rows.append(
            f"| {r['model']} | {r['val']['macro_f1']} | {r['test']['accuracy']} | {r['test']['macro_precision']} | "
            f"{r['test']['macro_recall']} | **{r['test']['macro_f1']}** | {lat['p50']} / {lat['p95']} | {r['config'].get('train_seconds', 'n/a')} |"
        )
    best = max(results, key=lambda r: r["test"]["macro_f1"])
    per_class = "\n".join(
        f"| {label} | {m['precision']} | {m['recall']} | {m['f1']} | {m['support']} |"
        for label, m in best["test"]["per_class"].items()
    )
    n_train, n_test = len(manifest["participants"]["train"]), len(manifest["participants"]["test"])
    limits = [
        f"Trained on {n_train} participant(s) and tested on {n_test} held-out participant(s). "
        "This is a small sample, so treat the numbers as preliminary evidence that the pipeline works, "
        "not as a claim about general accuracy.",
        f"Windows overlap in time (stride {manifest['stride']} of {manifest['sequence_length']} frames), so "
        "windows from one recording are correlated; the split is by participant, which is what keeps the test honest.",
    ]
    if n_test < 2:
        limits.append("Only one test participant: results depend heavily on that person, so report the confusion matrix alongside the F1 score.")
    if min(manifest["windows"].values()) < 50:
        limits.append("At least one split has fewer than 50 windows; per-class metrics on so few samples are unstable.")
    limitations = "\n".join(f"- {line}" for line in limits)

    return f"""# FitAI pipeline run — {started:%Y-%m-%d %H:%M}

Generated by `ml/scripts/run_pipeline_demo.py`. All test numbers are on **participants held out
of training**: {", ".join(manifest["participants"]["test"])}.

## Dataset

| | |
|---|---|
| Landmark files | {", ".join(Path(p).name for p in manifest["inputs"])} |
| Participants (train / val / test) | {len(manifest["participants"]["train"])} / {len(manifest["participants"]["val"])} / {len(manifest["participants"]["test"])} |
| Windows (train / val / test) | {manifest["windows"]["train"]} / {manifest["windows"]["val"]} / {manifest["windows"]["test"]} |
| Sequence length / stride | {manifest["sequence_length"]} frames / {manifest["stride"]} |
| Features per frame | 99 (33 landmarks × x, y, visibility), hip-centred and body-scale normalised |
| Classes | {", ".join(manifest["exercise_labels"])} |

## Exercise classification (test participants)

{chr(10).join(rows)}

Best by test macro F1: **{best["model"]}** ({best["test"]["macro_f1"]}).

### Per-class results for {best["model"]}

| Class | Precision | Recall | F1 | Support |
|---|---|---|---|---|
{per_class}

Confusion matrix: `{best["model"]}_confusion_matrix.png`

## Limitations

{limitations}

## How to reproduce

```
python ml/scripts/run_pipeline_demo.py --landmarks "{args.landmarks[0]}" --epochs {args.epochs}
```

Environment: Python {platform.python_version()} on {platform.system()} {platform.release()}.
Full console output: `execution_log.txt`.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--landmarks", nargs="+", required=True, help="landmark CSV/Parquet files or globs")
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--sequence-length", type=int, default=60)
    parser.add_argument("--stride", type=int, default=15)
    parser.add_argument("--val-participants", nargs="*")
    parser.add_argument("--test-participants", nargs="*")
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--models", nargs="+", default=["baseline", "bilstm", "gru"], choices=["baseline", "bilstm", "gru"])
    parser.add_argument("--form-exercise", help="also train a form classifier for this exercise")
    parser.add_argument("--rep-counts", type=Path, help="CSV of manual rep counts, to evaluate the repetition counter")
    parser.add_argument("--export-best", action="store_true", help="copy the best model into backend/trained_models/")
    args = parser.parse_args()

    started = datetime.now()
    out_dir = args.out_dir or ML_DIR / "results" / f"pipeline_demo_{started:%Y%m%d_%H%M%S}"
    out_dir.mkdir(parents=True, exist_ok=True)
    log = Tee(out_dir / "execution_log.txt")
    sequences = out_dir / "sequences.npz"

    log.write(f"FitAI pipeline demo\nstarted: {started:%Y-%m-%d %H:%M:%S}\n")
    log.write(f"python {platform.python_version()} on {platform.system()} {platform.release()}\n")
    log.write(f"output: {out_dir}\n")

    try:
        banner(log, "1/6", "Data loading and preprocessing (landmarks -> normalised windows, split by participant)")
        build_args = ["--inputs", *args.landmarks, "--out", str(sequences),
                      "--sequence-length", str(args.sequence_length), "--stride", str(args.stride)]  # fmt: skip
        if args.val_participants:
            build_args += ["--val-participants", *args.val_participants]
        if args.test_participants:
            build_args += ["--test-participants", *args.test_participants]
        run(log, "build_sequences.py", build_args)

        manifest = json.loads(sequences.with_suffix(".json").read_text(encoding="utf-8"))
        banner(log, "2/6", "Dataset summary")
        dataset_summary(log, manifest, sequences)

        results = []
        for i, model in enumerate(args.models, start=3):
            banner(log, f"{i}/6", f"Training: {model}" + (" (primary model)" if model == "bilstm" else " (baseline)" if model == "baseline" else " (comparison)"))
            run(log, "train.py", ["--data", str(sequences), "--task", "exercise", "--model", model, "--epochs", str(args.epochs), "--batch-size", str(args.batch_size)])
            run_dir = latest_run("exercise_classifier")
            banner(log, f"{i}/6", f"Evaluating {model} on held-out participants")
            run(log, "evaluate.py", ["--data", str(sequences), "--run", str(run_dir)])
            results.append(collect(run_dir))

        if args.form_exercise:
            banner(log, "6/6", f"Form classifier for {args.form_exercise}")
            run(log, "train.py", ["--data", str(sequences), "--task", "form", "--exercise", args.form_exercise, "--model", "bilstm", "--epochs", str(args.epochs)])
            run(log, "evaluate.py", ["--data", str(sequences), "--run", str(latest_run(f"form_classifier_{args.form_exercise}"))])

        if args.rep_counts:
            banner(log, "6/6", "Repetition counter (joint-angle state machine) against manual counts")
            run(log, "evaluate_rep_counter.py", ["--landmarks", *args.landmarks, "--labels", str(args.rep_counts),
                                                 "--out", str(out_dir / "rep_counter_metrics.json")])  # fmt: skip

        banner(log, "6/6", "Model comparison (test participants)")
        for r in results:
            lat = r["test"]["latency_ms_per_window"]
            log.write(f"{r['model']:<10} val macro F1 {r['val']['macro_f1']:<8} test macro F1 {r['test']['macro_f1']:<8} "
                      f"accuracy {r['test']['accuracy']:<8} latency p50 {lat['p50']} ms\n")  # fmt: skip
        best = max(results, key=lambda r: r["test"]["macro_f1"])
        log.write(f"\nbest by test macro F1: {best['model']} ({best['test']['macro_f1']}) from {best['run_dir'].name}\n")

        (out_dir / "RESULTS.md").write_text(results_markdown(results, manifest, args, started), encoding="utf-8")
        for r in results:
            for name in ("confusion_matrix.png", "test_metrics.json", "val_metrics.json", "config.json", "history.json"):
                src = r["run_dir"] / name
                if src.exists():
                    (out_dir / f"{r['model']}_{name}").write_bytes(src.read_bytes())

        if args.export_best:
            if best["model"] == "baseline":
                log.write("\nnot exporting: the baseline is not served by the API (only Keras models are).\n")
            else:
                TRAINED_MODELS_DIR.mkdir(parents=True, exist_ok=True)
                for suffix in (".keras", ".meta.json"):
                    src = best["run_dir"] / f"exercise_classifier{suffix}"
                    (TRAINED_MODELS_DIR / src.name).write_bytes(src.read_bytes())
                log.write(f"\nexported {best['model']} to {TRAINED_MODELS_DIR} - restart the API to load it.\n")

        log.write(f"\nDone in {(datetime.now() - started).total_seconds():.0f}s.\n")
        log.write(f"Evidence for the review:\n  {out_dir / 'execution_log.txt'}\n  {out_dir / 'RESULTS.md'}\n  {out_dir}/*_confusion_matrix.png\n")
    finally:
        log.close()


if __name__ == "__main__":
    main()
