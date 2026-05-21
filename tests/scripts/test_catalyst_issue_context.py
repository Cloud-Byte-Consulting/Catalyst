from __future__ import annotations
import json, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
FIXTURE_ISSUE = Path(__file__).parent / "fixtures" / "sample_issue.json"
FIXTURE_LIST = Path(__file__).parent / "fixtures" / "sample_issues_list.json"
sys.path.insert(0, str(SCRIPTS))
from lib.catalyst_domains import build_gh_issue_query, extract_handoff_sections, format_issue_markdown
def test_extract_handoff_sections():
    issue = json.loads(FIXTURE_ISSUE.read_text(encoding="utf-8"))
    sections = extract_handoff_sections(issue["body"])
    assert "Context" in sections and "Next" in sections
def test_build_gh_issue_query_labels():
    q = build_gh_issue_query(kind="iac", state="agent-working")
    assert "kind/iac" in q["labels"] and "state/agent-working" in q["labels"]
def test_format_issue_markdown():
    issue = json.loads(FIXTURE_ISSUE.read_text(encoding="utf-8"))
    md = format_issue_markdown(issue)
    assert "# Issue #42" in md
    assert "### Decision" in md
    assert "### Rationale" not in md or "### Decision" in md
def test_issue_context_fixture_export():
    proc = subprocess.run([sys.executable, str(SCRIPTS / "catalyst-issue-context.py"),
        "--issue", "42", "--fixture", str(FIXTURE_ISSUE)], cwd=ROOT, check=True, capture_output=True, text=True)
    payload = json.loads(proc.stdout)
    assert payload["issue"]["number"] == 42
    assert payload["handoff"]["body"]["Context"].startswith("Prior")
def test_issue_list_fixture():
    proc = subprocess.run([sys.executable, str(SCRIPTS / "catalyst-issue-context.py"),
        "--kind", "iac", "--fixture", str(FIXTURE_LIST)], cwd=ROOT, check=True, capture_output=True, text=True)
    assert len(json.loads(proc.stdout)["issues"]) == 2


def test_issue_list_labels_markdown():
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "catalyst-issue-context.py"),
            "--labels",
            "kind/iac",
            "--fixture",
            str(FIXTURE_LIST),
            "--limit",
            "5",
            "--markdown",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "# Issues" in proc.stdout
    assert "#" in proc.stdout
