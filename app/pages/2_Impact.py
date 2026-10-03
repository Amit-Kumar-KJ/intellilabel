"""Impact (Phase 6 / 10 / 12.2 page 3): matrix, counts, explainable risk, approvers, draft regeneration."""
import pandas as pd
import streamlit as st
from common import api, badge, footer, pick_cr, setup

setup("Impact", ":material/account_tree:")
cid = pick_cr()
cr = api("GET", f"/change-requests/{cid}")
if cr["source"] == "product" and "changes" in cr["payload"]:
    st.markdown("**Changes:** " + "; ".join(f"`{c['key']}`: {c.get('old')} → **{c['new']}** ({c['scope']})"
                                           for c in cr["payload"]["changes"]))
elif "requirement" in cr["payload"]:
    r = cr["payload"]["requirement"]
    st.markdown(f"**New requirement {r['requirement_id']}** ({r['regulation']} {r['section']}): {r['requirement_text']}")
if cr["state"] == "RELEASED" and not cr["labels"]:
    st.info("Historical (synthetic) change request - no impact data.")
    st.stop()

im = api("GET", f"/change-requests/{cid}/impact")
risk = im["risk"]
c = st.columns(5)
c[0].metric("Impacted labels", im["impacted_labels"], help="Label variants that must change")
c[1].metric("Unaffected", im["unaffected_labels"])
c[2].metric("Markets", len(im["by_market"]))
c[3].metric("Risk score", f"{risk['score']:.2f}")
c[4].markdown(f"Risk tier<br>{badge(risk['tier'])}", unsafe_allow_html=True)
if risk.get("override"):
    st.warning(f"Tier override: {risk['override']}")

a, b = st.columns([3, 2])
with a:
    st.markdown("##### Counts")
    cc = st.columns(3)
    cc[0].dataframe(pd.DataFrame(im["by_market"].items(), columns=["market", "labels"]), hide_index=True)
    cc[1].dataframe(pd.DataFrame(im["by_packaging_level"].items(), columns=["level", "labels"]), hide_index=True)
    cc[2].dataframe(pd.DataFrame(im["by_language"].items(), columns=["language", "labels"]), hide_index=True)
with b:
    st.markdown("##### Why this risk score (weighted sum, not ML)")
    rows = [{"factor": k, "value": risk["factors"][k], "weight": round(risk["weights"][k], 3),
             "contribution": risk["contributions"][k]} for k in risk["contributions"]]
    df = pd.DataFrame(rows).sort_values("contribution", ascending=False)
    st.bar_chart(df.set_index("factor")["contribution"], horizontal=True, height=230)
    st.markdown("Required approvers: " + ", ".join(f"`{r}`" for r in im["required_approvers"]))

st.markdown("##### Impact matrix")
rows = []
for r in im["matrix"]:
    rows.append({"label": r["label_id"], "sku": r["sku_id"], "market": r["market"], "level": r["packaging_level"],
                 "languages": ",".join(r["languages"]), "elements": ", ".join(sorted({e["element_id"]
                                                                                       for e in r["elements"]})),
                 "actions": "; ".join(r["actions"])})
st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", height=320)
if im.get("regulatory_failures"):
    with st.expander("Non-compliant labels and the finding for each"):
        for k, v in im["regulatory_failures"].items():
            st.markdown(f"- **{k}**: {v[0]}")

st.divider()
st.markdown("##### Regenerate drafts")
st.caption("Deterministic template generator with the new attribute versions: it cannot hallucinate. Approved "
           "revisions stay untouched.")
plant = st.checkbox("Demo: simulate an artwork slip (planted unrequested edit on one EU carton)", value=False)
if st.button("Generate drafts", type="primary", disabled=bool(cr["labels"])):
    with st.spinner("Generating drafts..."):
        out = api("POST", f"/change-requests/{cid}/drafts", json={"plant_unrequested_edit": plant,
                                                                  "user": st.session_state["user"]})
    st.success(f"{len(out)} draft label revisions created. Next: **Drafts and Redline**.")
if cr["labels"]:
    st.info(f"{len(cr['labels'])} draft revisions already exist for {cid}.")
footer()
