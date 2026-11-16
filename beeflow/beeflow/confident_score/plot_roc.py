import argparse
import json
from pathlib import Path
from typing import Any

from analyze_thresholds import (
    FEATURES,
    RECOMMENDED_RULE_FEATURES,
    CombinationMetrics,
    ThresholdMetrics,
    best_with_fpr_at_most,
    evaluate_combination,
    load_rows,
    quantile_thresholds,
    scan_feature,
)


DEFAULT_DATASET_PATH = Path("confident_score/confident_scoring_dataset.relaxed.json")
DEFAULT_OUTPUT_PATH = Path("confident_score/roc_curves.svg")
FEATURE_TITLES = {
    "max_embedding_score": "Max embedding score",
    "max_rerank_score": "Max rerank score",
}


def fmt(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def svg_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def roc_points(results: list[ThresholdMetrics]) -> list[tuple[float, float, float]]:
    points = sorted(
        {(item.fpr, item.recall, item.threshold) for item in results},
        key=lambda item: (item[0], item[1], item[2]),
    )
    return points


def roc_frontier_points(results: list[ThresholdMetrics]) -> list[tuple[float, float, float]]:
    best_by_fpr: dict[float, ThresholdMetrics] = {}
    for item in results:
        existing = best_by_fpr.get(item.fpr)
        if existing is None or (item.recall, item.precision, item.f1) > (
            existing.recall,
            existing.precision,
            existing.f1,
        ):
            best_by_fpr[item.fpr] = item

    frontier = []
    best_recall_so_far = -1.0
    for item in sorted(best_by_fpr.values(), key=lambda value: (value.fpr, value.recall)):
        if item.recall > best_recall_so_far:
            frontier.append((item.fpr, item.recall, item.threshold))
            best_recall_so_far = item.recall
    return frontier


def auc(points: list[tuple[float, float, float]]) -> float:
    if len(points) < 2:
        return 0.0

    best_by_fpr: dict[float, float] = {}
    for fpr, recall, _threshold in points:
        best_by_fpr[fpr] = max(best_by_fpr.get(fpr, 0.0), recall)

    curve = sorted(best_by_fpr.items())
    area = 0.0
    previous_fpr, previous_recall = curve[0]
    for fpr, recall in curve[1:]:
        area += (fpr - previous_fpr) * (previous_recall + recall) / 2
        previous_fpr = fpr
        previous_recall = recall
    return area


def combination_results(
    rows: list[dict[str, Any]],
    features: tuple[str, ...],
    grid_size: int,
) -> list[CombinationMetrics]:
    feature_thresholds = [
        quantile_thresholds(rows, feature, grid_size)
        for feature in features
    ]
    results = []
    for embedding_threshold in feature_thresholds[0]:
        for rerank_threshold in feature_thresholds[1]:
            thresholds = {
                features[0]: embedding_threshold,
                features[1]: rerank_threshold,
            }
            results.append(evaluate_combination(rows, thresholds))
    return results


def frontier_points(results: list[CombinationMetrics]) -> list[CombinationMetrics]:
    best_by_fpr: dict[float, CombinationMetrics] = {}
    for item in results:
        existing = best_by_fpr.get(item.fpr)
        if existing is None or (item.recall, item.precision, item.f1) > (
            existing.recall,
            existing.precision,
            existing.f1,
        ):
            best_by_fpr[item.fpr] = item

    frontier = []
    best_recall_so_far = -1.0
    for item in sorted(best_by_fpr.values(), key=lambda value: (value.fpr, value.recall)):
        if item.recall > best_recall_so_far:
            frontier.append(item)
            best_recall_so_far = item.recall
    return frontier


def point_to_svg(
    fpr: float,
    recall: float,
    plot_x: float,
    plot_y: float,
    plot_width: float,
    plot_height: float,
) -> tuple[float, float]:
    x = plot_x + max(0.0, min(fpr, 1.0)) * plot_width
    y = plot_y + (1.0 - max(0.0, min(recall, 1.0))) * plot_height
    return x, y


def render_axes(
    x: int,
    y: int,
    width: int,
    height: int,
    title: str,
    subtitle: str,
    max_fpr: float,
) -> tuple[list[str], float, float, float, float]:
    margin_left = 58
    margin_right = 18
    margin_top = 54
    margin_bottom = 56
    plot_x = x + margin_left
    plot_y = y + margin_top
    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom

    parts = [
        f'<rect x="{x}" y="{y}" width="{width}" height="{height}" fill="#ffffff" stroke="#d9dee7"/>',
        f'<text x="{x + 16}" y="{y + 25}" font-size="15" font-weight="700" fill="#172033">{svg_escape(title)}</text>',
        f'<text x="{x + 16}" y="{y + 43}" font-size="11" fill="#637083">{svg_escape(subtitle)}</text>',
        f'<line x1="{plot_x}" y1="{plot_y}" x2="{plot_x}" y2="{plot_y + plot_height}" stroke="#8a94a6"/>',
        f'<line x1="{plot_x}" y1="{plot_y + plot_height}" x2="{plot_x + plot_width}" y2="{plot_y + plot_height}" stroke="#8a94a6"/>',
    ]

    for tick_index in range(6):
        ratio = tick_index / 5
        tick_x = plot_x + ratio * plot_width
        tick_y = plot_y + plot_height - ratio * plot_height
        parts.extend(
            [
                f'<line x1="{tick_x:.2f}" y1="{plot_y}" x2="{tick_x:.2f}" y2="{plot_y + plot_height}" '
                'stroke="#edf0f5"/>',
                f'<line x1="{tick_x:.2f}" y1="{plot_y + plot_height}" x2="{tick_x:.2f}" '
                f'y2="{plot_y + plot_height + 5}" stroke="#8a94a6"/>',
                f'<text x="{tick_x:.2f}" y="{plot_y + plot_height + 20}" text-anchor="middle" '
                f'font-size="10" fill="#637083">{fmt(ratio)}</text>',
                f'<line x1="{plot_x}" y1="{tick_y:.2f}" x2="{plot_x + plot_width}" y2="{tick_y:.2f}" '
                'stroke="#edf0f5"/>',
                f'<line x1="{plot_x - 5}" y1="{tick_y:.2f}" x2="{plot_x}" y2="{tick_y:.2f}" '
                'stroke="#8a94a6"/>',
                f'<text x="{plot_x - 9}" y="{tick_y + 3:.2f}" text-anchor="end" '
                f'font-size="10" fill="#637083">{fmt(ratio)}</text>',
            ]
        )

    baseline_x1, baseline_y1 = point_to_svg(0.0, 0.0, plot_x, plot_y, plot_width, plot_height)
    baseline_x2, baseline_y2 = point_to_svg(1.0, 1.0, plot_x, plot_y, plot_width, plot_height)
    max_fpr_x, _ = point_to_svg(max_fpr, 0.0, plot_x, plot_y, plot_width, plot_height)
    parts.extend(
        [
            f'<line x1="{baseline_x1:.2f}" y1="{baseline_y1:.2f}" x2="{baseline_x2:.2f}" '
            f'y2="{baseline_y2:.2f}" stroke="#b8c0cc" stroke-dasharray="4 4"/>',
            f'<line x1="{max_fpr_x:.2f}" y1="{plot_y}" x2="{max_fpr_x:.2f}" '
            f'y2="{plot_y + plot_height}" stroke="#dc2626" stroke-dasharray="4 4"/>',
            f'<text x="{max_fpr_x + 5:.2f}" y="{plot_y + 13}" font-size="10" fill="#dc2626">'
            f'FPR &lt;= {fmt(max_fpr)}</text>',
            f'<text x="{plot_x + plot_width / 2:.2f}" y="{y + height - 12}" text-anchor="middle" '
            'font-size="11" fill="#455064">False positive rate</text>',
            f'<text x="{x + 16}" y="{y + height - 12}" font-size="10" fill="#637083">Recall / TPR</text>',
        ]
    )
    return parts, plot_x, plot_y, plot_width, plot_height


def render_feature_panel(
    results: list[ThresholdMetrics],
    feature: str,
    best_item: ThresholdMetrics | None,
    x: int,
    y: int,
    width: int,
    height: int,
    max_fpr: float,
) -> str:
    raw_points = roc_points(results)
    curve_points = roc_frontier_points(results)
    parts, plot_x, plot_y, plot_width, plot_height = render_axes(
        x=x,
        y=y,
        width=width,
        height=height,
        title=FEATURE_TITLES.get(feature, feature),
        subtitle=f"AUC={auc(curve_points):.4f}; thresholds={len(raw_points)}; curve points={len(curve_points)}",
        max_fpr=max_fpr,
    )

    if curve_points:
        path_points = [
            point_to_svg(fpr, recall, plot_x, plot_y, plot_width, plot_height)
            for fpr, recall, _threshold in curve_points
        ]
        path = " ".join(
            ("M" if index == 0 else "L") + f"{point_x:.2f},{point_y:.2f}"
            for index, (point_x, point_y) in enumerate(path_points)
        )
        parts.append(f'<path d="{path}" fill="none" stroke="#2563eb" stroke-width="3"/>')

    if best_item is not None:
        point_x, point_y = point_to_svg(
            best_item.fpr,
            best_item.recall,
            plot_x,
            plot_y,
            plot_width,
            plot_height,
        )
        parts.extend(
            [
                f'<circle cx="{point_x:.2f}" cy="{point_y:.2f}" r="5" fill="#dc2626"/>',
                f'<text x="{point_x + 8:.2f}" y="{point_y - 8:.2f}" font-size="10" fill="#172033">'
                f't={best_item.threshold:.4f}</text>',
            ]
        )

    return "\n".join(parts)


def render_combination_panel(
    results: list[CombinationMetrics],
    best_item: CombinationMetrics | None,
    x: int,
    y: int,
    width: int,
    height: int,
    max_fpr: float,
) -> str:
    frontier = frontier_points(results)
    parts, plot_x, plot_y, plot_width, plot_height = render_axes(
        x=x,
        y=y,
        width=width,
        height=height,
        title="Rule: embedding AND rerank",
        subtitle=f"Grid points={len(results)}; frontier points={len(frontier)}",
        max_fpr=max_fpr,
    )

    for item in results:
        point_x, point_y = point_to_svg(item.fpr, item.recall, plot_x, plot_y, plot_width, plot_height)
        parts.append(f'<circle cx="{point_x:.2f}" cy="{point_y:.2f}" r="1.6" fill="#8a94a6" opacity="0.28"/>')

    if frontier:
        path_points = [
            point_to_svg(item.fpr, item.recall, plot_x, plot_y, plot_width, plot_height)
            for item in frontier
        ]
        path = " ".join(
            ("M" if index == 0 else "L") + f"{point_x:.2f},{point_y:.2f}"
            for index, (point_x, point_y) in enumerate(path_points)
        )
        parts.append(f'<path d="{path}" fill="none" stroke="#2563eb" stroke-width="2.2"/>')

    if best_item is not None:
        point_x, point_y = point_to_svg(
            best_item.fpr,
            best_item.recall,
            plot_x,
            plot_y,
            plot_width,
            plot_height,
        )
        embedding_threshold = best_item.thresholds[RECOMMENDED_RULE_FEATURES[0]]
        rerank_threshold = best_item.thresholds[RECOMMENDED_RULE_FEATURES[1]]
        parts.extend(
            [
                f'<circle cx="{point_x:.2f}" cy="{point_y:.2f}" r="5.5" fill="#dc2626"/>',
                f'<text x="{point_x + 8:.2f}" y="{point_y - 8:.2f}" font-size="10" fill="#172033">'
                f'emb={embedding_threshold:.4f}, rerank={rerank_threshold:.4f}</text>',
            ]
        )

    return "\n".join(parts)


def render_svg(
    rows: list[dict[str, Any]],
    max_fpr: float,
    grid_size: int,
) -> str:
    feature_results = {
        feature: scan_feature(rows, feature)
        for feature in FEATURES
    }
    feature_best = {
        feature: best_with_fpr_at_most(results, max_fpr)
        for feature, results in feature_results.items()
    }
    combo_results = combination_results(rows, RECOMMENDED_RULE_FEATURES, grid_size)
    combo_best = best_with_fpr_at_most(combo_results, max_fpr)

    panel_width = 560
    panel_height = 350
    gap = 24
    left = 24
    top = 78
    width = left * 2 + panel_width * 2 + gap
    height = top + panel_height * 2 + gap + 36
    true_count = sum(1 for row in rows if row.get("label") is True)
    false_count = sum(1 for row in rows if row.get("label") is False)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#f6f8fb"/>',
        '<style>text { font-family: Arial, sans-serif; }</style>',
        f'<text x="{left}" y="30" font-size="22" font-weight="700" fill="#111827">'
        "Confident scoring ROC analysis</text>",
        f'<text x="{left}" y="53" font-size="12" fill="#637083">'
        f'Rows={len(rows)} true={true_count} false={false_count}. '
        "Red marker is selected by max recall under the FPR limit.</text>",
        f'<rect x="{width - 260}" y="24" width="26" height="3" fill="#2563eb"/>',
        f'<text x="{width - 226}" y="31" font-size="12" fill="#455064">ROC/frontier</text>',
        f'<circle cx="{width - 125}" cy="28" r="5" fill="#dc2626"/>',
        f'<text x="{width - 113}" y="31" font-size="12" fill="#455064">selected rule</text>',
    ]

    for index, feature in enumerate(FEATURES):
        panel_x = left + index * (panel_width + gap)
        panel_y = top
        parts.append(
            render_feature_panel(
                results=feature_results[feature],
                feature=feature,
                best_item=feature_best[feature],
                x=panel_x,
                y=panel_y,
                width=panel_width,
                height=panel_height,
                max_fpr=max_fpr,
            )
        )

    parts.append(
        render_combination_panel(
            results=combo_results,
            best_item=combo_best,
            x=left,
            y=top + panel_height + gap,
            width=panel_width * 2 + gap,
            height=panel_height,
            max_fpr=max_fpr,
        )
    )
    parts.append("</svg>")
    return "\n".join(parts)


def write_analysis_points(
    rows: list[dict[str, Any]],
    output: Path,
    max_fpr: float,
    grid_size: int,
) -> None:
    feature_payload = {}
    for feature in FEATURES:
        results = scan_feature(rows, feature)
        feature_payload[feature] = [
            {
                "threshold": item.threshold,
                "fpr": item.fpr,
                "recall": item.recall,
                "precision": item.precision,
                "tp": item.tp,
                "fp": item.fp,
                "tn": item.tn,
                "fn": item.fn,
            }
            for item in results
        ]

    combo_results = combination_results(rows, RECOMMENDED_RULE_FEATURES, grid_size)
    payload = {
        "criteria": {
            "max_fpr": max_fpr,
            "grid_size": grid_size,
        },
        "features": feature_payload,
        "combination": {
            "features": list(RECOMMENDED_RULE_FEATURES),
            "points": [
                {
                    "thresholds": item.thresholds,
                    "fpr": item.fpr,
                    "recall": item.recall,
                    "precision": item.precision,
                    "tp": item.tp,
                    "fp": item.fp,
                    "tn": item.tn,
                    "fn": item.fn,
                }
                for item in combo_results
            ],
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot Phase 1 confident-scoring ROC curves.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--points-output", type=Path, default=None)
    parser.add_argument("--max-fpr", type=float, default=0.10)
    parser.add_argument("--grid-size", type=int, default=50)
    args = parser.parse_args()

    if args.grid_size < 2:
        raise ValueError("--grid-size must be at least 2")
    if args.max_fpr < 0 or args.max_fpr > 1:
        raise ValueError("--max-fpr must be between 0 and 1")

    rows = load_rows(args.dataset)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_svg(rows, args.max_fpr, args.grid_size), encoding="utf-8")
    if args.points_output is not None:
        write_analysis_points(rows, args.points_output, args.max_fpr, args.grid_size)

    true_count = sum(1 for row in rows if row.get("label") is True)
    false_count = sum(1 for row in rows if row.get("label") is False)
    print(f"Rows: {len(rows)}")
    print(f"Labels: true={true_count}, false={false_count}")
    print(f"Saved ROC SVG: {args.output}")
    if args.points_output is not None:
        print(f"Saved ROC points: {args.points_output}")


if __name__ == "__main__":
    main()
