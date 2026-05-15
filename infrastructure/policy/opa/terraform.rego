package catalyst.terraform

deny[msg] {
  some rc
  rc := input.resource_changes[_]
  rc.type == "aws_iam_policy"
  contains(lower(json.marshal(rc.change.after.policy)), ""action":"*"")
  msg := sprintf("IAM policy wildcard action is not allowed: %s", [rc.address])
}

deny[msg] {
  some rc
  rc := input.resource_changes[_]
  rc.type == "aws_iam_policy"
  contains(lower(json.marshal(rc.change.after.policy)), ""resource":"*"")
  msg := sprintf("IAM policy wildcard resource is not allowed: %s", [rc.address])
}
