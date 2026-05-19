#!/usr/bin/env python3
"""Sync canonical skills/agents into per-tool stub locations.

Layout:
  skills/<name>/SKILL.md         -- canonical content
  .claude/skills/<name>/SKILL.md -- auto-generated stub
  .cursor/skills/<name>/SKILL.md -- auto-generated stub

  agents/<name>.md               -- canonical persona content
  .cursor/agents/<name>.md       -- auto-generated stub
  .claude/agents/<name>.md       -- adapter (NOT auto-generated; ships Claude frontmatter)

Stubs are file copies prefixed with a one-line provenance header.
This script is idempotent: it regenerates every stub from canonical and
writes only when the resulting content differs.

The companion `check_tool_stubs.py` runs the same generation and exits
non-zero if any stub on disk differs from the canonical expansion — the
CI workflow uses that one.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SKILL_STUB_HEADER = (
    "<!-- AUTO-GENERATED from skills/{name}/SKILL.md — do not edit here. "
    "Run scripts/sync_tool_skills.py to regenerate. -->\n"
)

AGENT_STUB_HEADER = (
    "<!-- AUTO-GENERATED from agents/{name}.md — do not edit here. "
    "Run scripts/sync_tool_skills.py to regenerate. -->\n"
)


def iter_canonical_skills() -> list[Path]:
    base = ROOT / "skills"
    if not base.is_dir():
        return []
    return sorted(p for p in base.iterdir() if p.is_dir() and (p / "SKILL.md").is_file())


def iter_canonical_agents() -> list[Path]:
    base = ROOT / "agents"
    if not base.is_dir():
        return []
    return sorted(p for p in base.glob("*.md") if p.is_file())


def render_skill_stub(canonical: Path) -> str:
    name = canonical.name
    body = (canonical / "SKILL.md").read_text(encoding="utf-8")
    return SKILL_STUB_HEADER.format(name=name) + body


def render_cursor_agent_stub(canonical: Path) -> str:
    name = canonical.stem
    body = canonical.read_text(encoding="utf-8")
    return AGENT_STUB_HEADER.format(name=name) + body


def write_if_changed(path: Path, content: str, *, check_only: bool) -> bool:
    """Returns True if file was/would-be written (i.e. drift exists)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.is_file() else None
    if existing == content:
        return False
    if check_only:
        return True
    path.write_text(content, encoding="utf-8", newline="\n")
    return True


def sync(check_only: bool = False) -> int:
    drift: list[str] = []

    for canonical in iter_canonical_skills():
        name = canonical.name
        content = render_skill_stub(canonical)
        for tool_dir in ("claude", "cursor"):
            stub = ROOT / f".{tool_dir}" / "skills" / name / "SKILL.md"
            if write_if_changed(stub, content, check_only=check_only):
                drift.append(str(stub.relative_to(ROOT)))

    # Cursor agents are pure persona prose — stub-copy them.
    # Claude agents need explicit frontmatter (model/tools) so they are
    # adapter files curated in-repo, not auto-generated.
    for canonical in iter_canonical_agents():
        name = canonical.stem
        content = render_cursor_agent_stub(canonical)
        stub = ROOT / ".cursor" / "agents" / f"{name}.md"
        if write_if_changed(stub, content, check_only=check_only):
            drift.append(str(stub.relative_to(ROOT)))

    if check_only and drift:
        print("Drift detected in the following tool stubs:", file=sys.stderr)
        for entry in drift:
            print(f"  - {entry}", file=sys.stderr)
        print(
            "\nRun `python scripts/sync_tool_skills.py` to regenerate.",
            file=sys.stderr,
        )
        return 1
    if drift:
        print(f"Regenerated {len(drift)} stub(s).")
    else:
        print("All stubs in sync with canonical sources.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if any stub is out of sync (for CI).",
    )
    args = parser.parse_args()
    return sync(check_only=args.check)


if __name__ == "__main__":
    sys.exit(main())
