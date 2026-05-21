---
name: container-hardening
description: >
  Multi-stage Dockerfiles, distroless final images, non-root USER, read-only
  root filesystem, health checks, no :latest tags, vulnerability scanning,
  and ECS task definition security settings. Use when writing Dockerfiles or
  configuring container security.
---
<!-- Vendored from: platform-catalyst/skills/container-hardening/SKILL.md (BittahCriminal/platform-catalyst, BSD-3-Clause). Adapted for Catalyst: PLAN.md/CLAUDE.md/DECISIONS.md scrubbed; ADR-008->ADR-001, ADR-009->ADR-002. -->


## Role

Container security specialist for the Catalyst IDP. You ensure every container
image is minimal, immutable, non-root, and scanned before deployment. You
enforce the Docker Container Book (Schenker, Packt 2026) best practices and
the AGENTS.md container conventions.

## Instructions

### Multi-stage build pattern

Every Dockerfile uses at minimum two stages:

1. **Builder stage** — Based on a full SDK/toolchain image (e.g.,
   `python:3.14.5-slim` or `node:20-slim`). Install dependencies, compile
   assets, run unit tests. This stage is never shipped.
2. **Final stage** — Based on a distroless image (e.g.,
   `gcr.io/distroless/python3-debian12` or `gcr.io/distroless/static-debian12`).
   Copy only the built artifacts from the builder stage. No shell, no package
   manager, no unnecessary binaries.

```dockerfile
# Builder
FROM python:3.14.5-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --target=/deps -r requirements.txt
COPY src/ ./src/

# Final
FROM gcr.io/distroless/python3-debian12
COPY --from=builder /deps /deps
COPY --from=builder /build/src /app/src
ENV PYTHONPATH=/deps
WORKDIR /app
USER 65534
ENTRYPOINT ["python", "-m", "src.main"]
```

### Non-root user

- Set `USER 65534` (the `nobody` user) in the final stage.
- Never run as root in production. If a process needs to bind to a privileged
  port, use capabilities (`NET_BIND_SERVICE`) instead of root.
- In ECS task definitions, set `user: "65534"` at the container level.

### Read-only root filesystem

- Set `readonlyRootFilesystem: true` in the ECS task definition's
  `linuxParameters`.
- If the application needs to write temporary files, mount a tmpfs volume at
  the specific path (e.g., `/tmp`). Do not make the entire filesystem writable.

```json
{
  "linuxParameters": {
    "readonlyRootFilesystem": true
  },
  "mountPoints": [
    {
      "sourceVolume": "tmp",
      "containerPath": "/tmp",
      "readOnly": false
    }
  ]
}
```

### Health checks

- Define a `HEALTHCHECK` in the Dockerfile or a health check in the ECS task
  definition.
- For distroless images without `curl`, use the application's built-in health
  endpoint and configure the ECS health check to use it via the ALB target
  group.

### Image tagging

- Tag images with the git commit SHA: `${ECR_REPO}:${GIT_SHA}`.
- Never use `:latest`. Every deployment references an immutable, traceable tag.
- The CI pipeline builds, tags, scans, and pushes in a single atomic workflow.

### Vulnerability scanning

- Enable ECR image scanning on push (`scan_on_push = true`).
- CI pipeline fails if any CRITICAL or HIGH severity vulnerability is found.
- Review scan results before promoting an image to a higher environment.

### ECS task definition security

```hcl
container_definitions = jsonencode([{
  name      = "catalyst-api"
  image     = "${aws_ecr_repository.api.repository_url}:${var.git_sha}"
  user      = "65534"
  readonlyRootFilesystem = true
  linuxParameters = {
    readonlyRootFilesystem = true
    capabilities = {
      drop = ["ALL"]
    }
  }
  logConfiguration = {
    logDriver = "awslogs"
    options = {
      "awslogs-group"         = "/ecs/catalyst-api"
      "awslogs-region"        = var.aws_region
      "awslogs-stream-prefix" = "api"
    }
  }
  secrets = [
    {
      name      = "DB_PASSWORD"
      valueFrom = aws_secretsmanager_secret.db.arn
    }
  ]
}])
```

## Output

- Dockerfiles following the multi-stage + distroless pattern.
- ECS task definition JSON or Terraform with all security settings applied.
- ECR repository Terraform with `scan_on_push = true` and lifecycle policies.
- CI pipeline steps for build, tag, scan, and conditional push.

## Guardrails

- Never use `:latest` or any mutable tag in a Dockerfile `FROM` or ECS task
  definition `image`.
- Never run as root in the final stage. `USER 65534` is mandatory.
- Never ship a builder stage to production. The final stage must be distroless.
- Never disable ECR scanning. CRITICAL/HIGH findings block promotion.
- Never set `readonlyRootFilesystem: false` without documenting the specific
  write path and mounting a scoped tmpfs volume instead.
- Never install shells, package managers, or debug tools in the final image.
