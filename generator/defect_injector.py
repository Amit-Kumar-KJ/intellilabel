"""Phase 4.4: injects one known defect into a clean label spec (Appendix B catalogue).

Each injector mutates a deep copy of the spec and returns (spec, truth_items). A defect is only
injected where its expected rule applies (e.g. D05 only on EU labels), so the ground truth is fair.
"""
from __future__ import annotations

import copy
import random

from core import gs1
from core import master as M

RULE_SEVERITY = {"R01": "critical", "R02": "critical", "R03": "critical", "R04": "critical", "R05": "critical",
                 "R06": "critical", "R07": "major", "R08": "major", "R09": "critical", "R10": "critical",
                 "R11": "major", "R12": "major", "R13": "major", "R14": "critical", "R15": "major",
                 "R16": "minor", "R17": "critical", "R18": "critical", "R19": "critical", "R20": "major",
                 "R21": "major"}

DEFECTS = {
    "D01": ("UDI-DI check digit wrong", "R01"),
    "D02": ("Plain-text UDI differs from barcode", "R02"),
    "D03": ("Expiry mismatch between barcode and text", "R03"),
    "D04": ("Manufacturer symbol or address missing", "R05"),
    "D05": ("Authorised representative missing on an EU label", "R06"),
    "D06": ("Superseded symbol glyph used", "R15"),
    "D07": ("Sterilization symbol missing", "R09"),
    "D08": ("Wrong date format for the market", "R08"),
    "D09": ("Required language panel missing", "R14"),
    "D10": ("Warning number or unit altered", "R17"),
    "D11": ("Barcode overlaps text or symbol too small", "R16"),
    "D12": ("Outdated revision printed", "R18"),
    "D13": ("Glossary violation in a translation", "R21"),
    "D14": ("GTIN belongs to another SKU", "R04"),
}

GLOSSARY_SWAPS = {
    "de": [("Nicht wiederverwenden", "Nicht erneut benutzen"), ("Gebrauchsanweisung", "Bedienungsanleitung"),
           ("beschädigter", "defekter"), ("Ethylenoxid", "Äthylenoxid")],
    "fr": [("Ne pas réutiliser", "Ne pas réemployer"), ("mode d'emploi", "notice d'utilisation"),
           ("endommagé", "abîmé"), ("oxyde d'éthylène", "gaz EO")],
}
NUMBER_SWAPS = [("0.5 mm", "0.6 mm"), ("0,5 mm", "0,6 mm"), ("25 °C", "30 °C"), ("3 T", "7 T"),
                ("1.5 T", "2.5 T"), ("1,5 T", "2,5 T")]


def _el(spec, element_id):
    for e in spec["elements"]:
        if e["element_id"] == element_id:
            return e
    return None


def _find(spec, element):
    return [e for e in spec["elements"] if e["element"] == element]


def _truth(defect_id, element, bbox, rule=None):
    rule = rule or DEFECTS[defect_id][1]
    return {"defect_id": defect_id, "element": element, "bbox_mm": [round(v, 2) for v in bbox],
            "expected_rule": rule, "severity": RULE_SEVERITY[rule]}


def _set_udi(spec, gtin=None, expiry=None, lot=None, barcode=True, hri=True):
    bc, hr = _el(spec, "udi_aidc"), _el(spec, "udi_hri")
    cur = gs1.parse_hri(hr["value"])
    g = gtin or cur["01"]
    x = expiry or cur["17"]
    lt = lot or cur["10"]
    if barcode:
        bc["value"] = gs1.build_element_string(g, x, lt)
    if hri:
        hr["value"] = gs1.build_hri(g, x, lt)


def applicable_rules(spec: dict) -> set[str]:
    from core.regulatory import applicable_requirements

    return {r["rule_id"] for r in applicable_requirements(spec)}


def eligible(defect_id: str, spec: dict) -> bool:
    rules = applicable_rules(spec)
    if DEFECTS[defect_id][1] not in rules:
        return False
    lvl, mkt = spec["packaging_level"], spec["market"]
    if defect_id in ("D09", "D13"):
        return len(spec["languages"]) > 1
    if defect_id == "D10":
        return any(any(a in (e["value"] or "") for a, _ in NUMBER_SWAPS) for e in _find(spec, "warning") +
                   _find(spec, "storage_statement") + _find(spec, "mr_conditions"))
    if defect_id == "D06":
        return bool(_el(spec, "expiry_symbol") or _el(spec, "sterilization_symbol"))
    if defect_id == "D07":
        return bool(_el(spec, "sterilization_symbol"))
    if defect_id == "D05":
        return mkt == "EU" and bool(_el(spec, "authorised_rep"))
    _ = lvl
    return True


def inject(spec: dict, defect_id: str, rng: random.Random) -> tuple[dict, list[dict]]:
    s = copy.deepcopy(spec)
    truth = []
    if defect_id == "D01":
        bc = _el(s, "udi_hri")
        g = gs1.parse_hri(bc["value"])["01"]
        bad = g[:-1] + str((int(g[-1]) + rng.randint(1, 9)) % 10)
        _set_udi(s, gtin=bad)
        truth.append(_truth("D01", "udi_aidc", _el(s, "udi_aidc")["bbox_mm"]))
    elif defect_id == "D02":
        hr = _el(s, "udi_hri")
        ais = gs1.parse_hri(hr["value"])
        if rng.random() < 0.5:
            lot = ais["10"]
            i = rng.randint(1, len(lot) - 1)
            ais["10"] = lot[:i] + str((int(lot[i]) + 1) % 10) + lot[i + 1:]
        else:
            x = ais["17"]
            ais["17"] = x[:5] + str((int(x[5]) + 1) % 10)
        hr["value"] = gs1.build_hri(ais["01"], ais["17"], ais["10"])
        truth.append(_truth("D02", "udi_hri", hr["bbox_mm"]))
    elif defect_id == "D03":
        ais = gs1.parse_hri(_el(s, "udi_hri")["value"])
        yy, mm_, dd = int(ais["17"][:2]), int(ais["17"][2:4]), ais["17"][4:]
        mm_ += 1
        if mm_ > 12:
            yy, mm_ = yy + 1, 1
        _set_udi(s, expiry=f"{yy:02d}{mm_:02d}{dd}")
        truth.append(_truth("D03", "udi_aidc", _el(s, "udi_aidc")["bbox_mm"]))
    elif defect_id == "D04":
        mode = rng.choice(["symbol", "text", "both"])
        for eid in (["manufacturer_symbol"] if mode == "symbol" else ["manufacturer_name_address"] if mode == "text"
                    else ["manufacturer_symbol", "manufacturer_name_address"]):
            e = _el(s, eid)
            s["elements"].remove(e)
            truth.append(_truth("D04", eid, e["bbox_mm"]))
    elif defect_id == "D05":
        for eid in ("authorised_rep_symbol", "authorised_rep"):
            e = _el(s, eid)
            s["elements"].remove(e)
        truth.append(_truth("D05", "authorised_rep", e["bbox_mm"]))
    elif defect_id == "D06":
        options = [e for e in (_el(s, "expiry_symbol"), _el(s, "sterilization_symbol")) if e]
        e = rng.choice(options)
        old = "SYM-EXP-OLD" if e["element"] == "expiry_symbol" else "SYM-STE-EO-OLD"
        from generator.label_generator import glyph_size_mm

        srow = M.symbols()[old]
        w, h = glyph_size_mm(srow["glyph_file"])
        e.update(symbol_id=old, value=old, glyph_file=srow["glyph_file"])
        e["bbox_mm"] = [e["bbox_mm"][0], e["bbox_mm"][1], w, h]
        truth.append(_truth("D06", e["element"], e["bbox_mm"]))
    elif defect_id == "D07":
        e = _el(s, "sterilization_symbol")
        s["elements"].remove(e)
        truth.append(_truth("D07", "sterilization_symbol", e["bbox_mm"]))
    elif defect_id == "D08":
        e = _el(s, "expiry_date")
        y, m, d = e["value"].split("-")
        e["value"] = rng.choice([f"{d}.{m}.{y}", f"{m}/{d}/{y}", f"{d}/{m}/{y[2:]}"])
        truth.append(_truth("D08", "expiry_date", e["bbox_mm"]))
    elif defect_id == "D09":
        lang = rng.choice([lg for lg in s["languages"] if lg != "en"])
        dropped = [e for e in s["elements"] if e.get("zone") == "languages" and e.get("language") == lang]
        for e in dropped:
            s["elements"].remove(e)
        hdr = [e for e in dropped if e["element"] == "language_header"][0]
        truth.append(_truth("D09", f"language_panel.{lang}", hdr["bbox_mm"]))
    elif defect_id == "D10":
        cands = []
        for e in _find(s, "warning") + _find(s, "storage_statement") + _find(s, "mr_conditions"):
            for a, b in NUMBER_SWAPS:
                if a in (e["value"] or ""):
                    cands.append((e, a, b))
        e, a, b = rng.choice(cands)
        e["value"] = e["value"].replace(a, b, 1)
        truth.append(_truth("D10", e["element_id"], e["bbox_mm"]))
    elif defect_id == "D11":
        if rng.random() < 0.5:
            bc, hr = _el(s, "udi_aidc"), _el(s, "udi_hri")
            x, y, w, h = bc["bbox_mm"]
            bc["bbox_mm"] = [x, round(hr["bbox_mm"][1] - h + 2.5, 2), w, h]  # slide down onto the HRI text
            truth.append(_truth("D11", "udi_aidc", bc["bbox_mm"]))
        else:
            syms = [e for e in s["elements"] if e["type"] == "symbol" and e["element"] != "udi_symbol"]
            e = rng.choice(syms)
            x, y, w, h = e["bbox_mm"]
            f = rng.choice([0.45, 0.5, 0.55])
            e["bbox_mm"] = [x, y, round(w * f, 2), round(h * f, 2)]
            truth.append(_truth("D11", e["element"], e["bbox_mm"]))
    elif defect_id == "D12":
        e = _el(s, "label_revision")
        cur = s["revision"]
        old = f"R{int(cur[1:]) - 1:02d}"
        e["value"] = e["value"].replace(f"Rev {cur}", f"Rev {old}")
        truth.append(_truth("D12", "label_revision", e["bbox_mm"]))
    elif defect_id == "D13":
        cands = []
        for e in s["elements"]:
            lg = e.get("language")
            if e.get("zone") == "languages" and lg in GLOSSARY_SWAPS:
                for a, b in GLOSSARY_SWAPS[lg]:
                    if a in (e["value"] or ""):
                        cands.append((e, a, b))
        e, a, b = rng.choice(cands)
        e["value"] = e["value"].replace(a, b, 1)
        truth.append(_truth("D13", e["element_id"], e["bbox_mm"]))
    elif defect_id == "D14":
        others = [k for k in M.skus() if k != s["sku_id"]]
        other = rng.choice(others)
        g = M.packaging()[(other, s["packaging_level"])]["gtin14"]
        _set_udi(s, gtin=g)
        truth.append(_truth("D14", "udi_aidc", _el(s, "udi_aidc")["bbox_mm"]))
    else:
        raise ValueError(defect_id)
    return s, truth
