"""
Fix backslash paths in markdown files to forward slashes.
"""
from pathlib import Path
import re

def fix_markdown_paths():
    repo_root = Path(__file__).resolve().parent.parent
    count = 0
    for md in repo_root.glob("**/*.md"):
        if ".venv" in md.parts or ".git" in md.parts:
            continue
        try:
            content = md.read_text(encoding="utf-8")
        except Exception:
            continue

        def _repl(match):
            nonlocal count
            text = match.group(1)
            target = match.group(2)
            if "\\" in target:
                count += 1
                target = target.replace("\\", "/")
            return f"[{text}]({target})"

        new_content = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", _repl, content)
        if new_content != content:
            md.write_text(new_content, encoding="utf-8")
            print(f"Normalized paths in: {md.relative_to(repo_root)}")

    print(f"Total link paths normalized: {count}")

if __name__ == "__main__":
    fix_markdown_paths()
