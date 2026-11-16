from pathlib import Path
import beegen


def get_beegen_root():
    """Get the root directory of installed package."""
    package_root = Path(beegen.__file__).parent.parent    
    for i in (".git", ".project_root", ".gitignore"):
        if (package_root / i).exists():
            break
    else:
        package_root = Path.cwd()
    return package_root


CONFIG_ROOT =  Path("D:/beeflow/beeflow")
BEEGEN_ROOT = Path(r"C:\Users\Nam Cuong\Desktop\Do-An-Ki-Su")
LLM_API_TIMEOUT = 300
WINDOW_SIZE: int = 4
