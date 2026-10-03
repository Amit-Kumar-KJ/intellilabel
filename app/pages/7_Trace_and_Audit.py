"""Trace and Audit (Phase 9.3-9.4 / 12.2 page 8)."""
import pandas as pd
import streamlit as st
from common import api, badge, footer, setup

setup("Trace and Audit", ":material/route:")
t1, t2, t3 = st.tabs(["Backward trace (element → sources)", "Forward trace (attribute → labels)", "Audit ledger"])

with t1:
    labels = [x for x in api("GET", "/labels") if x["state"] != "SUPERSEDED"]
    ids = [x["label_id"] for x in labels]
    lid = st.selectbox("Label", ids, index=next((i for i, x in enumerate(ids) if "R03" in x), 0))
    tr = api("GET", f"/labels/{lid}/trace")
    names = [e["element_id"] for e in tr["elements"]]
    el = st.selectbox("Element", names, index=names.index("expiry_date") if "expiry_date" in names else 0)
    e = next(x for x in tr["elements"] if x["element_id"] == el)
    a, b = st.columns([2, 3])
    a.image(api("GET", f"/labels/{lid}/file/png"), width="stretch")
    with b:
        st.markdown(f"**{el}** = `{str(e['value'])[:80]}`")
        st.markdown("**Bound to**")
        st.code("\n".join([e["binding"]] + [f"derived from {d}" for d in e["deps"]]))
        st.markdown("**Source chains (graph)**")
        for s in e["sources"]:
            st.markdown(f"- `{s}`")
        st.markdown("**Requirements and clauses**")
        for r in e["requirements"] or []:
            st.markdown(f"- `{r['id']}` · {r['clause']} · rule {r['rule']}: {r['text']}")
        if not e["requirements"]:
            st.caption("No regulatory requirement points at this element (internal content).")
        st.markdown("**Change request**")
        st.write(e["change_request"] or "Released baseline (no change request)")
        st.markdown("**Approvals**")
        if e["approvals"]:
            st.dataframe(pd.DataFrame(e["approvals"]), hide_index=True)
        else:
            st.caption("None yet")

with t2:
    c = st.columns(2)
    sku = c[0].selectbox("SKU", ["CS-100", "CS-200", "CS-300"])
    key = c[1].selectbox("Attribute", ["shelf_life_months", "sterilization_text_id", "warning_text_id",
                                       "storage_text_id", "mr_conditions_text_id", "units_per_shipper"])
    fw = api("GET", "/trace/forward", params={"sku_id": sku, "key": key})
    st.markdown(f"**{len(fw['labels'])} released labels** and **{len(fw['elements'])} elements** depend on "
                f"`{fw['attribute']}`")
    st.dataframe(pd.DataFrame(fw["elements"]), hide_index=True, width="stretch")

with t3:
    c = st.columns([1, 1, 3])
    if c[0].button("Verify ledger", type="primary"):
        v = api("GET", "/audit/verify")
        if v["ok"]:
            st.success(f"Chain intact: {v['checked']} events verified.")
        else:
            st.error(f"Chain BROKEN at event #{v['broken_id']} ({v['action']} on {v['entity']}): {v['reason']}")
    if c[1].button("Tamper demo", help="Edits one row directly in the database, bypassing the ledger"):
        t = api("POST", "/audit/tamper-demo")
        st.warning(f"Row #{t['tampered_id']} edited directly. Now press Verify ledger. (Reset demo restores it.)")
    ev = api("GET", "/audit", params={"limit": 300})
    df = pd.DataFrame(ev)
    if not df.empty:
        df["payload"] = df["payload"].astype(str).str[:120]
        st.dataframe(df[["id", "ts", "actor_type", "actor_id", "action", "entity", "payload", "model_version",
                         "prompt_hash", "prev_hash", "hash"]], hide_index=True, width="stretch", height=420)
_ = badge
footer()
