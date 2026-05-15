provider "aws" {
  region                      = "us-west-2"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
}

run "ecs_alb_module_plans" {
  command = plan

  module {
    source = "./modules/ecs-alb"
  }

  variables {
    vpc_id                = "vpc-01234567"
    public_subnet_ids     = ["subnet-aaaa", "subnet-bbbb"]
    alb_security_group_id = "sg-cafebabe"
  }

  assert {
    condition     = aws_lb.this.load_balancer_type == "application"
    error_message = "ECS module must front the cluster with an Application Load Balancer"
  }

  assert {
    condition     = aws_lb_target_group.api.health_check[0].path == "/health"
    error_message = "ALB target group must health-check the /health endpoint (ADR-007)"
  }

  assert {
    condition     = aws_ssm_parameter.ecs_cluster.name == "/catalyst/shared/ecs/cluster/arn"
    error_message = "ECS cluster ARN must publish to documented SSM path"
  }

  assert {
    condition     = aws_ssm_parameter.alb_listener.name == "/catalyst/shared/alb/listener/arn"
    error_message = "ALB listener ARN must publish to documented SSM path"
  }
}
