variable "name" { type = string default = "catalyst-platform-state" }
resource "aws_dynamodb_table" "platform_state" {
  name         = var.name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"
  attribute { name = "pk" type = "S" }
  attribute { name = "sk" type = "S" }
  point_in_time_recovery { enabled = true }
  ttl { attribute_name = "expires_at" enabled = true }
}
output "table_name" { value = aws_dynamodb_table.platform_state.name }
