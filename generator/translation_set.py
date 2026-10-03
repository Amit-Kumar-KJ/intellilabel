"""Phase 4.7: translation test set: correct translations plus ~25 seeded errors.

error types: glossary (forbidden variant), number (changed number/unit), negation (dropped negation),
missing_sentence. Expected statuses follow Phase 11.3: glossary -> WARNING, others -> FAIL.
"""
from __future__ import annotations

import random
import re

from core import master as M
from generator.defect_injector import GLOSSARY_SWAPS, NUMBER_SWAPS

NEGATION_DROPS = {"de": [("nicht ", ""), ("Nicht ", "")], "fr": [("Ne pas ", ""), ("ne pas ", ""), ("n'est pas ", "est ")]}


def build_translation_set(seed: int) -> list[dict]:
    rng = random.Random(seed + 3)
    texts = M.master_texts()
    ids = sorted({tid for (tid, lg) in texts if lg == "en" and (tid, "de") in texts})
    rows = []
    n = 0

    def add(tid, lg, translation, status, etype):
        nonlocal n
        rows.append({"case_id": f"TR-{n:03d}", "text_id": tid, "language": lg, "source_en": texts[(tid, "en")]["text"],
                     "translation": translation, "expected_status": status, "error_type": etype})
        n += 1

    errors = []
    for tid in ids:
        for lg in ("de", "fr"):
            t = texts[(tid, lg)]["text"]
            add(tid, lg, t, "PASS", "none")
            for a, b in GLOSSARY_SWAPS[lg]:
                if a in t:
                    errors.append((tid, lg, t.replace(a, b, 1), "WARNING", "glossary"))
            for a, b in NUMBER_SWAPS:
                if a in t:
                    errors.append((tid, lg, t.replace(a, b, 1), "FAIL", "number"))
            for a, b in NEGATION_DROPS[lg]:
                if a in t:
                    errors.append((tid, lg, t.replace(a, b, 1), "FAIL", "negation"))
                    break
            sents = [s for s in re.split(r"(?<=[.!?])\s+", t) if s]
            if len(sents) > 1:
                errors.append((tid, lg, " ".join(sents[:-1]), "FAIL", "missing_sentence"))
    rng.shuffle(errors)
    by_type: dict[str, list] = {}
    for e in errors:
        by_type.setdefault(e[4], []).append(e)
    # balanced pick: up to 7 per type, ~25 total
    picked = []
    for et in ("glossary", "number", "negation", "missing_sentence"):
        picked += by_type.get(et, [])[:7]
    for e in picked[:26]:
        add(*e)
    return rows
