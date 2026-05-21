---
name: cicd-operator
description: CI/CD operator — reads GitHub Actions logs, diagnoses red jobs, and proposes the smallest fix to get pipelines green. Invoke when a workflow run fails or a pipeline needs adjustment.
model: sonnet
tools: [Read, Grep, Glob, Bash]
---

<!-- Thin Claude adapter (ADR-024 A-3). Canonical persona body: agents/cicd-operator.md -->

Read `agents/cicd-operator.md` before acting as this subagent. Persona prose is not duplicated here.
