"""Approval Queue (Phase 9 / 12.2 page 7): role picker in the sidebar, gates enforced by the API."""
import streamlit as st
from common import ApiError, api, badge, footer, label_image, pick_cr, setup

cfg = setup("Approval Queue", ":material/approval:")
role, user = st.session_state["role"], st.session_state["user"]
st.markdown(f"Acting as **{cfg['roles'][role]}** (`{user}`). Change role in the sidebar. "
            "Every gate below is enforced in code by the API, not by this page.")
cid = pick_cr(only_open=True)
cr = api("GET", f"/change-requests/{cid}")
st.markdown(f"Risk tier {badge(cr['risk_tier'] or '-')} · state {badge(cr['state'])}", unsafe_allow_html=True)
labels = cr["labels"]
if not labels:
    st.info("No drafts for this change request yet.")
    st.stop()

with st.expander("Bulk actions for the whole change request"):
    c = st.columns(3)
    if c[0].button("Move all AUTO_VALIDATED → IN_REVIEW"):
        for lab in labels:
            if lab["state"] == "AUTO_VALIDATED":
                try:
                    api("POST", f"/workflow/{lab['label_id']}/transition", json={"target": "IN_REVIEW", "user": user})
                except ApiError as e:
                    st.error(f"{lab['label_id']}: {e}")
        st.rerun()
    pw_bulk = c[1].text_input("Password", type="password", key="pwb", help="demo password: intellilabel")
    if c[1].button(f"Sign all IN_REVIEW as {role}"):
        n = 0
        for lab in labels:
            if lab["state"] == "IN_REVIEW":
                try:
                    api("POST", "/approvals", json={"label_id": lab["label_id"], "role": role, "user": user,
                                                    "meaning": "approved", "password": pw_bulk})
                    n += 1
                except ApiError as e:
                    st.warning(f"{lab['label_id']}: {e}")
        st.success(f"Signed {n} label(s)")
    if c[2].button("Approve all fully signed"):
        for lab in labels:
            if lab["state"] == "IN_REVIEW":
                try:
                    api("POST", f"/workflow/{lab['label_id']}/transition", json={"target": "APPROVED", "user": user})
                except ApiError as e:
                    st.warning(f"{lab['label_id']}: {e}")
        st.rerun()

for lab in labels:
    full = api("GET", f"/labels/{lab['label_id']}")
    with st.container(border=True):
        a, b, c = st.columns([2, 3, 2])
        img = label_image(lab["label_id"])
        if img:
            a.image(img, width="stretch")
        b.markdown(f"**{lab['label_id']}** {badge(lab['state'])} · validation {badge(lab['validation_status'] or '-')}"
                   f" · diff {badge(lab['diff_status'] or '-')}", unsafe_allow_html=True)
        signed = {s["role"] for s in full["signatures"]}
        b.markdown("Signatures: " + " ".join(badge(r, "#1a7f37" if r in signed else "#9ca3af")
                                             for r in full["required_roles"]), unsafe_allow_html=True)
        open_crit = [f for f in full["findings"] if f["status"] == "open" and f["severity"] == "critical"]
        if open_crit:
            b.error(f"{len(open_crit)} open critical finding(s) - waive with justification on the Compliance page "
                    "or reject.")
        nxt = {"DRAFT": "AUTO_VALIDATED", "AUTO_VALIDATED": "IN_REVIEW", "IN_REVIEW": "APPROVED"}.get(lab["state"])
        if nxt and c.button(f"→ {nxt}", key=f"t{lab['label_id']}"):
            try:
                api("POST", f"/workflow/{lab['label_id']}/transition", json={"target": nxt, "user": user})
                st.rerun()
            except ApiError as e:
                c.error(f"Refused: {e}")
        if lab["state"] == "IN_REVIEW" and role in full["required_roles"] and role not in signed:
            with c.form(f"s{lab['label_id']}"):
                meaning = st.selectbox("Meaning", ["approved", "reviewed"], key=f"m{lab['label_id']}")
                pw = st.text_input("Password", type="password", key=f"p{lab['label_id']}")
                if st.form_submit_button("E-sign"):
                    try:
                        api("POST", "/approvals", json={"label_id": lab["label_id"], "role": role, "user": user,
                                                        "meaning": meaning, "password": pw})
                        st.rerun()
                    except ApiError as e:
                        st.error(str(e))
        if lab["state"] in ("AUTO_VALIDATED", "IN_REVIEW", "APPROVED"):
            with c.popover("Reject"):
                reason = st.text_input("Reason", key=f"r{lab['label_id']}")
                if st.button("Confirm reject", key=f"rj{lab['label_id']}"):
                    try:
                        api("POST", f"/workflow/{lab['label_id']}/transition", json={"target": "REJECTED",
                                                                                     "user": user, "reason": reason})
                        st.rerun()
                    except ApiError as e:
                        st.error(str(e))

st.divider()
st.markdown("##### Release (Quality assurance)")
pw = st.text_input("QA password", type="password", key="pwrel")
if st.button("Build release package and release", type="primary", disabled=role != "quality_assurance"):
    try:
        res = api("POST", f"/release/{cid}", json={"user": user, "password": pw})
        st.success(f"Released {len(res['labels'])} labels · manifest sha256 {res['manifest_sha256'][:16]}...")
        st.download_button("Download release package", api("GET", f"/release/{cid}/download"),
                           file_name=res["zip"].split("/")[-1])
    except ApiError as e:
        st.error(f"Refused: {e}")
if role != "quality_assurance":
    st.caption("Switch to Quality assurance in the sidebar to release.")
footer()
