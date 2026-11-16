import ast
from typing import Dict

def extract_variables(expression: str) -> Dict[str, str]:
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

# Example usage
conditions = {
    "a <= 1 and b >= 2": "Node1",
    "x == 'test' or y > 5": "Node2",
    "c != 3.5": "Node3",
    "is_active == True": "Node4",
    "threshold < 0.7": "Node5"
}

for cond, target in conditions.items():
    params = extract_variables(cond)
    print(f"Condition: {cond}")
    print(f"Extracted Params: {params}\n")
