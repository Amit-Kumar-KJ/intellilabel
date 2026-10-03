"""GS1 utilities: GTIN check digits and GS1 element string build/parse (Phase 3.3).

Application identifiers used: (01) GTIN-14, (11) production date YYMMDD,
(17) expiry YYMMDD, (10) batch/lot (variable, <=20), (21) serial (variable, <=20).
Variable-length AIs are terminated with the GS (FNC1) separator \x1d unless last.
"""
from __future__ import annotations

import re

GS = "\x1d"
FIXED = {"01": 14, "11": 6, "17": 6}
VARIABLE = {"10": 20, "21": 20}
# GS1 restricted circulation GTIN-13 prefixes 020-029 (verify against GS1 General Specifications)
RESTRICTED_PREFIX = "02"


def check_digit(body: str) -> int:
    """Mod-10 check digit for a GTIN body (all digits except the check digit)."""
    if not body.isdigit():
        raise ValueError(f"GTIN body must be digits: {body!r}")
    total = 0
    for i, ch in enumerate(reversed(body)):
        total += int(ch) * (3 if i % 2 == 0 else 1)
    return (10 - total % 10) % 10


def make_gtin14(indicator: int, company_item: str) -> str:
    """indicator (0-8) + 12 digit GTIN-13 body -> GTIN-14 with check digit."""
    body = f"{indicator}{company_item}"
    if len(body) != 13:
        raise ValueError("indicator + company/item must be 13 digits")
    return body + str(check_digit(body))


def is_valid_gtin(gtin: str) -> bool:
    if not gtin or not gtin.isdigit() or len(gtin) not in (8, 12, 13, 14):
        return False
    return check_digit(gtin[:-1]) == int(gtin[-1])


def build_element_string(gtin: str, expiry_yymmdd: str | None = None, lot: str | None = None,
                         serial: str | None = None, prod_yymmdd: str | None = None) -> str:
    """Raw GS1 element string as encoded in the Data Matrix (no parentheses)."""
    parts = [("01", gtin)]
    if prod_yymmdd:
        parts.append(("11", prod_yymmdd))
    if expiry_yymmdd:
        parts.append(("17", expiry_yymmdd))
    if lot:
        parts.append(("10", lot))
    if serial:
        parts.append(("21", serial))
    out = ""
    for i, (ai, val) in enumerate(parts):
        out += ai + val
        if ai in VARIABLE and i < len(parts) - 1:
            out += GS
    return out


def build_hri(gtin: str, expiry_yymmdd=None, lot=None, serial=None, prod_yymmdd=None) -> str:
    """Human readable interpretation: (01)...(17)...(10)..."""
    s = f"(01){gtin}"
    if prod_yymmdd:
        s += f"(11){prod_yymmdd}"
    if expiry_yymmdd:
        s += f"(17){expiry_yymmdd}"
    if lot:
        s += f"(10){lot}"
    if serial:
        s += f"(21){serial}"
    return s


def parse_element_string(data: str) -> dict:
    """Parse a raw GS1 element string (with optional leading ]d2 / FNC1) into {ai: value}."""
    s = data
    for prefix in ("]d2", "]C1", "]Q3", GS):
        if s.startswith(prefix):
            s = s[len(prefix):]
    out: dict[str, str] = {}
    i = 0
    while i < len(s):
        ai = s[i:i + 2]
        i += 2
        if ai in FIXED:
            n = FIXED[ai]
            out[ai] = s[i:i + n]
            i += n
        elif ai in VARIABLE:
            end = s.find(GS, i)
            end = len(s) if end == -1 else end
            out[ai] = s[i:end][: VARIABLE[ai]]
            i = end + 1
        else:
            out.setdefault("_unparsed", "")
            out["_unparsed"] += ai + s[i:]
            break
    return out


HRI_RE = re.compile(r"\((\d{2})\)([^()\s]+)")


def parse_hri(text: str) -> dict:
    """Parse '(01)0...(17)...(10)...' plain text into {ai: value}."""
    return {ai: val for ai, val in HRI_RE.findall(text.replace(" ", ""))}
