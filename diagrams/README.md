# Catalyst architecture diagrams

This directory holds the source-of-truth architecture views for Catalyst, sliced by audience and format.

## The six diagrams

| File | Format | Audience | What it shows |
|---|---|---|---|
| [`control-plane.md`](./control-plane.md) | Mermaid | Reviewer / panel | Request path: caller → ALB → Lambda → DynamoDB/SSM/STS; provisioning tiers (bootstrap vs pipeline); phase-ordering sequence enforced by `terraform.yml` + `service-cd.yml` |
| [`ha.md`](./ha.md) | Mermaid | Site-reliability eng | Multi-AZ ECS topology with Aurora Serverless v2, NAT redundancy, failure-mode coverage. Scale-out variant of ADR-009 (the demo runs Lambda) |
| [`gitops.md`](./gitops.md) | Mermaid | Platform eng | PR → plan comment → review → apply → deploy → andon flow; OIDC role separation per phase; drift becomes `state/pending` issue |
| [`network-layer.drawio`](./network-layer.drawio) | Draw.io XML | Cloud / network eng | VPC 10.50.0.0/16, two AZs, public/private-app/private-data subnets, NAT, IGW, EIP, 12 VPC endpoints panel, three security groups, ALB ingress allowlist annotation |
| [`application-layer.drawio`](./application-layer.drawio) | Draw.io XML | Service developer | ALB → Lambda (Mangum); Lambda → DynamoDB/S3/SSM/Secrets/CloudWatch Logs; SigV4 verification path via STS + IAM `ListGroupsForUser`; dashed alternative to ECS Fargate (`RUNTIME=ecs`) |
| [`agentic-workflow.drawio`](./agentic-workflow.drawio) | Draw.io XML | Interview panel + future agents | Six AGENTS.md gates (codified by ADR-011); Issues state machine; peer-review sub-agent fork; RLM scaffold trigger; OIDC role separation per phase; drift andon flow with worked-example callouts (PR #147 / #115 / #151) |

## Format choice — when to use Mermaid vs Draw.io

**Mermaid** renders inline in GitHub markdown — preferred when the diagram needs to be visible without opening a separate tool (PR bodies, README, issue context). The three Mermaid diagrams above are the "embedded" views.

**Draw.io** (`.drawio` XML) is preferred when:
- The diagram has rich grouping (VPC → AZ → subnet hierarchy) that Mermaid doesn't express cleanly
- AWS-native icon fidelity matters (interview panel, audit context)
- The diagram needs to be edited in a visual tool by mixed-skill collaborators
- The diagram is too dense for a single rendered Mermaid (e.g. agentic-workflow has 30+ nodes and many cross-references)

The three Draw.io files open in: any browser at https://app.diagrams.net/, the Draw.io VS Code extension, or an IDE Draw.io plugin. They do **not** render inline in GitHub.

## Authoring conventions

All Catalyst diagrams (both formats) follow the conventions documented in [`.claude/skills/draw-aws-diagrams/SKILL.md`](../.claude/skills/draw-aws-diagrams/SKILL.md):

- **Group hierarchy:** AWS Cloud → VPC → AZ → subnet → resource. AZ groups are dashed; subnets are solid with tier-coded fills (public blue, private-app green, private-data tan).
- **Connector colors:** AWS orange for in-VPC traffic, blue for private egress, red for andon/kaizen flow, slate for internet ingress, long-dash for alternative paths.
- **Labels:** resource names as committed in Terraform, CIDR blocks where applicable, pipeline-variable names for GitHub-Actions-controlled values, ADR cross-references in the legend.
- **Title block + subtitle** at top: subject, key detail, region, audience, source-of-truth path.
- **Legend block** at the bottom citing the relevant ADRs.

## ADR cross-reference index

Every diagram cites at least one ADR. Reverse index:

| ADR | Diagram(s) where it appears |
|---|---|
| ADR-001 (Issues state machine) | `agentic-workflow.drawio` |
| ADR-002 (Construct hierarchy) | `control-plane.md` (implicit) |
| ADR-003 (Static + ephemeral envs) | `gitops.md` (implicit) |
| ADR-004 (RLM scaffold) | `agentic-workflow.drawio` |
| ADR-005 (Agentic platform engineering pattern) | `agentic-workflow.drawio` |
| ADR-006 (CI/CD pipeline architecture) | `gitops.md`, `agentic-workflow.drawio` |
| ADR-007 (Golden paths) | `application-layer.drawio` |
| ADR-008 (RBAC + SigV4) | `application-layer.drawio` |
| ADR-009 (Runtime strategy) | `application-layer.drawio`, `network-layer.drawio`, `ha.md` |
| ADR-010 (Egress control) | `network-layer.drawio` |
| ADR-011 (Agentic workflow contract) | `agentic-workflow.drawio` |

## Updating a diagram

When `infrastructure/modules/` or `services/catalyst-api/` change in a way that invalidates a diagram:

1. Open the relevant file in Draw.io (for `.drawio`) or your markdown editor (for `.md`)
2. Edit per the conventions in `.claude/skills/draw-aws-diagrams/SKILL.md`
3. Save and commit on a feature branch
4. PR body should cite the upstream module/code change that triggered the diagram update
5. Update this index if a new diagram is added or the audience description changes

## Authoring a new diagram

Use the skill: `.claude/skills/draw-aws-diagrams/SKILL.md`. It documents the two authoring modes (hand-authored XML — always works; live MCP bridge — requires the Draw.io browser extension), working AWS shape style strings for 17+ services, and the standard `.drawio` file skeleton.
