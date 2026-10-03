"""Symbol family: R15 current library version (+ uncertain symbol detections go to review)."""
from __future__ import annotations

from engines.rules import Rule, register


@register
class R15SymbolVersion(Rule):
    id, family, severity = "R15", "symbol", "major"
    title = "Symbols come from the current library version"

    def check(self, model, ctx):
        out = []
        for s in model["symbols"]:
            if s["symbol_id"] and s["status"] == "superseded":
                out.append(self.finding(ctx, f"Symbol {s['symbol_id']} ({s['concept']}) is from superseded library "
                                             f"version {s['library_version']}.", s["concept"], s["bbox_mm"],
                                        "Replace with the current library glyph.", evidence_text=s["symbol_id"]))
            elif not s["symbol_id"]:
                out.append(self.finding(ctx, f"Unrecognised graphic (best match score {s['score']}).", "unknown_graphic",
                                        s["bbox_mm"], "Check the graphic against the symbol library.",
                                        severity="major", uncertain=True))
        return out
