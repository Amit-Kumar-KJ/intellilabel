"""Presence family: R05-R07, R09-R13, R19, R20 (generic element presence for new requirements)."""
from __future__ import annotations

import re

from rapidfuzz import fuzz

from engines.rules import Rule, register


def _get(model, name):
    return model["elements"].get(name)


def _any_lang(model, prefix):
    return [v for k, v in model["elements"].items() if k.startswith(prefix + ".") and isinstance(v, dict)]


@register
class R05Manufacturer(Rule):
    id, family, severity = "R05", "presence", "critical"
    title = "Manufacturer name and address present, with the manufacturer symbol"

    def check(self, model, ctx):
        out = []
        sym = _get(model, "manufacturer_symbol")
        txt = _get(model, "manufacturer_name_address")
        if not sym:
            out.append(self.finding(ctx, "Manufacturer symbol not found.", "manufacturer_symbol",
                                    txt["bbox_mm"] if txt else None, "Place the manufacturer symbol next to the name "
                                                                     "and address."))
        if not txt:
            # text may exist without its symbol: look for the master manufacturer name anywhere
            name = ctx["manufacturer"]["name"]
            hit = next((b for b in model["blocks"] if fuzz.partial_ratio(name, b["text"]) > 90), None)
            if not hit:
                out.append(self.finding(ctx, "Manufacturer name and address not found.", "manufacturer_name_address",
                                        sym["bbox_mm"] if sym else None, "Add the manufacturer name and address from "
                                                                         "master data."))
        elif fuzz.partial_ratio(ctx["manufacturer"]["name"], txt["value"]) < 85:
            out.append(self.finding(ctx, f"Manufacturer text does not match master data ('{txt['value'][:40]}').",
                                    "manufacturer_name_address", txt["bbox_mm"], "Use the registered name/address.",
                                    severity="major", uncertain=txt.get("uncertain", False)))
        return out


@register
class R06AuthorisedRep(Rule):
    id, family, severity = "R06", "presence", "critical"
    title = "EU labels carry authorised representative details when the manufacturer is outside the EU"

    def check(self, model, ctx):
        txt = _get(model, "authorised_rep")
        sym = _get(model, "authorised_rep_symbol")
        if txt and sym:
            return []
        hit = next((b for b in model["blocks"] if fuzz.partial_ratio(ctx["manufacturer"]["eu_auth_rep_name"],
                                                                     b["text"]) > 90), None)
        if hit and sym:
            return []
        return [self.finding(ctx, "EU authorised representative (EC REP symbol + name and address) missing.",
                             "authorised_rep", (txt or sym or {}).get("bbox_mm"),
                             "Add the EC REP block from manufacturer master data.")]


@register
class R07Importer(Rule):
    id, family, severity = "R07", "presence", "major"
    title = "Importer details present where applicable"

    def check(self, model, ctx):
        if _get(model, "importer") or any(fuzz.partial_ratio(ctx["manufacturer"]["eu_importer_name"], b["text"]) > 90
                                          for b in model["blocks"]):
            return []
        return [self.finding(ctx, "Importer name and address not found.", "importer", None,
                             "Add the importer block (symbol + name and address).")]


@register
class R09Sterile(Rule):
    id, family, severity = "R09", "presence", "critical"
    title = "Sterile devices show sterile state and method, and the damaged-package warning"

    def check(self, model, ctx):
        out = []
        for req in self.reqs(ctx):
            if req["label_element"] == "sterile_indication":
                if not _get(model, "sterilization_symbol"):
                    txt = _any_lang(model, "sterile_indication")
                    out.append(self.finding(ctx, "Sterilization symbol (sterile state and method) not found.",
                                            "sterilization_symbol", None,
                                            "Add the 'STERILE EO' symbol for ethylene oxide sterilization.",
                                            req=req, sterile_text_present=bool(txt)))
            elif req["label_element"] == "damaged_package_warning":
                if not _get(model, "damaged_package_symbol") and not _any_lang(model, "damaged_package_warning"):
                    out.append(self.finding(ctx, "No 'do not use if package is damaged' symbol or statement.",
                                            "damaged_package_warning", None, "Add symbol and/or approved text "
                                                                             "MT-DAMAGE-01.", req=req))
        return out


@register
class R10CeMarking(Rule):
    id, family, severity = "R10", "presence", "critical"
    title = "CE marking present with notified body number where required"

    def check(self, model, ctx):
        ce = _get(model, "ce_marking")
        nb = _get(model, "notified_body_number")
        if not ce:
            return [self.finding(ctx, "CE marking not found.", "ce_marking", None, "Add CE marking.")]
        expected = ctx["product"].get("notified_body")
        if not nb or not re.fullmatch(r"\d{4}", nb["value"].strip()) or (expected and nb["value"].strip() != expected):
            return [self.finding(ctx, f"Notified body number missing or wrong next to CE marking (expected {expected}).",
                                 "notified_body_number", ce["bbox_mm"], f"Print {expected} after the CE marking.")]
        return []


@register
class R11Rx(Rule):
    id, family, severity = "R11", "presence", "major"
    title = "Prescription statement on US prescription devices"

    def check(self, model, ctx):
        if _get(model, "rx_statement"):
            return []
        return [self.finding(ctx, "'Rx only' statement not found.", "rx_statement", None, "Add 'Rx only'.")]


@register
class R12Ifu(Rule):
    id, family, severity = "R12", "presence", "major"
    title = "Consult-instructions symbol or statement present when an IFU applies"

    def check(self, model, ctx):
        if _get(model, "ifu_indication") or _any_lang(model, "ifu_text"):
            return []
        return [self.finding(ctx, "No consult-IFU symbol or statement found.", "ifu_indication", None,
                             "Add the consult-IFU symbol.")]


@register
class R13Mr(Rule):
    id, family, severity = "R13", "presence", "major"
    title = "MR safety marking present on implants where applicable"

    def check(self, model, ctx):
        if _get(model, "mr_marking"):
            return []
        return [self.finding(ctx, "MR Conditional marking not found.", "mr_marking", None,
                             "Add the MR Conditional marking.")]


@register
class R19DeviceName(Rule):
    id, family, severity = "R19", "presence", "critical"
    title = "Device name or trade name present"

    def check(self, model, ctx):
        dn = _get(model, "device_name")
        brand = ctx["product"]["brand"]
        if dn and fuzz.ratio(dn["value"], brand) >= 85:
            return []
        if any(fuzz.ratio(b["text"], brand) >= 85 for b in model["blocks"]):
            return []
        return [self.finding(ctx, f"Device trade name '{brand}' not found.", "device_name",
                             dn["bbox_mm"] if dn else None, f"Print '{brand}' in the header.")]


ELEMENT_ALIASES = {
    "single_use_indication": ["single_use_indication", "single_use_text."],
    "storage_statement": ["storage_statement."],
    "lot": ["lot"],
    "model": ["model"],
    "md_symbol": ["md_symbol"],
}


@register
class R20GenericPresence(Rule):
    """Generic presence check driven by the requirement row's label_element. This is what lets a NEW regulatory
    requirement (Scenario B) be enforced without writing new code."""
    id, family, severity = "R20", "presence", "major"
    title = "Required label element present (generic, requirement-driven)"

    def check(self, model, ctx):
        out = []
        keys = list(model["elements"].keys())
        for req in self.reqs(ctx):
            el = req["label_element"]
            aliases = ELEMENT_ALIASES.get(el, [el, el + "."])
            ok = any(k == a or (a.endswith(".") and k.startswith(a)) for k in keys for a in aliases)
            if not ok:
                out.append(self.finding(ctx, f"Required element '{el}' not found ({req['requirement_text']}).", el,
                                        None, f"Add '{el}' to the label template.", req=req))
        return out
