"""
Exporter module for text2sql.
Chịu trách nhiệm export dữ liệu ra CSV và upload lên S3.
"""
from typing import Dict, Any, List
import io
import csv
import time
import requests
import yaml
from datetime import datetime
from beegenerate.const import BEEGEN_ROOT

from threading import Lock

_token_lock = Lock()


def _load_beegen_multimedia_config() -> Dict[str, Any]:
    config_path = BEEGEN_ROOT / "config" / "beegen_multimedia.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


BEEGEN_MULTIMEDIA_CONFIG = _load_beegen_multimedia_config()

_TOKEN_CACHE = {
    "access_token": None,
    "refresh_token": None,
    "access_expire_at": 0,
    "refresh_expire_at": 0,
}


def _login_keycloak():
    cfg = BEEGEN_MULTIMEDIA_CONFIG["keycloak"]

    response = requests.post(
        cfg["token_url"],
        data={
            "grant_type": "password",
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "username": cfg["username"],
            "password": cfg["password"],
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=5,
        verify=False
    )

    response.raise_for_status()
    data = response.json()

    now = time.time()

    _TOKEN_CACHE["access_token"] = data["access_token"]
    _TOKEN_CACHE["refresh_token"] = data.get("refresh_token")
    _TOKEN_CACHE["access_expire_at"] = now + data["expires_in"] - 30
    _TOKEN_CACHE["refresh_expire_at"] = now + data["refresh_expires_in"] - 30


def _refresh_token():
    cfg = BEEGEN_MULTIMEDIA_CONFIG["keycloak"]

    response = requests.post(
        cfg["token_url"],
        data={
            "grant_type": "refresh_token",
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "refresh_token": _TOKEN_CACHE["refresh_token"],
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=5,
        verify=False
    )

    response.raise_for_status()
    data = response.json()

    now = time.time()

    _TOKEN_CACHE["access_token"] = data["access_token"]
    _TOKEN_CACHE["refresh_token"] = data.get("refresh_token") or _TOKEN_CACHE["refresh_token"]
    _TOKEN_CACHE["access_expire_at"] = now + data["expires_in"] - 30
    _TOKEN_CACHE["refresh_expire_at"] = now + data.get("refresh_expires_in", 10800) - 30


def _is_token_valid(leeway: int = 5) -> bool:
    expire_at = _TOKEN_CACHE["access_expire_at"]
    return _TOKEN_CACHE["access_token"] and expire_at and time.time() < (expire_at - leeway)


def _get_keycloak_token() -> str:
    # Đi thẳng không cần lock
    if _is_token_valid():
        return _TOKEN_CACHE["access_token"]

    with _token_lock:
        now = time.time()

        try:
            # 1. access token còn sống
            if _is_token_valid():
                return _TOKEN_CACHE["access_token"]

            # 2. refresh
            if _TOKEN_CACHE["refresh_token"] and now < _TOKEN_CACHE["refresh_expire_at"]:
                try:
                    _refresh_token()
                    return _TOKEN_CACHE["access_token"]
                except Exception:
                    # refresh fail → login lại
                    _TOKEN_CACHE["refresh_token"] = None
                    pass

            # 3. login lại
            _login_keycloak()
            return _TOKEN_CACHE["access_token"]

        except Exception as e:
            # fallback cuối cùng để tránh crash hệ thống
            raise RuntimeError(f"Keycloak token error: {str(e)}")


def create_csv_and_upload_s3(
    data: List[Dict],
    bot_id: str,
    client_message_id: str
) -> Dict[str, Any]:
    """
    Create CSV from data and upload to S3.

    Args:
        data (List[Dict]): List of dictionaries containing query results
        sql (str): The SQL query that was executed
        bot_id (str): Bot ID for the upload API
        client_message_id (str): Client message ID for the upload API

    Returns:
        download_link (str): Full URL to download the file
        file_id (str): File ID from S3 response
        file_name (str): Name of the uploaded file
        row_count (int): Number of rows exported
        error (str): Error message if any
    """
    if not data:
        return {
            "download_link": "",
            "file_id": "",
            "file_name": "",
            "row_count": 0,
            "error": "No data to export"
        }
    try:
        access_token = _get_keycloak_token()
    except Exception as e:
        return {
            "download_link": "",
            "file_id": "",
            "file_name": "",
            "row_count": len(data),
            "error": f"Cannot get access token: {str(e)}"
        }
    cfg = BEEGEN_MULTIMEDIA_CONFIG["beegen_multimedia"]

    base_url = cfg["base_url"]
    domain = cfg["domain"]
    upload_path = cfg["upload_path"]
    download_path = cfg["download_path"]
    # Create CSV content
    output = io.StringIO()
    if data:
        fieldnames = data[0].keys()
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)

    csv_content = output.getvalue()
    output.close()

    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y_%m_%d_T_%H_%M_%S")
    filename = f"export_data_{timestamp}.csv"

    # Upload to S3 via API
    upload_url = f"{base_url}{upload_path}?botId={bot_id}&type=BOT_RESPONSE"

    files = {
        'files': (filename, csv_content, 'text/csv')
    }

    headers = {
        'accept': '*/*',
        'clientMessageId': client_message_id,
        'Authorization': f"Bearer {access_token}"
    }

    try:
        response = requests.post(upload_url, files=files, headers=headers, timeout=10, verify=False)
        if response.status_code == 401:
            _TOKEN_CACHE["access_token"] = None
            access_token = _get_keycloak_token()
            headers["Authorization"] = f"Bearer {access_token}"
            response = requests.post(upload_url, files=files, headers=headers, timeout=10, verify=False)

        response.raise_for_status()
        response_data = response.json()

        if response_data.get("status") == 200 and response_data.get("data"):
            file_info = response_data["data"][0]
            file_id = file_info.get("id", "")
            file_name = file_info.get("fileName", filename)

            # Construct download link
            download_link = f"{domain}{download_path}?botId={bot_id}&id={file_id}&name={file_name}"

            return {
                "download_link": download_link,
                "file_id": file_id,
                "file_name": file_name,
                "row_count": len(data),
                "error": None
            }
        else:
            return {
                "download_link": "",
                "file_id": "",
                "file_name": filename,
                "row_count": len(data),
                "error": f"Upload failed: {response_data.get('error', 'Unknown error')}"
            }

    except Exception as e:
        return {
            "download_link": "",
            "file_id": "",
            "file_name": filename,
            "row_count": len(data),
            "error": f"Upload failed: {str(e)}"
        }
