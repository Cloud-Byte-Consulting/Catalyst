# Catalyst 6-minute demo script

Interview-panel walkthrough of Catalyst. Goal: prove this is a production-grade
AWS Internal Developer Platform built by AI agents under a disciplined
operating contract. Six minutes with a 0:45 closing buffer (5:15–6:00).

## Pre-demo checklist (5 min before)

```powershell
# Load creds and validate the stack is alive
Get-Content .env | Where-Object { $_ -match '^[A-Z]' } | ForEach-Object {
  $k,$v = $_ -split '=',2; Set-Item -Path "env:$k" -Value $v
}
aws sts get-caller-identity
$tgArn = aws elbv2 describe-target-groups --query 'TargetGroups[?contains(TargetGroupName, `catalyst`)].TargetGroupArn' --output text
aws elbv2 describe-target-health --target-group-arn $tgArn --query 'TargetHealthDescriptions[].TargetHealth.State' --output text
# Expect: healthy
```

Open these tabs in order before starting:

1. `https://github.com/Cloud-Byte-Consulting/Catalyst` (repo root)
2. `https://github.com/Cloud-Byte-Consulting/Catalyst/blob/HEAD/AGENTS.md`
3. `https://github.com/Cloud-Byte-Consulting/Catalyst/pull/147` (peer-review evidence)
4. `https://github.com/Cloud-Byte-Consulting/Catalyst/actions` (CI runs)
5. `https://github.com/Cloud-Byte-Consulting/Catalyst/blob/HEAD/diagrams/control-plane.md`
6. Terminal with creds loaded

## 0:00 — 0:45 · What Catalyst is

> "Catalyst is an AWS-native Internal Developer Platform control plane. A FastAPI
> service behind an OIDC-protected ALB, Terraform infrastructure, IAM-group RBAC,
> all delivered through a CI/CD pipeline that uses GitHub OIDC for AWS access —
> zero long-lived keys."

Show **README → Repository layout** + **Architecture** sections. Click into
`diagrams/control-plane.md` — point at the request path (caller → ALB →
Lambda → DynamoDB/SSM/STS) and the phase-ordering sequence diagram.

## 0:45 — 1:45 · The operating contract

> "What makes this interesting is *how* it was built. Every PR in this repo was
> produced by an AI agent under this contract."

Open `AGENTS.md`. Scroll the six gates:

1. Model decision logging (`### Agent Decision Log` on every issue)
2. RLM trigger at ~50k chars (ADR-004)
3. AWS OIDC only — no long-lived keys (ADR-006)
4. Container security gate (Trivy + SBOM + SARIF)
5. **Pre-PR peer review (mandatory)** — sub-agent spawn before `gh pr create`
6. GitHub MCP secret scanning

> "The contract is enforced by `.github/scripts/validate_workflows.py` in
> CI — a structural regression fails before reaching AWS."

## 1:45 — 3:00 · Evidence — PR #147

Open PR #147. Walk the PR body top to bottom:

- **Context & Scope** sections — concise problem framing.
- **Gherkin acceptance criteria** — three `Given/When/Then` scenarios.
- **Agent Decision Log** — model selection, fallback behavior, rationale.
- **Pre-PR Peer Review section** — sub-agent verdict transcribed.
  Suggestion-disposition table: each finding has ACCEPT/REJECT + rationale.
- **The diff** — 3 added lines. `secrets.*` hoisted from step-level `if:` to
  job-level `env:`. Single-line root cause.

> "Five-line fix. Six-section PR body. That ratio is the contract working."

Briefly show the related issue (linked at top of PR) — labels, state machine
transitions, decision-log comments.

## 3:00 — 4:15 · CI/CD pipelines

Open Actions tab. Point at four workflows running green:

- `pr-checks.yml` — terraform fmt/validate, tflint, tfsec, Checkov, Trivy,
  gitleaks, pytest with `--cov-fail-under=93.83` (223 tests).
- `terraform.yml` — consolidated plan-on-PR + apply-on-release. OIDC role
  pinned to `pull_request` for plan, `ref:refs/heads/release` for apply.
- `service-cd.yml` — image build + push + runtime-switched deploy (`lambda`
  or `ecs` per ADR-009).
- `tf-drift.yml` — nightly at 06:00 UTC; non-zero diff opens an issue tagged
  `state/pending` (andon-cord pattern).

Open `diagrams/gitops.md` if time allows — show the PR → plan comment →
review → apply → deploy → andon flow.

## 4:15 — 5:15 · Live stack

Switch to terminal:

```powershell
$albDns = aws elbv2 describe-load-balancers --names catalyst-alb --query 'LoadBalancers[0].DNSName' --output text
curl "http://$albDns/health"
curl "http://$albDns/openapi.json" | jq '.info.title, .paths | keys'
```

Expect `{"status":"ok"}` and the OpenAPI title + path list.

> "The stack is what you'd expect of a real IDP: VPC with NAT + VPC endpoints
> for private egress (ADR-010), DynamoDB platform-state table, Lambda runtime
> (ECS Fargate available via the `RUNTIME` switch per ADR-009), and an ALB
> with a SigV4-verified RBAC layer (ADR-008)."

**30s — KMS / data-at-rest (ADR-016):**

> "Every Catalyst data surface is encrypted with a customer-managed KMS key, not
> the AWS-managed default. The DynamoDB platform-state table, ECR image
> repository, and CloudWatch log groups all use the same CMK provisioned by
> `infrastructure/modules/kms`. ADR-016 captures the rotation policy and key
> grants. This closes the last two AWS-managed-key gaps from the Option 1 audit."

**30s — Aurora Serverless v2 + IAM-auth Postgres (ADR-019):**

> "Beyond DynamoDB there's an Aurora Serverless v2 cluster — IAM-auth only, no
> static passwords, accessed by the runtime over the VPC endpoint path. It backs
> the `GET /deployment-history` endpoint, so deploy events have a relational
> trail you can join against in SQL. ADR-019 documents the IAM-auth flow and the
> scaling envelope (0.5–2 ACUs in demo, headroom higher in prod)."

**30s — ECS app autoscaling (#235):**

> "When the runtime switch is flipped to ECS, the Fargate service has app
> autoscaling wired: target tracking on CPU and on `ALBRequestCountPerTarget`.
> A traffic burst grows the task count without an operator in the loop, and it
> scales back in once requests drain. This is the scale-out variant in
> `diagrams/ha.md` — the demo runs Lambda, but the production path is wired."

If asked about cost: `teardown-scheduled.yml` runs Mon–Fri 22:00 UTC and
destroys everything except the bootstrap tier. Bootstrap resources cost $0.

## 5:15 — 6:00 · Closing + buffer

> "Decisions are in `docs/ADR/` — eleven ADRs, every one cross-referenced from
> the code or workflows that implement it. Evidence the codebase was produced
> by agents-on-contract is in `docs/ai-workflow-narrative.md` with PR citations."

Anticipated questions:

| Question | One-line answer |
|---|---|
| How do you prevent the agent from yolo-ing? | The six gates in AGENTS.md, enforced by CI plus the pre-PR peer-review sub-agent. See ADR-011. |
| What if the model picks the wrong fix? | Peer-review sub-agent disagreement triggers an issue comment, not a merge. PR #147 is an example: peer-review *upgraded* the diagnosis. |
| Cost story? | Bootstrap tier $0. Demo tier ~$3/day when running; auto-destroyed nightly. Drift detection runs against state at 06:00 UTC daily. |
| Why Lambda over ECS by default? | ADR-009. Cold-start is acceptable for a demo IDP; scale-out path to ECS Fargate is a single variable flip (`RUNTIME=ecs`) with the matching deploy branch in `service-cd.yml`. |
| Security posture? | OIDC-only AWS access (ADR-006), SigV4 + IAM-group RBAC (ADR-008), egress through VPC endpoints with optional Network Firewall for compliance tiers (ADR-010). |
| How do you handle drift? | `tf-drift.yml` cron, opens `state/pending` issues with `type/kaizen` label. Andon-cord pattern from `diagrams/gitops.md`. |

## Recovery playbook (if the stack is down mid-demo)

1. `gh workflow run terraform.yml --ref release` — re-applies in ~3 minutes
2. While it runs: pivot to `docs/ai-workflow-narrative.md` and PR #147 walkthrough
3. If teardown was scheduled and not yet rebuilt: follow `docs/operator-bootstrap.md` §Step 7
