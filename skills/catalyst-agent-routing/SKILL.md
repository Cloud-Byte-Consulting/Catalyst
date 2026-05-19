---
name: catalyst-agent-routing
description: Auto-route Catalyst sessions to the right persona by topic match. Use whenever the user mentions Terraform, OPA, Checkov, Score, AWS, security, IAM, encryption, container hardening, secret scanning, CI/CD, or PR review.
---


# Catalyst persona routing

Catalyst's `agents/` directory holds a small set of specialised personas vendored from `BittahCriminal/platform-catalyst` (BSD-3-Clause) and adapted per the 16 locked decisions in `docs/research/platform-catalyst-agents-evaluation.md`. This rule helps you pick the right one when a request maps to a single rubric area.

## Routing table

| When the user is asking about… | Invoke / cite |
|---|---|
| Terraform modules, `.tftest.hcl`, IAM policy authoring, KMS, ECS Fargate / Lambda / S3 / DynamoDB / Aurora / Bedrock HCL, OIDC trust, `terraform fmt` discipline | `agents/terraform-engineer.md` |
| Checkov gate failures, finding triage (`must-fix` / `risk-accepted` / `false-positive`), suppression policy, custom Checkov checks | `agents/checkov-expert.md` |
| OPA / Rego, Conftest in CI, `state_machine.rego` for ADR-001 transitions, bundle/discovery troubleshooting, `opa eval --explain` | `agents/opa-expert.md` |
| AWS-native code generation (templates for ECS Fargate, OIDC workflows, container scanning, static-egress VPC, golden-path docs) and the `aws-platform-engineering` MCP wrapper | `agents/aws-platform-engineer.md` |
| Secret scanning, secrets rotation contracts, container hardening, network segmentation, AI threat modelling, GitHub MCP `secret_protection` toolset | `agents/security-hardener.md` |
| FastAPI control plane, Lambda handlers, async orchestration (SQS/EventBridge/Step Functions), multi-tenant patterns, GitHub Issues state machine enforcement | `agents/automation-architect.md` |
| GitHub Actions OIDC, policy-as-code gates, blue/green ECS deploys, Lambda canary, CloudWatch alarms, SLO burn-rate, Andon dashboard, runbook procedures | `agents/cicd-operator.md` |
| Bedrock Claude multi-agent PR reviewer pipeline, Converse API integration, prompt engineering for code review, pydantic output validation, EMF metrics for AI calls, AI threat-modelling | `agents/ai-reviewer-architect.md` |
| Score (score.dev) workload specs, `score.yaml` validation against pinned `../spec/`, translating Score + construct address into Terraform variable maps, portability boundary statements | `agents/score-expert.md` |
| IDP / operating-model strategy, golden paths, service catalog governance, paved-road decisions, cross-cutting platform-as-product framing — plus the merged docs-communicator scope: README clarity, MADR ADRs, draw.io diagrams, RUNBOOK procedures, Kaizen Issues, interview-ready trade-off narratives. Complements `aws-platform-engineer` (AWS implementation detail) and `security-hardener` (security posture) per decision #2's three-persona AWS split. | `agents/platform-engineering-architect.md` |

> All planned import-phase personas and overlays have now landed (`terraform-engineer`, `checkov-expert`, `opa-expert`, `aws-platform-engineer`, `security-hardener`, `automation-architect`, `cicd-operator`, `ai-reviewer-architect`, `score-expert`, `platform-engineering-architect`). Keep this table additive — never remove a row, only add.

## Routing protocol

1. **Single-area request** — pick the one persona above whose row matches and read its file with the Read tool before composing the answer. The persona file is the system prompt for that part of the work.
2. **Cross-cutting request** — name the personas you are coordinating (typically architect → terraform → security/CI/CD), and follow their **adjacent experts** sections to chain.
3. **No persona match** — fall back to default Cursor behaviour and `AGENTS.md`. Do not invent a persona.
4. **Long-context artifact** — every persona inherits the RLM bullet from decision #16. If the artifact you need to read exceeds ~50k chars, follow `.cursor/rules/rlm-workflow.mdc` first and let the persona consume the RLM summary instead of the raw blob.
5. **Construct address** — every change carries the `tenant/env/lz/project/app` address from `docs/ADR/ADR-002-construct-hierarchy.md` as labels, tags, alarm names, EMF dimensions.
6. **State machine** — every action that creates or transitions an Issue follows `docs/ADR/ADR-001-github-issues-as-state-machine.md` and `docs/ADR/STATE-MACHINE.md` (allowed `state/*` transitions, comment headings, audit shape).
7. **Intent-judge** — `intent-judge` is **not** a persona file under `agents/`. It is a rule + MCP shim pair (`.cursor/rules/intent-judge.mdc` + `.cursor/skills/intent-judge-shim/intent_judge_mcp_server.py`, registered in `.cursor/mcp.json` as the `intent-judge` server). The rule activates automatically on high-risk tool calls (writes, deletes, deploys, secret ops, broad-scope automation) and returns `allow` / `deny` / `clarify` via the `validate_intent` MCP tool; `deny` and `clarify` halt and transition the issue to `state/blocked-on-human` per ADR-001. Per decision #3, the upstream `plugins/catalyst-judge/` package is intentionally not vendored.

## Anti-patterns

- Do **not** load multiple persona files at once when one suffices — the persona files are independent system prompts. Pick one and chain via "adjacent experts" only when truly needed.
- Do **not** invent a new persona file inline; if a routing gap exists, open a `type/kaizen` issue under milestone #5 (Communication and Documentation) so a future phase can land it.
- Do **not** drop or reword the `Vendored from` line in any persona file — it is the BSD-3-Clause attribution shape per decision #9.

## Provenance

Personas were imported in phased PRs against `release` per the import plan in `docs/plans/platform-catalyst-import-plan.md`:

- Phase 1 (`rc/import-pc-phase-1-terraform`): `terraform-engineer`, `checkov-expert`, `opa-expert` + 7 skills + this rule.
- Phase 2 (`rc/import-pc-phase-2-automation`): `automation-architect`, `cicd-operator` (+ overlay onto pre-existing `security-hardener`).
- Phase 3 (`rc/import-pc-phase-3-ai-review`): `ai-reviewer-architect`, `score-expert`, separate Bedrock MCP server.
- Phase 4 (`rc/import-pc-phase-4-architect`): `platform-engineering-architect` (with `docs-communicator` responsibilities merged in per decision #7).

`intent-judge` lands as a Cursor rule + ~80-line MCP shim on `rc/intent-judge-shim` per decision #3 (the upstream `plugins/catalyst-judge/` package is intentionally not vendored).
