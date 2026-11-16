import os
import ast
import inspect
from typing import Dict, List, Optional

class DocGenerator:
    def __init__(self, project_path: str):
        self.project_path = project_path
        self.markdown_content = []

    def generate_docs(self) -> str:
        """
        Main method to generate documentation for the entire project.
        Returns the complete markdown string.
        """
        self.markdown_content = []
        self._add_header("Project Documentation", 1)
        
        for root, dirs, files in os.walk(self.project_path):
            # Skip __pycache__ and virtual environment directories
            dirs[:] = [d for d in dirs if not d.startswith(('__', '.'))]
            
            # Process Python files
            for file in files:
                if file.endswith('.py'):
                    file_path = os.path.join(root, file)
                    relative_path = os.path.relpath(file_path, self.project_path)
                    
                    self._add_header(f"Module: {relative_path}", 2)
                    self._process_file(file_path)
                    self.markdown_content.append("")  # Add spacing between modules

        return "\n".join(self.markdown_content)

    def _process_file(self, file_path: str) -> None:
        """
        Process a single Python file and extract its documentation.
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()
            
            module = ast.parse(content)
            
            # Get module docstring
            module_doc = ast.get_docstring(module)
            if module_doc:
                self.markdown_content.append(f"**Module Description:**\n{module_doc}\n")
            
            # Process all node types
            for node in module.body:
                if isinstance(node, ast.ClassDef):
                    self._process_class(node)
                elif isinstance(node, ast.FunctionDef):
                    self._process_function(node)

        except Exception as e:
            self.markdown_content.append(f"Error processing {file_path}: {str(e)}\n")

    def _process_class(self, node: ast.ClassDef) -> None:
        """
        Process a class definition and extract its documentation.
        """
        self._add_header(f"Class: {node.name}", 3)
        
        # Get class docstring
        class_doc = ast.get_docstring(node)
        if class_doc:
            self.markdown_content.append(f"**Description:**\n{class_doc}\n")
        
        # Process class methods
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                self._process_function(item, is_method=True)

    def _process_function(self, node: ast.FunctionDef, is_method: bool = False) -> None:
        """
        Process a function definition and extract its documentation.
        """
        prefix = "Method" if is_method else "Function"
        self._add_header(f"{prefix}: {node.name}", 4)
        
        # Get function docstring
        func_doc = ast.get_docstring(node)
        if func_doc:
            self.markdown_content.append(f"**Description:**\n{func_doc}\n")
        
        # Get function arguments
        args = self._get_function_args(node)
        if args:
            self.markdown_content.append("**Arguments:**\n```python")
            self.markdown_content.append(args)
            self.markdown_content.append("```\n")

    def _get_function_args(self, node: ast.FunctionDef) -> str:
        """
        Extract and format function arguments.
        """
        args = []
        
        # Process arguments
        for arg in node.args.args:
            arg_name = arg.arg
            # Get type annotation if it exists
            if arg.annotation:
                if isinstance(arg.annotation, ast.Name):
                    arg_type = arg.annotation.id
                elif isinstance(arg.annotation, ast.Subscript):
                    arg_type = self._format_type_annotation(arg.annotation)
                else:
                    arg_type = "Any"
            else:
                arg_type = "Any"
            
            args.append(f"{arg_name}: {arg_type}")
        
        # Add return type if it exists
        if node.returns:
            if isinstance(node.returns, ast.Name):
                return_type = f" -> {node.returns.id}"
            elif isinstance(node.returns, ast.Subscript):
                return_type = f" -> {self._format_type_annotation(node.returns)}"
            else:
                return_type = " -> Any"
        else:
            return_type = " -> None"
        
        return f"def {node.name}({', '.join(args)}){return_type}"

    def _format_type_annotation(self, node: ast.Subscript) -> str:
        """
        Format complex type annotations (e.g., List[str], Dict[str, int]).
        """
        if isinstance(node.value, ast.Name):
            base = node.value.id
            if isinstance(node.slice, ast.Index):
                if isinstance(node.slice.value, ast.Name):
                    return f"{base}[{node.slice.value.id}]"
            return f"{base}[Any]"
        return "Any"

    def _add_header(self, text: str, level: int) -> None:
        """
        Add a markdown header of specified level.
        """
        self.markdown_content.append(f"{'#' * level} {text}\n")

def generate_project_docs(project_path: str, output_file: str = "project_documentation.md") -> None:
    """
    Generate markdown documentation for a Python project.
    
    Args:
        project_path: Path to the Python project root directory
        output_file: Name of the output markdown file
    """
    generator = DocGenerator(project_path)
    documentation = generator.generate_docs()
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(documentation)
    
    print(f"Documentation generated successfully in {output_file}")

# Example usage:
if __name__ == "__main__":
    import sys
    
    # Use current directory as default project path
    project_path = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    output_file = "projects.md"
    
    generate_project_docs(project_path, output_file)