import ast
import re
from typing import Optional, Dict, List, Any, Set


class DocstringParseError(Exception):
    """Exception raised when docstring parsing fails."""
    pass


class FuncParser:
    """
    Class for parsing Python function definitions, extracting information about
    parameters, return types, and function call relationships.
    """
    
    class _NodeVisitor(ast.NodeVisitor):
        """Inner class to handle AST traversal"""
        
        def __init__(self):
            self.functions = []  # Track functions in order of appearance
            self.calls = {}      # Map functions to their calls
            self.params = {}     # Store parameters for each function
            self.returns = {}    # Store return types from docstrings
            self.current_func = None

        def visit_FunctionDef(self, node: ast.FunctionDef):
            func_name = node.name
            self.functions.append(func_name)
            self.current_func = func_name
            self.calls[func_name] = set()
            
            # Extract parameters with their type annotations
            self.params[func_name] = {
                arg.arg: ast.unparse(arg.annotation) if arg.annotation else 'Any'
                for arg in node.args.args
            }
            
            # Parse docstring for return information
            docstring = ast.get_docstring(node)
            if docstring:
                returns_section = re.search(r"Returns:([\s\S]*?)(?:Args:|$)", docstring)
                if returns_section:
                    return_text = returns_section.group(1).strip()
                    parsed_returns = dict(re.findall(r'(\w+):\s*(\S+)', return_text))
                    if not parsed_returns:
                        raise DocstringParseError(f"Function '{func_name}' has a Returns section but no parsable return types")
                    self.returns[func_name] = parsed_returns
                else:
                    raise DocstringParseError(f"Function '{func_name}' is missing 'Returns:' section in docstring")
            else:
                raise DocstringParseError(f"Function '{func_name}' is missing docstring")

            self.generic_visit(node)
            self.current_func = None

        def visit_Call(self, node: ast.Call):
            if isinstance(node.func, ast.Name) and self.current_func:
                self.calls[self.current_func].add(node.func.id)
            self.generic_visit(node)
    
    def __init__(self):
        self._visitor = None
        self._parsed = False
    
    def parse(self, code_str: str) -> None:
        """
        Parse the provided Python code string and extract function information.
        
        Args:
            code_str: Python code as a string
            
        Raises:
            SyntaxError: If the code cannot be parsed
            DocstringParseError: If docstring parsing fails
        """
        tree = ast.parse(code_str)
        self._visitor = self._NodeVisitor()
        self._visitor.visit(tree)
        self._parsed = True
        
        import ast
import re
from typing import Optional, Dict, List, Any, Set


class DocstringParseError(Exception):
    """Exception raised when docstring parsing fails."""
    pass


class FuncParser:
    """
    Class for parsing Python function definitions, extracting information about
    parameters, return types, and function call relationships.
    """
    
    class _NodeVisitor(ast.NodeVisitor):
        """Inner class to handle AST traversal"""
        
        def __init__(self):
            self.functions = []  # Track functions in order of appearance
            self.calls = {}      # Map functions to their calls
            self.params = {}     # Store parameters for each function
            self.returns = {}    # Store return types from docstrings
            self.current_func = None

        def visit_FunctionDef(self, node: ast.FunctionDef):
            func_name = node.name
            self.functions.append(func_name)
            self.current_func = func_name
            self.calls[func_name] = set()
            
            # Extract parameters with their type annotations
            self.params[func_name] = {
                arg.arg: ast.unparse(arg.annotation) if arg.annotation else 'Any'
                for arg in node.args.args
            }
            
            # Parse docstring for return information
            docstring = ast.get_docstring(node)
            if docstring:
                returns_section = re.search(r"Returns:([\s\S]*?)(?:Args:|$)", docstring)
                if returns_section:
                    return_text = returns_section.group(1).strip()
                    parsed_returns = dict(re.findall(r'(\w+):\s*(\S+)', return_text))
                    if not parsed_returns:
                        raise DocstringParseError(f"Function '{func_name}' has a Returns section but no parsable return types")
                    self.returns[func_name] = parsed_returns
                else:
                    raise DocstringParseError(f"Function '{func_name}' is missing 'Returns:' section in docstring")
            else:
                raise DocstringParseError(f"Function '{func_name}' is missing docstring")

            self.generic_visit(node)
            self.current_func = None

        def visit_Call(self, node: ast.Call):
            if isinstance(node.func, ast.Name) and self.current_func:
                self.calls[self.current_func].add(node.func.id)
            self.generic_visit(node)
    
    def __init__(self):
        self._visitor = None
        self._parsed = False
    
    def parse(self, code_str: str) -> Dict[str, Any]:
        """
        Parse the provided Python code string and extract the main function information.
        
        Args:
            code_str: Python code as a string
            
        Returns:
            Dict with name, inputs, and outputs of the main (entry point) function
            
        Raises:
            SyntaxError: If the code cannot be parsed
            DocstringParseError: If docstring parsing fails
        """
        tree = ast.parse(code_str)
        self._visitor = self._NodeVisitor()
        self._visitor.visit(tree)
        self._parsed = True
        
        # Find the entry point (main) function
        all_called = set()
        for calls in self._visitor.calls.values():
            all_called.update(calls)
            
        # Return the first function that's not called by others
        for func in self._visitor.functions:
            if func not in all_called:
                return {
                    'name': func,
                    'inputs': self._visitor.params.get(func, {}),
                    'outputs': self._visitor.returns.get(func, {})
                }
                
        # If no clear entry point, return the first function
        if self._visitor.functions:
            func = self._visitor.functions[0]
            return {
                'name': func,
                'inputs': self._visitor.params.get(func, {}),
                'outputs': self._visitor.returns.get(func, {})
            }
            
        return {}
    
    def _ensure_parsed(self) -> None:
        """Ensure code has been parsed before accessing data"""
        if not self._parsed:
            raise RuntimeError("No code has been parsed. Call parse() first.")
    
    def get_functions(self) -> List[str]:
        """Get list of function names in order of appearance"""
        self._ensure_parsed()
        return self._visitor.functions
    
    def get_params(self, func_name: Optional[str] = None) -> Dict:
        """
        Get parameters for a specific function or all functions
        
        Args:
            func_name: Optional function name to get params for
            
        Returns:
            Dict of parameter information
        """
        self._ensure_parsed()
        if func_name:
            return self._visitor.params.get(func_name, {})
        return self._visitor.params
    
    def get_returns(self, func_name: Optional[str] = None) -> Dict:
        """
        Get return types for a specific function or all functions
        
        Args:
            func_name: Optional function name to get return types for
            
        Returns:
            Dict of return type information
        """
        self._ensure_parsed()
        if func_name:
            return self._visitor.returns.get(func_name, {})
        return self._visitor.returns
    
    def get_calls(self, func_name: Optional[str] = None) -> Dict[str, Set[str]]:
        """
        Get function calls made by a specific function or all functions
        
        Args:
            func_name: Optional function name to get calls for
            
        Returns:
            Dict mapping functions to sets of called functions
        """
        self._ensure_parsed()
        if func_name:
            return {func_name: self._visitor.calls.get(func_name, set())}
        return self._visitor.calls
    
    def find_entry_point(self) -> Optional[Dict[str, Any]]:
        """
        Identifies the entry point function in code (one that is defined but never called by other functions).
        
        Returns:
            Dictionary with the entry point function's name, inputs, and outputs, or None if not found
        """
        self._ensure_parsed()
        
        # Collect all called functions
        all_called = set()
        for calls in self._visitor.calls.values():
            all_called.update(calls)

        # Find the first defined function that is never called
        for func in self._visitor.functions:
            if func not in all_called:
                return {
                    'name': func,
                    'inputs': self._visitor.params.get(func, {}),
                    'outputs': self._visitor.returns.get(func, {})
                }

        return None


# Example usage
if __name__ == "__main__":
    def sum_prices(products: List[Dict]) -> float:
        """
        Calculate the sum of all product prices.
        
        Args:
            products: List of product dictionaries with price information
            
        Returns:
            total: float
        """
        total = sum(product.get('price', 0) for product in products)
        return total

    def calculate_average(total: float, count: int) -> float:
        """
        Calculate the average price from total and count.
        
        Args:
            total: Sum of all prices
            count: Number of products
            
        Returns:
            average: float
        """
        average = total / count if count else 0
        return average

    def calculate_metrics(products: List[Dict]) -> Dict[str, Any]:
        """
        Calculate various metrics from a list of product dictionaries.
        
        Args:
            products: List of product dictionaries with price information
            
        Returns:
            total_price: float
            avg_price: float
            product_count: int
        """
        total_price = sum_prices(products)
        product_count = len(products)
        avg_price = calculate_average(total_price, product_count)
        
        return {
            'total_price': total_price,
            'avg_price': avg_price,
            'product_count': product_count
        }
    
    from beegenerate.utils.code_parser import FuncExporter
    
    code_str = FuncExporter().export(calculate_metrics)
    print("Original code:")
    print(code_str)
    print("\n")
    
    parser = FuncParser()
    result = parser.parse(code_str)
        
    print(result)