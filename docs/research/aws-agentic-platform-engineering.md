# AWS Agentic Platform Engineering — research synthesis

**Issue**: [#19 — Adapt MS Agentic Platform Engineering pattern to AWS as Cursor plugin](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/19)
**Branch**: `rc/aws-agentic-platform-engineering`
**Status**: Research complete — informs [`docs/ADR/ADR-005-aws-agentic-platform-engineering.md`](../ADR/ADR-005-aws-agentic-platform-engineering.md) and [`docs/plans/aws-agentic-platform-engineering-plan.md`](../plans/aws-agentic-platform-engineering-plan.md)
**Last updated**: 2026-05-14

This document captures the research underpinning ADR-005. It summarises Microsoft's
"Agentic Platform Engineering" pattern, summarises the relevant AWS prescriptive
guidance (CAF Platform perspective, Internal Developer Platform guide, Security
Reference Architecture, landing zones, ALB/subnet routing, static-egress pattern,
ADR process, GenAI platform-engineering blog), maps the MS constructs to AWS
equivalents, and recommends a Catalyst-fit architecture for the Cursor plugin.

> Sources marked **AWS-prescriptive** are normative for Catalyst — the agent treats
> them as constraints, not suggestions. Source URLs cited inline are the only ones
> the synthesis relies on; all were fetched and read during this work.

---

## 1. Microsoft's "Agentic Platform Engineering" pattern

### 1.1 What it is

Microsoft GBB published a three-act platform-engineering pattern that wires GitHub
Copilot (with custom agents and reusable prompt files) into the inner loop, into
CI, and into Day-2 operations. Reference repo:
[microsoftgbb/agentic-platform-engineering](https://github.com/microsoftgbb/agentic-platform-engineering).
Companion blogs:
[Part 1 — Agentic Platform Engineering with GitHub Copilot](https://devblogs.microsoft.com/all-things-azure/agentic-platform-engineering-with-github-copilot/)
and
[Part 2 — Putting Agentic Platform Engineering to the test](https://devblogs.microsoft.com/all-things-azure/putting-agentic-platform-engineering-to-the-test/).

| Concept | Where it lives in the MS repo |
|---|---|
| Custom agent persona (markdown frontmatter + persona body) | `.github/agents/cluster-doctor.agent.md` |
| Reusable team prompts (slash-invokable) | `.github/prompts/<name>.prompt.md` |
| MCP server registration (GitHub MCP + AKS MCP) | `.copilot/mcp-config.json` |
| CI: docs auto-generation via Copilot CLI | `.github/workflows/copilot.generate-docs.yml` |
| CI: incident -> issue -> agent loop | `.github/workflows/argocd-deployment-failure.yml` + `.github/workflows/copilot.trigger-cluster-doctor.yml` |
| Reference cluster manifests + broken-app demo | `Act-3/argocd/...`, `Act-3/aks-store-all-in-one.yaml` |
| Walkthroughs by Act | `Act-1/README.md`, `Act-2/README.md`, `Act-3/README.md` |

### 1.2 The three Acts

**Act 1 — The platform is growing faster than the team.** Knowledge lives in
people; people don't scale. Encode tribal knowledge as agent personas (`name`,
`description`, persona body) and link them to your service catalog and IaC modules.
The MS repo includes a "starter prompt" template (`Act-1/starter-prompt.md`) and
references two AWS-irrelevant external agents (`ricardocovo/iac-module-catalog` and
`ricardocovo/ghcp-infra-reverse-engineer`) that demonstrate the pattern.

**Act 2 — Standards exist, but they're not enforced.** Reusable team prompts
under `.github/prompts/` are invokable on-demand by any team member; the same
prompts run in CI via Copilot CLI on `push`/`pull_request`. The repo ships
`aks-check-pods.prompt.md`, `aks-check-nodes.prompt.md`, `aks-remediation.prompt.md`,
and `analyze-for-docs.prompt.md`. The pattern: encode the standard once as a prompt,
then trigger it from both the inner loop (slash command) and the outer loop
(`copilot.generate-docs.yml`).

**Act 3 — Day-2 ops don't scale linearly.** The "Cluster Doctor" agent is the
showpiece. The flow:

1. Argo CD detects a degraded application.
2. Argo CD Notifications POSTs a custom payload to GitHub via `repository_dispatch`.
3. `argocd-deployment-failure.yml` parses the payload and creates (or comments on)
   a structured GitHub issue with labels `argocd-deployment-failure`, `automated`,
   `bug`, `cluster-doctor`, including resource group, cluster name, namespace,
   health/sync status, error message, degraded resources, and pre-baked kubectl
   commands. It then dispatches a `cluster-doctor-trigger` event.
4. `copilot.trigger-cluster-doctor.yml` runs on the dispatch (or `issues.labeled`
   `cluster-doctor`). It auths to Azure via Workload Identity Federation
   (`ARM_USE_OIDC: true`), installs Copilot CLI, parses cluster info from the
   issue body via Copilot+MCP, fetches AKS credentials, port-forwards the AKS-MCP
   service, posts a "Cluster Doctor is on the case" comment, then invokes Copilot
   with the `cluster-doctor` agent and `--additional-mcp-config @.copilot/mcp-config.json`.

The MS pattern's safety guarantee is encoded in the agent persona itself: the
Cluster Doctor must verify cluster identity via two independent signals before any
write action and prefers GitOps PRs over `kubectl apply`.

### 1.3 What the pattern actually requires structurally

Stripped of AKS/Azure specifics, the MS pattern needs five things:

1. **A persona file format** the IDE/CLI can discover (`.github/agents/*.agent.md`
   for Copilot; `.cursor/agents/*.md` is the analogous Cursor surface).
2. **A reusable prompt format** that both humans and CI can invoke
   (`.github/prompts/*.prompt.md`).
3. **An MCP configuration** that the agent uses for tool-native access to the
   forge (GitHub MCP) and the runtime (AKS MCP -> in our case AWS-flavoured
   equivalents).
4. **An issue-tracker as the durable substrate** for incident -> agent handoffs
   (the MS pattern leans on GitHub Issues; Catalyst already enforces this via
   [ADR-001](../ADR/ADR-001-github-issues-as-state-machine.md) and
   [STATE-MACHINE.md](../ADR/STATE-MACHINE.md)).
5. **OIDC-based CI auth to the cloud** (`ARM_USE_OIDC: true` in Azure;
   `aws-actions/configure-aws-credentials` with `role-to-assume` + OIDC trust on AWS).

Catalyst already has (4). The plugin work in this branch supplies (1)/(2)/(3) and
encodes (5) as an `AWS-prescriptive` guardrail.

---

## 2. Relevant AWS guidance

### 2.1 AWS CAF Platform perspective — `AWS-prescriptive`

Source: [Platform engineering — AWS Cloud Adoption Framework: Platform Perspective](https://docs.aws.amazon.com/prescriptive-guidance/latest/aws-caf-platform-perspective/platform-eng.html).

Maturity is staged Start -> Advance -> Excel.

- **Start**: deploy a landing zone with detective + preventative guardrails;
  centralise authentication via an external IdP (no IAM users); deploy a
  centralised network account; collect/aggregate/protect logs (cross-account
  observability, dedicated log archive account); establish baseline controls;
  implement cloud financial management with cost-allocation tags + AWS Cost
  Categories.
- **Advance**: build infrastructure automation (IaC + RBAC/ABAC, automated
  account vending, ITSM integration); centralised observability that correlates
  logs, metrics, traces; systems management + AMI governance via SSM; manage
  credential use (roles + temporary credentials, no long-lived keys); deploy
  XDR-style security tooling.
- **Excel**: source and distribute identity constructs with automation and
  policy validation; add anomaly detection across environments; threat-model
  continuously; review and refine permissions on a closed loop; measure platform
  metrics deliberately.

The CAF document is the authoritative outcome list Catalyst's plugin must align
to. It does not name specific MS-repo equivalents; it specifies the *capabilities*
the platform must deliver.

### 2.2 AWS internal developer platform guide — `AWS-prescriptive`

Source: [Building an internal developer platform on AWS](https://docs.aws.amazon.com/prescriptive-guidance/latest/internal-developer-platform/introduction.html)
(Omar Kahil, AWS, April 2024).

Quoting the four goals verbatim: "(1) Help developers be self-sufficient. (2)
Reduce the cognitive load for developers. (3) Encapsulate common best practices
into reusable building blocks, known as **golden paths**. (4) Automate many
common tasks, such as provisioning clusters or CI/CD pipelines."

Adjacent pages of this guide
([platform-capabilities](https://docs.aws.amazon.com/prescriptive-guidance/latest/internal-developer-platform/platform-capabilities.html),
[architecture](https://docs.aws.amazon.com/prescriptive-guidance/latest/internal-developer-platform/architecture.html),
[golden-paths](https://docs.aws.amazon.com/prescriptive-guidance/latest/internal-developer-platform/golden-paths.html))
serve the same intro framing in this CMS render but the explicit guidance is
clear: an IDP is a *product* whose users are developers, whose deliverables are
golden paths (curated, self-service, opinionated patterns), and whose success
measure is developer productivity + business outcomes — not platform-team
output.

For Catalyst, this maps directly: the Cursor plugin is the IDE-facing surface of
an IDP, with golden-path generators as its primary user-visible features (see
mapping in §3 and the skill specification in
[`.cursor/skills/aws-platform-engineering/SKILL.md`](../../.cursor/skills/aws-platform-engineering/SKILL.md)).

### 2.3 AWS Security Reference Architecture (SRA) — `AWS-prescriptive`

Source: [AWS Security Reference Architecture (AWS SRA) – core architecture](https://docs.aws.amazon.com/prescriptive-guidance/latest/security-reference-architecture/welcome.html),
[The AWS Security Reference Architecture](https://docs.aws.amazon.com/prescriptive-guidance/latest/security-reference-architecture/architecture.html),
[SRA building blocks – AWS Organizations, accounts, and guardrails](https://docs.aws.amazon.com/prescriptive-guidance/latest/security-reference-architecture/organizations.html),
[Security OU – Security Tooling account](https://docs.aws.amazon.com/prescriptive-guidance/latest/security-reference-architecture/security-tooling.html).

The SRA prescribes a **multi-account org structure** centred on these account
types (Catalyst maps to these verbatim where possible):

| OU | Account | Purpose (SRA verbatim) |
|---|---|---|
| (root) | **Org Management** | Organization root, billing, SCPs, AWS Organizations |
| Security | **Security Tooling** | Centralised security services (GuardDuty, Security Hub, Inspector, Detective, Macie, Audit Manager, IAM Access Analyzer) |
| Security | **Log Archive** | Immutable, encrypted log destination (CloudTrail org trail, S3 access logs, VPC flow logs, Config) |
| Infrastructure | **Network** | Centralised egress, Transit Gateway, Network Firewall, DNS, inbound resolvers |
| Infrastructure | **Shared Services** | Shared services (AD/SSO, image factories, golden AMIs, internal package mirrors) |
| Workloads | **Application** (one per workload + per environment) | Application runtime accounts |

Key SRA principles Catalyst's plugin must respect:

- **No long-lived IAM users** — federated SSO via IAM Identity Center; CI uses
  OIDC + `sts:AssumeRoleWithWebIdentity`.
- **Account = blast-radius boundary** — each workload×environment combination
  gets its own account; IAM Identity Center and SCPs enforce separation.
- **Security services are centralised** — the Security Tooling account is the
  delegated administrator for GuardDuty, Security Hub, Macie, Inspector, Access
  Analyzer; log destinations live in Log Archive only.
- **Network egress is centralised** — workload accounts use Transit Gateway
  routes pointing to the Network account, not their own NAT gateways, except
  in the explicit static-egress pattern (§2.5).
- **CloudTrail organization trail** writes to the Log Archive account with
  bucket policies preventing write/delete by anyone except the organization.

The SRA explicitly relies on **AWS Organizations + multi-account strategy** as
the foundation for IAM guardrails (SRA `organizations.html`). Catalyst's
construct hierarchy (`docs/ADR/ADR-002-construct-hierarchy.md`) already aligns
at the Tenant -> Environment -> LandingZone boundary; the SRA specifies what
goes inside each of those buckets.

### 2.4 Landing zones — `AWS-prescriptive`

Sources:
[What is a landing zone?](https://docs.aws.amazon.com/prescriptive-guidance/latest/migration-aws-environment/understanding-landing-zones.html)
and
[Setting up a secure and scalable multi-account AWS environment](https://docs.aws.amazon.com/prescriptive-guidance/latest/migration-aws-environment/preparing-landing-zone.html)
(Durairaj & Hertsens, AWS, July 2024).

A landing zone is "a well-architected, multi-account AWS environment that is
scalable and secure" with seven foundational features:

1. Multi-account architecture (per SRA — §2.3).
2. Initial security baseline.
3. Identity and access management (centralised, federated).
4. Governance (SCPs, Config rules, Control Tower if used).
5. Data security (KMS keys per account, S3 default encryption, Backup vaults).
6. Network design (centralised TGW, segmented VPCs, no overlapping CIDRs).
7. Logging (org-trail to Log Archive; CloudWatch cross-account observability).

The four reasons cited for multiple accounts (admin isolation, limited
discoverability, blast-radius reduction, isolation of recovery/audit data) map
directly onto Catalyst's `lz/*` and `env/*` label vocabulary. Implementations
are AWS Control Tower (managed, opinionated) or custom-built (e.g., the
Landing Zone Accelerator on AWS — LZA solution). Catalyst's plugin generates
**Control Tower–ready scaffolding** by default and explicitly notes when a
generated module assumes Control Tower vs raw Organizations.

### 2.5 ALB stickiness, subnet routing, and static egress — `AWS-prescriptive`

Sources:
[Load balancer subnets and routing](https://docs.aws.amazon.com/prescriptive-guidance/latest/load-balancer-stickiness/subnets-routing.html)
and
[Generate a static outbound IP address using a Lambda function, Amazon VPC, and a serverless architecture](https://docs.aws.amazon.com/prescriptive-guidance/latest/patterns/generate-a-static-outbound-ip-address-using-a-lambda-function-amazon-vpc-and-a-serverless-architecture.html)
(Thomas Scott, AWS).

Two operational constraints the plugin's scaffolds must enforce:

- **ALB best practice**: Internet-facing ALB lives in **public subnets** (one
  per AZ); EC2/ECS targets live in **private subnets**; the ALB nodes route
  intra-VPC to the targets via the route table. Targets do not have public IPs;
  return traffic flows back through the ALB nodes in the same AZ. The plugin's
  ECS/EC2 service generator must produce this layout by default.
- **Static outbound IP for serverless**: Lambda-in-VPC pattern — two public
  subnets (with NAT gateways and EIPs), two private subnets (Lambda lives
  here), Lambda's outbound traffic egresses through the NAT gateways and gains
  a static IP. Use this when an external system requires IP allowlisting (SFTP
  partners, regulator firewalls). The plugin ships this as a reference
  Terraform snippet under the skill's `templates/`.

These two constraints are the most common non-obvious mistakes the agent will
encounter when generating AWS-native scaffolds; encoding them as guardrails in
the persona + skill removes a class of failure.

### 2.6 AWS prescriptive ADR process — `AWS-prescriptive`

Sources:
[Using architectural decision records to streamline technical decision-making for a software development project](https://docs.aws.amazon.com/prescriptive-guidance/latest/architectural-decision-records/welcome.html)
(Kunce & Goby, AWS, March 2022),
[ADR process](https://docs.aws.amazon.com/prescriptive-guidance/latest/architectural-decision-records/adr-process.html),
[Appendix: Example ADR](https://docs.aws.amazon.com/prescriptive-guidance/latest/architectural-decision-records/appendix.html).

Key normative points:

- **ADRs are immutable once accepted.** New insights produce a new ADR that
  supersedes the old one; the old one moves to `Superseded`.
- **Sections required**: Title, Status, Date, Context, Decision, Consequences
  (positive AND negative), and (per the appendix example) Compliance + Notes
  (author, version, changelog).
- **Lifecycle**: Proposed -> (Reviewed) -> Accepted | Rejected | Superseded.
- **Scope**: write an ADR for every architecturally significant decision
  affecting structure, non-functional requirements, dependencies, interfaces,
  or construction techniques.
- The collection of ADRs IS the decision log; team members "skim the headlines"
  to get project context.

Catalyst's existing ADR template (`docs/ADR/template.md`) is consistent with
the AWS prescriptive shape. ADR-005 in this branch follows the same template
and explicitly cites the AWS ADR process so future agents treat the immutability
rule as binding. The plugin's skill includes a `generate-adr` capability that
emits this exact shape.

### 2.7 Container supply chain — Trivy / Docker Scout / SBOM / ECR Enhanced

Sources:

- **Trivy** — [https://trivy.dev/](https://trivy.dev/) (project) and
  [aquasecurity/trivy-action](https://github.com/aquasecurity/trivy-action)
  (the GitHub Action used in the CI snippets).
- **Docker Scout** — [https://docs.docker.com/scout/](https://docs.docker.com/scout/)
  (product docs) and [docker/scout-action](https://github.com/docker/scout-action)
  (the GitHub Action used in the alternative CI snippet).
- **SPDX 2.3** — [https://spdx.dev/](https://spdx.dev/) (spec).
- **CycloneDX 1.5** — [https://cyclonedx.org/](https://cyclonedx.org/) (spec).
- **AWS ECR enhanced scanning** — [Image scanning enhanced (AWS-prescriptive)](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-scanning-enhanced.html).
- **Amazon Inspector V2 + ECR** — [Scanning ECR repositories with Amazon Inspector (AWS-prescriptive)](https://docs.aws.amazon.com/inspector/latest/user/scanning-ecr.html).
- **GitHub code scanning + SARIF** — [About code scanning](https://docs.github.com/en/code-security/code-scanning) + [SARIF v2.1.0 spec](https://docs.oasis-open.org/sarif/sarif/v2.1.0/sarif-v2.1.0.html).

Key normative points Catalyst encodes:

- **Trivy is the primary scanner.** Single tool covers OS packages, language
  libraries, IaC, Dockerfile misconfig, AND SBOM emission (`--format
  spdx-json`, `--format cyclonedx`). SARIF is native. Pinned-by-SHA Action
  available. The skill's `generate-container-scan-workflow` capability emits
  the canonical workflow.
- **Docker Scout is the documented alternative.** Use when Docker Hub /
  Docker Desktop is already in the developer loop OR when an active Scout
  subscription already pays for the policy + remediation features. Same
  SARIF + SBOM artifact contract as Trivy. No third option (per ADR-005
  §Container supply chain decision boundary).
- **SBOMs in BOTH SPDX 2.3 JSON AND CycloneDX 1.5 JSON.** Customers,
  regulators, and vulnerability platforms split on which spec they consume.
  Producing both is cheap and removes friction at consumption.
- **ECR Enhanced (Inspector V2)** is the AWS-prescriptive runtime registry
  scanning. `aws_ecr_registry_scanning_configuration { scan_type = "ENHANCED" }`
  declared once per account (typically Security Tooling or Shared Services per
  the SRA — §2.3) provides continuous scanning of registry-resident images;
  findings flow to Security Hub via the SRA delegated admin pattern.
- **Severity gate**: build fails on `HIGH,CRITICAL` by default. Documented
  exceptions live in `.trivyignore` with a rationale + a `review-by` date,
  reviewed quarterly.
- **Base-image policy** (B-1..B-8): pin by digest, minimal/distroless or
  AL2023-minimal only, multi-stage builds, non-root user, `HEALTHCHECK`,
  no build-time secrets, documented exceptions, OCI image labels for
  chargeback.
- **Currency**: Dependabot watches the `docker` ecosystem so pinned digests
  are kept current; PRs land as `type/kaizen` and are gated by the same
  scan workflow.

This composes with §2.3 (SRA) — Inspector V2 findings go to Security Hub in
the Security Tooling account, then via Catalyst's webhook-handler into
`type/ops-intel-finding` issues per ADR-001. No new state vocabulary or
dispatcher.

The skill's bound capabilities for this layer are #9-#13 in
[`.cursor/skills/aws-platform-engineering/SKILL.md`](../../.cursor/skills/aws-platform-engineering/SKILL.md):
`generate-container-scan-workflow` (Trivy),
`generate-container-scan-scout-workflow`, `generate-ecr-scan-on-push`,
`generate-base-image-policy`, `generate-dependabot-container`.

### 2.8 Python tooling — pytest + knack + moto

Sources:

- **pytest** —
  [docs.pytest.org / stable](https://docs.pytest.org/en/stable/),
  [How to use fixtures](https://docs.pytest.org/en/stable/how-to/fixtures.html),
  [How to parametrize](https://docs.pytest.org/en/stable/how-to/parametrize.html),
  [Configuration](https://docs.pytest.org/en/stable/reference/customize.html),
  [How to monkeypatch / mock](https://docs.pytest.org/en/stable/how-to/monkeypatch.html),
  [tmp_path](https://docs.pytest.org/en/stable/how-to/tmp_path.html),
  [Capture stdout/stderr](https://docs.pytest.org/en/stable/how-to/capture-stdout-stderr.html),
  [Markers](https://docs.pytest.org/en/stable/how-to/mark.html).
- **pytest-cov** — [pypi.org/project/pytest-cov/](https://pypi.org/project/pytest-cov/).
- **pytest-xdist** — [pypi.org/project/pytest-xdist/](https://pypi.org/project/pytest-xdist/).
- **moto** — [docs.getmoto.org](https://docs.getmoto.org/) (v5 unified `mock_aws()`).
- **knack** — [github.com/microsoft/knack](https://github.com/microsoft/knack)
  (the framework Microsoft Azure CLI is built on);
  [knack/docs/commands.md](https://github.com/microsoft/knack/blob/dev/docs/commands.md),
  [knack/docs/arguments.md](https://github.com/microsoft/knack/blob/dev/docs/arguments.md),
  [knack/docs/help.md](https://github.com/microsoft/knack/blob/dev/docs/help.md),
  [knack/docs/output.md](https://github.com/microsoft/knack/blob/dev/docs/output.md).

Key normative points Catalyst encodes (per ADR-005 §Python tooling and the
[`python-cli-and-testing`](../../.cursor/skills/python-cli-and-testing/SKILL.md) skill):

- **CLI = `knack`.** `CLICommandsLoader.load_command_table` declares the
  command table; `CommandGroup` groups commands; `ArgumentsContext`
  customises arguments and registers `validator`s; YAML help authoring
  via the `helps[]` dict at module scope. knack ships JSON / JSON-colored
  / Table / TSV output; the Catalyst scaffold adds a YAML formatter via
  `OutputProducer.format_dict["yaml"] = ...` for parity with `--output`
  conventions developers expect from cloud CLIs. Knack's `dev` branch
  carries the canonical docs.
- **Tests = `pytest`** with `[tool.pytest.ini_options]` in
  `pyproject.toml`. The Catalyst defaults (per the skill):
  `addopts = "-ra --strict-markers --strict-config --showlocals
  --tb=short --import-mode=importlib"`,
  `testpaths = ["tests"]`,
  `markers = [...]` (registers `slow`, `integration`, `e2e`, `moto`),
  `filterwarnings = ["error", ...]`. Coverage gate
  `[tool.coverage.report] fail_under = 85`.
- **Fixtures lean on built-ins** (`tmp_path`, `monkeypatch`, `capsys`)
  per pytest's how-to-fixtures docs. Construct-anchor fixture
  (`tenant`/`environment`/`landing_zone`/`project`/`application`) supplies
  the labels every Catalyst service expects.
- **AWS mocking = `moto` v5 `mock_aws()`.** One context manager handles
  any service; the `tests/conftest.py` ships `s3_client` / `ddb_client`
  fixtures that yield a moto-mocked boto3 client. `placebo` and `vcrpy`
  are permitted only with a written justification in the test module's
  docstring.
- **Markers select the test class** at run time:
  `pytest -m "not e2e and not slow"` for the default loop;
  `pytest -m moto` for AWS-touching tests; `pytest -n auto` for parallel
  via `pytest-xdist`. `e2e` tests are auto-skipped unless `RUN_E2E=1`
  per a `pytest_collection_modifyitems` hook in the conftest.
- **CI command (canonical)**:
  `pytest -q -ra --strict-markers --strict-config --junitxml=junit.xml
  --cov --cov-report=xml --cov-fail-under=85 -m "not e2e and not slow"`.
  Emitted by the skill's `scaffold-pytest-ci-workflow` capability across
  a `python: ["3.11", "3.12"]` matrix.
- **Automation-service handlers** are factored so business logic is unit-
  testable *without* the HTTP / Lambda envelope. The integration test uses
  FastAPI's `TestClient` (sync) or `httpx.AsyncClient` (async) and
  monkeypatches the dep-injection seam at the consumption point — never
  reaching the network.

This composes with §2.6 (AWS prescriptive ADR process — supersession
governs Python tooling decisions just like everything else) and
§2.7 (container supply chain — pytest CI workflow is a separate workflow
from the Trivy scan workflow; both run on the same PR).

### 2.9 GenAI platform-engineering blog

Source: [Accelerating generative AI applications with a platform engineering approach](https://aws.amazon.com/blogs/machine-learning/accelerating-generative-ai-applications-with-a-platform-engineering-approach/)
(Foo & Bhatt, AWS, ~2025).

The blog argues that GenAI applications need the same platform-engineering
discipline as classical apps. It lays out a reusable-components blueprint:

- **Frontend** — micro-frontend modules, session management, auth/authz.
- **Connectors** — REST/WebSocket layer to embed AI in other apps.
- **Data** — structured (Aurora/RDS via dedicated read interfaces) and
  unstructured (vector stores, knowledge bases per domain); fine-grained
  governance via Lake Formation.
- **Controls** — unified output-control layer (toxicity, PII redaction,
  faithfulness, relevancy), enforced before the response is returned to the
  user.
- **Observability** — CloudWatch + X-Ray + OpenSearch.
- **Orchestration** — Step Functions for multi-step workflows, DynamoDB for
  prompt/agent state, Lambda for per-step logic.
- **LLMs** — Bedrock for managed models; SageMaker for fine-tuning/custom.

This frames the *Bedrock-backed gen-AI service skeleton* the plugin's skill
generates: the skeleton is not just "a Lambda that calls Bedrock", it is a
service shell with the controls + observability + orchestration shape from this
blog.

---

## 3. MS -> AWS construct mapping

This is the load-bearing section. Cells marked **`AWS-prescriptive`** are
constraints (not suggestions) per the cited AWS guidance.

| Microsoft construct | AWS equivalent | Plugin guidance | Source |
|---|---|---|---|
| Bicep / ARM templates | **Terraform first** (CDK if better fit) — `AWS-prescriptive` (CAF: "use IaC to define configurations declaratively") | Skill's `generate-terraform-module` capability emits HCL with policy-as-code hooks (tfsec, Checkov, OPA via Conftest). Catalyst already standardises on Terraform per the README's "Toyota production line" framing. | CAF Platform §Build infrastructure automation |
| Azure Landing Zones (ALZ) | **AWS Landing Zone** (Control Tower or Landing Zone Accelerator) — `AWS-prescriptive` | Skill's `generate-landing-zone-skeleton` capability emits a Control Tower-ready Org/OU/account scaffold with the SRA OU shape (Security, Infrastructure, Workloads). | Migration §Understanding landing zones; SRA §architecture |
| AKS (Azure Kubernetes Service) | **EKS** (parity) **or ECS Fargate** (lighter, AWS-idiomatic for stateless workloads) | Skill defaults to ECS Fargate for the generated platform service skeleton; calls out EKS as the option when the workload requires k8s primitives. | n/a (architectural judgment) |
| Argo CD on AKS | **EKS + Argo CD** (1:1) **or** **CodePipeline + ECS deploy** (AWS-native) | For the Cluster Doctor analogue, Catalyst leans on the existing webhook-handler pattern (ADR-001 §What this means for the runtime) — EventBridge / CloudWatch Alarms -> webhook-handler -> create `type/incident` or `type/ops-intel-finding` issue. | ADR-001; CAF Platform §centralised observability |
| Azure API Management (APIM) | **API Gateway** (REST/HTTP/WebSocket) | Skill's gen-AI service skeleton uses API Gateway + WAF in front of the Lambda/ECS handler. | GenAI blog §Frontend / Connectors |
| Azure DevOps / GitHub Actions on Azure | **GitHub Actions on AWS via OIDC** — `AWS-prescriptive` (CAF: "rely on temporary credentials") | Skill's `generate-actions-oidc-workflow` capability emits a workflow that uses `aws-actions/configure-aws-credentials@v4` with `role-to-assume` and `audience: sts.amazonaws.com`. Never uses static AWS keys. | CAF Platform §Manage credential use |
| Azure OpenAI | **Amazon Bedrock** | Skill's `generate-bedrock-service-skeleton` emits an ECS/Lambda service with the controls/observability/orchestration shape from the GenAI blog. | GenAI blog §Anatomy / blueprint |
| Microsoft Foundry / Foundry IQ for org knowledge | **Bedrock Knowledge Bases + S3 + OpenSearch Serverless** | Bedrock Knowledge Bases handles the RAG pattern Foundry IQ surfaces. | GenAI blog §Data |
| Defender for Cloud | **Security Hub + GuardDuty + Inspector + Macie** (centralised in the **Security Tooling** account) — `AWS-prescriptive` | Skill notes account-placement requirements; never recommends enabling these per-workload-account in isolation. | SRA §Security Tooling account |
| Azure Monitor / Application Insights | **CloudWatch + X-Ray + OpenSearch** (cross-account observability per CAF) — `AWS-prescriptive` | Skill's service skeleton wires structured JSON logging, X-Ray tracing, and CloudWatch alarms by default. | CAF Platform §Provide centralised observability |
| Azure Workload Identity Federation | **AWS IAM OIDC provider for GitHub** + IAM role with `sts:AssumeRoleWithWebIdentity` — `AWS-prescriptive` | Skill's `generate-actions-oidc-workflow` includes the trust policy for the OIDC role; cite the Catalyst convention "no static AWS keys in CI". | CAF Platform §Manage credential use |
| Cosmos DB | **DynamoDB** (key/value, single-digit ms) **or** **Aurora Serverless v2** (relational) | Skill's gen-AI orchestration skeleton uses DynamoDB for prompt/agent state per the GenAI blog. | GenAI blog §Orchestration |
| Azure Key Vault | **AWS Secrets Manager** (rotated secrets) **+ SSM Parameter Store** (config) — `AWS-prescriptive` | Persona guardrail: never inline secrets; reference by `arn:aws:secretsmanager:...` or `ssm:/path/to/param`. | CAF Platform §Establish controls / Manage credential use |
| Azure App Configuration | **AppConfig** (release feature flags) + SSM Parameter Store | Skill includes AppConfig binding when generating an ECS service. | n/a (AWS-native idiom) |
| Azure Front Door + WAF | **CloudFront + AWS WAF** | Skill's external-facing service scaffold places CloudFront in front of ALB or API GW. | n/a (AWS-native idiom) |
| Azure Policy | **AWS Service Control Policies (SCPs)** + **AWS Config rules** + **OPA/Conftest** in CI | Catalyst already runs Conftest in CI per the README; SCPs and Config rules are managed in the Org Management / Security Tooling accounts per SRA. | SRA §organizations |
| Azure Bastion | **Systems Manager Session Manager** | Skill never recommends opening 22 to anything; SSM Session Manager is the only sanctioned shell access. | CAF Platform §Manage credential use |
| AKS-MCP server | (gap — no first-party AWS-MCP) | Catalyst plugin defines a thin MCP wrapper exposing `generate_terraform_module`, `generate_actions_oidc_workflow`, `generate_adr`. Optional and lives in `.cursor/skills/aws-platform-engineering/`. | n/a (gap acknowledged) |
| `.github/agents/*.agent.md` | `.cursor/agents/*.md` | 1:1 mapping with the Cursor convention. | Cursor docs (existing pattern) |
| `.github/prompts/*.prompt.md` | `.cursor/prompts/*.md` | 1:1 mapping. | Cursor docs (existing pattern) |
| `.copilot/mcp-config.json` | `.cursor/mcp.json` | 1:1 mapping. | Existing Catalyst convention (RLM MCP) |
| Argo CD `repository_dispatch` webhook | **EventBridge -> webhook-handler Lambda -> GitHub Issues `create`** | Already exists in Catalyst (`services/webhook-handler`); the plugin documents how to add a new event source rather than re-inventing the dispatch pattern. | ADR-001 |

### 3.1 Where the mapping is *not* clean

- **Workload Identity Federation in K8s pods**: Azure WIF is a single primitive
  the AKS pod uses to federate to Entra. AWS uses **IRSA** (IAM Roles for
  Service Accounts) on EKS, which is conceptually identical but procedurally
  different (different annotations, different OIDC provider URL). The plugin's
  EKS skeleton notes this; the ECS skeleton uses Task IAM Roles which are a
  cleaner fit for most platform services.
- **AKS-MCP**: there is no AWS-equivalent first-party MCP for "drive the
  cluster from an agent" yet. Catalyst's plugin exposes only its own thin
  MCP for *generation* tasks; runtime access stays in the human/CI loop.
- **Foundry IQ**: Microsoft's "host private models inside Foundry, expose via
  MCP" is a single product. The AWS equivalent stitches Bedrock + Knowledge
  Bases + custom MCP. The plugin's gen-AI skeleton documents this stitching
  rather than pretending it's a single product.

---

## 4. Recommended Catalyst-fit architecture for the Cursor plugin

### 4.1 Plugin shape

```
.cursor/
├── agents/
│   └── aws-platform-engineer.md          # persona (senior AWS PE / IDP architect)
├── rules/
│   └── aws-platform-engineering.mdc       # workspace rule wiring persona to skills/prompts
├── skills/
│   ├── aws-platform-engineering/
│   │   ├── SKILL.md                       # capability spec
│   │   ├── aws_pe_mcp_server.py           # optional thin MCP (pure stdlib)
│   │   └── templates/
│   │       ├── terraform-module.tf.tmpl
│   │       ├── github-actions-oidc.yml.tmpl
│   │       ├── adr.md.tmpl
│   │       ├── ecs-fargate-service.tf.tmpl
│   │       ├── bedrock-service.tf.tmpl
│   │       ├── static-egress-vpc.tf.tmpl  # the §2.5 pattern
│   │       └── golden-path.md.tmpl
│   └── rlm/                               # untouched (existing)
├── prompts/
│   ├── aws-architect.md                   # SRA + landing-zone reasoning
│   ├── aws-cost-engineer.md
│   ├── aws-security-engineer.md           # SRA-aligned IAM + security services
│   ├── aws-sre.md
│   ├── aws-idp-product-owner.md           # IDP-as-product framing
│   ├── architect.md                       # untouched (existing)
│   ├── skeptic.md                         # untouched (existing)
│   └── advocate.md                        # untouched (existing)
└── mcp.json                                # extended to register aws-pe MCP alongside rlm-repl
```

### 4.2 Trigger model

- **Inner loop**: agent persona auto-activates from the workspace rule on
  matched contexts (mentions of AWS services, `*.tf` files, `.github/workflows`
  edits touching AWS). Prompts are slash-invokable.
- **Issue-driven (Cluster Doctor analogue)**: `type/incident` or
  `type/ops-intel-finding` issues created by `services/webhook-handler` pick up
  this persona automatically when an agent claims them; the persona's body
  documents the cluster-identity-certainty pattern adapted to AWS account/region
  identity (verify `aws sts get-caller-identity` AccountId + Region against the
  issue body's construct anchors before any write action).
- **CI**: `generate-actions-oidc-workflow` emits a job that runs the persona's
  prompts via Cursor CLI / Cursor Agent SDK on `pull_request` / `push`. This is
  the AWS analogue of the MS `copilot.generate-docs.yml` flow.

### 4.3 Personas the plugin ships

| Persona | When to invoke | Maps to (MS) |
|---|---|---|
| `aws-platform-engineer` (agent file) | Default for any AWS PE work | Cluster Doctor (extended scope) |
| `aws-architect` (prompt) | New service / module design — must reason about SRA OU placement, landing zone primitives, ALB/subnet routing | Bicep/ARM design prompts |
| `aws-cost-engineer` (prompt) | Cost reviews, RI/SP analysis, tagging audits | (no MS direct equivalent) |
| `aws-security-engineer` (prompt) | IAM policy review, SCP design, GuardDuty/Security Hub finding triage | Security review prompts |
| `aws-sre` (prompt) | Day-2 ops, alarm design, incident triage, runbook generation | `aks-check-pods` / `aks-check-nodes` / `aks-remediation` |
| `aws-idp-product-owner` (prompt) | Treat the platform as a product — golden-path proposals, developer-survey synthesis, golden-path retros | (implicit in MS Acts 1+2) |

### 4.4 Skill capabilities (binding list)

The skill lists exactly these capabilities (each backed by a template under
`templates/`):

1. `bootstrap-landing-zone-skeleton` — emits an SRA-aligned Org/OU/account
   scaffold (Org Management / Security: {Tooling, Log Archive} / Infrastructure:
   {Network, Shared Services} / Workloads: {App-X-{dev,stage,prod}}). Notes
   Control Tower vs raw Organizations explicitly. **`AWS-prescriptive`**.
2. `generate-terraform-module` — HCL module skeleton with `variables.tf`,
   `outputs.tf`, `versions.tf`, `README.md`, `examples/`, and pre-commit hooks
   for tflint + tfsec + Checkov + Conftest.
3. `generate-actions-oidc-workflow` — GitHub Actions workflow using OIDC; never
   long-lived keys; explicit `permissions:` block with `id-token: write`. **`AWS-prescriptive`**.
4. `generate-adr` — emits an ADR matching both the in-repo template and the
   AWS prescriptive shape (Title/Status/Date/Context/Decision/Consequences/
   Compliance/Notes); states `Status: Proposed` and the immutability rule.
   **`AWS-prescriptive`**.
5. `generate-platform-service-skeleton` — ECS Fargate (default) or Lambda
   service with structured JSON logging, X-Ray, CloudWatch alarms, ALB
   in-public + tasks-in-private layout (per §2.5 ALB routing).
6. `generate-bedrock-service-skeleton` — Lambda or ECS service backed by
   Bedrock with the GenAI-blog control layer (toxicity / PII redaction),
   X-Ray, DynamoDB prompt-state, Step Functions orchestration when multi-step.
7. `generate-static-egress-vpc` — the §2.5 pattern: 2 public subnets + NAT
   gateways + EIPs, 2 private subnets, Lambda-in-VPC. **`AWS-prescriptive`** for
   any workload that requires IP allowlisting at a partner.
8. `generate-golden-path-doc` — IDP-style golden-path doc per the IDP guide
   vocabulary: the *what*, the *why*, the *opinion*, the *paved road*, the
   *escape hatch*. **`AWS-prescriptive`**.

### 4.5 MCP (optional, thin)

The MCP server is **optional** and pure-stdlib. It exposes the skill's
generators as MCP tools so agents in Cursor can invoke them tool-natively
instead of via Shell round-trips. It registers under `.cursor/mcp.json`
alongside the existing `rlm-repl` server. No new runtime dependency for the
Catalyst services build.

---

## 5. Composition with existing Catalyst conventions

| Existing convention | How this plugin composes |
|---|---|
| ADR-001 (GitHub Issues as state machine) | Cluster Doctor analogue creates `type/incident` / `type/ops-intel-finding` issues via existing `webhook-handler`. Agent comment handoffs follow `docs/issue-execution-gherkin-workflow-2026-05-13.md`. |
| ADR-004 (RLM for long context) | Skill flags the trigger threshold: `terraform plan` outputs and CloudTrail exports above ~50k chars route through the RLM workflow before agent reasoning. |
| STATE-MACHINE label vocabulary | Plugin only uses existing `type/*` labels; never invents new ones. Construct anchors (`tenant/*`, `env/*`, `lz/*`, `project/*`, `app/*`) are the cluster-identity-certainty signals for AWS (account ID + region + construct anchor). |
| Construct hierarchy (ADR-002) | Plugin's landing-zone scaffold maps Tenant -> AWS Org root, Environment-class -> OU, LandingZone -> Account, Project/Application -> tags + IAM. Verbatim with the existing convention. |
| AGENTS.md operating rule (RLM trigger) | Plugin adds **one** new operating rule: "AWS work uses GitHub OIDC, never long-lived keys." |

---

## 6. Open follow-ups (not in this branch)

1. **First-party AWS-MCP for runtime access** — the MS pattern leans on AKS-MCP
   for "drive the cluster from an agent". There is no first-party AWS analogue
   yet. Track as `type/kaizen` if/when AWS publishes one.
2. **Cluster Doctor analogue end-to-end** — the issue-driven loop already
   composes via `webhook-handler` + ADR-001, but no `eks-doctor` /
   `ecs-doctor` agent has been wired yet. Belongs under
   *Automation Service* milestone; this branch ships the persona scaffolding.
3. **Bedrock-backed pr-reviewer / ops-intel agent runtime** — the GenAI blog
   blueprint informs the design but the running services live in the
   *[Option 2] optional — AWS Bedrock in containerized service(s)* milestone.
4. **Cost-Engineer prompt with Cost Explorer / CUR access** — the prompt ships
   in this branch but its full data-access pattern (Cost Explorer + CUR in
   Athena) deserves its own ADR.

---

## 7. Sources

All sources fetched and read during this work. Format: `URL — short label
(AWS-prescriptive where applicable)`.

**Microsoft side:**

- https://github.com/microsoftgbb/agentic-platform-engineering — repo root
- https://api.github.com/repos/microsoftgbb/agentic-platform-engineering/git/trees/main?recursive=1 — full repo tree (used to enumerate the actual files referenced above)
- https://raw.githubusercontent.com/microsoftgbb/agentic-platform-engineering/main/README.md
- https://raw.githubusercontent.com/microsoftgbb/agentic-platform-engineering/main/Act-1/README.md
- https://raw.githubusercontent.com/microsoftgbb/agentic-platform-engineering/main/Act-2/README.md
- https://raw.githubusercontent.com/microsoftgbb/agentic-platform-engineering/main/Act-3/README.md
- https://raw.githubusercontent.com/microsoftgbb/agentic-platform-engineering/main/.github/agents/cluster-doctor.agent.md
- https://raw.githubusercontent.com/microsoftgbb/agentic-platform-engineering/main/.copilot/mcp-config.json
- https://raw.githubusercontent.com/microsoftgbb/agentic-platform-engineering/main/.github/workflows/copilot.trigger-cluster-doctor.yml
- https://raw.githubusercontent.com/microsoftgbb/agentic-platform-engineering/main/.github/workflows/copilot.generate-docs.yml
- https://raw.githubusercontent.com/microsoftgbb/agentic-platform-engineering/main/.github/workflows/argocd-deployment-failure.yml
- https://devblogs.microsoft.com/all-things-azure/agentic-platform-engineering-with-github-copilot/ — Part 1 blog
- https://devblogs.microsoft.com/all-things-azure/putting-agentic-platform-engineering-to-the-test/ — Part 2 blog (Git-ape demo)

**AWS side:**

- https://docs.aws.amazon.com/prescriptive-guidance/latest/aws-caf-platform-perspective/platform-eng.html — CAF Platform perspective (`AWS-prescriptive`)
- https://docs.aws.amazon.com/prescriptive-guidance/latest/internal-developer-platform/introduction.html — IDP guide intro (`AWS-prescriptive`)
- https://docs.aws.amazon.com/prescriptive-guidance/latest/internal-developer-platform/platform-capabilities.html — IDP guide adjacent
- https://docs.aws.amazon.com/prescriptive-guidance/latest/internal-developer-platform/architecture.html — IDP guide adjacent
- https://docs.aws.amazon.com/prescriptive-guidance/latest/internal-developer-platform/golden-paths.html — IDP guide adjacent
- https://aws.amazon.com/blogs/machine-learning/accelerating-generative-ai-applications-with-a-platform-engineering-approach/ — GenAI platform-engineering blog
- https://docs.aws.amazon.com/prescriptive-guidance/latest/architectural-decision-records/welcome.html — ADR guide (`AWS-prescriptive`)
- https://docs.aws.amazon.com/prescriptive-guidance/latest/architectural-decision-records/adr-process.html — ADR process (`AWS-prescriptive`)
- https://docs.aws.amazon.com/prescriptive-guidance/latest/architectural-decision-records/appendix.html — ADR example
- https://docs.aws.amazon.com/prescriptive-guidance/latest/security-reference-architecture/welcome.html — SRA overview (`AWS-prescriptive`)
- https://docs.aws.amazon.com/prescriptive-guidance/latest/security-reference-architecture/architecture.html — SRA core architecture (`AWS-prescriptive`)
- https://docs.aws.amazon.com/prescriptive-guidance/latest/security-reference-architecture/organizations.html — SRA Organizations / accounts (`AWS-prescriptive`)
- https://docs.aws.amazon.com/prescriptive-guidance/latest/security-reference-architecture/security-tooling.html — Security Tooling account (`AWS-prescriptive`)
- https://docs.aws.amazon.com/prescriptive-guidance/latest/migration-aws-environment/understanding-landing-zones.html — landing zones (`AWS-prescriptive`)
- https://docs.aws.amazon.com/prescriptive-guidance/latest/migration-aws-environment/preparing-landing-zone.html — landing-zone setup (`AWS-prescriptive`)
- https://docs.aws.amazon.com/prescriptive-guidance/latest/load-balancer-stickiness/subnets-routing.html — ALB subnet routing (`AWS-prescriptive`)
- https://docs.aws.amazon.com/prescriptive-guidance/latest/patterns/generate-a-static-outbound-ip-address-using-a-lambda-function-amazon-vpc-and-a-serverless-architecture.html — static-egress pattern

**Container supply chain:**

- https://trivy.dev/ — Trivy (project)
- https://github.com/aquasecurity/trivy-action — Trivy GitHub Action
- https://docs.docker.com/scout/ — Docker Scout (product docs)
- https://github.com/docker/scout-action — Docker Scout GitHub Action
- https://spdx.dev/ — SPDX 2.3 spec
- https://cyclonedx.org/ — CycloneDX 1.5 spec
- https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-scanning-enhanced.html — ECR enhanced scanning (`AWS-prescriptive`)
- https://docs.aws.amazon.com/inspector/latest/user/scanning-ecr.html — Inspector V2 + ECR (`AWS-prescriptive`)
- https://docs.github.com/en/code-security/code-scanning — GitHub code scanning
- https://docs.oasis-open.org/sarif/sarif/v2.1.0/sarif-v2.1.0.html — SARIF v2.1.0 spec
- https://github.com/GoogleContainerTools/distroless — distroless base images
- https://docs.aws.amazon.com/linux/al2023/ug/minimal-container.html — Amazon Linux 2023 minimal container
- https://docs.github.com/en/code-security/dependabot/dependabot-version-updates/configuration-options-for-the-dependabot.yml-file — dependabot.yml reference

**Python tooling:**

- https://docs.pytest.org/en/stable/ — pytest docs root
- https://docs.pytest.org/en/stable/how-to/fixtures.html — pytest fixtures
- https://docs.pytest.org/en/stable/how-to/parametrize.html — pytest parametrize
- https://docs.pytest.org/en/stable/reference/customize.html — pytest configuration (pyproject.toml)
- https://docs.pytest.org/en/stable/how-to/monkeypatch.html — pytest monkeypatch
- https://docs.pytest.org/en/stable/how-to/tmp_path.html — pytest tmp_path
- https://docs.pytest.org/en/stable/how-to/capture-stdout-stderr.html — pytest capsys / capture
- https://docs.pytest.org/en/stable/how-to/mark.html — pytest markers
- https://pypi.org/project/pytest-cov/ — pytest-cov
- https://pypi.org/project/pytest-xdist/ — pytest-xdist
- https://docs.getmoto.org/ — moto (v5 unified `mock_aws()`)
- https://github.com/microsoft/knack — knack repo
- https://github.com/microsoft/knack/blob/dev/docs/commands.md — knack commands doc
- https://github.com/microsoft/knack/blob/dev/docs/arguments.md — knack arguments doc
- https://github.com/microsoft/knack/blob/dev/docs/help.md — knack help authoring
- https://github.com/microsoft/knack/blob/dev/docs/output.md — knack output formats
