"""Phase 12.1: FastAPI. All logic lives behind these endpoints; Streamlit only calls them.
Interactive docs at http://localhost:8000/docs
"""
from __future__ import annotations

import shutil
from contextlib import asynccontextmanager
import tempfile
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from core import services as S
from core import workflow as W
from core.audit import verify
from core.db import absolute, ensure_db, session_scope
from core.models import ChangeRequest, Finding, Label

@asynccontextmanager
async def lifespan(_app):
    ensure_db()
    yield


app = FastAPI(title="IntelliLabel AI", version="0.1.0", lifespan=lifespan,
              description="Rules decide, AI proposes and explains, humans sign. Prototype - synthetic data.")


# ---------------------------------------------------------------- schemas
class ParseIn(BaseModel):
    text: str = Field(..., examples=["Extend CardioSafe shelf life to 36 months and update the sterilization wording"])
    user: str = "ra_user_01"


class Change(BaseModel):
    scope: dict
    key: str
    old: str | None = None
    new: str


class RequirementIn(BaseModel):
    requirement_id: str
    market: str
    regulation: str
    section: str
    label_element: str
    requirement_text: str
    obligation: str = "mandatory"
    applies_if: str = "all"
    packaging_levels: str = "pouch|carton"
    rule_id: str = "R20"
    source_url: str
    retrieved_on: str = ""
    verified_by: str = "UNVERIFIED"


class ChangeRequestIn(BaseModel):
    source: Literal["product", "regulatory"] = "product"
    reason: str = ""
    changes: list[Change] | None = None
    requirement: RequirementIn | None = None
    user: str = "ra_user_01"


class DraftsIn(BaseModel):
    plant_unrequested_edit: bool = False
    user: str = "labeling_engineer_user"


class TransitionIn(BaseModel):
    target: Literal["AUTO_VALIDATED", "IN_REVIEW", "APPROVED", "REJECTED", "DRAFT"]
    user: str
    reason: str | None = None


class SignIn(BaseModel):
    label_id: str
    role: str
    user: str
    meaning: str = "approved"
    password: str


class WaiverIn(BaseModel):
    finding_id: int
    reason: str
    user: str
    role: str
    password: str


class ChangeReviewIn(BaseModel):
    index: int
    decision: Literal["accepted", "rejected"]
    user: str
    note: str = ""


class ReleaseIn(BaseModel):
    user: str
    password: str


class TranslationIn(BaseModel):
    source_en: str
    translation: str
    language: str
    text_id: str | None = None


def _err(e: Exception):
    raise HTTPException(status_code=409 if isinstance(e, W.GateError) else 400, detail=str(e))


# ---------------------------------------------------------------- change requests
@app.post("/change-requests/parse", tags=["change requests"])
def parse(body: ParseIn) -> dict:
    from engines.llm_gateway import parse_change

    with session_scope() as s:
        return parse_change(body.text, session=s, actor_id=body.user)


@app.post("/change-requests", tags=["change requests"])
def create_cr(body: ChangeRequestIn) -> dict:
    data = body.model_dump()
    if body.source == "product" and not body.changes:
        raise HTTPException(400, "product change requests need 'changes'")
    if body.source == "regulatory" and not body.requirement:
        raise HTTPException(400, "regulatory change requests need 'requirement'")
    with session_scope() as s:
        cr = S.create_change_request(s, data, body.user)
        return {"id": cr.id, "state": cr.state}


@app.get("/change-requests", tags=["change requests"])
def list_crs() -> list[dict]:
    with session_scope() as s:
        return S.dashboard(s)["change_requests"]


@app.get("/change-requests/{cid}", tags=["change requests"])
def get_cr(cid: str) -> dict:
    with session_scope() as s:
        cr = s.get(ChangeRequest, cid)
        if not cr:
            raise HTTPException(404, "unknown change request")
        labels = [{"label_id": lab.label_id, "state": lab.state, "validation_status": lab.validation_status,
                   "diff_status": (lab.diff_json or {}).get("status"), "parent_label_id": lab.parent_label_id,
                   "market": lab.market, "packaging_level": lab.packaging_level, "sku_id": lab.sku_id,
                   "revision": lab.revision}
                  for lab in s.query(Label).filter(Label.change_request_id == cid).order_by(Label.label_id)]
        return {"id": cr.id, "source": cr.source, "reason": cr.reason, "payload": cr.payload, "state": cr.state,
                "risk_tier": cr.risk_tier, "risk_score": cr.risk_score, "created_by": cr.created_by,
                "labels": labels}


@app.get("/change-requests/{cid}/impact", tags=["change requests"])
def get_impact(cid: str, refresh: bool = False) -> dict:
    with session_scope() as s:
        return S.impact(s, cid, refresh=refresh)


@app.post("/change-requests/{cid}/drafts", tags=["change requests"])
def make_drafts(cid: str, body: DraftsIn) -> list[dict]:
    with session_scope() as s:
        return S.drafts(s, cid, plant_unrequested_edit=body.plant_unrequested_edit, user=body.user)


@app.post("/change-requests/{cid}/auto-validate", tags=["change requests"])
def auto_validate(cid: str, user: str = "system") -> list[dict]:
    with session_scope() as s:
        return S.auto_validate_cr(s, cid, user=user)


# ---------------------------------------------------------------- labels
@app.get("/labels", tags=["labels"])
def list_labels(state: str | None = None) -> list[dict]:
    with session_scope() as s:
        q = s.query(Label)
        if state:
            q = q.filter(Label.state == state)
        return [{"label_id": lab.label_id, "sku_id": lab.sku_id, "market": lab.market,
                 "packaging_level": lab.packaging_level, "revision": lab.revision, "state": lab.state,
                 "validation_status": lab.validation_status, "change_request_id": lab.change_request_id,
                 "languages": lab.language_set} for lab in q.order_by(Label.label_id)]


@app.get("/labels/{label_id}", tags=["labels"])
def get_label(label_id: str) -> dict:
    with session_scope() as s:
        lab = s.get(Label, label_id)
        if not lab:
            raise HTTPException(404, "unknown label")
        findings = [{"id": f.id, "rule_id": f.rule_id, "severity": f.severity, "message": f.message,
                     "clause_ref": f.clause_ref, "requirement_id": f.requirement_id, "element": f.element,
                     "evidence_bbox": f.evidence_bbox, "suggested_fix": f.suggested_fix, "explanation": f.explanation,
                     "status": f.status, "waiver_reason": f.waiver_reason}
                    for f in s.query(Finding).filter(Finding.label_id == label_id).order_by(Finding.id)]
        return {"label_id": lab.label_id, "sku_id": lab.sku_id, "market": lab.market, "revision": lab.revision,
                "packaging_level": lab.packaging_level, "state": lab.state, "languages": lab.language_set,
                "validation_status": lab.validation_status, "validation_report": lab.validation_report,
                "pdf_path": lab.pdf_path, "png_path": lab.png_path, "parent_label_id": lab.parent_label_id,
                "change_request_id": lab.change_request_id, "diff": lab.diff_json, "findings": findings,
                "required_roles": W.required_roles(s, lab) if lab.change_request_id else [],
                "signatures": [{"role": a.role, "user": a.user, "meaning": a.meaning, "valid": a.valid,
                                "timestamp": str(a.timestamp)} for a in W.valid_signatures(s, lab)]
                if lab.state in ("IN_REVIEW", "APPROVED", "RELEASED") else []}


@app.get("/labels/{label_id}/file/{kind}", tags=["labels"])
def label_file(label_id: str, kind: Literal["pdf", "png", "report", "overlay"]):
    with session_scope() as s:
        lab = s.get(Label, label_id)
        if not lab:
            raise HTTPException(404, "unknown label")
        p = {"pdf": lab.pdf_path, "png": lab.png_path, "report": lab.validation_report,
             "overlay": (lab.diff_json or {}).get("overlay_png")}[kind]
    if not p or not absolute(p).exists():
        raise HTTPException(404, f"{kind} not available")
    return FileResponse(absolute(p))


@app.post("/labels/upload/validate", tags=["labels"])
def upload_validate(file: UploadFile = File(...), sku_id: str = Form("CS-100"), market: str = Form("EU"),
                    packaging_level: str = Form("carton"), revision: str = Form("R02"),
                    force_ocr: bool = Form(False)) -> dict:
    from engines.compliance import validate_file

    suffix = Path(file.filename or "x.pdf").suffix or ".pdf"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        path = tmp.name
    with session_scope() as s:
        from core.db import active_requirements

        rep = validate_file(path, {"label_id": f"upload:{file.filename}", "sku_id": sku_id, "market": market,
                                   "packaging_level": packaging_level, "revision": revision},
                            reqs=active_requirements(s), force_ocr=force_ocr)
        from core.audit import log, sha256

        log(s, "label.upload_validated", f"upload:{file.filename}", {"status": rep["status"], "sha256": sha256(
            Path(path).read_bytes())})
    model = rep.pop("model")
    rep["extracted"] = {"source": model["source"], "languages_present": model["languages_present"],
                        "elements": {k: v for k, v in model["elements"].items() if isinstance(v, dict)},
                        "barcodes": model["barcodes"], "symbols": model["symbols"]}
    return rep


@app.post("/labels/{label_id}/validate", tags=["labels"])
def validate(label_id: str, user: str = "system") -> dict:
    with session_scope() as s:
        return S.validate_label(s, label_id, user=user)


@app.post("/labels/{label_id}/diff", tags=["labels"])
def diff(label_id: str, user: str = "system") -> dict:
    with session_scope() as s:
        return S.diff_label(s, label_id, user=user)


@app.post("/labels/{label_id}/diff/review", tags=["labels"])
def review_change(label_id: str, body: ChangeReviewIn) -> dict:
    with session_scope() as s:
        return W.review_change(s, label_id, body.index, body.decision, body.user, body.note)


@app.post("/translations/check", tags=["translations"])
def translation_check(body: TranslationIn) -> dict:
    from engines.translation import check

    return check(body.source_en, body.translation, body.language, body.text_id)


@app.get("/labels/{label_id}/trace", tags=["trace"])
def label_trace(label_id: str, element_id: str | None = None) -> dict:
    with session_scope() as s:
        return S.trace(s, label_id, element_id)


@app.get("/trace/forward", tags=["trace"])
def trace_forward(sku_id: str, key: str) -> dict:
    with session_scope() as s:
        return S.forward_trace(s, sku_id, key)


# ---------------------------------------------------------------- workflow
@app.post("/workflow/{label_id}/transition", tags=["workflow"])
def transition(label_id: str, body: TransitionIn) -> dict:
    try:
        with session_scope() as s:
            lab = W.transition(s, label_id, body.target, body.user, body.reason)
            return {"label_id": label_id, "state": lab.state}
    except W.GateError as e:
        _err(e)


@app.post("/approvals", tags=["workflow"])
def approve(body: SignIn) -> dict:
    try:
        with session_scope() as s:
            a = W.sign(s, body.label_id, body.role, body.user, body.meaning, body.password)
            return {"id": a.id, "artefact_hash": a.artefact_hash}
    except W.GateError as e:
        _err(e)


@app.post("/waivers", tags=["workflow"])
def waiver(body: WaiverIn) -> dict:
    try:
        with session_scope() as s:
            f = W.waive(s, body.finding_id, body.reason, body.user, body.role, body.password)
            return {"finding_id": f.id, "status": f.status}
    except W.GateError as e:
        _err(e)


@app.post("/release/{change_id}", tags=["workflow"])
def release(change_id: str, body: ReleaseIn) -> dict:
    try:
        with session_scope() as s:
            return W.release(s, change_id, body.user, body.password)
    except W.GateError as e:
        _err(e)


@app.get("/release/{change_id}/download", tags=["workflow"])
def release_download(change_id: str):
    from core.config import RELEASE_DIR

    zips = sorted(RELEASE_DIR.glob(f"{change_id}_*.zip"))
    if not zips:
        raise HTTPException(404, "no release package")
    return FileResponse(zips[-1], filename=zips[-1].name)


# ---------------------------------------------------------------- audit / metrics / admin
@app.get("/audit", tags=["audit"])
def audit_list(limit: int = 200) -> list[dict]:
    with session_scope() as s:
        return S.audit_events(s, limit)


@app.get("/audit/verify", tags=["audit"])
def audit_verify() -> dict:
    with session_scope() as s:
        return verify(s)


@app.post("/audit/tamper-demo", tags=["audit"])
def audit_tamper() -> dict:
    with session_scope() as s:
        return S.tamper_demo(s)


@app.get("/dashboard", tags=["metrics"])
def dashboard() -> dict:
    with session_scope() as s:
        return S.dashboard(s)


@app.get("/metrics", tags=["metrics"])
def metrics() -> dict:
    return S.metrics()


@app.get("/config", tags=["admin"])
def cfg() -> dict[str, Any]:
    from core import config
    from core.master import scenario_b_requirement
    from engines.llm_gateway import DEMO_SENTENCES, mode

    return {"llm_mode": mode(), "llm_provider": config.LLM_PROVIDER, "llm_model": config.LLM_MODEL,
            "demo_sentences": DEMO_SENTENCES, "scenario_b_requirement": scenario_b_requirement(),
            "roles": W.ROLE_LABELS, "demo_password_hint": "intellilabel"}


@app.post("/admin/reset-demo", tags=["admin"])
def reset_demo() -> dict:
    """Restore the seeded state in one click (drafts, releases and the ledger are rebuilt)."""
    from core.config import DRAFT_DIR, RELEASE_DIR, REPORT_DIR
    from core.db import rebuild
    from engines.llm_gateway import seed_demo_cache

    for d in (DRAFT_DIR, RELEASE_DIR, REPORT_DIR):
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True, exist_ok=True)
    res = rebuild(verbose=False)
    with session_scope() as s:
        seed_demo_cache(s)
    return {"ok": True, "labels": res["labels"], "integrity_errors": len(res["integrity_errors"])}
