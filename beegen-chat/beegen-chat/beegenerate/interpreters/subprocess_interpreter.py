import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import Any, ClassVar, Dict, List

from colorama import Fore

from beegenerate.interpreters.base import BaseInterpreter
from beegenerate.interpreters.interpreter_error import InterpreterError

import asyncio


class SubprocessInterpreter(BaseInterpreter):
    r"""SubprocessInterpreter is a class for executing code files or code
    strings in a subprocess.

    This class handles the execution of code in different scripting languages
    (currently Python and Bash) within a subprocess, capturing their
    stdout and stderr streams, and allowing user checking before executing code
    strings.

    Args:
        require_confirm (bool, optional): If True, prompt user before running
            code strings for security. (default: :obj:`True`)
        print_stdout (bool, optional): If True, print the standard output of
            the executed code. (default: :obj:`False`)
        print_stderr (bool, optional): If True, print the standard error of the
            executed code. (default: :obj:`True`)
    """

    _CODE_EXECUTE_CMD_MAPPING: ClassVar[Dict[str, str]] = {
        "python": "python {file_name}",
        "bash": "bash {file_name}",
    }

    _CODE_EXTENSION_MAPPING: ClassVar[Dict[str, str]] = {
        "python": "py",
        "bash": "sh",
    }

    _CODE_TYPE_MAPPING: ClassVar[Dict[str, str]] = {
        "python": "python",
        "py3": "python",
        "python3": "python",
        "py": "python",
        "shell": "bash",
        "bash": "bash",
        "sh": "bash",
    }

    def __init__(
        self,
        require_confirm: bool = False,
        print_stdout: bool = False,
        print_stderr: bool = True,
    ) -> None:
        self.require_confirm = require_confirm
        self.print_stdout = print_stdout
        self.print_stderr = print_stderr

    def run_file(
        self,
        file: Path,
        code_type: str,
    ) -> str:
        r"""Executes a code file in a subprocess and captures its output.

        Args:
            file (Path): The path object of the file to run.
            code_type (str): The type of code to execute (e.g., 'python',
                'bash').

        Returns:
            str: A string containing the captured stdout and stderr of the
                executed code.

        Raises:
            RuntimeError: If the provided file path does not point to a file.
            InterpreterError: If the code type provided is not supported.
        """
        if not file.is_file():
            raise RuntimeError(f"{file} is not a file.")
        code_type = self._check_code_type(code_type)
        cmd = shlex.split(
            self._CODE_EXECUTE_CMD_MAPPING[code_type].format(
                file_name=str(file.resolve()).replace('\\', '/')
            )
        )
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        stdout, stderr = proc.communicate()
        if self.print_stdout and stdout:
            print("======stdout======")
            print(Fore.GREEN + stdout + Fore.RESET)
            print("==================")
        if self.print_stderr and stderr:
            print("======stderr======")
            print(Fore.RED + stderr + Fore.RESET)
            print("==================")
        exec_result = f"{stdout}"
        exec_result += f"(stderr: {stderr})" if stderr else ""
        return exec_result

    def run(
        self,
        code: str,
        code_type: str,
    ) -> str:
        r"""Generates a temporary file with the given code, executes it, and
            deletes the file afterward.

        Args:
            code (str): The code string to execute.
            code_type (str): The type of code to execute (e.g., 'python',
                'bash').

        Returns:
            str: A string containing the captured stdout and stderr of the
                executed code.

        Raises:
            InterpreterError: If the user declines to run the code or if the
                code type is unsupported.
        """
        code_type = self._check_code_type(code_type)

        # Print code for security checking
        if self.require_confirm:
            print(f"The following {code_type} code will run on your computer:")
            print(Fore.CYAN + code + Fore.RESET)
            while True:
                choice = input("Running code? [Y/n]:").lower()
                if choice in ["y", "yes", "ye", ""]:
                    break
                elif choice in ["no", "n"]:
                    raise InterpreterError(
                        "Execution halted: User opted not to run the code. "
                        "This choice stops the current operation and any "
                        "further code execution."
                    )
        temp_file_path = self._create_temp_file(
            code=code, extension=self._CODE_EXTENSION_MAPPING[code_type]
        )

        result = self.run_file(temp_file_path, code_type)

        temp_file_path.unlink()
        return result

    def _create_temp_file(self, code: str, extension: str) -> Path:
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=f".{extension}"
        ) as f:
            f.write(code)
            name = f.name
        return Path(name)

    def _check_code_type(self, code_type: str) -> str:
        if code_type not in self._CODE_TYPE_MAPPING:
            raise InterpreterError(
                f"Unsupported code type {code_type}. Currently "
                f"`{self.__class__.__name__}` only supports "
                f"{', '.join(self._CODE_EXTENSION_MAPPING.keys())}."
            )
        return self._CODE_TYPE_MAPPING[code_type]

    def supported_code_types(self) -> List[str]:
        r"""Provides supported code types by the interpreter."""
        return list(self._CODE_EXTENSION_MAPPING.keys())

    def update_action_space(self, action_space: Dict[str, Any]) -> None:
        r"""Updates action space for *python* interpreter"""
        raise RuntimeError(
            "SubprocessInterpreter doesn't support " "`action_space`."
        )
        
        
def run_code_string_test():
    # Initialize interpreter with output printing enabled
    interpreter = SubprocessInterpreter(
        require_confirm=False,   # Will ask for confirmation before running
        print_stdout=True,      # Will print stdout to console
        print_stderr=True       # Will print stderr if there are errors
    )
    
    # Example 1: Running Python code as a string
    python_code = """
import random

# Generate some random numbers
numbers = [random.randint(1, 100) for _ in range(5)]
print(f"Random numbers: {numbers}")

# Calculate and print statistics
print(f"Sum: {sum(numbers)}")
print(f"Average: {sum(numbers)/len(numbers):.2f}")
"""

    print("\n=== Running Python code string ===")
    result = interpreter.run(python_code, code_type="python")
    
    print("\nResult from code string execution:")
    print(result)
    
    
def run_code_file_test():
    # Initialize interpreter with output printing enabled
    interpreter = SubprocessInterpreter(
        require_confirm=False,   # Will ask for confirmation before running
        print_stdout=True,      # Will print stdout to console
        print_stderr=True       # Will print stderr if there are errors
    )
    # Example 2: Running a Python file
    # First create a sample Python file
    sample_file_content = """
def calculate_fibonacci(n):
    if n <= 0:
        return []
    elif n == 1:
        return [0]
    
    fib = [0, 1]
    for i in range(2, n):
        fib.append(fib[i-1] + fib[i-2])
    return fib

# Calculate first 10 Fibonacci numbers
fibonacci_sequence = calculate_fibonacci(10)
print(f"First 10 Fibonacci numbers: {fibonacci_sequence}")
"""
    
    # Create a temporary Python file
    file_path = Path("sample_script.py")
    file_path.write_text(sample_file_content)
    
    try:
        print("\n=== Running Python file ===")
        result = interpreter.run_file(file_path, code_type="python")
        print("\nResult from file execution:")
        print(result)
    finally:
        # Clean up - delete the temporary file
        file_path.unlink()
    
    # Example 3: Demonstrating error handling
    error_code = """
# This will raise a NameError
print(undefined_variable)
"""
    
    print("\n=== Running code with error ===")
    try:
        result = interpreter.run(error_code, code_type="python")
        print(result)
    except Exception as e:
        print(f"Caught error: {e}")
    
    # Example 4: Showing supported code types
    print("\n=== Supported code types ===")
    supported_types = interpreter.supported_code_types()
    print(f"This interpreter supports: {supported_types}")
    

if __name__ == "__main__":
    run_code_string_test()