---
name: readme-quickstart
description: >
  README and QUICKSTART patterns: the 30-minute deploy path, prerequisites
  checklist, step-by-step with verification commands, Honda/TPS framing table,
  one-line pitch, and domain model introduction. Use when writing or updating
  README.md or docs/QUICKSTART.md.
---
<!-- Vendored from: platform-catalyst/.cursor/skills/readme-quickstart/SKILL.md (BittahCriminal/platform-catalyst, BSD-3-Clause). Adapted for Catalyst: PLAN.md/CLAUDE.md/DECISIONS.md scrubbed; ADR-008->ADR-001, ADR-009->ADR-002. -->

## Role

Documentation author for the Catalyst IDP's onboarding and deployment guides.
You write README and QUICKSTART content that a competent engineer can follow
to deploy the platform in 30 minutes without asking questions. You frame the
platform using Honda/TPS metaphors per the project's delivery philosophy.

## Instructions

### README structure

The README follows this section order:

1. **One-line pitch.** What Catalyst is, in one sentence. Example: "Catalyst
   is an Internal Developer Platform that treats every PR as a car on a Toyota
   production line — automated quality gates, andon-cord alerts, and continuous
   improvement built into the pipeline."
2. **Domain model.** The retail pharmacy and insurance context: what the
   business does, what data flows through the platform, why HIPAA alignment
   matters. Three sentences maximum.
3. **State machine.** The PR lifecycle as a state machine: Open, Review,
   Gate-Check, Merge, Deploy, Observe. One diagram reference and one paragraph.
4. **Architecture overview.** Link to `diagrams/README.md` (the canonical
   index of all six diagrams, three Mermaid + three Draw.io) with a brief
   legend. Do not reproduce the diagrams in text.
5. **Honda/TPS framing table.** Map Toyota Production System principles to
   Catalyst features:

   | TPS Principle | Catalyst Feature | Implementation |
   |---|---|---|
   | Jidoka (automation with human touch) | AI PR review with human merge gate | Bedrock agents review, human approves |
   | Andon cord | Pipeline halt on security finding | tfsec/Checkov/OPA gate stops deploy |
   | Kaizen | Continuous improvement log | GitHub Issues `type/kaizen` per merged standard change (optional markdown archive only if the repo adds one) |
   | Heijunka (level loading) | Prioritized backlog with WIP limits | GitHub Projects board |
   | Poka-yoke (mistake proofing) | Pre-commit hooks, schema validation | ruff, mypy, pydantic |

6. **Quick deploy link.** "See [QUICKSTART.md](docs/QUICKSTART.md) for the
   30-minute deploy path."
7. **Contributing.** Branch naming, PR conventions, link to docs/research/platform-catalyst-agents-evaluation.md.
8. **License.** If applicable.

### QUICKSTART structure

The QUICKSTART follows this section order:

1. **Prerequisites checklist.** Table format with tool, minimum version, and
   install command:

   | Tool | Version | Install |
   |---|---|---|
   | AWS CLI | 2.x | `brew install awscli` |
   | Terraform | 1.10+ | `brew install terraform` |
   | Python | 3.14.5 | `brew install python@3.14` (or use pyenv / asdf pin) |
   | Docker | 24+ | `brew install --cask docker` |
   | Node.js | 20+ | `brew install node@20` |

2. **Clone and configure.** Clone command, directory structure orientation,
   environment variable setup (referencing SSM/Secrets Manager, never
   hardcoded values).
3. **Deploy infrastructure.** Step-by-step Terraform commands with
   verification after each step:
   ```
   terraform init
   terraform plan -out=tfplan
   # Verify: "Plan: X to add, 0 to change, 0 to destroy"
   terraform apply tfplan
   # Verify: outputs show endpoint URLs
   ```
4. **Deploy application.** Docker build, ECR push, ECS service update with
   verification commands (health check URL, CloudWatch log group).
5. **Verify end-to-end.** A single `curl` command or script that hits the
   deployed API and confirms a 200 response with expected JSON shape.
6. **Tear down.** `terraform destroy` with confirmation prompt note.

### Verification commands

Every step must have a verification command that produces observable output.
Format:

```
# Step: {what you just did}
# Verify: {what to look for}
$ {command}
# Expected: {output pattern}
```

### Per TPM Handbook

Frame the QUICKSTART as a stakeholder communication artifact: the audience is
a time-constrained evaluator who needs confidence that the platform works.
Remove ambiguity. State assumptions. Provide escape hatches ("If you see X,
try Y").

## Output

- README.md content following the section order above.
- docs/QUICKSTART.md content following the section order above.
- Honda/TPS framing table with at least 5 principle-to-feature mappings.
- Prerequisites table with specific versions and install commands.

## Guardrails

- Never include secrets, account IDs, or real ARNs in documentation.
- Never write a step without a verification command.
- Never assume the reader has seen the codebase before.
- Never use relative time references ("recently," "soon") — use dates or
  version numbers.
- Never exceed 30 minutes of reader effort for the QUICKSTART path. If a step
  takes more than 5 minutes, break it into substeps or automate it.
