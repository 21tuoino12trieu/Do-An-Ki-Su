import os
import json
import argparse
import requests
import urllib3
import pandas as pd
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv() # create .env file or fix below

# ==============================
# CONFIG
# ==============================
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY", "") # Fix Me
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY", "") # Fix Me
LANGFUSE_BASE_URL = os.getenv("LANGFUSE_BASE_URL", "") # Fix Me

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

AUTH = (LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY)
HEADERS = {"Accept": "application/json"}


def parse_time(time_str: str) -> datetime:
    """Convert string -> datetime (ISO format)"""
    return datetime.fromisoformat(time_str).replace(tzinfo=timezone.utc)


def fetch_traces_by_name_and_time(
    name: str,
    start_time: str,
    end_time: str,
    limit: int = 100,
    max_pages: int = None,
):
    """
    Fetch ALL trace data from Langfuse by name and time range.
    Returns complete trace objects without filtering or normalization.
    """
    start_dt = parse_time(start_time)
    end_dt = parse_time(end_time)

    from_ts = start_dt.isoformat().replace("+00:00", "Z")
    to_ts = end_dt.isoformat().replace("+00:00", "Z")

    all_traces = []
    page = 1

    while True:
        params = {
            "page": page,
            "limit": limit,
            "fromTimestamp": from_ts,
            "toTimestamp": to_ts,
        }
        if name:
            params["name"] = name

        resp = requests.get(
            f"{LANGFUSE_BASE_URL}/api/public/traces",
            headers=HEADERS,
            auth=AUTH,
            params=params,
            verify=False
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])

        if not data:
            break

        for trace in data:
            # Get FULL trace details
            try:
                trace_detail = get_trace_details(trace.get("id"))
                all_traces.append(trace_detail)
            except Exception:
                # Fallback to basic trace data
                all_traces.append(trace)

        print(f"Page {page}: fetched {len(data)} traces, total: {len(all_traces)}")

        if len(data) < limit:
            break

        page += 1

        if max_pages and page > max_pages:
            print(f"Reached max pages limit: {max_pages}")
            break

    return all_traces


def fetch_traces_by_time(
    start_time: str,
    end_time: str,
    limit: int = 100,
    max_pages: int = None,
):
    """
    Fetch ALL trace data from Langfuse by time range only (no name filter).
    Returns complete trace objects without filtering or normalization.
    """
    return fetch_traces_by_name_and_time(
        name=None,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        max_pages=max_pages,
    )


def add_7_hours(dt: datetime) -> datetime:
    """Add 7 hours to datetime"""
    from datetime import timedelta
    return dt + timedelta(hours=7)


def get_observation_with_max_start_time(observations: list) -> dict: # Fix me
    """Get observation with highest endTime where output.role = assistant"""
    # Filter observations where output has role = assistant
    assistant_obs = [
        obs for obs in observations
        if isinstance(obs.get("output"), dict) and obs.get("output", {}).get("role") == "assistant"
    ]
    if not assistant_obs:
        return {}
    max_obs = max(assistant_obs, key=lambda x: x.get("startTime", ""))
    return max_obs


def extract_trace_info(trace: dict) -> dict: # Fix me
    """
    Extract specific fields from trace:
    - id
    - name
    - timestamp (add 7 hours)
    - input.username
    - question: content của message cuối trong input.messages
    - response: content của output của observation được filter
    - observations (object with max startTime)
    """
    # Parse timestamp and add 7 hours
    ts = trace.get("timestamp", "")
    if ts:
        dt = parse_time(ts)
        dt_plus_7 = add_7_hours(dt)
        timestamp = dt_plus_7.isoformat().replace("+00:00", "Z")
    else:
        timestamp = ""

    # Get input.username
    input_data = trace.get("input", {})
    username = input_data.get("username", "")

    # Get question: content của message cuối trong input.messages
    messages = input_data.get("messages", [])
    question = ""
    if messages and len(messages) > 0:
        last_message = messages[-1]
        question = last_message.get("content", "")

    # Get observation with max startTime
    observations = trace.get("observations", [])
    max_observation = get_observation_with_max_start_time(observations)

    # Get response: content của output của observation được filter
    response = ""
    if max_observation:
        output = max_observation.get("output", {})
        if isinstance(output, dict):
            response = output.get("content", "")

    return {
        # "id": trace.get("id", ""),
        "name": trace.get("name", ""),
        "timestamp": timestamp,
        "username": username,
        "question": question,
        "response": response,
        # "observations": max_observation,
    }


def format_timestamp(ts: str) -> str:
    """
    Convert ISO timestamp -> dd/mm/YYYY HH:MM:SS
    """
    if not ts:
        return ""

    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return dt.strftime("%d/%m/%Y %H:%M:%S")


def transform_data(data: list[dict]) -> list[dict]:
    """
    Rename fields + format timestamp
    """
    new_data = []

    for item in data:
        new_item = {
            "Tên": item.get("name"),
            "Thời gian": format_timestamp(item.get("timestamp")),
            "Người dùng": item.get("username"),
            "Câu hỏi": item.get("question"),
            "Phản hồi": item.get("response"),
        }
        new_data.append(new_item)

    return new_data


def convert_json_to_xlsx(json_file: str, xlsx_file: str = None):
    """
    Convert JSON log file to XLSX format.
    """
    if xlsx_file is None:
        xlsx_file = json_file.replace(".json", ".xlsx")

    # Load JSON
    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Transform data
    data = transform_data(data)

    # Convert to DataFrame and export
    df = pd.DataFrame(data)
    df.to_excel(xlsx_file, index=False)
    print(f"Saved to {xlsx_file}")


def get_trace_details(trace_id: str):
    """
    Fetch a single trace details by ID.
    """
    url = f"{LANGFUSE_BASE_URL}/api/public/traces/{trace_id}"
    resp = requests.get(url, headers=HEADERS, auth=AUTH, verify=False)
    resp.raise_for_status()
    return resp.json()


def fetch_trace_by_id(trace_id: str):
    """
    Fetch a single trace by ID with all details.
    """
    return get_trace_details(trace_id)


# ==============================
# CLI
# ==============================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch Langfuse logs - all fields, no filter")

    parser.add_argument("--name", help="Trace name filter (optional)")
    parser.add_argument("--start", required=True, help="Start time (ISO format, e.g., 2026-04-01T00:00:00)")
    parser.add_argument("--end", required=True, help="End time (ISO format, e.g., 2026-04-07T23:59:59)")
    parser.add_argument("--limit", type=int, default=100, help="Page size")
    parser.add_argument("--max-pages", type=int, default=None, help="Max pages to fetch")
    parser.add_argument("--trace-id", help="Fetch single trace by ID")
    parser.add_argument("--output", help="Output file path (without extension)")
    parser.add_argument("--format", choices=["json", "xlsx"], default="json", help="Output format (default: json)")

    args = parser.parse_args()

    if args.trace_id:
        # Fetch single trace
        result = fetch_trace_by_id(args.trace_id)
        logs = [result]
    elif args.name:
        # Fetch by name and time
        logs = fetch_traces_by_name_and_time(
            name=args.name,
            start_time=args.start,
            end_time=args.end,
            limit=args.limit,
            max_pages=args.max_pages,
        )
    else:
        # Fetch by time only (no name filter)
        logs = fetch_traces_by_time(
            start_time=args.start,
            end_time=args.end,
            limit=args.limit,
            max_pages=args.max_pages,
        )

    print(f"\nTotal traces fetched: {len(logs)}")

    # Extract only required fields from each trace
    extracted_logs = [extract_trace_info(trace) for trace in logs] # Fix Me
    print(f"Extracted {len(extracted_logs)} traces with required fields")

    # Output
    if args.output:
        if args.format == "json":
            output_file = f"{args.output}.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(extracted_logs, f, indent=2, ensure_ascii=False)
            print(f"Saved to {output_file}")
        elif args.format == "xlsx":
            output_file = f"{args.output}.xlsx"
            # Transform data and export directly to xlsx
            transformed = transform_data(extracted_logs)
            df = pd.DataFrame(transformed)
            df.to_excel(output_file, index=False)
            print(f"Saved to {output_file}")
    else:
        print(json.dumps(extracted_logs, indent=2, ensure_ascii=False))
