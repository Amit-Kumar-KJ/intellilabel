"""Format family: R08 date formats."""
from __future__ import annotations

import re

from engines.rules import Rule, register

FMT_RE = {"YYYY-MM-DD": r"^\d{4}-\d{2}-\d{2}$", "YYYY-MM": r"^\d{4}-\d{2}$", "DD.MM.YYYY": r"^\d{2}\.\d{2}\.\d{4}$"}


@register
class R08DateFormat(Rule):
    id, family, severity = "R08", "format", "major"
    title = "Dates follow the market's required plain-text format"

    def check(self, model, ctx):
        fmt = ctx["date_format"]
        pat = FMT_RE.get(fmt, r"^\d{4}-\d{2}-\d{2}$")
        out = []
        for name in ("expiry_date", "mfg_date"):
            el = model["elements"].get(name)
            if el and not re.match(pat, el["value"].strip()):
                out.append(self.finding(ctx, f"{name} '{el['value']}' is not in the required {fmt} format for "
                                             f"{ctx['label']['market']}.", name, el["bbox_mm"],
                                        f"Print the date as {fmt}.", evidence_text=el["value"],
                                        uncertain=el.get("uncertain", False)))
        return out
