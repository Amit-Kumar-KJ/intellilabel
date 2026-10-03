"""Phase 7.1-7.2: extraction service.  extract(pdf_or_image) -> LabelModel (a plain dict).

The extractor reads the label artwork ONLY (it never opens label.json). Order, cheapest first:
  1. native PDF text (PyMuPDF spans with font, size and bbox)
  2. OCR fallback (Tesseract) for PNG/JPEG/photographed labels, word boxes + confidences
  3. barcodes: GS1 Data Matrix (pylibdmtx) and linear codes (pyzbar), parsed into AIs
  4. symbols: for digital PDFs each embedded image is classified against the glyph library; for raster input
     multi-scale template matching (OpenCV NCC, scales 0.5-1.5) with non-maximum suppression
  5. language panels: panel headers + per-block language detection (stopword/script heuristic)
Then `normalise` turns raw extractions into named elements (Step 7.2).
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from rapidfuzz import fuzz

from core import gs1
from core import master as M
from core.config import DPI, SYMBOL_DIR

PX_MM = DPI / 25.4
PT_TO_MM = 25.4 / 72
SYMBOL_THRESHOLD = 0.75
CLASSIFY_THRESHOLD = 0.55
TEXT_MATCH_THRESHOLD = 90  # rapidfuzz ratio for an exact-ish master text match
TEXT_PROBABLE_THRESHOLD = 72  # below this a block is "unmatched"
UNCERTAIN_CONFIDENCE = 0.6

TEXT_ID_ELEMENT = {"MT-WARN": "warning", "MT-STOR": "storage_statement", "MT-STER": "sterile_indication",
                   "MT-REUSE": "single_use_text", "MT-MR": "mr_conditions", "MT-IFU": "ifu_text",
                   "MT-DAMAGE": "damaged_package_warning", "MT-DESC": "device_description", "MT-RX": "rx_statement"}

SYMBOL_ELEMENT = {"SYM-MFR": "manufacturer_symbol", "SYM-MFGDATE": "mfg_date_symbol", "SYM-EXP": "expiry_symbol",
                  "SYM-LOT": "lot_symbol", "SYM-REF": "ref_symbol", "SYM-ECREP": "authorised_rep_symbol",
                  "SYM-IMPORTER": "importer_symbol", "SYM-STE-EO": "sterilization_symbol",
                  "SYM-DAMAGED": "damaged_package_symbol", "SYM-NOREUSE": "single_use_indication",
                  "SYM-IFU": "ifu_indication", "SYM-MD": "md_symbol", "SYM-UDI": "udi_symbol",
                  "SYM-MRCOND": "mr_marking", "SYM-CE": "ce_marking", "SYM-EXP-OLD": "expiry_symbol",
                  "SYM-STE-EO-OLD": "sterilization_symbol"}

STOPWORDS = {
    "en": {"the", "and", "use", "do", "not", "only", "store", "below", "if", "is", "for", "of", "to", "in", "at",
           "under", "its", "more", "than", "above", "keep", "dry", "using", "package", "single", "consult",
           "instructions", "permitted", "conditions", "sterile", "sterilized", "unless", "or", "damaged"},
    "de": {"der", "die", "das", "und", "nicht", "mit", "bei", "zum", "nur", "unter", "den", "ist", "über", "hinaus",
           "lagern", "trocken", "aufbewahren", "verwenden", "steril", "sterilisiert", "verpackung", "gebrauchsanweisung",
           "beachten", "bedingungen", "einmalgebrauch", "solange", "oder", "als", "mehr"},
    "fr": {"le", "la", "les", "de", "des", "et", "ne", "pas", "à", "au", "du", "si", "un", "une", "est", "selon",
           "plus", "son", "conserver", "moins", "sec", "utiliser", "usage", "unique", "consulter", "mode", "emploi",
           "stérile", "stérilisé", "emballage", "sous", "conditions", "tant", "que", "ou", "l'emballage", "d'emploi"},
}
LANG_CODES = {"EN": "en", "DE": "de", "FR": "fr", "JA": "ja", "ZH": "zh", "AR": "ar", "ES": "es", "IT": "it"}
DATE_RE = re.compile(r"^\s*(\d{4}-\d{2}(-\d{2})?|\d{2}[./]\d{2}[./]\d{2,4})\s*$")


# ---------------------------------------------------------------- language detection (langdetect-free heuristic)
def detect_language(text: str) -> tuple[str | None, float]:
    if not text or len(text.strip()) < 2:
        return None, 0.0
    if re.search(r"[぀-ヿ]", text):
        return "ja", 0.95
    if re.search(r"[一-鿿]", text):
        return "zh", 0.9
    if re.search(r"[؀-ۿ]", text):
        return "ar", 0.95
    words = re.findall(r"[a-zA-Zäöüßéèêàâçîôûëïœ']+", text.lower())
    if not words:
        return None, 0.0
    scores = {lg: sum(1 for w in words if w in sw) for lg, sw in STOPWORDS.items()}
    if re.search(r"[äöüß]", text):
        scores["de"] += 2
    if re.search(r"[éèêàâçîôûœ]", text):
        scores["fr"] += 2
    best = max(scores, key=scores.get)
    tot = sum(scores.values())
    if scores[best] == 0:
        return None, 0.0
    return best, scores[best] / tot


# ---------------------------------------------------------------- geometry helpers
def bbox_union(a, b):
    x0, y0 = min(a[0], b[0]), min(a[1], b[1])
    x1, y1 = max(a[0] + a[2], b[0] + b[2]), max(a[1] + a[3], b[1] + b[3])
    return [x0, y0, x1 - x0, y1 - y0]


def iou(a, b):
    ax1, ay1, bx1, by1 = a[0] + a[2], a[1] + a[3], b[0] + b[2], b[1] + b[3]
    iw = max(0, min(ax1, bx1) - max(a[0], b[0]))
    ih = max(0, min(ay1, by1) - max(a[1], b[1]))
    inter = iw * ih
    u = a[2] * a[3] + b[2] * b[3] - inter
    return inter / u if u > 0 else 0.0


def overlap_area(a, b):
    iw = max(0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    ih = max(0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    return iw * ih


def r2(b):
    return [round(float(v), 2) for v in b]


# ---------------------------------------------------------------- 1. native PDF text
def pdf_lines(page) -> list[dict]:
    lines = []
    d = page.get_text("dict")
    for b in d["blocks"]:
        for ln in b.get("lines", []):
            spans = [s for s in ln["spans"] if s["text"].strip()]
            if not spans:
                continue
            text = "".join(s["text"] for s in ln["spans"]).strip()
            x0 = min(s["bbox"][0] for s in spans)
            y0 = min(s["bbox"][1] for s in spans)
            x1 = max(s["bbox"][2] for s in spans)
            y1 = max(s["bbox"][3] for s in spans)
            size = max(s["size"] for s in spans)
            bold = any("Bold" in s["font"] for s in spans)
            lines.append({"text": text, "bbox_mm": r2([x0 * PT_TO_MM, y0 * PT_TO_MM, (x1 - x0) * PT_TO_MM,
                                                       (y1 - y0) * PT_TO_MM]), "size_pt": round(size, 2),
                          "bold": bold, "confidence": 1.0, "source": "pdf"})
    return lines


# ---------------------------------------------------------------- 2. OCR fallback
def ocr_lines(gray: np.ndarray) -> list[dict]:
    """Tesseract (page segmentation 3) word boxes -> lines; tesseract lines are split at wide gaps (columns)."""
    import pytesseract

    try:
        data = pytesseract.image_to_data(gray, lang="eng+deu+fra", output_type=pytesseract.Output.DICT,
                                         config="--psm 3")
    except Exception:  # noqa: BLE001 - language packs missing
        data = pytesseract.image_to_data(gray, output_type=pytesseract.Output.DICT, config="--psm 3")
    groups: dict[tuple, list[dict]] = {}
    for i, t in enumerate(data["text"]):
        if not t.strip() or float(data["conf"][i]) < 0:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        groups.setdefault(key, []).append({"text": t, "x": data["left"][i], "y": data["top"][i],
                                           "w": data["width"][i], "h": data["height"][i],
                                           "conf": float(data["conf"][i]) / 100.0})
    lines: list[list[dict]] = []
    rows: list[list[dict]] = []
    for ws in groups.values():  # tesseract sometimes puts two close text rows in one "line": split by y first
        ws.sort(key=lambda w: w["y"] + w["h"] / 2)
        med_h = float(np.median([w["h"] for w in ws]))
        row = [ws[0]]
        for w in ws[1:]:
            if (w["y"] + w["h"] / 2) - (row[-1]["y"] + row[-1]["h"] / 2) > 0.6 * med_h:
                rows.append(row)
                row = [w]
            else:
                row.append(w)
        rows.append(row)
    for ws in rows:
        ws.sort(key=lambda w: w["x"])
        cur = [ws[0]]
        for w in ws[1:]:
            last = cur[-1]
            if w["x"] - (last["x"] + last["w"]) > 2.5 * max(w["h"], last["h"]):
                lines.append(cur)
                cur = [w]
            else:
                cur.append(w)
        lines.append(cur)
    out = []
    for ln in lines:
        x0 = min(w["x"] for w in ln)
        y0 = min(w["y"] for w in ln)
        x1 = max(w["x"] + w["w"] for w in ln)
        y1 = max(w["y"] + w["h"] for w in ln)
        h_mm = (y1 - y0) / PX_MM
        out.append({"text": " ".join(w["text"] for w in ln),
                    "bbox_mm": r2([x0 / PX_MM, y0 / PX_MM, (x1 - x0) / PX_MM, h_mm]),
                    "size_pt": round(h_mm / PT_TO_MM / 0.75, 1), "bold": False,
                    "confidence": round(min(w["conf"] for w in ln), 2), "source": "ocr"})
    return out


def group_paragraphs(lines: list[dict]) -> list[dict]:
    """Merge vertically adjacent lines with same left edge and font size into paragraphs."""
    ls = sorted(lines, key=lambda l_: (l_["bbox_mm"][0], l_["bbox_mm"][1]))
    paras: list[dict] = []
    for ln in sorted(ls, key=lambda l_: (l_["bbox_mm"][1], l_["bbox_mm"][0])):
        x, y, w, h = ln["bbox_mm"]
        best = None
        for p in paras:
            px, py, pw, ph = p["bbox_mm"]
            last = p["lines"][-1]["bbox_mm"]
            gap = y - (last[1] + last[3])
            pdf = ln["source"] == "pdf"
            same_size = (abs(p["size_pt"] - ln["size_pt"]) < 0.6 if pdf else
                         abs(p["size_pt"] - ln["size_pt"]) < 0.4 * max(p["size_pt"], ln["size_pt"]))
            if (abs(px - x) < (0.8 if pdf else 1.2) and same_size and -0.5 < gap < (0.05 if pdf else 0.35) * h
                    and p["bold"] == ln["bold"]):
                best = p
                break
        if best:
            best["lines"].append(ln)
            best["bbox_mm"] = r2(bbox_union(best["bbox_mm"], ln["bbox_mm"]))
            best["text"] = best["text"] + " " + ln["text"]
            best["confidence"] = min(best["confidence"], ln["confidence"])
        else:
            paras.append({"text": ln["text"], "bbox_mm": ln["bbox_mm"], "size_pt": ln["size_pt"], "bold": ln["bold"],
                          "confidence": ln["confidence"], "source": ln["source"], "lines": [ln]})
    for i, p in enumerate(paras):
        p["block_id"] = f"B{i:02d}"
        # hyphen-free join; keep line breaks for addresses
        p["text_lines"] = [ln["text"] for ln in p["lines"]]
        del p["lines"]
    return paras


# ---------------------------------------------------------------- 3. barcodes
def read_barcodes(gray: np.ndarray) -> list[dict]:
    from pylibdmtx.pylibdmtx import decode as dm_decode

    h = gray.shape[0]
    out = []
    pil = Image.fromarray(gray)
    try:
        res = dm_decode(pil, timeout=3000, max_count=1)
    except Exception:  # noqa: BLE001
        res = []
    for r in res:
        raw = r.data.decode("latin-1")
        rect = r.rect
        top_px = h - rect.top - rect.height  # pylibdmtx measures 'top' from the bottom edge
        out.append({"symbology": "datamatrix", "raw": raw, "ais": gs1.parse_element_string(raw),
                    "bbox_mm": r2([rect.left / PX_MM, top_px / PX_MM, rect.width / PX_MM, rect.height / PX_MM]),
                    "confidence": 1.0})
    try:
        from pyzbar.pyzbar import decode as zb_decode

        for r in zb_decode(pil):
            raw = r.data.decode("latin-1")
            out.append({"symbology": r.type.lower(), "raw": raw, "ais": gs1.parse_element_string(raw),
                        "bbox_mm": r2([r.rect.left / PX_MM, r.rect.top / PX_MM, r.rect.width / PX_MM,
                                       r.rect.height / PX_MM]), "confidence": 1.0})
    except Exception:  # noqa: BLE001
        pass
    return out


# ---------------------------------------------------------------- 4. symbols
@lru_cache(maxsize=1)
def glyph_library() -> dict:
    lib = {}
    for sid, row in M.symbols().items():
        img = cv2.imread(str(SYMBOL_DIR / row["glyph_file"]), cv2.IMREAD_GRAYSCALE)
        if img is not None:
            lib[sid] = {"img": img, "row": row}
    return lib


def _ncc_same_size(a: np.ndarray, b: np.ndarray) -> float:
    a = a.astype(np.float32)
    b = b.astype(np.float32)
    a -= a.mean()
    b -= b.mean()
    den = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / den) if den > 0 else 0.0


def classify_crop(crop: np.ndarray) -> tuple[str | None, float]:
    best, best_s = None, -1.0
    ch, cw = crop.shape
    if ch < 4 or cw < 4:
        return None, 0.0
    for sid, g in glyph_library().items():
        gh, gw = g["img"].shape
        if abs((gw / gh) - (cw / ch)) / (gw / gh) > 0.25:
            continue
        tpl = cv2.resize(g["img"], (cw, ch), interpolation=cv2.INTER_AREA)
        s = _ncc_same_size(crop, tpl)
        if s > best_s:
            best, best_s = sid, s
    return (best, best_s) if best_s >= CLASSIFY_THRESHOLD else (None, max(best_s, 0.0))


def symbols_from_pdf(page, gray: np.ndarray) -> list[dict]:
    out = []
    for info in page.get_image_info():
        x0, y0, x1, y1 = info["bbox"]
        bb = [x0 * PT_TO_MM, y0 * PT_TO_MM, (x1 - x0) * PT_TO_MM, (y1 - y0) * PT_TO_MM]
        px = [int(round(v * PX_MM)) for v in bb]
        crop = gray[max(px[1], 0):px[1] + px[3], max(px[0], 0):px[0] + px[2]]
        sid, score = classify_crop(crop)
        out.append(_symbol_entry(sid, score, bb, "pdf_image"))
    return out


def symbols_from_raster(gray: np.ndarray, scale_factor: float = 0.5) -> list[dict]:
    """Multi-scale template matching on a downscaled raster, then NMS across all glyphs."""
    small = cv2.resize(gray, None, fx=scale_factor, fy=scale_factor, interpolation=cv2.INTER_AREA)
    cands = []
    for sid, g in glyph_library().items():
        for s in np.arange(0.5, 1.55, 0.1):
            tpl = cv2.resize(g["img"], None, fx=s * scale_factor, fy=s * scale_factor, interpolation=cv2.INTER_AREA)
            th, tw = tpl.shape
            if th < 6 or tw < 6 or th >= small.shape[0] or tw >= small.shape[1]:
                continue
            res = cv2.matchTemplate(small, tpl, cv2.TM_CCOEFF_NORMED)
            ys, xs = np.where(res >= SYMBOL_THRESHOLD)
            for y, x in zip(ys, xs):
                cands.append((float(res[y, x]), sid, [x / scale_factor / PX_MM, y / scale_factor / PX_MM,
                                                      tw / scale_factor / PX_MM, th / scale_factor / PX_MM]))
    cands.sort(key=lambda c: -c[0])
    kept = []
    for score, sid, bb in cands:
        if all(iou(bb, k[2]) < 0.3 and overlap_area(bb, k[2]) < 0.5 * min(bb[2] * bb[3], k[2][2] * k[2][3])
               for k in kept):
            kept.append((score, sid, bb))
    return [_symbol_entry(sid, score, bb, "template_match") for score, sid, bb in kept]


def _symbol_entry(sid, score, bb, method):
    row = M.symbols().get(sid) if sid else None
    return {"symbol_id": sid, "concept": row["concept"] if row else None,
            "library_version": row["library_version"] if row else None, "status": row["status"] if row else None,
            "bbox_mm": r2(bb), "score": round(float(score), 3), "method": method,
            "uncertain": sid is None or score < 0.7}


# ---------------------------------------------------------------- master text matching
@lru_cache(maxsize=1)
def _master_index():
    return [(tid, lg, row["text"]) for (tid, lg), row in M.master_texts().items()]


def match_master_text(text: str, language: str | None = None) -> dict | None:
    best = None
    for tid, lg, mt in _master_index():
        if language and lg != language:
            continue
        sc = fuzz.ratio(text, mt)
        if best is None or sc > best["score"]:
            best = {"text_id": tid, "language": lg, "score": round(sc, 1), "approved_text": mt}
    if best and best["score"] >= TEXT_PROBABLE_THRESHOLD:
        best["exact"] = text.strip() == best["approved_text"].strip()
        best["match"] = "exact" if best["exact"] else ("close" if best["score"] >= TEXT_MATCH_THRESHOLD else
                                                           "probable")
        return best
    return None


# ---------------------------------------------------------------- 5 + 7.2 normalise
def _right_of(sym_bb, paras, max_dx=14.0):
    sx, sy, sw, sh = sym_bb
    cands = []
    for p in paras:
        x, y, w, h = p["bbox_mm"]
        first_line_cy = y + min(h, p["size_pt"] * PT_TO_MM * 1.2) / 2
        if sx + sw - 1 <= x <= sx + sw + max_dx and sy - 1.5 <= first_line_cy <= sy + sh + 1.0:
            cands.append((x - (sx + sw), p))
    return min(cands, key=lambda c: c[0])[1] if cands else None


def normalise(model: dict) -> dict:
    paras = model["blocks"]
    elements: dict[str, dict] = {}
    used: set[str] = set()

    def put(name, value, bbox, conf, source, **extra):
        el = {"value": value, "bbox_mm": r2(bbox), "confidence": round(conf, 3), "source": source,
              "uncertain": conf < UNCERTAIN_CONFIDENCE}
        el.update(extra)
        if name in elements:  # keep a list for repeated elements
            elements.setdefault(name + "#all", [elements[name]]).append(el)
        else:
            elements[name] = el

    # symbols -> symbol elements + adjacent text
    adj = {"SYM-MFR": "manufacturer_name_address", "SYM-EXP": "expiry_date", "SYM-EXP-OLD": "expiry_date",
           "SYM-LOT": "lot", "SYM-REF": "model", "SYM-MFGDATE": "mfg_date", "SYM-ECREP": "authorised_rep",
           "SYM-IMPORTER": "importer", "SYM-CE": "notified_body_number"}
    for s in model["symbols"]:
        if not s["symbol_id"]:
            continue
        name = SYMBOL_ELEMENT[s["symbol_id"]]
        put(name, s["symbol_id"], s["bbox_mm"], s["score"], "symbol", symbol_status=s["status"])
        if s["symbol_id"] in adj:
            p = _right_of(s["bbox_mm"], [p for p in paras if p["block_id"] not in used])
            if p:
                used.add(p["block_id"])
                val = "\n".join(p["text_lines"]) if adj[s["symbol_id"]] in (
                    "manufacturer_name_address", "authorised_rep", "importer") else p["text"]
                put(adj[s["symbol_id"]], val, p["bbox_mm"], p["confidence"], p["source"], block_id=p["block_id"])

    # language panel headers
    headers = [p for p in paras if p["text"].strip().upper() in LANG_CODES and len(p["text"].strip()) == 2]
    headers.sort(key=lambda p: p["bbox_mm"][0])
    panels = []
    for i, h in enumerate(headers):
        used.add(h["block_id"])
        x0 = h["bbox_mm"][0] - 0.5
        x1 = headers[i + 1]["bbox_mm"][0] - 0.5 if i + 1 < len(headers) else 1e9
        panels.append({"language": LANG_CODES[h["text"].strip().upper()], "header_bbox": h["bbox_mm"], "x0": x0,
                       "x1": x1, "y0": h["bbox_mm"][1], "blocks": []})

    # pattern-based elements
    for p in paras:
        if p["block_id"] in used:
            continue
        t = p["text"].strip()
        if re.search(r"\(01\)\d", t):
            put("udi_hri", t.replace(" ", ""), p["bbox_mm"], p["confidence"], p["source"])
            used.add(p["block_id"])
        elif re.search(r"\bRev\.?\s*R[0-9O]\d", t):
            put("label_revision", t, p["bbox_mm"], p["confidence"], p["source"],
                revision=re.search(r"Rev\.?\s*(R[0-9O]\d)", t).group(1).replace("O", "0"))
            used.add(p["block_id"])
        elif re.match(r"^QTY\s*\d+", t):
            put("quantity", t, p["bbox_mm"], p["confidence"], p["source"])
            used.add(p["block_id"])
        elif "Ø" in t or re.match(r"^\S?\s*\d+[.,]\d\s*mm", t):
            put("device_size", t, p["bbox_mm"], p["confidence"], p["source"])
            used.add(p["block_id"])
        elif re.fullmatch(r"Rx only|Caution: Federal law.*", t):
            put("rx_statement", t, p["bbox_mm"], p["confidence"], p["source"])
            used.add(p["block_id"])

    # fallbacks when a symbol is missing: dates / lot by pattern
    if "expiry_date" not in elements:
        dates = [p for p in paras if p["block_id"] not in used and DATE_RE.match(p["text"])]
        if dates:
            p = dates[0]
            used.add(p["block_id"])
            put("expiry_date", p["text"], p["bbox_mm"], min(p["confidence"], 0.65), p["source"], fallback=True)

    # device name = largest bold text not yet used
    free = [p for p in paras if p["block_id"] not in used]
    if free:
        p = max(free, key=lambda q: q["size_pt"])
        if p["size_pt"] >= 10:
            put("device_name", p["text"], p["bbox_mm"], p["confidence"], p["source"])
            used.add(p["block_id"])

    # remaining paragraphs: assign to panels, detect language, match master texts
    texts = []
    for p in paras:
        if p["block_id"] in used:
            continue
        cx = p["bbox_mm"][0]
        panel = next((pn for pn in panels if pn["x0"] <= cx < pn["x1"] and p["bbox_mm"][1] >= pn["y0"]), None)
        lang_det, lconf = detect_language(p["text"])
        lang = panel["language"] if panel else lang_det
        m = match_master_text(p["text"], lang) or match_master_text(p["text"])
        if m and not panel:
            lang = m["language"]
        entry = {"block_id": p["block_id"], "text": p["text"], "bbox_mm": p["bbox_mm"], "language": lang,
                 "language_detected": lang_det, "language_confidence": round(lconf, 2), "panel": bool(panel),
                 "master_match": m, "confidence": p["confidence"], "source": p["source"]}
        texts.append(entry)
        if panel:
            panel["blocks"].append(p["block_id"])
        if m:
            fam = re.match(r"(MT-[A-Z]+)", m["text_id"]).group(1)
            name = TEXT_ID_ELEMENT.get(fam)
            if name:
                key = name if name in ("device_description", "rx_statement") else f"{name}.{lang}"
                put(key, p["text"], p["bbox_mm"], p["confidence"], p["source"], text_id=m["text_id"], language=lang,
                    match=m["match"], match_score=m["score"], block_id=p["block_id"])

    # a language counts as present if it has a populated panel or at least one approved text matched in it
    langs_present = sorted({pn["language"] for pn in panels if pn["blocks"]} |
                           {t["language"] for t in texts if t["language"] and t["master_match"]
                            and t["master_match"]["text_id"] not in ("MT-DESC-01", "MT-RX-01")})
    model["elements"] = elements
    model["text_blocks"] = texts
    model["language_panels"] = [{k: v for k, v in pn.items() if k not in ("x0", "x1", "y0")} for pn in panels]
    model["languages_present"] = langs_present
    return model


# ---------------------------------------------------------------- entry point
def extract(path: str | Path, force_ocr: bool = False) -> dict:
    """pdf_or_image -> LabelModel"""
    path = Path(path)
    if path.suffix.lower() == ".pdf" and not force_ocr:
        import pymupdf

        doc = pymupdf.open(str(path))
        page = doc[0]
        pix = page.get_pixmap(dpi=DPI, colorspace=pymupdf.csGRAY)
        gray = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width).copy()
        lines = pdf_lines(page)
        symbols = symbols_from_pdf(page, gray)
        page_mm = [round(page.rect.width * PT_TO_MM, 2), round(page.rect.height * PT_TO_MM, 2)]
        source = "pdf"
        doc.close()
    else:
        if path.suffix.lower() == ".pdf":
            import pymupdf

            doc = pymupdf.open(str(path))
            pix = doc[0].get_pixmap(dpi=DPI, colorspace=pymupdf.csGRAY)
            gray = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width).copy()
            doc.close()
        else:
            gray = np.array(Image.open(path).convert("L"))
        lines = ocr_lines(gray)
        symbols = symbols_from_raster(gray)
        page_mm = [round(gray.shape[1] / PX_MM, 2), round(gray.shape[0] / PX_MM, 2)]
        source = "image"
    barcodes = read_barcodes(gray)
    # do not let OCR text that sits on top of a symbol or barcode pollute text blocks
    if source == "image":
        occupied = [s["bbox_mm"] for s in symbols if s["symbol_id"]] + [b["bbox_mm"] for b in barcodes]
        lines = [ln for ln in lines if all(overlap_area(ln["bbox_mm"], o) < 0.5 * ln["bbox_mm"][2] * ln["bbox_mm"][3]
                                           for o in occupied)]
    model = {"source": source, "file": path.name, "page_mm": page_mm, "lines": lines,
             "blocks": group_paragraphs(lines), "barcodes": barcodes, "symbols": symbols}
    return normalise(model)
