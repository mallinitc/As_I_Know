from pathlib import Path
import textwrap

PROJECT_ROOT = Path(r"D:\Usecase\Projects\pim-least-privilege-prototype")

def write_py_file(relative_path: str, code: str, overwrite: bool = True) -> Path:
    target_path = PROJECT_ROOT / relative_path

    if target_path.suffix != ".py":
        raise ValueError(f"Target must be a .py file. Received: {target_path}")

    if target_path.exists() and not overwrite:
        raise FileExistsError(f"File already exists: {target_path}")

    target_path.parent.mkdir(parents=True, exist_ok=True)

    cleaned_code = textwrap.dedent(code).strip() + "\n"
    target_path.write_text(cleaned_code, encoding="utf-8")

    print(f"Saved Python file: {target_path}")
    return target_path


def read_py_file(relative_path: str) -> str:
    target_path = PROJECT_ROOT / relative_path

    if not target_path.exists():
        raise FileNotFoundError(f"File not found: {target_path}")

    return target_path.read_text(encoding="utf-8")
