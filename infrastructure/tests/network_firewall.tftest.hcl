run "disabled_noop" {
  command = plan
  variables {
    enabled   = false
    vpc_id    = "vpc-1234"
    subnet_id = "subnet-1234"
  }
  assert {
    condition     = var.enabled == false
    error_message = "disabled firewall should be no-op"
  }
}