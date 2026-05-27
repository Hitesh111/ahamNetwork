from __future__ import annotations
import uuid
import hashlib


def new_id() -> str:
    return uuid.uuid4().hex[:16]


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]
