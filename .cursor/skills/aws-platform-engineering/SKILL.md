---
name: aws-platform-engineering
description: "Generators for AWS platform-engineering scaffolds — landing zones (SRA-aligned), Terraform modules, GitHub Actions OIDC workflows, ADRs (AWS prescriptive shape), ECS Fargate / Lambda platform services, Bedrock-backed gen-AI services, static-outbound-IP VPC layouts, and IDP golden-path docs. Backs the AWS Platform Engineer persona; binds AWS prescriptive guidance (CAF Platform, IDP guide, SRA, landing zones, ADR process, ALB/subnet routing, static-egress pattern, GenAI blueprint) into every artifact."
---

# AWS Platform Engineering — Cursor skill

Eight bound capabilities, each backed by a template under `templates/`.
Capabilities are listed in the order an agent typically reaches for them.
Capability removal or addition lands via a successor ADR (per ADR-005 §Compliance).

This skill is the *generation* layer for the AWS Platform Engineer persona at
[`.cursor/agents/aws-platform-engineer.md`](../../agents/aws-platform-engineer.md).
The persona owns *intent*; this skill owns *artifacts*.

> Sources marked **`AWS-prescriptive`** are normative — capabilities marked this
> way encode AWS prescriptive guidance verbatim and the agent is not free to
> deviate without a written justification cited in the generated artifact.

---

## Capability index

| # | Capability | Template | `AWS-prescriptive`? |
|---|---|---|---|
| 1 | `bootstrap-landing-zone-skeleton` | [`templates/landing-zone.md.tmpl`](templates/landing-zone.md.tmpl) | yes — SRA + landing-zone guide |
| 2 | `generate-terraform-module` | [`templates/terraform-module.tf.tmpl`](templates/terraform-module.tf.tmpl) | partial — module shape per CAF Platform |
| 3 | `generate-actions-oidc-workflow` | [`templates/github-actions-oidc.yml.tmpl`](templates/github-actions-oidc.yml.tmpl) | yes — CAF Platform "no long-lived credentials" |
| 4 | `generate-adr` | [`templates/adr.md.tmpl`](templates/adr.md.tmpl) | yes — AWS prescriptive ADR process |
| 5 | `generate-platform-service-skeleton` | [`templates/ecs-fargate-service.tf.tmpl`](templates/ecs-fargate-service.tf.tmpl) | partial — ALB layout per ALB/subnet guide |
| 6 | `generate-bedrock-service-skeleton` | [`templates/bedrock-service.tf.tmpl`](templates/bedrock-service.tf.tmpl) | partial — GenAI blueprint |
| 7 | `generate-static-egress-vpc` | [`templates/static-egress-vpc.tf.tmpl`](templates/static-egress-vpc.tf.tmpl) | yes — static-outbound-IP pattern |
| 8 | `generate-golden-path-doc` | [`templates/golden-path.md.tmpl`](templates/golden-path.md.tmpl) | yes — AWS IDP guide vocabulary |

---

## 1. `bootstrap-landing-zone-skeleton` — `AWS-prescriptive`

**When to use.** A new tenant or a major workload requires a fresh AWS landing
zone (e.g., a new regulated environment, a new business unit). The output is a
*scaffold doc* + a top-level `infrastructure/landing-zones/<name>/` directory
shape that an operator can take to Control Tower (preferred) or to a custom
Organizations + Landing Zone Accelerator deployment.

**Inputs.**

- `landing_zone_name` — short kebab-case identifier (e.g., `pharm-prod`).
- `tenant` — Catalyst tenant slug (per `tenant/*` label).
- `regions` — primary + DR regions (e.g., `us-east-1` + `us-west-2`).
- `account_baseline` — `control-tower` (default) or `organizations`.

**Output shape.** A markdown scaffold doc + directory layout matching the SRA:

```
infrastructure/landing-zones/<name>/
├── README.md                         # rendered from template
├── org/
│   ├── ous.tf                        # Workloads / Infrastructure / Security OUs
│   ├── scps/
│   │   ├── deny-leave-org.json
│   │   ├── deny-root-actions.json
│   │   └── deny-disable-cloudtrail.json
│   └── delegated-admin.tf            # Security Tooling = delegated admin
├── accounts/
│   ├── org-management/               # billing, SCPs, Org-trail
│   ├── security-tooling/             # GuardDuty, Security Hub, Inspector, Macie, Access Analyzer
│   ├── log-archive/                  # Org CloudTrail S3 + KMS
│   ├── network/                      # TGW, central egress, NFW, DNS
│   ├── shared-services/              # SSO, image factory, internal mirrors
│   └── workloads/<app>-<env>/        # one per (app x env)
└── docs/
    └── golden-paths/                 # rendered via capability #8
```

**Guardrails.**

- The skeleton MUST instantiate the SRA OU shape verbatim
  ([SRA architecture](https://docs.aws.amazon.com/prescriptive-guidance/latest/security-reference-architecture/architecture.html)).
- Security services live in the **Security Tooling** account as the delegated
  admin
  ([SRA — Security Tooling](https://docs.aws.amazon.com/prescriptive-guidance/latest/security-reference-architecture/security-tooling.html)).
- CloudTrail organization trail writes to the **Log Archive** account only,
  with bucket policy denying writes by anyone outside the organization.
- `account_baseline=control-tower` is the default; `organizations` is allowed
  but the scaffold doc must call out which Control Tower features the operator
  is foregoing (account factory, account customization, drift detection,
  centralised guardrails) and what they will replace those with (e.g., LZA).
- All seven landing-zone foundational features MUST be addressed in the
  scaffold doc
  ([Understanding landing zones](https://docs.aws.amazon.com/prescriptive-guidance/latest/migration-aws-environment/understanding-landing-zones.html)):
  multi-account architecture, security baseline, identity, governance, data
  security, network design, logging.

**Composition.** Pair with capabilities #2 (per-account modules), #3 (CI for
each account), #8 (golden-path docs for the developer-facing services).

---

## 2. `generate-terraform-module`

**When to use.** Any new reusable infra primitive (a VPC, an RDS cluster, an
S3 bucket pattern, an SQS DLQ pattern, etc.) lands as a Terraform module under
`infrastructure/modules/` first; consumer code wires modules together.

**Inputs.**

- `module_name` — kebab-case (e.g., `s3-encrypted-bucket`).
- `module_type` — `resource` (single-purpose) or `composite` (multi-resource).
- `aws_provider_version` — pinned (e.g., `~> 5.60`).
- `inputs` — list of `{ name, type, description, default? }` objects.
- `outputs` — list of `{ name, description }` objects.

**Output shape.**

```
infrastructure/modules/<resource|composite>/<module-name>/
├── README.md
├── versions.tf
├── variables.tf
├── outputs.tf
├── main.tf
├── examples/
│   └── basic/
│       ├── main.tf
│       └── README.md
└── .pre-commit-config.yaml
```

**Guardrails.**

- `versions.tf` pins both Terraform and provider versions.
- `README.md` documents inputs, outputs, examples, and Well-Architected
  pillar trade-offs.
- `.pre-commit-config.yaml` wires `tflint`, `tfsec`, `checkov`, and `conftest`
  (OPA) — these are the policy-as-code hooks the persona expects on every
  module per CAF Platform §Build infrastructure automation.
- No real AWS account IDs in any example; use `123456789012`.

---

## 3. `generate-actions-oidc-workflow` — `AWS-prescriptive`

**When to use.** Any new GitHub Actions workflow that touches AWS — `terraform
plan`/`apply`, `aws s3 sync`, `aws ecs update-service`, `aws lambda
update-function-code`, etc.

**Inputs.**

- `workflow_name` — display name (e.g., `Catalyst API — terraform plan`).
- `trigger` — `pull_request`, `push`, `schedule`, `workflow_dispatch`.
- `target_branch` — for `push` triggers; binds the OIDC role's trust policy.
- `aws_role_arn_var` — secret/var name (e.g., `OIDC_ROLE_TF_PLAN`).
- `aws_region` — target region.
- `concurrency_group` — for serialised deploy jobs.

**Output shape.** A workflow YAML file with:

- Top-of-file `# AWS-AUTH: oidc` marker.
- `permissions: { id-token: write, contents: read }` at workflow-level.
- `aws-actions/configure-aws-credentials@v4` step with `role-to-assume`,
  `aws-region`, and `audience: sts.amazonaws.com`.
- No `aws-access-key-id` / `aws-secret-access-key` anywhere.
- Concurrency block for any push-triggered apply step.

**Guardrails (binding — `AWS-prescriptive`).**

- The OIDC role's trust policy (in the matching Terraform) MUST bind on
  `repository:Cloud-Byte-Consulting/Catalyst` PLUS a `ref` condition for
  production workflows; never wildcard `repository:*`.
- The job MUST use a specific role ARN per (env x action) — read-only roles
  for `plan`, write-capable roles for `apply`. Never reuse one role for both.
- The workflow MUST NOT echo `${{ secrets.* }}` to logs.

Cite source: [CAF Platform — Manage credential use](https://docs.aws.amazon.com/prescriptive-guidance/latest/aws-caf-platform-perspective/platform-eng.html).

---

## 4. `generate-adr` — `AWS-prescriptive`

**When to use.** Any architecturally significant decision — structure,
non-functional requirements, dependencies, interfaces, construction techniques
([ADR process §Scope](https://docs.aws.amazon.com/prescriptive-guidance/latest/architectural-decision-records/adr-process.html)).

**Inputs.**

- `adr_number` — next sequential per `docs/ADR/` (e.g., `006`).
- `adr_title` — imperative-mood (e.g., `"Adopt EventBridge Scheduler over CloudWatch Events"`).
- `context_summary` — 3-6 sentences on the forces at play.
- `decision_summary` — one paragraph stating the choice.
- `alternatives` — list of `{ option, why_rejected }` objects.

**Output shape.** A markdown file at `docs/ADR/ADR-<NNN>-<slug>.md` matching
both the in-repo template and the AWS prescriptive shape:

- `Title`, `Status: Proposed`, `Date: <YYYY-MM-DD>`.
- `Context`, `Decision`, `Consequences` (positive + negative + risks +
  mitigations), `Alternatives considered`, `Compliance`, `Notes` (author,
  version, changelog), `Related`.

**Guardrails (binding — `AWS-prescriptive`).**

- `Status` starts at `Proposed`. The skill never writes `Accepted` directly.
- The immutability rule is documented in the generated ADR's `Compliance`
  section: "Once Accepted, this ADR is immutable. Replace via a successor
  ADR per the AWS prescriptive ADR process."
- Every `Consequences` block MUST include both positive and negative bullets
  ([ADR process §ADR contents](https://docs.aws.amazon.com/prescriptive-guidance/latest/architectural-decision-records/adr-process.html)).
- Every `Alternatives` row MUST have a `why rejected` reason — no
  unrejected alternatives ([example ADR](https://docs.aws.amazon.com/prescriptive-guidance/latest/architectural-decision-records/appendix.html)).

---

## 5. `generate-platform-service-skeleton`

**When to use.** A new Catalyst-managed service that runs on AWS — typically
ECS Fargate (default) for stateless web/API workloads, Lambda for event-driven
or low-traffic, EKS only when k8s primitives are required.

**Inputs.**

- `service_name` — kebab-case (e.g., `catalyst-api`).
- `runtime` — `ecs-fargate` (default) | `lambda` | `eks`.
- `lb` — `alb-internet-facing` | `alb-internal` | `none` (Lambda).
- `image_repo` — ECR repo URI (or build-from-source flag).
- `port` — container port.
- `health_check_path` — HTTP health probe path.

**Output shape.** A Terraform composite module that wires:

- VPC subnets per the ALB-public / targets-private layout (G-6,
  [ALB subnet routing](https://docs.aws.amazon.com/prescriptive-guidance/latest/load-balancer-stickiness/subnets-routing.html)).
- IAM Task Role (least-privilege) + Task Execution Role.
- Structured JSON logging via `awslogs` driver with log group retention.
- X-Ray daemon sidecar (or Lambda layer for Lambda runtime).
- CloudWatch alarms: 5xx rate, latency p95/p99, target health.
- Secrets referenced by SSM/Secrets Manager ARN (G-3).
- Optional WAF + CloudFront for `alb-internet-facing`.
- Per-env tfvars stub showing the `env/dev`, `env/stage`, `env/prod` overrides.

**Guardrails.**

- `lb=alb-internet-facing` => targets MUST live in private subnets (G-6).
- IAM Task Role action list is the smallest viable set — no wildcards (G-2).
- All env vars come from SSM/Secrets Manager; no inline secrets (G-3).
- Module README documents Well-Architected trade-offs (cost vs HA: single AZ
  vs multi-AZ; cold-start vs always-warm for Lambda).

---

## 6. `generate-bedrock-service-skeleton`

**When to use.** A new gen-AI capability — PR review, ops-intel summariser,
ADR drafter, golden-path generator. Backed by Bedrock; uses the GenAI
platform-engineering blueprint.

**Inputs.**

- `service_name` — kebab-case.
- `bedrock_model_id` — e.g., `anthropic.claude-3-5-sonnet-20240620-v1:0`.
- `multistep` — `true` if the service orchestrates multiple Bedrock calls
  (use Step Functions); `false` for single-shot.
- `kb_id` — optional Bedrock Knowledge Base ID for RAG.

**Output shape.** A Terraform composite module + Lambda/ECS service that
implements the GenAI blueprint
([Accelerating generative AI applications with a platform engineering approach](https://aws.amazon.com/blogs/machine-learning/accelerating-generative-ai-applications-with-a-platform-engineering-approach/)):

- **Connectors**: API Gateway + WAF; optional WebSocket for streaming.
- **Controls**: pre-response toxicity / PII redaction / faithfulness /
  relevancy guard. Bedrock Guardrails enforced; output sanitised before
  user response.
- **Data**: Bedrock Knowledge Base (if `kb_id` set); fine-grained Lake
  Formation grants on the underlying S3.
- **Observability**: CloudWatch metrics for prompt/response token counts,
  X-Ray traces per Bedrock call, OpenSearch index for prompt history.
- **Orchestration**: Step Functions state machine for multistep; DynamoDB
  table for prompt/agent state with TTL.
- **LLM**: explicit `bedrock_model_id` pin; no model-version drift.

**Guardrails.**

- The controls layer is non-negotiable. A skeleton without
  Bedrock Guardrails or an equivalent output sanitiser is a hard reject.
- Token-rate limits enforced via API Gateway usage plan and Bedrock
  invocations metered to a daily budget (DynamoDB conditional updates), per
  the Heijunka principle in the Catalyst README.
- Prompt logs in OpenSearch are retained for 30 days then archived to S3
  (Glacier IT) for audit; prompts containing secrets are redacted on the
  way in (`secrets-scrubbed` modifier label per STATE-MACHINE §2.6).

---

## 7. `generate-static-egress-vpc` — `AWS-prescriptive`

**When to use.** A workload (Lambda, ECS task) must egress from a predictable
IP — partner SFTP allowlist, regulator firewall, private API requiring source-
IP allowlist.

**Inputs.**

- `vpc_name` — kebab-case (e.g., `lambda-static-egress-vpc`).
- `cidr` — VPC CIDR (default `10.0.0.0/25` per the AWS pattern).
- `azs` — 2 AZs (HA default; documented single-AZ override exists).
- `attach_lambda` — Lambda function name to attach (optional; pure VPC if
  omitted).

**Output shape.** Terraform module per
[Generate a static outbound IP address using a Lambda function, Amazon VPC, and a serverless architecture](https://docs.aws.amazon.com/prescriptive-guidance/latest/patterns/generate-a-static-outbound-ip-address-using-a-lambda-function-amazon-vpc-and-a-serverless-architecture.html):

- VPC with the specified CIDR.
- Two **public** subnets (one per AZ) with NAT gateway + Elastic IP each.
- Two **private** subnets (one per AZ) — Lambda or ECS task lives here.
- Internet gateway attached to the VPC.
- Route tables: public subnets default-route to IGW; private subnets
  default-route to the AZ-local NAT GW.
- Outputs: the two Elastic IP addresses (the static egress IPs the partner
  must allowlist), the private subnet IDs.

**Guardrails.**

- HA default is two NAT GWs. Single-NAT cost-saving override is documented
  in the module README but not the default.
- The module README explicitly enumerates the cost (~$65/mo per NAT GW at
  idle) so the cost-engineer prompt can challenge the choice.
- The output Elastic IPs are tagged `Purpose=static-egress`,
  `tenant=<>`, `env=<>` to make IPAM auditable.

---

## 8. `generate-golden-path-doc` — `AWS-prescriptive`

**When to use.** A new service offering or module is ready for self-service
adoption; a golden-path doc is the user-visible artifact developers consume
([AWS IDP guide §goals](https://docs.aws.amazon.com/prescriptive-guidance/latest/internal-developer-platform/introduction.html):
"Encapsulate common best practices into reusable building blocks, known as
golden paths").

**Inputs.**

- `golden_path_name` — kebab-case (e.g., `aws-fargate-web-service`).
- `target_persona` — `application-developer` | `platform-engineer` |
  `data-scientist`.
- `linked_module` — Terraform module the golden path materialises.

**Output shape.** A markdown doc at
`docs/golden-paths/<golden_path_name>.md` with the IDP-prescribed shape:

- **What** — one-paragraph definition of the offering.
- **Why** — the developer pain it removes (cognitive load reduction).
- **Opinion** — the team's stance: defaults, what's enforced, what's not.
- **Paved road** — step-by-step the developer follows to consume the module.
- **Escape hatch** — when the paved road doesn't fit, the supported way to
  diverge (typically: open a `type/kaizen` describing the unmet need).
- **Owner + on-call rota + SLOs** — who owns the path, response targets.

**Guardrails.**

- The five IDP sections (What / Why / Opinion / Paved road / Escape hatch)
  are non-negotiable. A doc missing any is rejected.
- The doc explicitly cites Cognitive Load Reduction as a goal per the IDP
  guide.
- The doc links to the generated module (capability #2 or #5/#6/#7).

---

## How an agent invokes a capability

Three equivalent paths:

### Path A — direct file authoring from the template

The agent reads `templates/<template-file>`, substitutes the inputs, writes
the result to the target path. This is the universal fallback and works
without any MCP server.

### Path B — MCP tool call (preferred when the `aws-pe` server is registered)

If `.cursor/mcp.json` registers the `aws-pe` MCP server (see
[`aws_pe_mcp_server.py`](aws_pe_mcp_server.py)), the agent calls the matching
MCP tool:

| Capability | MCP tool |
|---|---|
| #1 `bootstrap-landing-zone-skeleton` | `aws_pe_landing_zone` |
| #2 `generate-terraform-module` | `aws_pe_terraform_module` |
| #3 `generate-actions-oidc-workflow` | `aws_pe_oidc_workflow` |
| #4 `generate-adr` | `aws_pe_adr` |
| #5 `generate-platform-service-skeleton` | `aws_pe_service_skeleton` |
| #6 `generate-bedrock-service-skeleton` | `aws_pe_bedrock_skeleton` |
| #7 `generate-static-egress-vpc` | `aws_pe_static_egress_vpc` |
| #8 `generate-golden-path-doc` | `aws_pe_golden_path` |

Each tool returns the rendered text + the suggested target path; the agent
writes the file using its native Write tool.

### Path C — Shell invocation of the MCP wrapper as a CLI

`python .cursor/skills/aws-platform-engineering/aws_pe_mcp_server.py --cli
<capability> <args>` — for one-off renders outside an agent session.

---

## Composition with existing skills

- **RLM** (`.cursor/skills/rlm/`): when generating a module that touches a
  large existing artifact (a hundred-resource Terraform plan, a CloudTrail
  export), route the analysis through RLM first; this skill consumes the
  RLM synthesis as the input to a generator.
- **Issue-execution-gherkin-workflow**: every generation lands as a structured
  Issue comment (Decision / Rationale / Actions taken / Verification / Next).
  The skill never silently writes files; it reports what it created.

---

## References

- ADR: [`docs/ADR/ADR-005-aws-agentic-platform-engineering.md`](../../../docs/ADR/ADR-005-aws-agentic-platform-engineering.md)
- Research: [`docs/research/aws-agentic-platform-engineering.md`](../../../docs/research/aws-agentic-platform-engineering.md)
- Persona: [`.cursor/agents/aws-platform-engineer.md`](../../agents/aws-platform-engineer.md)
- Workspace rule: [`.cursor/rules/aws-platform-engineering.mdc`](../../rules/aws-platform-engineering.mdc)
- AWS prescriptive sources: enumerated in the research doc §7.
