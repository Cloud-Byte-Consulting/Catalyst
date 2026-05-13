# Catalyst



Catalyst is an Internal Developer Platform (IDP) that automates the work platform engineersdo every day at a retail pharmacy and insurance provider: blue/green deployments, secrets management, GitHub-driven workflows, and operational intelligence. It is delivered as one coherent product on AWS, framed as a Toyota production line — every PR is a car body moving down the line, every gate is a proving check, every alarm is an andon cord.


## How Catalyst is built (the Honda way)

Toyota and Honda solved "produce correct outputs at scale, reliably, without
a human in every loop" for physical goods over fifty years. The principles
they evolved transfer almost directly to platform engineering — what changes
is the unit of production (a pull request instead of a car door) and the
medium (Terraform plans and tool calls instead of sheet metal). Catalyst
encodes those principles into specific files and features:

| TPS / Honda principle | Catalyst artefact | Mechanism |
|---|---|---|
| **Jidoka** (stop the line on defect) | `.github/workflows/tf-plan.yml`, `tf-apply.yml`; AI reviewer verdict `block` | Branch protection requires green AI verdict + plan-apply approval. No override. |
| **Andon** (visible defect signal) | PR labels `agent-working` / `blocked-on-human` / `policy-fail`; SNS topic `catalyst-deploy-summary`; CloudWatch dashboard `Catalyst-Andon` | Status visible from the PR list. SNS fans out to Slack `#catalyst-line`. |
| **JIT / Pull** (only what's needed when needed) | `modules/composite/preview-env`, torn down on PR close; `ops-intel` on EventBridge cron, not poll loops | Resources exist only while a PR is open; ops scans run on schedule. |
| **Heijunka** (level the workload) | `services/ai-pr-reviewer/dispatcher.py` rank-parallel `Semaphore(4)`; CI matrix; API GW usage plan throttle | Smooths Bedrock token bursts, prevents 429 cascades. |
| **Kaizen** (small continuous improvement, measured) | GitHub Issues [**`type/kaizen`**](https://github.com/BittahCriminal/platform-catalyst/issues?q=is%3Aissue+label%3Atype%2Fkaizen) (template); [`KAIZEN.md`](./KAIZEN.md) format + archive; `metrics/ci_duration.json` | CI p50 duration tracked as leading indicator. |
| **Poka-yoke** (mistake-proofing) | `.pre-commit-config.yaml` (tflint, tfsec, Checkov, gitleaks); `infrastructure/policy/opa/*.rego` via Conftest | Mistakes can't reach `main`. |
| **Muda** (eliminate waste) | Bedrock prompt-caching enabled; single ECR image promoted across envs; shared TF modules | Build once, deploy many. |
| **Standardised work** | [`.github/PULL_REQUEST_TEMPLATE.md`](./.github/pull_request_template.md), [`docs/adr/template.md`](./docs/adr/template.md) | Every PR / ADR follows a known shape. |
| **Genchi Genbutsu** (go and see) | Structured JSON logs capture real request shape; `ops-intel` queries real AWS APIs (Cost Explorer, Trusted Advisor) | Decisions made from primary sources. |
| **Hansei** (honest reflection) | [`docs/POST-MORTEM-TEMPLATE.md`](./docs/POST-MORTEM-TEMPLATE.md); the open PR `#42 — self-correction` | Reflection is shipped, not hidden. |
