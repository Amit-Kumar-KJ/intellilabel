"""Loads master data and regulatory CSVs into plain Python structures.

Used by the generator (before the DB exists) and by `core.db` to seed tables.
Attributes are versioned key/value rows; `current_attributes` returns the latest version.
"""
from __future__ import annotations

import csv
import json
from functools import lru_cache
from pathlib import Path

from core.config import MASTER_DIR, REG_DIR


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _bool(v: str) -> bool:
    return str(v).strip().lower() in ("true", "1", "yes")


@lru_cache(maxsize=None)
def products() -> dict:
    out = {}
    for r in read_csv(MASTER_DIR / "products.csv"):
        for k in ("sterile", "implantable", "single_use", "rx", "ifu_required"):
            r[k] = _bool(r[k])
        out[r["product_id"]] = r
    return out


@lru_cache(maxsize=None)
def skus() -> dict:
    return {r["sku_id"]: r for r in read_csv(MASTER_DIR / "skus.csv")}


@lru_cache(maxsize=None)
def manufacturers() -> dict:
    out = {}
    for r in read_csv(MASTER_DIR / "manufacturers.csv"):
        r["outside_eu"] = _bool(r["outside_eu"])
        out[r["manufacturer_id"]] = r
    return out


@lru_cache(maxsize=None)
def markets(active_only: bool = True) -> dict:
    out = {}
    for r in read_csv(MASTER_DIR / "markets.csv"):
        r["active"] = _bool(r["active"])
        r["languages"] = r["languages"].split("|")
        r["packaging_levels"] = r["packaging_levels"].split("|")
        if r["active"] or not active_only:
            out[r["market"]] = r
    return out


@lru_cache(maxsize=None)
def attribute_rows() -> list[dict]:
    rows = read_csv(MASTER_DIR / "attributes.csv")
    for r in rows:
        r["version"] = int(r["version"])
    return rows


def current_attributes(sku_id: str, rows: list[dict] | None = None) -> dict:
    """Latest version of every attribute key for a SKU."""
    best: dict[str, dict] = {}
    for r in rows if rows is not None else attribute_rows():
        if r["sku_id"] != sku_id:
            continue
        if r["key"] not in best or r["version"] > best[r["key"]]["version"]:
            best[r["key"]] = r
    return {k: v["value"] for k, v in best.items()}


@lru_cache(maxsize=None)
def master_texts() -> dict:
    """{(text_id, language): row}"""
    return {(r["text_id"], r["language"]): r for r in read_csv(MASTER_DIR / "master_texts.csv")}


@lru_cache(maxsize=None)
def glossary() -> list[dict]:
    rows = read_csv(MASTER_DIR / "glossary.csv")
    for r in rows:
        r["forbidden"] = [v for v in r["forbidden_variants"].split("|") if v]
    return rows


@lru_cache(maxsize=None)
def symbols() -> dict:
    out = {}
    for r in read_csv(REG_DIR / "symbols.csv"):
        r["min_height_mm"] = float(r["min_height_mm"])
        out[r["symbol_id"]] = r
    return out


@lru_cache(maxsize=None)
def requirements() -> list[dict]:
    return read_csv(REG_DIR / "requirements.csv")


def scenario_b_requirement() -> dict:
    return json.loads((REG_DIR / "scenario_b_requirement.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def packaging() -> dict:
    """{(sku_id, level): row} incl. gtin14 - built by generator.master_build."""
    p = MASTER_DIR / "packaging.csv"
    if not p.exists():
        return {}
    return {(r["sku_id"], r["packaging_level"]): r for r in read_csv(p)}


def product_context(sku_id: str, market: str, attrs: dict | None = None) -> dict:
    """Flat attribute context used by `applies_if` and rules."""
    sku = skus()[sku_id]
    prod = products()[sku["product_id"]]
    mfr = manufacturers()[prod["manufacturer_id"]]
    return {
        "sku_id": sku_id,
        "product_id": prod["product_id"],
        "device_class": prod["device_class_eu"] if market == "EU" else prod["device_class_us"],
        "sterile": prod["sterile"],
        "implantable": prod["implantable"],
        "single_use": prod["single_use"],
        "rx": prod["rx"],
        "ifu_required": prod["ifu_required"],
        "market": market,
        "manufacturer_outside_eu": mfr["outside_eu"],
        "attributes": attrs if attrs is not None else current_attributes(sku_id),
    }


def clear_caches():
    for fn in (products, skus, manufacturers, markets, attribute_rows, master_texts, glossary, symbols,
               requirements, packaging):
        fn.cache_clear()
