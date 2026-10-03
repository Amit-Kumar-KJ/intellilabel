"""Language family: R14 required languages present; R21 glossary compliance."""
from __future__ import annotations

import re

from core import master as M
from engines.rules import Rule, register


@register
class R14Languages(Rule):
    id, family, severity = "R14", "language", "critical"
    title = "All required languages for the market are present"

    def check(self, model, ctx):
        req = set(ctx["languages"]) if ctx["label"]["packaging_level"] != "shipper" else {"en"}
        missing = sorted(req - set(model["languages_present"]))
        if missing:
            return [self.finding(ctx, f"Missing required language(s): {', '.join(missing)} (present: "
                                      f"{', '.join(model['languages_present']) or 'none'}).", "language_panels", None,
                                 f"Add the {', '.join(missing)} panel(s) with approved translations.")]
        return []


def forbidden_hits(text: str, language: str) -> list[tuple[str, str]]:
    """[(forbidden_variant, approved_term)] present in text, ignoring occurrences inside the approved term."""
    hits = []
    for g in M.glossary():
        if g["language"] != language:
            continue
        # allow short inflection suffixes (beschädigt -> beschädigter, defekt -> defekter)
        cleaned = re.sub(re.escape(g["approved_term"]) + r"\w{0,3}", " ", text, flags=re.IGNORECASE)
        for f in g["forbidden"]:
            if re.search(r"(?<!\w)" + re.escape(f) + r"\w{0,3}(?!\w)", cleaned, flags=re.IGNORECASE):
                hits.append((f, g["approved_term"]))
    return hits


@register
class R21Glossary(Rule):
    id, family, severity = "R21", "language", "major"
    title = "Translations use approved glossary terms only"

    def check(self, model, ctx):
        out = []
        for t in model["text_blocks"]:
            if not t["language"]:
                continue
            for f, a in forbidden_hits(t["text"], t["language"]):
                out.append(self.finding(ctx, f"[{t['language']}] forbidden term '{f}' used; approved term is '{a}'.",
                                        t["master_match"]["text_id"] if t["master_match"] else "text", t["bbox_mm"],
                                        f"Replace '{f}' with '{a}' (use the approved master text).",
                                        evidence_text=t["text"]))
        return out
