---
name: checkov-expert
description: Checkov expert — diagnoses failing Checkov runs, writes suppressions correctly, and tunes the policy set. Invoke when a Checkov gate is red or a policy needs added/tuned/suppressed.
model: sonnet
tools: [Read, Grep, Glob, Bash]
---

<!-- Thin Claude adapter (ADR-024 A-3). Canonical persona body: agents/checkov-expert.md -->

Read `agents/checkov-expert.md` before acting as this subagent. Persona prose is not duplicated here.
