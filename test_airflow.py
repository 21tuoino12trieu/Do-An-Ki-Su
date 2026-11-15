"""python test_airflow.py [--read-only] — DAG thật qua API Airflow 3.

Chế độ mặc định trigger một run gửi/đọc Kafka và lưu manifest.
--read-only kiểm tra run đã lưu, không tạo run mới. Không in mật khẩu/JWT.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import uuid

ROOT = Path(__file__).resolve().parent
BASE = "http://127.0.0.1:8080"
DAG = "infra_kafka_smoke"
MANIFEST = ROOT / "tests/output/airflow_smoke_manifest.json"


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--read-only", action="store_true")
    args = parser.parse_args()
    token = None
    restore_pause = False

    def api(path, method="GET", body=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        request = Request(BASE + path, method=method, headers=headers,
                          data=json.dumps(body).encode() if body is not None else None)
        with urlopen(request, timeout=15) as response:
            return json.load(response)

    try:
        health = api("/api/v2/monitor/health")
        for key in ("metadatabase", "scheduler", "dag_processor"):
            if health.get(key, {}).get("status") != "healthy":
                raise RuntimeError("Thành phần Airflow chưa healthy: " + key)
        password = json.loads((ROOT / "infra/airflow/secrets/passwords.json").read_text())["admin"]
        token = api("/auth/token", "POST", {"username": "admin", "password": password})["access_token"]
        print("[1] API, PostgreSQL, scheduler và DAG processor healthy; đăng nhập OK.", flush=True)
        if args.read_only:
            run_id = json.loads(MANIFEST.read_text())["run_id"]
        else:
            dag = api("/api/v2/dags/" + DAG)
            restore_pause = dag["is_paused"]
            if restore_pause:
                api("/api/v2/dags/" + DAG, "PATCH", {"is_paused": False})
            run_id = "manual__smoke_" + uuid.uuid4().hex
            api(f"/api/v2/dags/{DAG}/dagRuns", "POST", {
                "dag_run_id": run_id, "logical_date": datetime.now(timezone.utc).isoformat(), "conf": {}})
            MANIFEST.parent.mkdir(parents=True, exist_ok=True)
            MANIFEST.write_text(json.dumps({"dag_id": DAG, "run_id": run_id}, indent=2), encoding="utf-8")
            print("[2] Đã trigger:", run_id, flush=True)
        deadline = time.monotonic() + 180
        last_state = None
        while time.monotonic() < deadline:
            run = api(f"/api/v2/dags/{DAG}/dagRuns/{run_id}")
            state = run["state"]
            if state != last_state:
                print("    Run state:", state, flush=True)
                last_state = state
            if state == "failed":
                raise RuntimeError("DAG failed; mở giao diện xem task log.")
            if state == "success":
                tasks = api(f"/api/v2/dags/{DAG}/dagRuns/{run_id}/taskInstances")["task_instances"]
                if {t["task_id"] for t in tasks} != {"send_event", "verify_event"} or any(t["state"] != "success" for t in tasks):
                    raise RuntimeError("Chưa xác nhận đủ hai task success.")
                print("[3] send_event và verify_event đều success.")
                print("THÀNH CÔNG. UI:", BASE)
                return 0
            time.sleep(3)
        raise RuntimeError("Hết 180 giây chờ DAG hoàn tất.")
    except HTTPError as exc:
        print("THẤT BẠI: HTTP", exc.code, "— kiểm tra API, DAG đã được parse và tài khoản.")
        return 1
    except Exception as exc:
        print("THẤT BẠI:", type(exc).__name__)
        if isinstance(exc, RuntimeError):
            print(str(exc))
        return 1
    finally:
        if restore_pause and token:
            try:
                api("/api/v2/dags/" + DAG, "PATCH", {"is_paused": True})
                print("Đã trả DAG về trạng thái paused.")
            except Exception:
                print("Chưa khôi phục được paused; kiểm tra trên giao diện.")


if __name__ == "__main__":
    raise SystemExit(main())
