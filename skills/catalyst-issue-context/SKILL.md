---
name: catalyst-issue-context
description: >-
  Export GitHub Issue body, labels, and handoff sections; list issues by kind/*.
  Use before persona routing (ADR-024).
---

# Catalyst issue context

```bash
python3 scripts/catalyst-issue-context.py --issue 306
python3 scripts/catalyst-issue-context.py --kind iac --state agent-working
python3 scripts/catalyst-issue-context.py --issue 42 --fixture tests/scripts/fixtures/sample_issue.json
python3 scripts/catalyst-ask.py "Terraform module fails Checkov"
```

Registry: `registry/catalyst-domains.yaml`. Then use `skills/catalyst-agent-routing`.
