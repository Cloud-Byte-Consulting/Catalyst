#!/usr/bin/env python3
"""Wire canonical skills/ and agents/ into per-tool trees (ADR-024 §A.2).

Unix: directory/file symlinks into .cursor/, .claude/, and .gemini/.
Windows or --copy: recursive copies with the same layout.

Run after clone or when canonical skills/agents change:
  python platform/bootstrap.py
  python platform/bootstrap.py --check   # CI / verify (exit 1 on drift)

Claude-only rlm-subcall.md under .claude/agents/ is never removed or overwritten.
MCP client configs are emitted in a later bootstrap phase (ADR-024 A-2).
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TOOL_SKILL_DIRS = (
    ROOT / ".cursor" / "skills",
    ROOT / ".claude" / "skills",
    ROOT / ".gemini" / "skills",
)
TOOL_AGENT_DIRS = (
    ROOT / ".cursor" / "agents",
    ROOT / ".claude" / "agents",
    ROOT / ".gemini" / "agents",
)


def _symlinks_supported() -> bool:
    if os.name == "nt":
        return False
    probe = ROOT / ".bootstrap_symlink_probe"
    target = ROOT / ".bootstrap_symlink_target"
    try:
        target.mkdir(exist_ok=True)
        if probe.exists() or probe.is_symlink():
            probe.unlink(missing_ok=True)
        os.symlink(target, probe, target_is_directory=True)
        ok = probe.is_symlink() and probe.resolve() == target.resolve()
        probe.unlink(missing_ok=True)
        return ok
    except OSError:
        return False
    finally:
        probe.unlink(missing_ok=True)
        if target.exists() and not any(target.iterdir()):
            target.rmdir()


def _relative_link_target(link_path: Path, canonical: Path) -> Path:
    return Path(os.path.relpath(canonical.resolve(), link_path.parent.resolve()))


def _remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def _copy_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        _remove_path(dst)
    shutil.copytree(src, dst, symlinks=False)


def _link_or_copy(
    canonical: Path,
    link_path: Path,
    *,
    use_symlinks: bool,
    check_only: bool,
) -> bool:
    """Wire link_path → canonical. Returns True if drift exists or was fixed."""
    if not canonical.exists():
        raise FileNotFoundError(canonical)

    if link_path.is_symlink():
        drift = link_path.resolve() != canonical.resolve()
    elif link_path.is_file() or link_path.is_dir():
        if use_symlinks:
            drift = True
        elif link_path.is_file():
            drift = link_path.read_bytes() != canonical.read_bytes()
        else:
            drift = not _trees_equal(link_path, canonical)
    else:
        drift = True

    if not drift:
        return False

    if check_only:
        return True

    link_path.parent.mkdir(parents=True, exist_ok=True)
    if link_path.exists() or link_path.is_symlink():
        _remove_path(link_path)

    if use_symlinks:
        rel = _relative_link_target(link_path, canonical)
        link_path.symlink_to(rel, target_is_directory=canonical.is_dir())
    elif canonical.is_dir():
        _copy_tree(canonical, link_path)
    else:
        shutil.copy2(canonical, link_path)
    return True


def _trees_equal(a: Path, b: Path) -> bool:
    if not a.is_dir() or not b.is_dir():
        return False
    a_files = {p.relative_to(a) for p in a.rglob("*") if p.is_file()}
    b_files = {p.relative_to(b) for p in b.rglob("*") if p.is_file()}
    if a_files != b_files:
        return False
    for rel in a_files:
        if (a / rel).read_bytes() != (b / rel).read_bytes():
            return False
    return True


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


def bootstrap_skills(*, use_symlinks: bool, check_only: bool) -> list[str]:
    drift: list[str] = []
    for canonical in iter_canonical_skills():
        name = canonical.name
        for tool_dir in TOOL_SKILL_DIRS:
            link_path = tool_dir / name
            if _link_or_copy(
                canonical,
                link_path,
                use_symlinks=use_symlinks,
                check_only=check_only,
            ):
                drift.append(str(link_path.relative_to(ROOT)))
    return drift


def bootstrap_agents(*, use_symlinks: bool, check_only: bool) -> list[str]:
    drift: list[str] = []
    for canonical in iter_canonical_agents():
        name = canonical.name
        for tool_dir in TOOL_AGENT_DIRS:
            link_path = tool_dir / name
            if _link_or_copy(
                canonical,
                link_path,
                use_symlinks=use_symlinks,
                check_only=check_only,
            ):
                drift.append(str(link_path.relative_to(ROOT)))
    return drift


def bootstrap(*, force_copy: bool, check_only: bool) -> int:
    use_symlinks = not force_copy and _symlinks_supported()
    mode = "symlink" if use_symlinks else "copy"
    drift = bootstrap_skills(use_symlinks=use_symlinks, check_only=check_only)
    drift.extend(bootstrap_agents(use_symlinks=use_symlinks, check_only=check_only))

    if check_only and drift:
        print("Bootstrap drift detected:", file=sys.stderr)
        for entry in drift:
            print(f"  - {entry}", file=sys.stderr)
        print(
            f"\nRun `python platform/bootstrap.py` to wire tool trees ({mode} mode).",
            file=sys.stderr,
        )
        return 1

    if not check_only:
        if drift:
            print(f"Bootstrapped {len(drift)} path(s) ({mode} mode).")
        else:
            print(f"Tool trees already wired ({mode} mode).")
    else:
        print(f"Bootstrap check passed ({mode} mode).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if tool trees are missing or stale vs canonical.",
    )
    parser.add_argument(
        "--copy",
        action="store_true",
        help="Force copy mode even on Unix (Windows fallback).",
    )
    args = parser.parse_args()
    return bootstrap(force_copy=args.copy, check_only=args.check)


if __name__ == "__main__":
    sys.exit(main())
