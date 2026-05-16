# AI Workflow Narrative

## What worked

- Issue-driven execution with Context/Scope/Gherkin acceptance criteria produced reviewable outputs.
- ADR alignment (006-010) provided clear constraints for runtime, RBAC, and egress design.
- Continuous verification gates (`terraform validate`, `pytest --cov-fail-under=85`) reduced integration drift.

## Where AI was course-corrected

- Shifted RBAC enforcement to application-layer checks to match ALB front-door architecture.
- Added explicit runtime branching (`RUNTIME=lambda|ecs`) in deployment workflow.
- Added resource visibility filtering for tenant/project-scoped support groups.

## How to improve

- Add automated issue comment checks to enforce decision-log section headings.
- Add snapshot tests for workflow YAML and issue templates.
- Add synthetic load tests to compare Lambda vs ECS runtime behavior before switching defaults.
