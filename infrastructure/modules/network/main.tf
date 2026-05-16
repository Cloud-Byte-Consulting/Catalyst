resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true
}

resource "aws_internet_gateway" "this" { vpc_id = aws_vpc.this.id }

# The log group uses the default AWS-owned KMS key today; CMK rollout is
# tracked alongside the DynamoDB/ECR encryption upgrade described in
# modules/dynamodb and modules/ecr.
# tfsec:ignore:aws-cloudwatch-log-group-customer-key
resource "aws_cloudwatch_log_group" "vpc_flow_logs" {
  name              = "/catalyst/vpc/flow-logs"
  retention_in_days = 30
}

resource "aws_iam_role" "vpc_flow_logs" {
  name = "${var.name_prefix}-vpc-flow-logs-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "vpc-flow-logs.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

# The wildcard is scoped to log streams *inside* the Flow Logs log group only.
# The CloudWatch Logs API does not support log-stream-level ARNs at policy
# attach time (streams are created at runtime by the Flow Logs service); the
# correct AWS-documented pattern is `${log_group_arn}:log-stream:*` and
# `${log_group_arn}` itself for Describe* calls.
# tfsec:ignore:aws-iam-no-policy-wildcards
resource "aws_iam_role_policy" "vpc_flow_logs" {
  name = "${var.name_prefix}-vpc-flow-logs-policy"
  role = aws_iam_role.vpc_flow_logs.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "WriteFlowLogStreams"
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ]
        Resource = "${aws_cloudwatch_log_group.vpc_flow_logs.arn}:log-stream:*"
      },
      {
        Sid    = "DescribeFlowLogGroup"
        Effect = "Allow"
        Action = [
          "logs:DescribeLogGroups",
          "logs:DescribeLogStreams",
        ]
        Resource = aws_cloudwatch_log_group.vpc_flow_logs.arn
      },
    ]
  })
}

resource "aws_flow_log" "this" {
  vpc_id          = aws_vpc.this.id
  traffic_type    = "ALL"
  log_destination = aws_cloudwatch_log_group.vpc_flow_logs.arn
  iam_role_arn    = aws_iam_role.vpc_flow_logs.arn
}

data "aws_region" "current" {}

resource "aws_subnet" "public" {
  for_each          = { for idx, az in var.availability_zones : az => var.public_subnet_cidrs[idx] }
  vpc_id            = aws_vpc.this.id
  cidr_block        = each.value
  availability_zone = each.key
  # The ALB (the only resource in public subnets today) gets its own
  # internet-facing IP via the load_balancer_type=application config;
  # subnet-level auto-assign is not required and is flagged by tfsec
  # aws-ec2-no-public-ip-subnet. NAT gateways here also do not need it.
  map_public_ip_on_launch = false
}

resource "aws_subnet" "private" {
  for_each          = { for idx, az in var.availability_zones : az => var.private_subnet_cidrs[idx] }
  vpc_id            = aws_vpc.this.id
  cidr_block        = each.value
  availability_zone = each.key
}

resource "aws_eip" "nat" {
  for_each = aws_subnet.public
  domain   = "vpc"
}

resource "aws_nat_gateway" "this" {
  for_each      = aws_subnet.public
  allocation_id = aws_eip.nat[each.key].id
  subnet_id     = each.value.id
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }
}

resource "aws_route_table_association" "public" {
  for_each       = aws_subnet.public
  subnet_id      = each.value.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table" "private" {
  for_each = aws_subnet.private
  vpc_id   = aws_vpc.this.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.this[each.key].id
  }
}

resource "aws_route_table_association" "private" {
  for_each       = aws_subnet.private
  subnet_id      = each.value.id
  route_table_id = aws_route_table.private[each.key].id
}

resource "aws_vpc_endpoint" "dynamodb" {
  vpc_id            = aws_vpc.this.id
  service_name      = "com.amazonaws.${data.aws_region.current.region}.dynamodb"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [for rt in aws_route_table.private : rt.id]
}

resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.this.id
  service_name      = "com.amazonaws.${data.aws_region.current.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [for rt in aws_route_table.private : rt.id]
}
