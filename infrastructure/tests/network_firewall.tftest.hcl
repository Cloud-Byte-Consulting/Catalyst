run "disabled_noop" {
  command = plan
  variables {
    enabled   = false
    vpc_id    = "vpc-1234"
    subnet_id = "subnet-1234"
  }
  assert {
    condition     = true
    error_message = "disabled firewall should be no-op"
  }
}