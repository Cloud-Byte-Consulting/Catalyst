# ADR-005 — Adapt the Agentic Platform Engineering pattern to AWS as a Cursor plugin

**Status**: Proposed · 2026-05-14
**Related**: [ADR-001](ADR-001-github-issues-as-state-machine.md), [ADR-002](ADR-002-construct-hierarchy.md), [ADR-003](ADR-003-static-and-ephemeral-environments.md), [ADR-004](ADR-004-rlm-for-long-context-agent-tasks.md), [STATE-MACHINE.md](STATE-MACHINE.md), [`docs/research/aws-agentic-platform-engineering.md`](../research/aws-agentic-platform-engineering.md), [`docs/plans/aws-agentic-platform-engineering-plan.md`](../plans/aws-agentic-platform-engineering-plan.md)

## Context

Microsoft GBB published an end-to-end "Agentic Platform Engineering" pattern
([microsoftgbb/agentic-platform-engineering](https://github.com/microsoftgbb/agentic-platform-engineering),
[Part 1 blog](https://devblogs.microsoft.com/all-things-azure/agentic-platform-engineering-with-github-copilot/),
[Part 2 blog](https://devblogs.microsoft.com/all-things-azure/putting-agentic-platform-engineering-to-the-test/))
that organises platform-team work into three "Acts": (1) capture tribal
knowledge as agent personas + reusable prompt files; (2) embed those prompts
into PR/CI workflows for "standards-as-agents"; (3) wire monitoring -> issue
tracker -> autonomous remediation agent (the "Cluster Doctor"). The pattern is
Azure-native (AKS, Bicep, Workload Identity Federation, Azure OpenAI, Azure MCP,
AKS-MCP, Microsoft Foundry).

Catalyst is an AWS-native Internal Developer Platform whose core conventions
already supply the structural prerequisites the MS pattern relies on:

- GitHub Issues + Project board as the durable agent state machine
  (ADR-001, STATE-MACHINE.md).
- Structured issue handoff comments
  (`docs/issue-execution-gherkin-workflow-2026-05-13.md`).
- RLM scaffold for long-context analysis (ADR-004).
- Cursor plugin assets under `.cursor/` (rules, skills, prompts, MCP).

The two missing pieces in Catalyst today are (a) an *AWS-flavoured agent
persona* the IDE picks up by default for AWS work and (b) reusable, generator-
shaped *skills/prompts* that emit AWS scaffolds aligned to AWS-prescriptive
guidance. Without (a)/(b) the plugin gives no opinion when an agent is asked
"add an ECS service", "open a new landing zone account", "wire a CI workflow
that deploys to AWS" — leaving each Cursor session to re-derive the pattern.

The AWS guidance that constrains how we close the gap is normative, not
optional — specifically:

- The **AWS Cloud Adoption Framework — Platform perspective** ([CAF Platform
  perspective](https://docs.aws.amazon.com/prescriptive-guidance/latest/aws-caf-platform-perspective/platform-eng.html))
  prescribes the maturity ladder (Start -> Advance -> Excel) and the platform
  capabilities (landing zone, central IdP, central network, central log
  archive, OIDC-only credentials, central observability, IaC, FinOps).
- The **AWS Internal Developer Platform guide** ([IDP guide](https://docs.aws.amazon.com/prescriptive-guidance/latest/internal-developer-platform/introduction.html))
  defines an IDP as a **product** whose deliverables are *golden paths* for
  developer self-service.
- The **AWS Security Reference Architecture (SRA)** ([SRA welcome](https://docs.aws.amazon.com/prescriptive-guidance/latest/security-reference-architecture/welcome.html),
  [SRA architecture](https://docs.aws.amazon.com/prescriptive-guidance/latest/security-reference-architecture/architecture.html),
  [SRA Organizations](https://docs.aws.amazon.com/prescriptive-guidance/latest/security-reference-architecture/organizations.html))
  prescribes the multi-account org structure (Org Management / Security:
  {Tooling, Log Archive} / Infrastructure: {Network, Shared Services} /
  Workloads: {Application}) and where each security service must live.
- The **landing-zone guidance** ([Understanding landing zones](https://docs.aws.amazon.com/prescriptive-guidance/latest/migration-aws-environment/understanding-landing-zones.html),
  [Setting up the landing zone](https://docs.aws.amazon.com/prescriptive-guidance/latest/migration-aws-environment/preparing-landing-zone.html))
  defines the seven foundational features the platform must provide.
- The **AWS prescriptive ADR process** ([ADR welcome](https://docs.aws.amazon.com/prescriptive-guidance/latest/architectural-decision-records/welcome.html),
  [ADR process](https://docs.aws.amazon.com/prescriptive-guidance/latest/architectural-decision-records/adr-process.html),
  [example](https://docs.aws.amazon.com/prescriptive-guidance/latest/architectural-decision-records/appendix.html))
  prescribes ADR shape, lifecycle (Proposed -> Accepted | Rejected | Superseded)
  and the **immutability rule** (accepted ADRs are not edited; new insight
  produces a new ADR).
- The **ALB subnet/routing guidance** ([Load balancer subnets and routing](https://docs.aws.amazon.com/prescriptive-guidance/latest/load-balancer-stickiness/subnets-routing.html))
  prescribes the public-subnets-for-ALB / private-subnets-for-targets layout.
- The **static-outbound-IP serverless pattern** ([static-egress pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/patterns/generate-a-static-outbound-ip-address-using-a-lambda-function-amazon-vpc-and-a-serverless-architecture.html))
  is the canonical layout for Lambda workloads that must egress from a
  predictable IP (regulator firewalls, SFTP partners).
- The **GenAI platform-engineering blog** ([Accelerating generative AI applications](https://aws.amazon.com/blogs/machine-learning/accelerating-generative-ai-applications-with-a-platform-engineering-approach/))
  defines the reusable-component blueprint for Bedrock-backed services
  (frontend / connectors / data / controls / observability / orchestration / LLMs).

The full source synthesis lives in
[`docs/research/aws-agentic-platform-engineering.md`](../research/aws-agentic-platform-engineering.md);
this ADR captures only the decision and its consequences.

## Decision

We will adopt the agentic platform-engineering pattern adapted to AWS-native
primitives and ship it as **additive Cursor plugin assets** inside Catalyst.

Concretely:

1. **An AWS platform-engineer agent persona** at
   `.cursor/agents/aws-platform-engineer.md` (senior AWS platform engineer / IDP
   architect) with explicit, AWS-prescriptive guardrails: least-privilege IAM,
   no wildcard `Resource: "*"`, secrets via Secrets Manager / SSM Parameter
   Store, GitHub OIDC for CI auth (no long-lived keys), Well-Architected lenses
   on all designs, SRA-aligned account placement, landing-zone primitives,
   ALB-public/targets-private routing, and the static-egress pattern when
   IP-allowlisting is required.
2. **A workspace rule** at `.cursor/rules/aws-platform-engineering.mdc` that
   wires the persona to the skill, the prompts, this ADR, and the research doc;
   it auto-activates on AWS contexts (mentions of AWS services, `*.tf` files,
   `.github/workflows/` edits touching AWS).
3. **A skill** at `.cursor/skills/aws-platform-engineering/SKILL.md` exposing
   eight bound capabilities: `bootstrap-landing-zone-skeleton`,
   `generate-terraform-module`, `generate-actions-oidc-workflow`, `generate-adr`
   (matching the AWS prescriptive ADR shape), `generate-platform-service-skeleton`
   (ECS Fargate default, Lambda alternative), `generate-bedrock-service-skeleton`,
   `generate-static-egress-vpc`, `generate-golden-path-doc`. Each capability
   ships a template under `templates/`.
4. **Five prompts** under `.cursor/prompts/`: `aws-architect.md`,
   `aws-cost-engineer.md`, `aws-security-engineer.md`, `aws-sre.md`,
   `aws-idp-product-owner.md`.
5. **An optional thin MCP wrapper** at
   `.cursor/skills/aws-platform-engineering/aws_pe_mcp_server.py` (pure stdlib),
   registered alongside the existing `rlm-repl` server in `.cursor/mcp.json`.
   Provides tool-native generators so the agent can call `generate_terraform_module`
   without a Shell round-trip.
6. **The Cluster Doctor analogue** is composed from existing Catalyst pieces:
   EventBridge / CloudWatch Alarms -> `services/webhook-handler` -> create
   `type/incident` or `type/ops-intel-finding` issue (per ADR-001) -> the
   `aws-platform-engineer` persona claims it. No new state-machine vocabulary
   is introduced; the `cluster-identity-certainty` requirement maps onto
   construct-anchor labels (`tenant/*`, `env/*`, `lz/*`, `project/*`, `app/*`)
   plus runtime `aws sts get-caller-identity` verification before any write.
7. **No existing Claude / RLM assets are modified.** The plugin is purely
   additive.

The AWS prescriptive ADR process is the authority on this ADR's shape and
lifecycle: this ADR is **Proposed**; once accepted it is immutable, and any
revision lands as a successor ADR with `Superseded by ADR-NNN` on this one.

## Rationale

The MS pattern stripped of Azure specifics needs five things: a discoverable
persona format, a discoverable prompt format, an MCP for tool-native access, an
issue tracker as the durable substrate, and OIDC-based CI auth. Catalyst already
supplies the issue tracker (ADR-001) and the OIDC convention is implicit in the
README's "Toyota production line" framing of CI as the line stop. The remaining
three deliverables are exactly what the plugin adds.

The deliberate choices in the decision are:

- **Cursor agent file format over GitHub Copilot Custom Agents**. The team's
  primary IDE is Cursor; the agent file format mirrors the existing
  `.claude/agents/rlm-subcall.md` convention (per ADR-004) so the Cursor and
  Claude surfaces compose. CI invocations of the same persona via the Cursor
  Agent SDK or the `cursor` CLI are tracked under the *Automation Service*
  milestone, not this branch.
- **Terraform first** (CDK if better fit). CAF Platform perspective requires
  IaC; the existing Catalyst Terraform footprint and the README's `infrastructure/modules/composite/`
  convention make Terraform the obvious default. CDK is reserved for cases
  where the construct model adds material clarity (e.g., ECS Fargate behind
  ALB with WAF).
- **ECS Fargate as the default platform-service runtime, not EKS**. EKS gives
  the closest 1:1 to AKS but adds operational surface area Catalyst does not
  need for stateless platform services. The skill emits ECS Fargate by default;
  the EKS option is documented for workloads that actually require k8s
  primitives (Operators, CRDs, sidecars).
- **SRA OU shape encoded into the landing-zone scaffold, not invented**. The
  landing-zone scaffold the skill emits matches the SRA's
  Org Management / Security: {Tooling, Log Archive} / Infrastructure: {Network,
  Shared Services} / Workloads: {Application} layout verbatim. Marked
  `AWS-prescriptive` so the agent treats it as a constraint.
- **The Cluster Doctor analogue is composed, not invented**. ADR-001 already
  prescribes the issue-driven incident loop and `services/webhook-handler` is
  the entry point; introducing a new dispatcher would duplicate state. The
  persona simply claims existing `type/incident` issues and the construct-anchor
  labels supply the cluster-identity-certainty signals the MS persona needs
  before any write action.
- **Optional MCP rather than mandatory MCP**. The MS repo registers AKS-MCP as
  load-bearing for runtime access; we only need MCP for *generation* tasks
  (write a module, write a workflow, write an ADR) where tool-native helpers
  beat Shell round-trips. Runtime AWS access stays in the human/CI loop until a
  first-party AWS-MCP exists.

## Consequences

### Good

- Catalyst gains a default, opinionated AWS persona for every Cursor session
  that touches AWS. The class of failure where each session re-derives the
  same SRA-placement / OIDC / ALB-routing / static-egress pattern goes away.
- Golden paths become a concrete artifact: the skill emits IDP-style
  golden-path docs that match the AWS IDP-guide vocabulary (the *what*, the
  *why*, the *opinion*, the *paved road*, the *escape hatch*).
- The plugin's ADR generator binds the AWS prescriptive ADR shape and the
  immutability rule into every new architecturally-significant decision the
  agent records — no more silent drift between ADR style and AWS guidance.
- The Cluster Doctor analogue composes cleanly with ADR-001 and ADR-002. No
  new state-machine vocabulary, no new dispatcher.
- The plugin is **additive** — existing Claude/RLM assets are untouched. There
  is no risk of breaking the long-context workflow already in production.
- The ADR-001 audit trail (issue comments) becomes the agent's session log; no
  separate observability layer is needed.

### Trade-offs we accept

- **Cursor-first, GitHub Copilot second.** The MS pattern is Copilot-native;
  agents using GitHub Copilot Custom Agents inside this repo will not pick up
  the persona automatically. Mitigation: the prompts under `.cursor/prompts/`
  are plain markdown and can be invoked in any IDE that supports `@file`
  references. Re-export to `.github/agents/` and `.github/prompts/` is a
  follow-up `type/kaizen` if/when the team adopts Copilot Custom Agents.
- **No first-party AWS-MCP for runtime access.** The MS Cluster Doctor leans
  on AKS-MCP for `kubectl` / cluster diagnostics; AWS has no equivalent
  first-party MCP yet. Catalyst's plugin only exposes *generation* tools. For
  runtime work the agent shells out to `aws` CLI or uses the existing
  webhook-handler / ops-intel pipelines. Tracked as an open follow-up in
  the research doc §6.
- **Skill is opinionated.** ECS Fargate over EKS, Terraform over CDK, OIDC
  over keys, Bedrock over Foundry. Workloads with legitimate need for the
  rejected option must override the default explicitly, with a comment in the
  generated module pointing to the rationale. This is the "opinion + escape
  hatch" pattern from the AWS IDP guide.
- **One new operating rule in AGENTS.md.** "AWS work uses GitHub OIDC, never
  long-lived keys" is added. Marginal AGENTS.md growth; the trade-off is high-
  signal-to-noise.
- **Terraform-style ALB default.** The ALB-public / targets-private layout is
  enforced as the default; workloads that need the inverted layout (e.g.,
  internal ALB in a private VPC) must opt out explicitly. This avoids the
  most common subnet-routing mistake (per the prescriptive ALB routing guide).
- **The static-egress generator is opinionated about NAT cost.** Two NAT
  gateways across AZs is HA-correct but ~$65/mo at idle; cheaper alternatives
  (single NAT, instance-based NAT, `EgressOnlyInternetGateway` for IPv6) are
  documented in the template's README but not the default.

### Risks and mitigations

| Risk | Mitigation |
|---|---|
| Persona drifts from AWS prescriptive guidance over time | Skill capability `generate-adr` is the only place new architectural decisions land; AWS prescriptive ADR process (immutable + supersession) keeps drift auditable. Quarterly review of cited AWS sources in research doc §7. |
| Agents bypass the skill and generate ad-hoc Terraform | Workspace rule activates the persona by default; persona body explicitly directs the agent to the skill's generators before authoring inline. |
| OIDC trust policy mistakes (overbroad `repository:` claim) | `generate-actions-oidc-workflow` template binds the trust policy to a specific repo + branch; persona guardrail rejects wildcard `repository:*`. |
| ALB layout regressions | `generate-platform-service-skeleton` template is the only sanctioned source; workspace rule warns when the agent is about to author ALB Terraform without using the template. |
| SRA-aligned scaffold conflicts with existing Catalyst Terraform that pre-dates ADR-005 | Skill marks the scaffold "for new landing zones only"; existing modules are not retrofitted in this branch. Migration is a separate `type/kaizen`. |
| Optional MCP server becomes load-bearing without being designed for it | MCP wrapper is documented as a *generation-time convenience*; the same generators are reachable via the Shell tool. CI does not depend on the MCP being running. |
| Cluster-identity-certainty check insufficient for AWS multi-account | Persona requires three signals: `aws sts get-caller-identity` (account ID + ARN), `aws ec2 describe-availability-zones --region <r>` for region, and the construct-anchor labels on the issue (`tenant/*` / `env/*` / `lz/*`) — all three must agree before any write. |

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| **Vendor the MS repo's `Act-3` workflows verbatim and rebrand for AWS** | The Argo CD -> repository_dispatch -> issue flow already exists in Catalyst as `webhook-handler` (ADR-001). Vendoring would duplicate state and contradict ADR-001. |
| **Wait for a first-party AWS-MCP and skip the plugin work** | No timeline; meanwhile every Cursor session re-derives the same patterns. The generation-side MCP wrapper is cheap and ships value today. |
| **Stand up a Backstage / Port portal as the IDP surface** | Belongs to the *[Option 5] optional — Production-ready or HA architecture diagrams* milestone; the IDE-facing IDP surface (Cursor) is the leading-indicator surface and ships value first. |
| **Author one mega-prompt instead of an agent + skill + prompts split** | Loses Cursor's auto-activation on rule contexts; loses the IDP "golden paths as discrete artifacts" framing; harder to keep the AWS-prescriptive guardrails versionable. |
| **Use AWS CDK as the default IaC language** | Catalyst's existing infra is Terraform; CDK introduces a Python/TypeScript runtime in the platform path that doesn't exist today. CDK remains an explicit option in the skill, but not the default. |
| **Make the persona auto-activate on every Cursor session in the repo** | Noise on unrelated tasks (RLM work, doc edits, issue triage). The rule is `alwaysApply: false` and matches AWS contexts only — same convention as `rlm-workflow.mdc`. |

## Compliance

- The `aws-platform-engineer` persona must be present at
  `.cursor/agents/aws-platform-engineer.md` and reference this ADR in its body.
- The workspace rule `.cursor/rules/aws-platform-engineering.mdc` must include
  this ADR's filename in its `## References` section.
- The skill at `.cursor/skills/aws-platform-engineering/SKILL.md` must list
  exactly the eight capabilities in §Decision item 3; capability removals or
  additions land via a successor ADR.
- The five prompts under `.cursor/prompts/` listed in §Decision item 4 must
  exist; new prompts may be added under the same naming pattern.
- Any optional Python helper (e.g., the MCP wrapper) must pass
  `python -m py_compile` and depend only on stdlib.
- AWS examples in any plugin asset use `123456789012` as a placeholder
  account ID; never a real one.

## Notes

- Author: rc/aws-agentic-platform-engineering branch (issue #19)
- Version: 0.1
- Changelog: 0.1 — initial proposed version (2026-05-14)

## Related

- [ADR-001 — GitHub Issues + Projects as the durable state machine](ADR-001-github-issues-as-state-machine.md)
- [ADR-002 — construct hierarchy](ADR-002-construct-hierarchy.md)
- [ADR-003 — static and ephemeral environments](ADR-003-static-and-ephemeral-environments.md)
- [ADR-004 — RLM for long-context agent tasks](ADR-004-rlm-for-long-context-agent-tasks.md)
- [STATE-MACHINE.md](STATE-MACHINE.md)
- [`docs/research/aws-agentic-platform-engineering.md`](../research/aws-agentic-platform-engineering.md)
- [`docs/plans/aws-agentic-platform-engineering-plan.md`](../plans/aws-agentic-platform-engineering-plan.md)
- [`docs/issue-execution-gherkin-workflow-2026-05-13.md`](../issue-execution-gherkin-workflow-2026-05-13.md)
- AWS prescriptive: CAF Platform perspective, AWS SRA, AWS landing zones, AWS IDP guide, AWS prescriptive ADR process — see research doc §7 for full URLs.
- MS source: [microsoftgbb/agentic-platform-engineering](https://github.com/microsoftgbb/agentic-platform-engineering).
