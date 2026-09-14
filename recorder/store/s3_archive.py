"""
Immutable, long-term archive (Section 6.3, Section 9): S3 with Object Lock.
Postgres is the queryable 30-day hot store; this is the durable copy an
investigation can lean on after that window, or export as an incident
package (Section 6.5). Written when a session reaches a terminal or
contained status — see recorder/main.py's drain loop.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Protocol

from common.schema import Trace


class ArchiveStore(Protocol):
    async def archive_trace(self, trace: Trace) -> str: ...


class LocalDiskArchive:
    """Dev/test fallback when ARCHIVE_S3_BUCKET is unset — same interface,
    a local directory instead of a bucket. Never used in a real
    deployment (Section 9 wires S3ObjectLockArchive there)."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    async def archive_trace(self, trace: Trace) -> str:
        path = self._root / f"{trace.session.session_id}.json"
        path.write_text(trace.model_dump_json(indent=2))
        return str(path)


class S3ObjectLockArchive:
    """Real boto3 write. The bucket must already have versioning and
    Object Lock enabled (deploy/terraform — Section 9); this class only
    writes objects, it does not configure the bucket. Re-archiving the same
    session creates a new object version rather than failing — Object Lock
    protects against deletion within the retention window, not against a
    newer version being written."""

    def __init__(self, bucket: str, *, prefix: str = "traces", client=None) -> None:
        self._bucket = bucket
        self._prefix = prefix
        self._client = client if client is not None else _default_s3_client()

    async def archive_trace(self, trace: Trace) -> str:
        key = f"{self._prefix}/{trace.session.session_id}.json"
        body = trace.model_dump_json(indent=2).encode()

        def _put() -> None:
            self._client.put_object(Bucket=self._bucket, Key=key, Body=body, ContentType="application/json")

        await asyncio.to_thread(_put)
        return f"s3://{self._bucket}/{key}"


def _default_s3_client():
    import boto3

    return boto3.client("s3")
