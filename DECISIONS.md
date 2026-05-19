# Decisions

Catalyst architectural decisions are maintained as ADRs in `docs/ADR/`.

- `ADR-006`: CI/CD pipeline architecture
- `ADR-007`: Golden path API contracts
- `ADR-008`: IAM-based RBAC model
- `ADR-009`: Runtime strategy (Lambda default, ECS option)
- `ADR-010`: Egress controls and firewall tiers
- `ADR-012`: Onboarding experience (three audience tracks)
- `ADR-013`: Guided milestone orchestration (console-first; GitHub Issue as system of record)
- `ADR-016`: Customer-managed KMS key strategy — CMK at rest for DynamoDB, ECR, and CloudWatch log groups; see `docs/ADR/ADR-016-cmk-key-strategy.md`
- `ADR-019`: Aurora Serverless v2 with IAM-auth Postgres for the catalyst-api `/deployment-history` endpoint; see `docs/ADR/ADR-019-aurora-serverless-iam-auth.md` (numbering skips 018 to dodge the 016/017/018 collision introduced by PR #233 — see ADR-019 §Numbering note)
- `ADR-020`: Catalyst homelab deployment (placeholder — self-hosted / lab target; see `docs/ADR/ADR-020-catalyst-homelab-deployment.md`; renumbered from ADR-016 per #257)
- `ADR-021`: Migration from GitHub to self-hosted Gitea (placeholder — future forge track; see `docs/ADR/ADR-021-migration-github-to-gitea.md`; renumbered from ADR-017 per #257)
