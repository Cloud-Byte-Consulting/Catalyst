#!/usr/bin/env python3
"""Deprecated: use platform/bootstrap.py (ADR-024 A-4)."""
from __future__ import annotations
import argparse, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
BOOTSTRAP = ROOT / "platform" / "bootstrap.py"
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    print("scripts/sync_tool_skills.py is deprecated; use platform/bootstrap.py", file=sys.stderr)
    if not BOOTSTRAP.is_file():
        return 1
    cmd = [sys.executable, str(BOOTSTRAP)] + (["--check"] if args.check else [])
    return subprocess.call(cmd, cwd=ROOT)
if __name__ == "__main__":
    raise SystemExit(main())
