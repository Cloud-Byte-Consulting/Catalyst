#!/usr/bin/env python3
"""Idempotently ensure ADR-024 agent-index labels exist in a GitHub repo.

Creates or updates labels defined in docs/ADR/STATE-MACHINE.md §2.7–2.7.1
(kind/security, kind/docs, kind/platform, kind/score, cloud/*, area/*).
Safe to run repeatedly — existing labels with matching name/description/color
are left unchanged.

Usage:
  python3 scripts/ensure_agent_index_labels.py
  python3 scripts/ensure_agent_index_labels.py --repo owner/name --dry-run
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class LabelSpec:
    name: str
    color: str
    description: str


# Registry aligned with ADR-024 §B.3 and STATE-MACHINE §2.7–2.7.1.
AGENT_INDEX_LABELS: tuple[LabelSpec, ...] = (
    LabelSpec("kind/security", "9c27b0", "IAM, secrets, containers, scanning, WAF"),
    LabelSpec("kind/docs", "0075ca", "ADRs, README, diagrams, onboarding docs"),
    LabelSpec("kind/platform", "5319e7", "IDP strategy, golden paths, cross-cutting platform"),
    LabelSpec("kind/score", "1d76db", "Score workload specs and portability"),
    LabelSpec("cloud/aws", "ff9900", "AWS-scoped work (ADR-023 parity)"),
    LabelSpec("cloud/azure", "0078d4", "Azure-scoped work"),
    LabelSpec("cloud/gcp", "4285f4", "GCP-scoped work"),
    LabelSpec("area/infrastructure", "006b75", "Infrastructure path scope"),
    LabelSpec("area/services", "006b75", "services/ path scope"),
    LabelSpec("area/docs", "006b75", "docs/ path scope"),
)

DEFAULT_REPO = "Cloud-Byte-Consulting/Catalyst"

# Deprecated labels that block namespaced creation (GitHub names are case-insensitive).
LEGACY_RENAMES: dict[str, str] = {
    "Kind/Security": "kind/security",
}


def run_gh(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["gh", *args],
        check=False,
        capture_output=True,
        text=True,
    )


def list_labels(repo: str) -> dict[str, dict[str, str]]:
    result = run_gh(["api", f"repos/{repo}/labels", "--paginate"])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "gh api labels failed")
    labels: dict[str, dict[str, str]] = {}
    payload = json.loads(result.stdout)
    items = payload if isinstance(payload, list) else [payload]
    for item in items:
        labels[item["name"]] = {
            "color": item.get("color", ""),
            "description": item.get("description") or "",
        }
    return labels


def label_matches(existing: dict[str, str], spec: LabelSpec) -> bool:
    return (
        existing.get("color", "").lower() == spec.color.lower()
        and (existing.get("description") or "") == spec.description
    )


def find_legacy_blocker(existing: dict[str, dict[str, str]], spec: LabelSpec) -> str | None:
    target = spec.name.lower()
    for name in existing:
        if name != spec.name and name.lower() == target:
            return name
    for legacy, new_name in LEGACY_RENAMES.items():
        if new_name == spec.name and legacy in existing:
            return legacy
    return None


def ensure_labels(
    repo: str,
    specs: tuple[LabelSpec, ...],
    *,
    dry_run: bool,
) -> list[tuple[str, str]]:
    existing = list_labels(repo)
    results: list[tuple[str, str]] = []

    for spec in specs:
        current = existing.get(spec.name)
        if current and label_matches(current, spec):
            results.append((spec.name, "ok"))
            print(f"{spec.name}: ok")
            continue

        legacy = find_legacy_blocker(existing, spec)
        if legacy and not current:
            action = "rename"
            if dry_run:
                results.append((spec.name, f"would-{action}-from-{legacy}"))
                print(f"{spec.name}: would-{action}-from-{legacy}")
                continue
            encoded = legacy.replace("/", "%2F")
            result = run_gh(
                [
                    "api",
                    "-X",
                    "PATCH",
                    f"repos/{repo}/labels/{encoded}",
                    "-f",
                    f"new_name={spec.name}",
                    "-f",
                    f"color={spec.color}",
                    "-f",
                    f"description={spec.description}",
                ]
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"rename {legacy} -> {spec.name} failed: "
                    f"{result.stderr.strip() or result.stdout.strip()}"
                )
            results.append((spec.name, action))
            print(f"{spec.name}: {action}-from-{legacy}")
            existing[spec.name] = {"color": spec.color, "description": spec.description}
            existing.pop(legacy, None)
            continue

        if current:
            action = "update"
            if dry_run:
                results.append((spec.name, f"would-{action}"))
                print(f"{spec.name}: would-{action}")
                continue
            encoded = spec.name.replace("/", "%2F")
            result = run_gh(
                [
                    "api",
                    "-X",
                    "PATCH",
                    f"repos/{repo}/labels/{encoded}",
                    "-f",
                    f"color={spec.color}",
                    "-f",
                    f"description={spec.description}",
                ]
            )
        else:
            action = "create"
            if dry_run:
                results.append((spec.name, f"would-{action}"))
                print(f"{spec.name}: would-{action}")
                continue
            result = run_gh(
                [
                    "api",
                    "-X",
                    "POST",
                    f"repos/{repo}/labels",
                    "-f",
                    f"name={spec.name}",
                    "-f",
                    f"color={spec.color}",
                    "-f",
                    f"description={spec.description}",
                ]
            )

        if result.returncode != 0:
            raise RuntimeError(
                f"{action} {spec.name} failed: {result.stderr.strip() or result.stdout.strip()}"
            )
        results.append((spec.name, action))
        print(f"{spec.name}: {action}")

    return results


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo",
        default=DEFAULT_REPO,
        help=f"GitHub repository (default: {DEFAULT_REPO})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned actions without calling the GitHub API",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    results = ensure_labels(args.repo, AGENT_INDEX_LABELS, dry_run=args.dry_run)

    created = sum(1 for _, s in results if s == "create")
    updated = sum(1 for _, s in results if s == "update")
    renamed = sum(1 for _, s in results if s == "rename")
    unchanged = sum(1 for _, s in results if s == "ok")
    print(
        f"\nSummary: {unchanged} unchanged, {created} created, {updated} updated, {renamed} renamed"
        + (" (dry-run)" if args.dry_run else "")
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
