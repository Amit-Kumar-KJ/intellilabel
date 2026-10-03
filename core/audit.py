"""Phase 9.3: hash-chained, tamper-evident audit ledger.

hash = sha256(prev_hash + canonical_json(event)). Every write in the system goes through `log`.
`verify` recomputes the chain and returns the first broken row (or None).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.models import AuditEvent

GENESIS = "0" * 64


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256(data) -> str:
    if not isinstance(data, (bytes, bytearray)):
        data = (data if isinstance(data, str) else canonical_json(data)).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _event_body(e: AuditEvent) -> dict:
    return {"ts": e.ts, "actor_type": e.actor_type, "actor_id": e.actor_id, "action": e.action, "entity": e.entity,
            "payload": e.payload, "input_hash": e.input_hash, "output_hash": e.output_hash,
            "model_version": e.model_version, "prompt_hash": e.prompt_hash}


def log(session: Session, action: str, entity: str, payload: dict | None = None, actor_type: str = "system",
        actor_id: str = "system", input_hash=None, output_hash=None, model_version=None, prompt_hash=None,
        ts: str | None = None) -> AuditEvent:
    last = session.execute(select(AuditEvent).order_by(AuditEvent.id.desc()).limit(1)).scalar_one_or_none()
    prev = last.hash if last else GENESIS
    e = AuditEvent(ts=ts or datetime.now(timezone.utc).isoformat(timespec="seconds"), actor_type=actor_type,
                   actor_id=actor_id, action=action, entity=entity, payload=json.loads(canonical_json(payload or {})),
                   input_hash=input_hash, output_hash=output_hash, model_version=model_version,
                   prompt_hash=prompt_hash, prev_hash=prev)
    e.hash = sha256(prev + canonical_json(_event_body(e)))
    session.add(e)
    session.flush()
    return e


def verify(session: Session) -> dict:
    prev = GENESIS
    n = 0
    for e in session.execute(select(AuditEvent).order_by(AuditEvent.id)).scalars():
        n += 1
        expected = sha256(prev + canonical_json(_event_body(e)))
        if e.prev_hash != prev or e.hash != expected:
            return {"ok": False, "checked": n, "broken_id": e.id, "action": e.action, "entity": e.entity,
                    "reason": "prev_hash mismatch" if e.prev_hash != prev else "content hash mismatch"}
        prev = e.hash
    return {"ok": True, "checked": n, "broken_id": None}
