# Demo session state (Section 9): the app-level in-memory rate limiter and
# outcome tracker in scenarios/demo/guardrails.py and scenarios/demo/main.py
# work for a single process; this table is what the same logic would read
# and write in a real multi-instance deployment, with DynamoDB's native TTL
# doing the "ephemeral, auto-expiring" part of Section 8's abuse guardrails
# instead of an in-process dict.

variable "name_prefix" { type = string }

resource "aws_dynamodb_table" "demo_sessions" {
  name         = "${var.name_prefix}-demo-sessions"
  billing_mode = "PAY_PER_REQUEST" # no capacity to plan for or pay for while idle — right call for spiky demo traffic
  hash_key     = "session_id"

  attribute {
    name = "session_id"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  tags = { Name = "${var.name_prefix}-demo-sessions" }
}

output "table_name" { value = aws_dynamodb_table.demo_sessions.name }
output "table_arn" { value = aws_dynamodb_table.demo_sessions.arn }
