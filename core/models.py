"""Phase 5.1: SQLAlchemy models (SQLite by default; switch DATABASE_URL to Postgres for a shared DB)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"
    product_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    brand: Mapped[str] = mapped_column(String)
    manufacturer_id: Mapped[str] = mapped_column(String)
    device_class_us: Mapped[str] = mapped_column(String)
    device_class_eu: Mapped[str] = mapped_column(String)
    sterile: Mapped[bool] = mapped_column(Boolean)
    implantable: Mapped[bool] = mapped_column(Boolean)
    single_use: Mapped[bool] = mapped_column(Boolean)
    rx: Mapped[bool] = mapped_column(Boolean)
    mr_status: Mapped[str] = mapped_column(String)


class Sku(Base):
    __tablename__ = "skus"
    sku_id: Mapped[str] = mapped_column(String, primary_key=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.product_id"))
    model: Mapped[str] = mapped_column(String)
    diameter_mm: Mapped[float] = mapped_column(Float)
    length_mm: Mapped[float] = mapped_column(Float)
    revision: Mapped[str] = mapped_column(String)


class Packaging(Base):
    __tablename__ = "packaging"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku_id: Mapped[str] = mapped_column(ForeignKey("skus.sku_id"))
    packaging_level: Mapped[str] = mapped_column(String)
    gtin14: Mapped[str] = mapped_column(String)
    quantity: Mapped[int] = mapped_column(Integer)


class Attribute(Base):
    __tablename__ = "attributes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku_id: Mapped[str] = mapped_column(ForeignKey("skus.sku_id"))
    key: Mapped[str] = mapped_column(String)
    value: Mapped[str] = mapped_column(String)
    version: Mapped[int] = mapped_column(Integer)
    effective_date: Mapped[str] = mapped_column(String)
    change_request_id: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="released")  # released | pending


class Market(Base):
    __tablename__ = "markets"
    market: Mapped[str] = mapped_column(String, primary_key=True)
    regulator: Mapped[str] = mapped_column(String)
    languages: Mapped[list] = mapped_column(JSON)
    date_format: Mapped[str] = mapped_column(String)
    packaging_levels: Mapped[list] = mapped_column(JSON)
    active: Mapped[bool] = mapped_column(Boolean)


class Requirement(Base):
    __tablename__ = "requirements"
    requirement_id: Mapped[str] = mapped_column(String, primary_key=True)
    market: Mapped[str] = mapped_column(String)
    regulation: Mapped[str] = mapped_column(String)
    section: Mapped[str] = mapped_column(String)
    label_element: Mapped[str] = mapped_column(String)
    requirement_text: Mapped[str] = mapped_column(Text)
    obligation: Mapped[str] = mapped_column(String)
    applies_if: Mapped[str] = mapped_column(String)
    packaging_levels: Mapped[str] = mapped_column(String)
    rule_id: Mapped[str] = mapped_column(String)
    source_url: Mapped[str] = mapped_column(String)
    retrieved_on: Mapped[str] = mapped_column(String, default="")
    verified_by: Mapped[str] = mapped_column(String, default="")
    status: Mapped[str] = mapped_column(String, default="active")  # active | pending | retired
    change_request_id: Mapped[str | None] = mapped_column(String, nullable=True)


class Symbol(Base):
    __tablename__ = "symbols"
    symbol_id: Mapped[str] = mapped_column(String, primary_key=True)
    concept: Mapped[str] = mapped_column(String)
    iso_ref: Mapped[str] = mapped_column(String)
    library_version: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    min_height_mm: Mapped[float] = mapped_column(Float)
    requires_adjacent_text: Mapped[str] = mapped_column(String)
    glyph_file: Mapped[str] = mapped_column(String)


class GlossaryTerm(Base):
    __tablename__ = "glossary"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    term_id: Mapped[str] = mapped_column(String)
    language: Mapped[str] = mapped_column(String)
    approved_term: Mapped[str] = mapped_column(String)
    forbidden_variants: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)


class MasterText(Base):
    __tablename__ = "master_texts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    text_id: Mapped[str] = mapped_column(String)
    language: Mapped[str] = mapped_column(String)
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String)
    approved_on: Mapped[str] = mapped_column(String)
    translation_status: Mapped[str] = mapped_column(String)


class Label(Base):
    __tablename__ = "labels"
    label_id: Mapped[str] = mapped_column(String, primary_key=True)
    sku_id: Mapped[str] = mapped_column(ForeignKey("skus.sku_id"))
    market: Mapped[str] = mapped_column(String)
    language_set: Mapped[list] = mapped_column(JSON)
    packaging_level: Mapped[str] = mapped_column(String)
    template_id: Mapped[str] = mapped_column(String)
    revision: Mapped[str] = mapped_column(String)
    state: Mapped[str] = mapped_column(String)  # DRAFT AUTO_VALIDATED IN_REVIEW APPROVED RELEASED REJECTED SUPERSEDED
    pdf_path: Mapped[str] = mapped_column(String)
    png_path: Mapped[str] = mapped_column(String)
    json_path: Mapped[str] = mapped_column(String)
    spec_hash: Mapped[str] = mapped_column(String)
    change_request_id: Mapped[str | None] = mapped_column(String, nullable=True)
    parent_label_id: Mapped[str | None] = mapped_column(String, nullable=True)
    validation_status: Mapped[str | None] = mapped_column(String, nullable=True)  # PASS REVIEW FAIL
    validation_report: Mapped[str | None] = mapped_column(String, nullable=True)
    diff_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class LabelElement(Base):
    __tablename__ = "label_elements"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    label_id: Mapped[str] = mapped_column(ForeignKey("labels.label_id"))
    element_id: Mapped[str] = mapped_column(String)
    element: Mapped[str] = mapped_column(String)
    type: Mapped[str] = mapped_column(String)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    bbox: Mapped[list] = mapped_column(JSON)
    language: Mapped[str | None] = mapped_column(String, nullable=True)
    binding_type: Mapped[str] = mapped_column(String)
    binding_ref: Mapped[str] = mapped_column(String)
    deps: Mapped[list] = mapped_column(JSON)


class ChangeRequest(Base):
    __tablename__ = "change_requests"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    source: Mapped[str] = mapped_column(String)  # product | regulatory
    reason: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String)  # OPEN DRAFTED IN_REVIEW APPROVED RELEASED REJECTED
    risk_tier: Mapped[str | None] = mapped_column(String, nullable=True)
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_breakdown: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    impact: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[str] = mapped_column(String)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Finding(Base):
    __tablename__ = "findings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    label_id: Mapped[str] = mapped_column(String)
    rule_id: Mapped[str] = mapped_column(String)
    requirement_id: Mapped[str | None] = mapped_column(String, nullable=True)
    severity: Mapped[str] = mapped_column(String)
    element: Mapped[str | None] = mapped_column(String, nullable=True)
    evidence_bbox: Mapped[list | None] = mapped_column(JSON, nullable=True)
    clause_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    message: Mapped[str] = mapped_column(Text)
    suggested_fix: Mapped[str | None] = mapped_column(Text, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, default="open")  # open | waived | resolved
    waiver_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Approval(Base):
    __tablename__ = "approvals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String)  # label | change_request | waiver | release
    entity_id: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String)
    user: Mapped[str] = mapped_column(String)
    meaning: Mapped[str] = mapped_column(String)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    artefact_hash: Mapped[str] = mapped_column(String)
    valid: Mapped[bool] = mapped_column(Boolean, default=True)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[str] = mapped_column(String)
    actor_type: Mapped[str] = mapped_column(String)  # user | system | llm
    actor_id: Mapped[str] = mapped_column(String)
    action: Mapped[str] = mapped_column(String)
    entity: Mapped[str] = mapped_column(String)
    payload: Mapped[dict] = mapped_column(JSON)
    input_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    output_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    model_version: Mapped[str | None] = mapped_column(String, nullable=True)
    prompt_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    prev_hash: Mapped[str] = mapped_column(String)
    hash: Mapped[str] = mapped_column(String)
