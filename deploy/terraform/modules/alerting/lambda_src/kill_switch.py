"""
The automated half of Section 8's "CloudWatch billing alarm with an
automated kill switch that disables live runs and falls back to recorded
traces." Triggered by the SNS topic AWS Budgets publishes to when the
monthly budget threshold is crossed (see modules/alerting/main.tf).

Flips an SSM Parameter Store value rather than touching ECS directly — the
running mediator/demo tasks poll this parameter
(scenarios/demo/guardrails.py's KillSwitch), so no redeploy is needed and
the effect is visible within one cache TTL (30s).
"""

import os

import boto3

ssm = boto3.client("ssm")

PARAM_NAME = os.environ["KILL_SWITCH_PARAM_NAME"]


def handler(event, context):
    ssm.put_parameter(Name=PARAM_NAME, Value="false", Type="String", Overwrite=True)
    return {"disabled_param": PARAM_NAME}
