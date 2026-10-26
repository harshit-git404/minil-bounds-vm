#!/usr/bin/env python3
"""
scripts/scrub_paths.py
Hygiene pass: scrubs personal paths and usernames from repository text files.
Records all changes in results/scrub_log.json.
"""

import os
import re
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRUB_LOG = REPO_ROOT / "results" / "scrub_log.json"

TARGET_DIRS = [
    REPO_ROOT / "docs",
    REPO_ROOT / "results",
    REPO_ROOT / "scripts",
    REPO_ROOT / "benchmarks",
    REPO_ROOT / "examples",
    REPO_ROOT / "paper"
]

TARGET_FILES = [
    REPO_ROOT / "REPORT.md",
    REPO_ROOT / "README.md"
]

def main():
    changes = []
    # Patterns to match
    #  -> relative
    # ./ -> ./
    # ~ -> ~
    
    all_files = list(TARGET_FILES)
    for d in TARGET_DIRS:
        if d.exists():
            for root, _, files in os.walk(d):
                for f in files:
                    p = Path(root) / f
                    if p.suffix in [".md", ".json", ".csv", ".txt", ".sh", ".py", ".tex", ".ps1"]:
                        all_files.append(p)

    for p in all_files:
        if not p.exists() or p.is_dir() or p == SCRUB_LOG:
            continue
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        orig = content
        # Scrub 
        content = content.replace("", "")
        content = content.replace("./", "./")
        content = content.replace("~", "~")

        if content != orig:
            p.write_text(content, encoding="utf-8")
            changes.append({
                "file": str(p.relative_to(REPO_ROOT)),
                "status": "scrubbed_personal_paths"
            })
            print(f"Scrubbed personal paths in {p.relative_to(REPO_ROOT)}")

    with open(SCRUB_LOG, "w") as f:
        json.dump({
            "total_files_scrubbed": len(changes),
            "records": changes
        }, f, indent=2)

    print(f"Scrubbing complete. Recorded {len(changes)} changes in {SCRUB_LOG}")

if __name__ == "__main__":
    main()
