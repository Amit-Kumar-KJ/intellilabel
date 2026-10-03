"""Phase 6.4 + 11.1: the ONLY place the system talks to an LLM.

Contract enforced here:
  * registered, versioned, hashed prompts (engines/prompts/*.yaml)
  * temperature 0, JSON output validated against a schema; one retry, then fall back
  * grounding: quotes in the output must exist verbatim in the source text, otherwise the output is discarded
  * audit: model, prompt hash, input hash, output hash and latency go to the ledger
  * cache keyed by prompt hash + input hash; LLM_MODE=cached replays it, LLM_MODE=off disables every LLM feature
The LLM proposes and explains. It never decides pass/fail, approves or releases.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import jsonschema
import yaml

from core import config
from core.audit import canonical_json, sha256

CHANGE_SCHEMA = {
    "type": "object",
    "required": ["source", "changes"],
    "properties": {
        "source": {"enum": ["product"]},
        "reason": {"type": "string"},
        "changes": {"type": "array", "minItems": 1, "items": {
            "type": "object", "required": ["scope", "key", "new"],
            "properties": {"scope": {"type": "object"}, "key": {"type": "string"}, "old": {"type": ["string", "null"]},
                           "new": {"type": "string"}}}},
    },
}
EXPLAIN_SCHEMA = {"type": "object", "required": ["explanation", "suggested_fix", "quote"],
                  "properties": {"explanation": {"type": "string"}, "suggested_fix": {"type": "string"},
                                 "quote": {"type": "string"}}}
SEMANTIC_SCHEMA = {"type": "object", "required": ["verdict"],
                   "properties": {"verdict": {"enum": ["equivalent", "different", "unsure"]},
                                  "differing_words": {"type": "array"}}}


class LLMUnavailable(Exception):
    pass


def mode() -> str:
    return config.LLM_MODE if config.LLM_MODE in ("live", "cached", "off") else "cached"


def load_prompt(pid: str) -> dict:
    p = yaml.safe_load((config.PROMPT_DIR / f"{pid}.yaml").read_text(encoding="utf-8"))
    p["hash"] = sha256(canonical_json({"system": p["system"], "template": p["template"], "version": p["version"]}))
    return p


def _fill(t: str, variables: dict) -> str:
    for k, v in variables.items():
        t = t.replace("{" + k + "}", str(v))
    return t


def _cache() -> dict:
    if config.LLM_CACHE.exists():
        return json.loads(config.LLM_CACHE.read_text(encoding="utf-8"))
    return {}


def _cache_put(key: str, value: dict, origin: str):
    c = _cache()
    c[key] = {"output": value, "origin": origin}
    config.LLM_CACHE.write_text(json.dumps(c, indent=1, ensure_ascii=False), encoding="utf-8")


def cache_key(prompt_hash: str, input_hash: str) -> str:
    return f"{prompt_hash[:16]}:{input_hash[:24]}"


def _post(system: str, user: str) -> str:
    import httpx

    if not config.LLM_API_KEY:
        raise LLMUnavailable("LLM_API_KEY not set")
    if config.LLM_PROVIDER == "anthropic":
        r = httpx.post("https://api.anthropic.com/v1/messages", timeout=30,
                       headers={"x-api-key": config.LLM_API_KEY, "anthropic-version": "2023-06-01",
                                "content-type": "application/json"},
                       json={"model": config.LLM_MODEL, "max_tokens": 800, "temperature": 0, "system": system,
                             "messages": [{"role": "user", "content": user}]})
        r.raise_for_status()
        return "".join(b.get("text", "") for b in r.json()["content"])
    r = httpx.post(config.LLM_BASE_URL.rstrip("/") + "/chat/completions", timeout=30,
                   headers={"Authorization": f"Bearer {config.LLM_API_KEY}"},
                   json={"model": config.LLM_MODEL, "temperature": 0,
                         "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _json_from(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON object in output")
    return json.loads(m.group(0))


def call(pid: str, variables: dict, schema: dict, session=None, actor_id="system") -> dict:
    """Returns {"output": dict, "origin": live|cache|...}. Raises LLMUnavailable when nothing can be produced."""
    if mode() == "off":
        raise LLMUnavailable("LLM_MODE=off")
    p = load_prompt(pid)
    system = _fill(p["system"], variables)
    user = _fill(p["template"], variables)
    in_hash = sha256(system + "\n" + user)
    key = cache_key(p["hash"], in_hash)
    t0 = time.time()
    out, origin = None, None
    cached = _cache().get(key)
    if mode() == "live":
        for attempt in range(2):
            try:
                cand = _json_from(_post(system, user))
                jsonschema.validate(cand, schema)
                out, origin = cand, "live"
                _cache_put(key, out, f"live:{config.LLM_PROVIDER}:{config.LLM_MODEL}")
                break
            except LLMUnavailable:
                break
            except Exception:  # noqa: BLE001 - retry once, then fall back
                continue
    if out is None and cached:
        out, origin = cached["output"], "cache"
    if out is None:
        raise LLMUnavailable("no live response and no cached response")
    if session is not None:
        from core.audit import log

        log(session, f"llm.{pid}", f"prompt:{pid}@v{p['version']}", {"origin": origin,
                                                                     "latency_ms": int((time.time() - t0) * 1000)},
            actor_type="llm", actor_id=actor_id, input_hash=in_hash, output_hash=sha256(canonical_json(out)),
            model_version=config.LLM_MODEL if origin == "live" else (cached or {}).get("origin", origin),
            prompt_hash=p["hash"])
    return {"output": out, "origin": origin, "prompt_hash": p["hash"], "input_hash": in_hash, "cache_key": key}


# ---------------------------------------------------------------- parse_change
def parse_context(session) -> dict:
    from sqlalchemy import select

    from core.db import db_attributes
    from core.models import MasterText, Product, Sku

    prods = [p.product_id + f" ({p.brand} {p.name})" for p in session.execute(select(Product)).scalars()]
    skus = [s.sku_id for s in session.execute(select(Sku)).scalars()]
    attrs = db_attributes(session, skus[0]) if skus else {}
    tids = sorted({m.text_id for m in session.execute(select(MasterText)).scalars()})
    return {"products": ", ".join(prods), "skus": ", ".join(skus),
            "attributes": json.dumps(attrs, sort_keys=True), "text_ids": ", ".join(tids),
            "_skus": skus, "_attrs": attrs, "_tids": tids, "_products": [p.split(" ")[0] for p in prods]}


def validate_change(cr: dict, ctx: dict) -> list[str]:
    errs = []
    try:
        jsonschema.validate(cr, CHANGE_SCHEMA)
    except jsonschema.ValidationError as e:
        return [f"schema: {e.message}"]
    for ch in cr["changes"]:
        if ch["key"] not in ctx["_attrs"]:
            errs.append(f"unknown attribute key '{ch['key']}'")
        sc = ch["scope"]
        if "sku" in sc and sc["sku"] not in ctx["_skus"]:
            errs.append(f"unknown SKU '{sc['sku']}'")
        if "product" in sc and sc["product"] not in ctx["_products"]:
            errs.append(f"unknown product '{sc['product']}'")
        if ch["key"].endswith("_text_id") and ch["new"] not in ctx["_tids"]:
            errs.append(f"unknown master text '{ch['new']}'")
        if ch["key"] == "shelf_life_months" and not str(ch["new"]).isdigit():
            errs.append("shelf_life_months must be an integer")
    return errs


def rule_based_parse(text: str, ctx: dict) -> dict | None:
    """Deterministic fallback used when no LLM output exists (clearly labelled in the UI)."""
    t = text.lower()
    changes = []
    m = re.search(r"shelf[\s-]*life[^0-9]{0,40}?(\d{1,3})\s*(months|month|mo)", t)
    if m:
        changes.append({"scope": {"product": "P-CS"}, "key": "shelf_life_months",
                        "old": ctx["_attrs"].get("shelf_life_months"), "new": m.group(1)})
    if re.search(r"steril\w*\s+(wording|text|statement)", t) or "mt-ster-02" in t:
        changes.append({"scope": {"product": "P-CS"}, "key": "sterilization_text_id",
                        "old": ctx["_attrs"].get("sterilization_text_id"), "new": "MT-STER-02"})
    m = re.search(r"(store|storage)[^0-9]{0,30}(\d{2})\s*°?\s*c", t)
    if m:
        changes.append({"scope": {"product": "P-CS"}, "key": "storage_temp_max_c",
                        "old": ctx["_attrs"].get("storage_temp_max_c"), "new": m.group(2)})
    for ch in changes:
        sm = re.search(r"\b(cs-?\d00)\b", t)
        if sm:
            ch["scope"] = {"sku": sm.group(1).upper().replace("CS", "CS-").replace("--", "-")}
    if not changes:
        return None
    return {"source": "product", "reason": text.strip(), "changes": changes}


def parse_change(text: str, session=None, actor_id="system") -> dict:
    """text -> {"change_request": dict, "origin": ..., "errors": [...]}. Nothing runs until the user confirms."""
    ctx = parse_context(session)
    variables = {k: v for k, v in ctx.items() if not k.startswith("_")} | {"text": text.strip()}
    cr, origin, errors = None, None, []
    try:
        res = call("parse_change", variables, {"type": "object"}, session=session, actor_id=actor_id)
        out = res["output"]
        origin = res["origin"]
        if "error" in out:
            errors.append(out["error"])
        else:
            cr = out
    except LLMUnavailable as e:
        origin = f"unavailable ({e})"
    if cr is None and mode() != "off":
        cr = rule_based_parse(text, ctx)
        if cr:
            origin = "rule-based fallback (no LLM output available)"
    if cr is not None:
        errors += validate_change(cr, ctx)
    return {"change_request": cr if not errors else cr, "origin": origin, "errors": errors,
            "llm_mode": mode()}


# ---------------------------------------------------------------- explain_finding (restricted)
def template_explanation(f: dict) -> dict:
    req = f.get("requirement_text") or "the internal labeling control"
    return {"explanation": f"{f['message']} The applicable requirement ({f.get('clause_ref') or f['rule_id']}) "
                           f"states: \"{req}\".", "suggested_fix": f.get("suggested_fix") or "Review the element.",
            "quote": req, "origin": "template"}


def explain_finding(f: dict, session=None) -> dict:
    if not f.get("requirement_text"):
        return template_explanation(f)
    try:
        res = call("explain_finding", {k: f.get(k) or "" for k in ("message", "rule_id", "severity", "clause_ref",
                                                                     "requirement_text", "evidence_text")},
                   EXPLAIN_SCHEMA, session=session)
        out = res["output"]
        # grounding: the quote must exist verbatim in the requirement row
        if out.get("quote") and out["quote"].strip().strip('"') in f["requirement_text"]:
            return out | {"origin": res["origin"]}
        return template_explanation(f) | {"origin": "template (LLM quote not grounded - discarded)"}
    except (LLMUnavailable, Exception):  # noqa: BLE001
        return template_explanation(f)


def semantic_check(approved: str, printed: str, language: str, session=None) -> dict:
    from engines.rules.content import invariant_diffs

    d = invariant_diffs(approved, printed, language)
    if d:
        return {"verdict": "different", "reason": "; ".join(d), "origin": "deterministic"}
    if approved.strip() == printed.strip():
        return {"verdict": "equivalent", "reason": "identical", "origin": "deterministic"}
    try:
        res = call("semantic_check", {"language": language, "approved": approved, "printed": printed},
                   SEMANTIC_SCHEMA, session=session)
        return res["output"] | {"origin": res["origin"]}
    except (LLMUnavailable, Exception):  # noqa: BLE001
        return {"verdict": "unsure", "reason": "no LLM available; routed to a human", "origin": "fallback"}


def seed_demo_cache(session) -> int:
    """Hand-written demo fixtures for the hero sentences so LLM_MODE=cached works offline. These are NOT model
    outputs; they are marked origin='hand-written demo fixture' and are replaced by real outputs when run live."""
    ctx = parse_context(session)
    variables = {k: v for k, v in ctx.items() if not k.startswith("_")}
    p = load_prompt("parse_change")
    fixtures = {
        "Extend CardioSafe shelf life to 36 months and update the sterilization wording":
            {"source": "product", "reason": "Stability study supports 36-month shelf life; sterilization wording "
                                            "updated to MT-STER-02",
             "changes": [{"scope": {"product": "P-CS"}, "key": "shelf_life_months", "old": "24", "new": "36"},
                         {"scope": {"product": "P-CS"}, "key": "sterilization_text_id", "old": "MT-STER-01",
                          "new": "MT-STER-02"}]},
        "extend CardioSafe shelf life to 36 months":
            {"source": "product", "reason": "Extend shelf life to 36 months",
             "changes": [{"scope": {"product": "P-CS"}, "key": "shelf_life_months", "old": "24", "new": "36"}]},
    }
    n = 0
    for sentence, out in fixtures.items():
        v = variables | {"text": sentence}
        system = _fill(p["system"], v)
        user = _fill(p["template"], v)
        key = cache_key(p["hash"], sha256(system + "\n" + user))
        if key not in _cache():
            _cache_put(key, out, "hand-written demo fixture")
            n += 1
    return n


DEMO_SENTENCES = ["Extend CardioSafe shelf life to 36 months and update the sterilization wording",
                  "extend CardioSafe shelf life to 36 months"]
_ = Path
