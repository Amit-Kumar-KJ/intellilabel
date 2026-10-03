"""`make data`: rebuild master files, clean labels, defective labels, revision pairs, translation set and all
truth files from ONE seed (Phase 3 + Phase 4)."""
from __future__ import annotations

import argparse
import copy
import csv
import json
import random
import shutil
import time

import numpy as np
from PIL import Image, ImageFilter

from core import master as M
from core.config import DEFECT_DIR, GEN_DIR, LABEL_DIR, PAIRS_DIR, SEED, SYMBOL_DIR
from generator import glyphs
from generator.defect_injector import DEFECTS, eligible, inject
from generator.label_generator import build_spec, glyph_size_mm, production_data, render
from generator.master_build import build_packaging
from generator.translation_set import build_translation_set

LEVELS = ["pouch", "carton", "shipper"]
DEFECTS_PER_TYPE = 9
CLEAN_RUNS = 4  # production runs (lots) per base label -> 72 clean labels
CLEAN_HOLDOUT = 30  # untouched clean labels for false-positive measurement


def base_matrix():
    return [(sku, mkt, lvl) for sku in sorted(M.skus()) for mkt in sorted(M.markets()) for lvl in LEVELS
            if lvl in M.markets()[mkt]["packaging_levels"]]


def variant_explosion() -> dict:
    """Full theoretical variant matrix incl. planned markets, for the deck."""
    all_mk = M.markets(active_only=False)
    n_sku = len(M.skus())
    rows = []
    total = 0
    for code, mk in all_mk.items():
        n = n_sku * len(mk["packaging_levels"])
        rows.append({"market": code, "languages": len(mk["languages"]), "label_variants": n,
                     "language_panels": n * len(mk["languages"])})
        total += n
    return {"skus": n_sku, "markets": len(all_mk), "packaging_levels": 3, "label_variants_per_revision": total,
            "language_panels_per_revision": sum(r["language_panels"] for r in rows), "by_market": rows,
            "note": "A single attribute change (e.g. shelf life) touches every variant that prints an expiry date."}


def build_clean(seed: int):
    clean = []
    for sku, mkt, lvl in base_matrix():
        # approved base label (the 'released' R02 artwork used by the workflow)
        spec = build_spec(sku, mkt, lvl, seed=seed)
        render(spec, LABEL_DIR / spec["label_id"])
        for run in range(CLEAN_RUNS):
            prod = production_data(f"{sku}|{mkt}|{lvl}|run{run}", seed)
            lid = f"{spec['label_id']}-p{run}"
            s = build_spec(sku, mkt, lvl, production=prod, label_id=lid, seed=seed)
            clean.append(s)
    rng = random.Random(seed)
    rng.shuffle(clean)
    for s in clean:
        render(s, GEN_DIR / "clean" / s["label_id"])
    holdout = sorted(s["label_id"] for s in clean[:CLEAN_HOLDOUT])
    return clean, holdout


def build_defective(clean, holdout, seed: int):
    rng = random.Random(seed + 1)
    pool = [s for s in clean if s["label_id"] not in holdout]
    truth = []
    for did in DEFECTS:
        cands = [s for s in pool if eligible(did, s)]
        rng.shuffle(cands)
        # vary SKU / market / level: round-robin over distinct combos first
        seen, picked = set(), []
        for s in cands:
            key = (s["sku_id"], s["market"], s["packaging_level"])
            if key not in seen:
                seen.add(key)
                picked.append(s)
        for s in cands:
            if len(picked) >= DEFECTS_PER_TYPE:
                break
            if s not in picked:
                picked.append(s)
        for i, base in enumerate(picked[:DEFECTS_PER_TYPE]):
            spec, items = inject(base, did, rng)
            spec["label_id"] = f"{base['label_id']}-{did.lower()}-{i:02d}"
            spec["base_label_id"] = base["label_id"]
            render(spec, DEFECT_DIR / spec["label_id"])
            truth.append({"label_id": spec["label_id"], "base_label_id": base["label_id"], "defects": items})
    return truth


def build_pairs(seed: int):
    """Phase 4.6: 10 approved/revised pairs with 1-4 known edits + 3 noise-only pairs."""
    rng = random.Random(seed + 2)
    combos = base_matrix()
    rng.shuffle(combos)
    truth = []
    edit_kinds = ["text_change", "barcode_change", "symbol_moved", "element_added"]
    for i, (sku, mkt, lvl) in enumerate(combos[:13]):
        pid = f"PAIR-{i:02d}"
        approved = build_spec(sku, mkt, lvl, seed=seed)
        rev = copy.deepcopy(approved)
        edits = []
        noise = i >= 10
        if not noise:
            kinds = rng.sample(edit_kinds, rng.randint(1, 4))
            for k in kinds:
                if k == "text_change":
                    e = [x for x in rev["elements"] if x["type"] in ("text_block", "text") and x["element"] in (
                        "storage_statement", "device_description", "single_use_text", "damaged_package_warning",
                        "sterile_indication")]
                    e = rng.choice(e)
                    e["value"] = (e["value"] or "") + " Protect from light."
                    edits.append({"type": "text_change", "element": e["element_id"], "bbox_mm": e["bbox_mm"]})
                elif k == "barcode_change":
                    from core import gs1

                    hr = [x for x in rev["elements"] if x["element"] == "udi_hri"][0]
                    bc = [x for x in rev["elements"] if x["element"] == "udi_aidc"][0]
                    lt = [x for x in rev["elements"] if x["element"] == "lot"][0]
                    ais = gs1.parse_hri(hr["value"])
                    new_lot = f"B{rng.randint(10000, 99999)}"
                    hr["value"] = gs1.build_hri(ais["01"], ais["17"], new_lot)
                    bc["value"] = gs1.build_element_string(ais["01"], ais["17"], new_lot)
                    lt["value"] = new_lot
                    edits.append({"type": "barcode_change", "element": "udi_aidc", "bbox_mm": bc["bbox_mm"]})
                    edits.append({"type": "text_change", "element": "lot", "bbox_mm": lt["bbox_mm"]})
                    edits.append({"type": "text_change", "element": "udi_hri", "bbox_mm": hr["bbox_mm"]})
                elif k == "symbol_moved":
                    syms = [x for x in rev["elements"] if x["type"] == "symbol" and x["element"] in (
                        "single_use_indication", "ifu_indication", "mr_marking", "damaged_package_symbol",
                        "sterilization_symbol")]
                    if not syms:
                        continue
                    e = rng.choice(syms)
                    e["bbox_mm"] = [round(e["bbox_mm"][0] + 3.0, 2), e["bbox_mm"][1], *e["bbox_mm"][2:]]
                    edits.append({"type": "layout_move", "element": e["element"], "bbox_mm": e["bbox_mm"]})
                elif k == "element_added":
                    srow = M.symbols()["SYM-MD"]
                    w, h = glyph_size_mm(srow["glyph_file"])
                    x0 = 72 if lvl != "pouch" else 46
                    y0 = 52 if lvl == "carton" else (36 if lvl == "pouch" else 64)
                    if lvl == "shipper":
                        x0 = 60
                    rev["elements"].append({"element_id": "md_symbol", "element": "md_symbol", "type": "symbol",
                                            "value": "SYM-MD", "symbol_id": "SYM-MD", "glyph_file": srow["glyph_file"],
                                            "bbox_mm": [x0, y0, w, h], "zone": "symbols",
                                            "binding": {"type": "symbol", "ref": "symbol:SYM-MD", "deps": []}})
                    edits.append({"type": "element_added", "element": "md_symbol", "bbox_mm": [x0, y0, w, h]})
        rev["label_id"] = approved["label_id"] + "-rev"
        d_app = PAIRS_DIR / pid / "approved"
        d_rev = PAIRS_DIR / pid / "revised"
        render(approved, d_app)
        render(rev, d_rev)
        if noise:
            # rendering noise only: identical PDF content, PNG shifted 1 px or slightly blurred
            shutil.copy(d_app / "label.pdf", d_rev / "label.pdf")
            im = Image.open(d_app / "label.png")
            if i % 2 == 0:
                arr = np.array(im)
                arr = np.roll(arr, 1, axis=1)
                Image.fromarray(arr).save(d_rev / "label.png")
            else:
                im.filter(ImageFilter.GaussianBlur(0.6)).save(d_rev / "label.png")
        truth.append({"pair_id": pid, "approved": str(d_app.relative_to(GEN_DIR)), "revised":
                      str(d_rev.relative_to(GEN_DIR)), "noise_only": noise, "edits": edits})
    return truth


def main(seed: int = SEED):
    t0 = time.time()
    for d in ("labels", "clean", "defective", "pairs", "drafts", "reports"):
        shutil.rmtree(GEN_DIR / d, ignore_errors=True)
        (GEN_DIR / d).mkdir(parents=True, exist_ok=True)
    if not (SYMBOL_DIR / "mfr_v2.png").exists():
        glyphs.build_glyphs()
    build_packaging()
    M.clear_caches()
    clean, holdout = build_clean(seed)
    print(f"clean labels: {len(clean)} (+{len(base_matrix())} approved base labels)")
    gt = build_defective(clean, holdout, seed)
    print(f"defective labels: {len(gt)}")
    (GEN_DIR / "ground_truth.json").write_text(json.dumps(gt, indent=1), encoding="utf-8")
    (GEN_DIR / "clean_set.json").write_text(json.dumps({"holdout_clean": holdout, "all_clean": sorted(
        s["label_id"] for s in clean)}, indent=1), encoding="utf-8")
    pairs = build_pairs(seed)
    (GEN_DIR / "diff_truth.json").write_text(json.dumps(pairs, indent=1), encoding="utf-8")
    print(f"revision pairs: {len(pairs)}")
    rows = build_translation_set(seed)
    with open(GEN_DIR / "translation_truth.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"translation cases: {len(rows)}")
    (GEN_DIR / "variant_matrix.json").write_text(json.dumps(variant_explosion(), indent=1), encoding="utf-8")
    print(f"done in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=SEED)
    main(ap.parse_args().seed)
