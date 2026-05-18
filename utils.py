import os
import subprocess
from pathlib import Path


def _compute_app_version() -> str:
    """Short git SHA for cache-busting static assets in templates.
    Computed once at import; falls back to 'dev' outside a git checkout."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).parent,
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=2,
        ).strip()
    except Exception:
        return "dev"


APP_VERSION = _compute_app_version()


def delete_file(file_path: str):

      # Check if file exists
    if os.path.exists(file_path):
        try:
            # Delete the file
            os.remove(file_path)
            print(f"Deleted file: {file_path}")
        except Exception as e:
            print(f"Error deleting file: {e}")
            return {"error": f"Failed to delete file: {str(e)}"}
    else:
        print(f"File not found: {file_path}")
        return {"error": "File not found"}

    return {"message": "File deleted successfully."}