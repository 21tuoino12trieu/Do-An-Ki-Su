import ast
from typing import Dict, Any, Optional

def extract_return_types(func_code: str) -> Dict[str, str]:
    """
    Extract output parameter names and types based on the return dictionary in a function.
    
    Args:
        func_code: String containing the function code
        
    Returns:
        Dictionary mapping parameter names to their inferred types
    """
    tree = ast.parse(func_code)
    
    # Find the return statement in the function
    return_visitor = ReturnStatementVisitor()
    return_visitor.visit(tree)
    
    if not return_visitor.return_dict:
        return {}
    
    # Now analyze the return dictionary
    return_dict = return_visitor.return_dict
    
    # Extract variable names referenced in the return dict
    output_types = {}
    for key, value_node in return_dict.items():
        # Get the key name (must be a string literal)
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            param_name = key.value
            # Infer the type from the value expression
            param_type = infer_type_from_node(value_node)
            output_types[param_name] = param_type
    
    return output_types


class ReturnStatementVisitor(ast.NodeVisitor):
    """Visitor to find the return statement with a dictionary literal"""
    
    def __init__(self):
        self.return_dict = None  # Will store key-value pairs from the return dict
    
    def visit_Return(self, node):
        # Check if returning a dictionary literal
        if isinstance(node.value, ast.Dict):
            # Store the key-value pairs
            self.return_dict = dict(zip(node.value.keys, node.value.values))
        self.generic_visit(node)


def infer_type_from_node(node: ast.AST) -> str:
    """
    Infer the type of a node in the AST.
    
    Args:
        node: An AST node representing a value
        
    Returns:
        A string representation of the inferred type
    """
    if isinstance(node, ast.Constant):
        # For literals, use their Python type
        return type(node.value).__name__
    
    elif isinstance(node, ast.Name):
        # For variables, we can try to track their previous assignments
        # For simplicity, we'll use a basic approach
        if node.id in ['True', 'False']:
            return 'bool'
        return 'Any'  # Default to Any for variables
    
    elif isinstance(node, ast.Call):
        # For function calls, try to infer based on common functions
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            if func_name == 'len':
                return 'int'
            elif func_name in ['sum', 'min', 'max']:
                return 'float'  # Assuming numeric operations
        return 'Any'
    
    elif isinstance(node, ast.BinOp):
        # For binary operations like division
        if isinstance(node.op, ast.Div):
            return 'float'
        return 'Any'
    
    # Add more cases as needed
    return 'Any'  # Default fallback


# Example usage
if __name__ == "__main__":
    example_function = """
def calculate_metrics(products: List[Dict]) -> Dict[str, Any]:
    total_price = sum(product.get('price', 0) for product in products)
    avg_price = total_price / len(products) if products else 0        

    return {
        'total_price': total_price,
        'avg_price': avg_price,
        'product_count': len(products)
    }
"""
    output_types = extract_return_types(example_function)
    print("Extracted output types:")
    for param, type_info in output_types.items():
        print(f"- {param}: {type_info}")