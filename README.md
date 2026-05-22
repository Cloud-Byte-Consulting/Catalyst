# Catalyst

**An AWS-native Internal Developer Platform delivered by coding agents.** The repo is the platform, GitHub Issues are its state machine, and Cursor / Claude Code / Gemini CLI agents are the primary contributors. Humans review, approve, and unblock.

| | |
|---|---|
| **Operating contract** | [`AGENTS.md`](./AGENTS.md) |
| **Agent onboarding** | [`docs/AGENT-GETTING-STARTED.md`](./docs/AGENT-GETTING-STARTED.md) |
| **AWS operator onboarding** | [`docs/onboarding/`](./docs/onboarding/) (Platform / Organization / Application tracks) |
| **Workflow board** | [Catalyst Progress / Andon](https://github.com/orgs/Cloud-Byte-Consulting/projects/3) (Project #3) |

## What is this?

Catalyst is an **Internal Developer Platform (IDP) control plane for AWS**: deployable Terraform modules, a FastAPI control-plane service (`services/catalyst-api/`), a Knack CLI (`clients/catalyst-cli/`), CI/CD pipelines, and the agent-system itself. It is also an **AI-native delivery model** ([ADR-011](./docs/ADR/ADR-011-catalyst-agentic-workflow.md)): instead of humans driving a portal or a Terraform repo by hand, **agents pick up tracked issues and execute against a Gherkin acceptance contract**.

Three properties make this work:

- **GitHub Issues are the durable state machine.** Every unit of work is a labelled issue. The legal `state/*` transitions and the rest of the label vocabulary live in [`docs/ADR/STATE-MACHINE.md`](./docs/ADR/STATE-MACHINE.md); the rationale is [ADR-001](./docs/ADR/ADR-001-github-issues-as-state-machine.md).
- **One operating contract, three tools.** `AGENTS.md` is the shared contract for Cursor, Claude Code, and Gemini CLI. Canonical `skills/` and `agents/` trees are wired into each tool's directory by `python platform/bootstrap.py` ([ADR-024](./docs/ADR/ADR-024-unified-agent-config-and-issue-indexing.md), [ADR-022](./docs/ADR/ADR-022-multi-tool-skill-layout.md)).
- **AWS work is OIDC-only.** No long-lived AWS keys live in CI, secrets, or developer laptops. Plan, apply, deploy, and drift all use distinct GitHub OIDC roles ([ADR-005](./docs/ADR/ADR-005-aws-agentic-platform-engineering.md), [ADR-006](./docs/ADR/ADR-006-cicd-pipeline-architecture.md)).

## Quick start (engineers)

```bash
git clone https://github.com/Cloud-Byte-Consulting/Catalyst.git
cd Catalyst
git checkout release
python platform/bootstrap.py          # wire .cursor/, .claude/, .gemini/ to canonical skills/ + agents/
python platform/bootstrap.py --check  # verify (CI runs this; exits 1 on drift)
```

Then follow [`docs/AGENT-GETTING-STARTED.md`](./docs/AGENT-GETTING-STARTED.md) for the **clone → IDE → AGENTS.md → first issue** path. Per-IDE specifics (rules, hooks, MCP wiring) live in [`docs/multi-tool-config.md`](./docs/multi-tool-config.md).

| IDE | Entry file | Generated MCP config |
|---|---|---|
| **Cursor** | [`AGENTS.md`](./AGENTS.md) | `.cursor/mcp.json` |
| **Claude Code** | [`CLAUDE.md`](./CLAUDE.md) + [`AGENTS.md`](./AGENTS.md) | `.mcp.json` |
| **Gemini CLI** | [`GEMINI.md`](./GEMINI.md) + [`AGENTS.md`](./AGENTS.md) | `.gemini/settings.json` |

**Picking a first issue.** Browse `state/pending` work with no `kind/umbrella`:

```bash
gh issue list --label "state/pending" --label "type/kaizen" --search "no:assignee"
gh issue list --label "state/pending" --label "kind/docs"
```

The full label vocabulary and what each `kind/*` routes to is in [`docs/ADR/STATE-MACHINE.md`](./docs/ADR/STATE-MACHINE.md) §2.7.

## Repo layout

| Path | What lives here |
|---|---|
| `AGENTS.md`, `CLAUDE.md`, `GEMINI.md` | Operating contract (shared) + tool-specific entry stubs |
| `agents/` | Canonical persona system prompts (`terraform-engineer`, `checkov-expert`, `security-hardener`, `cicd-operator`, etc.) |
| `skills/` | Canonical agent skills, including [`catalyst-agent-routing`](./skills/catalyst-agent-routing/SKILL.md) and [`catalyst-issue-context`](./skills/catalyst-issue-context/SKILL.md) |
| `platform/` | Bootstrap (`bootstrap.py`), MCP registry (`mcp.servers.json`), persona dispatch metadata — see [`platform/README.md`](./platform/README.md) |
| `services/catalyst-api/` | FastAPI control plane (Tier 1/2 golden paths, product catalogue, inventory, deployment history) |
| `clients/catalyst-cli/` | Knack-based CLI for the API |
| `infrastructure/` | Terraform root + modules (network, IAM, runtime, KMS, ECR, ECS, Lambda, Aurora) |
| `.github/workflows/` | CI/CD pipelines — see [`.github/workflows/README.md`](./.github/workflows/README.md) |
| `docs/ADR/` | Accepted architectural decisions (start at [ADR-001](./docs/ADR/ADR-001-github-issues-as-state-machine.md)) |
| `docs/onboarding/` | AWS operator runbooks (Platform / Organization / Application) per [ADR-012](./docs/ADR/ADR-012-onboarding-experience.md) |
| `diagrams/` | Architecture diagrams (Mermaid + Draw.io) — index at [`diagrams/README.md`](./diagrams/README.md) |
| `registry/` | `catalyst-domains.yaml` and other machine-queryable indexes for agent routing |

## How agents work here

`AGENTS.md` is the operating contract, shared across Cursor, Claude Code, and Gemini CLI. The contract is six in-session gates ([ADR-011](./docs/ADR/ADR-011-catalyst-agentic-workflow.md)) layered on top of the unified agent config ([ADR-024](./docs/ADR/ADR-024-unified-agent-config-and-issue-indexing.md)):

1. **Model decision logging** — before implementation and at every material architecture, security, deploy, or scope decision, post an `### Agent Decision Log` comment on the tracking issue (model selected, fallback known, rationale, next).
2. **RLM trigger at ~50k chars** — long artifacts (diffs, terraform plans, CloudWatch exports, codebase reads spanning >10 files) route through the recursive language model scaffold ([ADR-004](./docs/ADR/ADR-004-rlm-for-long-context-agent-tasks.md)) before inline reading.
3. **AWS OIDC only** — no long-lived AWS keys anywhere; plan/apply/deploy/drift use distinct GitHub OIDC roles ([ADR-006](./docs/ADR/ADR-006-cicd-pipeline-architecture.md)), enforced by `validate_workflows.py`.
4. **Container security gate** — Trivy (or Scout) HIGH/CRITICAL gate, SPDX 2.3 + CycloneDX 1.5 SBOMs, SARIF upload to GitHub code scanning on every PR touching a Dockerfile or image.
5. **Pre-PR peer review (mandatory)** — before `gh pr create`, spawn a peer-review sub-agent that checks correctness vs Gherkin AC, ADR compliance, security, coverage (`--cov-fail-under=85` minimum), and naming. Every suggestion is recorded on the tracking issue as ACCEPT or REJECT with a one-line rationale.
6. **GitHub MCP secret scanning** — `secret_protection` toolset invoked on any PR adding files or credentials before posting the `pr_merged=true` done gate.

Beyond the gates, day-1 agent work also follows the **PR-open contract**: every PR MUST contain `Closes #<N>` AND be added to the Catalyst Progress project (#3) via `gh project item-add 3 --owner Cloud-Byte-Consulting --url <pr-url>`. Agents refuse to call `gh pr create` if either check would fail — see [`skills/pr-open-contract/SKILL.md`](./skills/pr-open-contract/SKILL.md).

Issue body shape, comment headings, and dependency handling are spelled out in [`docs/issue-execution-gherkin-workflow-2026-05-13.md`](./docs/issue-execution-gherkin-workflow-2026-05-13.md). Persona routing per topic is in [`skills/catalyst-agent-routing/SKILL.md`](./skills/catalyst-agent-routing/SKILL.md). Evidence the contract is followed in practice: [`docs/ai-workflow-narrative.md`](./docs/ai-workflow-narrative.md).

**What still needs humans.** PR merges (branch protection on `release`), any issue in `state/blocked-on-human`, the one-time AWS account bootstrap, and any agent action the `intent-judge` rule flags as `clarify` or `deny`.

## Day-to-day workflows

### Pick up an issue

```bash
gh issue view 331 --json title,body,labels
python3 scripts/catalyst-issue-context.py --issue 331    # Gherkin AC + handoff summary
# Read skills/catalyst-agent-routing/SKILL.md, pick agents/<persona>.md, load it
```

Free-form work without an existing issue: `python3 scripts/catalyst-ask.py "<task>"` to find the right domain in `registry/catalyst-domains.yaml`, then open an issue with the correct `kind/*` and construct-address labels.

### Open a PR

1. Implement against the Gherkin AC on the tracking issue.
2. Run the pre-PR peer review sub-agent (gate 5).
3. `gh pr create` with `Closes #<N>` in the body.
4. `gh project item-add 3 --owner Cloud-Byte-Consulting --url <pr-url>` (requires `read:project` scope on the gh token — `gh auth refresh -s read:project` if missing).
5. `gh pr view --json projectItems` to confirm the project assignment took.

### Run things locally

```bash
# Terraform sanity (no AWS calls)
terraform -chdir=infrastructure init -backend=false
terraform -chdir=infrastructure fmt -recursive -check
terraform -chdir=infrastructure validate
terraform -chdir=infrastructure test

# API service (coverage gate 93.83%)
pip install -r services/catalyst-api/requirements-dev.txt
pytest services/catalyst-api/tests --cov=services/catalyst-api/catalyst --cov-branch --cov-fail-under=93.83

# CLI client (coverage gate 80%; live tests opt-in via -m live)
pip install -r clients/catalyst-cli/requirements-dev.txt
pytest clients/catalyst-cli/tests -m 'not live' --cov=catalyst_cli --cov-branch --cov-fail-under=80
```

API smoke against a deployed Catalyst ALB lives in [`docs/smoke-tests.md`](./docs/smoke-tests.md). Full CI inventory is in [`.github/workflows/README.md`](./.github/workflows/README.md).

## Key docs

| Doc | What it covers |
|---|---|
| [ADR-001 — Issues as state machine](./docs/ADR/ADR-001-github-issues-as-state-machine.md) | Why GitHub Issues are the durable state machine and comments are the audit trail |
| [ADR-002 — Construct hierarchy](./docs/ADR/ADR-002-construct-hierarchy.md) | The five-level Tenant → Environment → LandingZone → Project → Application model and its label/tag mapping |
| [ADR-005 — AWS agentic platform engineering](./docs/ADR/ADR-005-aws-agentic-platform-engineering.md) | OIDC-only AWS, Trivy/SBOM/SARIF gates, `knack` CLI + `pytest`/`moto` test conventions |
| [ADR-011 — Catalyst agentic workflow](./docs/ADR/ADR-011-catalyst-agentic-workflow.md) | The six-gate operating contract (`AGENTS.md` is the implementation) |
| [ADR-012 — Onboarding experience](./docs/ADR/ADR-012-onboarding-experience.md) | The three AWS-operator onboarding tracks under `docs/onboarding/` |
| [ADR-022 — Multi-tool skill layout](./docs/ADR/ADR-022-multi-tool-skill-layout.md) | Canonical `skills/` and `agents/` paths shared across tools |
| [ADR-024 — Unified agent config + issue indexing](./docs/ADR/ADR-024-unified-agent-config-and-issue-indexing.md) | Bootstrap-generated tool trees and the `kind/*` label index |
| [`docs/ADR/STATE-MACHINE.md`](./docs/ADR/STATE-MACHINE.md) | Authoritative label vocabulary, legal transitions, kind/* routing table |
| [`docs/issue-execution-gherkin-workflow-2026-05-13.md`](./docs/issue-execution-gherkin-workflow-2026-05-13.md) | Issue body shape, Gherkin AC, comment headings |
| [`docs/multi-tool-config.md`](./docs/multi-tool-config.md) | Per-IDE wiring (Cursor rules, Claude adapters, Gemini settings, MCP) |
| [`docs/ai-workflow-narrative.md`](./docs/ai-workflow-narrative.md) | Evidence trail for the contract — real PRs, decision logs, peer-review threads |

The full index is `docs/ADR/` (24 ADRs accepted as of `release`). `DECISIONS.md` is a pointer back to it.

## AWS onboarding tracks

For **AWS platform operators** (not agent contributors), pick the audience-sliced track that matches your role ([ADR-012](./docs/ADR/ADR-012-onboarding-experience.md)):

| Track | Audience | Runbook | Outcome |
|---|---|---|---|
| **A — Platform** | Cloud / platform engineering | [`docs/onboarding/platform.md`](./docs/onboarding/platform.md) | Fresh AWS account ready for GitOps; Catalyst API reachable |
| **B — Organization** | Team / lab leaders (Owners) | [`docs/onboarding/organization.md`](./docs/onboarding/organization.md) | Tenant hierarchy registered (OUs, landing zones, environments) |
| **C — Application** | Application teams (Administrators) | [`docs/onboarding/application.md`](./docs/onboarding/application.md) | App onboarded onto an existing tenant via `POST /services/onboard` |

Index and cross-track sequencing: [`docs/onboarding/README.md`](./docs/onboarding/README.md). Day-0 canonical sequence: [`docs/operator-bootstrap.md`](./docs/operator-bootstrap.md). The `Catalyst` GitHub Actions environment variables and secrets are in [`.github/workflows/README.md`](./.github/workflows/README.md).

## Architecture

Seven diagrams, indexed at **[`diagrams/README.md`](./diagrams/README.md)**.

GitHub-inline (Mermaid):

- [`diagrams/control-plane.md`](./diagrams/control-plane.md) — request path (caller → ALB → Lambda → DynamoDB/SSM/STS), provisioning tiers, phase ordering enforced by `terraform.yml` + `service-cd.yml`
- [`diagrams/ha.md`](./diagrams/ha.md) — multi-AZ ECS topology with Aurora Serverless v2, NAT redundancy, failure-mode coverage
- [`diagrams/gitops.md`](./diagrams/gitops.md) — PR → plan → review → apply → deploy → andon flow with OIDC role separation

Draw.io (open in IDE plugin or app.diagrams.net):

- [`diagrams/network-layer.drawio`](./diagrams/network-layer.drawio) — VPC, subnets, NAT, IGW, VPC endpoints, security groups
- [`diagrams/application-layer.drawio`](./diagrams/application-layer.drawio) — request path, persistence, SigV4 RBAC, ECS Fargate runtime
- [`diagrams/agentic-workflow.drawio`](./diagrams/agentic-workflow.drawio) — six gates, Issues state machine, peer-review fork, OIDC per phase
- [`diagrams/cicd-pipeline.drawio`](./diagrams/cicd-pipeline.drawio) — all nine GitHub Actions workflows, gates, OIDC roles, outcomes

Authoring conventions: [`skills/draw-aws-diagrams/SKILL.md`](./skills/draw-aws-diagrams/SKILL.md).

## Deploy

Catalyst splits provisioning into two tiers; the GitHub Actions pipeline is the single source of truth for everything outside the one-time bootstrap. Full table in [`.github/workflows/README.md`](./.github/workflows/README.md).

| Tier | Owns | How |
|---|---|---|
| Bootstrap (one-time) | IAM bootstrap-admin role, GitHub OIDC provider, `catalyst-github-{plan,apply,deploy}` roles, RBAC IAM groups, Terraform state S3 bucket, Terraform DynamoDB lock, Catalyst API data S3 bucket | `scripts/bootstrap-aws-account.sh` |
| Pipeline (ongoing) | VPC + subnets + NAT + endpoints, security groups, ECR, ECS cluster + ALB + target group, Lambda runtime, DynamoDB platform-state table, KMS CMKs ([ADR-016](./docs/ADR/ADR-016-cmk-key-strategy.md)), Aurora Serverless v2 ([ADR-019](./docs/ADR/ADR-019-aurora-serverless-iam-auth.md)), optional Network Firewall | `terraform.yml` (PR plan + release apply) → `tf-drift.yml` (daily) |
| Service deploy | Catalyst API container image build/push + runtime update (Lambda or ECS via `RUNTIME` knob — [ADR-009](./docs/ADR/ADR-009-runtime-strategy.md)) | `service-cd.yml` |

Self-deploy on top of Catalyst itself: `catalyst products deploy catalyst-api --construct <addr>` ([`docs/products.md`](./docs/products.md), [#103](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/103)).

After teardown or to trigger teardown on demand (demo env auto-destructs nightly at 22:00 UTC Mon–Fri via `teardown-scheduled.yml`): [`docs/teardown.md`](./docs/teardown.md).

## Runtime configuration

Resolution order per setting: explicit env var → SSM parameter (`CATALYST_*_PARAMETER`) → Secrets Manager secret (`CATALYST_*_SECRET`) → built-in default.

| Setting | Env var | Default | Notes |
|---|---|---|---|
| Repository backend | `CATALYST_REPOSITORY` | `memory` | Set to `dynamodb` in production. |
| DynamoDB table name | `CATALYST_DYNAMODB_TABLE` or `CATALYST_DYNAMODB_TABLE_PARAMETER` | resolved from SSM in prod | Module: `infrastructure/modules/dynamodb`. |
| Auth mode | `CATALYST_AUTH_MODE` | `headers` | `sigv4` enforces presigned-STS verification + `iam:ListGroupsForUser`. |
| Group cache TTL | `CATALYST_GROUP_CACHE_TTL` | `300` (seconds) | Per-process IAM group cache. |
| Runtime secrets | `CATALYST_RUNTIME_SECRET_<KEY>_SECRET` | unset | Names a Secrets Manager secret for `<KEY>`. |
| API ingress allowlist | `CATALYST_API_INGRESS_ALLOWLIST` | `["73.239.59.22"]` | JSON array; plain IPv4 entries normalized to `/32`, passed as `TF_VAR_alb_ingress_allowlist`. |

Scoped RBAC groups use `catalyst-{tenant}--{project}--{role}`. Migration notes: [`docs/migrations/2026-05-15-rbac-scoped-group-delimiter.md`](./docs/migrations/2026-05-15-rbac-scoped-group-delimiter.md).

## Getting help

- **Tracking work / status**: [Catalyst issues](https://github.com/Cloud-Byte-Consulting/Catalyst/issues) and the [Catalyst Progress / Andon board (Project #3)](https://github.com/orgs/Cloud-Byte-Consulting/projects/3). Viewing project items via `gh project` requires the `read:project` scope on your gh token (`gh auth refresh -s read:project` once).
- **Issue context for an agent session**: [`skills/catalyst-issue-context/SKILL.md`](./skills/catalyst-issue-context/SKILL.md) — `python3 scripts/catalyst-issue-context.py --issue <N>` exports labels, Gherkin AC, and handoff comments.
- **Agent routing questions** ("which persona owns this?"): [`skills/catalyst-agent-routing/SKILL.md`](./skills/catalyst-agent-routing/SKILL.md) — topic-to-persona table.
- **Specific personas**: see `agents/<name>.md` (e.g. [`agents/terraform-engineer.md`](./agents/terraform-engineer.md), [`agents/checkov-expert.md`](./agents/checkov-expert.md), [`agents/security-hardener.md`](./agents/security-hardener.md), [`agents/cicd-operator.md`](./agents/cicd-operator.md), [`agents/platform-engineering-architect.md`](./agents/platform-engineering-architect.md)).
- **Stuck on a gate / refusal**: when an agent posts a `state/blocked-on-human` comment, the comment is the handoff. Read it, decide, then re-label `state/agent-working` (rules in [`docs/ADR/STATE-MACHINE.md`](./docs/ADR/STATE-MACHINE.md) §3).
- **File a kaizen issue** (improvement to docs, gates, contracts, or tooling): open with labels `type/kaizen` · `kind/<domain>` · `tenant/catalyst` · `env/shared` · `lz/shared` · `project/platform` · `app/kaizen` · `state/pending`. The kind/docs default routes to `platform-engineering-architect`; other `kind/*` values route per the [STATE-MACHINE.md §2.7 table](./docs/ADR/STATE-MACHINE.md).
- **Maintainers**: no `CODEOWNERS` or `CONTRIBUTING.md` on `release` yet — opening a kaizen issue is the canonical way to flag both content and policy gaps.

## Contributing

1. Run `python platform/bootstrap.py` after clone or whenever `skills/` / `agents/` change ([ADR-024](./docs/ADR/ADR-024-unified-agent-config-and-issue-indexing.md)).
2. Read [`AGENTS.md`](./AGENTS.md) — it is the operating contract for every tool (Cursor, Claude Code, Gemini CLI).
3. Work an issue per [`docs/issue-execution-gherkin-workflow-2026-05-13.md`](./docs/issue-execution-gherkin-workflow-2026-05-13.md): Context / Scope / Gherkin AC + structured handoff comments.
4. Run the pre-PR peer-review sub-agent (gate 5) before `gh pr create`.
5. Honour the PR-open contract: `Closes #<N>` in the body and `gh project item-add 3 --owner Cloud-Byte-Consulting --url <pr-url>` immediately after PR creation. See [`skills/pr-open-contract/SKILL.md`](./skills/pr-open-contract/SKILL.md).

## License

[BSD 3-Clause](./LICENSE). Security policy: [`SECURITY.md`](./SECURITY.md).
