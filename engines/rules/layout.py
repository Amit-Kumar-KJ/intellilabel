"""Layout family: R16 minimum symbol size and overlaps with the UDI carrier."""
from __future__ import annotations

from core import master as M
from engines.extraction import overlap_area
from engines.rules import Rule, register

SIZE_TOLERANCE = 0.9  # allow 10% measurement tolerance


@register
class R16Layout(Rule):
    id, family, severity = "R16", "layout", "minor"
    title = "Symbols meet minimum size and sit clear of the UDI carrier"

    def check(self, model, ctx):
        out = []
        syms = M.symbols()
        for s in model["symbols"]:
            if not s["symbol_id"]:
                continue
            mn = syms[s["symbol_id"]]["min_height_mm"]
            if s["bbox_mm"][3] < mn * SIZE_TOLERANCE:
                out.append(self.finding(ctx, f"Symbol {s['symbol_id']} is {s['bbox_mm'][3]:.1f} mm high; minimum is "
                                             f"{mn} mm.", s["concept"], s["bbox_mm"], f"Scale to at least {mn} mm."))
        for b in model["barcodes"]:
            things = [(ln["text"], ln["bbox_mm"]) for ln in model["lines"]] + \
                     [(s["symbol_id"], s["bbox_mm"]) for s in model["symbols"] if s["symbol_id"]]
            for name, bb in things:
                if overlap_area(b["bbox_mm"], bb) > 0.5:
                    out.append(self.finding(ctx, f"UDI carrier overlaps '{name}'.", "udi_aidc", b["bbox_mm"],
                                            "Restore the quiet zone around the Data Matrix.", evidence_text=name))
                    break
        return out
