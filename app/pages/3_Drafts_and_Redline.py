"""Drafts and Redline (Phase 8 / 12.2 page 4): approved vs draft, overlay, explained / unexplained changes."""
import pandas as pd
import streamlit as st
from common import ApiError, api, badge, footer, label_image, pick_cr, setup

setup("Drafts and Redline", ":material/difference:")
cid = pick_cr()
cr = api("GET", f"/change-requests/{cid}")
if not cr["labels"]:
    st.info("No drafts yet - generate them on the Impact page.")
    st.stop()

if st.button("Run verification on all drafts (compliance + diff)", type="primary"):
    with st.spinner("Extracting, checking rules and diffing every draft..."):
        res = api("POST", f"/change-requests/{cid}/auto-validate", params={"user": st.session_state["user"]})
    st.dataframe(pd.DataFrame(res), hide_index=True, width="stretch")
    cr = api("GET", f"/change-requests/{cid}")

df = pd.DataFrame(cr["labels"])
st.dataframe(df[["label_id", "state", "validation_status", "diff_status", "parent_label_id"]], hide_index=True,
             width="stretch")
lid = st.selectbox("Draft", [r["label_id"] for r in cr["labels"]],
                   index=next((i for i, r in enumerate(cr["labels"]) if r["diff_status"] == "UNEXPLAINED_CHANGES"),
                              0))
lab = api("GET", f"/labels/{lid}")
if lab["diff"] is None and lab["parent_label_id"]:
    if st.button("Run diff for this draft"):
        api("POST", f"/labels/{lid}/diff")
        st.rerun()
    st.stop()
d = lab["diff"]
st.markdown(f"Diff status: {badge(d['status'])} · validation: {badge(lab['validation_status'] or 'not run')}",
            unsafe_allow_html=True)
a, b = st.columns(2)
a.markdown(f"**Approved** {lab['parent_label_id']}")
img = label_image(lab["parent_label_id"])
if img:
    a.image(img, width="stretch")
b.markdown(f"**Draft {lid}** (overlay: green explained, blue moves, thick red = unexplained)")
ov = label_image(lid, "overlay")
if ov:
    b.image(ov, width="stretch")

s = d["summary"]
st.markdown("##### Summary")
cols = st.columns(8)
for i, (k, lbl) in enumerate([("text_changes", "Text"), ("udi_changes", "UDI text"), ("barcode_changes", "Barcode"),
                              ("symbol_changes", "Symbols"), ("layout_changes", "Layout"), ("added", "Added"),
                              ("graphic_changes", "Graphic"), ("unexplained_changes", "Unexplained")]):
    cols[i].metric(lbl, s.get(k, 0))

st.markdown("##### Change list")
for i, c in enumerate(d["changes"]):
    ok = c.get("explained")
    review = c.get("review")
    color = "PASS" if ok else ("REVIEW" if review == "accepted" else "FAIL")
    tag = "explained" if ok else (f"unexplained · {review} by {c.get('review_by')}" if review else "UNEXPLAINED")
    with st.container(border=True):
        st.markdown(f"{badge(tag, None if ok else ('#b26a00' if review else '#c62828'))} **{c['type']}** · "
                    f"`{c['element']}`", unsafe_allow_html=True)
        if c.get("word_diff"):
            st.markdown(" ".join(f"~~{w['old']}~~ → **{w['new']}**" if w["op"] == "replace" else
                                 (f"+**{w['new']}**" if w["op"] == "insert" else f"~~{w['old']}~~")
                                 for w in c["word_diff"]))
        elif c.get("fields"):
            st.markdown("; ".join(c["fields"]))
        elif c["type"] != "graphic":
            st.caption(f"{str(c.get('old'))[:90]} → {str(c.get('new'))[:90]}")
        st.caption(c.get("explanation", ""))
        if ok is False and not review:
            st.markdown("*Unexplained changes block approval until a reviewer accepts or rejects them.*")
            k1, k2, k3 = st.columns([3, 1, 1])
            note = k1.text_input("Reviewer note", key=f"note{i}")
            if k2.button("Accept", key=f"acc{i}"):
                api("POST", f"/labels/{lid}/diff/review", json={"index": i, "decision": "accepted",
                                                                "user": st.session_state["user"], "note": note})
                st.rerun()
            if k3.button("Reject", key=f"rej{i}"):
                api("POST", f"/labels/{lid}/diff/review", json={"index": i, "decision": "rejected",
                                                                "user": st.session_state["user"], "note": note})
                st.rerun()
_ = ApiError
footer()
