import os
from pathlib import Path
import beegenerate



def get_beegen_root():
    """Get the root directory of installed package."""
    package_root = Path(beegenerate.__file__).parent.parent    
    for i in (".git", ".project_root", ".gitignore"):
        if (package_root / i).exists():
            break
    else:
        package_root = Path.cwd()
    return package_root


CONFIG_ROOT = Path.home() / ".beegen"
BEEGEN_ROOT = get_beegen_root()
LLM_API_TIMEOUT = 300
WINDOW_SIZE: int = 4