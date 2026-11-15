from typing import Any, Dict, Iterable, Set, List, Callable
import os
import platform
import re
import sys
import asyncio
import ast
import decimal

from beegen.loggings import LOGGER
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
from datetime import datetime, date, time
import uuid
from haikunator import Haikunator


h = Haikunator()

def unique_name():
    return h.haikunate()


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
                # It's a method call like `var.method()`. We need to visit `var`.
                self.visit(node.func.value)
            
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


def ensure_async(func: Callable) -> Callable:
    """
    Ensure the function is async. If it's synchronous, wrap it in an async function.
    
    Args:
        func: The function to make async
        
    Returns:
        An async function
    """
    if asyncio.iscoroutinefunction(func):
        # Already async, return as is
        return func
    else:
        # Handle regular synchronous functions
        async def async_wrapper(*args, **kwargs):
            # Run the sync function in a thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, lambda: func(*args, **kwargs))
        return async_wrapper
    

def verify_data(value: Any) -> None:
    """
    Kiểm tra xem value có thích hợp để làm giá trị trong workflow không?
    
    Basic types: int, float, str, bool, None, datetime, date, time
    Collections: dict, list, tuple, set, frozenset
    Special: numpy.ndarray và numpy scalar types (np.int64, np.float32, etc.)
    
    Args:
        value: Giá trị cần kiểm tra
    
    Raises:
        TypeError: Nếu value không phải là kiểu dữ liệu hợp lệ
    """
    # Check None first
    if value is None:
        return
    
    basic_types = (int, float, str, bool, datetime, date, time, bytes, decimal.Decimal)
    
    if isinstance(value, basic_types):
        return
    
    # Kiểm tra numpy types (ndarray và scalar types)
    value_type = type(value)
    if hasattr(value_type, '__module__') and value_type.__module__.startswith('numpy'):
        return
    
    # Kiểm tra dict
    if isinstance(value, dict):
        for k, v in value.items():
            verify_data(k)
            verify_data(v)
        return
    
    # Kiểm tra list/tuple/set/frozenset
    if isinstance(value, (list, tuple, set, frozenset)):
        for idx, item in enumerate(value):
            verify_data(item)
        return
    
    # Nếu đến đây nghĩa là invalid type
    raise TypeError(
        f"Kiểu dữ liệu không hợp lệ tại {type(value).__name__}. "
        f"Các kiểu được phép: int, float, str, bool, None, datetime, date, time, "
        f"dict, list, tuple, set, frozenset, numpy types"
    )


def main():
    """Test all cases for verify_data"""
    
    print("=" * 60)
    print("Testing verify_data()")
    print("=" * 60)
    
    # Test basic types (should pass)
    print("\n✅ Basic types (should all pass):")
    test_cases_valid = [
        (42, "int"),
        (3.14, "float"),
        ("hello", "str"),
        (True, "bool"),
        (False, "bool"),
        (None, "None"),
    ]
    
    for value, name in test_cases_valid:
        verify_data(value)
        print(f"  {name:15} {repr(value):20} -> ✅ Pass")
    
    # Test datetime types (should pass)
    print("\n✅ Datetime types (should all pass):")
    datetime_cases = [
        (datetime.now(), "datetime"),
        (date.today(), "date"),
        (time(12, 30, 45), "time"),
    ]
    
    for value, name in datetime_cases:
        verify_data(value)
        print(f"  {name:15} {repr(value)[:30]:30} -> ✅ Pass")
    
    # Test collections (should pass)
    print("\n✅ Collections (should all pass):")
    collection_cases = [
        ([1, 2, 3], "list"),
        ((1, 2, 3), "tuple"),
        ({1, 2, 3}, "set"),
        (frozenset([1, 2, 3]), "frozenset"),
        ({"key": "value"}, "dict"),
        ([], "empty list"),
        ({}, "empty dict"),
    ]
    
    for value, name in collection_cases:
        verify_data(value)
        print(f"  {name:15} {repr(value)[:30]:30} -> ✅ Pass")
    
    # Test nested collections (should pass)
    print("\n✅ Nested collections (should all pass):")
    nested_cases = [
        ({"users": [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]}, "nested dict/list"),
        ([1, [2, [3, [4]]]], "deeply nested list"),
        ({"a": {"b": {"c": "deep"}}}, "deeply nested dict"),
        ({"data": [1, 2, 3], "meta": {"count": 3}}, "mixed nested"),
        ([{1, 2}, {3, 4}], "list of sets"),
    ]
    
    for value, name in nested_cases:
        verify_data(value)
        print(f"  {name:20} -> ✅ Pass")
    
    # Test numpy (if available)
    print("\n✅ NumPy types (if numpy installed):")
    try:
        import numpy as np
        
        numpy_cases = [
            (np.array([1, 2, 3]), "np.ndarray"),
            (np.int64(42), "np.int64"),
            (np.float32(3.14), "np.float32"),
            (np.array([[1, 2], [3, 4]]), "np.ndarray 2D"),
        ]
        
        for value, name in numpy_cases:
            verify_data(value)
            print(f"  {name:20} -> ✅ Pass")
            
    except ImportError:
        print("  NumPy not installed - skipping numpy tests")
    
    # Test invalid cases (should raise TypeError)
    print("\n❌ Invalid types (should all raise TypeError):")
    
    class CustomClass:
        pass
    
    class AnotherClass:
        def __init__(self):
            self.value = 42
    
    invalid_cases = [
        (CustomClass(), "custom class instance"),
        (AnotherClass(), "another class instance"),
        (lambda x: x, "lambda function"),
        (print, "built-in function"),
        ({"key": CustomClass()}, "dict with custom class"),
        ([1, 2, CustomClass()], "list with custom class"),
        ({CustomClass: "value"}, "dict with class as key"),
    ]
    
    for value, name in invalid_cases:
        try:
            verify_data(value)
            print(f"  {name:30} -> ❌ FAILED: Should have raised TypeError!")
            raise AssertionError(f"Expected TypeError for {name}")
        except TypeError as e:
            print(f"  {name:30} -> ✅ Raised: {str(e)}...")
    
    print("\n" + "=" * 60)
    print("✅ All tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    main()