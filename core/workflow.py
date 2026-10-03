"""Phase 9.1-9.2 + 9.5: workflow state machine with gates enforced in code, e-signatures, release package.

DRAFT -> AUTO_VALIDATED -> IN_REVIEW -> APPROVED -> RELEASED ; any review state -> REJECTED (-> new DRAFT)
"""
from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from core import audit
from core.config import RELEASE_DIR
from core.db import absolute
from core.models import Approval, Attribute, ChangeRequest, Finding, Label, Requirement, Sku

STATES = ["DRAFT", "AUTO_VALIDATED", "IN_REVIEW", "APPROVED", "RELEASED", "REJECTED"]
ROLES = ["labeling_engineer", "regulatory_affairs", "quality_assurance", "clinical_safety", "regulatory_affairs_2"]
ROLE_LABELS = {"labeling_engineer": "Labeling engineer", "regulatory_affairs": "Regulatory affairs",
               "quality_assurance": "Quality assurance", "clinical_safety": "Clinical / safety reviewer",
               "regulatory_affairs_2": "Second regulatory reviewer"}
DEMO_PASSWORD = "intellilabel"  # simulated identity check for the prototype (see docs/ai_governance.md)


class GateError(Exception):
    pass


def file_hash(path) -> str:
    return hashlib.sha256(absolute(path).read_bytes()).hexdigest()


def required_roles(session: Session, label: Label) -> list[str]:
    from core.risk import TIER_ROLES

    cr = session.get(ChangeRequest, label.change_request_id) if label.change_request_id else None
    tier = (cr.risk_tier if cr and cr.risk_tier else "High")
    return TIER_ROLES[tier]


def open_findings(session, label_id, severity=None):
    q = select(Finding).where(Finding.label_id == label_id, Finding.status == "open")
    if severity:
        q = q.where(Finding.severity == severity)
    return list(session.execute(q).scalars())


def unexplained_changes(label: Label) -> list[dict]:
    d = label.diff_json or {}
    return [c for c in d.get("changes", []) if c.get("explained") is False and c.get("review") != "accepted"]


def valid_signatures(session, label: Label) -> list[Approval]:
    sigs = session.execute(select(Approval).where(Approval.entity_type == "label", Approval.entity_id ==
                                                  label.label_id, Approval.valid.is_(True))).scalars().all()
    h = file_hash(label.pdf_path)
    good = []
    for a in sigs:
        if a.artefact_hash != h:  # artefact changed after signing -> signature no longer matches
            a.valid = False
            audit.log(session, "signature.invalidated", f"label:{label.label_id}", {"role": a.role,
                                                                                   "reason": "artefact hash changed"})
        else:
            good.append(a)
    return good


def check_gate(session: Session, label: Label, target: str) -> list[str]:
    """Returns the list of reasons the transition is blocked (empty = allowed)."""
    s = label.state
    problems = []
    allowed = {("DRAFT", "AUTO_VALIDATED"), ("AUTO_VALIDATED", "IN_REVIEW"), ("IN_REVIEW", "APPROVED"),
               ("APPROVED", "RELEASED"), ("AUTO_VALIDATED", "REJECTED"), ("IN_REVIEW", "REJECTED"),
               ("APPROVED", "REJECTED"), ("REJECTED", "DRAFT")}
    if (s, target) not in allowed:
        return [f"Transition {s} -> {target} is not allowed"]
    if target == "AUTO_VALIDATED":
        if not label.validation_status:
            problems.append("Compliance run not completed")
        if label.parent_label_id and label.diff_json is None:
            problems.append("Diff against the approved revision not completed")
    if target == "IN_REVIEW":
        crit = [f for f in open_findings(session, label.label_id, "critical")]
        if crit:
            problems.append(f"{len(crit)} open critical finding(s) without a signed waiver")
        unx = unexplained_changes(label)
        if unx:
            problems.append(f"{len(unx)} unexplained artwork change(s) not accepted by a reviewer")
    if target == "APPROVED":
        roles = {a.role for a in valid_signatures(session, label)}
        missing = [r for r in required_roles(session, label) if r not in roles]
        if missing:
            problems.append("Missing signatures: " + ", ".join(ROLE_LABELS[r] for r in missing))
    if target == "RELEASED":
        problems.append("Use the release endpoint: QA release signature and a hashed release package are required")
    return problems


def transition(session: Session, label_id: str, target: str, actor: str, reason: str | None = None) -> Label:
    label = session.get(Label, label_id)
    if label is None:
        raise GateError(f"unknown label {label_id}")
    if target == "REJECTED" and not reason:
        raise GateError("A rejection reason is required")
    problems = check_gate(session, label, target)
    if problems:
        audit.log(session, "workflow.transition_refused", f"label:{label_id}", {"from": label.state, "to": target,
                                                                                "problems": problems}, "user", actor)
        raise GateError("; ".join(problems))
    old = label.state
    label.state = target
    audit.log(session, "workflow.transition", f"label:{label_id}", {"from": old, "to": target, "reason": reason},
              "user", actor)
    return label


def sign(session: Session, label_id: str, role: str, user: str, meaning: str, password: str) -> Approval:
    if password != DEMO_PASSWORD:
        audit.log(session, "signature.refused", f"label:{label_id}", {"role": role, "reason": "bad password"},
                  "user", user)
        raise GateError("Password confirmation failed")
    label = session.get(Label, label_id)
    if label.state != "IN_REVIEW":
        raise GateError(f"Label must be IN_REVIEW to sign (is {label.state})")
    if role not in required_roles(session, label):
        raise GateError(f"Role {ROLE_LABELS.get(role, role)} is not required for this risk tier")
    h = file_hash(label.pdf_path)
    a = Approval(entity_type="label", entity_id=label_id, role=role, user=user, meaning=meaning, artefact_hash=h)
    session.add(a)
    session.flush()
    audit.log(session, "signature.applied", f"label:{label_id}", {"role": role, "meaning": meaning,
                                                                  "artefact_hash": h}, "user", user)
    return a


def waive(session: Session, finding_id: int, reason: str, user: str, role: str, password: str) -> Finding:
    if password != DEMO_PASSWORD:
        raise GateError("Password confirmation failed")
    if not reason or len(reason.strip()) < 10:
        raise GateError("A waiver needs a written justification (10+ characters)")
    f = session.get(Finding, finding_id)
    f.status, f.waiver_reason = "waived", reason
    session.add(Approval(entity_type="waiver", entity_id=str(finding_id), role=role, user=user,
                         meaning="waiver: " + reason[:80], artefact_hash=audit.sha256(f"{f.id}{f.message}")))
    audit.log(session, "finding.waived", f"finding:{finding_id}", {"label": f.label_id, "rule": f.rule_id,
                                                                    "reason": reason}, "user", user)
    return f


def review_change(session: Session, label_id: str, index: int, decision: str, user: str, note: str = "") -> dict:
    label = session.get(Label, label_id)
    d = json.loads(json.dumps(label.diff_json))
    d["changes"][index]["review"] = decision
    d["changes"][index]["review_by"] = user
    d["changes"][index]["review_note"] = note
    label.diff_json = d
    audit.log(session, "diff.change_reviewed", f"label:{label_id}", {"index": index, "decision": decision,
                                                                     "note": note}, "user", user)
    return d["changes"][index]


def release(session: Session, change_id: str, user: str, password: str) -> dict:
    """QA release signature + ZIP (approved PDFs, validation reports, diffs, trace, audit extract, manifest)."""
    if password != DEMO_PASSWORD:
        raise GateError("Password confirmation failed")
    cr = session.get(ChangeRequest, change_id)
    labels = list(session.execute(select(Label).where(Label.change_request_id == change_id,
                                                      Label.state != "REJECTED")).scalars())
    if not labels:
        raise GateError("No labels for this change request")
    not_ready = [lab.label_id for lab in labels if lab.state != "APPROVED"]
    if not_ready:
        raise GateError(f"All labels must be APPROVED before release; not ready: {', '.join(not_ready)}")
    for lab in labels:  # signatures must still match the artefacts
        roles = {a.role for a in valid_signatures(session, lab)}
        missing = [r for r in required_roles(session, lab) if r not in roles]
        if missing:
            lab.state = "IN_REVIEW"
            raise GateError(f"{lab.label_id}: signatures no longer valid ({', '.join(missing)}); back to IN_REVIEW")
    from core.services import trace_report

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    zpath = RELEASE_DIR / f"{change_id}_{ts}.zip"
    manifest = {}
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        def add(arc, data: bytes):
            z.writestr(arc, data)
            manifest[arc] = hashlib.sha256(data).hexdigest()

        for lab in labels:
            add(f"labels/{lab.label_id}.pdf", absolute(lab.pdf_path).read_bytes())
            if lab.validation_report and absolute(lab.validation_report).exists():
                add(f"validation/{lab.label_id}_report.pdf", absolute(lab.validation_report).read_bytes())
            add(f"diff/{lab.label_id}_diff.json", json.dumps(lab.diff_json or {}, indent=1).encode())
        add("trace_report.json", json.dumps(trace_report(session, change_id), indent=1, default=str).encode())
        from core.models import AuditEvent

        evs = [{"id": e.id, "ts": e.ts, "actor": e.actor_id, "action": e.action, "entity": e.entity,
                "hash": e.hash, "prev_hash": e.prev_hash} for e in session.execute(select(AuditEvent)).scalars()
               if change_id in json.dumps(e.payload) or any(lab.label_id in e.entity for lab in labels)
               or change_id in e.entity]
        add("audit_extract.json", json.dumps(evs, indent=1).encode())
        man = json.dumps({"change_request": change_id, "released_by": user, "released_at": ts, "files": manifest},
                         indent=1).encode()
        z.writestr("manifest.json", man)
    manifest_hash = hashlib.sha256(man).hexdigest()
    session.add(Approval(entity_type="release", entity_id=change_id, role="quality_assurance", user=user,
                         meaning="released", artefact_hash=manifest_hash))
    for lab in labels:
        lab.state = "RELEASED"
        if lab.parent_label_id:
            parent = session.get(Label, lab.parent_label_id)
            if parent and parent.state == "RELEASED":
                parent.state = "SUPERSEDED"
        sku = session.get(Sku, lab.sku_id)
        sku.revision = max(sku.revision, lab.revision)
    for a in session.execute(select(Attribute).where(Attribute.change_request_id == change_id)).scalars():
        a.status = "released"
    for r in session.execute(select(Requirement).where(Requirement.change_request_id == change_id)).scalars():
        r.status = "active"
    cr.state = "RELEASED"
    audit.log(session, "release.package_built", f"change_request:{change_id}",
              {"zip": zpath.name, "manifest_sha256": manifest_hash, "labels": [lab.label_id for lab in labels]},
              "user", user)
    return {"zip": str(zpath), "manifest_sha256": manifest_hash, "labels": [lab.label_id for lab in labels]}
