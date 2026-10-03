"""Phase 8: artwork diff engine. Says WHAT changed (content level) plus a pixel-level safety net, and flags every
change that no change request explains (unexplained changes block approval).

diff(approved_pdf, revised_pdf, approved_png=None, revised_png=None, explain=None) -> DiffResult
"""
from __future__ import annotations

import difflib
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

from core.config import DPI
from engines.extraction import extract, iou, overlap_area

PX_MM = DPI / 25.4
MOVE_MM = 1.0
RESIZE_FRAC = 0.05
SSIM_THRESHOLD = 0.55
MIN_REGION_MM2 = 1.5


def _named(model) -> dict:
    out = {}
    for k, v in model["elements"].items():
        if "#" in k or not isinstance(v, dict):
            continue
        out[k] = v
    return out


def word_diff(a: str, b: str) -> list[dict]:
    aw, bw = (a or "").split(), (b or "").split()
    ops = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=aw, b=bw).get_opcodes():
        if tag != "equal":
            ops.append({"op": tag, "old": " ".join(aw[i1:i2]), "new": " ".join(bw[j1:j2])})
    return ops


def content_diff(ma: dict, mb: dict) -> list[dict]:
    a, b = _named(ma), _named(mb)
    changes = []
    for name in sorted(set(a) | set(b)):
        ea, eb = a.get(name), b.get(name)
        kind = "symbol" if (ea or eb).get("source") == "symbol" else "text"
        if ea and not eb:
            # a named text whose content changed may no longer match its master text: find it by position
            moved_txt = next((t for t in mb["text_blocks"] if not t["master_match"] and
                              abs(t["bbox_mm"][0] - ea["bbox_mm"][0]) < 1 and abs(t["bbox_mm"][1] - ea["bbox_mm"][1]) < 1),
                             None) if kind == "text" else None
            if moved_txt:
                moved_txt["_claimed"] = True
                changes.append({"type": "text", "element": name, "old": ea["value"], "new": moved_txt["text"],
                                "bbox_old": ea["bbox_mm"], "bbox_new": moved_txt["bbox_mm"], "kind": "text",
                                "word_diff": word_diff(str(ea["value"]), moved_txt["text"])})
                continue
            changes.append({"type": "removed", "element": name, "old": ea["value"], "new": None,
                            "bbox_old": ea["bbox_mm"], "bbox_new": None, "kind": kind})
            continue
        if eb and not ea:
            changes.append({"type": "added", "element": name, "old": None, "new": eb["value"], "bbox_old": None,
                            "bbox_new": eb["bbox_mm"], "kind": kind})
            continue
        if str(ea["value"]).strip() != str(eb["value"]).strip():
            t = "udi_text" if name == "udi_hri" else ("symbol" if kind == "symbol" else "text")
            changes.append({"type": t, "element": name, "old": ea["value"], "new": eb["value"],
                            "bbox_old": ea["bbox_mm"], "bbox_new": eb["bbox_mm"], "kind": kind,
                            "word_diff": word_diff(str(ea["value"]), str(eb["value"])) if kind == "text" else None})
            continue
        (xa, ya, wa, ha), (xb, yb, wb, hb) = ea["bbox_mm"], eb["bbox_mm"]
        moved = max(abs(xa - xb), abs(ya - yb)) > MOVE_MM
        resized = abs(wa - wb) > RESIZE_FRAC * max(wa, 0.1) or abs(ha - hb) > RESIZE_FRAC * max(ha, 0.1)
        if moved or resized:
            changes.append({"type": "layout", "element": name, "old": ea["bbox_mm"], "new": eb["bbox_mm"],
                            "bbox_old": ea["bbox_mm"], "bbox_new": eb["bbox_mm"], "kind": kind,
                            "detail": ("moved" if moved else "") + (" resized" if resized else "")})
    # unnamed text blocks (not matched to any element): match by position
    used_b = set()
    ua = [t for t in ma["text_blocks"] if not t["master_match"]]
    ub = [t for t in mb["text_blocks"] if not t["master_match"] and not t.get("_claimed")]
    for ta in ua:
        best = max(ub, key=lambda tb: iou(ta["bbox_mm"], tb["bbox_mm"]), default=None)
        if best and iou(ta["bbox_mm"], best["bbox_mm"]) > 0.3:
            used_b.add(best["block_id"])
            if ta["text"] != best["text"]:
                changes.append({"type": "text", "element": f"block@{ta['bbox_mm'][0]:.0f},{ta['bbox_mm'][1]:.0f}",
                                "old": ta["text"], "new": best["text"], "bbox_old": ta["bbox_mm"],
                                "bbox_new": best["bbox_mm"], "kind": "text",
                                "word_diff": word_diff(ta["text"], best["text"])})
    # barcodes: field by field
    ba = {k: v for k, v in (ma["barcodes"][0]["ais"] if ma["barcodes"] else {}).items() if not k.startswith("_")}
    bb = {k: v for k, v in (mb["barcodes"][0]["ais"] if mb["barcodes"] else {}).items() if not k.startswith("_")}
    if ba != bb:
        fields = [f"({k}) {ba.get(k)} -> {bb.get(k)}" for k in sorted(set(ba) | set(bb)) if ba.get(k) != bb.get(k)]
        changes.append({"type": "barcode", "element": "udi_aidc", "old": ba, "new": bb,
                        "bbox_old": ma["barcodes"][0]["bbox_mm"] if ma["barcodes"] else None,
                        "bbox_new": mb["barcodes"][0]["bbox_mm"] if mb["barcodes"] else None, "kind": "barcode",
                        "fields": fields})
    return changes


def _load_gray(p) -> np.ndarray:
    return np.array(Image.open(p).convert("L"))


def align(ref: np.ndarray, mov: np.ndarray) -> np.ndarray:
    """ORB + RANSAC homography; ECC (translation) fallback for near-identical images."""
    if ref.shape != mov.shape:
        mov = cv2.resize(mov, (ref.shape[1], ref.shape[0]))
    try:
        warp = np.eye(2, 3, dtype=np.float32)
        small_r = cv2.resize(ref, None, fx=0.5, fy=0.5).astype(np.float32) / 255
        small_m = cv2.resize(mov, None, fx=0.5, fy=0.5).astype(np.float32) / 255
        _, warp = cv2.findTransformECC(small_r, small_m, warp, cv2.MOTION_TRANSLATION,
                                       (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 50, 1e-4))
        warp[:, 2] *= 2
        if np.abs(warp[:, 2]).max() < 40:
            return cv2.warpAffine(mov, warp, (ref.shape[1], ref.shape[0]), flags=cv2.INTER_LINEAR +
                                  cv2.WARP_INVERSE_MAP, borderValue=255)
    except cv2.error:
        pass
    orb = cv2.ORB_create(3000)
    k1, d1 = orb.detectAndCompute(ref, None)
    k2, d2 = orb.detectAndCompute(mov, None)
    if d1 is None or d2 is None:
        return mov
    matches = sorted(cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(d1, d2), key=lambda m: m.distance)[:500]
    if len(matches) < 10:
        return mov
    src = np.float32([k2[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)
    dst = np.float32([k1[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
    H, _ = cv2.findHomography(src, dst, cv2.RANSAC, 3.0)
    if H is None:
        return mov
    return cv2.warpPerspective(mov, H, (ref.shape[1], ref.shape[0]), borderValue=255)


def pixel_regions(png_a, png_b) -> list[list[float]]:
    from skimage.metrics import structural_similarity

    a = _load_gray(png_a)
    b = align(a, _load_gray(png_b))
    f = 0.5  # work at 150 dpi
    sa = cv2.resize(a, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    sb = cv2.resize(b, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    sa = cv2.GaussianBlur(sa, (3, 3), 0)
    sb = cv2.GaussianBlur(sb, (3, 3), 0)
    _, smap = structural_similarity(sa, sb, full=True, data_range=255)
    mask = (smap < SSIM_THRESHOLD).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    regions = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        mm2 = area / (PX_MM * f) ** 2
        if mm2 >= MIN_REGION_MM2:
            regions.append([x / (PX_MM * f), y / (PX_MM * f), w / (PX_MM * f), h / (PX_MM * f)])
    # merge overlapping regions
    merged = []
    for r in regions:
        for m in merged:
            if overlap_area([m[0] - 1, m[1] - 1, m[2] + 2, m[3] + 2], r) > 0:
                x0, y0 = min(m[0], r[0]), min(m[1], r[1])
                x1, y1 = max(m[0] + m[2], r[0] + r[2]), max(m[1] + m[3], r[1] + r[3])
                m[:] = [x0, y0, x1 - x0, y1 - y0]
                break
        else:
            merged.append(list(r))
    return [[round(v, 2) for v in r] for r in merged]


def diff(approved_pdf, revised_pdf, approved_png=None, revised_png=None, explain=None, pixel=True) -> dict:
    """explain(change) -> (explained: bool, reason: str); None means 'no change request context'."""
    ma, mb = extract(approved_pdf), extract(revised_pdf)
    changes = content_diff(ma, mb)
    graphic = []
    if pixel and approved_png and revised_png:
        content_boxes = [c[k] for c in changes for k in ("bbox_old", "bbox_new") if c.get(k)]
        for r in pixel_regions(approved_png, revised_png):
            covered = any(overlap_area([cb[0] - 1, cb[1] - 1, cb[2] + 2, cb[3] + 2], r) > 0.2 * r[2] * r[3]
                          for cb in content_boxes)
            if not covered:
                graphic.append({"type": "graphic", "element": "graphic_region", "old": None, "new": None,
                                "bbox_old": r, "bbox_new": r, "kind": "graphic"})
    changes += graphic
    # reflow: if any language text changed, pure moves inside the language zone are a consequence of it
    lang_text_changed = any(c["type"] == "text" and "." in c["element"] for c in changes)
    for c in changes:
        if explain is None:
            c["explained"], c["explanation"] = None, "no change request context"
        else:
            ok, why = explain(c)
            if not ok and c["type"] == "layout" and lang_text_changed and "." in c["element"]:
                ok, why = True, "reflow caused by a changed text in the same language panel"
            c["explained"], c["explanation"] = ok, why
    summary = {
        "text_changes": sum(c["type"] == "text" for c in changes),
        "udi_changes": sum(c["type"] in ("udi_text",) for c in changes),
        "barcode_changes": sum(c["type"] == "barcode" for c in changes),
        "symbol_changes": sum(c["type"] == "symbol" or (c["type"] in ("added", "removed") and c["kind"] == "symbol")
                              for c in changes),
        "layout_changes": sum(c["type"] == "layout" for c in changes),
        "added": sum(c["type"] == "added" for c in changes), "removed": sum(c["type"] == "removed" for c in changes),
        "graphic_changes": len(graphic),
        "unexplained_changes": sum(c.get("explained") is False for c in changes),
    }
    status = "NO_CHANGE" if not changes else ("UNEXPLAINED_CHANGES" if summary["unexplained_changes"] else
                                              ("CHANGES_EXPLAINED" if explain else "CHANGES"))
    return {"status": status, "summary": summary, "changes": changes}


def overlay(revised_png, result: dict, out_png) -> Path:
    im = Image.open(revised_png).convert("RGB")
    d = ImageDraw.Draw(im)
    colors = {"added": (0, 160, 60), "removed": (210, 30, 30), "layout": (30, 90, 220)}
    for c in result["changes"]:
        bb = c.get("bbox_new") or c.get("bbox_old")
        if not bb:
            continue
        x, y, w, h = [v * PX_MM for v in bb]
        col = colors.get(c["type"], (0, 160, 60) if c.get("explained") is not False else (210, 30, 30))
        width = 4
        if c.get("explained") is False:
            col, width = (220, 0, 0), 12
        d.rectangle([x - 6, y - 6, x + w + 6, y + h + 6], outline=col, width=width)
        if c["type"] == "removed" and c.get("bbox_old"):
            x, y, w, h = [v * PX_MM for v in c["bbox_old"]]
            d.line([x, y, x + w, y + h], fill=(210, 30, 30), width=4)
    im.save(out_png)
    return Path(out_png)


def explainer_for(session, cr, draft_label_id: str):
    """Build explain(change) from the draft's element bindings and the change request."""
    from sqlalchemy import select

    from core.models import LabelElement

    keys = set()
    req_elements = set()
    if cr.source == "product":
        keys = {ch["key"] for ch in cr.payload["changes"]}
    else:
        req_elements = {cr.payload["requirement"]["label_element"]}
    els = {le.element_id: le for le in session.execute(select(LabelElement).where(
        LabelElement.label_id == draft_label_id)).scalars()}
    by_name = {}
    for le in els.values():
        by_name.setdefault(le.element, []).append(le)

    def bound_to_change(le) -> str | None:
        refs = [le.binding_ref] + list(le.deps or [])
        for k in keys:
            for r in refs:
                if r.endswith(f":{k}"):
                    return f"bound to changed attribute '{k}' via {r}"
        return None

    def explain(c):
        name = c["element"]
        cands = []
        if name in els:
            cands = [els[name]]
        elif name in by_name:
            cands = by_name[name]
        elif name == "udi_aidc" or name == "udi_hri":
            cands = by_name.get(name, [])
        for le in cands:
            why = bound_to_change(le)
            if why:
                return True, why
            if le.element in req_elements:
                return True, f"required by {cr.payload['requirement']['requirement_id']}"
        if c["type"] == "added" and name in req_elements:
            return True, f"required by {cr.payload['requirement']['requirement_id']}"
        if c["type"] == "barcode" and any(bound_to_change(le) for le in by_name.get("udi_aidc", [])):
            return True, "UDI derived from a changed attribute"
        if name == "label_revision":
            return True, "new revision for this change request"
        return False, "no change request explains this change"

    return explain
