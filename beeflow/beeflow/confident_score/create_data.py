import argparse
import json
import re
from pathlib import Path
from typing import Any

from openpyxl import load_workbook


DEFAULT_ENTERPRISE_PATH = Path("confident_score/enterprise.xlsx")
DEFAULT_LOG_PATH = Path("confident_score/log.json")
DEFAULT_OUTPUT_PATH = Path("confident_score/confident_scoring_dataset.relaxed.json")
IGNORED_LABEL_VALUES = {"", "cân nhắc", "can nhac"}
DEFAULT_MIN_RERANK_COUNT = 1


def normalize_query(value: Any) -> str:
    """Normalize query text enough for deterministic joins."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def parse_label(value: Any) -> bool | None:
    """Convert Excel label values to bool when possible."""
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if value == 0:
        return None

    text = str(value).strip().lower()
    if text in IGNORED_LABEL_VALUES:
        return None

    if text in {"true", "1", "yes", "y", "đúng", "dung", "pass", "matched"}:
        return True
    if text in {"false", "0", "no", "n", "sai", "fail", "unmatched"}:
        return False
    return None


def load_enterprise_labels(path: Path) -> dict[str, dict[str, Any]]:
    """Load question labels from enterprise.xlsx keyed by normalized question."""
    workbook = load_workbook(path, read_only=True, data_only=True)
    sheet = workbook.active
    rows = sheet.iter_rows(values_only=True)
    headers = next(rows)

    header_index = {name: index for index, name in enumerate(headers) if name}
    question_index = header_index["Câu hỏi"]
    label_index = header_index["Kết quả đánh giá"]

    labels = {}
    for row in rows:
        question = normalize_query(row[question_index])
        if not question:
            continue

        raw_label = row[label_index]
        label = parse_label(raw_label)
        if label is None:
            continue

        labels[question] = {
            "enterprise_question": question,
            "label": label,
            "raw_label": raw_label,
        }

    return labels


def find_observation(observations: list[dict[str, Any]], name: str) -> dict[str, Any]:
    """Return the latest observation with the given name."""
    matched = [item for item in observations if item.get("name") == name]
    if not matched:
        return {}
    return max(matched, key=lambda item: item.get("startTime", ""))


def get_output_dict(observation: dict[str, Any]) -> dict[str, Any]:
    output = observation.get("output")
    if isinstance(output, dict):
        return output
    return {}


def flatten_single_query_results(results: Any) -> list[dict[str, Any]]:
    """Milvus output can be either [doc, ...] or [[doc, ...]]."""
    if isinstance(results, dict):
        results = results.get("results") or results.get("data") or []
    if not isinstance(results, list):
        return []
    if len(results) == 1 and isinstance(results[0], list):
        results = results[0]
    return [item for item in results if isinstance(item, dict)]


def as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def average(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def extract_origin_query(observations: list[dict[str, Any]]) -> str:
    init_query_obs = find_observation(observations, "init_quiery_fn")
    output = get_output_dict(init_query_obs)
    return normalize_query(output.get("origin_query"))


def extract_retrieve_scores(observations: list[dict[str, Any]]) -> list[float]:
    vec_search_obs = find_observation(observations, "vec_search")
    output = get_output_dict(vec_search_obs)
    results = flatten_single_query_results(output.get("results"))

    scores = []
    for item in results:
        score = as_float(item.get("distance", item.get("score")))
        if score is not None:
            scores.append(score)
    return scores


def extract_rerank_scores(observations: list[dict[str, Any]]) -> list[float]:
    rerank_obs = find_observation(observations, "rerank")
    output = get_output_dict(rerank_obs)
    reranks = output.get("reranks") or []
    if not isinstance(reranks, list):
        return []

    scores = []
    for item in reranks:
        if not isinstance(item, dict):
            continue
        score = as_float(item.get("score"))
        if score is not None:
            scores.append(score)
    return scores


def build_score_features(scores: list[float], prefix: str) -> dict[str, Any]:
    top1 = scores[0] if len(scores) > 0 else None
    top2 = scores[1] if len(scores) > 1 else None

    return {
        f"{prefix}_scores": scores,
        f"{prefix}_count": len(scores),
        f"{prefix}_top1_score": top1,
        f"{prefix}_top2_score": top2,
        f"{prefix}_gap_top1_top2": top1 - top2 if top1 is not None and top2 is not None else None,
        f"{prefix}_avg_top3": average(scores[:3]),
        f"{prefix}_max_score": max(scores) if scores else None,
        f"{prefix}_min_score": min(scores) if scores else None,
    }


def index_logs_by_origin_query(logs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    logs_by_query = {}

    for trace in logs:
        observations = trace.get("observations") or []
        origin_query = extract_origin_query(observations)
        if not origin_query or origin_query in logs_by_query:
            continue

        logs_by_query[origin_query] = trace

    return logs_by_query


def should_keep_rerank_scores(
    rerank_scores: list[float],
    expected_rerank_count: int | None,
    min_rerank_count: int | None,
) -> bool:
    if expected_rerank_count is not None:
        return len(rerank_scores) == expected_rerank_count
    if min_rerank_count is not None:
        return len(rerank_scores) >= min_rerank_count
    return bool(rerank_scores)


def build_dataset(
    logs: list[dict[str, Any]],
    labels_by_query: dict[str, dict[str, Any]],
    expected_rerank_count: int | None,
    min_rerank_count: int | None,
) -> list[dict[str, Any]]:
    dataset = []
    logs_by_query = index_logs_by_origin_query(logs)

    for origin_query, label_info in labels_by_query.items():
        trace = logs_by_query.get(origin_query)
        if trace is None:
            continue

        observations = trace.get("observations") or []
        retrieve_scores = extract_retrieve_scores(observations)
        rerank_scores = extract_rerank_scores(observations)
        if not retrieve_scores:
            continue
        if not should_keep_rerank_scores(rerank_scores, expected_rerank_count, min_rerank_count):
            continue

        row = {
            "trace_id": trace.get("id"),
            "trace_name": trace.get("name"),
            "origin_query": origin_query,
            "enterprise_question": label_info.get("enterprise_question"),
            "label": label_info.get("label"),
            "raw_label": label_info.get("raw_label"),
        }
        row.update(build_score_features(retrieve_scores, "retrieve"))
        row.update(build_score_features(rerank_scores, "rerank"))

        row["max_embedding_score"] = row["retrieve_max_score"]
        row["avg_top3_embedding"] = row["retrieve_avg_top3"]
        row["max_rerank_score"] = row["rerank_max_score"]
        row["rerank_gap"] = row["rerank_gap_top1_top2"]

        dataset.append(row)

    return dataset


def write_json(rows: list[dict[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8") as file:
        json.dump(rows, file, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create Phase 1 confident-scoring dataset from Langfuse logs.")
    parser.add_argument("--enterprise", type=Path, default=DEFAULT_ENTERPRISE_PATH)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--min-rerank-count", type=int, default=DEFAULT_MIN_RERANK_COUNT)
    parser.add_argument("--expected-rerank-count", type=int, default=None, help="Use strict filtering and override --min-rerank-count")
    args = parser.parse_args()

    min_rerank_count = None if args.expected_rerank_count is not None else args.min_rerank_count

    labels_by_query = load_enterprise_labels(args.enterprise)
    with args.log.open("r", encoding="utf-8") as file:
        logs = json.load(file)

    dataset = build_dataset(
        logs=logs,
        labels_by_query=labels_by_query,
        expected_rerank_count=args.expected_rerank_count,
        min_rerank_count=min_rerank_count,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_json(dataset, args.output)

    print(f"Rows: {len(dataset)}")
    print(f"Saved JSON: {args.output}")


if __name__ == "__main__":
    main()
