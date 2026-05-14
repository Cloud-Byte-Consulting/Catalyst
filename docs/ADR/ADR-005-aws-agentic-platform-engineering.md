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

## Container supply chain

### Decision

- **Trivy** is the **primary** container image scanner for Catalyst.
  Skill capability `generate-container-scan-workflow` emits the canonical
  GitHub Actions workflow.
- **Docker Scout** is the **documented alternative**. Skill capability
  `generate-container-scan-scout-workflow` emits the equivalent workflow.
  Both produce the SAME artifact contract — SARIF + SPDX 2.3 + CycloneDX 1.5
  — so swapping scanners is a workflow-file change, not a downstream-consumer
  change.
- **SBOMs** are produced in BOTH **SPDX 2.3 JSON** AND **CycloneDX 1.5 JSON**,
  uploaded as the workflow artifact `sbom-${{ github.sha }}` (90-day
  retention), and attached to GitHub Releases on tagged pushes.
- **Severity gate**: build fails on `HIGH,CRITICAL` by default. Relaxation
  requires PR-body justification; documented exceptions live in
  `.trivyignore` with a `# rationale: <text>` and a `review-by: <date>`
  for every entry; reviewed quarterly.
- **Registry-side scanning**: every ECR repo has `scan_on_push = true`
  (basic) AND the account has registry-wide `ENHANCED` scanning via
  Inspector V2 (`aws_ecr_registry_scanning_configuration`). Findings flow
  to AWS Security Hub via the SRA Security Tooling delegated admin
  pattern.
- **Base-image policy** (B-1..B-8): pin by digest, minimal/distroless or
  AL2023-minimal only, multi-stage builds, non-root user, `HEALTHCHECK`,
  no build-time secrets, documented `.trivyignore` exceptions, OCI image
  labels for chargeback.
- **Currency**: Dependabot watches the `docker` ecosystem on every
  containerised path; PRs land as `type/kaizen` and are gated by the same
  scan workflow.
- **Decision boundary**: Trivy default; Scout alternative; **no third
  scanner**. PRs introducing Grype/Snyk/Clair are rejected with a pointer
  to this section.
- **GitHub MCP secret scanning** is enabled via the `secret_protection`
  toolset and `run_secret_scanning` tool registered in `.cursor/mcp.json`.
  Agents (specifically the `security-hardener` persona at
  `.cursor/agents/security-hardener.md`) invoke secret scanning as a
  **pre-merge gate** on any PR that adds new files or credential-adjacent
  content, running alongside the Trivy image scan. Findings are ephemeral
  (session-only, not persisted to the GitHub Security tab); persisted alerts
  are managed via `list_secret_scanning_alerts` / `get_secret_scanning_alert`.
  Escalation path and triage rules are in
  `.cursor/rules/github-secret-scanning.mdc`.
  _Sources_: [Changelog GA 2026-05-05](https://github.blog/changelog/2026-05-05-secret-scanning-with-github-mcp-server-is-now-generally-available/),
  [GHAS + AI coding agents guide](https://docs.github.com/en/code-security/how-tos/use-ghas-with-ai-coding-agents/scan-for-secrets-with-github-mcp-server).

### Rationale

- **Trivy is OSS, broad coverage, SARIF-native.** Single tool covers OS
  packages, language libraries, IaC, Dockerfile misconfig, and SBOM
  generation. Native SARIF + SPDX + CycloneDX output. Pinned-by-SHA
  Action available (`aquasecurity/trivy-action`). Aligned to GitHub's
  code-scanning conventions out of the box.
- **Scout is the right alternative when Docker is already in the loop.**
  Teams already paying for Docker Hub / Docker Desktop and using Scout's
  policy + remediation features should not be forced off it. The same
  artifact contract means downstream Catalyst consumers (Security Hub
  forwarder, release pipeline) do not care which scanner produced the
  SARIF / SBOM.
- **Both SPDX 2.3 and CycloneDX 1.5.** Customers, regulators, and
  vulnerability platforms split on which spec they consume. Producing both
  costs marginal CI time and removes a friction point at consumption.
- **ECR Enhanced (Inspector V2) for runtime scanning.** Continuous
  scanning of registry-resident images catches vulns disclosed AFTER
  build time (the most common case). Inspector V2 -> Security Hub -> 
  Catalyst's webhook-handler -> `type/ops-intel-finding` issues completes
  the loop into the existing state machine without inventing a new
  pipeline.
- **HIGH/CRITICAL gate.** Lower-severity gates create alert fatigue and
  push teams to silence findings; HIGH/CRITICAL is the level where the
  tradeoff between false-positive rate and exploitability favours
  blocking.
- **Pin-by-digest base-image rule.** Tag drift is the single most common
  cause of "I rebuilt and now it's vulnerable / no longer vulnerable"
  flake. Digest pins make builds reproducible and SBOMs accurate.

### Consequences

#### Good

- Container PRs ship with a uniform contract: a SARIF in the Security tab,
  two SBOMs in artifact storage, a HIGH/CRITICAL gate enforced by CI.
- Findings flow into the existing GitHub-Issues state machine via
  ECR-Enhanced -> Inspector V2 -> Security Hub -> webhook-handler. No new
  state vocabulary, no new dispatcher.
- The Trivy/Scout split honours team preference without fragmenting the
  downstream contract.
- `.trivyignore` becomes auditable rather than a silent allowlist; the
  `review-by` date stops permanent exceptions from accumulating.

#### Trade-offs we accept

- **Build-time gate cost.** Trivy scan + SBOM jobs add ~3-7 minutes per
  PR for a typical service image. Acceptable; outweighed by the cost of
  shipping a known HIGH/CRITICAL CVE.
- **`.trivyignore` governance.** Every exception requires a rationale + a
  date. This is operational toil that the persona owns; the alternative
  (silent allowlists) is worse.
- **SBOM storage / retention.** 90-day artifact retention + indefinite
  Release attachment costs money. Acceptable; SBOMs are the audit trail
  for supply-chain incidents.
- **Scout requires Docker Hub auth** even for ECR-resident images; the
  Scout workflow uses `secrets.DOCKERHUB_USERNAME` + `DOCKERHUB_TOKEN` and
  the trade-off is documented at the top of the workflow.
- **Inspector V2 is per-account.** The `aws_ecr_registry_scanning_configuration`
  MUST be declared once per account (typically Security Tooling or Shared
  Services); duplicating it per workload is a design error.

### Alternatives considered

| Alternative | Why rejected |
|---|---|
| **Grype + Syft** (Anchore stack) — Grype for vulns, Syft for SBOM | Two-tool split adds CI orchestration cost. Trivy's vulns + SBOM in one tool wins on simplicity. Syft's SBOM output is excellent but Trivy's is sufficient for our consumers. |
| **Snyk** (commercial) | Adds vendor cost + lock-in for marginal capability over Trivy. Better triage UI, but our triage UI is the GitHub Issue (per ADR-001), not a vendor dashboard. |
| **Clair** (Quay-aligned) | Less active maintenance vs Trivy; weaker SBOM story; weaker GitHub Action integration. |
| **ECR Basic only** | Misses IaC misconfig + Dockerfile lint that Trivy catches at build time. Basic scan also lacks Inspector V2's continuous re-scanning of already-pushed images. |
| **SBOM in only one format (e.g., SPDX)** | Forces consumers to bridge formats. Producing both costs marginal CI time and removes a friction point. |
| **No build-time gate; fix-forward only** | Leaves a window where shipped images carry known HIGH/CRITICAL CVEs. The SRE prompt's MTTR SLO would balloon. |
| **Allow Grype/Snyk/Clair as third options "if a team prefers"** | Fragments the artifact contract; downstream consumers (Security Hub forwarder, release pipeline) would have to support multiple SARIF / SBOM dialects. The Trivy ↔ Scout swap is sufficient to honour team preference. |

## Python tooling

### Decision

- **CLI framework**: Microsoft [`knack`](https://github.com/microsoft/knack)
  for any new Catalyst Python CLI. The
  [`python-cli-and-testing`](../../.cursor/skills/python-cli-and-testing/SKILL.md)
  skill's `scaffold-knack-cli` capability emits the canonical
  `cli.py` / `commands.py` / `arguments.py` / `validators.py` /
  `formatters.py` / `help.py` / `exceptions.py` shape. CLI ships with
  `--help` per subcommand, `--output {table,json,tsv,yaml}` (knack ships
  the first three; the YAML formatter is added by the Catalyst scaffold),
  declarative validators, structured exceptions with mapped exit codes.
- **Test framework**: [`pytest`](https://docs.pytest.org/en/stable/)
  configured in `pyproject.toml` `[tool.pytest.ini_options]` with
  `--strict-markers` + `--strict-config` + `addopts = "-ra"`, the
  `tests/{unit,integration,e2e}` layout, registered markers
  (`slow`, `integration`, `e2e`, `moto`), and coverage via
  [`pytest-cov`](https://pypi.org/project/pytest-cov/) with
  `--cov-fail-under=85`. The skill's `scaffold-pytest-config` capability
  emits the config; `scaffold-pytest-ci-workflow` emits the GitHub
  Actions job.
- **AWS service mocking in tests**: [`moto`](https://docs.getmoto.org/)
  via the v5 unified `mock_aws()` decorator / context manager. The
  `tests/conftest.py` ships with `aws_credentials`, `s3_client`, and
  `ddb_client` fixtures wired through `mock_aws()`.
- **Parallelism**: [`pytest-xdist`](https://pypi.org/project/pytest-xdist/)
  available for `pytest -n auto`. Not required by default; CI defaults
  to single-process for deterministic ordering.

### Rationale

- **knack is small, declarative, and battle-tested.** It is the framework
  Microsoft Azure CLI is built on (per [microsoft/knack repo](https://github.com/microsoft/knack)),
  which means the `CLICommandsLoader` / `ArgumentsContext` / YAML help
  patterns are exercised by a CLI with hundreds of commands. Catalyst's
  CLI grows in similar shape (groups of commands per resource), so the
  patterns transfer cleanly. The framework removes the bespoke argparse
  boilerplate that otherwise accretes around growing CLIs.
- **pytest is the de-facto Python testing standard.** Rich fixture model,
  native `@pytest.mark.parametrize`, mature plugin ecosystem (`pytest-cov`,
  `pytest-xdist`, `pytest-asyncio`), and the assertion rewrite gives
  unittest-style TDD without unittest's class-and-method ceremony. Strict
  markers + strict config catch typos at collection time rather than
  silently no-op-ing.
- **moto is the lowest-friction AWS mocking layer.** v5's `mock_aws()`
  context manager replaces the per-service `mock_s3` / `mock_dynamodb` /
  ... decorators (per [docs.getmoto.org](https://docs.getmoto.org/)), so
  one fixture covers any service without per-test boilerplate. moto runs
  in-process — no Docker, no LocalStack, no recorded fixtures to maintain.

### Consequences

#### Good

- Every Catalyst Python CLI looks the same: same help layout, same output
  switches, same exit-code semantics. Operators learn one CLI shape.
- Every Catalyst test suite looks the same: same `pyproject.toml` config,
  same fixture names, same coverage gate. New contributors find tests in
  the expected place.
- AWS mocking is uniform — moto-backed tests look identical across
  services; reviewers do not have to remember whether a given service is
  `placebo`-recorded or `vcrpy`-recorded.
- `--strict-markers` + `--strict-config` keeps test config honest.

#### Trade-offs we accept

- **Small extra deps** (`knack`, `pytest`, `pytest-cov`, `moto`). All are
  pure-Python, all have stable APIs, all are in active maintenance.
- **Learning curve** for `CLICommandsLoader` / `CommandGroup` style.
  Documented in the skill with reference code; one read of
  [knack/docs/commands.md](https://github.com/microsoft/knack/blob/dev/docs/commands.md)
  and [knack/docs/arguments.md](https://github.com/microsoft/knack/blob/dev/docs/arguments.md)
  is sufficient.
- **Knack's `dev` branch is the doc source of truth.** The repo's docs
  live on the `dev` branch (not `main`). The research doc cites those
  URLs explicitly so the agent always reads from the active docs branch.
- **YAML output is a custom formatter, not native.** knack ships JSON /
  JSON-colored / Table / TSV (per [knack/docs/output.md](https://github.com/microsoft/knack/blob/dev/docs/output.md));
  the Catalyst scaffold registers `yaml` via `OutputProducer.format_dict`.
  This is a small piece of glue but it's pinned to a knack internal API
  that *could* shift; covered by the CLI tests in
  `tests/unit/test_formatters.py`.
- **Coverage gate at 85%** is intentionally not 100%. 100% coverage
  forces tests of trivial getters / dataclasses / `if TYPE_CHECKING:`
  blocks. 85% with `branch = true` and the `exclude_lines` block in
  `[tool.coverage.report]` strikes the right balance.

### Alternatives considered

| Alternative | Why rejected |
|---|---|
| **`Click`** | More popular than knack but encourages decorator-heavy CLI definitions that drift from a declarative model as the CLI grows. Click's parameter-on-command pattern complicates shared / inherited arguments — knack's `ArgumentsContext` with scope inheritance is cleaner for Catalyst's groups-within-groups shape. |
| **`Typer`** | Typer wraps Click with type hints. Same drift concern as Click for a growing CLI. Typer's strength is small CLIs; Catalyst's CLI is not small. |
| **`argparse` (stdlib)** | Floor-level. Re-derives knack's value (declarative groups, validators, output formatters, help authoring) by hand. Acceptable for one-off scripts; not the default for Catalyst's CLI. |
| **`unittest`** | Older, class-and-method ceremony, weaker fixture model, no native parametrize, no assertion rewrite. Catalyst keeps existing `unittest`-style code in place; new tests use pytest. |
| **`nose2`** | Less momentum than pytest. Plugin ecosystem is smaller. Some active development but pytest is the better bet. |
| **`placebo`** | Records-and-replays real boto3 traffic. Recordings drift; refreshing them is operator toil. moto's in-process service simulation has fewer moving parts. |
| **`vcrpy`** | Same critique as `placebo` — recorded HTTP cassettes drift. Useful for non-AWS HTTP testing; permitted for that case with a written justification. Not the default for AWS. |
| **LocalStack** | Heavier (Docker-required) than moto for the unit/integration test surface Catalyst needs. Worth revisiting for `e2e`-marked tests. |

## Compliance

- The `aws-platform-engineer` persona must be present at
  `.cursor/agents/aws-platform-engineer.md` and reference this ADR in its body.
- The workspace rule `.cursor/rules/aws-platform-engineering.mdc` must include
  this ADR's filename in its `## References` section.
- The skill at `.cursor/skills/aws-platform-engineering/SKILL.md` must list
  exactly the **thirteen** capabilities (eight original + five container
  supply chain); capability removals or additions land via a successor ADR.
- The companion skill at `.cursor/skills/python-cli-and-testing/SKILL.md`
  must exist with the three capabilities listed in §Python tooling
  (`scaffold-knack-cli`, `scaffold-pytest-config`,
  `scaffold-pytest-ci-workflow`); capability removals or additions land
  via a successor ADR.
- The five prompts under `.cursor/prompts/` listed in §Decision item 4 must
  exist; new prompts may be added under the same naming pattern.
- Any optional Python helper (e.g., the MCP wrapper) must pass
  `python -m py_compile` and depend only on stdlib.
- AWS examples in any plugin asset use `123456789012` as a placeholder
  account ID; never a real one.
- Container image PRs follow the contract in §Container supply chain;
  workflows that bypass the scan job, omit either SBOM format, or relax
  the HIGH/CRITICAL gate without justification are rejected by the
  `aws-security-engineer` prompt.
- New Catalyst Python CLIs use `knack` per §Python tooling; new test
  suites use `pytest` with the strict-markers + `--cov-fail-under=85`
  config from the `python-cli-and-testing` skill; AWS-touching tests
  default to `moto` mocking.
- This ADR is **immutable** once Accepted per the AWS prescriptive ADR
  process; revisions land as a successor ADR.

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
