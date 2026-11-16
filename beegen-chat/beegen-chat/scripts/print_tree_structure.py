import os
from beegenerate.const import BEEGEN_ROOT

def print_tree(directory, prefix=""):
    # List of directories to exclude
    exclude_dirs = {'.git', 'system-logs'}
    
    try:
        entries = os.listdir(directory)
        # Filter out excluded directories and __pycache__
        entries = [e for e in entries if e not in exclude_dirs and '__pycache__' not in e]
        
        for i, entry in enumerate(entries):
            is_last = i == len(entries) - 1
            print(prefix + ("└── " if is_last else "├── ") + entry)
            full_path = os.path.join(directory, entry)
            if os.path.isdir(full_path):
                new_prefix = prefix + ("    " if is_last else "│   ")
                print_tree(full_path, new_prefix)
    except PermissionError:
        print(prefix + "Permission denied")
    except Exception as e:
        print(prefix + f"Error accessing directory: {str(e)}")

# Usage
if __name__ == "__main__":
    print_tree(str(BEEGEN_ROOT))  # Start from current directory