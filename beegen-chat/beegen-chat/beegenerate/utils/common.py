from typing import Dict, Iterable, Set, List
import time
import os
import platform
import re
import sys
import asyncio
import ast

from beegenerate.loggings import LOGGER


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


def get_prompt_template_key_words(template: str) -> Set[str]:
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
   for source_item in source_data:
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

        def visit_Compare(self, node: ast.Compare):
            if isinstance(node.left, ast.Name) and isinstance(node.comparators[0], ast.Constant):
                value = node.comparators[0].value
                inferred_type = type(value).__name__
                self.variables[node.left.id] = inferred_type
            self.generic_visit(node)

        def visit_Name(self, node: ast.Name):
            if node.id not in self.variables:
                self.variables[node.id] = "Any"

    visitor = VariableVisitor()
    tree = ast.parse(expression, mode="eval")
    visitor.visit(tree)
    return visitor.variables


def transform_bot_id(bot_id: str) -> str:
    return bot_id.replace('-', '_')


if __name__ == "__main__":
    # Data containing content
    content_data = [
        {
            'id': 'd49189f1-834b-4d0d-911e-c5a1593b3596',
            'doc': 'd49189f1-834b-4d0d-911e-c5a1593b3596',
            'content': '...'
        }
    ]

    # Data containing metadata/scores
    metadata = [
        {
            'id': 'd49189f1-834b-4d0d-911e-c5a1593b3596',
            'score': 0.7369304895401001,
            'role': '11',
            'topic': 'QA'
        }
    ]

    merged = join_dicts(content_data, metadata)
    
    import json
    
    print(json.dumps(merged, indent=2, ensure_ascii=False))