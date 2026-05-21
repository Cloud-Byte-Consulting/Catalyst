"""ADR-024 domain registry."""
from __future__ import annotations
import re
from pathlib import Path
from typing import Any
import yaml
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_REGISTRY = _REPO_ROOT / "registry" / "catalyst-domains.yaml"
_HANDOFF_HEADINGS = (
    "Context", "Decision", "Rationale", "Alternatives considered",
    "Actions taken", "Verification", "Risks / follow-ups", "Risks or follow-ups",
    "Next", "Agent Decision Log",
)
def load_registry(path: Path | str | None = None) -> dict[str, Any]:
    reg_path = Path(path) if path is not None else _DEFAULT_REGISTRY
    with reg_path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict) or "kinds" not in data:
        raise ValueError(f"invalid registry: {reg_path}")
    return data
def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _gh_query_string(registry: dict[str, Any], kind_key: str | None) -> str:
    repo = registry.get("repo") or "Cloud-Byte-Consulting/Catalyst"
    parts = ["gh issue list", f'--repo "{repo}"', "--state open", "--limit 20"]
    if kind_key and kind_key in registry.get("kinds", {}):
        parts.append(f'--label "{registry["kinds"][kind_key]["label"]}"')
    return " ".join(parts)
def classify_question(question: str, registry: dict[str, Any] | None = None) -> dict[str, Any]:
    reg = registry if registry is not None else load_registry()
    q = _normalize(question)
    kinds = reg["kinds"]
    keyword_kind = reg.get("keyword_kind") or {}
    for phrase, kind_key in sorted(keyword_kind.items(), key=lambda kv: len(kv[0]), reverse=True):
        if _normalize(phrase) in q:
            entry = kinds[kind_key]
            return {
                "kind": kind_key,
                "label": entry["label"],
                "personas": list(entry["personas"]),
                "domains": [{"kind": kind_key, "label": entry["label"], "score": 3, "matched_signals": [phrase]}],
                "confidence": 0.9,
                "confidence_label": "high",
                "method": "keyword_kind",
                "matched": phrase,
                "suggested_gh_query": _gh_query_string(reg, kind_key),
            }
    scores = []
    for kind_key, entry in kinds.items():
        matched = [s for s in (entry.get("signals") or []) if _normalize(s) in q]
        if matched:
            scores.append((len(matched), kind_key, matched))
    if not scores:
        empty = {
            "kind": None,
            "label": None,
            "personas": [],
            "domains": [],
            "confidence": 0.0,
            "confidence_label": "none",
            "method": "none",
            "matched": [],
            "suggested_gh_query": _gh_query_string(reg, None),
        }
        return empty
    scores.sort(key=lambda t: (-t[0], t[1]))
    _, kind_key, matched_signals = scores[0]
    entry = kinds[kind_key]
    confidence_label = "high" if scores[0][0] >= 2 else "medium"
    confidence = 0.85 if confidence_label == "high" else 0.6
    domains = [
        {
            "kind": key,
            "label": kinds[key]["label"],
            "score": count,
            "matched_signals": matched,
        }
        for count, key, matched in scores[:3]
    ]
    return {
        "kind": kind_key,
        "label": entry["label"],
        "personas": list(entry["personas"]),
        "domains": domains,
        "confidence": confidence,
        "confidence_label": confidence_label,
        "method": "signals",
        "matched": matched_signals,
        "suggested_gh_query": _gh_query_string(reg, kind_key),
    }
def build_gh_issue_query(*, kind: str | None = None, state: str | None = None, type_label: str | None = None,
                         registry: dict[str, Any] | None = None, repo: str | None = None) -> dict[str, Any]:
    reg = registry if registry is not None else load_registry()
    repo_name = repo or reg.get("repo") or "Cloud-Byte-Consulting/Catalyst"
    labels = []
    if kind:
        if kind not in reg["kinds"]:
            raise ValueError(f"unknown kind: {kind}")
        labels.append(reg["kinds"][kind]["label"])
    if state:
        labels.append(state if state.startswith("state/") else f"state/{state}")
    if type_label:
        labels.append(type_label if type_label.startswith("type/") else f"type/{type_label}")
    args = ["issue", "list", "--repo", repo_name, "--json", "number,title,labels,state"]
    for lab in labels:
        args.extend(["--label", lab])
    return {"repo": repo_name, "labels": labels, "gh_args": args}
_SECTION_RE = re.compile(r"^###\s+(.+?)\s*$", re.MULTILINE)
def extract_handoff_sections(markdown: str) -> dict[str, str]:
    if not markdown:
        return {}
    sections = {}
    matches = list(_SECTION_RE.finditer(markdown))
    for idx, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(markdown)
        body = markdown[start:end].strip()
        if title in _HANDOFF_HEADINGS or title.startswith("Agent Decision Log"):
            sections[title] = body
    return sections
def format_issue_markdown(issue: dict[str, Any]) -> str:
    number = issue.get("number") or issue.get("id")
    title = issue.get("title", "").strip()
    state = issue.get("state", "")
    labels = issue.get("labels") or []
    if labels and isinstance(labels[0], dict):
        label_names = sorted(lb.get("name", "") for lb in labels if lb.get("name"))
    else:
        label_names = sorted(str(lb) for lb in labels)
    body = (issue.get("body") or "").strip()
    lines = [f"# Issue #{number}: {title}"]
    if state:
        lines.append(f"**State:** {state}")
    if label_names:
        lines.append(f"**Labels:** {', '.join(label_names)}")
    lines.append("")
    lines.append(body if body else "_No description._")
    handoff = extract_handoff_sections(body)
    if handoff:
        lines.extend(["", "## Handoff sections", ""])
        for heading, content in handoff.items():
            lines.extend([f"### {heading}", "", content, ""])
    return "\n".join(lines) + "\n"
