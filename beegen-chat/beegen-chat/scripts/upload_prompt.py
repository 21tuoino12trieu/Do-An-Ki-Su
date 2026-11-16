from beegenerate.loggings.loggers import lf
import ast
import os
import re

def get_variables_from_file(file_path):
    with open(file_path, 'r', encoding="utf8") as file:
        tree = ast.parse(file.read(), filename=file_path)
    
    variables = []
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    var_name = target.id
                    if isinstance(node.value, ast.Str):
                        var_value = node.value.s
                    elif isinstance(node.value, ast.Num):
                        var_value = node.value.n
                    elif isinstance(node.value, ast.Name):
                        var_value = node.value.id
                    else:
                        var_value = None  # Handle other types if needed
                    variables.append({"var_name": var_name, "var_value": var_value})
    
    return variables


def walk_python_files(folder_path):
    list_file = []
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            if file.endswith('.py'):
                if file.startswith('__init__'):
                    continue
                else:
                    full_path = os.path.join(root, file)
                    list_file.append(full_path)
    return list_file                

def escape_curly_braces(text):
    # Define the pattern to match {var}
    pattern = r'\{(\w+)\}'
    
    # Define the replacement pattern {{var}}
    replacement = r'{{\1}}'
    
    # Use re.sub to replace all occurrences of the pattern
    escaped_text = re.sub(pattern, replacement, text)
    return escaped_text

def main():
    list_folder = [
        # {
        #     "name": "BEECHAT_KHCN",
        #     "path": "../beechat_khcn/prompts"
        # },
        # {
        #     "name": "BEECHAT",
        #     "path": "../beechat/prompts"
        # }
        {
            "name":"beehi_QHLD",
            "path": "beehi_QHLD/data"
        }
    ]
    for bot_folder in list_folder:
        list_file = walk_python_files(bot_folder['path'])
        for file in list_file:
            # print(f"file name: {file}")
            list_var = get_variables_from_file(file)
            for var in list_var:
                if var['var_value'] is None:
                    print(f"ERROR: {var['var_name']} | {file}")
                    continue
                else:
                    lf.create_prompt(
                        name=f"{bot_folder['name']}_{var['var_name']}",
                        type="text",
                        prompt=escape_curly_braces(var['var_value']),
                        labels=["production"],  # directly promote to production
                        # config={
                        #     "model": "gpt-4o",
                        #     "temperature": 0.7,
                        #     "supported_languages": ["en", "fr"],
                        # },  # optionally, add configs (e.g. model parameters or model tools) or tags
                    )

main()