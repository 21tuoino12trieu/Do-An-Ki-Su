import re
from typing import Optional, Dict


class DocstringParser:
    """Service for parsing Google-style docstrings."""
    
    def parse_description(self, docstring: str) -> str:
        """Extract the main description from docstring."""
        if not docstring:
            return ""
        
        # Remove leading/trailing whitespace and normalize line breaks
        cleaned_docstring = docstring.strip()
        
        # Find the first section (Args:, Returns:, Raises:, etc.)
        section_match = re.search(r"\n\s*(Args:|Returns:|Raises:|Note:|Example:|Examples:)", 
                                cleaned_docstring, re.IGNORECASE)
        
        if section_match:
            # Extract everything before the first section
            description = cleaned_docstring[:section_match.start()]
        else:
            # No sections found, entire docstring is description
            description = cleaned_docstring
        
        # Clean up the description
        # Remove extra whitespace and normalize line breaks
        # description = re.sub(r'\n\s*\n', '\n\n', description)  # Preserve paragraph breaks
        # description = re.sub(r'\n\s+', ' ', description)       # Join continuation lines
        # description = description.strip()
        
        return description
    
    def parse_parameter_descriptions(self, docstring: str) -> Dict[str, str]:
        """Extract parameter descriptions from docstring Args section."""
        if not docstring:
            return {}
        
        descriptions = {}
        
        # Look for Args: section
        args_match = re.search(r"Args:([\s\S]*?)(?:Returns:|Raises:|$)", docstring, re.IGNORECASE)
        if not args_match:
            return descriptions
            
        args_section = args_match.group(1)
        
        # Parse parameter descriptions
        # Matches: "param_name (type): description" or "param_name: description"
        param_patterns = [
            r'(\w+)\s*\([^)]+\):\s*(.+?)(?=\n\s*\w+\s*(?:\([^)]*\))?\s*:|$)',
            r'(\w+):\s*(.+?)(?=\n\s*\w+\s*:|$)'
        ]
        
        for pattern in param_patterns:
            matches = re.findall(pattern, args_section, re.DOTALL | re.MULTILINE)
            for param_name, description in matches:
                # Clean up description
                clean_desc = ' '.join(description.strip().split())
                descriptions[param_name] = clean_desc
                
        return descriptions
    
    def parse_return_info(self, docstring: str) -> Optional[Dict[str, str]]:
        """Extract return information from docstring Returns section."""
        if not docstring:
            return None
            
        returns_section = re.search(r"Returns:([\s\S]*?)(?:Args:|Raises:|$)", docstring)
        if returns_section:
            return_text = returns_section.group(1).strip()
            # Extract return type information: "name (type): description"
            return dict(re.findall(r'(\w+)\s*\(([\w\[\],\s]+)\)', return_text))
        
        return None
    

if __name__ == "__main__":
    from typing import List, Dict, Any
    
    def helper_function(x: int) -> int:
        """A helper function."""
        return x * 2

    def complex_function(
        name: str,
        age: int = 25,
        items: List[str] = None,
        active: bool = True
    ) -> Dict[str, Any]:
        """
        Process person information and return a structured data dictionary.
        
        This function takes personal information, processes the age through a helper
        function, and returns a standardized dictionary containing all relevant
        person data with processed values.
        
        Args:
            name (str): The person's full name. Must be a non-empty string.
            age (int, optional): The person's age in years. Must be a positive
                integer. Defaults to 25 if not provided.
            items (List[str], optional): A list of items associated with the person.
                Can be None or an empty list. Defaults to None, which will be
                converted to an empty list in the output.
            active (bool, optional): Indicates whether the person is currently
                active in the system. Defaults to True.
        
        Returns:
            name (str): The original name provided
            processed_age (Any): The age after processing by helper_function
            items (List[str]): The items list or empty list if None was provided
            active (bool): The active status
        
        Example:
            >>> result = complex_function("John Doe", 30, ["item1", "item2"])
            >>> print(result['name'])
            'John Doe'
            >>> print(result['items'])
            ['item1', 'item2']
        """
        result = helper_function(age)
        return {
            'name': name,
            'processed_age': result,
            'items': items or [],
            'active': active
        }
        
    # Test the parser
    docstring_parser = DocstringParser()
    
    # Parse function description
    description = docstring_parser.parse_description(complex_function.__doc__)
    print("Function Description:")
    print(description)
    print("\n" + "="*50 + "\n")
    
    # Parse parameter descriptions
    params = docstring_parser.parse_parameter_descriptions(complex_function.__doc__)
    print("Parameter Descriptions:")
    for param, desc in params.items():
        print(f"  {param}: {desc}")
    print("\n" + "="*50 + "\n")
    
    # Parse return information
    return_info = docstring_parser.parse_return_info(complex_function.__doc__)
    print("Return Information:")
    print(return_info)