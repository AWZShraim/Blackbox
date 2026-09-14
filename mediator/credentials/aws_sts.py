"""
AwsStsBroker: I3's enterprise-correct implementation (Section 9). Calls
`sts:AssumeRole` with a session policy scoped to the specific tool call and
a short duration; the resulting credentials are used by the mediator to
execute the call and are never returned to the agent. Role ARN and session
name are recorded as `credential_ref` in the trace — Blackbox is an
authorisation point here, not a secret store.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from common.interfaces import ScopedCredential

# STS enforces a 900s (15 minute) floor on AssumeRole session duration,
# even if the caller asks for less — ttl_seconds below that is clamped up,
# not silently ignored.
STS_MIN_DURATION_SECONDS = 900


def policy_for_tool(tool_name: str, risk: str) -> dict[str, Any]:
    """A minimal IAM session policy scoped to what this one tool call
    needs. This PoC default is deliberately conservative; a real deployment
    maps tool_name -> specific resource ARNs rather than "*"."""
    actions = ["dynamodb:GetItem", "s3:GetObject"]
    if risk in ("high", "critical"):
        actions += ["dynamodb:PutItem", "s3:PutObject"]
    return {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Action": actions,
            "Resource": "*",
            "Condition": {"StringEquals": {"aws:RequestTag/blackbox_tool": tool_name}},
        }],
    }


class AwsStsBroker:
    def __init__(self, *, role_arn: str, client: Any = None) -> None:
        self._role_arn = role_arn
        if client is not None:
            self._client = client
        else:
            import boto3

            self._client = boto3.client("sts")
        self._outstanding: dict[str, ScopedCredential] = {}

    async def mint(self, *, session_id, tool_name, risk, ttl_seconds) -> ScopedCredential:
        session_name = f"bb-{session_id}-{tool_name}-{uuid.uuid4().hex[:8]}"[:64]
        policy = policy_for_tool(tool_name, risk)
        duration = max(STS_MIN_DURATION_SECONDS, ttl_seconds)

        def _assume():
            return self._client.assume_role(
                RoleArn=self._role_arn,
                RoleSessionName=session_name,
                Policy=json.dumps(policy),
                DurationSeconds=duration,
            )

        resp = await asyncio.to_thread(_assume)
        creds = resp["Credentials"]
        credential_ref = f"cred:aws-sts:{self._role_arn}:{session_name}"
        scoped = ScopedCredential(
            credential_ref=credential_ref,
            secret=json.dumps({
                "AccessKeyId": creds["AccessKeyId"],
                "SecretAccessKey": creds["SecretAccessKey"],
                "SessionToken": creds["SessionToken"],
            }),
            expires_at=creds["Expiration"],
            metadata={"role_arn": self._role_arn, "session_name": session_name, "tool_name": tool_name},
        )
        self._outstanding[credential_ref] = scoped
        return scoped

    async def revoke(self, credential_ref: str) -> None:
        # STS session credentials cannot be force-expired short of an IAM
        # policy change on the role; they are short-TTL by construction
        # instead. Dropping the local reference stops the mediator from
        # reusing it, which is the guarantee Blackbox actually makes.
        self._outstanding.pop(credential_ref, None)

    async def revoke_session(self, session_id) -> None:
        prefix = f"bb-{session_id}-"
        stale = [
            ref for ref, c in self._outstanding.items()
            if c.metadata.get("session_name", "").startswith(prefix)
        ]
        for ref in stale:
            self._outstanding.pop(ref, None)
