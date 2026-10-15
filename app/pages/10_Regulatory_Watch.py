import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root
from engines import reg_monitor as rm

MARKETS = ["EU", "US", "ALL"]

st.title("Regulatory Watch")
st.caption("The monitor proposes. A human reviews. Nothing enters the rulebook without approval.")

if "flash" in st.session_state:
    st.success(st.session_state.pop("flash"))

c1, c2 = st.columns(2)
if c1.button("Check sources now"):
    with st.spinner("Checking sources..."):
        for line in rm.run_check():
            st.write(line)
if c2.button("Simulate a regulatory update (demo only)"):
    st.write(rm.simulate("ec_udi"))

with st.expander("What the monitor watches"):
    state = rm._load(rm.STATE, {})
    auto = pd.read_csv(rm.WATCHLIST, dtype=str, keep_default_na=False)
    auto["last_checked"] = auto["source_id"].map(lambda s: state.get(s, {}).get("last_checked", ""))
    auto["error"] = auto["source_id"].map(lambda s: state.get(s, {}).get("error", ""))
    st.markdown("**Checked automatically**")
    st.dataframe(auto[["source_id", "name", "market", "last_checked", "error"]], hide_index=True)
    manual_path = rm.WATCHLIST.with_name("manual_watch.csv")
    if manual_path.exists():
        manual = pd.read_csv(manual_path, dtype=str, keep_default_na=False)
        st.markdown("**Manual watch (blocked, or link not yet fixed)**")
        st.dataframe(manual[["source_id", "name", "reason"]], hide_index=True)

user = st.session_state.get("user", "regulatory_affairs_user")
props = rm.list_proposals()
if not props:
    st.info("No proposals yet. Run a check, or simulate an update.")

for p in reversed(props):
    pid = p["proposal_id"]
    tag = "  [SIMULATED]" if p["simulated"] else ""
    with st.expander(f"{pid} | {p['source_name']} | {p['status']}{tag}"):
        if p["simulated"]:
            st.warning("Simulated update for demonstration. Approving it does not change requirements.csv.")
        st.write(f"Source: {p['url']}")
        st.write(f"Detected: {p['detected_on']}")
        st.markdown("**Added text**")
        for s in p["added"]:
            st.success(s)
        st.markdown("**Removed text**")
        for s in p["removed"]:
            st.error(s)
        if p["status"] != "PENDING":
            st.write(f"Decision by {p['reviewer']} {p['decision_note']}")
            if p["draft_row"]:
                st.json(p["draft_row"])
            if p.get("scenario_b"):
                st.write("Sent to Scenario B:")
                st.json(p["scenario_b"])
            elif p["status"] in ("APPROVED", "APPROVED_DEMO"):
                if st.button("Send to Scenario B", key=f"sb_{pid}"):
                    try:
                        resp = rm.send_to_scenario_b(pid, user)
                        st.success("Regulatory change request created in the app. Open Impact to see the labels that fail it.")
                        st.json(resp)
                    except Exception as e:
                        st.error(str(e))
            continue
        if hasattr(rm, "ai_draft") and st.button("Suggest a row with AI", key=f"ai_{pid}"):
            try:
                rm.ai_draft(pid)
                st.rerun()
            except Exception as e:
                st.warning(f"AI drafting unavailable: {e}")
        d = p.get("ai_draft") or {}
        with st.form(f"form_{pid}"):
            market = st.selectbox("Market", MARKETS,
                                  index=MARKETS.index(p["market"]) if p["market"] in MARKETS else 0)
            regulation = st.text_input("Regulation", p["source_name"])
            section = st.text_input("Section (read it in the source)")
            element = st.text_input("Label element", d.get("label_element", ""))
            text = st.text_area("Requirement text", d.get("requirement_text", ""))
            obligation = st.selectbox("Obligation", ["mandatory", "conditional"])
            applies = st.text_input("Applies if", d.get("applies_if", "all"))
            levels = st.text_input("Packaging levels", "pouch|carton")
            rule = st.text_input("Rule id (manual if no rule exists)", "manual")
            note = st.text_input("Note")
            ok = st.form_submit_button("Approve and add requirement")
            no = st.form_submit_button("Reject")
            if ok:
                msg = None
                try:
                    row = dict(market=market, regulation=regulation, section=section,
                               label_element=element, requirement_text=text,
                               obligation=obligation, applies_if=applies,
                               packaging_levels=levels, rule_id=rule)
                    full = rm.approve(pid, row, user)
                    if p["simulated"]:
                        msg = f"Approved for the demo as {full['requirement_id']}. requirements.csv was not changed."
                    else:
                        msg = (f"Added to requirements.csv as {full['requirement_id']}. "
                               "The database loads requirements from this file when it is rebuilt.")
                except Exception as e:
                    st.error(str(e))
                if msg:
                    st.session_state["flash"] = msg
                    st.rerun()
            if no:
                msg = None
                try:
                    rm.reject(pid, user, note)
                    msg = f"{pid} rejected."
                except Exception as e:
                    st.error(str(e))
                if msg:
                    st.session_state["flash"] = msg
                    st.rerun()
