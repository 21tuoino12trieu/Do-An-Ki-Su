from typing import Dict, Any, List
import requests
import yaml
from beegenerate.const import BEEGEN_ROOT
import logging

logger = logging.getLogger(__name__)


# Load Bytebase API configuration from YAML
def _load_bytebase_config() -> Dict[str, Any]:
    config_path = BEEGEN_ROOT / "config" / "bytebase.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


BYTEBASE_CONFIG = _load_bytebase_config()

def _build_count_query(query: str) -> str:
    """Wrap original query thành COUNT(*) subquery."""
    clean_query = query.strip().rstrip(";").strip()
    return f"SELECT COUNT(*) AS TOTAL_COUNT FROM ({clean_query}) q"

def _parse_rows(result: Dict[str, Any]) -> List[Dict]:
    """Parse rows từ Bytebase result block thành list of dicts."""
    column_names = result.get("columnNames", [])
    rows = result.get("rows", [])
    formatted = []

    for row in rows:
        if "values" not in row:
            continue
        row_dict = {}
        for i, col_name in enumerate(column_names):
            if i >= len(row["values"]):
                continue
            value = row["values"][i]
            if "stringValue" in value:
                row_dict[col_name] = value["stringValue"]
            elif "nullValue" in value:
                row_dict[col_name] = None
            elif "numberValue" in value:
                row_dict[col_name] = value["numberValue"]
            elif "boolValue" in value:
                row_dict[col_name] = value["boolValue"]
            elif "timestampValue" in value:
                ts = value["timestampValue"]
                row_dict[col_name] = ts["googleTimestamp"] if isinstance(ts, dict) and "googleTimestamp" in ts else ts
            else:
                row_dict[col_name] = value
        formatted.append(row_dict)

    return formatted



def execute_sql_via_bytebase(query: str, login_timeout: int = 10, query_timeout: int = 30, fetch_total_count: bool = True) -> Dict[str, Any]:
    """
    Execute SQL query via Bytebase API.

    Args:
        query (str): SQL statement to execute
        login_timeout (int): Login request timeout in seconds (default 10)
        query_timeout (int): SQL query request timeout in seconds (default 30)
        fetch_total_count (bool, optional): 
            If True, executes an additional COUNT(*) query to retrieve the total number of rows.
            If False, the count is equal to the number of rows returned (≤ limit).

    Returns:
        count (int): number of rows returned
        data (List[Dict]): list of row dictionaries
        status (str): 'success' or 'error'
        error (str): error message if any
    """
    config = BYTEBASE_CONFIG
    domain = config["domain"]

    # Login to get token
    login_url = f"{domain}/v1/auth/login"
    login_payload = {
        "email": config["email"],
        "password": config["password"],
        "web": False
    }

    try:
        login_response = requests.post(login_url, json=login_payload, timeout=login_timeout, verify=False)
        login_response.raise_for_status()
        login_data = login_response.json()
        token = login_data.get("token")

        if not token:
            return {
                "count": 0,
                "data": [],
                "status": "error",
                "error": "Failed to get token from Bytebase login"
            }
    except Exception as e:
        return {
            "count": 0,
            "data": [],
            "status": "error",
            "error": f"Login failed: {str(e)}"
        }

    # Execute query
    query_url = f"{domain}/v1/instances/{config['instance']}/databases/{config['database']}:query"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    query_payload = {
        "statement": query,
        "limit": config["limit"],
        "dataSourceId": config["data_source_id"],
        "explain": False,
        "schema": None,
        "queryOption": {
            "redisRunCommandsOn": None,
            "mssqlExplainFormat": None
        },
        "container": None
    }

    try:
        query_response = requests.post(query_url, json=query_payload, headers=headers, timeout=query_timeout, verify=False)
        query_response.raise_for_status()
        query_data = query_response.json()

        # Parse results
        if not query_data.get("results"):
            return {
                "count": 0,
                "data": [],
                "status": "error",
                "error": "No results returned from Bytebase"
            }

        result = query_data["results"][0]

        # Check for error in result
        if "error" in result:
            return {
                "count": 0,
                "data": [],
                "status": "error",
                "error": result.get("error", "Unknown error")
            }

        # Parse successful result
        formatted_data = _parse_rows(result)
        rows_count = result.get("rowsCount")
        count = int(rows_count) if rows_count else len(formatted_data)

        if fetch_total_count:
            count_query = _build_count_query(query)
            count_payload = {
                "statement": count_query,
                "dataSourceId": config["data_source_id"],
                "explain": False,
                "schema": None,
                "queryOption": {
                    "redisRunCommandsOn": None,
                    "mssqlExplainFormat": None
                },
                "container": None
            }

            try:
                count_response = requests.post(query_url, json=count_payload, headers=headers, timeout=query_timeout, verify=False)
                count_response.raise_for_status()
                count_data = count_response.json()
                count_results = count_data.get("results", [])

                if count_results and "error" not in count_results[0]:
                    count_rows = _parse_rows(count_results[0])

                    if count_rows:
                        raw = count_rows[0].get("TOTAL_COUNT", count)
                        count = int(raw) if raw is not None else count

            except Exception as e:
                error_text = None
                status_code = None

                if count_response is not None:
                    try:
                        error_text = count_response.text
                        status_code = count_response.status_code
                    except Exception:
                        pass
                logger.warning(
                    "Count query failed",
                    extra={
                        "error": str(e),
                        "status_code": status_code,
                        "response_text": error_text,
                        "count_query": count_query,
                    }
                )

        return {
            "count": count,
            "data": formatted_data,
            "status": "success",
            "error": None
        }

    except requests.exceptions.RequestException as e:
        return {
            "count": 0,
            "data": [],
            "status": "error",
            "error": f"Query execution failed: {str(e)}"
        }
    except Exception as e:
        return {
            "count": 0,
            "data": [],
            "status": "error",
            "error": f"Unexpected error: {str(e)}"
        }


def execute_sql_with_custom_limit(query: str, limit: int = 1000, login_timeout: int = 10, query_timeout: int = 30) -> Dict[str, Any]:
    """
    Execute SQL query via Bytebase API with custom limit.

    Args:
        query (str): SQL statement to execute
        limit (int): Row limit for the query (default 1000 for export)
        login_timeout (int): Login request timeout in seconds (default 10)
        query_timeout (int): SQL query request timeout in seconds (default 30)

    Returns:
        count (int): number of rows returned
        data (List[Dict]): list of row dictionaries
        status (str): 'success' or 'error'
        error (str): error message if any
    """
    config = BYTEBASE_CONFIG
    domain = config["domain"]

    # Login to get token
    login_url = f"{domain}/v1/auth/login"
    login_payload = {
        "email": config["email"],
        "password": config["password"],
        "web": False
    }

    try:
        login_response = requests.post(login_url, json=login_payload, timeout=login_timeout, verify=False)
        login_response.raise_for_status()
        login_data = login_response.json()
        token = login_data.get("token")

        if not token:
            return {
                "count": 0,
                "data": [],
                "status": "error",
                "error": "Failed to get token from Bytebase login"
            }
    except Exception as e:
        return {
            "count": 0,
            "data": [],
            "status": "error",
            "error": f"Login failed: {str(e)}"
        }

    # Execute query with custom limit
    query_url = f"{domain}/v1/instances/{config['instance']}/databases/{config['database']}:query"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    query_payload = {
        "statement": query,
        "limit": limit,  # Use custom limit
        "dataSourceId": config["data_source_id"],
        "explain": False,
        "schema": None,
        "queryOption": {
            "redisRunCommandsOn": None,
            "mssqlExplainFormat": None
        },
        "container": None
    }

    try:
        query_response = requests.post(query_url, json=query_payload, headers=headers, timeout=query_timeout, verify=False)
        query_response.raise_for_status()
        query_data = query_response.json()

        if not query_data.get("results"):
            return {
                "count": 0,
                "data": [],
                "status": "error",
                "error": "No results returned from Bytebase"
            }

        result = query_data["results"][0]

        if "error" in result:
            return {
                "count": 0,
                "data": [],
                "status": "error",
                "error": result.get("error", "Unknown error")
            }

        formatted_data = _parse_rows(result)

        rows_count = result.get("rowsCount")
        count = int(rows_count) if rows_count else len(formatted_data)

        return {
            "count": count,
            "data": formatted_data,
            "status": "success",
            "error": None
        }

    except requests.exceptions.RequestException as e:
        return {
            "count": 0,
            "data": [],
            "status": "error",
            "error": f"Query execution failed: {str(e)}"
        }
    except Exception as e:
        return {
            "count": 0,
            "data": [],
            "status": "error",
            "error": f"Unexpected error: {str(e)}"
        }
