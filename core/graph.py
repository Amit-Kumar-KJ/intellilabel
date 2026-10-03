"""Phase 5.2-5.3: product graph and regulatory graph (NetworkX), built from the DB at call time.

Product graph nodes:  product:P, sku:S, attr:S:key, packaging:S:level:gtin14, mt:TEXT, symbol:SYM, manufacturer:M:f,
                      el:LABEL:ELEMENT_ID, label:LABEL, market:X, language:xx, level:L
Edges: product -> sku -> attr -> label_element -> label; master_text -> label_element; label -> market/language/level
"""
from __future__ import annotations

import networkx as nx
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.models import Attribute, Label, LabelElement, Requirement, Sku

CURRENT_STATES = ("RELEASED",)


def build_product_graph(session: Session, label_states=CURRENT_STATES, label_ids: list[str] | None = None) -> nx.DiGraph:
    g = nx.DiGraph()
    for s in session.execute(select(Sku)).scalars():
        g.add_edge(f"product:{s.product_id}", f"sku:{s.sku_id}", kind="has_sku")
    for a in session.execute(select(Attribute)).scalars():
        g.add_edge(f"sku:{a.sku_id}", f"attr:{a.sku_id}:{a.key}", kind="has_attribute")
        g.nodes[f"attr:{a.sku_id}:{a.key}"]["type"] = "attribute"
    q = select(Label)
    q = q.where(Label.label_id.in_(label_ids)) if label_ids else q.where(Label.state.in_(label_states))
    labels = {lab.label_id: lab for lab in session.execute(q).scalars()}
    for lab in labels.values():
        ln = f"label:{lab.label_id}"
        g.add_node(ln, type="label", sku=lab.sku_id, market=lab.market, level=lab.packaging_level)
        g.add_edge(ln, f"market:{lab.market}", kind="for_market")
        g.add_edge(ln, f"level:{lab.packaging_level}", kind="packaging_level")
        for lg in lab.language_set:
            g.add_edge(ln, f"language:{lg}", kind="language")
    if labels:
        for le in session.execute(select(LabelElement).where(LabelElement.label_id.in_(list(labels)))).scalars():
            en = f"el:{le.label_id}:{le.element_id}"
            g.add_node(en, type="label_element", element=le.element, etype=le.type, language=le.language,
                       label_id=le.label_id, value=le.value)
            g.add_edge(en, f"label:{le.label_id}", kind="placed_on")
            if le.binding_ref:
                src = le.binding_ref
                if src.startswith("sku:"):
                    g.add_edge(f"sku:{src.split(':')[1]}", src, kind="field")
                g.add_edge(src, en, kind="binds")
            for dep in le.deps or []:
                g.add_edge(dep, en, kind="derives")
                if dep.startswith("attr:"):
                    g.add_edge(f"sku:{dep.split(':')[1]}", dep, kind="has_attribute")
    return g


def forward(g: nx.DiGraph, node: str) -> dict:
    """Everything downstream of an attribute / text: label elements and labels."""
    if node not in g:
        return {"elements": [], "labels": []}
    # breadth-first, but never walk out of a label (label -> market/language would fan out to unrelated elements)
    desc, stack = set(), [node]
    while stack:
        n = stack.pop()
        for m in g.successors(n):
            if m in desc:
                continue
            desc.add(m)
            if not m.startswith("label:"):
                stack.append(m)
    els = sorted(n for n in desc if n.startswith("el:"))
    labs = sorted(n[6:] for n in desc if n.startswith("label:"))
    return {"elements": els, "labels": labs}


def backward(g: nx.DiGraph, element_node: str) -> list[list[str]]:
    """Chains from an element back to its sources (roots)."""
    if element_node not in g:
        return []
    chains = []
    anc = nx.ancestors(g, element_node)
    roots = [n for n in anc if g.in_degree(n) == 0] or list(g.predecessors(element_node))
    for r in roots:
        for path in nx.all_simple_paths(g, r, element_node, cutoff=6):
            chains.append(path)
    return sorted(chains, key=len)


def build_regulatory_graph(session: Session) -> nx.DiGraph:
    g = nx.DiGraph()
    for r in session.execute(select(Requirement).where(Requirement.status == "active")).scalars():
        reg = f"regulation:{r.regulation}"
        clause = f"clause:{r.regulation}|{r.section}"
        g.add_edge(f"market:{r.market}", reg, kind="governed_by")
        g.add_edge(reg, clause, kind="contains")
        g.add_edge(clause, f"req:{r.requirement_id}", kind="states")
        g.add_edge(f"req:{r.requirement_id}", f"rule:{r.rule_id}", kind="checked_by")
        g.add_edge(f"req:{r.requirement_id}", f"element_type:{r.label_element}", kind="about")
        g.nodes[f"req:{r.requirement_id}"].update(text=r.requirement_text, applies_if=r.applies_if,
                                                  levels=r.packaging_levels)
    return g


def applicable_requirements(label: Label, attrs: dict | None = None, session: Session | None = None) -> list[dict]:
    """Evaluates every requirement's applies_if against the label's product attributes."""
    from core.regulatory import applicable_requirements as _app

    return _app({"sku_id": label.sku_id, "market": label.market, "packaging_level": label.packaging_level,
                 "attributes": attrs})
