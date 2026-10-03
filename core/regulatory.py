"""Which requirements (and therefore rules) apply to a label.

Requirement rows come from the database when it exists (so new regulatory change requests are seen),
otherwise from data/regulatory/requirements.csv.
"""
from __future__ import annotations

from core import master as M

_provider = None  # set by core.db to return active requirement rows from the DB


def set_provider(fn):
    global _provider
    _provider = fn


def get_requirements() -> list[dict]:
    if _provider is not None:
        try:
            rows = _provider()
            if rows:
                return rows
        except Exception:  # noqa: BLE001 - DB not initialised yet
            pass
    return M.requirements()


def label_context(spec_or_label: dict) -> dict:
    s = spec_or_label
    ctx = M.product_context(s["sku_id"], s["market"], s.get("attributes"))
    ctx["packaging_level"] = s["packaging_level"]
    return ctx


def requirement_applies(req: dict, ctx: dict) -> bool:
    from generator.label_generator import eval_condition

    if req["market"] not in (ctx["market"], "ALL"):
        return False
    if ctx["packaging_level"] not in req["packaging_levels"].split("|"):
        return False
    return eval_condition(req.get("applies_if"), ctx, set())


def applicable_requirements(spec_or_label: dict, reqs: list[dict] | None = None) -> list[dict]:
    ctx = label_context(spec_or_label)
    return [r for r in (reqs if reqs is not None else get_requirements()) if requirement_applies(r, ctx)]
