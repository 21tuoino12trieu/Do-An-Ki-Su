import os

def print_folders_and_py_files(root_path, prefix=""):
    """
    Recursively print folders and .py files in a tree-like structure
    Excludes .git folders and other common ignore patterns
    """
    # Folders to ignore
    ignore_folders = {
        '.git', '.venv', 'venv', 'env', '.env',
        '__pycache__', '.pytest_cache', '.mypy_cache', 
        'node_modules', '.vscode', '.idea', '.vs',
        'lib', 'lib64', 'include', 'bin', 'share',
        '.tox', 'dist', 'build', 'egg-info', '.eggs',
        '.coverage', '.nyc_output', 'coverage',
        '.DS_Store', 'Thumbs.db'
    }
    
    try:
        # Get all items in the current directory
        items = sorted(os.listdir(root_path))
        
        # Separate directories and .py files
        directories = []
        py_files = []
        
        for item in items:
            item_path = os.path.join(root_path, item)
            if os.path.isdir(item_path):
                # Only add directory if it's not in the ignore list
                if item not in ignore_folders:
                    directories.append(item)
            elif item.endswith('.py'):
                py_files.append(item)
        
        # Print directories first (only the non-ignored ones)
        for i, directory in enumerate(directories):
            is_last_dir = (i == len(directories) - 1) and len(py_files) == 0
            connector = "└── " if is_last_dir else "├── "
            print(f"{prefix}{connector}{directory}/")
            
            # Recursive call for subdirectories
            new_prefix = prefix + ("    " if is_last_dir else "│   ")
            dir_path = os.path.join(root_path, directory)
            print_folders_and_py_files(dir_path, new_prefix)
        
        # Print .py files
        for i, py_file in enumerate(py_files):
            is_last = i == len(py_files) - 1
            connector = "└── " if is_last else "├── "
            print(f"{prefix}{connector}{py_file}")
            
    except PermissionError:
        print(f"{prefix}[Permission Denied]")
    except Exception as e:
        print(f"{prefix}[Error: {e}]")

# Example usage
if __name__ == "__main__":
    import sys
    
    # Use current directory if no path provided
    path = sys.argv[1] if len(sys.argv) > 1 else "."
    
    print(f"Directory structure for: {os.path.abspath(path)}")
    print(f"{os.path.basename(os.path.abspath(path))}/")
    print_folders_and_py_files(path)