resource "aws_security_group" "alb" {
  name_prefix = "${var.name_prefix}-alb-"
  description = "Catalyst API public ALB - ingress is allowlisted by CIDR (var.alb_ingress_allowlist); egress is scoped to the VPC CIDR so the ALB can only reach in-VPC targets."
  vpc_id      = var.vpc_id

  # The ALB only forwards to in-VPC targets (Lambda VPC config or ECS tasks),
  # so internet egress is not required and would be flagged by tfsec
  # aws-ec2-no-public-egress-sg.
  egress {
    description = "Forward HTTPS to in-VPC targets (Lambda/ECS task ENIs)"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr_block]
  }
}

locals {
  normalized_alb_ingress_cidrs = distinct([
    for entry in var.alb_ingress_allowlist :
    can(cidrhost(trimspace(entry), 0))
    ? trimspace(entry)
    : format("%s/32", trimspace(entry))
  ])
}

resource "aws_vpc_security_group_ingress_rule" "alb_https_allowlisted" {
  for_each = var.exposure_mode == "public-alb" ? {
    for cidr in local.normalized_alb_ingress_cidrs : cidr => cidr
  } : {}

  description       = "Catalyst API ingress allowlist (CATALYST_API_INGRESS_ALLOWLIST)"
  security_group_id = aws_security_group.alb.id
  cidr_ipv4         = each.value
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
}

# Runtime SG egress permits 443 to AWS service endpoints (ECR API + DKR for
# cold-start image pull, CloudWatch Logs, SSM, Secrets Manager). DynamoDB and
# S3 already flow via VPC gateway endpoints. Switching the remaining services
# to PrivateLink interface endpoints is the follow-up to eliminate the
# 0.0.0.0/0 egress entirely; until then this is an explicit, scoped ignore
# (the SG only attaches to the runtime ENIs, not anything that can pivot).
# tfsec:ignore:aws-ec2-no-public-egress-sgr
resource "aws_security_group" "runtime" {
  name_prefix = "${var.name_prefix}-runtime-"
  description = "Catalyst API runtime ENIs (Lambda VPC config / ECS tasks). Ingress is restricted to the ALB SG; egress hits AWS service APIs on 443. Interface endpoint rollout to remove the 0.0.0.0/0 egress is the documented follow-up."
  vpc_id      = var.vpc_id

  egress {
    description = "AWS service API egress (ECR/Logs/SSM/Secrets); interface endpoint rollout tracked separately"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_vpc_security_group_ingress_rule" "runtime_from_alb" {
  description                  = "Allow ALB to forward HTTPS to runtime ENIs"
  security_group_id            = aws_security_group.runtime.id
  referenced_security_group_id = aws_security_group.alb.id
  from_port                    = 443
  to_port                      = 443
  ip_protocol                  = "tcp"
}

resource "aws_security_group" "data" {
  name_prefix = "${var.name_prefix}-data-"
  description = "Catalyst data-plane interface endpoints / private resources. Ingress is restricted to the runtime SG."
  vpc_id      = var.vpc_id
}

resource "aws_vpc_security_group_ingress_rule" "data_from_runtime" {
  for_each                     = toset(var.allowed_runtime_ingress_security_group_ids)
  description                  = "Allow runtime ENIs to reach data-plane endpoints on 443"
  security_group_id            = aws_security_group.data.id
  referenced_security_group_id = each.value
  from_port                    = 443
  to_port                      = 443
  ip_protocol                  = "tcp"
}
