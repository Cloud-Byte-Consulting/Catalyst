#!/usr/bin/env python3
"""Backfill missing kind/* labels on open Catalyst issues (ADR-024 §B.4).

Infers a single `kind/*` label from existing labels, legacy `Kind/*` names,
`type/*`, and title keywords. Optionally strips deprecated legacy labels when
an issue is touched.

Usage:
  python3 scripts/backfill_issue_kind_labels.py --dry-run
  python3 scripts/backfill_issue_kind_labels.py --apply
  python3 scripts/backfill_issue_kind_labels.py --apply --include-recent-closed

By default only **open** issues are considered. Closed issues are skipped unless
``--include-recent-closed`` is passed (30-day window). Never mass-retags full
closed history.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

DEFAULT_REPO = "Cloud-Byte-Consulting/Catalyst"

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

LEGACY_KIND_MAP = {
    "Kind/Documentation": "kind/docs",
    "Kind/Security": "kind/security",
    "Kind/Feature": "kind/service",
    "Kind/Enhancement": "kind/platform",
    "Kind/Bug": "kind/service",
    "Kind/Testing": "kind/cicd",
}

DEPRECATED_PREFIXES = ("Kind/", "Priority/", "Status/", "Reviewed/")
DEPRECATED_EXACT = frozenset({"bug", "enhancement", "documentation"})

TYPE_KIND_DEFAULTS = {
    "type/docs": "kind/docs",
    "type/deploy": "kind/cicd",
    "type/pr-review": "kind/ai-workflow",
    "type/secret-rotation": "kind/security",
    "type/ops-intel-finding": "kind/security",
    "type/ops-intel-digest": "kind/platform",
    "type/incident": "kind/platform",
    "type/preview-env": "kind/iac",
}

TITLE_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("umbrella", "meta-tracking", "consolidated adr"), "kind/umbrella"),
    (("terraform", "checkov", " opa", "iac", "hcl", "module", "ecs autoscaling", "aurora"), "kind/iac"),
    (("github action", "cicd", "ci/cd", "workflow", "oidc", "pipeline", "deploy"), "kind/cicd"),
    (("bedrock", "pr review", "ai review", "prompt", "reviewer", "ai-workflow"), "kind/ai-workflow"),
    (("iam", "secret", "trivy", "waf", "security", "scan", "encryption"), "kind/security"),
    (("adr", "readme", "diagram", "docs", "onboarding", "documentation", "platform.md"), "kind/docs"),
    (("score.yaml", "score ", "portability", "score-"), "kind/score"),
    (("platform", "golden path", "idp", "bootstrap", "agent-system", "kaizen"), "kind/platform"),
    (("lambda", "fastapi", "service", "api", "webhook", "cli", "client cli", "opa", "checkov"), "kind/service"),
)


@dataclass(frozen=True)
class Proposal:
    number: int
    title: str
    state: str
    current_kinds: tuple[str, ...]
    proposed_kind: str | None
    remove_labels: tuple[str, ...]
    reason: str


def run_gh(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["gh", *args], capture_output=True, text=True, check=False)


def fetch_issues(repo: str, *, state: str, recent_closed_days: int | None) -> list[dict]:
    fields = ["number", "title", "state", "labels", "closedAt"]
    result = run_gh(
        [
            "issue",
            "list",
            "--repo",
            repo,
            "--state",
            state,
            "--limit",
            "500",
            "--json",
            ",".join(fields),
        ]
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "gh issue list failed")
    issues = json.loads(result.stdout)
    if state != "closed" or recent_closed_days is None:
        return issues
    cutoff = datetime.now(tz=UTC) - timedelta(days=recent_closed_days)
    filtered = []
    for issue in issues:
        closed_at = issue.get("closedAt")
        if not closed_at:
            continue
        closed_dt = datetime.fromisoformat(closed_at.replace("Z", "+00:00"))
        if closed_dt >= cutoff:
            filtered.append(issue)
    return filtered


def label_names(issue: dict) -> list[str]:
    return [label["name"] for label in issue.get("labels", [])]


def infer_kind(labels: list[str], title: str) -> tuple[str | None, str]:
    kinds = [name for name in labels if name in KIND_LABELS]
    if len(kinds) == 1:
        return kinds[0], "existing-single-kind"
    if len(kinds) > 1:
        return None, f"ambiguous-kind:{','.join(sorted(kinds))}"

    for legacy, kind in LEGACY_KIND_MAP.items():
        if legacy in labels:
            return kind, f"legacy:{legacy}"

    type_labels = [name for name in labels if name.startswith("type/")]
    for type_label in type_labels:
        if type_label in TYPE_KIND_DEFAULTS:
            return TYPE_KIND_DEFAULTS[type_label], f"type-default:{type_label}"

    lowered = title.lower()
    for keywords, kind in TITLE_RULES:
        if any(keyword in lowered for keyword in keywords):
            return kind, f"title:{kind}"

    if "type/kaizen" in type_labels:
        return "kind/platform", "type/kaizen-default"

    if type_labels:
        return "kind/platform", f"fallback-for-{type_labels[0]}"

    return None, "no-signal"


def deprecated_labels(labels: list[str]) -> list[str]:
    remove: list[str] = []
    for name in labels:
        if name in DEPRECATED_EXACT:
            remove.append(name)
        elif any(name.startswith(prefix) for prefix in DEPRECATED_PREFIXES):
            remove.append(name)
    return sorted(set(remove))


def build_proposals(issues: list[dict]) -> list[Proposal]:
    proposals: list[Proposal] = []
    for issue in issues:
        labels = label_names(issue)
        kinds = tuple(sorted(name for name in labels if name in KIND_LABELS))
        proposed, reason = infer_kind(labels, issue["title"])
        remove = tuple(deprecated_labels(labels))
        needs_kind = len(kinds) != 1
        needs_cleanup = bool(remove)
        if not needs_kind and not needs_cleanup:
            continue
        if needs_kind and proposed is None:
            proposals.append(
                Proposal(
                    issue["number"],
                    issue["title"],
                    issue["state"],
                    kinds,
                    None,
                    remove,
                    reason,
                )
            )
            continue
        if needs_kind:
            proposals.append(
                Proposal(
                    issue["number"],
                    issue["title"],
                    issue["state"],
                    kinds,
                    proposed,
                    remove,
                    reason,
                )
            )
        elif needs_cleanup:
            proposals.append(
                Proposal(
                    issue["number"],
                    issue["title"],
                    issue["state"],
                    kinds,
                    kinds[0],
                    remove,
                    "deprecated-cleanup-only",
                )
            )
    return sorted(proposals, key=lambda item: item.number)


def apply_proposal(repo: str, proposal: Proposal) -> None:
    view = run_gh(["issue", "view", str(proposal.number), "--repo", repo, "--json", "labels"])
    if view.returncode != 0:
        raise RuntimeError(view.stderr.strip() or f"failed to read #{proposal.number}")
    labels = label_names(json.loads(view.stdout))
    target = [name for name in labels if name not in proposal.remove_labels]
    target = [name for name in target if name not in KIND_LABELS]
    if proposal.proposed_kind:
        target.append(proposal.proposed_kind)

    to_add = sorted(set(target) - set(labels))
    to_remove = sorted(set(labels) - set(target))

    if to_add:
        result = run_gh(
            [
                "issue",
                "edit",
                str(proposal.number),
                "--repo",
                repo,
                "--add-label",
                ",".join(to_add),
            ]
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"issue #{proposal.number} add labels: "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )
    if to_remove:
        result = run_gh(
            [
                "issue",
                "edit",
                str(proposal.number),
                "--repo",
                repo,
                "--remove-label",
                ",".join(to_remove),
            ]
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"issue #{proposal.number} remove labels: "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )


def format_summary(proposals: list[Proposal], *, applied: bool) -> str:
    actionable = [p for p in proposals if p.proposed_kind]
    ambiguous = [p for p in proposals if p.proposed_kind is None]
    lines = [
        "### Actions taken" if applied else "### Verification",
        "",
        f"**Mode**: {'apply' if applied else 'dry-run'}",
        f"**Proposed kind/* updates**: {len(actionable)}",
        f"**Ambiguous (needs human)**: {len(ambiguous)}",
        "",
        "| Issue | Proposed kind/* | Remove legacy | Reason |",
        "|---|---|---|---|",
    ]
    for proposal in proposals:
        kind = proposal.proposed_kind or "—"
        remove = ", ".join(proposal.remove_labels) if proposal.remove_labels else "—"
        title = proposal.title.replace("|", "\\|")[:80]
        lines.append(
            f"| #{proposal.number} {title} | `{kind}` | {remove} | {proposal.reason} |"
        )
    if ambiguous:
        lines.extend(["", "**Ambiguous issues (manual review before apply):**"])
        for proposal in ambiguous:
            lines.append(f"- #{proposal.number}: {proposal.reason}")
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--include-recent-closed",
        action="store_true",
        help="Also process issues closed within the last 30 days",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    issues = fetch_issues(args.repo, state="open", recent_closed_days=None)
    if args.include_recent_closed:
        issues.extend(fetch_issues(args.repo, state="closed", recent_closed_days=30))

    proposals = build_proposals(issues)
    summary = format_summary(proposals, applied=args.apply)
    print(summary)

    if args.dry_run:
        return 0

    for proposal in proposals:
        if proposal.proposed_kind is None:
            continue
        apply_proposal(args.repo, proposal)
        print(f"updated #{proposal.number} -> {proposal.proposed_kind}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
