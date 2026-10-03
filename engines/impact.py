"""Phase 6.2-6.3: change impact analysis and deterministic draft regeneration.

analyse(session, cr)  -> ImpactReport (matrix, counts by market/language/level, actions, risk, approvers)
regenerate(session, cr) -> new DRAFT label revisions linked to the change request (approved revisions untouched)
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from core import audit
from core import master as M
from core.config import DRAFT_DIR
from core.db import absolute, active_requirements, db_attributes, load_spec, register_label
from core.graph import build_product_graph, forward
from core.models import ChangeRequest, Finding, Label, LabelElement, Product, Sku
from core.risk import SAFETY_ELEMENTS, SAFETY_KEYS, score

UDI_ELEMENTS = {"udi_aidc", "udi_hri"}


def action_for(element: str, etype: str, binding_type: str) -> list[str]:
    if etype == "date" or element in UDI_ELEMENTS or binding_type == "derived":
        return ["Regenerate label", "Regenerate UDI barcode", "Re-verify date format"]
    if binding_type == "master_text":
        return ["Regenerate label", "Re-validate every translation of that text", "Human linguist review"]
    if etype == "symbol":
        return ["Regenerate label", "Re-check symbol rules"]
    if binding_type == "manufacturer":
        return ["Regenerate all labels for that manufacturer", "Check regulatory notification needs (manual)"]
    return ["Regenerate label"]


def _skus_in_scope(session, scope: dict) -> list[str]:
    if "sku" in scope:
        return [scope["sku"]]
    pid = scope.get("product")
    return [s.sku_id for s in session.execute(select(Sku).where(Sku.product_id == pid)).scalars()]


def _current_labels(session, sku_ids=None) -> list[Label]:
    q = select(Label).where(Label.state == "RELEASED")
    if sku_ids:
        q = q.where(Label.sku_id.in_(sku_ids))
    return list(session.execute(q).scalars())


def defect_history_share(session, product_id="P-CS") -> float:
    crs = session.execute(select(ChangeRequest).where(ChangeRequest.state.in_(["RELEASED", "REJECTED"]))).scalars().all()
    if not crs:
        return 0.0
    crit = {f.label_id.replace("HIST-", "") for f in session.execute(select(Finding).where(
        Finding.severity == "critical")).scalars() if f.label_id.startswith("HIST-")}
    return round(sum(1 for c in crs if c.id in crit) / len(crs), 3)


def analyse(session: Session, cr: ChangeRequest) -> dict:
    payload = cr.payload
    rows: dict[str, dict] = {}
    changed_keys = set()
    labels_all = {lab.label_id: lab for lab in _current_labels(session)}
    regulatory_failures = {}
    if cr.source == "product":
        g = build_product_graph(session)
        for ch in payload["changes"]:
            changed_keys.add(ch["key"])
            for sku in _skus_in_scope(session, ch["scope"]):
                fw = forward(g, f"attr:{sku}:{ch['key']}")
                for en in fw["elements"]:
                    nd = g.nodes[en]
                    lab = labels_all.get(nd["label_id"])
                    if not lab:
                        continue
                    le = session.execute(select(LabelElement).where(LabelElement.label_id == lab.label_id,
                                                                    LabelElement.element_id == en.split(":", 2)[2])
                                         ).scalar_one()
                    row = rows.setdefault(lab.label_id, {"label_id": lab.label_id, "sku_id": lab.sku_id,
                                                         "market": lab.market, "packaging_level": lab.packaging_level,
                                                         "languages": lab.language_set, "revision": lab.revision,
                                                         "elements": [], "actions": set(), "keys": set()})
                    row["keys"].add(ch["key"])
                    row["elements"].append({"element_id": le.element_id, "element": le.element, "type": le.type,
                                            "language": le.language, "old_value": le.value,
                                            "binding": le.binding_ref, "via": ch["key"],
                                            "actions": action_for(le.element, le.type, le.binding_type)})
                    row["actions"].update(action_for(le.element, le.type, le.binding_type))
    else:
        from engines.compliance import validate_file

        req = payload["requirement"]
        for lab in labels_all.values():
            spec = load_spec(lab)
            rep = validate_file(absolute(lab.pdf_path), {**spec, "label_id": lab.label_id}, reqs=[req])
            if req["requirement_id"] in rep["applicable_requirements"]:
                fails = [f for f in rep["findings"] if f["requirement_id"] == req["requirement_id"]]
                if fails:
                    regulatory_failures[lab.label_id] = fails
                    rows[lab.label_id] = {"label_id": lab.label_id, "sku_id": lab.sku_id, "market": lab.market,
                                          "packaging_level": lab.packaging_level, "languages": lab.language_set,
                                          "revision": lab.revision, "keys": {req["label_element"]},
                                          "elements": [{"element_id": req["label_element"],
                                                        "element": req["label_element"], "type": "requirement",
                                                        "language": None, "old_value": None, "binding":
                                                            f"req:{req['requirement_id']}",
                                                        "via": req["requirement_id"],
                                                        "actions": [f"Run rule {req['rule_id']}",
                                                                    "Regenerate with updated template"],
                                                        "finding": fails[0]["message"]}],
                                          "actions": {f"Run rule {req['rule_id']} on all applicable labels",
                                                      "Regenerate with updated template", "List failures"}}
    matrix = []
    for r in sorted(rows.values(), key=lambda x: x["label_id"]):
        r["actions"] = sorted(r["actions"])
        r["keys"] = sorted(r["keys"])
        matrix.append(r)
    by_market = Counter(r["market"] for r in matrix)
    by_level = Counter(r["packaging_level"] for r in matrix)
    by_lang = Counter(lg for r in matrix for lg in r["languages"])
    # risk factors (Phase 10)
    prod_id = payload.get("product") or "P-CS"
    prod = session.get(Product, prod_id) or session.execute(select(Product)).scalars().first()
    els = {e["element"] for r in matrix for e in r["elements"]}
    multi_lang_text = [r for r in matrix if any(e["language"] and len(r["languages"]) > 1 for e in r["elements"])]
    active_markets = [m for m, v in M.markets().items()]
    factors = {
        "safety": 1.0 if (changed_keys & SAFETY_KEYS or els & SAFETY_ELEMENTS) else 0.0,
        "device_class": 1.0 if prod.device_class_eu == "III" else (0.5 if prod.device_class_eu.startswith("II")
                                                                     else 0.0),
        "udi": 1.0 if els & UDI_ELEMENTS else 0.0,
        "translation": round(len(multi_lang_text) / len(matrix), 3) if matrix else 0.0,
        "breadth": round(len(matrix) / max(1, len(labels_all)), 3),
        "markets": round(len(by_market) / max(1, len(active_markets)), 3),
        "symbol": 1.0 if any(e["type"] == "symbol" or e["element"].endswith("symbol") for r in matrix
                             for e in r["elements"]) else 0.0,
        "defect_history": defect_history_share(session),
    }
    risk = score(factors)
    report = {"change_request_id": cr.id, "source": cr.source, "impacted_labels": len(matrix),
              "total_current_labels": len(labels_all), "unaffected_labels": len(labels_all) - len(matrix),
              "by_market": dict(by_market), "by_packaging_level": dict(by_level), "by_language": dict(by_lang),
              "matrix": matrix, "risk": risk, "required_approvers": risk["required_roles"],
              "regulatory_failures": {k: [f["message"] for f in v] for k, v in regulatory_failures.items()}}
    return report


def next_revision(rev: str) -> str:
    return f"R{int(rev[1:]) + 1:02d}"


def regenerate(session: Session, cr: ChangeRequest, plant_unrequested_edit: bool = False,
               actor: str = "system") -> list[dict]:
    from generator.label_generator import build_spec, label_id_for, render

    impact = cr.impact or analyse(session, cr)
    active_ids = {r["requirement_id"] for r in active_requirements(session)}
    out = []
    planted = False
    for row in impact["matrix"]:
        parent = session.get(Label, row["label_id"])
        pspec = load_spec(parent)
        new_rev = next_revision(parent.revision)
        attrs = db_attributes(session, parent.sku_id, include_pending_cr=cr.id)
        lid = label_id_for(parent.sku_id, parent.market, parent.packaging_level, new_rev)
        spec = build_spec(parent.sku_id, parent.market, parent.packaging_level, new_rev, attrs=attrs,
                          production={"lot": pspec["production"]["lot"], "mfg_date": pspec["production"]["mfg_date"]},
                          active_reqs=active_ids, label_id=lid)
        note = None
        if plant_unrequested_edit and not planted and parent.market == "EU" and parent.packaging_level == "carton":
            for e in spec["elements"]:
                if e["element"] == "ifu_indication":
                    e["bbox_mm"][0] = round(e["bbox_mm"][0] + 3.0, 2)
                    planted = True
                    note = "DEMO: planted unrequested artwork edit (IFU symbol moved 3 mm)"
        paths = render(spec, DRAFT_DIR / cr.id / lid)
        register_label(session, spec, paths, state="DRAFT", change_request_id=cr.id, parent_label_id=parent.label_id)
        audit.log(session, "label.draft_generated", f"label:{lid}", {"change_request": cr.id, "parent":
                                                                     parent.label_id, "revision": new_rev,
                                                                     "note": note}, actor_id=actor)
        out.append({"label_id": lid, "parent_label_id": parent.label_id, "revision": new_rev, "png": paths["png"],
                    "note": note})
    return out


def _unused():  # keep imports referenced for linters
    return json, defaultdict
