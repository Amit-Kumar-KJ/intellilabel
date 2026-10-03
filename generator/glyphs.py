"""Draws our OWN simplified symbol glyphs (Phase 2.3).

ISO 15223-1 artwork is copyrighted. These glyphs only *represent* each concept so the
prototype can place and detect symbols; production would use the licensed library.
Each glyph is saved as PNG at 300 dpi at its nominal size.
"""
from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

from core.config import ASSETS, DPI, SYMBOL_DIR

SS = 4  # supersampling factor
PX_PER_MM = DPI / 25.4
FONT = str(ASSETS / "fonts" / "DejaVuSans-Bold.ttf")

# glyph_file -> (width_mm, height_mm)
SIZES = {
    "mfr_v2.png": (6, 6), "mfgdate_v2.png": (6, 6), "exp_v2.png": (6, 6), "exp_v1.png": (6, 6),
    "lot_v2.png": (9, 6), "ref_v2.png": (9, 6), "ecrep_v2.png": (13, 6), "importer_v2.png": (7, 6),
    "ste_eo_v2.png": (16, 6), "ste_eo_v1.png": (8, 8), "damaged_v2.png": (6, 6), "noreuse_v2.png": (6, 6),
    "ifu_v2.png": (6, 6), "md_v2.png": (8, 6), "udi_v2.png": (9, 6), "mrcond_v2.png": (7, 6),
    "ce_v2.png": (8, 6),
}


def _canvas(w_mm, h_mm):
    w, h = int(round(w_mm * PX_PER_MM * SS)), int(round(h_mm * PX_PER_MM * SS))
    img = Image.new("L", (w, h), 255)
    return img, ImageDraw.Draw(img), w, h


def _font(size_px):
    return ImageFont.truetype(FONT, int(size_px))


def _text_center(d, box, text, size_px):
    x0, y0, x1, y1 = box
    while True:  # shrink until the text fits 82% of the box width
        f = _font(size_px)
        bb = d.textbbox((0, 0), text, font=f)
        if bb[2] - bb[0] <= 0.82 * (x1 - x0) or size_px < 6:
            break
        size_px *= 0.92
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    d.text(((x0 + x1 - tw) / 2 - bb[0], (y0 + y1 - th) / 2 - bb[1]), text, fill=0, font=f)


def _boxed_text(text, w_mm, h_mm, double=False):
    img, d, w, h = _canvas(w_mm, h_mm)
    lw = max(2, int(0.35 * PX_PER_MM * SS))
    d.rectangle([lw, lw, w - lw, h - lw], outline=0, width=lw)
    if double:
        m = lw * 3
        d.line([(w * 0.55, m), (w * 0.55, h - m)], fill=0, width=lw)
    _text_center(d, (0, 0, w, h), text, h * 0.5)
    return img


def factory(filled=True):
    img, d, w, h = _canvas(6, 6)
    lw = int(0.4 * PX_PER_MM * SS)
    pts = [(w * .08, h * .92), (w * .08, h * .45), (w * .35, h * .25), (w * .35, h * .45), (w * .62, h * .25),
           (w * .62, h * .45), (w * .75, h * .45), (w * .75, h * .08), (w * .92, h * .08), (w * .92, h * .92)]
    if filled:
        d.polygon(pts, fill=0)
    else:
        d.line(pts + [pts[0]], fill=0, width=lw)
    return img


def hourglass(v1=False):
    img, d, w, h = _canvas(6, 6)
    lw = int(0.45 * PX_PER_MM * SS)
    if v1:  # superseded: outlined hourglass with frame bars + sand line
        d.line([(w * .15, h * .08), (w * .85, h * .08)], fill=0, width=lw)
        d.line([(w * .15, h * .92), (w * .85, h * .92)], fill=0, width=lw)
        d.line([(w * .25, h * .1), (w * .75, h * .9)], fill=0, width=lw)
        d.line([(w * .75, h * .1), (w * .25, h * .9)], fill=0, width=lw)
        d.line([(w * .4, h * .75), (w * .6, h * .75)], fill=0, width=lw)
        return img
    d.polygon([(w * .2, h * .05), (w * .8, h * .05), (w * .52, h * .5), (w * .8, h * .95),
               (w * .2, h * .95), (w * .48, h * .5)], fill=0)
    return img


def damaged():
    img, d, w, h = _canvas(6, 6)
    lw = int(0.4 * PX_PER_MM * SS)
    d.rectangle([w * .15, h * .3, w * .85, h * .8], outline=0, width=lw)
    d.line([(w * .15, h * .3), (w * .5, h * .12), (w * .85, h * .3)], fill=0, width=lw)
    d.ellipse([lw, lw, w - lw, h - lw], outline=0, width=lw)
    d.line([(w * .15, h * .15), (w * .85, h * .85)], fill=0, width=lw)
    return img


def noreuse():
    img, d, w, h = _canvas(6, 6)
    lw = int(0.45 * PX_PER_MM * SS)
    d.ellipse([lw, lw, w - lw, h - lw], outline=0, width=lw)
    _text_center(d, (0, 0, w, h), "2", h * .62)
    d.line([(w * .15, h * .15), (w * .85, h * .85)], fill=0, width=lw)
    return img


def ifu():
    img, d, w, h = _canvas(6, 6)
    lw = int(0.4 * PX_PER_MM * SS)
    d.polygon([(w * .05, h * .2), (w * .5, h * .3), (w * .95, h * .2), (w * .95, h * .9), (w * .5, h * .98),
               (w * .05, h * .9)], outline=0, width=lw)
    d.line([(w * .5, h * .3), (w * .5, h * .98)], fill=0, width=lw)
    _text_center(d, (w * .55, h * .3, w * .95, h * .9), "i", h * .5)
    return img


def importer():
    img, d, w, h = _canvas(7, 6)
    lw = int(0.4 * PX_PER_MM * SS)
    d.rectangle([w * .3, h * .2, w * .95, h * .85], outline=0, width=lw)
    d.polygon([(w * .02, h * .52), (w * .3, h * .3), (w * .3, h * .74)], fill=0)
    d.line([(w * .3, h * .52), (w * .6, h * .52)], fill=0, width=lw)
    return img


def mrcond():
    img, d, w, h = _canvas(7, 6)
    lw = int(0.5 * PX_PER_MM * SS)
    d.polygon([(w * .5, h * .03), (w * .97, h * .95), (w * .03, h * .95)], outline=0, width=lw)
    _text_center(d, (w * .2, h * .4, w * .8, h * .92), "MR", h * .33)
    return img


def ce():
    img, d, w, h = _canvas(8, 6)
    _text_center(d, (0, 0, w, h), "CE", h * .85)
    return img


def ste_eo_v1():
    img, d, w, h = _canvas(8, 8)
    lw = int(0.35 * PX_PER_MM * SS)
    d.rectangle([lw, lw, w - lw, h - lw], outline=0, width=lw)
    _text_center(d, (0, 0, w, h * .55), "STERILE", h * .17)
    _text_center(d, (0, h * .45, w, h), "EO", h * .35)
    return img


def build_glyphs():
    SYMBOL_DIR.mkdir(parents=True, exist_ok=True)
    glyphs = {
        "mfr_v2.png": factory(True), "mfgdate_v2.png": factory(False), "exp_v2.png": hourglass(False),
        "exp_v1.png": hourglass(True), "lot_v2.png": _boxed_text("LOT", 9, 6), "ref_v2.png": _boxed_text("REF", 9, 6),
        "ecrep_v2.png": _boxed_text("EC REP", 13, 6), "importer_v2.png": importer(),
        "ste_eo_v2.png": _boxed_text("STERILE EO", 16, 6), "ste_eo_v1.png": ste_eo_v1(),
        "damaged_v2.png": damaged(), "noreuse_v2.png": noreuse(), "ifu_v2.png": ifu(),
        "md_v2.png": _boxed_text("MD", 8, 6), "udi_v2.png": _boxed_text("UDI", 9, 6), "mrcond_v2.png": mrcond(),
        "ce_v2.png": ce(),
    }
    for name, img in glyphs.items():
        w_mm, h_mm = SIZES[name]
        out = img.resize((int(round(w_mm * PX_PER_MM)), int(round(h_mm * PX_PER_MM))), Image.LANCZOS)
        out.save(SYMBOL_DIR / name, dpi=(DPI, DPI))
    return list(glyphs)


if __name__ == "__main__":
    print(build_glyphs())
