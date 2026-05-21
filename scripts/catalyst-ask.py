#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
_SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS))
from lib.catalyst_domains import classify_question, load_registry
def main(argv=None):
    p = argparse.ArgumentParser(description="Catalyst question classifier (JSON).")
    p.add_argument("question", nargs="*")
    p.add_argument("--stdin", action="store_true")
    p.add_argument("--registry", type=Path, default=None)
    a = p.parse_args(argv)
    q = sys.stdin.read() if a.stdin else " ".join(a.question)
    q = q.strip()
    if not q:
        p.error("question is required")
    reg = load_registry(a.registry)
    out = classify_question(q, reg)
    json.dump({"question": q, **out}, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
