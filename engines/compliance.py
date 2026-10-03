"""Phase 7.4: compliance runner.  validate_file(...) / validate(label_id) -> Report

1. extract and normalise  2. applicable requirements + rules  3. run rules  4. compare with master data
5. status: FAIL if any open critical, REVIEW if any major or uncertain item, PASS otherwise
6. (validate) write findings + audit event   7. render a validation report PDF with numbered evidence boxes
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from core import master as M
from core.regulatory import applicable_requirements
from engines.extraction import extract
from engines.rules import RULES

STATIC_TEXT_IDS = {"MT-DAMAGE-01", "MT-REUSE-01", "MT-IFU-01", "MT-DESC-01", "MT-RX-01"}


def build_ctx(meta: dict, reqs: list[dict] | None = None) -> dict:
    sku = M.skus()[meta["sku_id"]]
    prod = M.products()[sku["product_id"]]
    mfr = M.manufacturers()[prod["manufacturer_id"]]
    attrs = meta.get("attributes") or M.current_attributes(meta["sku_id"])
    label_like = {"sku_id": meta["sku_id"], "market": meta["market"], "packaging_level": meta["packaging_level"],
                  "attributes": attrs}
    app = applicable_requirements(label_like, reqs)
    by_rule = defaultdict(list)
    for r in app:
        by_rule[r["rule_id"]].append(r)
    pk = M.packaging()
    return {
        "label": {"label_id": meta.get("label_id"), "sku_id": meta["sku_id"], "market": meta["market"],
                  "packaging_level": meta["packaging_level"], "revision": meta.get("revision") or sku["revision"]},
        "product": prod, "manufacturer": mfr, "attributes": attrs,
        "expected_gtin": pk[(meta["sku_id"], meta["packaging_level"])]["gtin14"],
        "gtin_owner": {v["gtin14"]: k for k, v in pk.items()},
        "date_format": M.markets()[meta["market"]]["date_format"],
        "languages": M.markets()[meta["market"]]["languages"],
        "requirements": app, "requirements_by_rule": dict(by_rule),
        "expected_text_ids": {v for k, v in attrs.items() if k.endswith("_text_id")} | STATIC_TEXT_IDS,
    }


def run_rules(model: dict, ctx: dict) -> list[dict]:
    findings = []
    for rid in sorted(RULES):
        rule = RULES[rid]
        if not rule.applies(ctx):
            continue
        try:
            findings += [f.to_dict() for f in rule.check(model, ctx)]
        except Exception as e:  # noqa: BLE001 - a crashing rule must not hide others; it becomes a review item
            findings.append({"rule_id": rid, "severity": "major", "message": f"Rule error: {e}", "uncertain": True,
                             "element": None, "evidence_bbox": None, "requirement_id": None, "clause_ref": None,
                             "requirement_text": None, "suggested_fix": "Investigate rule failure.",
                             "evidence_text": None, "extra": {}})
    # uncertain extracted elements produce review items (not pass/fail)
    for name, el in model["elements"].items():
        if isinstance(el, dict) and el.get("uncertain") and el.get("source") != "symbol":
            findings.append({"rule_id": "EXTRACT", "severity": "minor", "message": f"Low-confidence reading of "
                             f"'{name}' ({el['confidence']:.2f}); please verify.", "uncertain": True, "element": name,
                             "evidence_bbox": el["bbox_mm"], "requirement_id": None, "clause_ref": None,
                             "requirement_text": None, "suggested_fix": "Human check.", "evidence_text":
                             str(el["value"])[:80], "extra": {}})
    return findings


def status_of(findings: list[dict]) -> str:
    open_f = [f for f in findings if f.get("status", "open") == "open"]
    if any(f["severity"] == "critical" and not f.get("uncertain") for f in open_f):
        return "FAIL"
    if any(f["severity"] == "major" or f.get("uncertain") for f in open_f):
        return "REVIEW"
    return "PASS"


def validate_file(path: str | Path, meta: dict, reqs: list[dict] | None = None, force_ocr=False) -> dict:
    model = extract(path, force_ocr=force_ocr)
    ctx = build_ctx(meta, reqs)
    findings = run_rules(model, ctx)
    for i, f in enumerate(findings, 1):
        f["n"] = i
    return {"label_id": meta.get("label_id"), "status": status_of(findings), "findings": findings,
            "applicable_requirements": [r["requirement_id"] for r in ctx["requirements"]],
            "rules_run": sorted(ctx["requirements_by_rule"]), "model": model, "file": str(path)}


# ---------------------------------------------------------------- report PDF
def render_report(report: dict, png_path: str | Path, out_pdf: str | Path) -> Path:
    from PIL import Image, ImageDraw, ImageFont
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Image as RLImage
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    from core.config import ASSETS, DPI

    px_mm = DPI / 25.4
    im = Image.open(png_path).convert("RGB")
    d = ImageDraw.Draw(im)
    font = ImageFont.truetype(str(ASSETS / "fonts" / "DejaVuSans-Bold.ttf"), 28)
    sev_col = {"critical": (200, 30, 30), "major": (220, 140, 0), "minor": (60, 110, 200)}
    for f in report["findings"]:
        bb = f.get("evidence_bbox")
        if not bb:
            continue
        x, y, w, h = [v * px_mm for v in bb]
        c = sev_col.get(f["severity"], (100, 100, 100))
        d.rectangle([x - 4, y - 4, x + w + 4, y + h + 4], outline=c, width=5)
        d.text((x - 4, max(y - 34, 0)), str(f["n"]), fill=c, font=font)
    ann = Path(out_pdf).with_suffix(".annotated.png")
    im.save(ann)

    ss = getSampleStyleSheet()
    small = ss["BodyText"].clone("small", fontSize=7.5, leading=9)
    doc = SimpleDocTemplate(str(out_pdf), pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=14 * mm,
                            bottomMargin=14 * mm, title=f"Validation report {report['label_id']}")
    st = report["status"]
    stc = {"PASS": colors.HexColor("#1a7f37"), "REVIEW": colors.HexColor("#b26a00"), "FAIL": colors.HexColor("#c62828")}
    story = [Paragraph("IntelliLabel AI - Validation report", ss["Title"]),
             Paragraph(f"Label <b>{report['label_id']}</b> &nbsp; Status: <font color='{stc[st].hexval()}'><b>{st}"
                       f"</b></font>", ss["Heading3"]),
             Paragraph(f"Applicable requirements: {', '.join(report['applicable_requirements'])}", small),
             Paragraph(f"Rules run: {', '.join(report['rules_run'])}", small), Spacer(1, 6)]
    counts = {s: sum(1 for f in report["findings"] if f["severity"] == s) for s in ("critical", "major", "minor")}
    story.append(Table([["Critical", "Major", "Minor", "Uncertain"],
                        [counts["critical"], counts["major"], counts["minor"],
                         sum(1 for f in report["findings"] if f.get("uncertain"))]],
                       style=TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                                         ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee"))])))
    story.append(Spacer(1, 8))
    rows = [["#", "Rule", "Severity", "Finding", "Clause", "Suggested fix"]]
    for f in report["findings"]:
        rows.append([str(f["n"]), f["rule_id"], f["severity"] + (" (uncertain)" if f.get("uncertain") else ""),
                     Paragraph(f["message"] + (f"<br/><i>{f['explanation']}</i>" if f.get("explanation") else ""),
                               small),
                     Paragraph(f.get("clause_ref") or "-", small), Paragraph(f.get("suggested_fix") or "-", small)])
    if len(rows) == 1:
        rows.append(["", "", "", Paragraph("No findings.", small), "", ""])
    story.append(Table(rows, colWidths=[7 * mm, 11 * mm, 18 * mm, 72 * mm, 35 * mm, 39 * mm], repeatRows=1,
                       style=TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 7),
                                         ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                         ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee"))])))
    story.append(Spacer(1, 10))
    w_mm = 180
    story.append(RLImage(str(ann), width=w_mm * mm, height=w_mm * mm * im.height / im.width))
    story.append(Paragraph("Evidence boxes: red = critical, amber = major, blue = minor. Rules decide; any AI "
                           "explanation is advisory and never changes the status.", small))
    doc.build(story)
    return Path(out_pdf)
