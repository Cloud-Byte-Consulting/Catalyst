<!-- AUTO-GENERATED from skills/network-segmentation/SKILL.md — do not edit here. Run scripts/sync_tool_skills.py to regenerate. -->
---
name: network-segmentation
description: >
  VPC design with private subnets for ECS/Aurora/Lambda, public subnets for
  ALB only, security group least-privilege, WAF rate limiting, CloudFront
  edge security, VPC endpoints for AWS service access, and single NAT gateway
  architecture. Use when designing or reviewing network infrastructure.
---
<!-- Vendored from: platform-catalyst/.cursor/skills/network-segmentation/SKILL.md (BittahCriminal/platform-catalyst, BSD-3-Clause). Adapted for Catalyst: PLAN.md/CLAUDE.md/DECISIONS.md scrubbed; ADR-008->ADR-001, ADR-009->ADR-002. -->


## Role

Network security specialist for the Catalyst IDP. You design and review all
VPC architecture, subnet placement, security group rules, edge security, and
service connectivity patterns. You enforce the CSPM (Nomani, Packt 2024)
principles of landing zone design and network isolation.

## Instructions

### VPC layout

Use a three-tier VPC pattern (public, private-app, private-data) across at
least two availability zones. The CIDRs below are an example baseline and
must be parameterized per environment:

| Tier | Purpose | Subnet CIDR (AZ-a) | Subnet CIDR (AZ-b) | Internet access |
|---|---|---|---|---|
| **Public** | ALB, NAT Gateway | `10.40.0.0/24` | `10.40.1.0/24` | Internet Gateway |
| **Private-app** | ECS tasks, Lambda | `10.40.10.0/24` | `10.40.11.0/24` | NAT Gateway (egress only) |
| **Private-data** | Aurora, ElastiCache | `10.40.20.0/24` | `10.40.21.0/24` | None |

- Only the ALB resides in public subnets. No compute workloads face the
  internet directly.
- Private-data subnets have no route to the internet. AWS service access is
  via VPC endpoints only.

### VPC endpoints

Minimize NAT Gateway data processing charges and reduce attack surface by
using VPC endpoints:

- **Gateway endpoints** (free): S3, DynamoDB.
- **Interface endpoints** (per-hour + per-GB): Secrets Manager, SSM, ECR API,
  ECR Docker, CloudWatch Logs, STS, Bedrock Runtime, KMS.

Each interface endpoint gets a security group allowing inbound HTTPS (443)
from the private-app and private-data security groups only.

### Security group patterns

- **ALB SG**: Inbound 443 from `0.0.0.0/0` (CloudFront IP ranges preferred
  via prefix list). Outbound to ECS SG on the application port only.
- **ECS SG**: Inbound from ALB SG on the application port. Outbound to
  Aurora SG on 5432, to VPC endpoint SGs on 443, and to NAT Gateway for
  external API calls.
- **Aurora SG**: Inbound from ECS SG on 5432 only. No outbound internet access.
- **VPC Endpoint SG**: Inbound 443 from ECS SG and Lambda SG. No other ingress.
- **Lambda SG**: Outbound to Aurora SG on 5432 and to VPC endpoint SGs on 443.

Reference security groups by ID, not CIDR blocks, for all intra-VPC rules.

### WAF rules

AWS WAF is attached to both CloudFront and the ALB:

- **Rate limiting**: 2000 requests per 5-minute window per IP.
- **Geo-blocking**: Allow US only (adjustable per environment).
- **Managed rule groups**: AWSManagedRulesCommonRuleSet,
  AWSManagedRulesKnownBadInputsRuleSet, AWSManagedRulesSQLiRuleSet.
- **Custom rules**: Block requests with bodies exceeding 8 KB to API endpoints
  that do not expect large payloads.
- WAF logging to CloudWatch Logs for analysis and alerting.

### CloudFront edge security

- CloudFront distribution with HTTPS-only viewer protocol policy.
- Origin protocol policy: HTTPS only to ALB.
- Custom header shared secret between CloudFront and ALB to prevent direct
  ALB access (ALB rejects requests missing the header).
- TLS 1.2 minimum on all connections.

### NAT Gateway

- Single NAT Gateway in `public AZ-a` for cost optimization.
- Private-app subnets in both AZs route `0.0.0.0/0` through this single NAT
  Gateway.
- Accept the AZ-a dependency for non-production environments. Production
  environments should evaluate multi-AZ NAT for resilience if the budget
  allows.

## Output

- Terraform VPC module with subnet definitions, route tables, and NAT Gateway.
- Security group resources with explicit ingress/egress rules referencing
  security group IDs.
- VPC endpoint resources with associated security groups and route table
  associations.
- WAF web ACL with rate limiting, geo-blocking, and managed rule groups.
- CloudFront distribution with origin access and custom header validation.

## Guardrails

- Never place compute workloads (ECS, Lambda) in public subnets.
- Never use `0.0.0.0/0` in security group ingress rules except for the ALB
  on port 443.
- Never use CIDR-based security group rules for intra-VPC traffic when
  security group references are available.
- Never allow private-data subnets to route to the internet.
- Never skip WAF attachment on internet-facing resources.
- Never use TLS versions below 1.2.
- Never hardcode CIDR blocks in security group rules; use variables or data
  sources.
