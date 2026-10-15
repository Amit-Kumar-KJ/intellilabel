"""Regulatory monitor: detects changes on watched pages and creates PROPOSALS.
Only approve() can touch requirements.csv, and it needs a named human reviewer."""
import argparse
import difflib
import hashlib
import json
import re
import urllib.error
import urllib.request
from datetime import date, datetime
from html import unescape
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "data" / "regulatory"
WATCHLIST = REG / "watchlist.csv"
SNAP_DIR = REG / "monitor" / "snapshots"
STATE = REG / "monitor" / "state.json"
PROPOSALS = REG / "monitor" / "proposals.json"
REQ_CSV = REG / "requirements.csv"
REQ_COLS = ["requirement_id", "market", "regulation", "section", "label_element",
            "requirement_text", "obligation", "applies_if", "packaging_levels",
            "rule_id", "source_url", "retrieved_on", "verified_by"]
DEMO_SENTENCE = ("DEMO ONLY simulated update: the label shall additionally state "
                 "that the device is a medical device.")


def _load(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _ecfr_text(data):
    """Turn an eCFR amendment log (JSON) into one readable sentence per version."""
    lines = []
    for v in data["content_versions"]:
        name = re.sub(r"\s+", " ", v.get("name", ""))
        name = re.sub(r"[.;]\s+", ", ", name).rstrip(". ")
        flags = "substantive" if v.get("substantive") else "non-substantive"
        if v.get("removed"):
            flags += ", removed"
        lines.append(f"{v.get('title', '?')} CFR {v.get('identifier', '?')}: version {v.get('date')}, "
                     f"amended {v.get('amendment_date')}, issued {v.get('issue_date')}, {flags}, {name}.")
    text = " ".join(sorted(lines))
    if len(text) < 500:
        raise ValueError("eCFR log too short (unexpected response)")
    return text


def fetch_text(url, ignore_regex=""):
    """Download a page and reduce it to plain, whitespace-normalised text."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (IntelliLabel research prototype)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        page = r.read().decode("utf-8", errors="ignore")
    try:                                           # official eCFR amendment logs are JSON
        data = json.loads(page)
    except ValueError:
        data = None
    if isinstance(data, dict) and "content_versions" in data:
        return _ecfr_text(data)
    page = re.sub(r"(?is)<(script|style|nav|header|footer)\b.*?</\1>", " ", page)
    text = unescape(re.sub(r"(?s)<[^>]+>", " ", page))
    if ignore_regex:
        text = re.sub(ignore_regex, " ", text)   # remove known noise (dates, banners)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) < 500:
        raise ValueError("page text too short (blocked or empty page)")
    return text


def sentence_diff(old, new, limit=10):
    """Return (added, removed) sentences between two versions of a page."""
    def split(t):
        return [s.strip() for s in re.split(r"(?<=[.;])\s+", t) if len(s.strip()) > 20]
    a, b = split(old), split(new)
    added, removed = [], []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op in ("replace", "delete"):
            removed += a[i1:i2]
        if op in ("replace", "insert"):
            added += b[j1:j2]
    return added[:limit], removed[:limit]


def _new_proposal(src, added, removed, old_hash, new_hash, simulated):
    props = _load(PROPOSALS, [])
    pid = f"PROP-{len(props) + 1:04d}"
    props.append({"proposal_id": pid, "status": "PENDING", "simulated": simulated,
                  "source_id": src["source_id"], "source_name": src["name"],
                  "market": "ALL" if src["market"] == "GLOBAL" else src["market"], "url": src["url"], "detected_on": _now(),
                  "added": added, "removed": removed, "old_hash": old_hash,
                  "new_hash": new_hash, "ai_draft": None, "draft_row": None,
                  "reviewer": "", "decision_note": ""})
    _save(PROPOSALS, props)
    return pid


def check_source(src, new_text=None, simulated=False):
    """Compare the current page text with the saved snapshot; propose if it changed."""
    sid = src["source_id"]
    snap = SNAP_DIR / f"{sid}.txt"
    state = _load(STATE, {})
    if new_text is None:
        new_text = fetch_text(src["url"], src.get("ignore_regex", ""))
    entry = state.setdefault(sid, {})
    entry["last_checked"] = _now()
    entry["error"] = ""
    if not snap.exists():                          # first run: save baseline, no alert
        snap.parent.mkdir(parents=True, exist_ok=True)
        snap.write_text(new_text, encoding="utf-8")
        entry["hash"] = _hash(new_text)
        _save(STATE, state)
        return f"{sid}: baseline saved ({len(new_text)} chars)"
    old_text = snap.read_text(encoding="utf-8")
    if _hash(old_text) == _hash(new_text):
        _save(STATE, state)
        return f"{sid}: no change"
    added, removed = sentence_diff(old_text, new_text)
    if not added and not removed:
        _save(STATE, state)
        return f"{sid}: text differs but no meaningful sentence change"
    pid = _new_proposal(src, added, removed, _hash(old_text), _hash(new_text), simulated)
    if not simulated:                              # a simulation never replaces the baseline
        snap.write_text(new_text, encoding="utf-8")
        entry["hash"] = _hash(new_text)
    _save(STATE, state)
    return f"{sid}: CHANGE DETECTED -> {pid}"


def _watchlist():
    return pd.read_csv(WATCHLIST, dtype=str, keep_default_na=False).to_dict("records")


def run_check():
    """Check every source in the watchlist. Returns a list of status lines."""
    lines = []
    for src in _watchlist():
        try:
            lines.append(check_source(src))
        except Exception as e:                     # one failing source must not stop the rest
            state = _load(STATE, {})
            state.setdefault(src["source_id"], {})["error"] = str(e)[:200]
            _save(STATE, state)
            lines.append(f"{src['source_id']}: FAILED ({e})")
    return lines


def simulate(source_id):
    """Demo helper: pretend the page gained a new sentence. Flagged as simulated."""
    src = next(r for r in _watchlist() if r["source_id"] == source_id)
    snap = SNAP_DIR / f"{source_id}.txt"
    if not snap.exists():
        raise SystemExit("Run 'check' once first to create a baseline.")
    fake = snap.read_text(encoding="utf-8").rstrip(". ") + ". " + DEMO_SENTENCE
    return check_source(src, new_text=fake, simulated=True)


def list_proposals(status=None):
    props = _load(PROPOSALS, [])
    return [p for p in props if status is None or p["status"] == status]


def _find(props, prop_id):
    for p in props:
        if p["proposal_id"] == prop_id:
            return p
    raise ValueError(f"{prop_id} not found")


def next_req_id(market, df):
    nums = [int(m.group(1)) for rid in df["requirement_id"]
            if (m := re.fullmatch(rf"REQ-{market}-(\d+)", rid))]
    return f"REQ-{market}-{max(nums, default=0) + 1:03d}"


def approve(prop_id, row, reviewer):
    """Human approval. Real proposals append a row to requirements.csv.
    Simulated proposals never touch the rulebook; the row is stored for the demo only."""
    props = _load(PROPOSALS, [])
    p = _find(props, prop_id)
    if p["status"] != "PENDING":
        raise ValueError(f"{prop_id} is already {p['status']}")
    required = ["market", "regulation", "section", "label_element", "requirement_text",
                "obligation", "applies_if", "packaging_levels", "rule_id"]
    missing = [k for k in required if not str(row.get(k, "")).strip()]
    if missing:
        raise ValueError(f"missing fields: {missing}")
    full = {c: "" for c in REQ_COLS}
    full.update({k: row[k].strip() for k in required})
    full.update({"source_url": p["url"], "retrieved_on": date.today().isoformat(),
                 "verified_by": reviewer})
    if p["simulated"]:
        full["requirement_id"] = f"DEMO-{prop_id}"
        p["status"] = "APPROVED_DEMO"
    else:
        df = pd.read_csv(REQ_CSV, dtype=str, keep_default_na=False)
        if list(df.columns) != REQ_COLS:
            raise ValueError("requirements.csv columns changed; refusing to write")
        full["requirement_id"] = next_req_id(full["market"], df)
        out = pd.concat([df, pd.DataFrame([full])[REQ_COLS]], ignore_index=True)
        out.to_csv(REQ_CSV, index=False)
        p["status"] = "APPROVED"
    p["draft_row"], p["reviewer"] = full, reviewer
    _save(PROPOSALS, props)
    return full


def reject(prop_id, reviewer, note):
    props = _load(PROPOSALS, [])
    p = _find(props, prop_id)
    if p["status"] != "PENDING":
        raise ValueError(f"{prop_id} is already {p['status']}")
    p.update(status="REJECTED", reviewer=reviewer, decision_note=note)
    _save(PROPOSALS, props)


def send_to_scenario_b(prop_id, user="regulatory_affairs_user"):
    """Send an APPROVED proposal to the app as a regulatory change request (Scenario B)."""
    import os
    props = _load(PROPOSALS, [])
    p = _find(props, prop_id)
    if p["status"] not in ("APPROVED", "APPROVED_DEMO") or not p["draft_row"]:
        raise ValueError(f"{prop_id} is {p['status']}; only approved proposals can be sent")
    if p.get("scenario_b"):
        raise ValueError(f"{prop_id} was already sent")
    body = {"source": "regulatory",
            "reason": f"Regulatory update from {p['source_name']} ({prop_id})",
            "changes": [], "requirement": dict(p["draft_row"]), "user": user}
    base = os.getenv("INTELLILABEL_API", "http://127.0.0.1:8000")
    req = urllib.request.Request(base + "/change-requests", data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            resp = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise ValueError(f"The app API refused the request (HTTP {e.code}): "
                         f"{e.read().decode('utf-8', 'ignore')[:500]}")
    except urllib.error.URLError:
        raise ValueError("Cannot reach the app API. Is 'make demo' running?")
    p["scenario_b"] = resp
    _save(PROPOSALS, props)
    return resp


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Regulatory monitor")
    ap.add_argument("cmd", choices=["check", "simulate", "list"])
    ap.add_argument("source_id", nargs="?")
    a = ap.parse_args()
    if a.cmd == "check":
        print("\n".join(run_check()))
    elif a.cmd == "simulate":
        print(simulate(a.source_id or "ec_udi"))
    else:
        for p in list_proposals():
            tag = " (SIMULATED)" if p["simulated"] else ""
            print(p["proposal_id"], p["status"], p["source_id"], f"+{len(p['added'])}/-{len(p['removed'])}{tag}")
