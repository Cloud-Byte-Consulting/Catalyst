---
name: draw-aws-diagrams
description: Author AWS architecture diagrams in Draw.io for the Catalyst repo. Use when the user asks for a .drawio diagram, a new architecture view, or wants to extend diagrams/. Covers two modes (MCP-bridge to a live browser canvas, or hand-authored .drawio XML), the AWS shape-style strings that actually work, and the VPC → AZ → subnet → resource group hierarchy used across Catalyst diagrams.
---

# draw-aws-diagrams

Catalyst-specific skill for authoring AWS architecture diagrams in Draw.io. The repo's `diagrams/` directory holds the source-of-truth for architecture; this skill keeps new diagrams consistent with the existing set (`network-layer.drawio`, `application-layer.drawio`, `agentic-workflow.drawio`, and the three Mermaid diagrams `control-plane.md`, `ha.md`, `gitops.md`).

## When to use this skill

- User asks for a `.drawio` diagram of any Catalyst component
- User wants to extend `diagrams/` with a new view (compliance tier, runtime variant, data flow)
- A PR touches `infrastructure/modules/` substantially enough that the architecture diagrams need a follow-up

Do not use this skill for:
- Mermaid diagrams (use the Mermaid Chart MCP directly; they render inline in GitHub but Draw.io files don't)
- One-off sketches in PR bodies (Mermaid is the right tool — it renders in GitHub markdown)
- Per-environment diagrams — Catalyst diagrams are environment-agnostic by convention

## Two authoring modes

### Mode A: Hand-authored XML (default — always works)

Write the `.drawio` file directly with the Write tool. Files are XML and open in any Draw.io editor (browser at app.diagrams.net, VS Code Draw.io extension, IDE plugin). This mode requires zero MCP setup and produces committable artifacts immediately.

Use this mode when:
- The MCP bridge isn't available (no browser tab connected, schema-empty issue)
- The diagram is mostly structural (groups, boxes, labels) rather than freeform
- You want a deterministic, reproducible file that diffs cleanly

### Mode B: Live MCP bridge (interactive editing)

The Draw.io MCP server (`drawio-mcp-server` v2.1+) bridges Claude to a live Draw.io browser tab via a WebSocket extension on port 4444. Tools like `add-rectangle`, `add-cell-of-shape`, `add-edge` mutate the open canvas in real time.

Setup prerequisites for Mode B:
1. Both `claude_desktop_config.json` and `~/.claude.json` have the `Draw_io_Diagrams` MCP entry with `--extension-port 4444`
2. Browser extension installed in Chrome/Edge/Brave (Firefox needs TLS mode)
3. Draw.io open in that browser at https://app.diagrams.net/
4. Extension shows "connected" + document registered
5. `mcp__Draw_io_Diagrams__list-documents` returns a non-empty array

**Known limitation (as of 2026-05-18):** This MCP server's tool schemas are empty (`properties: {}`), so the Claude tool-call framework serializes typed values (numbers, nested objects) as strings — which the server then rejects with `expected: number, received: string`. **Until the server publishes complete schemas, Mode A is the only mode that actually produces output.** Re-verify Mode B viability by running `mcp__Draw_io_Diagrams__add-rectangle` with `x: 40, y: 40, width: 120, height: 60` — if it fails with type errors, stay in Mode A.

## Catalyst diagram conventions

### Group hierarchy (top-down)

Every Catalyst diagram nests groups in this order. Each layer uses a specific AWS Groups icon (`mxgraph.aws4.group_*`) and a distinct stroke color:

```
AWS Cloud (mxgraph.aws4.group_aws_cloud_alt, stroke #232F3E)
└── VPC (mxgraph.aws4.group_vpc, stroke #248814)
    └── Availability Zone (mxgraph.aws4.group_az, stroke #147EBA, dashed=1)
        └── Subnet (mxgraph.aws4.group_security_group, stroke #147EBA, dashed=0)
            └── Resource icon (Lambda / ALB / NAT / EIP / etc.)
```

Reasoning: the AWS Groups library doesn't have a dedicated "subnet" shape, so we reuse `group_security_group` (the dashed rectangle) for subnets and color-code by tier:
- Public subnet: `fillColor=#E6F2F8` (light blue)
- Private-app subnet: `fillColor=#F0F8E6` (light green)
- Private-data subnet: `fillColor=#FFFAEB` (light tan)

### Connector conventions

| Use | Style fragment |
|---|---|
| **In-VPC traffic** (ALB → Lambda, etc.) | `strokeColor=#ED7100` (AWS orange), `edgeStyle=orthogonalEdgeStyle`, solid |
| **Private egress** (Lambda → NAT, Lambda → VPC endpoint) | `strokeColor=#147EBA` (AWS blue), `dashed=1` |
| **Internet ingress** (Caller → IGW → ALB) | `strokeColor=#5A6C7D` (slate), `endArrow=classic` |
| **AWS API calls** (Lambda → DynamoDB, Lambda → SSM) | `strokeColor=#5A6C7D`, `dashed=1` |
| **Andon / kaizen flow** (drift → issue) | `strokeColor=#D13212` (AWS red), `dashed=1` |
| **Alternative path** (RUNTIME=ecs swap, deferred features) | `strokeColor=#5A6C7D`, `dashed=8 4` (long-dash) |

All edges use `edgeStyle=orthogonalEdgeStyle` (right-angle routing) unless the diagram is a sequence flow.

### Labeling conventions

- **Resource names** as committed in Terraform (`catalyst-alb`, `catalyst-platform-state`)
- **CIDR blocks** on subnets and the VPC (`10.50.0.0/16`, `10.50.64.0/22`)
- **Pipeline variable names** for things controlled by GitHub Actions (`CATALYST_API_INGRESS_ALLOWLIST`, `CATALYST_LAMBDA_IMAGE_SEEDED`)
- **ADR cross-references** in the legend (`ADR-009 — runtime`, `ADR-010 — egress`)
- **No ARN suffixes or account IDs** — diagrams are environment-agnostic
- Title block at top: `<Subject> — <key-detail> — <region>` (e.g. `Catalyst Network Layer — VPC 10.50.0.0/16 — us-east-1`)
- Subtitle: audience + source-of-truth path (`Audience: cloud engineer. Source: infrastructure/modules/network`)

### Page layout

- Page size `1400 × 900` for the wide views (network, application)
- Page size `1000 × 1200` for vertical-flow views (agentic workflow)
- Title at `y=20`, subtitle at `y=60`, content starts at `y=100`
- Legend block at the bottom (`y=820`, width 400)
- AWS Cloud outer group sits at `x=180, y=100` with `width=1180, height=780` to leave room for an external caller on the left

## Working shape style strings

These are verified working in `diagrams/network-layer.drawio`. Copy verbatim into new diagrams.

### Resource icons (use `add-cell-of-shape` in MCP, or vertex with this style in XML)

| Service | `resIcon` value | Fill color |
|---|---|---|
| Lambda | `mxgraph.aws4.lambda` | `#ED7100` |
| Application Load Balancer | `mxgraph.aws4.application_load_balancer` | `#8C4FFF` |
| NAT Gateway | `mxgraph.aws4.nat_gateway` | `#8C4FFF` |
| Internet Gateway | `mxgraph.aws4.internet_gateway` | `#8C4FFF` |
| Elastic IP | `mxgraph.aws4.elastic_ip_addresses` | `#8C4FFF` |
| DynamoDB | `mxgraph.aws4.dynamodb` | `#3334B9` |
| S3 | `mxgraph.aws4.simple_storage_service` | `#7AA116` |
| ECR | `mxgraph.aws4.elastic_container_registry` | `#ED7100` |
| ECS | `mxgraph.aws4.elastic_container_service` | `#ED7100` |
| Fargate | `mxgraph.aws4.fargate` | `#ED7100` |
| SSM Parameter Store | `mxgraph.aws4.systems_manager_parameter_store` | `#E7157B` |
| Secrets Manager | `mxgraph.aws4.secrets_manager` | `#DD344C` |
| CloudWatch | `mxgraph.aws4.cloudwatch_2` | `#E7157B` |
| IAM Role | `mxgraph.aws4.role` | `#DD344C` |
| KMS | `mxgraph.aws4.key_management_service` | `#DD344C` |
| STS | `mxgraph.aws4.identity_and_access_management_iam_temporary_security_credential` | `#DD344C` |
| Users (caller) | `mxgraph.aws4.users` | `#5A30B5` |

**Full style template** (substitute `RESICON` and `FILLCOLOR`):

```
sketch=0;points=[[0,0,0],[0.25,0,0],[0.5,0,0],[0.75,0,0],[1,0,0],[0,1,0],[0.25,1,0],[0.5,1,0],[0.75,1,0],[1,1,0],[0,0.25,0],[0,0.5,0],[0,0.75,0],[1,0.25,0],[1,0.5,0],[1,0.75,0]];outlineConnect=0;fontColor=#232F3E;gradientColor=none;fillColor=FILLCOLOR;strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=11;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=RESICON;
```

Geometry: `width=60, height=60` for resource icons. Use `labelPosition=right;align=left;spacingLeft=8` when the label needs to sit beside (not below) the icon.

### Group containers

Substitute `GROUPICON` (e.g. `group_vpc`, `group_az`, `group_security_group`, `group_aws_cloud_alt`) and `STROKE` color.

```
points=[[0,0],[0.25,0],[0.5,0],[0.75,0],[1,0],[1,0.25],[1,0.5],[1,0.75],[1,1],[0.75,1],[0.5,1],[0.25,1],[0,1],[0,0.75],[0,0.5],[0,0.25]];outlineConnect=0;gradientColor=none;html=1;whiteSpace=wrap;fontSize=12;fontStyle=0;container=1;pointerEvents=0;collapsible=0;recursiveResize=0;shape=mxgraph.aws4.group;grIcon=mxgraph.aws4.GROUPICON;strokeColor=STROKE;fillColor=none;verticalAlign=top;align=left;spacingLeft=30;fontColor=STROKE;dashed=0;
```

Containers MUST set `container=1` and `collapsible=0`. Set `dashed=1` on AZ groups for the AWS convention.

### Annotation panels (non-AWS-icon callouts)

For things like "VPC Endpoints list", "Security Groups summary", legends:

```
rounded=1;whiteSpace=wrap;html=1;fillColor=#F5F5F5;strokeColor=#5A6C7D;align=left;verticalAlign=top;fontSize=11;spacing=8;fontColor=#232F3E;
```

For warning / red-stroke callouts (e.g. ingress allowlist annotation):
```
text;html=1;strokeColor=#D13212;fillColor=#FBE9E7;align=center;verticalAlign=middle;whiteSpace=wrap;rounded=1;fontSize=9;fontColor=#D13212;fontStyle=2;
```

## Standard .drawio file skeleton

```xml
<mxfile host="app.diagrams.net" type="device" version="24.0.0">
  <diagram name="page-name" id="catalyst-page-id">
    <mxGraphModel dx="1422" dy="864" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="1400" pageHeight="900" math="0" shadow="0">
      <root>
        <mxCell id="0" />
        <mxCell id="1" parent="0" />
        <!-- vertices and edges go here, parent="1" or parent="<group-id>" -->
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
```

For multi-page files, repeat the `<diagram>` element inside `<mxfile>`.

## Anti-patterns

| Pitfall | Fix |
|---|---|
| Resource icon disappears behind a group container | Resource icons must declare `parent="<group-id>"` AND be ordered after the group in the XML. Draw.io renders later-declared cells on top. |
| AZ group has no dashed border | Add `dashed=1` to the AZ group style (AWS convention). Subnets are solid. |
| Edge labels overlap shapes | Use `edgeStyle=orthogonalEdgeStyle` and let Draw.io route; if still cluttered, add `<Array as="points"><mxPoint x="..." y="..."/></Array>` waypoints. |
| Resource icons stretch when group resizes | Set `aspect=fixed` in the resource style (default in the working template above). |
| Connector floats away when shapes move | Use the orthogonal connector and let Draw.io's connection points handle it; do not hardcode `<mxPoint>` source/target unless drawing a stray annotation arrow. |
| Diagram exports as huge PNG with whitespace | Set `pageWidth` and `pageHeight` close to actual content size; use `crop-to-diagram-size` on export. |

## Authoring a new diagram (Mode A — hand-author)

1. **Identify the audience.** Each Catalyst diagram targets a specific reader (network engineer, service developer, interview panel). Title and subtitle name the audience and the source-of-truth path.
2. **Pick a page size.** `1400 × 900` for wide views, `1000 × 1200` for vertical flows.
3. **Draft the group hierarchy first.** AWS Cloud → VPC → AZ → subnet. Place containers with rough geometry; add resources after.
4. **Add resource icons inside their containers.** Use the verified styles above. Set `parent` to the container ID.
5. **Add edges.** Source/target reference the resource cell IDs. Use the connector conventions from the table above.
6. **Add annotation panels** (VPC endpoints list, security groups summary, legend).
7. **Add a legend block at the bottom** citing the relevant ADRs.
8. **Open the file in Draw.io to verify** — manually move shapes if anything overlaps. Re-save.
9. **Commit** as `diagrams/<audience>-layer.drawio` or similar; update `diagrams/README.md`.

## Authoring a new diagram (Mode B — MCP-driven, when schema bug is fixed)

When the Draw.io MCP server publishes proper schemas:

1. Open Draw.io in the browser, confirm extension shows connected
2. Call `mcp__Draw_io_Diagrams__list-documents` to confirm a document is registered
3. Use `mcp__Draw_io_Diagrams__rename-page` to name the current page
4. Use `mcp__Draw_io_Diagrams__add-cell-of-shape` with the shape IDs from the table above
5. Use `mcp__Draw_io_Diagrams__add-edge` to connect cells (source/target by cell ID)
6. Use `mcp__Draw_io_Diagrams__create-page` for additional pages
7. Use `mcp__Draw_io_Diagrams__export-diagram` to save a copy as PNG/SVG for previews

## Reference diagrams in the repo

- `diagrams/network-layer.drawio` — VPC + subnets + NAT + IGW + VPC endpoints + 3 SGs (canonical reference)
- `diagrams/application-layer.drawio` — request path + persistence + runtime switch
- `diagrams/agentic-workflow.drawio` — six-gate contract + issues state machine + peer-review spawn

When starting a new diagram, copy the closest match from these three and edit, rather than starting from a blank template. They embody the conventions in this skill.

## Verification checklist before committing

- [ ] Title and subtitle name the audience and source-of-truth path
- [ ] Every resource icon has a `parent` set to its containing group
- [ ] AZ groups are `dashed=1`; subnets are `dashed=0`
- [ ] Edge colors match the convention table (orange in-VPC, blue private egress, red andon, etc.)
- [ ] Labels include CIDR blocks where applicable
- [ ] Legend block cites relevant ADRs
- [ ] File opens cleanly in Draw.io with no parse errors
- [ ] `diagrams/README.md` index updated with a one-line audience description

## External references

- AWS-icons quick-load URL: https://www.draw.io/?libs=aws4&splash=0
- Draw.io's own AWS-diagrams blog: https://www.drawio.com/blog/aws-diagrams (basics: enabling libraries, templates, z-ordering pitfall)
- AWS Architecture Icons official PDF (search engine: "AWS Architecture Icons Q4 2024") — authoritative source for the shape catalog the `mxgraph.aws4.*` library mirrors
