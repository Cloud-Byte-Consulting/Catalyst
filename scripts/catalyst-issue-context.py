#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path
_SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS))
from lib.catalyst_domains import build_gh_issue_query, extract_handoff_sections, format_issue_markdown, load_registry
def _run_gh(args):
    proc = subprocess.run(["gh", *args], capture_output=True, text=True)
    if proc.returncode:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "gh failed")
    return json.loads(proc.stdout or "null")
def export_issue(number, repo, fixture):
    issue = json.loads(fixture.read_text(encoding="utf-8")) if fixture else _run_gh([
        "issue","view",str(number),"--repo",repo,
        "--json","number,title,body,state,labels,comments"])
    body = issue.get("body") or ""
    ch = {}
    for c in issue.get("comments") or []:
        cid = str(c.get("id") or c.get("author",{}).get("login") or "comment")
        s = extract_handoff_sections(c.get("body") or "")
        if s: ch[cid] = s
    return {"issue": issue, "markdown": format_issue_markdown(issue),
            "handoff": {"body": extract_handoff_sections(body), "comments": ch}}
def export_by_labels(kind, state, type_label, repo, registry_path, fixture, limit):
    reg = load_registry(registry_path)
    q = build_gh_issue_query(kind=kind, state=state, type_label=type_label, registry=reg, repo=repo)
    issues = json.loads(fixture.read_text(encoding="utf-8")) if fixture else _run_gh(q["gh_args"] + ["--limit", str(limit)])
    return {"query": q, "issues": issues}
def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--issue", type=int)
    p.add_argument("--kind", help="Short kind key (e.g. iac) or full label kind/iac.")
    p.add_argument("--labels", action="append", default=[], help="Full GitHub label(s), e.g. kind/ai-workflow.")
    p.add_argument("--state")
    p.add_argument("--type", dest="type_label")
    p.add_argument("--repo", default="Cloud-Byte-Consulting/Catalyst")
    p.add_argument("--registry", type=Path)
    p.add_argument("--fixture", type=Path)
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--markdown", action="store_true", help="Print markdown instead of JSON.")
    a = p.parse_args(argv)
    kind = a.kind
    if not kind and a.labels:
        for label in a.labels:
            if label.startswith("kind/"):
                kind = label.split("/", 1)[1]
                break
    if a.issue is not None:
        payload = export_issue(a.issue, a.repo, a.fixture)
        if a.markdown:
            sys.stdout.write(payload["markdown"])
            sys.stdout.write("\n")
            return 0
    elif kind or a.state or a.type_label:
        payload = export_by_labels(kind, a.state, a.type_label, a.repo, a.registry, a.fixture, a.limit)
        if a.markdown:
            lines = [f"# Issues ({len(payload['issues'])})", ""]
            for issue in payload["issues"]:
                lines.append(f"- **#{issue.get('number')}** {issue.get('title', '')} (`{issue.get('state', '')}`)")
            sys.stdout.write("\n".join(lines) + "\n")
            return 0
    else:
        p.error("provide --issue, --labels, or --kind/--state/--type")
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
