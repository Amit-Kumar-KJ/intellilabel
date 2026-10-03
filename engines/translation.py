"""Phase 11.3: translation validator.

For each translated master text:
 1. glossary   - approved term present when the English source uses the concept; no forbidden variant
 2. invariants - numbers, units and negations identical to the source (and to the approved translation if any)
 3. completeness - same sentence count as the source
 4. semantic similarity (optional, `pip install sentence-transformers`, TRANSLATION_SEMANTIC=1)
Status: FAIL if an invariant or completeness is broken, WARNING for glossary variants / low similarity, else PASS.
"""
from __future__ import annotations

import os
import re

from core import master as M
from engines.rules.content import negation_count, numbers_units
from engines.rules.language import forbidden_hits


def sentences(t: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", (t or "").strip()) if s]


def _approved_terms(lang: str) -> dict:
    return {g["term_id"]: g for g in M.glossary() if g["language"] == lang}


def check(source_en: str, translation: str, language: str, text_id: str | None = None) -> dict:
    problems = []
    status = "PASS"
    # 1. glossary
    en_terms = _approved_terms("en")
    tgt_terms = _approved_terms(language)
    for f, a in forbidden_hits(translation, language):
        problems.append({"check": "glossary", "severity": "WARNING", "detail": f"forbidden variant '{f}' (use '{a}')"})
    for tid, g in en_terms.items():
        if tid in tgt_terms and re.search(re.escape(g["approved_term"]), source_en, re.I):
            if not re.search(re.escape(tgt_terms[tid]["approved_term"]), translation, re.I):
                if not any(p["check"] == "glossary" for p in problems):
                    problems.append({"check": "glossary", "severity": "WARNING",
                                     "detail": f"approved term '{tgt_terms[tid]['approved_term']}' missing"})
    # 2. invariants
    a, b = sorted(numbers_units(source_en)), sorted(numbers_units(translation))
    if a != b:
        problems.append({"check": "invariants", "severity": "FAIL", "detail": f"numbers/units {a} vs {b}"})
    ref = M.master_texts().get((text_id, language)) if text_id else None
    if ref:
        if negation_count(ref["text"], language) != negation_count(translation, language):
            problems.append({"check": "invariants", "severity": "FAIL", "detail": "negation differs from approved "
                                                                                  "translation"})
    elif (negation_count(source_en, "en") > 0) != (negation_count(translation, language) > 0):
        problems.append({"check": "invariants", "severity": "FAIL", "detail": "negation lost or added"})
    # 3. completeness
    ns, nt = len(sentences(source_en)), len(sentences(translation))
    if nt < ns:
        problems.append({"check": "completeness", "severity": "FAIL", "detail": f"{nt} sentence(s) vs {ns} in source"})
    elif nt > ns + 1:
        problems.append({"check": "completeness", "severity": "WARNING", "detail": f"{nt} sentences vs {ns}"})
    # 4. semantic similarity (optional)
    if os.getenv("TRANSLATION_SEMANTIC") == "1":
        try:
            sim = semantic_similarity(source_en, translation)
            if sim < 0.75:
                problems.append({"check": "semantic", "severity": "WARNING", "detail": f"similarity {sim:.2f}"})
        except Exception:  # noqa: BLE001
            pass
    if any(p["severity"] == "FAIL" for p in problems):
        status = "FAIL"
    elif problems:
        status = "WARNING"
    return {"status": status, "problems": problems}


_model = None


def semantic_similarity(a: str, b: str) -> float:
    global _model
    from sentence_transformers import SentenceTransformer, util

    if _model is None:
        _model = SentenceTransformer("sentence-transformers/LaBSE")
    e = _model.encode([a, b], convert_to_tensor=True)
    return float(util.cos_sim(e[0], e[1]))
