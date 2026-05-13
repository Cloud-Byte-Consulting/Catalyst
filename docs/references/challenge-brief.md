# Senior Platform Engineer — code challenge (reference extract)

This file is a **structured text extract** of the employer challenge PDF committed
alongside Catalyst. It exists so requirements can cite stable sections without
parsing binary PDF in tooling. If the canonical PDF is updated, refresh this
extract to match.

**Canonical binary:** [Senior-Platform-Engineer-Project.pdf](./Senior-Platform-Engineer-Project.pdf)

---

## About

- Spend the time you need; quality and thoughtful decisions over raw completeness.
- AWS account required (free tier acceptable).
- Push code to a **GitHub** repository the reviewers can access **read-only**; maintain good Git practices.
- Review session focuses on design decisions, trade-offs, and improvements.

### Team values (from brief)

- Clean and concise code (style and structure).
- Simple architectures sustainable long term.
- Automation.
- Observability (monitoring, logging, alerting, telemetry).
- Immutable infrastructure.
- Iterative value delivery (MVP then improve).
- Leverage AI in development workflows.

### Current stack (examples)

- DevEx: GitHub, GitHub Actions, Claude Code, etc.
- Client and services: JavaScript, TypeScript, Java, React, Node, Python, etc.
- Infrastructure: Terraform, AWS (ECS, Lambda, CloudFront, S3, ElastiCache, RDS, SSM, etc.).
- CI/CD: any public source control with a **visible CI workflow** is acceptable (e.g. GitLab); bonus for skills in listed technologies.

---

## Rubric (evaluation weights)

| Area | Weight | What they evaluate |
|------|-------:|---------------------|
| Automation service | 30% | Code quality, error handling, architecture, developer experience |
| Infrastructure design and Terraform quality | 25% | Module structure, testing, idiomatic HCL, security posture |
| AI-native development workflow | 20% | AI as collaborator, not just mentioned |
| CI/CD and operational maturity | 15% | Pipeline design, observability, deployment strategy |
| Communication and documentation | 10% | README, design rationale, diagram quality, commit history |

---

## Your mission

**Core challenge is mandatory.** Choose **one or more additional** (“digging deeper”) challenges. Minimum bar: **core + at least one option.**

---

## Core challenge — numbered in brief

### 1. AI-native development workflow

- Use AI tools (Claude Code, Copilot, Cursor, or similar) as a **core** part of development.
- **Include** agent configuration in the repo (e.g. `CLAUDE.md`, custom instructions, MCP configs, or equivalent).
- **Leave at least one pull request open** showing AI-assisted process (commits, conversation, iteration).
- Interview: what worked, course-corrections, how you would improve the workflow.

### 2. Terraform and CI/CD

- Deploy **all workloads** via Terraform through a **CI/CD pipeline** of your choice.
- Terraform: reusable modules as needed; **Terraform Tests** in one or more modules verifying required configuration; pipeline for deploying Terraform; **least-privilege IAM**, **no wildcard policies**; secrets via **SSM Parameter Store**, **Secrets Manager**, or similar (**no hardcoded secrets**).

### 3. Automation service (primary focus)

- Build a service on **ECS Fargate or Lambda** supporting a common platform or developer workflow (“platform-as-a-product”).
- Language of your choice.
- **Service requirements:** input validation and robust error handling; **containerized** (Dockerfile) or Lambda packaging; exposed via **load balancer**, **REST API Gateway**, or **CloudFront**; demonstrable in technical interview; **observability** (structured logging, CloudWatch alarms with SNS for key metrics, or a simple dashboard) — operational awareness, not checkbox coverage.
- **Persist important data** to at least one of: **S3**, **DynamoDB**, **RDS Aurora PostgreSQL** (cluster).

### 4. Documentation

- **README:** deploy steps and explanation of what you built.
- **Design rationale:** 1–2 paragraphs on a key design decision and alternatives (README or separate `DECISIONS.md`).
- **Technical diagram:** draw.io or similar; commit image and/or raw file (e.g. `.xml`) under **`diagrams/`**.

---

## Digging deeper — pick at least one

| Option | Summary |
|--------|---------|
| **1** | More complex Terraform: modules everywhere, CMK encryption at rest, encryption in transit, logging, serverless RDS queried by app, autoscaling, automated IaC checks in CI. |
| **2** | AI maturity: **Bedrock** in containerized service, safe AI usage, multiple AI tasks together, AI for PR reviews + sample PR (may include intentionally bad code). |
| **3** | Dev skills in app: stronger application code, data layer, **IAM auth to Postgres** (or other data layer), health checks in service and infrastructure. |
| **4** | Operational intelligence: **Python or Go** tool aggregating platform ops data (examples: GHA history, S3 encryption/logging audit, IAM role usage, CW log ingestion, resource inventory). |
| **5** | More detailed diagram(s): e.g. production-ready GitOps or HA secure architecture. |
| **6** | Something else cool: combination or variation. |

---

## Follow-up interview expectations

- Screen share functioning solution.
- Walk through design and code.
- Baseline: brief CLI/coding exercise **without** AI.
- AI workflow demo: extend service, debug, or write module **live** with AI tools.
- Optional: show deployed environment or screenshots.
