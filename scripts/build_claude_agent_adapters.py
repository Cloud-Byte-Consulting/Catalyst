#!/usr/bin/env python3
"""Generate thin Claude Code subagent adapters from platform/personas.meta.yaml.

Persona bodies live only in agents/<name>.md. This script delegates to
platform/bootstrap.py (same output as the bootstrap Claude-adapter pass).

Prefer: python platform/bootstrap.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    bootstrap = ROOT / "platform" / "bootstrap.py"
    if not bootstrap.is_file():
        print("platform/bootstrap.py not found", file=sys.stderr)
        return 1
    print(
        "Delegating to platform/bootstrap.py (writes thin .claude/agents/*.md "
        "from platform/personas.meta.yaml)."
    )
    return subprocess.call([sys.executable, str(bootstrap)], cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
