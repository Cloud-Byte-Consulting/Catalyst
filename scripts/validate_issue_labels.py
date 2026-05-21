#!/usr/bin/env python3
"""Validate Catalyst issue label sets for agent indexing (ADR-024 §B.4).

Soft gate for CI or pre-commit: reads issue JSON (GitHub API shape) from stdin
or a file and exits non-zero when required namespaced labels are missing.

Usage:
  gh issue view 123 --json labels | python3 scripts/validate_issue_labels.py
  python3 scripts/validate_issue_labels.py --file issue.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CONSTRUCT_PREFIXES = ("tenant/", "env/", "lz/", "project/", "app/")
KIND_LABELS = frozenset(
    {
        "kind/iac",
        "kind/cicd",
        "kind/service",
        "kind/ai-workflow",
        "kind/security",
        "kind/docs",
        "kind/score",
        "kind/platform",
        "kind/umbrella",
    }
)
DEPRECATED_PREFIXES = ("Kind/", "Priority/", "Status/", "Reviewed/")


def load_payload(path: Path | None) -> dict:
    raw = path.read_text(encoding="utf-8") if path else sys.stdin.read()
    data = json.loads(raw)
    if "issue" in data and isinstance(data["issue"], dict):
        return data["issue"]
    return data


def label_names(payload: dict) -> list[str]:
    labels = payload.get("labels", [])
    if labels and isinstance(labels[0], dict):
        return [item["name"] for item in labels]
    return [str(item) for item in labels]


def validate(labels: list[str]) -> list[str]:
    errors: list[str] = []
    if not any(name.startswith("state/") for name in labels):
        errors.append("missing exactly one state/* label (e.g. state/pending)")
    if not any(name.startswith("type/") for name in labels):
        errors.append("missing exactly one type/* label (e.g. type/feat)")
    kinds = [name for name in labels if name in KIND_LABELS]
    if len(kinds) == 0:
        errors.append(
            "missing kind/* routing label — add one from STATE-MACHINE §2.7 "
            "(kind/iac, kind/cicd, kind/service, kind/docs, …)"
        )
    elif len(kinds) > 1:
        errors.append(f"multiple kind/* labels: {', '.join(sorted(kinds))}")
    for prefix in CONSTRUCT_PREFIXES:
        if not any(name.startswith(prefix) for name in labels):
            errors.append(f"missing construct label with prefix {prefix}")
    deprecated = [
        name
        for name in labels
        if any(name.startswith(prefix) for prefix in DEPRECATED_PREFIXES)
    ]
    if deprecated:
        errors.append(
            "deprecated labels present (remove on edit): " + ", ".join(sorted(deprecated))
        )
    return errors


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, help="Issue JSON file (default: stdin)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = load_payload(args.file)
    errors = validate(label_names(payload))
    if not errors:
        print("ok: label set satisfies Catalyst agent-index requirements")
        return 0
    print("label validation failed:", file=sys.stderr)
    for error in errors:
        print(f"  - {error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
