from typing import Dict, Iterable, Set, List
import time
import os
import platform
import re
import sys
import asyncio
import ast

from beegen_v1.loggings import LOGGER
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
from datetime import datetime
import uuid


def fake_chunk_from(
    content: str,
    model: str,
    chat_id: str = str(uuid.uuid4()),
    current_time: int = int(datetime.now().timestamp()),
    last=False,
    **kwargs
) -> ChatCompletionChunk:
    params = {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": current_time,
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {
                    "content": content
                },
                "logprobs": None,
                "finish_reason": None
            }
        ]
    }
    
    if last:
        if 'choices' in params:
            for choice in params['choices']:
                if "delta" in choice:
                    choice["delta"]["content"] = ""
                
                choice["logprobs"] = None
                choice["finish_reason"] = "stop"
                choice["stop_reason"] = None
    params.update(**kwargs)
    return ChatCompletionChunk(**params)


def to_pascal(snake: str) -> str:
    """Convert a snake_case string to PascalCase.

    Args:
        snake (str): The snake_case string to be converted.

    Returns:
        str: The converted PascalCase string.
    """
    # Check if the string is already in PascalCase
    if re.match(r'^[A-Z][a-zA-Z0-9]*([A-Z][a-zA-Z0-9]*)*$', snake):
        return snake
    # Remove leading and trailing underscores
    snake = snake.strip('_')
    # Replace multiple underscores with a single one
    snake = re.sub('_+', '_', snake)
    # Convert to PascalCase
    return re.sub(
        '_([0-9A-Za-z])',
        lambda m: m.group(1).upper(),
        snake.title(),
    )
    
def configure_event_loop() -> None:
    """Configure the event loop policy based on the operating system.
    
    Raises:
        RuntimeError: If the platform is not supported.
    """
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    elif sys.platform.startswith(("linux", "darwin")):
        asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
    else:
        raise_error(RuntimeError(f"Unsupported platform: {sys.platform}"))
    

def raise_error(e: Exception):
   """
   Logs and raises the provided exception.
   
   Args:
       e (Exception): Exception to be logged and raised
       
   Raises:
       The provided exception
   """
   LOGGER.error(f"Error occurred: {str(e)}", exc_info=True)
   raise e


def get_system_information():
    r"""Gathers information about the operating system.

    Returns:
        dict: A dictionary containing various pieces of OS information.
    """
    sys_info = {
        "OS Name": os.name,
        "System": platform.system(),
        "Release": platform.release(),
        "Version": platform.version(),
        "Machine": platform.machine(),
        "Processor": platform.processor(),
        "Platform": platform.platform(),
    }

    return sys_info


def vars_of_prompt(template: str) -> Set[str]:
    r"""Given a string template containing curly braces {}, return a set of
    the words inside the braces.

    Args:
        template (str): A string containing curly braces.

    Returns:
        List[str]: A list of the words inside the curly braces.

    Example:
        >>> get_prompt_template_key_words('Hi, {name}! How are you {status}?')
        {'name', 'status'}
    """
    return set(re.findall(r'{([^}]*)}', template))


def join_dicts(
    source_data: List[Dict], 
    lookup_data: List[Dict], 
    join_key: str = 'id'
) -> List[Dict]:
   """Join two lists of dictionaries based on a common key, similar to LEFT JOIN in SQL.
   
   Args:
       source_data (List[dict]): Primary data list that will be enriched
       lookup_data (List[dict]): Secondary data list used for enrichment
       join_key (str): Key used to match records between the two lists. Defaults to 'id'
       
   Returns:
       List[dict]: Merged records from both lists, maintaining source_data order and keeping all 
                  source_data records even if no match exists in lookup_data
   
   Example:
       >>> content_data = [{'id': '123', 'text': 'abc'}] 
       >>> metadata = [{'id': '123', 'score': 0.9}]
       >>> join_dicts(content_data, metadata)
       [{'id': '123', 'text': 'abc', 'score': 0.9}]
   """
   lookup_map = {item[join_key]: item for item in lookup_data}
   
   merged_data = []
   for source_item in lookup_data:
       result = source_item.copy()
       if source_item[join_key] in lookup_map:
           result.update(lookup_map[source_item[join_key]])
       merged_data.append(result)
   
   return merged_data


def extract_condition_variables(expression: str) -> Dict[str, str]:
    """
    Extract variable names and infer their types based on comparisons.
    Returns a dictionary {variable_name: inferred_type}.
    """
    class VariableVisitor(ast.NodeVisitor):
        def __init__(self):
            self.variables = {}
            self.function_names = set()

        def visit_Compare(self, node: ast.Compare):
            if isinstance(node.left, ast.Name) and isinstance(node.comparators[0], ast.Constant):
                value = node.comparators[0].value
                inferred_type = type(value).__name__
                if inferred_type == "NoneType":
                    inferred_type = "Any"
                self.variables[node.left.id] = inferred_type
            self.generic_visit(node)

        def visit_Call(self, node: ast.Call):
            # Track function names to avoid treating them as variables
            if isinstance(node.func, ast.Name):
                self.function_names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                # Handle method calls like obj.method()
                pass
            
            # Visit arguments and keywords to find variables within function calls
            for arg in node.args:
                self.visit(arg)
            for keyword in node.keywords:
                self.visit(keyword.value)

        def visit_Name(self, node: ast.Name):
            # Only capture names that are being loaded (used as values)
            # and are not function names
            if (isinstance(node.ctx, ast.Load) and 
                node.id not in self.variables and 
                node.id not in self.function_names):
                self.variables[node.id] = "Any"

    visitor = VariableVisitor()
    tree = ast.parse(expression, mode="eval")
    visitor.visit(tree)
    return visitor.variables


def transform_bot_id(bot_id: str) -> str:
    return f"bot_{bot_id.replace('-', '_')}"


if __name__ == "__main__":
    print(extract_condition_variables("a == 1 and sum(b) > 0"))