"""Version family: R18 printed revision matches the current revision."""
from __future__ import annotations

from engines.rules import Rule, register


@register
class R18Revision(Rule):
    id, family, severity = "R18", "version", "critical"
    title = "Label revision matches the current released revision"

    def check(self, model, ctx):
        el = model["elements"].get("label_revision")
        exp = ctx["label"]["revision"]
        if not el:
            return [self.finding(ctx, "Label revision code not found.", "label_revision", None,
                                 f"Print revision {exp}.", severity="major")]
        if el.get("revision") != exp:
            return [self.finding(ctx, f"Printed revision {el.get('revision')} but the current revision is {exp}.",
                                 "label_revision", el["bbox_mm"], f"Print revision {exp}.",
                                 evidence_text=el["value"], uncertain=el.get("uncertain", False))]
        return []
