"""
LocalDevBroker: I3 for local development against the synthetic Northwind
backend. There is no real secret to broker — the backend is a SQLite file
the mediator itself resolves — but this still enforces the invariant
structurally: the sandbox receives access only if a credential was minted
for this exact call, scoped by session + tool, with a TTL, and it is
revoked immediately after use. Swap for AwsStsBroker (aws_sts.py) in a real
deployment without touching mediator/core.py.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import uuid
from datetime import datetime, timedelta, timezone

from common.interfaces import ScopedCredential
from scenarios.company.db import db_path as northwind_db_path


class LocalDevBroker:
    def __init__(self, *, signing_key: bytes | None = None, db_path=None) -> None:
        self._signing_key = signing_key or os.environ.get(
            "BLACKBOX_CRED_SIGNING_KEY", "dev-only-not-a-real-secret"
        ).encode()
        self._db_path = db_path
        self._outstanding: dict[str, ScopedCredential] = {}

    async def mint(self, *, session_id, tool_name, risk, ttl_seconds) -> ScopedCredential:
        nonce = uuid.uuid4().hex[:8]
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        signature = hmac.new(
            self._signing_key,
            f"{session_id}:{tool_name}:{nonce}:{int(expires_at.timestamp())}".encode(),
            hashlib.sha256,
        ).hexdigest()[:16]
        credential_ref = f"cred:local:{session_id}:{tool_name}:{nonce}:{signature}"

        db = self._db_path or northwind_db_path()
        credential = ScopedCredential(
            credential_ref=credential_ref,
            secret=str(db),
            expires_at=expires_at,
            metadata={"tool_name": tool_name, "risk": risk, "session_id": str(session_id)},
        )
        self._outstanding[credential_ref] = credential
        return credential

    async def revoke(self, credential_ref: str) -> None:
        self._outstanding.pop(credential_ref, None)

    async def revoke_session(self, session_id) -> None:
        prefix = f"cred:local:{session_id}:"
        for ref in [r for r in self._outstanding if r.startswith(prefix)]:
            self._outstanding.pop(ref, None)

    def is_outstanding(self, credential_ref: str) -> bool:
        cred = self._outstanding.get(credential_ref)
        return cred is not None and cred.expires_at > datetime.now(timezone.utc)
