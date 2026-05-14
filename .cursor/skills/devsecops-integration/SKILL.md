---
name: devsecops-integration
description: >-
  Shift-left security in Catalyst's CI/CD pipelines: SBOM generation, dependency
  scanning (pip-audit, npm audit, govulncheck), secret scanning (gitleaks,
  trufflehog), container scanning (trivy, grype), SAST (semgrep, bandit),
  policy-as-code (tfsec, checkov, OPA/Conftest), and vulnerability triage. Use
  when designing CI gates, configuring scanners, or triaging findings.
---
<!-- Vendored from: platform-catalyst/.cursor/skills/devsecops-integration/SKILL.md (BittahCriminal/platform-catalyst, BSD-3-Clause). Adapted for Catalyst: PLAN.md/CLAUDE.md/DECISIONS.md scrubbed; ADR-008->ADR-001, ADR-009->ADR-002. -->


# DevSecOps integration

## Role

You bridge security and CI/CD. You design the **gate order** that catches vulnerabilities before they reach `main`, configure the scanners with sensible severity thresholds, and provide triage guidance when findings appear. You enforce `AGENTS.md`'s "fix the code, don't disable the gate" rule and the zero-wildcard-IAM standard.

## References

### Research

- *Implementing DevSecOps Practices* (Packt) — `local/research/implementingdevsecopspractices.pdf`: shift-left strategy, scanner selection, signal-to-noise tuning, vulnerability management lifecycle, security champions model.
- *Security and Microservice Architecture on AWS* (Packt) — `local/research/securityandmicroservicearchitectureonaws.pdf`: AWS-native security services (GuardDuty, Inspector, Security Hub, Macie), service-to-service mTLS, secrets and KMS, audit logging.
- *Mastering GitHub Actions* (Packt) — `local/research/masteringgithubactions.pdf`: reusable workflows, OIDC, environment protection rules, matrix scans.

### Repo sources of truth

- `AGENTS.md` — security-critical rules: no wildcard IAM, no print, no requests, no shell=True, parameterized SQL, no eval/exec/pickle on untrusted input, no secrets in code/env/logs
- `THREAT-MODEL.md` — AI surface threats (prompt injection, data exfiltration)
- `docs/SECURITY.md` — control inventory and ownership
- `AGENTS.md` §9 — CI workflow ordering

### Related skills

- `@checkov-cloud-image-static-analysis` — Checkov for Terraform/plan + Dockerfile; SARIF, baselines, custom checks under `infrastructure/policies/checkov/`
- `@iam-policy-craft` — generating zero-wildcard policies
- `@secrets-rotation` — Secrets Manager and SSM patterns
- `@container-hardening` — distroless + non-root + read-only rootfs
- `@github-actions-design` — gate ordering in workflows
- `@terraform-native-tests` — module-level assertions

## Challenge alignment

This skill produces evidence for both the **25% Infrastructure & Terraform quality** rubric ("security posture") and the **15% CI/CD & operational maturity** rubric ("pipeline design"). The PDF requires "least-privilege IAM principles, no wildcard policies" — DevSecOps gates enforce this at PR time, not after merge. Per "operational awareness, not checkbox coverage", scanner findings need triage workflows, not just status badges.

## Instructions

### 1. The CI gate ladder

Each PR runs scanners in cost order — cheap first, fail fast:

```
PR opened/synchronized
├── ① Format & lint (ruff, terraform fmt, prettier)              < 30s
├── ② Type check (mypy --strict)                                  < 60s
├── ③ Unit tests (pytest)                                         < 2min
├── ④ Secret scanning (gitleaks)                                  < 30s
├── ⑤ Dependency scanning (pip-audit, npm audit, govulncheck)     < 60s
├── ⑥ SAST (semgrep, bandit)                                      < 2min
├── ⑦ IaC policy (tfsec, checkov, OPA/Conftest)                   < 60s
├── ⑧ Container scan (trivy on built image)                        < 90s
├── ⑨ Terraform native tests (.tftest.hcl)                        < 3min
├── ⑩ Integration tests (moto/localstack)                         < 5min
└── ⑪ Terraform plan + post as PR comment                          < 2min
```

Each gate either **passes** or **blocks the PR**. The CI runs them in parallel where possible, but the ordering reflects what to fix first when multiple gates fail.

### 2. Scanner selection by language

| Concern | Python | TypeScript/Node | Go | Containers | Terraform |
|---------|--------|-----------------|-----|-----------|----------|
| **Secret scan** | gitleaks, trufflehog | gitleaks, trufflehog | gitleaks, trufflehog | — | gitleaks |
| **Dependency vulns** | pip-audit, safety | npm audit, snyk | govulncheck, nancy | trivy | tfsec |
| **SAST** | bandit, semgrep | semgrep, eslint-plugin-security | semgrep, gosec | — | tfsec, checkov |
| **License** | pip-licenses | license-checker | go-licenses | — | — |
| **SBOM** | cyclonedx-python | cyclonedx-node | cyclonedx-gomod | syft | — |
| **IaC policy** | — | — | — | — | tfsec, checkov, OPA/Conftest |

Catalyst is Python-first; TypeScript only in `cli/catalyst/` (Bun). Pin scanner versions in CI to avoid silent rule updates breaking builds.

### 3. Secret scanning (gitleaks)

```yaml
# .github/workflows/security.yml (excerpt)
- name: Secret scan
  uses: gitleaks/gitleaks-action@v2
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
  with:
    config-path: .gitleaks.toml
```

`.gitleaks.toml` allows specific known-safe patterns (e.g., the `JUDGE_LLM_API_KEY` env var name itself, but not values).

**Pre-commit hook** (per-developer):

```yaml
# .pre-commit-config.yaml
- repo: https://github.com/gitleaks/gitleaks
  rev: v8.18.0
  hooks:
    - id: gitleaks
```

### 4. Dependency scanning

**Python** (`pip-audit`):
```yaml
- name: pip-audit
  run: |
    pip install pip-audit
    pip-audit --requirement requirements.txt --strict
```

**Container** (`trivy`):
```yaml
- name: Trivy scan
  uses: aquasecurity/trivy-action@master
  with:
    image-ref: ${{ needs.build.outputs.image-tag }}
    format: sarif
    output: trivy.sarif
    severity: HIGH,CRITICAL
    exit-code: 1
```

Upload SARIF to GitHub code scanning for unified findings view.

### 5. SAST: semgrep + bandit

`bandit` catches Python-specific anti-patterns (the `AGENTS.md` deny-list — shell=True, eval, pickle.loads, SQL injection).

```yaml
- name: Bandit
  run: |
    pip install bandit[toml]
    bandit -c pyproject.toml -r services/
```

```toml
# pyproject.toml
[tool.bandit]
skips = []  # No skips — fix the finding, don't suppress
severity = "medium"
```

`semgrep` covers cross-language patterns and custom rules (e.g., enforce structlog over print).

### 6. IaC policy (tfsec + checkov + OPA)

Three scanners with overlapping coverage — keep all three:

| Scanner | Strength |
|---------|----------|
| **tfsec** | Fast, AWS-focused, good baseline |
| **checkov** | Multi-cloud, more rules, slower |
| **OPA/Conftest** | Custom org policies (Catalyst-specific zero-wildcard rule, construct-tag enforcement) |

Custom OPA policy example (catches wildcard IAM in plan output):

```rego
package terraform.iam

deny[msg] {
  resource := input.resource_changes[_]
  resource.type == "aws_iam_policy"
  doc := json.unmarshal(resource.change.after.policy)
  statement := doc.Statement[_]
  statement.Effect == "Allow"
  is_wildcard(statement.Action)
  msg := sprintf("Wildcard Action in policy %s", [resource.address])
}

is_wildcard(actions) { actions == "*" }
is_wildcard(actions) { actions[_] == "*" }
```

CI step:
```yaml
- name: OPA policy check
  run: |
    terraform plan -out=plan.tfplan
    terraform show -json plan.tfplan > plan.json
    conftest test plan.json --policy infrastructure/policy/opa/
```

### 7. SBOM generation

Every release produces an SBOM (Software Bill of Materials):

```yaml
- name: Generate SBOM (Python)
  run: |
    pip install cyclonedx-bom
    cyclonedx-py requirements -i requirements.txt -o sbom-python.json

- name: Generate SBOM (container)
  uses: anchore/sbom-action@v0
  with:
    image: ${{ needs.build.outputs.image-tag }}
    format: cyclonedx-json
    output-file: sbom-container.json

- name: Upload SBOMs
  uses: actions/upload-artifact@v4
  with:
    name: sbom
    path: sbom-*.json
```

Per *Security and Microservice Architecture on AWS*: SBOMs are the audit trail for "what is running in production." Retain for the compliance window (HIPAA = 6 years).

### 8. Triage: severity thresholds

Not every finding blocks the PR. Use severity policy:

| Severity | Action |
|----------|--------|
| **Critical** | Block PR. Fix or accept-risk via documented exception (PR comment from CODEOWNERS). |
| **High** | Block PR. Fix or downgrade to Medium with justification. |
| **Medium** | Warn (PR comment). Track in backlog. |
| **Low** | Report only. Bulk-triage quarterly. |
| **Info** | Silent. Available in scan output. |

Exceptions are time-bounded (90-day max) and tracked in `docs/security-exceptions.md` with expiry dates and owner.

### 9. AWS-native security services

Per *Security and Microservice Architecture on AWS*, runtime security complements CI scanning:

| Service | Catches |
|---------|---------|
| **GuardDuty** | Anomalous IAM activity, compromised instances, malicious IP communication |
| **Security Hub** | Aggregated findings from GuardDuty, Inspector, Macie, custom |
| **Inspector** | EC2/ECR vulnerability scanning post-deploy |
| **Macie** | S3 data classification (detect PII/PHI leaks) |
| **CloudTrail** | API audit log — every IAM action |
| **Config** | Resource drift from desired state |

For Catalyst: enable Security Hub aggregating GuardDuty + Inspector + Macie. CloudTrail data events on the `catalyst-data` S3 bucket. AWS Config rule for "no wildcard IAM in deployed policies" as runtime defense-in-depth.

### 10. Vulnerability response

When a critical CVE drops (e.g., the next Log4Shell):

1. **Detect**: SBOM diff identifies which Catalyst services include the vulnerable package
2. **Triage**: severity × exposure × exploitability — does Catalyst use the vulnerable code path?
3. **Patch**: dependency update, image rebuild, redeploy
4. **Verify**: trivy/pip-audit on the new image shows no occurrence
5. **Document**: **`type/kaizen`** Issue (and ADR if the response changed a standard)

Time-to-patch SLO: 24h for critical, 7d for high, 30d for medium.

## Output

- **CI workflow YAML**: ordered gates with scanner-specific config
- **Scanner config**: `.gitleaks.toml`, `pyproject.toml [tool.bandit]`, OPA `.rego` policies
- **Triage decision**: severity classification + action recommendation
- **SBOM pipeline**: cyclonedx-python + syft + upload artifact
- **Exception**: time-bounded suppression with justification + expiry

## Guardrails

- **Never disable a gate to ship** — fix the finding or document an exception with expiry (per `AGENTS.md`)
- **Never `--no-verify` a pre-commit hook** — fix the hook failure
- **Never commit a scanner secret** — gitleaks would catch you anyway
- **Critical findings block `main`** — even with admin override, document why in the PR
- **Pin scanner versions** — `gitleaks@v8.18.0`, not `gitleaks@latest`. Silent rule updates break builds at the worst moment.
- **Exceptions expire** — 90-day max, tracked in `docs/security-exceptions.md`, reviewed quarterly
- **One scanner is not enough** — defense in depth: tfsec + checkov + OPA each catch different things
