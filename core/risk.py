"""Phase 10: explainable risk scoring - a transparent weighted sum, NOT a trained model.

risk = sum_i w_i * f_i  with sum_i w_i = 1. Tiers: <0.3 Low, 0.3-0.7 Medium, >0.7 High.
Hard override: any open critical finding on a safety-related element -> High.
Weights start from the guide's defaults; Phase 14's FMEA should replace them (docs/risk_weights.md).
"""
from __future__ import annotations

import json

from core.config import ROOT

DEFAULT_WEIGHTS = {"safety": 0.30, "device_class": 0.15, "udi": 0.10, "translation": 0.10, "breadth": 0.10,
                   "markets": 0.10, "symbol": 0.05, "defect_history": 0.10}
FACTOR_LABELS = {"safety": "Safety-related element changed", "device_class": "Device class",
                 "udi": "UDI affected", "translation": "Translation affected", "breadth": "Breadth (labels)",
                 "markets": "Markets affected", "symbol": "Symbol change", "defect_history": "Defect history"}
SAFETY_KEYS = {"warning_text_id", "sterilization_text_id", "sterilization_method", "mr_conditions_text_id",
               "storage_text_id", "storage_temp_max_c"}
SAFETY_ELEMENTS = {"warning", "sterile_indication", "mr_conditions", "storage_statement", "sterilization_symbol",
                   "mr_marking", "damaged_package_warning", "contraindication"}
TIER_ROLES = {"Low": ["labeling_engineer", "regulatory_affairs"],
              "Medium": ["labeling_engineer", "regulatory_affairs", "quality_assurance"],
              "High": ["labeling_engineer", "regulatory_affairs", "quality_assurance", "clinical_safety",
                       "regulatory_affairs_2"]}


def load_weights() -> dict:
    p = ROOT / "docs" / "risk_weights.json"
    if p.exists():
        w = json.loads(p.read_text(encoding="utf-8"))
        tot = sum(w.values())
        return {k: v / tot for k, v in w.items()}
    return dict(DEFAULT_WEIGHTS)


def tier_of(score: float) -> str:
    return "Low" if score < 0.3 else ("Medium" if score <= 0.7 else "High")


def score(factors: dict, weights: dict | None = None, safety_critical_open: bool = False) -> dict:
    w = weights or load_weights()
    contrib = {k: round(w[k] * float(factors.get(k, 0.0)), 4) for k in w}
    total = round(sum(contrib.values()), 4)
    tier = tier_of(total)
    override = None
    if safety_critical_open and tier != "High":
        tier, override = "High", "Open critical finding on a safety-related element"
    return {"score": total, "tier": tier, "override": override, "factors": factors, "weights": w,
            "contributions": contrib, "required_roles": TIER_ROLES[tier]}


def sensitivity(vectors: list[dict], weights: dict | None = None, delta: float = 0.2) -> list[dict]:
    """Vary each weight by +/-delta (renormalised) and count how many change requests switch tier."""
    base_w = weights or load_weights()
    base = [tier_of(score(v, base_w)["score"]) for v in vectors]
    rows = []
    for k in base_w:
        for sign in (+1, -1):
            w = dict(base_w)
            w[k] = w[k] * (1 + sign * delta)
            tot = sum(w.values())
            w = {kk: vv / tot for kk, vv in w.items()}
            tiers = [tier_of(score(v, w)["score"]) for v in vectors]
            rows.append({"factor": k, "change": f"{'+' if sign > 0 else '-'}{int(delta * 100)}%",
                         "switched": sum(a != b for a, b in zip(base, tiers)), "of": len(vectors)})
    return rows
