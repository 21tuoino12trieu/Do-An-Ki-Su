import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_DATASET_PATH = Path("confident_score/confident_scoring_dataset.relaxed.json")
DEFAULT_OUTPUT_PATH = Path("confident_score/histograms.svg")
FEATURES = [
    ("max_embedding_score", "Max embedding score"),
    ("max_rerank_score", "Max rerank score"),
]


def load_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON array in {path}")
    return [item for item in data if isinstance(item, dict)]


def numeric_values(rows: list[dict[str, Any]], feature: str, label: bool) -> list[float]:
    values = []
    for row in rows:
        if row.get("label") is not label:
            continue

        value = row.get(feature)
        if isinstance(value, (int, float)):
            values.append(float(value))
    return values


def bin_range(values: list[float]) -> tuple[float, float]:
    min_value = min(values)
    max_value = max(values)
    if min_value == max_value:
        return min_value - 0.5, max_value + 0.5
    return min_value, max_value


def histogram_shares(values: list[float], min_value: float, max_value: float, bins: int) -> list[float]:
    counts = [0] * bins
    if not values:
        return [0.0] * bins

    span = max_value - min_value
    for value in values:
        if value >= max_value:
            index = bins - 1
        else:
            index = int((value - min_value) / span * bins)
            index = max(0, min(index, bins - 1))
        counts[index] += 1

    total = len(values)
    return [count / total for count in counts]


def fmt(value: float) -> str:
    if abs(value) >= 10:
        return f"{value:.1f}"
    return f"{value:.3f}".rstrip("0").rstrip(".")


def svg_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render_panel(
    feature: str,
    title: str,
    true_values: list[float],
    false_values: list[float],
    x: int,
    y: int,
    width: int,
    height: int,
    bins: int,
) -> str:
    all_values = true_values + false_values
    if not all_values:
        return ""

    min_value, max_value = bin_range(all_values)
    true_shares = histogram_shares(true_values, min_value, max_value, bins)
    false_shares = histogram_shares(false_values, min_value, max_value, bins)
    max_share = max(true_shares + false_shares) or 1.0

    margin_left = 58
    margin_right = 16
    margin_top = 42
    margin_bottom = 48
    plot_x = x + margin_left
    plot_y = y + margin_top
    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom
    bin_width = plot_width / bins
    true_bar_width = bin_width * 0.43
    false_bar_width = bin_width * 0.43

    parts = [
        f'<g class="panel" transform="translate({x},{y})">',
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff" stroke="#d9dee7"/>',
        f'<text x="16" y="24" font-size="15" font-weight="700" fill="#172033">{svg_escape(title)}</text>',
        f'<text x="{width - 16}" y="24" text-anchor="end" font-size="11" fill="#637083">'
        f'true={len(true_values)} false={len(false_values)}</text>',
        "</g>",
        f'<line x1="{plot_x}" y1="{plot_y}" x2="{plot_x}" y2="{plot_y + plot_height}" stroke="#8a94a6"/>',
        f'<line x1="{plot_x}" y1="{plot_y + plot_height}" x2="{plot_x + plot_width}" y2="{plot_y + plot_height}" stroke="#8a94a6"/>',
    ]

    for index, share in enumerate(true_shares):
        bar_height = share / max_share * plot_height
        bar_x = plot_x + index * bin_width + bin_width * 0.07
        bar_y = plot_y + plot_height - bar_height
        parts.append(
            f'<rect x="{bar_x:.2f}" y="{bar_y:.2f}" width="{true_bar_width:.2f}" '
            f'height="{bar_height:.2f}" fill="#2563eb" opacity="0.68"/>'
        )

    for index, share in enumerate(false_shares):
        bar_height = share / max_share * plot_height
        bar_x = plot_x + index * bin_width + bin_width * 0.50
        bar_y = plot_y + plot_height - bar_height
        parts.append(
            f'<rect x="{bar_x:.2f}" y="{bar_y:.2f}" width="{false_bar_width:.2f}" '
            f'height="{bar_height:.2f}" fill="#dc2626" opacity="0.68"/>'
        )

    for tick_index in range(5):
        ratio = tick_index / 4
        tick_value = min_value + ratio * (max_value - min_value)
        tick_x = plot_x + ratio * plot_width
        parts.extend(
            [
                f'<line x1="{tick_x:.2f}" y1="{plot_y + plot_height}" '
                f'x2="{tick_x:.2f}" y2="{plot_y + plot_height + 5}" stroke="#8a94a6"/>',
                f'<text x="{tick_x:.2f}" y="{plot_y + plot_height + 20}" '
                f'text-anchor="middle" font-size="10" fill="#637083">{fmt(tick_value)}</text>',
            ]
        )

    for tick_index in range(4):
        ratio = tick_index / 3
        tick_share = ratio * max_share
        tick_y = plot_y + plot_height - ratio * plot_height
        parts.extend(
            [
                f'<line x1="{plot_x - 5}" y1="{tick_y:.2f}" x2="{plot_x}" y2="{tick_y:.2f}" stroke="#8a94a6"/>',
                f'<text x="{plot_x - 9}" y="{tick_y + 3:.2f}" text-anchor="end" '
                f'font-size="10" fill="#637083">{fmt(tick_share)}</text>',
            ]
        )

    parts.extend(
        [
            f'<text x="{plot_x + plot_width / 2:.2f}" y="{y + height - 10}" '
            f'text-anchor="middle" font-size="11" fill="#455064">{svg_escape(feature)}</text>',
            f'<text x="{x + 16}" y="{y + height - 10}" font-size="10" fill="#637083">share</text>',
        ]
    )
    return "\n".join(parts)


def render_svg(rows: list[dict[str, Any]], bins: int) -> str:
    panel_width = 560
    panel_height = 330
    gap = 24
    top = 72
    left = 24
    panel_rows = (len(FEATURES) + 1) // 2
    width = left * 2 + panel_width * 2 + gap
    height = top + panel_height * panel_rows + gap * max(panel_rows - 1, 0) + 34
    true_count = sum(1 for row in rows if row.get("label") is True)
    false_count = sum(1 for row in rows if row.get("label") is False)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#f6f8fb"/>',
        '<style>text { font-family: Arial, sans-serif; }</style>',
        f'<text x="{left}" y="30" font-size="22" font-weight="700" fill="#111827">'
        "Confident scoring feature histograms</text>",
        f'<text x="{left}" y="52" font-size="12" fill="#637083">'
        f'Rows={len(rows)} true={true_count} false={false_count} bins={bins}. '
        "Bars show per-label share, not raw count.</text>",
        f'<rect x="{width - 210}" y="23" width="12" height="12" fill="#2563eb" opacity="0.68"/>',
        f'<text x="{width - 192}" y="33" font-size="12" fill="#455064">label=true</text>',
        f'<rect x="{width - 110}" y="23" width="12" height="12" fill="#dc2626" opacity="0.68"/>',
        f'<text x="{width - 92}" y="33" font-size="12" fill="#455064">label=false</text>',
    ]

    for index, (feature, title) in enumerate(FEATURES):
        panel_x = left + (index % 2) * (panel_width + gap)
        panel_y = top + (index // 2) * (panel_height + gap)
        true_values = numeric_values(rows, feature, True)
        false_values = numeric_values(rows, feature, False)
        parts.append(
            render_panel(
                feature=feature,
                title=title,
                true_values=true_values,
                false_values=false_values,
                x=panel_x,
                y=panel_y,
                width=panel_width,
                height=panel_height,
                bins=bins,
            )
        )

    parts.append("</svg>")
    return "\n".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot Phase 1 confident-scoring histograms.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--bins", type=int, default=30)
    args = parser.parse_args()

    if args.bins < 2:
        raise ValueError("--bins must be at least 2")

    rows = load_rows(args.dataset)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_svg(rows, args.bins), encoding="utf-8")

    true_count = sum(1 for row in rows if row.get("label") is True)
    false_count = sum(1 for row in rows if row.get("label") is False)
    print(f"Rows: {len(rows)}")
    print(f"Labels: true={true_count}, false={false_count}")
    print(f"Saved histogram SVG: {args.output}")


if __name__ == "__main__":
    main()
