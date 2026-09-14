# Console auth for the Investigator (Section 9). Reference profile only —
# the demo profile's Investigator is deliberately public (Section 8: a
# cold visitor must not need to sign up). A real deployment's forensics
# tool, used by actual responders investigating actual incidents, should
# not be open to the internet with no auth at all.

variable "name_prefix" { type = string }

resource "aws_cognito_user_pool" "investigator" {
  name = "${var.name_prefix}-investigator"

  password_policy {
    minimum_length    = 12
    require_uppercase = true
    require_lowercase = true
    require_numbers   = true
    require_symbols   = true
  }

  admin_create_user_config {
    allow_admin_create_user_only = true # invite-only — this is a responder tool, not self-serve signup
  }

  tags = { Name = "${var.name_prefix}-investigator-pool" }
}

resource "aws_cognito_user_pool_client" "investigator" {
  name         = "${var.name_prefix}-investigator-client"
  user_pool_id = aws_cognito_user_pool.investigator.id

  generate_secret                      = true
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "profile"]
  callback_urls                        = ["https://localhost/api/auth/callback/cognito"] # placeholder — replace with the real ALB/domain URL before apply
  supported_identity_providers         = ["COGNITO"]
}

resource "aws_cognito_user_pool_domain" "investigator" {
  domain       = "${var.name_prefix}-investigator"
  user_pool_id = aws_cognito_user_pool.investigator.id
}

output "user_pool_id" { value = aws_cognito_user_pool.investigator.id }
output "client_id" { value = aws_cognito_user_pool_client.investigator.id }
output "domain" { value = aws_cognito_user_pool_domain.investigator.domain }
