from __future__ import annotations
import json, subprocess, sys
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
from lib.catalyst_domains import classify_question, load_registry
GOLDEN = [
    ("terraform module fails checkov CKV_AWS_20", "iac", "terraform-engineer"),
    ("github actions oidc deploy workflow", "cicd", "cicd-operator"),
    ("fastapi control plane lambda handler", "service", "automation-architect"),
    ("bedrock converse api pr review pipeline", "ai-workflow", "ai-reviewer-architect"),
    ("secret scanning and container hardening", "security", "security-hardener"),
    ("write a MADR ADR for bootstrap", "docs", "platform-engineering-architect"),
    ("score.yaml validation portability", "score", "score-expert"),
    ("golden path IDP service catalog", "platform", "platform-engineering-architect"),
    ("umbrella epic parent issue rollup", "umbrella", "platform-engineering-architect"),
    ("checkov gate failure triage", "iac", "terraform-engineer"),
]
@pytest.mark.parametrize("question,kind,persona", GOLDEN)
def test_classify_question_golden(question, kind, persona):
    out = classify_question(question, load_registry())
    assert out["kind"] == kind
    assert persona in out["personas"]
    assert out["confidence"] >= 0.6
    assert out.get("suggested_gh_query", "").startswith("gh issue list")


def test_checkov_question_meets_ac_threshold():
    out = classify_question("fix Checkov CKV_AWS on ecs module", load_registry())
    assert out["kind"] == "iac"
    assert "checkov-expert" in out["personas"]
    assert "terraform-engineer" in out["personas"]
    assert out["confidence"] >= 0.7
def test_catalyst_ask_cli_json():
    proc = subprocess.run([sys.executable, str(SCRIPTS / "catalyst-ask.py"), "opa eval state_machine.rego"],
                          cwd=ROOT, check=True, capture_output=True, text=True)
    payload = json.loads(proc.stdout)
    assert payload["kind"] == "iac"
    assert payload["method"] == "keyword_kind"
