"""Content family: R17 printed texts match approved master text (numbers, units, negations identical)."""
from __future__ import annotations

import re

from core import master as M
from engines.rules import Rule, register

NEGATIONS = {"en": [r"\bnot\b", r"\bdo not\b", r"\bnever\b", r"\bno\b"],
             "de": [r"\bnicht\b", r"\bkein\w*\b", r"\bnie\b"],
             "fr": [r"\bne\b", r"\bpas\b", r"\bjamais\b", r"\bn'"]}
NUM_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(°C|mm|cm|T/m|T|%|months?|Monate|mois)?")


def numbers_units(text: str) -> list[tuple[str, str]]:
    return [(n.replace(",", "."), u or "") for n, u in NUM_RE.findall(text or "")]


def negation_count(text: str, lang: str) -> int:
    return sum(len(re.findall(p, (text or "").lower())) for p in NEGATIONS.get(lang, []))


def invariant_diffs(src: str, txt: str, lang: str) -> list[str]:
    d = []
    a, b = numbers_units(src), numbers_units(txt)
    if sorted(a) != sorted(b):
        d.append(f"numbers/units differ: approved {a} vs printed {b}")
    if negation_count(src, lang) != negation_count(txt, lang):
        d.append("negation differs from approved text")
    return d


@register
class R17Content(Rule):
    id, family, severity = "R17", "content", "critical"
    title = "Warning text matches the approved master text; numbers, units and negations identical"

    def check(self, model, ctx):
        from engines.rules.language import forbidden_hits

        out = []
        expected_ids = ctx["expected_text_ids"]
        for t in model["text_blocks"]:
            m = t["master_match"]
            if not m:
                if t["language"] and forbidden_hits(t["text"], t["language"]):
                    continue  # reported by R21 (glossary)
                if t["panel"]:
                    out.append(self.finding(ctx, f"Text block not found in the approved text library: "
                                                 f"'{t['text'][:60]}'.", "text", t["bbox_mm"],
                                            "Use an approved master text.", severity="major", uncertain=True,
                                            evidence_text=t["text"]))
                continue
            lang = m["language"]
            approved = m["approved_text"]
            if m["exact"]:
                fam = re.match(r"(MT-[A-Z]+)", m["text_id"]).group(1)
                if m["text_id"] not in expected_ids and any(e.startswith(fam + "-") for e in expected_ids):
                    exp = sorted(e for e in expected_ids if e.startswith(fam + "-"))[0]
                    out.append(self.finding(ctx, f"[{lang}] {m['text_id']} is printed but master data now requires "
                                                 f"{exp}.", m["text_id"], t["bbox_mm"],
                                            f"Regenerate the label to use {exp}.", severity="major",
                                            evidence_text=t["text"]))
                continue
            diffs = invariant_diffs(approved, t["text"], lang)
            if diffs and not (t["source"] == "ocr" and t["confidence"] < 0.8):
                out.append(self.finding(ctx, f"[{lang}] {m['text_id']}: " + "; ".join(diffs) + ".", m["text_id"],
                                        t["bbox_mm"], f"Replace with approved text: '{approved}'.",
                                        evidence_text=t["text"], approved_text=approved))
            elif forbidden_hits(t["text"], lang):
                continue  # glossary deviation is reported by R21
            elif t["source"] == "pdf":
                out.append(self.finding(ctx, f"[{lang}] {m['text_id']}: printed text deviates from the approved "
                                             f"master text.", m["text_id"], t["bbox_mm"],
                                        f"Replace with approved text: '{approved}'.", severity="major",
                                        evidence_text=t["text"], approved_text=approved))
            elif diffs:
                out.append(self.finding(ctx, f"[{lang}] {m['text_id']}: possible deviation (OCR): " + "; ".join(diffs),
                                        m["text_id"], t["bbox_mm"], "Verify against the approved text.",
                                        severity="major", uncertain=True, evidence_text=t["text"]))
        return out


def all_text_ids() -> set[str]:
    return {tid for tid, _ in M.master_texts()}
