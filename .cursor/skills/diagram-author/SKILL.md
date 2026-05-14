---
name: diagram-author
description: >
  Architecture diagram conventions for Catalyst: draw.io source files, layer
  separation (network/compute/data/external), color coding by construct level,
  trust zone boundaries, export as PNG+SVG, and the three required diagrams
  (architecture, data flow, deployment pipeline). Use when creating or
  updating diagrams in diagrams/.
---
<!-- Vendored from: platform-catalyst/.cursor/skills/diagram-author/SKILL.md (BittahCriminal/platform-catalyst, BSD-3-Clause). Adapted for Catalyst: PLAN.md/CLAUDE.md/DECISIONS.md scrubbed; ADR-008->ADR-001, ADR-009->ADR-002. -->

## Role

Diagram author for the Catalyst IDP. You create and maintain architecture
diagrams that are load-bearing documentation — they must stay synchronized
with the infrastructure code and be clear enough to anchor a technical
interview discussion. You follow the Platform Engineering for Architects
reference architecture conventions.

## Instructions

### File format

- Source files are draw.io XML (`.drawio`) stored in `diagrams/`.
- Each diagram is exported to both PNG (for GitHub rendering) and SVG (for
  scalable embedding) in the same directory.
- File naming: `{NN}-{slug}.drawio`, `{NN}-{slug}.png`, `{NN}-{slug}.svg`.
- Source files are committed alongside exports. Exports are regenerated in
  the same PR as any source change.

### Three required diagrams

Per AGENTS.md, the Catalyst IDP requires three diagrams:

1. **01-architecture** — Full system architecture showing all AWS services,
   their connections, network boundaries, and external integrations. This is
   the "poster diagram" for the interview.
2. **02-data-flow** — Data flow from external request through CloudFront, ALB,
   ECS, Aurora, Bedrock, and back. Shows PHI-adjacent data paths and
   encryption boundaries.
3. **03-deployment-pipeline** — CI/CD pipeline from git push through GitHub
   Actions, Terraform plan/apply, ECR build/push, ECS deploy, and
   post-deploy verification. Shows quality gates and approval points.

### Layer organization

Each architecture diagram uses four layers:

| Layer | Contents | Vertical position |
|---|---|---|
| **External** | Users, GitHub, external APIs | Top |
| **Network** | CloudFront, WAF, ALB, VPC boundary | Upper-middle |
| **Compute** | ECS tasks, Lambda functions, Bedrock | Lower-middle |
| **Data** | Aurora, DynamoDB, S3, Secrets Manager | Bottom |

Layers flow top-to-bottom, matching the request path from user to data store.

### Color coding by construct level

The Honda Construct hierarchy maps to diagram colors:

| Construct level | Color | Hex | Used for |
|---|---|---|---|
| **Line** (infrastructure spine) | Steel blue | `#4A90D9` | VPC, subnets, networking |
| **Station** (service boundary) | Teal | `#2AA198` | ECS services, Lambda functions |
| **Tool** (individual component) | Amber | `#D9A441` | Specific containers, databases, queues |
| **Quality gate** | Red | `#DC322F` | Pipeline gates, WAF rules, security checks |
| **External** | Gray | `#93A1A1` | Third-party services, user actors |

Apply colors consistently. Use solid borders for deployed resources and dashed
borders for planned/future resources.

### Trust zone boundaries

- Draw explicit trust zone boundaries as dashed rectangles with labels:
  - **Public zone**: CloudFront, WAF (internet-facing).
  - **DMZ**: ALB in public subnets (receives only from CloudFront).
  - **Application zone**: ECS tasks, Lambda in private-app subnets.
  - **Data zone**: Aurora, ElastiCache in private-data subnets.
  - **AWS managed zone**: Bedrock, Secrets Manager, SSM (AWS-operated).
- Trust zone crossings are marked with lock icons and labeled with the
  authentication/authorization mechanism (IAM role, mTLS, shared secret).

### Diagram quality standards

- Every box has a label with the AWS service name and the Catalyst resource
  name (e.g., "ECS: catalyst-api").
- Every arrow has a label with the protocol and port (e.g., "HTTPS/443",
  "PostgreSQL/5432").
- No orphaned boxes. Every resource connects to at least one other resource.
- No crossing arrows where avoidable. Rearrange boxes to minimize crossings.
- Include a legend in each diagram explaining the color coding and trust zone
  notation.

## Output

- draw.io XML source files for each diagram.
- PNG and SVG exports at readable resolution (minimum 1200px wide for PNG).
- Legend included in each diagram or as a separate `00-legend.drawio` file.
- Markdown image references for embedding in documentation:
  `![Architecture](diagrams/01-architecture.png)`

## Guardrails

- Never include real account IDs, ARNs, IP addresses, or secret values in
  diagrams.
- Never let a diagram fall out of sync with the infrastructure code. If a
  Terraform change adds or removes a service, the diagram is updated in the
  same PR.
- Never create a diagram without a source `.drawio` file. Screenshots and
  hand-drawn images are not acceptable.
- Never omit trust zone boundaries from architecture diagrams. Security
  context is not optional.
- Never use unlabeled arrows or boxes. Every element must be identifiable
  without referring to external documentation.
