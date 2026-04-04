#!/usr/bin/env python3
"""Archive final composition outputs to a song-named folder under output/."""

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path


def archive(workdir: str = ".clef-work") -> str:
    """
    Copy final composition files to output/{title}/ directory.

    Copies: score.abc -> score_final.abc, plan.json, and any *.mid files.
    Returns the archive directory path.
    """
    work = Path(os.path.normpath(os.path.abspath(workdir)))
    output_dir = work / "output"

    # Read title from plan.json
    plan_path = work / "plan.json"
    if not plan_path.exists():
        raise FileNotFoundError(f"plan.json not found in {workdir}")

    with open(plan_path, "r", encoding="utf-8") as f:
        plan = json.load(f)

    title = plan.get("title", "untitled")
    # Sanitize: strip filesystem-unsafe chars
    safe_title = re.sub(r'[<>:"/\\|?*]', '_', title).strip()
    safe_title = "".join(c for c in safe_title if c.isalnum() or c in " _-").strip()
    safe_title = safe_title or "untitled"

    archive_dir = output_dir / safe_title
    archive_dir.mkdir(parents=True, exist_ok=True)

    # Copy score.abc -> score_final.abc
    score_src = work / "score.abc"
    if score_src.exists():
        shutil.copy2(score_src, archive_dir / "score_final.abc")

    # Copy plan.json
    shutil.copy2(plan_path, archive_dir / "plan.json")

    # Copy all .mid files from workdir
    for mid in work.glob("*.mid"):
        shutil.copy2(mid, archive_dir / mid.name)

    return str(archive_dir)


def main():
    parser = argparse.ArgumentParser(description="Archive final composition to output/{title}/")
    parser.add_argument("--workdir", default=".clef-work", help="Working directory")
    args = parser.parse_args()

    if not os.path.isdir(args.workdir):
        print(f"Error: workdir not found: {args.workdir}", file=sys.stderr)
        sys.exit(1)

    dest = archive(args.workdir)
    print(f"Archived to: {dest}")


if __name__ == "__main__":
    main()
