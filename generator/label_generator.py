"""Phase 4: template-driven label generator (also the authoring engine for drafts in Phase 6).

build_spec(...)  -> label spec (dict): every element with value, bbox (mm, top-left origin), binding.
render(spec, dir) -> label.pdf (real text objects), label.png (300 dpi), label.json (the spec).

Deterministic: the same inputs and seed give byte-identical JSON (and PDFs, via reportlab invariant mode).
"""
from __future__ import annotations

import calendar
import hashlib
import json
import random
from datetime import date
from pathlib import Path

import yaml
from reportlab.graphics import renderPDF
from reportlab.graphics.barcode import createBarcodeDrawing
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from core import gs1
from core import master as M
from core.config import DPI, SEED, SYMBOL_DIR, TEMPLATE_DIR

PT_MM = 25.4 / 72.0
DEFAULT_MFG_DATE = "2026-09-15"

FONT_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"

if "IntelliLabel-DejaVu" not in pdfmetrics.getRegisteredFontNames():
    pdfmetrics.registerFont(
        TTFont("IntelliLabel-DejaVu", str(FONT_DIR / "DejaVuSans.ttf"))
    )
    pdfmetrics.registerFont(
        TTFont("IntelliLabel-DejaVu-Bold", str(FONT_DIR / "DejaVuSans-Bold.ttf"))
    )


# ---------------------------------------------------------------- helpers
def load_templates() -> dict:
    out = {}
    for p in sorted(TEMPLATE_DIR.glob("*.yaml")):
        t = yaml.safe_load(p.read_text(encoding="utf-8"))
        out[t["packaging_level"]] = t
    return out


def add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    y += d.year
    m += 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def format_date(d: date, fmt: str) -> str:
    return (fmt.replace("YYYY", f"{d.year:04d}").replace("MM", f"{d.month:02d}").replace("DD", f"{d.day:02d}"))


def eval_condition(expr: str | None, ctx: dict, active_reqs: set[str]) -> bool:
    """'key=value;key=value' (AND). Special key 'requirement' checks the active requirement set."""
    if not expr or expr.strip() in ("", "all"):
        return True
    for part in expr.split(";"):
        key, _, val = part.partition("=")
        key, val = key.strip(), val.strip()
        if key == "requirement":
            if val not in active_reqs:
                return False
            continue
        actual = ctx.get(key)
        if isinstance(actual, bool):
            if actual != (val.lower() == "true"):
                return False
        elif str(actual) != val:
            return False
    return True


def font_name(bold: bool) -> str:
    return "IntelliLabel-DejaVu-Bold" if bold else "IntelliLabel-DejaVu"


def wrap(text: str, width_mm: float, size_pt: float, bold=False) -> list[str]:
    fn = font_name(bold)
    lines = []
    for para in str(text).split("\n"):
        cur = ""
        for word in para.split(" "):
            trial = f"{cur} {word}".strip()
            if stringWidth(trial, fn, size_pt) * PT_MM <= width_mm or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = word
        lines.append(cur)
    return lines


def leading_mm(size_pt: float) -> float:
    return size_pt * 1.2 * PT_MM


def glyph_size_mm(glyph_file: str) -> tuple[float, float]:
    from PIL import Image

    with Image.open(SYMBOL_DIR / glyph_file) as im:
        w, h = im.size
    return round(w * 25.4 / DPI, 2), round(h * 25.4 / DPI, 2)


def production_data(label_key: str, seed: int = SEED) -> dict:
    rng = random.Random(f"{seed}:{label_key}")
    return {"lot": f"A{rng.randint(10000, 99999)}", "mfg_date": DEFAULT_MFG_DATE}


def label_id_for(sku_id: str, market: str, level: str, revision: str) -> str:
    return f"L-{sku_id.replace('-', '')}-{market}-{level}-{revision}"


# ---------------------------------------------------------------- spec builder
def build_spec(sku_id: str, market: str, level: str, revision: str | None = None, *, attrs: dict | None = None,
               production: dict | None = None, active_reqs: set[str] | None = None, label_id: str | None = None,
               seed: int = SEED, master_text_overrides: dict | None = None) -> dict:
    templates = load_templates()
    tpl = templates[level]
    sku = M.skus()[sku_id]
    prod = M.products()[sku["product_id"]]
    mfr = M.manufacturers()[prod["manufacturer_id"]]
    mkt = M.markets()[market]
    revision = revision or sku["revision"]
    attrs = attrs if attrs is not None else M.current_attributes(sku_id)
    ctx = M.product_context(sku_id, market, attrs)
    active_reqs = active_reqs if active_reqs is not None else {r["requirement_id"] for r in M.requirements()}
    label_id = label_id or label_id_for(sku_id, market, level, revision)
    production = production or production_data(f"{sku_id}|{market}|{level}", seed)
    texts = dict(M.master_texts())
    if master_text_overrides:
        texts.update(master_text_overrides)
    pk = M.packaging()[(sku_id, level)]
    languages = mkt["languages"]

    mfg = date.fromisoformat(production["mfg_date"])
    shelf = int(attrs["shelf_life_months"])
    expiry = add_months(mfg, shelf)
    gtin = pk["gtin14"]
    lot = production["lot"]
    udi_raw = gs1.build_element_string(gtin, expiry.strftime("%y%m%d"), lot)
    udi_hri = gs1.build_hri(gtin, expiry.strftime("%y%m%d"), lot)

    def text_of(text_id, lang):
        row = texts.get((text_id, lang))
        return row["text"] if row else None

    def resolve(bind: dict, lang: str | None = None):
        """-> (value, binding dict with deps for trace)"""
        if "product" in bind:
            f = bind["product"]
            return str(prod[f]), {"type": "product", "ref": f"product:{prod['product_id']}:{f}", "deps": []}
        if "sku" in bind:
            f = bind["sku"]
            return str(sku[f]), {"type": "sku", "ref": f"sku:{sku_id}:{f}", "deps": []}
        if "manufacturer" in bind:
            f = bind["manufacturer"]
            if f == "name_address":
                v = f"{mfr['name']}\n{mfr['address']}"
            elif f == "eu_auth_rep":
                v = f"{mfr['eu_auth_rep_name']}\n{mfr['eu_auth_rep_address']}"
            else:
                v = f"{mfr['eu_importer_name']}\n{mfr['eu_importer_address']}"
            return v, {"type": "manufacturer", "ref": f"manufacturer:{mfr['manufacturer_id']}:{f}", "deps": []}
        if "symbol" in bind:
            return bind["symbol"], {"type": "symbol", "ref": f"symbol:{bind['symbol']}", "deps": []}
        if "master_text" in bind:
            lg = bind.get("language", lang)
            return text_of(bind["master_text"], lg), {"type": "master_text", "ref": f"mt:{bind['master_text']}",
                                                       "deps": [], "language": lg}
        if "attribute_text" in bind:
            key = bind["attribute_text"]
            tid = attrs[key]
            lg = bind.get("language", lang)
            return text_of(tid, lg), {"type": "master_text", "ref": f"mt:{tid}", "language": lg,
                                      "deps": [f"attr:{sku_id}:{key}"]}
        if "production" in bind:
            f = bind["production"]
            v = production[f]
            if f == "mfg_date":
                v = format_date(mfg, mkt["date_format"])
            return v, {"type": "production", "ref": f"production:{f}", "deps": []}
        if "label" in bind:
            v = f"{tpl['template_id']} | {sku_id} {market} {level} | Rev {revision}"
            return v, {"type": "label", "ref": "label:revision", "deps": [f"sku:{sku_id}:revision"]}
        if "derived" in bind:
            d = bind["derived"]
            if d == "sku_size":
                return (f"Ø {sku['diameter_mm']} mm × {sku['length_mm']} mm",
                        {"type": "derived", "ref": "derived:sku_size",
                         "deps": [f"sku:{sku_id}:diameter_mm", f"sku:{sku_id}:length_mm"]})
            if d == "expiry_from_shelf_life":
                return format_date(expiry, mkt["date_format"]), {
                    "type": "derived", "ref": "derived:expiry_from_shelf_life",
                    "deps": [f"attr:{sku_id}:shelf_life_months", "production:mfg_date"]}
            if d in ("gs1_udi_string", "gs1_udi_hri"):
                return (udi_raw if d == "gs1_udi_string" else udi_hri), {
                    "type": "derived", "ref": f"derived:{d}",
                    "deps": [f"packaging:{sku_id}:{level}:gtin14", f"attr:{sku_id}:shelf_life_months",
                             "production:mfg_date", "production:lot"]}
            if d == "shipper_quantity":
                return f"QTY {attrs['units_per_shipper']}", {"type": "derived", "ref": "derived:shipper_quantity",
                                                            "deps": [f"attr:{sku_id}:units_per_shipper"]}
        raise ValueError(f"unknown binding {bind}")

    elements = []
    for zone in tpl["zones"]:
        if zone.get("type") == "language_panels":
            elements += _layout_language_panels(zone, languages, ctx, active_reqs, resolve)
            continue
        for e in zone["elements"]:
            if not eval_condition(e.get("include_if"), ctx, active_reqs):
                continue
            value, binding = resolve(e["bind"])
            el = {"element_id": e["element"], "element": e["element"], "type": e["type"], "value": value,
                  "zone": zone["id"], "binding": binding, "language": binding.get("language")}
            if e["type"] == "symbol":
                srow = M.symbols()[value]
                w, h = glyph_size_mm(srow["glyph_file"])
                el.update(symbol_id=value, glyph_file=srow["glyph_file"], bbox_mm=[e["bbox"][0], e["bbox"][1], w, h])
            else:
                el["bbox_mm"] = list(e["bbox"])
                el["font_pt"] = e.get("font_pt", 7)
                el["bold"] = bool(e.get("bold", False))
            elements.append(el)

    return {
        "label_id": label_id,
        "sku_id": sku_id,
        "product_id": prod["product_id"],
        "market": market,
        "packaging_level": level,
        "template_id": tpl["template_id"],
        "revision": revision,
        "languages": languages if any(e.get("zone") == "languages" for e in elements) else ["en"],
        "page_mm": tpl["page_mm"],
        "gtin14": gtin,
        "production": {"lot": lot, "mfg_date": production["mfg_date"], "expiry_date": expiry.isoformat()},
        "attributes": dict(sorted(attrs.items())),
        "seed": seed,
        "elements": elements,
    }


def _layout_language_panels(zone, languages, ctx, active_reqs, resolve):
    x0, y0, w, h = zone["box"]
    n = len(languages)
    gap = 3.0
    col_w = (w - gap * (n - 1)) / n
    blocks = [b for b in zone["blocks"] if eval_condition(b.get("include_if"), ctx, active_reqs)]
    size = zone.get("font_pt", 5.6)
    # shrink font until the tallest column fits
    while True:
        heights = []
        for lang in languages:
            tot = leading_mm(size + 1) + 0.6
            for b in blocks:
                v, _ = resolve(b["bind"], lang)
                tot += len(wrap(v or "", col_w, size)) * leading_mm(size) + 0.8
            heights.append(tot)
        if max(heights) <= h or size <= 4.0:
            break
        size = round(size - 0.2, 2)
    out = []
    for i, lang in enumerate(languages):
        cx = round(x0 + i * (col_w + gap), 2)
        y = y0
        hh = leading_mm(size + 1)
        out.append({"element_id": f"language_header.{lang}", "element": "language_header", "type": "text",
                    "value": lang.upper(), "zone": "languages", "language": lang, "bbox_mm": [cx, round(y, 2),
                                                                                             10, round(hh, 2)],
                    "font_pt": size + 1, "bold": True, "binding": {"type": "static", "ref": f"language:{lang}",
                                                                   "deps": []}})
        y += hh + 0.6
        for b in blocks:
            v, binding = resolve(b["bind"], lang)
            lines = wrap(v or "", col_w, size)
            bh = len(lines) * leading_mm(size)
            out.append({"element_id": f"{b['element']}.{lang}", "element": b["element"], "type": "text_block",
                        "value": v, "zone": "languages", "language": lang,
                        "bbox_mm": [cx, round(y, 2), round(col_w, 2), round(bh, 2)], "font_pt": size, "bold": False,
                        "binding": binding})
            y += bh + 0.8
    return out


# ---------------------------------------------------------------- renderer
def render(spec: dict, out_dir: Path, png: bool = True) -> dict:
    """Draw the spec. Returns paths. Text is real PDF text; symbols are embedded glyph images."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pw, ph = spec["page_mm"]
    pdf_path = out_dir / "label.pdf"
    c = canvas.Canvas(str(pdf_path), pagesize=(pw * mm, ph * mm), invariant=1)
    c.setTitle(spec["label_id"])
    c.setLineWidth(0.3)
    c.rect(1 * mm, 1 * mm, (pw - 2) * mm, (ph - 2) * mm)  # die-cut outline

    for el in spec["elements"]:
        x, y, w, h = el["bbox_mm"]
        if el["type"] == "symbol":
            img = ImageReader(str(SYMBOL_DIR / el["glyph_file"]))
            c.drawImage(img, x * mm, (ph - y - h) * mm, w * mm, h * mm)
        elif el["type"] == "barcode":
            d = createBarcodeDrawing("ECC200DataMatrix", value=el["value"])
            sc = (w * mm) / d.width
            c.saveState()
            c.translate(x * mm, (ph - y - h) * mm)
            c.scale(sc, sc)
            renderPDF.draw(d, c, 0, 0)
            c.restoreState()
        else:
            size = el.get("font_pt", 7)
            fn = font_name(el.get("bold", False))
            if el["type"] == "text_block":
                lines = wrap(el["value"] or "", w, size, el.get("bold", False))
            else:
                lines = [str(el["value"] or "")]
                while stringWidth(lines[0], fn, size) * PT_MM > w and size > 3:
                    size -= 0.25
            c.setFont(fn, size)
            lead = leading_mm(size)
            for i, line in enumerate(lines):
                base_y = ph - y - (i * lead) - size * 0.85 * PT_MM - 0.1
                c.drawString(x * mm, base_y * mm, line)
    c.showPage()
    c.save()

    (out_dir / "label.json").write_text(json.dumps(spec, indent=1, sort_keys=True, ensure_ascii=False),
                                        encoding="utf-8")
    paths = {"pdf": str(pdf_path), "json": str(out_dir / "label.json")}
    if png:
        paths["png"] = str(rasterize(pdf_path, out_dir / "label.png"))
    return paths


def rasterize(pdf_path: Path, png_path: Path, dpi: int = DPI) -> Path:
    import pymupdf

    doc = pymupdf.open(str(pdf_path))
    pix = doc[0].get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
    pix.save(str(png_path))
    doc.close()
    return png_path


def spec_hash(spec: dict) -> str:
    return hashlib.sha256(json.dumps(spec, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def generate(sku_id, market, level, revision=None, out_root: Path | None = None, **kw) -> tuple[dict, dict]:
    spec = build_spec(sku_id, market, level, revision, **kw)
    from core.config import LABEL_DIR

    paths = render(spec, (out_root or LABEL_DIR) / spec["label_id"])
    return spec, paths


if __name__ == "__main__":
    s, p = generate("CS-100", "EU", "carton")
    print(p)
