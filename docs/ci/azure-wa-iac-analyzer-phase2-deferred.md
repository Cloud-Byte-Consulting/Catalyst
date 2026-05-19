# Azure WA IaC Analyzer — Phase 2 (Deferred per Spike)

**Status:** Deferred per `docs/spike/azure-wa-iac-analyzer-spike.md` (PR #294)

**Issue:** Closes #290
**ADR:** ADR-023 Phase 2 (Azure variant) — see sibling branches for ADR text
**Siblings:** #294 (spike — DEFER verdict), #297 (Azure composite placeholder), #286 (AWS Phase 2 — the active job)

---

## Rationale

The Azure Well-Architected IaC Analyzer Phase 2 work is deferred. Three independent reasons:

1. **No Azure infra to anchor.** This repository currently has no Bicep, ARM, or
   `infrastructure/azure/**` Terraform modules. There is nothing for an analyzer
   job to scan.
2. **No analyzer backend chosen.** The spike (#288 → PR #294) returned DEFER
   without selecting an upstream analyzer (Microsoft WA Review API, third-party
   tool, or in-house parity port of the AWS analyzer). Activating CI before the
   backend is chosen would bake in a contract we will then have to break.
3. **Avoid false-positive CI noise.** A skeleton job today would either no-op on
   every PR (wasted minutes, misleading green checkmark) or fail on every PR
   (false negative that trains reviewers to ignore the signal). Both outcomes
   are worse than absence.

We therefore **do not** add a job to `.github/workflows/pr-checks.yml` in this
PR. Instead we pre-bake the contract so future activation is a small,
mechanical change.

---

## Reserved path filters (for future Phase 2 activation)

When work resumes, the job should trigger on changes to:

```yaml
paths:
  - '**/*.bicep'
  - 'infrastructure/azure/**/*.tf'
  - 'infrastructure/azure/**/*.tfvars'
  - '**/*.armtemplate.json'
  - '**/azuredeploy.json'
  - '**/azuredeploy.parameters.json'
```

Rationale: covers Bicep (native Azure DSL), Terraform under the reserved
`infrastructure/azure/` prefix (mirrors the AWS layout), and ARM templates by
both the explicit `*.armtemplate.json` convention and the canonical
`azuredeploy.json` / `azuredeploy.parameters.json` filenames.

---

## Gating contract (for future Phase 2 activation)

The future job MUST be gated on a repository variable:

| Variable | Type | Required state to run | Behavior when unset/empty |
|---|---|---|---|
| `WA_AZURE_ANALYZER_ENDPOINT` | repo variable | set AND non-empty | job exits cleanly with a neutral "analyzer not configured" notice; no PR check failure |

Pseudocode for the gate (to be implemented in Phase 2):

```yaml
- name: Gate on analyzer endpoint
  id: gate
  run: |
    if [ -z "${{ vars.WA_AZURE_ANALYZER_ENDPOINT }}" ]; then
      echo "skip=true" >> "$GITHUB_OUTPUT"
      echo "WA_AZURE_ANALYZER_ENDPOINT not set — skipping Azure WA analyzer."
    else
      echo "skip=false" >> "$GITHUB_OUTPUT"
    fi
```

The gate ensures that merging the activation PR before the endpoint is
provisioned does not break `pr-checks.yml` on every subsequent PR.

---

## Gherkin scenario mapping — issue #290

All scenarios from issue #290 map to **deferred — not implemented; will be
satisfied when Phase 2 ships**.

| Gherkin scenario (from #290) | Phase 2 status |
|---|---|
| Job runs on PRs touching Azure IaC | Deferred — path filters reserved above |
| Job uploads analyzer findings as PR annotations | Deferred — pending backend selection |
| Job is gated on `WA_AZURE_ANALYZER_ENDPOINT` | Deferred — gating contract documented above |
| Job is non-blocking until ADR-023 graduates from "experimental" | Deferred — to be re-confirmed at activation time |
| Job artifacts retained per ADR-006 retention defaults | Deferred — to be inherited from AWS Phase 2 job (#286) |

None of the above are implemented in this PR. This PR is itself the deferral
record.

---

## Re-open trigger

Re-open this work — by filing a new issue that references this deferral doc —
when **any** of the following becomes true:

- An Azure WA-Analyzer parity backend is chosen and reachable (Microsoft WA
  Review API GA, a vetted third-party tool, or an in-house port of the AWS
  analyzer used by #286).
- The repo gains its first Azure IaC asset (a Bicep file, an ARM template, or
  a module under `infrastructure/azure/`).
- ADR-023 is revised to make the Azure variant mandatory rather than aspirational.

The new issue should:

1. Link back to this file (`docs/ci/azure-wa-iac-analyzer-phase2-deferred.md`).
2. Reference the spike (#288 / PR #294) and its DEFER verdict.
3. Implement the path filters and gating contract documented above
   verbatim — they are the contract this deferral pre-baked.
