import json
import re
from typing import List, Dict, Any
from typing import Dict, List, Optional
from beegen.loggings.loggers import LOGGER

async def build_table_index(metadata: list) -> str:
    lines = []
    for i, table_info in enumerate(metadata, 1):
        table_name = f"{table_info.get('schema')}.{table_info.get('table_name')}"
        description = table_info.get("description", "<no description>")
        line = f"{i}. {table_name}: {description}"
        lines.append(line)
    return "\n".join(lines)

# Hàm lấy tên bảng sử dụng regex
def extract_table_name_from_query(rewrite: str) -> Dict[str, str]:
    """Trích xuất tên bảng từ query để search."""
    import re
    # Pattern 1: "bảng ABC" hoặc "table ABC"
    match = re.search(r'(?:bảng|table)\s+["\']?([A-Za-z0-9_]+)["\']?', rewrite, re.IGNORECASE)
    if match:
        return {"table_query": match.group(1)}
    
    # Pattern 2: Lấy từ cuối cùng có dạng table name (viết hoa, có underscore)
    words = rewrite.split()
    for word in reversed(words):
        if re.match(r'^[A-Z][A-Z0-9_]*$', word):
            return {"table_query": word}
    
    # Fallback: lấy từ cuối
    return {"table_query": words[-1] if words else ""}

def parse_tool_calls_from_llm(tool_calls_json: List[Dict]) -> Dict[str, Any]:
    """Parse tool_calls từ LLM response thành format cho MCPGatewayNode."""
    try:
        if not tool_calls_json or len(tool_calls_json) == 0:
            return {
                "tool_name": None,
                "tool_params": None,
                "error": "No tool calls found"
            }
        
        first_call = tool_calls_json[0]
        tool_name = first_call.get("function", {}).get("name")
        arguments_str = first_call.get("function", {}).get("arguments", "{}")
        
        # Parse arguments string to dict
        tool_params = json.loads(arguments_str)
        
        return {
            "tool_name": tool_name,
            "tool_params": tool_params,
            "error": None
        }
    except Exception as e:
        LOGGER.error(f"Error parsing tool calls: {e}")
        return {
            "tool_name": None,
            "tool_params": None,
            "error": str(e)
        }

def extract_generated_metadata_from_history(conversation: List) -> Dict[str, Any]:
    """
    Trích xuất ONLY generated_metadata từ lịch sử hội thoại.
    Tìm message cuối cùng của assistant có chứa generated_metadata.
    
    Support 2 formats:
    - List of dicts: [{"role": "user", "content": "..."}, ...]
    - List of strings: ["USER: ...", "BOT: ...", ...]
    """
    try:
        import yaml
        
        # Chuẩn hóa conversation thành list of dicts
        normalized_conv = []
        for msg in conversation:
            if isinstance(msg, dict):
                # Already dict format
                normalized_conv.append(msg)
            elif isinstance(msg, str):
                # String format: "USER: ..." or "BOT: ..."
                if msg.startswith("user:"):
                    normalized_conv.append({"role": "user", "content": msg[5:].strip()})
                elif msg.startswith("assistant:"):
                    normalized_conv.append({"role": "assistant", "content": msg[4:].strip()})
        
        # Tìm message cuối cùng của assistant có generated_metadata
        for msg in reversed(normalized_conv):
            if msg.get("role") == "assistant":
                content = msg.get("content", "")
                
                if "generated_metadata:" in content:
                    # Extract generated_metadata block
                    # Tìm vị trí bắt đầu và kết thúc
                    start_idx = content.find("generated_metadata:")
                    if start_idx == -1:
                        continue

                    # Tìm vị trí kết thúc: "preview:" hoặc ```
                    end_idx = len(content)
                    for end_marker in ["\npreview:", "\n```"]:
                        idx = content.find(end_marker, start_idx)
                        if idx != -1:
                            end_idx = min(end_idx, idx)

                    # Extract substring bao gồm cả "generated_metadata:"
                    yaml_str = content[start_idx:end_idx].strip()
                    LOGGER.debug(f"Extracted YAML block:\n{yaml_str[:200]}...")

                    try:
                        full_parsed = yaml.safe_load(yaml_str)
                        gen_meta = full_parsed.get("generated_metadata") or full_parsed
                    except yaml.YAMLError as e:
                        LOGGER.error(f"YAML parsing failed: {e}")
                        LOGGER.error(f"YAML string to parse:\n{yaml_str}")
                        return {"generated_metadata": None, "error": f"YAML parsing failed: {e}"}

                    # Extract fields
                    table_desc = gen_meta.get("table_description")
                    col_descs = gen_meta.get("column_descriptions", {})

                    # Chỉ lấy những field không null/empty
                    result_lines = []

                    if table_desc:
                        # Escape quotes nếu có
                        escaped_desc = table_desc.replace('"', '\\"')
                        result_lines.append(f'table_description: "{escaped_desc}"')

                    # Lọc column_descriptions không null
                    valid_col_descs = {k: v for k, v in col_descs.items() if v}
                    if valid_col_descs:
                        result_lines.append("column_descriptions:")
                        for col_name, col_desc in valid_col_descs.items():
                            # Escape quotes
                            escaped_col_desc = col_desc.replace('"', '\\"')
                            result_lines.append(f'  {col_name}: "{escaped_col_desc}"')

                    metadata_yaml = "\n".join(result_lines) if result_lines else None

                    return {
                        "generated_metadata": metadata_yaml,
                        "error": None
                    }
        
        return {
            "generated_metadata": None,
            "error": "Không tìm thấy generated_metadata trong lịch sử"
        }
    
    except Exception as e:
        import traceback
        LOGGER.error(f"Error extracting generated metadata: {e}")
        LOGGER.error(traceback.format_exc())
        return {
            "generated_metadata": None,
            "error": str(e)
        }

    
def parse_format_patch_output(format_result: str) -> Dict[str, Any]:
    """Parse output từ LLM format_patch thành tool params."""
    try:
        # Remove markdown code blocks nếu có
        import re
        json_match = re.search(r'```json\n(.*?)\n```', format_result, re.DOTALL)
        if json_match:
            format_result = json_match.group(1)
        
        patch_data = json.loads(format_result)
        
        return {
            "tool_name": "patch_entity",
            "tool_params": {
                "entityType": patch_data["entityType"],
                "entityFqn": patch_data["entityFqn"],
                "patch": json.dumps(patch_data["patch"], ensure_ascii=False)
            }
        }
    except Exception as e:
        LOGGER.error(f"Error parsing format patch output: {e}")
        return {
            "tool_name": None,
            "tool_params": None,
            "error": str(e)
        }
    
def extract_table_name_from_conversation(conv: List[str]) -> Dict[str, str]:
    """
    Trích xuất tên bảng từ user message yêu cầu sinh metadata
    """
    table_name = ""

    if conv and isinstance(conv, list):
        for msg in reversed(conv):
            if not isinstance(msg, str):
                continue

            if not msg.strip().startswith("user:"):
                continue

            text = msg[len("user:"):].strip().lower()

            if any(kw in text for kw in ["sinh", "tạo", "generate", "metadata"]):
                match = re.search(
                    r"bảng\s+([a-zA-Z0-9_\.]+)",
                    msg,
                    re.IGNORECASE
                )
                if match:
                    table_name = match.group(1)
                    break

    return {
        "table_query": table_name
    }

def build_search_params_for_generation(table_query: str) -> Dict[str, Any]:
    """Tạo params để search bảng với columns cho generate flow."""
    return {
        "tool_name": "search_metadata",
        "tool_params": {
            "query": table_query,
            "entity_type": "table",
            "fields": "columns",
            "limit": 1
        }
    }


# Node để lấy sample data của bảng
def fetch_sample_data(fqn: str) -> Dict[str, Any]:
    """Lấy sample data từ API dựa trên FQN của bảng"""
    try:
        import requests
        from beegen.registry.resource_hub import ResourceHub

        server = ResourceHub.self().mcp("mcp:openmetadata")
        token = server.opts.auth_token
        base_url = "https://ai-platform-open-metadata.tanzu-dev.mbbank.com.vn"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        }

        # Bước 1: Lấy table_id từ FQN
        url_by_name = f"{base_url}/api/v1/tables/name/{fqn}"
        resp_by_name = requests.get(url_by_name, headers=headers, verify=False)

        if resp_by_name.status_code != 200:
            return {"sample_data": None, "error": f"Không thể lấy table_id: {resp_by_name.status_code}"}

        table = resp_by_name.json()
        table_id = table.get("id")

        if not table_id:
            return {"sample_data": None, "error": "Không tìm thấy table_id trong response"}

        # Bước 2: Lấy sample data từ table_id
        url_sample = f"{base_url}/api/v1/tables/{table_id}/sampleData"
        resp_sample = requests.get(url_sample, headers=headers, verify=False)

        if resp_sample.status_code != 200:
            return {"sample_data": None, "error": f"Không thể lấy sample data: {resp_sample.status_code}"}

        sample_data = resp_sample.json()

        # Trích xuất chỉ phần sampleData cần thiết
        extracted_sample = {
            "columns": sample_data.get("columns", []),
            "rows": sample_data.get("sampleData", {}).get("rows", []) if sample_data.get("sampleData") else [],
            "rows_count": len(sample_data.get("sampleData", {}).get("rows", [])) if sample_data.get("sampleData") else 0
        }

        return {"sample_data": json.dumps(extracted_sample, ensure_ascii=False, indent=2), "error": None}

    except Exception as e:
        return {"sample_data": None, "error": f"Lỗi khi lấy sample data: {str(e)}"}