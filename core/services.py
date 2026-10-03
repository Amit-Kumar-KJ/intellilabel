"""Application services: the operations the API exposes. Each one writes an audit event."""
from __future__ import annotations

import json
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core import audit
from core.config import EVAL_DIR, REPORT_DIR
from core.db import absolute, active_requirements, load_spec, rel
from core.models import (Approval, Attribute, AuditEvent, ChangeRequest, Finding, Label, LabelElement, Requirement,
                         Sku)


# ---------------------------------------------------------------- change requests
def next_cr_id(session: Session) -> str:
    ids = [c.id for c in session.execute(select(ChangeRequest)).scalars()]
    n = max([int(i.split("-")[1]) for i in ids] + [41])
    return f"CR-{n + 1:04d}"


def create_change_request(session: Session, body: dict, user: str) -> ChangeRequest:
    """body: {"source": "product", "reason", "changes": [...]} or {"source": "regulatory", "reason",
    "requirement": {...requirement row...}}. The user has already confirmed the parsed request."""
    cid = next_cr_id(session)
    source = body.get("source", "product")
    if source == "product":
        payload = {"product": "P-CS", "changes": body["changes"]}
        for ch in body["changes"]:
            skus = [ch["scope"]["sku"]] if "sku" in ch["scope"] else [
                s.sku_id for s in session.execute(select(Sku).where(Sku.product_id == ch["scope"]["product"])).scalars()]
            for sku in skus:
                cur = session.execute(select(func.max(Attribute.version)).where(Attribute.sku_id == sku,
                                                                                 Attribute.key == ch["key"])).scalar()
                session.add(Attribute(sku_id=sku, key=ch["key"], value=str(ch["new"]), version=(cur or 0) + 1,
                                      effective_date=date.today().isoformat(), change_request_id=cid,
                                      status="pending"))
    else:
        req = dict(body["requirement"])
        req.setdefault("retrieved_on", "")
        req.setdefault("verified_by", "UNVERIFIED")
        payload = {"product": "P-CS", "requirement": req}
        # a new legal requirement applies from confirmation: existing labels are checked against it now
        session.merge(Requirement(**{k: req[k] for k in ("requirement_id", "market", "regulation", "section",
                                                          "label_element", "requirement_text", "obligation",
                                                          "applies_if", "packaging_levels", "rule_id", "source_url",
                                                          "retrieved_on", "verified_by")}, status="active",
                                  change_request_id=cid))
    cr = ChangeRequest(id=cid, source=source, reason=body.get("reason", ""), payload=payload, state="OPEN",
                       created_by=user)
    session.add(cr)
    session.flush()
    audit.log(session, "change_request.created", f"change_request:{cid}", {"source": source, "payload": payload},
              "user", user)
    return cr


def impact(session: Session, cid: str, refresh: bool = False) -> dict:
    from engines.impact import analyse

    cr = session.get(ChangeRequest, cid)
    if cr.impact and not refresh:
        return cr.impact
    rep = analyse(session, cr)
    cr.impact = json.loads(json.dumps(rep, default=list))
    cr.risk_score, cr.risk_tier, cr.risk_breakdown = rep["risk"]["score"], rep["risk"]["tier"], rep["risk"]
    audit.log(session, "impact.analysed", f"change_request:{cid}", {"impacted_labels": rep["impacted_labels"],
                                                                   "risk": rep["risk"]["score"],
                                                                   "tier": rep["risk"]["tier"]})
    return cr.impact


def drafts(session: Session, cid: str, plant_unrequested_edit=False, user="system") -> list[dict]:
    from engines.impact import regenerate

    cr = session.get(ChangeRequest, cid)
    impact(session, cid)
    out = regenerate(session, cr, plant_unrequested_edit=plant_unrequested_edit, actor=user)
    cr.state = "DRAFTED"
    return out


# ---------------------------------------------------------------- validation / diff
def validate_label(session: Session, label_id: str, explain: bool = True, user="system") -> dict:
    from engines.compliance import render_report, validate_file
    from engines.llm_gateway import explain_finding

    lab = session.get(Label, label_id)
    spec = load_spec(lab)
    meta = {**spec, "label_id": label_id, "revision": lab.revision}
    rep = validate_file(absolute(lab.pdf_path), meta, reqs=active_requirements(session))
    # keep waivers of identical findings from earlier runs
    old = {(f.rule_id, f.message): f for f in session.execute(select(Finding).where(Finding.label_id ==
                                                                                    label_id)).scalars()}
    session.query(Finding).filter(Finding.label_id == label_id, Finding.status == "open").delete()
    for f in rep["findings"]:
        if explain:
            ex = explain_finding(f, session=None)
            f["explanation"] = ex["explanation"]
            f["explanation_origin"] = ex.get("origin")
        prev = old.get((f["rule_id"], f["message"]))
        if prev and prev.status == "waived":
            f["status"] = "waived"
            continue
        session.add(Finding(label_id=label_id, rule_id=f["rule_id"], requirement_id=f.get("requirement_id"),
                            severity=f["severity"], element=f.get("element"), evidence_bbox=f.get("evidence_bbox"),
                            clause_ref=f.get("clause_ref"), message=f["message"],
                            suggested_fix=f.get("suggested_fix"), explanation=f.get("explanation"), status="open"))
    from engines.compliance import status_of

    rep["status"] = status_of(rep["findings"])
    out_pdf = REPORT_DIR / f"{label_id}_validation.pdf"
    render_report(rep, absolute(lab.png_path), out_pdf)
    lab.validation_status = rep["status"]
    lab.validation_report = rel(out_pdf)
    audit.log(session, "label.validated", f"label:{label_id}", {"status": rep["status"], "findings": len(
        rep["findings"]), "rules": rep["rules_run"]}, "system", user)
    rep.pop("model", None)
    rep["report_pdf"] = rel(out_pdf)
    return rep


def diff_label(session: Session, label_id: str, user="system") -> dict:
    from engines.diff import diff, explainer_for, overlay

    lab = session.get(Label, label_id)
    if not lab.parent_label_id:
        return {"status": "NO_PARENT", "changes": [], "summary": {}}
    parent = session.get(Label, lab.parent_label_id)
    cr = session.get(ChangeRequest, lab.change_request_id) if lab.change_request_id else None
    ex = explainer_for(session, cr, label_id) if cr else None
    res = diff(absolute(parent.pdf_path), absolute(lab.pdf_path), absolute(parent.png_path), absolute(lab.png_path),
               explain=ex)
    ov = overlay(absolute(lab.png_path), res, REPORT_DIR / f"{label_id}_diff.png")
    res["overlay_png"] = rel(ov)
    res["approved_label_id"] = parent.label_id
    prev = lab.diff_json or {}
    # keep reviewer decisions for identical changes
    for c in res["changes"]:
        for pc in prev.get("changes", []):
            if pc.get("review") and pc["element"] == c["element"] and pc["type"] == c["type"]:
                c["review"], c["review_by"] = pc["review"], pc.get("review_by")
    lab.diff_json = json.loads(json.dumps(res, default=str))
    audit.log(session, "label.diffed", f"label:{label_id}", {"status": res["status"], "summary": res["summary"]},
              "system", user)
    return lab.diff_json


def auto_validate_cr(session: Session, cid: str, user="system") -> list[dict]:
    """Run compliance + diff on every draft of a change request and move passing ones to AUTO_VALIDATED."""
    from core.workflow import GateError, transition

    out = []
    for lab in session.execute(select(Label).where(Label.change_request_id == cid, Label.state == "DRAFT")).scalars():
        v = validate_label(session, lab.label_id, user=user)
        d = diff_label(session, lab.label_id, user=user)
        try:
            transition(session, lab.label_id, "AUTO_VALIDATED", user)
            moved = True
        except GateError:
            moved = False
        out.append({"label_id": lab.label_id, "validation": v["status"], "diff": d["status"],
                    "unexplained": d["summary"].get("unexplained_changes", 0), "state": lab.state, "moved": moved})
    return out


# ---------------------------------------------------------------- trace
def trace(session: Session, label_id: str, element_id: str | None = None) -> dict:
    from core.graph import backward, build_product_graph

    lab = session.get(Label, label_id)
    g = build_product_graph(session, label_ids=[label_id])
    els = list(session.execute(select(LabelElement).where(LabelElement.label_id == label_id)).scalars())
    reqs = active_requirements(session)
    from core.regulatory import applicable_requirements

    spec = load_spec(lab)
    app = applicable_requirements(spec, reqs)
    by_el = {}
    for r in app:
        by_el.setdefault(r["label_element"], []).append(r)
    cr = session.get(ChangeRequest, lab.change_request_id) if lab.change_request_id else None
    approvals = [{"role": a.role, "user": a.user, "meaning": a.meaning, "timestamp": str(a.timestamp),
                  "valid": a.valid, "artefact_hash": a.artefact_hash[:16]}
                 for a in session.execute(select(Approval).where(Approval.entity_id == label_id)).scalars()]
    REQ_ALIAS = {"udi_aidc": "udi", "udi_hri": "udi", "manufacturer_symbol": "manufacturer_name_address",
                 "sterilization_symbol": "sterile_indication", "expiry_symbol": "expiry_date",
                 "authorised_rep_symbol": "authorised_rep", "importer_symbol": "importer", "lot_symbol": "lot",
                 "ref_symbol": "model", "notified_body_number": "ce_marking", "language_header": "language_panels"}
    out = []
    for le in els:
        if element_id and le.element_id != element_id:
            continue
        chains = backward(g, f"el:{label_id}:{le.element_id}")
        rq = by_el.get(le.element, []) + by_el.get(REQ_ALIAS.get(le.element, ""), [])
        if le.language:
            rq += by_el.get("language_panels", [])
        out.append({"element_id": le.element_id, "element": le.element, "value": le.value, "bbox": le.bbox,
                    "binding": le.binding_ref, "deps": le.deps,
                    "sources": [" -> ".join(c) for c in chains[:4]],
                    "requirements": [{"id": r["requirement_id"], "clause": f"{r['regulation']} {r['section']}",
                                      "text": r["requirement_text"], "rule": r["rule_id"]} for r in rq],
                    "change_request": {"id": cr.id, "reason": cr.reason} if cr else None,
                    "approvals": approvals})
    return {"label_id": label_id, "elements": out}


def forward_trace(session: Session, sku_id: str, key: str) -> dict:
    from core.graph import build_product_graph, forward

    g = build_product_graph(session)
    fw = forward(g, f"attr:{sku_id}:{key}")
    return {"attribute": f"attr:{sku_id}:{key}", "labels": fw["labels"],
            "elements": [{"node": e, "label_id": g.nodes[e]["label_id"], "element": g.nodes[e]["element"],
                          "value": g.nodes[e]["value"]} for e in fw["elements"]]}


def trace_report(session: Session, cid: str) -> dict:
    labels = [lab.label_id for lab in session.execute(select(Label).where(Label.change_request_id == cid)).scalars()]
    return {"change_request": cid, "labels": {lid: trace(session, lid) for lid in labels}}


# ---------------------------------------------------------------- dashboard / metrics
def dashboard(session: Session) -> dict:
    labs = list(session.execute(select(Label)).scalars())
    crs = list(session.execute(select(ChangeRequest)).scalars())
    fnd = list(session.execute(select(Finding).where(Finding.status == "open")).scalars())
    return {
        "devices": session.execute(select(func.count(Sku.sku_id))).scalar(),
        "labels_released": sum(lab.state == "RELEASED" for lab in labs),
        "labels_total": len(labs),
        "open_changes": sum(c.state not in ("RELEASED", "REJECTED") for c in crs),
        "pending_reviews": sum(lab.state in ("AUTO_VALIDATED", "IN_REVIEW") for lab in labs),
        "high_risk_changes": sum(c.risk_tier == "High" and c.state not in ("RELEASED", "REJECTED") for c in crs),
        "open_findings": len(fnd),
        "change_requests": [{"id": c.id, "source": c.source, "reason": c.reason, "state": c.state,
                             "risk_tier": c.risk_tier, "risk_score": c.risk_score, "synthetic": c.synthetic,
                             "created_at": str(c.created_at)[:10]}
                            for c in sorted(crs, key=lambda c: c.id, reverse=True)],
        "label_states": {s: sum(lab.state == s for lab in labs) for s in sorted({lab.state for lab in labs})},
    }


def metrics() -> dict:
    out = {}
    for p in sorted(EVAL_DIR.glob("*.json")):
        try:
            out[p.stem] = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    return out


def audit_events(session: Session, limit=200) -> list[dict]:
    evs = session.execute(select(AuditEvent).order_by(AuditEvent.id.desc()).limit(limit)).scalars()
    return [{"id": e.id, "ts": e.ts, "actor_type": e.actor_type, "actor_id": e.actor_id, "action": e.action,
             "entity": e.entity, "payload": e.payload, "model_version": e.model_version,
             "prompt_hash": (e.prompt_hash or "")[:12], "hash": e.hash[:16], "prev_hash": e.prev_hash[:16]}
            for e in evs]


def tamper_demo(session: Session) -> dict:
    """Edit one ledger row directly (bypassing log) to show verify() catches it."""
    e = session.execute(select(AuditEvent).order_by(AuditEvent.id).offset(3).limit(1)).scalar_one()
    p = dict(e.payload)
    p["tampered"] = True
    e.payload = p
    session.flush()
    return {"tampered_id": e.id}
