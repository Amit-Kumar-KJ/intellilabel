"""Change Intake (Phase 6.4 / 12.2 page 2): plain English -> parsed request -> human confirms."""
import json

import streamlit as st
from common import ApiError, api, footer, setup

cfg = setup("Change Intake", ":material/edit_note:")
tab_p, tab_r = st.tabs(["Product change (Scenario A)", "Regulatory change (Scenario B)"])

with tab_p:
    st.markdown("Describe the change in plain English. The LLM turns it into a structured change request; "
                "**nothing runs until you confirm**.")
    demo = cfg["demo_sentences"][0]
    text = st.text_area("Change description", value=st.session_state.get("intake_text", demo), height=80)
    c1, c2 = st.columns([1, 4])
    if c1.button("Parse", type="primary"):
        st.session_state["intake_text"] = text
        try:
            st.session_state["parsed"] = api("POST", "/change-requests/parse", json={"text": text,
                                                                                     "user": st.session_state["user"]})
        except ApiError as e:
            st.error(str(e))
    parsed = st.session_state.get("parsed")
    use_form = cfg["llm_mode"] == "off" or (parsed and not parsed.get("change_request"))
    if parsed:
        st.caption(f"Parser origin: **{parsed['origin']}** · LLM mode: {parsed['llm_mode']}")
        if parsed["errors"]:
            st.warning("Validation problems: " + "; ".join(parsed["errors"]))
    if parsed and parsed.get("change_request") and not parsed["errors"]:
        cr = parsed["change_request"]
        st.markdown("##### Parsed change request (please check)")
        st.dataframe([{"scope": json.dumps(c["scope"]), "key": c["key"], "old": c.get("old"), "new": c["new"]}
                      for c in cr["changes"]], hide_index=True, width="stretch")
        reason = st.text_input("Reason / justification", cr.get("reason", ""))
        if st.button("Confirm and create change request", type="primary"):
            res = api("POST", "/change-requests", json={"source": "product", "reason": reason,
                                                        "changes": cr["changes"], "user": st.session_state["user"]})
            st.session_state["cr_id"] = res["id"]
            st.session_state.pop("parsed", None)
            st.success(f"Created {res['id']}. Next: open **Impact**.")
    if use_form:
        st.markdown("##### Structured form (LLM off or parse failed)")
        with st.form("manual"):
            key = st.selectbox("Attribute", ["shelf_life_months", "sterilization_text_id", "storage_temp_max_c",
                                             "warning_text_id", "storage_text_id", "mr_conditions_text_id",
                                             "units_per_shipper"])
            scope = st.selectbox("Scope", ["product:P-CS", "sku:CS-100", "sku:CS-200", "sku:CS-300"])
            new = st.text_input("New value", "36")
            reason = st.text_input("Reason", "Stability study supports 36-month shelf life")
            if st.form_submit_button("Create change request"):
                k, v = scope.split(":")
                res = api("POST", "/change-requests", json={"source": "product", "reason": reason, "changes": [
                    {"scope": {k: v}, "key": key, "new": new}], "user": st.session_state["user"]})
                st.session_state["cr_id"] = res["id"]
                st.success(f"Created {res['id']}")

with tab_r:
    st.markdown("Add a new requirement row. The system checks **every applicable released label** against it "
                "and lists the non-compliant ones. The row must carry its source and section.")
    rq = dict(cfg["scenario_b_requirement"])
    col1, col2 = st.columns(2)
    rq["requirement_id"] = col1.text_input("Requirement id", rq["requirement_id"])
    rq["market"] = col2.selectbox("Market", ["EU", "US", "ALL"], index=["EU", "US", "ALL"].index(rq["market"]))
    rq["regulation"] = col1.text_input("Regulation", rq["regulation"])
    rq["section"] = col2.text_input("Section", rq["section"])
    rq["label_element"] = col1.text_input("Label element", rq["label_element"])
    rq["packaging_levels"] = col2.text_input("Packaging levels", rq["packaging_levels"])
    rq["requirement_text"] = st.text_input("Requirement text", rq["requirement_text"])
    rq["source_url"] = st.text_input("Source URL", rq["source_url"])
    rq["rule_id"] = col1.text_input("Rule (R20 = generic presence check)", rq["rule_id"])
    rq["applies_if"] = col2.text_input("Applies if", rq["applies_if"])
    reason = st.text_input("Reason", "New EU labeling requirement: medical device indication")
    if st.button("Create regulatory change request", type="primary"):
        try:
            res = api("POST", "/change-requests", json={"source": "regulatory", "reason": reason, "requirement": rq,
                                                        "user": st.session_state["user"]})
            st.session_state["cr_id"] = res["id"]
            st.success(f"Created {res['id']}. Next: open **Impact** to see non-compliant labels.")
        except ApiError as e:
            st.error(str(e))
footer()
