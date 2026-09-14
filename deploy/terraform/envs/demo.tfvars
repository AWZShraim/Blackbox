# Demo profile: single-AZ, minimal footprint, no PrivateLink. Meant to be
# stood up for a short verification window and torn down (`make destroy`),
# not run continuously — see the cost note below for why that matters.
#
# Estimated cost if left running for a full 30-day month (NOT the plan —
# this is a deploy-verify-teardown exercise per the actual instruction):
#
#   ALB (base + LCU)                         ~$16-20/mo
#   RDS db.t4g.micro, single-AZ, 20GB gp3     ~$13/mo
#   ECS Fargate Spot x4 (0.25vCPU/0.5GB ea.)  ~$8-12/mo
#   S3 (Object Lock, low volume)              ~$1/mo
#   DynamoDB (pay-per-request, low volume)    <$1/mo
#   Secrets Manager (2 secrets)               ~$0.80/mo
#   CloudWatch Logs                            ~$1-2/mo
#   SNS + Lambda + Budgets                     <$1/mo (Budgets: free for the first 2 budgets/account)
#   Data transfer                              ~$1-3/mo (demo traffic dependent)
#   ------------------------------------------------------------
#   TOTAL                                      ~$42-55/mo if run continuously
#
# This is honestly ABOVE the $25/month Budgets alarm threshold if left
# running for a full month — worth being direct about rather than picking
# a smaller instance/component mix just to make the number look better.
# The alarm's real job here is catching *model API* spend (Bedrock/
# Anthropic calls), which is the genuinely unbounded, usage-driven cost —
# fixed infrastructure (ALB/RDS/Fargate) is small, known, and bounded
# upfront regardless of demo traffic. The kill switch disables LIVE runs
# (the model-calling path) when the alarm fires; it does not and cannot
# stop the fixed infrastructure charges, which only `make destroy` does.
# For an actual few-hour deploy-verify-teardown cycle, real incurred cost
# is on the order of $0.10-0.50.

profile_name = "demo"
aws_region   = "us-east-1"
name_prefix  = "blackbox-demo"

az_count           = 1
enable_privatelink = false

use_fargate_spot = true

database_engine_mode = "rds"

archive_object_lock_mode           = "GOVERNANCE" # bypassable, so `make destroy` can actually empty the bucket
archive_object_lock_retention_days = 1

enable_cognito_console_auth = false # the whole point of the demo is no sign-up (Section 8)

monthly_budget_usd = 25
budget_alert_email = "" # set to your email before applying, or leave blank and check the SNS topic manually

model_provider = "bedrock" # keeps model traffic in-account (Section 7); set to "anthropic" + anthropic_api_key to use the direct API instead

# Built and pushed via `make tf-ecr-push` (see deploy/terraform/ecr_push.sh);
# these are placeholders until then.
mediator_image     = "REPLACE_ME.dkr.ecr.us-east-1.amazonaws.com/blackbox-demo-mediator:latest"
recorder_image     = "REPLACE_ME.dkr.ecr.us-east-1.amazonaws.com/blackbox-demo-recorder:latest"
demo_image         = "REPLACE_ME.dkr.ecr.us-east-1.amazonaws.com/blackbox-demo-demo:latest"
investigator_image = "REPLACE_ME.dkr.ecr.us-east-1.amazonaws.com/blackbox-demo-investigator:latest"
