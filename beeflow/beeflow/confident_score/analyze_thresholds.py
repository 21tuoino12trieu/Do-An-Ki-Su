import argparse
import bisect
import itertools
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


DEFAULT_DATASET_PATH = Path("confident_score/confident_scoring_dataset.relaxed.json")
DEFAULT_OUTPUT_PATH = Path("confident_score/threshold_analysis.relaxed.json")
FEATURES = [
    "max_embedding_score",
    "max_rerank_score",
]
RECOMMENDED_RULE_FEATURES = ("max_embedding_score", "max_rerank_score")


@dataclass(frozen=True)
class ThresholdMetrics:
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


@dataclass(frozen=True)
class CombinationMetrics:
    thresholds: dict[str, float]
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


def safe_divide(numerator: int | float, denominator: int | float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def evaluate_threshold(rows: list[dict[str, Any]], feature: str, threshold: float) -> ThresholdMetrics:
    tp = fp = tn = fn = 0

    for row in rows:
        label = row.get("label")
        value = row.get(feature)
        if not isinstance(label, bool) or not isinstance(value, (int, float)):
            continue

        predicted = float(value) >= threshold
        if label and predicted:
            tp += 1
        elif not label and predicted:
            fp += 1
        elif not label and not predicted:
            tn += 1
        else:
            fn += 1

    precision = safe_divide(tp, tp + fp)
    recall = safe_divide(tp, tp + fn)
    f1 = safe_divide(2 * precision * recall, precision + recall)
    fpr = safe_divide(fp, fp + tn)
    accuracy = safe_divide(tp + tn, tp + fp + tn + fn)

    return ThresholdMetrics(
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


def evaluate_combination(rows: list[dict[str, Any]], thresholds: dict[str, float]) -> CombinationMetrics:
    tp = fp = tn = fn = 0

    for row in rows:
        label = row.get("label")
        if not isinstance(label, bool):
            continue

        predicted = True
        for feature, threshold in thresholds.items():
            value = row.get(feature)
            if not isinstance(value, (int, float)) or float(value) < threshold:
                predicted = False
                break

        if label and predicted:
            tp += 1
        elif not label and predicted:
            fp += 1
        elif not label and not predicted:
            tn += 1
        else:
            fn += 1

    precision = safe_divide(tp, tp + fp)
    recall = safe_divide(tp, tp + fn)
    f1 = safe_divide(2 * precision * recall, precision + recall)
    fpr = safe_divide(fp, fp + tn)
    accuracy = safe_divide(tp + tn, tp + fp + tn + fn)

    return CombinationMetrics(
        thresholds=thresholds,
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


def build_combination_metrics(thresholds: dict[str, float], tp: int, fp: int, tn: int, fn: int) -> CombinationMetrics:
    precision = safe_divide(tp, tp + fp)
    recall = safe_divide(tp, tp + fn)
    f1 = safe_divide(2 * precision * recall, precision + recall)
    fpr = safe_divide(fp, fp + tn)
    accuracy = safe_divide(tp + tn, tp + fp + tn + fn)

    return CombinationMetrics(
        thresholds=thresholds,
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


def candidate_thresholds(rows: list[dict[str, Any]], feature: str) -> list[float]:
    values = sorted({
        float(row[feature])
        for row in rows
        if isinstance(row.get(feature), (int, float))
    })
    if not values:
        return []

    thresholds = [values[0] - 1e-12]
    thresholds.extend(values)
    thresholds.append(values[-1] + 1e-12)
    return thresholds


def quantile_thresholds(rows: list[dict[str, Any]], feature: str, grid_size: int) -> list[float]:
    values = sorted(
        float(row[feature])
        for row in rows
        if isinstance(row.get(feature), (int, float))
    )
    if not values:
        return []

    if grid_size >= len(values):
        return candidate_thresholds(rows, feature)

    thresholds = {values[0] - 1e-12, values[-1] + 1e-12}
    for index in range(grid_size):
        position = round(index * (len(values) - 1) / max(grid_size - 1, 1))
        thresholds.add(values[position])
    return sorted(thresholds)


def scan_feature(rows: list[dict[str, Any]], feature: str) -> list[ThresholdMetrics]:
    return [
        evaluate_threshold(rows, feature, threshold)
        for threshold in candidate_thresholds(rows, feature)
    ]


def scan_combination(
    rows: list[dict[str, Any]],
    features: tuple[str, ...],
    grid_size: int,
) -> list[CombinationMetrics]:
    feature_thresholds = [
        quantile_thresholds(rows, feature, grid_size)
        for feature in features
    ]
    if len(features) == 2:
        return scan_combination_2d(rows, features, feature_thresholds)

    results = []
    for threshold_values in itertools.product(*feature_thresholds):
        thresholds = dict(zip(features, threshold_values))
        results.append(evaluate_combination(rows, thresholds))
    return results


def suffix_sum_2d(values: list[list[int]]) -> list[list[int]]:
    row_count = len(values)
    column_count = len(values[0]) if values else 0
    suffix = [[0] * (column_count + 1) for _ in range(row_count + 1)]

    for row_index in range(row_count - 1, -1, -1):
        for column_index in range(column_count - 1, -1, -1):
            suffix[row_index][column_index] = (
                values[row_index][column_index]
                + suffix[row_index + 1][column_index]
                + suffix[row_index][column_index + 1]
                - suffix[row_index + 1][column_index + 1]
            )
    return suffix


def scan_combination_2d(
    rows: list[dict[str, Any]],
    features: tuple[str, ...],
    feature_thresholds: list[list[float]],
) -> list[CombinationMetrics]:
    x_feature, y_feature = features
    x_values = sorted({
        float(row[x_feature])
        for row in rows
        if isinstance(row.get(x_feature), (int, float))
    })
    y_values = sorted({
        float(row[y_feature])
        for row in rows
        if isinstance(row.get(y_feature), (int, float))
    })
    if not x_values or not y_values:
        return []

    x_indexes = {value: index for index, value in enumerate(x_values)}
    y_indexes = {value: index for index, value in enumerate(y_values)}
    true_counts = [[0] * len(y_values) for _ in x_values]
    false_counts = [[0] * len(y_values) for _ in x_values]
    total_true = total_false = 0

    for row in rows:
        label = row.get("label")
        if not isinstance(label, bool):
            continue

        if label:
            total_true += 1
        else:
            total_false += 1

        x_value = row.get(x_feature)
        y_value = row.get(y_feature)
        if not isinstance(x_value, (int, float)) or not isinstance(y_value, (int, float)):
            continue

        x_index = x_indexes[float(x_value)]
        y_index = y_indexes[float(y_value)]
        if label:
            true_counts[x_index][y_index] += 1
        else:
            false_counts[x_index][y_index] += 1

    true_suffix = suffix_sum_2d(true_counts)
    false_suffix = suffix_sum_2d(false_counts)
    results = []

    for x_threshold in feature_thresholds[0]:
        x_index = bisect.bisect_left(x_values, x_threshold)
        for y_threshold in feature_thresholds[1]:
            y_index = bisect.bisect_left(y_values, y_threshold)
            tp = true_suffix[x_index][y_index]
            fp = false_suffix[x_index][y_index]
            fn = total_true - tp
            tn = total_false - fp
            results.append(
                build_combination_metrics(
                    thresholds={
                        x_feature: x_threshold,
                        y_feature: y_threshold,
                    },
                    tp=tp,
                    fp=fp,
                    tn=tn,
                    fn=fn,
                )
            )

    return results


def best_with_fpr_at_most(results: list[ThresholdMetrics] | list[CombinationMetrics], max_fpr: float):
    if not results:
        return None
    candidates = [item for item in results if item.fpr <= max_fpr]
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item.recall, item.precision, item.f1, -item.fpr))


def top_by_precision(results: list[ThresholdMetrics] | list[CombinationMetrics], limit: int):
    useful = [item for item in results if item.tp + item.fp > 0]
    return sorted(
        useful,
        key=lambda item: (item.precision, item.recall, item.f1, -item.fpr),
        reverse=True,
    )[:limit]


def format_metric(value: float) -> str:
    return f"{value:.4f}"


def format_row(item: ThresholdMetrics | None) -> str:
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


def format_combo_row(item: CombinationMetrics | None) -> str:
    if item is None:
        return "n/a"

    thresholds = ", ".join(
        f"{feature}>={threshold:.6f}"
        for feature, threshold in item.thresholds.items()
    )
    return (
        f"{thresholds} "
        f"precision={format_metric(item.precision)} "
        f"recall={format_metric(item.recall)} "
        f"f1={format_metric(item.f1)} "
        f"fpr={format_metric(item.fpr)} "
        f"tp={item.tp} fp={item.fp} tn={item.tn} fn={item.fn}"
    )


def build_summary(
    rows: list[dict[str, Any]],
    max_fpr: float,
    top_n: int,
    combo_size: int,
    grid_size: int,
) -> dict[str, Any]:
    summary = {
        "rows": len(rows),
        "labels": {
            "true": sum(1 for row in rows if row.get("label") is True),
            "false": sum(1 for row in rows if row.get("label") is False),
        },
        "criteria": {
            "max_fpr": max_fpr,
            "top_n": top_n,
            "combo_size": combo_size,
            "grid_size": grid_size,
        },
        "features": {},
        "combinations": {},
        "recommended_rule": None,
    }

    for feature in FEATURES:
        results = scan_feature(rows, feature)
        summary["features"][feature] = {
            f"best_fpr_at_most_{max_fpr}": asdict(best_with_fpr_at_most(results, max_fpr)) if results else None,
            "top_precision": [asdict(item) for item in top_by_precision(results, top_n)],
        }

    for features in itertools.combinations(FEATURES, combo_size):
        results = scan_combination(rows, features, grid_size)
        combination_key = " AND ".join(features)
        best_fpr_item = best_with_fpr_at_most(results, max_fpr)
        summary["combinations"][combination_key] = {
            "features": list(features),
            f"best_fpr_at_most_{max_fpr}": asdict(best_fpr_item) if best_fpr_item else None,
            "top_precision": [asdict(item) for item in top_by_precision(results, top_n)],
        }
        if features == RECOMMENDED_RULE_FEATURES and best_fpr_item is not None:
            summary["recommended_rule"] = {
                "selection": f"maximize recall with FPR <= {max_fpr}",
                "features": list(features),
                "metrics": asdict(best_fpr_item),
                "rule": [
                    {
                        "feature": feature,
                        "operator": ">=",
                        "threshold": threshold,
                    }
                    for feature, threshold in best_fpr_item.thresholds.items()
                ],
            }

    return summary


def print_summary(summary: dict[str, Any], max_fpr: float) -> None:
    labels = summary["labels"]
    print(f"Rows: {summary['rows']}")
    print(f"Labels: true={labels['true']}, false={labels['false']}")

    print()
    print("Recommended Phase 1 rule")
    recommended_rule = summary.get("recommended_rule")
    if recommended_rule:
        metrics = CombinationMetrics(**recommended_rule["metrics"])
        print(f"Selection: {recommended_rule['selection']}")
        print(format_combo_row(metrics))
    else:
        print("n/a")

    for feature in FEATURES:
        feature_summary = summary["features"][feature]
        print()
        print(f"Feature: {feature}")

        fpr_key = f"best_fpr_at_most_{max_fpr}"
        fpr_item = feature_summary[fpr_key]
        print(
            f"Best recall with FPR <= {max_fpr}: "
            f"{format_row(ThresholdMetrics(**fpr_item) if fpr_item else None)}"
        )

    print()
    print("Combinations")
    for combination_key, combination_summary in summary["combinations"].items():
        print()
        print(f"Rule: {combination_key}")

        fpr_key = f"best_fpr_at_most_{max_fpr}"
        fpr_item = combination_summary[fpr_key]
        print(
            f"Best recall with FPR <= {max_fpr}: "
            f"{format_combo_row(CombinationMetrics(**fpr_item) if fpr_item else None)}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze Phase 1 confident-scoring thresholds.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--max-fpr", type=float, default=0.6)
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument("--combo-size", type=int, default=2)
    parser.add_argument("--grid-size", type=int, default=2000)
    args = parser.parse_args()

    if args.combo_size < 2 or args.combo_size > len(FEATURES):
        raise ValueError(f"--combo-size must be between 2 and {len(FEATURES)}")
    if args.grid_size < 2:
        raise ValueError("--grid-size must be at least 2")

    rows = load_rows(args.dataset)
    summary = build_summary(
        rows=rows,
        max_fpr=args.max_fpr,
        top_n=args.top_n,
        combo_size=args.combo_size,
        grid_size=args.grid_size,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as file:
        json.dump(summary, file, ensure_ascii=False, indent=2)

    print_summary(summary, args.max_fpr)
    print()
    print(f"Saved threshold analysis: {args.output}")


if __name__ == "__main__":
    main()
