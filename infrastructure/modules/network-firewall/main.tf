variable "enabled" {
  type    = bool
  default = false
}

variable "name_prefix" {
  type    = string
  default = "catalyst"
}

variable "vpc_id" {
  type = string
}

variable "subnet_id" {
  type = string
}

resource "aws_sns_topic" "egress_deny" {
  count = var.enabled ? 1 : 0
  name  = "${var.name_prefix}-egress-deny"
}

resource "aws_networkfirewall_rule_group" "fqdn" {
  count    = var.enabled ? 1 : 0
  capacity = 100
  name     = "${var.name_prefix}-egress-fqdn"
  type     = "STATEFUL"

  rule_group {
    rules_source {
      rules_string = <<-EOT
        pass tls any any -> any any (tls.sni; content:"api.github.com"; nocase; sid:100; rev:1;)
        drop tls any any -> any any (tls.sni; content:".github.com"; nocase; sid:200; rev:1;)
        drop tls any any -> any any (tls.sni; content:".amazonaws.com"; nocase; sid:300; rev:1;)
      EOT
    }

    stateful_rule_options {
      rule_order = "STRICT_ORDER"
    }
  }
}

resource "aws_networkfirewall_firewall_policy" "this" {
  count = var.enabled ? 1 : 0
  name  = "${var.name_prefix}-fw-policy"

  firewall_policy {
    stateless_default_actions          = ["aws:forward_to_sfe"]
    stateless_fragment_default_actions = ["aws:forward_to_sfe"]
    stateful_default_actions           = ["aws:drop_strict"]

    stateful_engine_options {
      rule_order = "STRICT_ORDER"
    }

    stateful_rule_group_reference {
      resource_arn = aws_networkfirewall_rule_group.fqdn[0].arn
      priority     = 1
    }
  }
}

resource "aws_networkfirewall_firewall" "this" {
  count               = var.enabled ? 1 : 0
  name                = "${var.name_prefix}-egress-fw"
  firewall_policy_arn = aws_networkfirewall_firewall_policy.this[0].arn
  vpc_id              = var.vpc_id

  subnet_mapping {
    subnet_id = var.subnet_id
  }
}
