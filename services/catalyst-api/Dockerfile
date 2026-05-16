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
# Once an ALB-fronted Fargate ECS service ships, a sibling Dockerfile (or a
# multi-stage build) can keep the uvicorn entrypoint for that runtime; the
# image_tag_mutability=IMMUTABLE policy on the ECR repo keeps each runtime's
# digest pinned regardless.
FROM public.ecr.aws/lambda/python:3.12

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY catalyst ${LAMBDA_TASK_ROOT}/catalyst

CMD ["catalyst.main.handler"]
