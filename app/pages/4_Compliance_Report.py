"""Compliance Report (Phase 7 / 12.2 page 5): findings with clause citations, evidence boxes, Why?, report PDF."""
import io

import pandas as pd
import streamlit as st
from common import ApiError, api, badge, footer, setup
from PIL import Image, ImageDraw

setup("Compliance Report", ":material/fact_check:")
tab_l, tab_u = st.tabs(["Label in the system", "Upload a label (PDF or photo)"])
SEV = {"critical": (198, 40, 40), "major": (178, 106, 0), "minor": (31, 95, 191)}


def draw_boxes(png: bytes, findings):
    im = Image.open(io.BytesIO(png)).convert("RGB")
    d = ImageDraw.Draw(im)
    pxmm = 300 / 25.4  # label PNGs are rendered at 300 dpi
    for n, f in enumerate(findings, 1):
        bb = f.get("evidence_bbox")
        if not bb:
            continue
        x, y, w, h = [v * pxmm for v in bb]
        c = SEV.get(f["severity"], (100, 100, 100))
        d.rectangle([x - 5, y - 5, x + w + 5, y + h + 5], outline=c, width=6)
        d.text((x - 4, max(0, y - 30)), str(n), fill=c)
    return im


def show_findings(findings, allow_waive=False):
    if not findings:
        st.success("No findings.")
        return
    for n, f in enumerate(findings, 1):
        with st.container(border=True):
            st.markdown(f"**{n}.** {badge(f['severity'])} `{f['rule_id']}` {f['message']}"
                        + (f" &nbsp; {badge('waived', '#6b7280')}" if f.get("status") == "waived" else ""),
                        unsafe_allow_html=True)
            st.caption(f"Clause: {f.get('clause_ref') or 'internal control'} · fix: {f.get('suggested_fix') or '-'}")
            with st.expander("Why?"):
                st.write(f.get("explanation") or "No explanation stored.")
                st.caption("Explanations are grounded in the requirement row and never change the status.")
            if allow_waive and f.get("status") == "open" and f["severity"] == "critical" and "id" in f:
                with st.form(f"w{f['id']}"):
                    reason = st.text_input("Waiver justification")
                    pw = st.text_input("Password (demo: intellilabel)", type="password")
                    if st.form_submit_button("Sign waiver"):
                        try:
                            api("POST", "/waivers", json={"finding_id": f["id"], "reason": reason,
                                                          "user": st.session_state["user"],
                                                          "role": st.session_state["role"], "password": pw})
                            st.rerun()
                        except ApiError as e:
                            st.error(str(e))


with tab_l:
    labels = api("GET", "/labels")
    ids = [x["label_id"] for x in labels if x["state"] != "SUPERSEDED"]
    default = next((i for i, x in enumerate(ids) if "R03" in x), 0)
    lid = st.selectbox("Label", ids, index=default)
    if st.button("Run compliance check", type="primary"):
        with st.spinner("Extracting and checking..."):
            api("POST", f"/labels/{lid}/validate", params={"user": st.session_state["user"]})
    lab = api("GET", f"/labels/{lid}")
    st.markdown(f"Status: {badge(lab['validation_status'] or 'not run')} · state {badge(lab['state'])}",
                unsafe_allow_html=True)
    fs = [f for f in lab["findings"] if f["status"] in ("open", "waived")]
    a, b = st.columns([3, 2])
    png = api("GET", f"/labels/{lid}/file/png")
    a.image(draw_boxes(png, fs), width="stretch")
    with b:
        show_findings(fs, allow_waive=True)
        if lab["validation_report"]:
            st.download_button("Download validation report (PDF)", api("GET", f"/labels/{lid}/file/report"),
                               file_name=f"{lid}_validation.pdf")

with tab_u:
    st.markdown("Validate a label the system did **not** generate (digital PDF or a phone photo). The extractor never "
                "sees any generator metadata.")
    up = st.file_uploader("Label file", type=["pdf", "png", "jpg", "jpeg"])
    c = st.columns(4)
    sku = c[0].selectbox("SKU", ["CS-100", "CS-200", "CS-300"])
    mkt = c[1].selectbox("Market", ["EU", "US"])
    lvl = c[2].selectbox("Packaging level", ["carton", "pouch", "shipper"])
    rev = c[3].text_input("Expected revision", "R02")
    ocr = st.checkbox("Force OCR path (treat PDF as image)")
    if up and st.button("Validate upload", type="primary"):
        with st.spinner("Extracting (OCR + template matching can take ~15 s)..."):
            rep = api("POST", "/labels/upload/validate", files={"file": (up.name, up.getvalue())},
                      data={"sku_id": sku, "market": mkt, "packaging_level": lvl, "revision": rev,
                            "force_ocr": str(ocr).lower()})
        st.markdown(f"Status: {badge(rep['status'])}", unsafe_allow_html=True)
        show_findings(rep["findings"])
        with st.expander("What the extractor read"):
            st.json({"languages_present": rep["extracted"]["languages_present"],
                     "barcodes": rep["extracted"]["barcodes"]})
            st.dataframe(pd.DataFrame([{"element": k, "value": str(v.get("value"))[:60], "confidence":
                                        v.get("confidence"), "source": v.get("source")}
                                       for k, v in rep["extracted"]["elements"].items()]), hide_index=True)
footer()
