"""Phase 7.6 / 8.5 / 11 / 13: `make bench` - runs every evaluation and writes eval/results/.

Tier 1 (seen) compliance, clean false-positive rate, confusion matrix, diff engine, translation validator,
ledger tamper detection, risk-weight sensitivity, optional robustness (raster/OCR path) and the AccessGUDID
real-data check-digit test when an extract is present.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import time
from collections import Counter, defaultdict

import numpy as np
from PIL import Image, ImageFilter

from core import master as M
from core.config import EVAL_DIR, GEN_DIR, ROOT
from engines.compliance import validate_file
from engines.extraction import iou

RULE_OF = {"D01": "R01", "D02": "R02", "D03": "R03", "D04": "R05", "D05": "R06", "D06": "R15", "D07": "R09",
           "D08": "R08", "D09": "R14", "D10": "R17", "D11": "R16", "D12": "R18", "D13": "R21", "D14": "R04"}


def _save(name, obj):
    (EVAL_DIR / f"{name}.json").write_text(json.dumps(obj, indent=1, default=str), encoding="utf-8")


def _matches(f, truth) -> bool:
    if f["rule_id"] != truth["expected_rule"]:
        return False
    if f.get("evidence_bbox") and truth.get("bbox_mm") and iou(f["evidence_bbox"], truth["bbox_mm"]) >= 0.3:
        return True
    el = (f.get("element") or "")
    te = truth["element"]
    return bool(el) and (el == te or te.startswith(el) or el.startswith(te.split(".")[0]) or
                         te.split(".")[0] in el) or f.get("evidence_bbox") is None


def tier1(force_ocr=False, subset=None):
    gt = json.loads((GEN_DIR / "ground_truth.json").read_text())
    clean = json.loads((GEN_DIR / "clean_set.json").read_text())["holdout_clean"]
    if subset:
        gt = gt[:subset]
    per = defaultdict(lambda: {"tp": 0, "fn": 0, "localised": 0})
    rule_fired = Counter()
    rule_tp = Counter()
    confusion = defaultdict(Counter)
    t0 = time.time()
    for g in gt:
        lid = g["label_id"]
        spec = json.loads((GEN_DIR / "defective" / lid / "label.json").read_text())
        rep = validate_file(GEN_DIR / "defective" / lid / "label.pdf", spec, reqs=M.requirements(), force_ocr=force_ocr)
        fired = {f["rule_id"] for f in rep["findings"] if f["severity"] in ("critical", "major", "minor")}
        for r in fired:
            rule_fired[r] += 1
        seen_types = set()
        for t in g["defects"]:
            d = t["defect_id"]
            if d in seen_types:  # one label may carry several truth items of the same defect (e.g. D04 'both')
                continue
            seen_types.add(d)
            for r in fired:
                confusion[d][r] += 1
            hit = [f for f in rep["findings"] if f["rule_id"] == t["expected_rule"]]
            if hit:
                per[d]["tp"] += 1
                rule_tp[t["expected_rule"]] += 1
                same = [x for x in g["defects"] if x["defect_id"] == d]
                if any(_matches(f, x) for f in hit for x in same):
                    per[d]["localised"] += 1
            else:
                per[d]["fn"] += 1
    n_def = len(gt)
    clean_fp = 0
    clean_rules = Counter()
    for lid in clean:
        spec = json.loads((GEN_DIR / "clean" / lid / "label.json").read_text())
        rep = validate_file(GEN_DIR / "clean" / lid / "label.pdf", spec, reqs=M.requirements(), force_ocr=force_ocr)
        bad = [f for f in rep["findings"] if f["severity"] in ("critical", "major")]
        if bad:
            clean_fp += 1
        for f in rep["findings"]:
            rule_fired[f["rule_id"]] += 1
            clean_rules[f["rule_id"]] += 1
    rows = []
    for d in sorted(per):
        r = RULE_OF[d]
        tp, fn = per[d]["tp"], per[d]["fn"]
        recall = tp / (tp + fn) if tp + fn else 0
        precision = rule_tp[r] / rule_fired[r] if rule_fired[r] else 0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0
        rows.append({"defect": d, "expected_rule": r, "n": tp + fn, "detected": tp, "recall": round(recall, 3),
                     "precision": round(precision, 3), "f1": round(f1, 3),
                     "localised": round(per[d]["localised"] / (tp + fn), 3) if tp + fn else 0})
    res = {"n_defective": n_def, "n_clean": len(clean), "per_defect": rows,
           "macro_recall": round(float(np.mean([r["recall"] for r in rows])), 4),
           "macro_precision": round(float(np.mean([r["precision"] for r in rows])), 4),
           "macro_f1": round(float(np.mean([r["f1"] for r in rows])), 4),
           "clean_fp_rate": round(clean_fp / len(clean), 4) if clean else None,
           "clean_findings_by_rule": dict(clean_rules),
           "confusion": {d: dict(c) for d, c in sorted(confusion.items())},
           "mode": "ocr+template" if force_ocr else "pdf", "seconds": round(time.time() - t0, 1)}
    return res


def degrade(png, kind, rng):
    im = Image.open(png).convert("L")
    if kind == "blur":
        return im.filter(ImageFilter.GaussianBlur(1.2))
    if kind == "noise_jpeg":
        a = np.array(im).astype(np.float32) + rng.normal(0, 12, im.size[::-1])
        im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
        import io

        b = io.BytesIO()
        im.save(b, "JPEG", quality=35)
        return Image.open(io.BytesIO(b.getvalue())).convert("L")
    if kind == "rotate":
        return im.rotate(1.5, expand=False, fillcolor=255, resample=Image.BICUBIC)
    return im


def robustness(n=8, seed=7):
    gt = json.loads((GEN_DIR / "ground_truth.json").read_text())
    rng = random.Random(seed)
    picks = rng.sample(gt, n)
    nrng = np.random.default_rng(seed)
    out_dir = GEN_DIR / "robustness"
    out_dir.mkdir(exist_ok=True)
    rows = []
    for kind in ("none", "blur", "noise_jpeg", "rotate"):
        hits = 0
        t0 = time.time()
        for g in picks:
            lid = g["label_id"]
            spec = json.loads((GEN_DIR / "defective" / lid / "label.json").read_text())
            p = out_dir / f"{lid}_{kind}.png"
            degrade(GEN_DIR / "defective" / lid / "label.png", kind, nrng).save(p)
            rep = validate_file(p, spec, reqs=M.requirements())
            if any(f["rule_id"] == g["defects"][0]["expected_rule"] for f in rep["findings"]):
                hits += 1
        rows.append({"degradation": kind, "labels": n, "recall": round(hits / n, 3),
                     "sec_per_label": round((time.time() - t0) / n, 1)})
        print("  robustness", rows[-1])
    return {"rows": rows, "note": "Raster path: Tesseract OCR + multi-scale template matching + Data Matrix decode; "
                                  "same defect labels, degraded images."}


def diff_eval():
    from engines.diff import diff

    truth = json.loads((GEN_DIR / "diff_truth.json").read_text())
    tmap = {"text_change": {"text", "udi_text"}, "barcode_change": {"barcode"}, "layout_move": {"layout"},
            "element_added": {"added"}}
    det = Counter()
    cls = Counter()
    tot = Counter()
    ious = []
    noise_fa = 0
    for p in truth:
        a, b = GEN_DIR / p["approved"], GEN_DIR / p["revised"]
        r = diff(a / "label.pdf", b / "label.pdf", a / "label.png", b / "label.png")
        if p["noise_only"]:
            noise_fa += len(r["changes"])
            continue
        for e in p["edits"]:
            tot[e["type"]] += 1
            name = e["element"]
            cands = [c for c in r["changes"] if c["element"] == name or c["element"].split(".")[0] == name.split(".")[0]
                     or (c.get("bbox_new") and iou(c["bbox_new"], e["bbox_mm"]) > 0.3)]
            if cands:
                det[e["type"]] += 1
                if any(c["type"] in tmap[e["type"]] for c in cands):
                    cls[e["type"]] += 1
                bb = [c.get("bbox_new") for c in cands if c.get("bbox_new")]
                if bb:
                    ious.append(max(iou(x, e["bbox_mm"]) for x in bb))
    n = sum(tot.values())
    return {"pairs": len(truth), "seeded_edits": n, "detection_rate": round(sum(det.values()) / n, 4),
            "classification_rate": round(sum(cls.values()) / n, 4), "mean_localisation_iou": round(float(np.mean(ious)),
                                                                                                  3),
            "noise_only_pairs": sum(p["noise_only"] for p in truth), "noise_false_alarms": noise_fa,
            "by_type": [{"type": k, "n": tot[k], "detected": det[k], "classified": cls[k]} for k in sorted(tot)]}


def translation_eval():
    from engines.translation import check

    rows = list(csv.DictReader(open(GEN_DIR / "translation_truth.csv", encoding="utf-8")))
    by = defaultdict(lambda: {"n": 0, "correct": 0})
    tp = fp = fn = 0
    for r in rows:
        res = check(r["source_en"], r["translation"], r["language"], r["text_id"])
        by[r["error_type"]]["n"] += 1
        by[r["error_type"]]["correct"] += res["status"] == r["expected_status"]
        flagged, bad = res["status"] != "PASS", r["expected_status"] != "PASS"
        tp += flagged and bad
        fp += flagged and not bad
        fn += (not flagged) and bad
    return {"cases": len(rows), "precision": round(tp / (tp + fp), 3) if tp + fp else None,
            "recall": round(tp / (tp + fn), 3) if tp + fn else None,
            "by_error_type": [{"error_type": k, "n": v["n"], "correct_status": v["correct"]} for k, v in by.items()],
            "note": "Seen set (Tier 1). Semantic similarity (LaBSE) is optional and off here."}


def ledger_eval(n=10, seed=3):
    from sqlalchemy import select

    from core.audit import verify
    from core.db import SessionLocal, ensure_db
    from core.models import AuditEvent

    ensure_db()
    rng = random.Random(seed)
    detected = 0
    s = SessionLocal()
    ids = [e.id for e in s.execute(select(AuditEvent)).scalars()]
    for _ in range(n):
        eid = rng.choice(ids)
        e = s.get(AuditEvent, eid)
        p = dict(e.payload)
        p["_tamper"] = rng.random()
        e.payload = p
        s.flush()
        v = verify(s)
        detected += (not v["ok"]) and v["broken_id"] == eid
        s.rollback()
    s.close()
    return {"random_edits": n, "detected_at_correct_row": detected}


def risk_eval():
    from sqlalchemy import select

    from core.db import SessionLocal
    from core.models import ChangeRequest
    from core.risk import sensitivity

    s = SessionLocal()
    vecs = [c.risk_breakdown["factors"] for c in s.execute(select(ChangeRequest)).scalars() if c.risk_breakdown]
    s.close()
    vecs += [{"safety": 1, "device_class": 1, "udi": 1, "translation": 0.5, "breadth": 1, "markets": 1, "symbol": 0,
              "defect_history": 0.4},  # Scenario A
             {"safety": 0, "device_class": 1, "udi": 0, "translation": 0, "breadth": 0.33, "markets": 0.5,
              "symbol": 1, "defect_history": 0.4}]  # Scenario B
    return {"vectors": len(vecs), "rows": sensitivity(vecs)}


def gudid_eval():
    from core import gs1

    p = ROOT / "data" / "raw" / "gudid" / "gudid_extract.csv"
    if not p.exists():
        return {"status": "skipped", "reason": "data/raw/gudid/gudid_extract.csv not present (Phase 3.1)"}
    rows = list(csv.DictReader(open(p, encoding="utf-8")))
    col = next((c for c in rows[0] if "primary" in c.lower() and "di" in c.lower()), None) if rows else None
    ids = [r[col].strip() for r in rows if col and r[col].strip().isdigit()]
    bad = [i for i in ids if not gs1.is_valid_gtin(i.zfill(14))]
    return {"identifiers": len(ids), "valid": len(ids) - len(bad), "invalid_examples": bad[:10]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--robustness", type=int, default=8, help="labels for the raster robustness test (0 = skip)")
    a = ap.parse_args()
    t = time.time()
    print("Tier 1 compliance (PDF path)...")
    t1 = tier1()
    _save("compliance_tier1", t1)
    print(f"  macro recall {t1['macro_recall']:.3f}, precision {t1['macro_precision']:.3f}, clean FP "
          f"{t1['clean_fp_rate']:.3f} ({t1['seconds']} s)")
    print("Diff engine...")
    d = diff_eval()
    _save("diff_results", d)
    print(f"  detection {d['detection_rate']:.3f}, classification {d['classification_rate']:.3f}, noise false alarms "
          f"{d['noise_false_alarms']}")
    tr = translation_eval()
    _save("translation_results", tr)
    print(f"Translation validator: precision {tr['precision']}, recall {tr['recall']}")
    lg = ledger_eval()
    _save("ledger_results", lg)
    print(f"Ledger tamper detection: {lg['detected_at_correct_row']}/{lg['random_edits']}")
    _save("risk_sensitivity", risk_eval())
    _save("gudid_check", gudid_eval())
    _save("variant_matrix", json.loads((GEN_DIR / "variant_matrix.json").read_text()))
    if a.robustness:
        print("Robustness (raster/OCR path)...")
        _save("robustness", robustness(a.robustness))
    write_markdown()
    print(f"Done in {time.time() - t:.0f}s -> eval/results/")


def write_markdown():
    def load(n):
        p = EVAL_DIR / f"{n}.json"
        return json.loads(p.read_text()) if p.exists() else None

    t1, d, tr, lg, rb = (load(n) for n in ("compliance_tier1", "diff_results", "translation_results",
                                           "ledger_results", "robustness"))
    L = ["# Benchmark results", "", "Generated by `make bench`. Every number links to a JSON file in this folder and "
         "should have a row in docs/assumptions.md.", ""]
    if t1:
        L += ["## Compliance engine - Tier 1 (seen)", "", f"Defective labels: {t1['n_defective']}, clean holdout: "
              f"{t1['n_clean']}, macro recall **{t1['macro_recall']:.1%}**, macro precision "
              f"**{t1['macro_precision']:.1%}**, clean false-positive rate **{t1['clean_fp_rate']:.1%}**.", "",
              "| Defect | Rule | n | detected | recall | precision | F1 | localised |",
              "|---|---|---|---|---|---|---|---|"]
        L += [f"| {r['defect']} | {r['expected_rule']} | {r['n']} | {r['detected']} | {r['recall']} | {r['precision']} "
              f"| {r['f1']} | {r['localised']} |" for r in t1["per_defect"]]
        L.append("")
    if rb:
        L += ["## Robustness (raster/OCR path)", "", "| Degradation | labels | recall | s/label |", "|---|---|---|---|"]
        L += [f"| {r['degradation']} | {r['labels']} | {r['recall']} | {r['sec_per_label']} |" for r in rb["rows"]]
        L.append("")
    if d:
        L += ["## Diff engine", "", f"{d['seeded_edits']} seeded edits in {d['pairs'] - d['noise_only_pairs']} pairs: "
              f"detection **{d['detection_rate']:.1%}**, classification **{d['classification_rate']:.1%}**, mean IoU "
              f"{d['mean_localisation_iou']}; false alarms on {d['noise_only_pairs']} noise-only pairs: "
              f"**{d['noise_false_alarms']}**.", ""]
    if tr:
        L += ["## Translation validator", "", f"{tr['cases']} cases: precision {tr['precision']}, recall "
              f"{tr['recall']}.", ""]
    if lg:
        L += ["## Audit ledger", "", f"Tamper detection: {lg['detected_at_correct_row']}/{lg['random_edits']} random "
              f"edits detected at the edited row.", ""]
    L += ["## Not yet run (team)", "", "- Tier 2 blind holdout (docs/blind_holdout_procedure.md) after "
          "`git tag eval-freeze`", "- Tier 3 printed + photographed labels", "- Timing study (Phase 13.4)", ""]
    (EVAL_DIR / "results.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    main()
