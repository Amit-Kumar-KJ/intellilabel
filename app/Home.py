"""Dashboard (Phase 12.2 page 1)."""
import pandas as pd
import streamlit as st
from common import api, badge, footer, setup

setup("Dashboard", ":material/dashboard:")
d = api("GET", "/dashboard")
c = st.columns(6)
c[0].metric("Device SKUs", d["devices"])
c[1].metric("Released labels", d["labels_released"])
c[2].metric("Open changes", d["open_changes"])
c[3].metric("Pending reviews", d["pending_reviews"])
c[4].metric("High-risk open changes", d["high_risk_changes"])
c[5].metric("Open findings", d["open_findings"])

st.markdown("#### The closed loop")
st.markdown("**Change intake → impact → draft regeneration → verification (rules + diff) → risk-routed approval → "
            "release → audit and trace.** Use the pages in the sidebar in that order.")

left, right = st.columns([3, 2])
with left:
    st.markdown("#### Change requests")
    df = pd.DataFrame(d["change_requests"])
    if not df.empty:
        df["synthetic"] = df["synthetic"].map({True: "synthetic", False: ""})
        st.dataframe(df[["id", "source", "reason", "state", "risk_tier", "risk_score", "created_at", "synthetic"]],
                     hide_index=True, width="stretch")
with right:
    st.markdown("#### Label revisions by state")
    st.markdown(" ".join(f"{badge(k)} **{v}**" for k, v in d["label_states"].items()), unsafe_allow_html=True)
    try:
        vm = api("GET", "/metrics").get("variant_matrix")
    except Exception:  # noqa: BLE001
        vm = None
    st.markdown("#### Why this matters")
    st.write("One attribute change (e.g. shelf life) touches every label variant that prints an expiry date: "
             "3 SKUs x markets x packaging levels x languages, each one a chance for a recall-grade error.")
    if vm:
        st.metric("Label variants per revision (incl. planned JP/CN)", vm["label_variants_per_revision"])
footer()
