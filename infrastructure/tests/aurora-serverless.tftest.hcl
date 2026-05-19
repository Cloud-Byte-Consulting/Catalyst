provider "aws" {
  region                      = "us-west-2"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
}

# ---------------------------------------------------------------------------
# Plan-time fixtures (ADR-019 / issue #229).
#
# All runs are command = plan so the test harness doesn't need live AWS
# credentials. The aws_caller_identity / aws_region data sources used by
# the module are overridden so plan-only runs render deterministic ARNs.
# ---------------------------------------------------------------------------

override_data {
  target = data.aws_caller_identity.current
  values = {
    account_id = "123456789012"
    arn        = "arn:aws:iam::123456789012:user/test-runner"
    user_id    = "AIDATESTUSER12345678"
  }
}

override_data {
  target = data.aws_region.current
  values = {
    region = "us-west-2"
  }
}

# ---------------------------------------------------------------------------
# Run 1 — default shape: PostgreSQL 16, serverless v2 0.5-2 ACU, encrypted
# with the supplied CMK, IAM-DB-auth enabled, parameter group attached,
# break-glass secret created.
# ---------------------------------------------------------------------------

run "default_shape" {
  command = plan

  module {
    source = "./modules/aurora-serverless"
  }

  variables {
    name                        = "acme-p1-a1"
    vpc_id                      = "vpc-fixture"
    private_subnet_ids          = ["subnet-aaa", "subnet-bbb"]
    consumer_security_group_ids = ["sg-runtime-1", "sg-runtime-2"]
    kms_key_arn                 = "arn:aws:kms:us-west-2:123456789012:key/abcd-1234-efgh-5678"
  }

  assert {
    condition     = aws_rds_cluster.this.engine == "aurora-postgresql"
    error_message = "Cluster engine MUST be aurora-postgresql per ADR-019."
  }

  assert {
    condition     = aws_rds_cluster.this.engine_mode == "provisioned"
    error_message = "Aurora Serverless v2 requires engine_mode = 'provisioned' with serverlessv2_scaling_configuration."
  }

  assert {
    condition     = aws_rds_cluster.this.engine_version == "16.4"
    error_message = "Default engine_version must be 16.4 (ADR-019 settles on the 16 family)."
  }

  assert {
    condition     = aws_rds_cluster.this.storage_encrypted == true
    error_message = "storage_encrypted MUST be true (encryption at rest, ADR-016)."
  }

  assert {
    condition     = aws_rds_cluster.this.kms_key_id == "arn:aws:kms:us-west-2:123456789012:key/abcd-1234-efgh-5678"
    error_message = "kms_key_id MUST equal the CMK ARN passed in by the composite (the catalyst_data_key)."
  }

  assert {
    condition     = aws_rds_cluster.this.iam_database_authentication_enabled == true
    error_message = "iam_database_authentication_enabled MUST be true — this is the load-bearing flag for the IAM-auth client path."
  }

  assert {
    condition     = aws_rds_cluster.this.port == 5432
    error_message = "PostgreSQL port MUST be 5432."
  }

  assert {
    condition     = aws_rds_cluster.this.database_name == "catalyst"
    error_message = "Default database name must be 'catalyst'."
  }

  assert {
    condition     = aws_rds_cluster.this.master_username == "catalyst_admin"
    error_message = "Master (break-glass) username must be 'catalyst_admin'."
  }

  assert {
    condition     = contains(aws_rds_cluster.this.enabled_cloudwatch_logs_exports, "postgresql")
    error_message = "enabled_cloudwatch_logs_exports must include 'postgresql' for query log shipping."
  }

  assert {
    condition     = aws_rds_cluster.this.serverlessv2_scaling_configuration[0].min_capacity == 0.5
    error_message = "Default Serverless v2 min_capacity must be 0.5 ACU (smallest paid floor)."
  }

  assert {
    condition     = aws_rds_cluster.this.serverlessv2_scaling_configuration[0].max_capacity == 2
    error_message = "Default Serverless v2 max_capacity must be 2 ACU (demo cost cap; bump for prod)."
  }

  assert {
    condition     = aws_rds_cluster_instance.writer.instance_class == "db.serverless"
    error_message = "Writer instance_class must be 'db.serverless' for Aurora Serverless v2."
  }

  assert {
    condition     = aws_rds_cluster_instance.writer.performance_insights_enabled == true
    error_message = "Performance Insights MUST be enabled (issue #229 scope)."
  }

  assert {
    condition     = aws_rds_cluster_instance.writer.performance_insights_kms_key_id == "arn:aws:kms:us-west-2:123456789012:key/abcd-1234-efgh-5678"
    error_message = "Performance Insights KMS key MUST equal the cluster CMK so a single revocation blackholes the data plane."
  }

  assert {
    condition     = aws_rds_cluster_parameter_group.this.family == "aurora-postgresql16"
    error_message = "Cluster parameter group family must match the 16.x engine version."
  }

  assert {
    condition     = aws_db_subnet_group.this.subnet_ids == toset(["subnet-aaa", "subnet-bbb"])
    error_message = "DB subnet group MUST use the supplied private_subnet_ids."
  }

  assert {
    condition     = aws_secretsmanager_secret.master.name == "acme-p1-a1/master-credentials"
    error_message = "Break-glass secret must be named $${name}/master-credentials."
  }
}

# ---------------------------------------------------------------------------
# Run 2 — security-group ingress: ONLY runtime SGs on 5432; no CIDR ingress.
# ---------------------------------------------------------------------------

run "security_group_ingress_only_from_runtime_sgs" {
  command = plan

  module {
    source = "./modules/aurora-serverless"
  }

  variables {
    name                        = "acme-p1-a1"
    vpc_id                      = "vpc-fixture"
    private_subnet_ids          = ["subnet-aaa", "subnet-bbb"]
    consumer_security_group_ids = ["sg-runtime-1"]
    kms_key_arn                 = "arn:aws:kms:us-west-2:123456789012:key/abcd-1234-efgh-5678"
  }

  # The ingress is built via for_each over var.consumer_security_group_ids
  # — assert the rule exists for our sole input SG with the correct
  # port + protocol.
  assert {
    condition     = aws_vpc_security_group_ingress_rule.from_consumer["sg-runtime-1"].from_port == 5432
    error_message = "Ingress rule from_port MUST be 5432."
  }

  assert {
    condition     = aws_vpc_security_group_ingress_rule.from_consumer["sg-runtime-1"].to_port == 5432
    error_message = "Ingress rule to_port MUST be 5432."
  }

  assert {
    condition     = aws_vpc_security_group_ingress_rule.from_consumer["sg-runtime-1"].ip_protocol == "tcp"
    error_message = "Ingress rule ip_protocol MUST be tcp."
  }

  assert {
    condition     = aws_vpc_security_group_ingress_rule.from_consumer["sg-runtime-1"].referenced_security_group_id == "sg-runtime-1"
    error_message = "Ingress rule MUST reference the runtime SG (not a CIDR)."
  }
}

# ---------------------------------------------------------------------------
# Run 3 — engine_version override threads through to the cluster.
# ---------------------------------------------------------------------------

run "engine_version_override" {
  command = plan

  module {
    source = "./modules/aurora-serverless"
  }

  variables {
    name                        = "acme-p1-a1"
    vpc_id                      = "vpc-fixture"
    private_subnet_ids          = ["subnet-aaa", "subnet-bbb"]
    consumer_security_group_ids = ["sg-runtime-1"]
    kms_key_arn                 = "arn:aws:kms:us-west-2:123456789012:key/abcd-1234-efgh-5678"
    engine_version              = "16.6"
  }

  assert {
    condition     = aws_rds_cluster.this.engine_version == "16.6"
    error_message = "engine_version override MUST thread through to aws_rds_cluster."
  }
}

# ---------------------------------------------------------------------------
# Run 4 — validation: kms_key_arn must be a real KMS ARN, not garbage.
# ---------------------------------------------------------------------------

run "rejects_malformed_kms_arn" {
  command = plan

  module {
    source = "./modules/aurora-serverless"
  }

  variables {
    name                        = "acme-p1-a1"
    vpc_id                      = "vpc-fixture"
    private_subnet_ids          = ["subnet-aaa", "subnet-bbb"]
    consumer_security_group_ids = ["sg-runtime-1"]
    kms_key_arn                 = "not-a-real-arn"
  }

  expect_failures = [var.kms_key_arn]
}

# ---------------------------------------------------------------------------
# Run 5 — validation: at least 2 private subnets (Aurora requirement).
# ---------------------------------------------------------------------------

run "rejects_single_subnet" {
  command = plan

  module {
    source = "./modules/aurora-serverless"
  }

  variables {
    name                        = "acme-p1-a1"
    vpc_id                      = "vpc-fixture"
    private_subnet_ids          = ["subnet-only-one"]
    consumer_security_group_ids = ["sg-runtime-1"]
    kms_key_arn                 = "arn:aws:kms:us-west-2:123456789012:key/abcd-1234-efgh-5678"
  }

  expect_failures = [var.private_subnet_ids]
}
