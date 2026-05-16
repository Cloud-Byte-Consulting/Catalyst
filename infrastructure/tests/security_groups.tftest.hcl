run "default_private_mode" {
  command = plan
  variables {
    vpc_id        = "vpc-1234"
    exposure_mode = "private"
  }
  assert {
    condition     = true
    error_message = "private mode should not create public ingress"
  }
}