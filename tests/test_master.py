import yaml

from core import master as M
from core.config import TEMPLATE_DIR
from engines.rules import RULES


def test_every_template_attribute_exists():
    keys = {r["key"] for r in M.attribute_rows()}
    for p in TEMPLATE_DIR.glob("*.yaml"):
        t = yaml.safe_load(p.read_text(encoding="utf-8"))
        for z in t["zones"]:
            for e in z.get("elements", []) + z.get("blocks", []):
                b = e["bind"]
                if "attribute_text" in b:
                    assert b["attribute_text"] in keys, (p.name, b)
                if "symbol" in b:
                    assert b["symbol"] in M.symbols(), (p.name, b)
                if "master_text" in b:
                    assert any(tid == b["master_text"] for tid, _ in M.master_texts()), (p.name, b)


def test_requirements_complete_and_rules_exist():
    for r in M.requirements():
        assert r["section"] and r["source_url"], r["requirement_id"]
        assert r["rule_id"] in RULES or r["rule_id"] == "manual", r["requirement_id"]
    assert M.scenario_b_requirement()["rule_id"] in RULES


def test_every_rule_in_catalogue_implemented():
    for i in range(1, 22):
        assert f"R{i:02d}" in RULES


def test_symbols_and_glossary_load():
    assert len(M.symbols()) >= 15
    assert any(s["status"] == "superseded" for s in M.symbols().values())
    assert len(M.glossary()) >= 30


def test_all_gtins_valid():
    from core import gs1

    assert M.packaging(), "run make data"
    for row in M.packaging().values():
        assert gs1.is_valid_gtin(row["gtin14"])
