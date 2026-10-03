"""Phase 5: database setup, CSV loading, integrity checks and synthetic history.

`python -m core.db --rebuild`  (== `make db`) drops and recreates all tables, loads master data, registers
the approved base labels, runs integrity checks and seeds a short SYNTHETIC change history.
"""
from __future__ import annotations

import argparse
import json
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from core import audit, regulatory
from core import master as M
from core.config import DATABASE_URL, LABEL_DIR, ROOT, TEMPLATE_DIR
from core.models import (Approval, Attribute, Base, ChangeRequest, Finding, GlossaryTerm, Label, LabelElement, Market,
                         MasterText, Packaging, Product, Requirement, Sku, Symbol)

engine = create_engine(DATABASE_URL, future=True,
                       connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


@contextmanager
def session_scope():
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def rel(p) -> str:
    try:
        return Path(p).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(p)


def absolute(p: str) -> Path:
    pp = Path(p)
    return pp if pp.is_absolute() else ROOT / pp


# ---------------------------------------------------------------- queries used across the app
def active_requirements(session: Session | None = None) -> list[dict]:
    def q(s):
        rows = s.execute(select(Requirement).where(Requirement.status == "active")).scalars().all()
        return [requirement_dict(r) for r in rows]

    if session is not None:
        return q(session)
    with session_scope() as s:
        return q(s)


def requirement_dict(r: Requirement) -> dict:
    return {c: getattr(r, c) for c in ("requirement_id", "market", "regulation", "section", "label_element",
                                       "requirement_text", "obligation", "applies_if", "packaging_levels", "rule_id",
                                       "source_url", "retrieved_on", "verified_by", "status", "change_request_id")}


def db_attributes(session: Session, sku_id: str, include_pending_cr: str | None = None) -> dict:
    """Latest released attribute versions (optionally including one pending change request's versions)."""
    rows = session.execute(select(Attribute).where(Attribute.sku_id == sku_id)).scalars().all()
    use = [r for r in rows if r.status == "released" or (include_pending_cr and r.change_request_id ==
                                                          include_pending_cr)]
    return M.current_attributes(sku_id, [{"sku_id": r.sku_id, "key": r.key, "value": r.value, "version": r.version}
                                         for r in use])


def register_label(session: Session, spec: dict, paths: dict, state: str, change_request_id=None,
                   parent_label_id=None) -> Label:
    from generator.label_generator import spec_hash

    lab = Label(label_id=spec["label_id"], sku_id=spec["sku_id"], market=spec["market"],
                language_set=spec["languages"], packaging_level=spec["packaging_level"],
                template_id=spec["template_id"], revision=spec["revision"], state=state,
                pdf_path=rel(paths["pdf"]), png_path=rel(paths["png"]), json_path=rel(paths["json"]),
                spec_hash=spec_hash(spec), change_request_id=change_request_id, parent_label_id=parent_label_id)
    session.merge(lab)
    session.query(LabelElement).filter(LabelElement.label_id == spec["label_id"]).delete()
    for e in spec["elements"]:
        b = e.get("binding", {})
        session.add(LabelElement(label_id=spec["label_id"], element_id=e["element_id"], element=e["element"],
                                 type=e["type"], value=e.get("value"), bbox=e["bbox_mm"], language=e.get("language"),
                                 binding_type=b.get("type", "static"), binding_ref=b.get("ref", ""),
                                 deps=b.get("deps", [])))
    session.flush()
    return lab


def load_spec(label: Label) -> dict:
    return json.loads(absolute(label.json_path).read_text(encoding="utf-8"))


# ---------------------------------------------------------------- build
def _load_master(s: Session):
    for r in M.products().values():
        s.add(Product(**{k: r[k] for k in ("product_id", "name", "brand", "manufacturer_id", "device_class_us",
                                           "device_class_eu", "sterile", "implantable", "single_use", "rx",
                                           "mr_status")}))
    for r in M.skus().values():
        s.add(Sku(sku_id=r["sku_id"], product_id=r["product_id"], model=r["model"],
                  diameter_mm=float(r["diameter_mm"]), length_mm=float(r["length_mm"]), revision=r["revision"]))
    for r in M.packaging().values():
        s.add(Packaging(sku_id=r["sku_id"], packaging_level=r["packaging_level"], gtin14=r["gtin14"],
                        quantity=int(r["quantity"])))
    for r in M.attribute_rows():
        s.add(Attribute(sku_id=r["sku_id"], key=r["key"], value=r["value"], version=r["version"],
                        effective_date=r["effective_date"], status="released"))
    for r in M.markets(active_only=False).values():
        s.add(Market(market=r["market"], regulator=r["regulator"], languages=r["languages"],
                     date_format=r["date_format"], packaging_levels=r["packaging_levels"], active=r["active"]))
    for r in M.requirements():
        s.add(Requirement(**{k: r[k] for k in r}, status="active"))
    for r in M.symbols().values():
        s.add(Symbol(**{k: r[k] for k in ("symbol_id", "concept", "iso_ref", "library_version", "status",
                                          "min_height_mm", "requires_adjacent_text", "glyph_file")}))
    for r in M.glossary():
        s.add(GlossaryTerm(term_id=r["term_id"], language=r["language"], approved_term=r["approved_term"],
                           forbidden_variants=r["forbidden_variants"], status=r["status"]))
    for (tid, lg), r in M.master_texts().items():
        s.add(MasterText(text_id=tid, language=lg, text=r["text"], status=r["status"], approved_on=r["approved_on"],
                         translation_status=r["translation_status"]))
    s.flush()


def _load_labels(s: Session) -> int:
    n = 0
    for d in sorted(LABEL_DIR.iterdir()):
        if not (d / "label.json").exists():
            continue
        spec = json.loads((d / "label.json").read_text(encoding="utf-8"))
        register_label(s, spec, {"pdf": d / "label.pdf", "png": d / "label.png", "json": d / "label.json"},
                       state="RELEASED")
        n += 1
    return n


def integrity_check(s: Session) -> list[str]:
    from engines.rules import RULES

    errors = []
    # every binding_ref exists
    attr_keys = {(a.sku_id, a.key) for a in s.execute(select(Attribute)).scalars()}
    mt_ids = {m.text_id for m in s.execute(select(MasterText)).scalars()}
    sym_ids = {x.symbol_id for x in s.execute(select(Symbol)).scalars()}
    templates = {p.stem for p in TEMPLATE_DIR.glob("*.yaml")}
    for le in s.execute(select(LabelElement)).scalars():
        ref = le.binding_ref
        if ref.startswith("mt:") and ref[3:] not in mt_ids:
            errors.append(f"{le.label_id}/{le.element_id}: unknown master text {ref}")
        if ref.startswith("symbol:") and ref[7:] not in sym_ids:
            errors.append(f"{le.label_id}/{le.element_id}: unknown symbol {ref}")
        for dep in le.deps or []:
            if dep.startswith("attr:"):
                _, sku, key = dep.split(":")
                if (sku, key) not in attr_keys:
                    errors.append(f"{le.label_id}/{le.element_id}: unknown attribute {dep}")
    for r in s.execute(select(Requirement)).scalars():
        if r.rule_id != "manual" and r.rule_id not in RULES:
            errors.append(f"{r.requirement_id}: unknown rule {r.rule_id}")
        if not r.section or not r.source_url:
            errors.append(f"{r.requirement_id}: missing section or source_url")
    for lab in s.execute(select(Label)).scalars():
        if lab.packaging_level not in templates:
            errors.append(f"{lab.label_id}: template for {lab.packaging_level} missing")
    return errors


def seed_history(s: Session):
    """Phase 5.4: ~10 SYNTHETIC past change requests so the dashboard looks realistic."""
    base = datetime(2026, 3, 2, 9, 0)
    from core.risk import TIER_ROLES, score

    F = lambda sa, ud, tr, br, mk, sy: {"safety": sa, "device_class": 1.0, "udi": ud, "translation": tr,  # noqa: E731
                                        "breadth": br, "markets": mk, "symbol": sy, "defect_history": 0.3}
    hist = [
        ("CR-0031", "product", "Correct manufacturer postcode", F(0, 0, 0, 1.0, 1.0, 0), "RELEASED", False),
        ("CR-0032", "product", "Update FR storage translation wording", F(1, 0, 1.0, 0.5, 0.5, 0), "RELEASED", True),
        ("CR-0033", "regulatory", "Add importer block for EU (MDR Art. 13)", F(0, 0, 0.5, 0.5, 0.5, 1), "RELEASED",
         True),
        ("CR-0034", "product", "Increase carton font size of lot number", F(0, 0, 0, 0.33, 1.0, 0), "RELEASED", False),
        ("CR-0035", "product", "New MR conditions text after testing at 3 T", F(1, 0, 0.5, 0.33, 1.0, 0), "RELEASED",
         True),
        ("CR-0036", "product", "Typo fix in DE single-use statement", F(0, 0, 0.5, 0.2, 0.5, 0), "REJECTED", False),
        ("CR-0037", "regulatory", "Symbol library update to current edition", F(0, 0, 0, 1.0, 1.0, 1), "RELEASED",
         False),
        ("CR-0038", "product", "Shipper quantity 12 -> 10", F(0, 1, 0, 0.33, 1.0, 0), "RELEASED", False),
        ("CR-0039", "product", "Storage temperature statement harmonised", F(1, 0, 1.0, 0.67, 1.0, 0), "RELEASED",
         True),
        ("CR-0040", "regulatory", "EU language set review", F(0, 0, 1.0, 0.5, 0.5, 0), "RELEASED", False),
    ]
    for i, (cid, src, reason, factors, state, had_crit) in enumerate(hist):
        ts = base + timedelta(days=17 * i)
        rs = score(factors)
        tier = rs["tier"]
        s.add(ChangeRequest(id=cid, source=src, reason=reason, payload={"product": "P-CS", "summary": reason},
                            state=state, risk_tier=tier, risk_score=rs["score"], risk_breakdown=rs,
                            created_by="ra_user_01", synthetic=True, created_at=ts))
        if had_crit:
            s.add(Finding(label_id=f"HIST-{cid}", rule_id="R17", severity="critical", message=(
                "Synthetic history: critical content finding caught before release"), status="resolved",
                synthetic=True, created_at=ts))
        if state == "RELEASED":
            for r in TIER_ROLES[tier]:
                s.add(Approval(entity_type="change_request", entity_id=cid, role=r, user=f"{r}_user",
                               meaning="approved for release", timestamp=ts + timedelta(days=2),
                               artefact_hash=audit.sha256(cid + r), synthetic=True))
        audit.log(s, "history.seeded", f"change_request:{cid}", {"state": state, "synthetic": True},
                  ts=ts.isoformat(timespec="seconds"))


def rebuild(verbose=True) -> dict:
    M.clear_caches()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with session_scope() as s:
        audit.log(s, "db.rebuild", "database", {"url": DATABASE_URL.split("@")[-1]})
        _load_master(s)
        n = _load_labels(s)
        audit.log(s, "labels.loaded", "labels", {"count": n, "state": "RELEASED"})
        seed_history(s)
        errors = integrity_check(s)
        audit.log(s, "db.integrity_check", "database", {"errors": len(errors)})
    with session_scope() as s:
        from engines.llm_gateway import seed_demo_cache

        seed_demo_cache(s)
    if verbose:
        print(f"Loaded {n} released labels. Integrity errors: {len(errors)}")
        for e in errors[:20]:
            print("  -", e)
    return {"labels": n, "integrity_errors": errors}


def ensure_db():
    """Create and load the DB on first use (so the app works right after `make data`)."""
    from sqlalchemy import inspect

    if "labels" not in inspect(engine).get_table_names():
        rebuild(verbose=False)
        return
    with session_scope() as s:
        if s.execute(select(Label).limit(1)).first() is None:
            rebuild(verbose=False)


regulatory.set_provider(active_requirements)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true")
    a = ap.parse_args()
    res = rebuild()
    raise SystemExit(1 if res["integrity_errors"] else 0)
