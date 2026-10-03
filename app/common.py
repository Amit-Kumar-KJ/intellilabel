"""Shared Streamlit helpers. The UI only talks to the API (over HTTP when API_URL is set, otherwise in-process
through FastAPI's TestClient - same routes, no separate server needed)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

GREEN, AMBER, RED, BLUE, GREY = "#1a7f37", "#b26a00", "#c62828", "#1f5fbf", "#6b7280"
STATUS_COLOR = {"PASS": GREEN, "REVIEW": AMBER, "FAIL": RED, "RELEASED": GREEN, "APPROVED": GREEN,
                "IN_REVIEW": AMBER, "AUTO_VALIDATED": BLUE, "DRAFT": GREY, "REJECTED": RED, "SUPERSEDED": GREY,
                "CHANGES_EXPLAINED": GREEN, "UNEXPLAINED_CHANGES": RED, "NO_CHANGE": GREY, "High": RED,
                "Medium": AMBER, "Low": GREEN, "critical": RED, "major": AMBER, "minor": BLUE, "OPEN": BLUE,
                "DRAFTED": BLUE, "WARNING": AMBER}


class ApiError(Exception):
    pass


@st.cache_resource
def _client():
    url = os.getenv("API_URL", "").strip()
    if url:
        import httpx

        return httpx.Client(base_url=url, timeout=600)
    from fastapi.testclient import TestClient

    from api.main import app

    c = TestClient(app)
    c.__enter__()  # run startup (creates the DB if needed)
    return c


def api(method: str, path: str, **kw):
    r = _client().request(method, path, **kw)
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail")
        except Exception:  # noqa: BLE001
            detail = r.text
        raise ApiError(str(detail))
    ct = r.headers.get("content-type", "")
    return r.json() if "json" in ct else r.content


def badge(text: str, color: str | None = None) -> str:
    c = color or STATUS_COLOR.get(str(text), GREY)
    return (f"<span style='background:{c};color:white;padding:2px 9px;border-radius:10px;font-size:0.8rem;"
            f"font-weight:600'>{text}</span>")


def setup(title: str, icon: str = ":material/label:"):
    st.set_page_config(page_title=f"IntelliLabel AI - {title}", page_icon=icon, layout="wide")
    st.markdown("""<style>
      .block-container {padding-top: 1.6rem;}
      div[data-testid="stMetricValue"] {font-size: 1.7rem;}
      .il-footer {color:#6b7280;font-size:0.75rem;margin-top:2rem;border-top:1px solid #e5e7eb;padding-top:.5rem}
    </style>""", unsafe_allow_html=True)
    with st.sidebar:
        st.markdown("### IntelliLabel AI")
        st.caption("Rules decide · AI proposes and explains · humans sign")
        try:
            cfg = api("GET", "/config")
        except Exception as e:  # noqa: BLE001
            st.error(f"API not reachable: {e}")
            st.stop()
        roles = cfg["roles"]
        st.session_state.setdefault("role", "regulatory_affairs")
        role = st.selectbox("Acting as (simulated user)", list(roles), format_func=lambda r: roles[r],
                            index=list(roles).index(st.session_state["role"]), key="role_picker")
        st.session_state["role"] = role
        st.session_state["user"] = f"{role}_user"
        st.caption(f"LLM mode: **{cfg['llm_mode']}**")
        if st.button("Reset demo", help="Restore the seeded state (drafts, releases, ledger)"):
            with st.spinner("Resetting..."):
                api("POST", "/admin/reset-demo")
            st.session_state.pop("cr_id", None)
            st.success("Demo reset")
    st.title(title)
    return cfg


def footer():
    st.markdown("<div class='il-footer'>Prototype · synthetic data (fictional manufacturer, generated labels, "
                "synthetic change history) · regulatory citations marked (verify) must be checked against the "
                "source · simplified symbol glyphs, not the licensed ISO 15223-1 library.</div>",
                unsafe_allow_html=True)


def pick_cr(label="Change request", only_open=False):
    crs = api("GET", "/change-requests")
    if only_open:
        crs = [c for c in crs if c["state"] not in ("RELEASED", "REJECTED")]
    if not crs:
        st.info("No change requests yet. Create one on the Change Intake page.")
        st.stop()
    ids = [c["id"] for c in crs]
    cur = st.session_state.get("cr_id")
    idx = ids.index(cur) if cur in ids else 0
    cid = st.selectbox(label, ids, index=idx, format_func=lambda i: next(
        f"{c['id']} · {c['state']} · {c['reason'][:60]}" + (" (synthetic)" if c["synthetic"] else "")
        for c in crs if c["id"] == i))
    st.session_state["cr_id"] = cid
    return cid


def label_image(label_id: str, kind="png"):
    try:
        return api("GET", f"/labels/{label_id}/file/{kind}")
    except ApiError:
        return None
