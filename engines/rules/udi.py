"""UDI family: R01-R04."""
from __future__ import annotations

from datetime import date

from core import gs1
from engines.rules import Rule, register


def _barcode(model):
    bcs = [b for b in model["barcodes"] if "01" in b["ais"]]
    return bcs[0] if bcs else None


def parse_any_date(s: str) -> date | None:
    import re

    s = (s or "").strip()
    for pat, order in ((r"^(\d{4})-(\d{2})-(\d{2})$", "ymd"), (r"^(\d{2})\.(\d{2})\.(\d{4})$", "dmy"),
                       (r"^(\d{2})/(\d{2})/(\d{4})$", "mdy"), (r"^(\d{2})/(\d{2})/(\d{2})$", "dmy2"),
                       (r"^(\d{4})-(\d{2})$", "ym")):
        m = re.match(pat, s)
        if m:
            g = [int(x) for x in m.groups()]
            try:
                if order == "ymd":
                    return date(g[0], g[1], g[2])
                if order == "dmy":
                    return date(g[2], g[1], g[0])
                if order == "mdy":
                    return date(g[2], g[0], g[1])
                if order == "dmy2":
                    return date(2000 + g[2], g[1], g[0])
                if order == "ym":
                    return date(g[0], g[1], 1)
            except ValueError:
                return None
    return None


@register
class R01CheckDigit(Rule):
    id, family, severity = "R01", "udi", "critical"
    title = "UDI-DI (GTIN-14) has a valid GS1 mod-10 check digit"

    def check(self, model, ctx):
        bc = _barcode(model)
        hri = model["elements"].get("udi_hri")
        gtin = bc["ais"].get("01") if bc else (gs1.parse_hri(hri["value"]).get("01") if hri else None)
        if not gtin:
            return []  # absence is reported by R02
        if not gs1.is_valid_gtin(gtin):
            return [self.finding(ctx, f"GTIN {gtin} fails the GS1 mod-10 check digit (expected "
                                      f"{gs1.check_digit(gtin[:-1])}, printed {gtin[-1]}).", "udi_aidc",
                                 bc["bbox_mm"] if bc else hri["bbox_mm"], "Regenerate the UDI from the master GTIN.",
                                 evidence_text=gtin)]
        return []


@register
class R02PlainTextMatchesBarcode(Rule):
    id, family, severity = "R02", "udi", "critical"
    title = "Plain-text UDI equals the UDI encoded in the barcode"

    def check(self, model, ctx):
        bc = _barcode(model)
        hri = model["elements"].get("udi_hri")
        out = []
        if not bc:
            out.append(self.finding(ctx, "No readable GS1 UDI carrier (Data Matrix) found on the label.", "udi_aidc",
                                    hri["bbox_mm"] if hri else None, "Add or repair the UDI Data Matrix.",
                                    uncertain=bool(model["source"] == "image")))
        if not hri:
            out.append(self.finding(ctx, "No human-readable UDI text found.", "udi_hri", bc["bbox_mm"] if bc else None,
                                    "Print the UDI in plain text below the barcode."))
        if bc and hri:
            h = gs1.parse_hri(hri["value"])
            b = {k: v for k, v in bc["ais"].items() if not k.startswith("_")}
            if h != b:
                diffs = [f"({k}) text={h.get(k)} barcode={b.get(k)}" for k in sorted(set(h) | set(b))
                         if h.get(k) != b.get(k)]
                out.append(self.finding(ctx, "Plain-text UDI differs from the barcode: " + "; ".join(diffs),
                                        "udi_hri", hri["bbox_mm"], "Regenerate HRI and barcode from the same UDI "
                                                                    "string.", evidence_text=hri["value"],
                                        uncertain=hri.get("uncertain", False)))
        return out


@register
class R03ProductionIdentifiers(Rule):
    id, family, severity = "R03", "udi", "critical"
    title = "Lot, expiry and serial in the barcode match the printed text"

    def check(self, model, ctx):
        bc = _barcode(model)
        if not bc:
            return []
        out = []
        el = model["elements"]
        exp = el.get("expiry_date")
        if "17" in bc["ais"] and exp:
            d = parse_any_date(exp["value"])
            if d and d.strftime("%y%m%d") != bc["ais"]["17"]:
                out.append(self.finding(ctx, f"Expiry in barcode (17){bc['ais']['17']} does not match printed "
                                             f"expiry {exp['value']}.", "udi_aidc", bc["bbox_mm"],
                                        "Re-derive both from manufacture date + shelf life.",
                                        evidence_text=exp["value"]))
        lot = el.get("lot")
        if "10" in bc["ais"] and lot and lot["value"].strip() != bc["ais"]["10"]:
            out.append(self.finding(ctx, f"Lot in barcode (10){bc['ais']['10']} does not match printed lot "
                                         f"{lot['value']}.", "udi_aidc", bc["bbox_mm"],
                                    "Use the batch record lot in both places.", evidence_text=lot["value"],
                                    uncertain=lot.get("uncertain", False)))
        return out


@register
class R04MasterGtin(Rule):
    id, family, severity = "R04", "udi", "critical"
    title = "Barcode GTIN matches the master GTIN for the SKU"

    def check(self, model, ctx):
        bc = _barcode(model)
        if not bc:
            return []
        g = bc["ais"].get("01")
        exp = ctx["expected_gtin"]
        if g and gs1.is_valid_gtin(g) and g != exp:
            other = ctx["gtin_owner"].get(g)
            who = f" (it belongs to {other[0]} {other[1]})" if other else ""
            return [self.finding(ctx, f"Barcode GTIN {g} is not the master GTIN {exp} for {ctx['label']['sku_id']} "
                                      f"{ctx['label']['packaging_level']}{who}.", "udi_aidc", bc["bbox_mm"],
                                 f"Use GTIN {exp} from master data.", evidence_text=g)]
        return []
