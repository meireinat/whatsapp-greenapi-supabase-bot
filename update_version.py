#!/usr/bin/env python3
"""
Script to update VERSION in app/constants.py with git commit hash.
This should be run as a git hook or in CI/CD pipeline.
"""

import subprocess
import re
from pathlib import Path

def get_git_commit_hash() -> str:
    """Get the current git commit hash."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def update_version_file(commit_hash: str):
    """Update VERSION in app/constants.py with commit hash."""
    constants_file = Path(__file__).parent / "app" / "constants.py"
    
    if not constants_file.exists():
        print(f"Error: {constants_file} not found")
        return
    
    content = constants_file.read_text(encoding="utf-8")
    
    # Update VERSION line to include commit hash
    pattern = r'VERSION = "([^"]+)"'
    replacement = f'VERSION = "0.1.0+{commit_hash}"'
    
    new_content = re.sub(pattern, replacement, content)
    
    if new_content != content:
        constants_file.write_text(new_content, encoding="utf-8")
        print(f"Updated VERSION to 0.1.0+{commit_hash}")
    else:
        print("VERSION already up to date or pattern not found")


if __name__ == "__main__":
    commit_hash = get_git_commit_hash()
    update_version_file(commit_hash)

