resource "aws_security_group" "alb" {
  name_prefix = "${var.name_prefix}-alb-"
  vpc_id      = var.vpc_id
  egress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_vpc_security_group_ingress_rule" "alb_https_public" {
  count             = var.exposure_mode == "public-alb" ? 1 : 0
  security_group_id = aws_security_group.alb.id
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
}

resource "aws_security_group" "runtime" {
  name_prefix = "${var.name_prefix}-runtime-"
  vpc_id      = var.vpc_id
  egress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_vpc_security_group_ingress_rule" "runtime_from_alb" {
  security_group_id            = aws_security_group.runtime.id
  referenced_security_group_id = aws_security_group.alb.id
  from_port                    = 443
  to_port                      = 443
  ip_protocol                  = "tcp"
}

resource "aws_security_group" "data" {
  name_prefix = "${var.name_prefix}-data-"
  vpc_id      = var.vpc_id
}

resource "aws_vpc_security_group_ingress_rule" "data_from_runtime" {
  for_each = toset(var.allowed_runtime_ingress_security_group_ids)
  security_group_id            = aws_security_group.data.id
  referenced_security_group_id = each.value
  from_port                    = 443
  to_port                      = 443
  ip_protocol                  = "tcp"
}
