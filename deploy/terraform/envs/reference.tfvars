# Reference profile: the full spec topology (Section 9) — multi-AZ, Aurora
# Serverless v2, PrivateLink, COMPLIANCE-mode Object Lock. This exists as
# the documented enterprise architecture. It is validated (`terraform
# validate` / `fmt`) but INTENTIONALLY NEVER APPLIED here — see the repo
# README and the user instruction this was built against: no AWS
# credentials are available in this environment, and this profile's own
# COMPLIANCE-mode Object Lock would make a real bucket impossible to empty
# for the retention period even if it were applied, which is incompatible
# with "this is a teardown exercise."
#
# Estimated cost if actually applied and run for a full 30-day month
# (inherently variable — Aurora Serverless v2 scales with load, this
# assumes light-to-moderate steady traffic, not peak):
#
#   Aurora Serverless v2 (0.5-4 ACU, 2 instances, multi-AZ)   ~$150-300/mo
#   PrivateLink interface endpoints x6 + processing            ~$45-55/mo
#   ALB (base + LCU)                                           ~$16-20/mo
#   ECS Fargate on-demand, 2 tasks x 4 services, multi-AZ       ~$140-150/mo
#   S3 (COMPLIANCE Object Lock, 90-day retention)                ~$5-10/mo
#   DynamoDB (pay-per-request)                                   ~$2-5/mo
#   Secrets Manager (2 secrets)                                  ~$0.80/mo
#   CloudWatch Logs (more services, longer retention)            ~$5-10/mo
#   Cognito (small user pool)                                    ~$0/mo (free tier)
#   SNS + Lambda + Budgets                                       <$1/mo
#   ------------------------------------------------------------
#   TOTAL                                                        ~$370-450/mo
#
# Nowhere near the $25/month demo threshold — deliberately: this profile
# documents what a real, always-on, multi-tenant-ready deployment costs,
# not what a student budget can run continuously. The $25 budget alarm
# still applies (every profile gets one per the standing requirement) and
# would fire almost immediately against this profile's actual spend —
# which is exactly why this profile is never applied outside a deliberate,
# reviewed decision to do so with a much larger budget configured first.

profile_name = "reference"
aws_region   = "us-east-1"
name_prefix  = "blackbox-ref"

az_count           = 3
enable_privatelink = true

use_fargate_spot = false

database_engine_mode = "aurora_serverless_v2"

archive_object_lock_mode           = "COMPLIANCE"
archive_object_lock_retention_days = 90

enable_cognito_console_auth = true

monthly_budget_usd = 25 # deliberately unchanged — see note above; raise this explicitly before ever applying this profile for real
budget_alert_email = ""

model_provider = "bedrock"

mediator_image     = "REPLACE_ME.dkr.ecr.us-east-1.amazonaws.com/blackbox-ref-mediator:latest"
recorder_image     = "REPLACE_ME.dkr.ecr.us-east-1.amazonaws.com/blackbox-ref-recorder:latest"
demo_image         = "REPLACE_ME.dkr.ecr.us-east-1.amazonaws.com/blackbox-ref-demo:latest"
investigator_image = "REPLACE_ME.dkr.ecr.us-east-1.amazonaws.com/blackbox-ref-investigator:latest"
