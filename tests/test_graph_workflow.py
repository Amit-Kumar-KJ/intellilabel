"""Phase 5, 6, 9 done-when tests (uses a separate test database)."""
import json

from sqlalchemy import select

from tests.conftest import needs_data


@needs_data
def test_forward_shelf_life_hits_every_expiry_label(fresh_db):
    from core.db import session_scope
    from core.graph import build_product_graph, forward
    from core.models import Label, LabelElement

    with session_scope() as s:
        g = build_product_graph(s)
        fw = forward(g, "attr:CS-100:shelf_life_months")
        expected = {le.label_id for le in s.execute(select(LabelElement).where(LabelElement.element == "expiry_date"))
                    .scalars() if s.get(Label, le.label_id).sku_id == "CS-100"}
        assert set(fw["labels"]) == expected and len(expected) == 6


@needs_data
def test_applicable_requirements_differ_us_pouch_vs_eu_carton():
    from core.regulatory import applicable_requirements

    us = {r["requirement_id"] for r in applicable_requirements({"sku_id": "CS-100", "market": "US",
                                                                 "packaging_level": "pouch"})}
    eu = {r["requirement_id"] for r in applicable_requirements({"sku_id": "CS-100", "market": "EU",
                                                                 "packaging_level": "carton"})}
    assert us != eu and "REQ-EU-004" in eu and "REQ-US-030" in us


@needs_data
def test_scenario_a_end_to_end_with_gates(fresh_db):
    from fastapi.testclient import TestClient

    from api.main import app

    with TestClient(app) as c:
        c.post("/admin/reset-demo")
        p = c.post("/change-requests/parse", json={"text": "Extend CardioSafe shelf life to 36 months and update "
                                                           "the sterilization wording"}).json()
        assert not p["errors"] and p["change_request"]
        cid = c.post("/change-requests", json=p["change_request"] | {"user": "ra"}).json()["id"]
        im = c.get(f"/change-requests/{cid}/impact").json()
        assert im["impacted_labels"] == 18 and im["risk"]["tier"] == "High"
        drafts = c.post(f"/change-requests/{cid}/drafts", json={"plant_unrequested_edit": True}).json()
        assert len(drafts) == 18
        res = c.post(f"/change-requests/{cid}/auto-validate").json()
        assert all(r["validation"] == "PASS" for r in res)
        planted = [r for r in res if r["unexplained"]]
        assert len(planted) == 1
        lid = planted[0]["label_id"]
        # gate: unexplained change blocks IN_REVIEW
        r = c.post(f"/workflow/{lid}/transition", json={"target": "IN_REVIEW", "user": "le"})
        assert r.status_code == 409
        # gate: approving before signatures is refused
        other = [x["label_id"] for x in res if x["label_id"] != lid][0]
        assert c.post(f"/workflow/{other}/transition", json={"target": "IN_REVIEW", "user": "le"}).status_code == 200
        assert c.post(f"/workflow/{other}/transition", json={"target": "APPROVED", "user": "le"}).status_code == 409
        assert c.get("/audit/verify").json()["ok"]


@needs_data
def test_scenario_b_lists_non_compliant_labels(fresh_db):
    from fastapi.testclient import TestClient

    from api.main import app
    from core.master import scenario_b_requirement

    with TestClient(app) as c:
        c.post("/admin/reset-demo")
        cid = c.post("/change-requests", json={"source": "regulatory", "reason": "MD symbol",
                                               "requirement": scenario_b_requirement()}).json()["id"]
        im = c.get(f"/change-requests/{cid}/impact").json()
        assert sorted(r["label_id"] for r in im["matrix"]) == sorted(
            f"L-CS{n}00-EU-{lvl}-R02" for n in (1, 2, 3) for lvl in ("carton", "pouch"))
        c.post(f"/change-requests/{cid}/drafts", json={})
        res = c.post(f"/change-requests/{cid}/auto-validate").json()
        assert all(r["validation"] == "PASS" for r in res)


def test_ledger_detects_tamper(fresh_db):
    from core.audit import verify
    from core.db import session_scope
    from core.services import tamper_demo

    with session_scope() as s:
        assert verify(s)["ok"]
        t = tamper_demo(s)
        v = verify(s)
        assert not v["ok"] and v["broken_id"] == t["tampered_id"]
        s.rollback()


def test_risk_override_and_tiers():
    from core.risk import score

    low = score({k: 0 for k in ("safety", "device_class", "udi", "translation", "breadth", "markets", "symbol",
                                "defect_history")})
    assert low["tier"] == "Low"
    assert score({"safety": 0}, safety_critical_open=True)["tier"] == "High"
    _ = json
