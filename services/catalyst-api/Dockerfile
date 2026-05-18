# Catalyst API container image for the gated AWS Lambda runtime
# (modules/lambda-service, package_type=Image). The previous Dockerfile started
# uvicorn directly, which works for an ECS Fargate task but cannot serve
# Lambda invocations: Lambda's package_type=Image requires the AWS Lambda
# Runtime Interface Client (RIC) so the runtime can drive the
# `catalyst.main.handler` (Mangum) entrypoint via the Lambda Runtime API.
#
# Switching to the AWS-published `public.ecr.aws/lambda/python:3.12` base
# image gives us RIC + the Lambda task root layout for free, and the existing
# `mangum==0.19.0` dependency in requirements.txt already wraps the FastAPI
# app for Lambda. CMD declares the handler module path.
#
# v2 (#167 / ADR-014): the image now bundles the `terraform` binary at
# `/opt/terraform/terraform` and the L4 per-application composite source at
# `/opt/catalyst-app/` so the synchronous onboard flow can shell out to
# `terraform init`/`terraform apply` at request time without downloading a
# binary or fetching module source at runtime. Image grows ~100 MB but
# cold-start adds only the binary's resident-set page-in latency, not a
# network fetch (per ADR-014 §Rationale).

# Stage 1: pull the canonical terraform binary from HashiCorp's official image.
# Pinning to a specific minor (1.15) keeps the bundled binary version aligned
# with what the catalyst-app composite's `required_version = ">= 1.7.0"`
# accepts; bumping requires re-running infrastructure/tests against the new
# binary in CI.
FROM hashicorp/terraform:1.15 AS terraform

# Stage 2: the actual Lambda runtime image.
FROM public.ecr.aws/lambda/python:3.12

# Bundle the terraform binary first; it never changes within an image so its
# layer caches cleanly across Python source changes.
COPY --from=terraform /bin/terraform /opt/terraform/terraform
RUN chmod 755 /opt/terraform/terraform

# Bundle the L4 catalyst-app composite source. catalyst.onboard.provision_app
# writes a per-invocation /tmp working dir containing a tiny `main.tf` that
# does `module "app" { source = "/opt/catalyst-app/" }` — so the module
# source resolves locally inside the Lambda root filesystem rather than via
# git clone at request time. CATALYST_APP_MODULE_SOURCE env var can override
# this path for tests.
COPY infrastructure/modules/composite/catalyst-app /opt/catalyst-app

COPY services/catalyst-api/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY services/catalyst-api/catalyst ${LAMBDA_TASK_ROOT}/catalyst

# Surface the bundled binary + composite locations as env vars so
# catalyst.onboard picks them up by default without per-deploy wiring.
ENV TERRAFORM_BIN=/opt/terraform/terraform \
    CATALYST_APP_MODULE_SOURCE=/opt/catalyst-app/

CMD ["catalyst.main.handler"]
