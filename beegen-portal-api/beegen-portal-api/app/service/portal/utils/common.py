from typing import Any, Dict


def convert_bot_id(bot_id: str) -> Dict[str, Any]:
    if not bot_id.startswith("bot"):
        bot_id = f"bot_{bot_id}"
    return {
        "collection_name": f"{bot_id.replace('-','_')}_chunk"
    }