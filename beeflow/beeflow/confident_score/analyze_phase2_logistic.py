import argparse
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from analyze_thresholds import DEFAULT_DATASET_PATH, safe_divide


DEFAULT_OUTPUT_PATH = Path("confident_score/phase2_logistic_analysis.relaxed.json")
DEFAULT_FEATURES = [
    "max_embedding_score",
    "avg_top3_embedding",
    "max_rerank_score",
    "rerank_gap",
]


@dataclass(frozen=True)
class ProbabilityMetrics:
    threshold: float
    tp: int
    fp: int
    tn: int
    fn: int
    precision: float
    recall: float
    f1: float
    fpr: float
    accuracy: float


def load_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON array in {path}")
    return [item for item in data if isinstance(item, dict)]


def import_sklearn():
    try:
        from sklearn.impute import SimpleImputer
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import roc_curve
        from sklearn.model_selection import train_test_split
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "Phase 2 Logistic Regression requires scikit-learn. "
            "Install it with: pip install scikit-learn"
        ) from exc

    return {
        "LogisticRegression": LogisticRegression,
        "Pipeline": Pipeline,
        "SimpleImputer": SimpleImputer,
        "StandardScaler": StandardScaler,
        "roc_curve": roc_curve,
        "train_test_split": train_test_split,
    }


def numeric_or_nan(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return math.nan


def build_examples(rows: list[dict[str, Any]], features: list[str]) -> tuple[list[list[float]], list[int]]:
    x_values = []
    y_values = []

    for row in rows:
        label = row.get("label")
        if not isinstance(label, bool):
            continue

        x_values.append([numeric_or_nan(row.get(feature)) for feature in features])
        y_values.append(1 if label else 0)

    return x_values, y_values


def validate_labels(y_values: list[int]) -> None:
    true_count = sum(y_values)
    false_count = len(y_values) - true_count
    if true_count == 0 or false_count == 0:
        raise ValueError("Phase 2 analysis requires both label=true and label=false examples")
    if true_count < 2 or false_count < 2:
        raise ValueError("Phase 2 stratified split requires at least 2 examples per label")


def evaluate_probability_threshold(
    y_true: list[int],
    y_score: list[float],
    threshold: float,
) -> ProbabilityMetrics:
    tp = fp = tn = fn = 0

    for label, score in zip(y_true, y_score):
        predicted = score >= threshold
        if label == 1 and predicted:
            tp += 1
        elif label == 0 and predicted:
            fp += 1
        elif label == 0 and not predicted:
            tn += 1
        else:
            fn += 1

    precision = safe_divide(tp, tp + fp)
    recall = safe_divide(tp, tp + fn)
    f1 = safe_divide(2 * precision * recall, precision + recall)
    fpr = safe_divide(fp, fp + tn)
    accuracy = safe_divide(tp + tn, tp + fp + tn + fn)

    return ProbabilityMetrics(
        threshold=threshold,
        tp=tp,
        fp=fp,
        tn=tn,
        fn=fn,
        precision=precision,
        recall=recall,
        f1=f1,
        fpr=fpr,
        accuracy=accuracy,
    )


def best_with_fpr_at_most(results: list[ProbabilityMetrics], max_fpr: float) -> ProbabilityMetrics | None:
    candidates = [item for item in results if item.fpr <= max_fpr]
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item.recall, item.precision, item.f1, -item.fpr))


def top_by_precision(results: list[ProbabilityMetrics], limit: int) -> list[ProbabilityMetrics]:
    useful = [item for item in results if item.tp + item.fp > 0]
    return sorted(
        useful,
        key=lambda item: (item.precision, item.recall, item.f1, -item.fpr),
        reverse=True,
    )[:limit]


def format_metric(value: float) -> str:
    return f"{value:.4f}"


def format_probability_row(item: ProbabilityMetrics | None) -> str:
    if item is None:
        return "n/a"

    return (
        f"threshold={item.threshold:.6f} "
        f"precision={format_metric(item.precision)} "
        f"recall={format_metric(item.recall)} "
        f"f1={format_metric(item.f1)} "
        f"fpr={format_metric(item.fpr)} "
        f"tp={item.tp} fp={item.fp} tn={item.tn} fn={item.fn}"
    )


def build_summary(
    rows: list[dict[str, Any]],
    features: list[str],
    max_fpr: float,
    test_size: float,
    random_state: int,
    top_n: int,
) -> dict[str, Any]:
    sklearn = import_sklearn()
    x_values, y_values = build_examples(rows, features)
    validate_labels(y_values)

    label_true_count = sum(y_values)
    label_false_count = len(y_values) - label_true_count
    train_test_split = sklearn["train_test_split"]
    x_train, x_eval, y_train, y_eval = train_test_split(
        x_values,
        y_values,
        test_size=test_size,
        random_state=random_state,
        stratify=y_values,
    )

    Pipeline = sklearn["Pipeline"]
    SimpleImputer = sklearn["SimpleImputer"]
    StandardScaler = sklearn["StandardScaler"]
    LogisticRegression = sklearn["LogisticRegression"]

    model = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            (
                "logistic_regression",
                LogisticRegression(class_weight="balanced", max_iter=1000, random_state=random_state),
            ),
        ]
    )
    model.fit(x_train, y_train)

    y_score = model.predict_proba(x_eval)[:, 1].tolist()
    fpr_values, recall_values, thresholds = sklearn["roc_curve"](y_eval, y_score)
    threshold_results = [
        evaluate_probability_threshold(y_eval, y_score, float(threshold))
        for threshold in thresholds
        if math.isfinite(float(threshold))
    ]
    best_fpr_item = best_with_fpr_at_most(threshold_results, max_fpr)

    logistic_model = model.named_steps["logistic_regression"]
    coefficients = {
        feature: float(coefficient)
        for feature, coefficient in zip(features, logistic_model.coef_[0])
    }

    summary = {
        "rows": len(x_values),
        "labels": {
            "true": label_true_count,
            "false": label_false_count,
        },
        "criteria": {
            "max_fpr": max_fpr,
            "test_size": test_size,
            "random_state": random_state,
            "top_n": top_n,
        },
        "features": features,
        "model": {
            "type": "LogisticRegression",
            "class_weight": "balanced",
            "max_iter": 1000,
            "preprocessing": ["SimpleImputer(strategy='median')", "StandardScaler()"],
            "coefficients_standardized": coefficients,
            "intercept": float(logistic_model.intercept_[0]),
        },
        "split": {
            "train_rows": len(x_train),
            "eval_rows": len(x_eval),
            "eval_true": sum(y_eval),
            "eval_false": len(y_eval) - sum(y_eval),
        },
        "roc_points": [
            {
                "fpr": float(fpr),
                "recall": float(recall),
                "threshold": float(threshold),
            }
            for fpr, recall, threshold in zip(fpr_values, recall_values, thresholds)
            if math.isfinite(float(threshold))
        ],
        "thresholds": {
            f"best_fpr_at_most_{max_fpr}": asdict(best_fpr_item) if best_fpr_item else None,
            "top_precision": [asdict(item) for item in top_by_precision(threshold_results, top_n)],
        },
        "recommended_probability_rule": None,
    }

    if best_fpr_item is not None:
        summary["recommended_probability_rule"] = {
            "selection": f"maximize recall with FPR <= {max_fpr}",
            "decision": f"P(relevant) >= {best_fpr_item.threshold}",
            "metrics": asdict(best_fpr_item),
        }

    return summary


def print_summary(summary: dict[str, Any], max_fpr: float) -> None:
    labels = summary["labels"]
    split = summary["split"]
    print(f"Rows: {summary['rows']}")
    print(f"Labels: true={labels['true']}, false={labels['false']}")
    print(
        "Split: "
        f"train={split['train_rows']}, eval={split['eval_rows']} "
        f"(true={split['eval_true']}, false={split['eval_false']})"
    )

    print()
    print("Recommended Phase 2 probability rule")
    recommended_rule = summary.get("recommended_probability_rule")
    if recommended_rule:
        metrics = ProbabilityMetrics(**recommended_rule["metrics"])
        print(f"Selection: {recommended_rule['selection']}")
        print(format_probability_row(metrics))
    else:
        print("n/a")

    print()
    print(f"Best recall with FPR <= {max_fpr}:")
    best_item = summary["thresholds"][f"best_fpr_at_most_{max_fpr}"]
    print(format_probability_row(ProbabilityMetrics(**best_item) if best_item else None))


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze Phase 2 confident scoring with Logistic Regression.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--max-fpr", type=float, default=0.20)
    parser.add_argument("--test-size", type=float, default=0.30)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument("--features", nargs="+", default=DEFAULT_FEATURES)
    args = parser.parse_args()

    if args.max_fpr < 0 or args.max_fpr > 1:
        raise ValueError("--max-fpr must be between 0 and 1")
    if args.test_size <= 0 or args.test_size >= 1:
        raise ValueError("--test-size must be between 0 and 1")

    rows = load_rows(args.dataset)
    try:
        summary = build_summary(
            rows=rows,
            features=args.features,
            max_fpr=args.max_fpr,
            test_size=args.test_size,
            random_state=args.random_state,
            top_n=args.top_n,
        )
    except ModuleNotFoundError as exc:
        parser.error(str(exc))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as file:
        json.dump(summary, file, ensure_ascii=False, indent=2)

    print_summary(summary, args.max_fpr)
    print()
    print(f"Saved Phase 2 analysis: {args.output}")


if __name__ == "__main__":
    main()
