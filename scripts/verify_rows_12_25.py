import pandas as pd

PATH = "data/regulatory/requirements.csv"
VERIFIER = "Siddhant"
TODAY = "2026-10-06"
APPLY_PACKAGING = False  # set True after the team agrees shippers get no UDI

# Confirmed section for each row
SECTIONS = {
    "REQ-EU-001": "Annex I 23.2(a)",
    "REQ-EU-002": "Annex I 23.2(b)",
    "REQ-EU-003": "Annex I 23.2(c)",
    "REQ-EU-004": "Annex I 23.2(d)",
    "REQ-EU-005": "Article 13(3)",
    "REQ-EU-006": "Annex I 23.2(g)",
    "REQ-EU-007": "Annex I 23.2(h); Article 27(4)",
    "REQ-EU-008": "Article 27(3); Annex VI Part C 2.4, 3.8",
    "REQ-EU-009": "Annex VI Part C 3.5",
    "REQ-EU-010": "Annex I 23.2(i)",
    "REQ-EU-011": "Annex I 23.2(k)",
    "REQ-EU-012": "Annex I 23.2(l)",
    "REQ-EU-013": "Annex I 23.2(m)",
    "REQ-EU-014": "Annex I 23.2(n)",
}
# UDI rows: shipping containers are exempt (Art 27(4), Annex VI Part C 3.2)
UDI_ROWS = ["REQ-EU-007", "REQ-EU-008", "REQ-EU-009"]

# Read as text so blank cells stay blank
df = pd.read_csv(PATH, dtype=str, keep_default_na=False)

for req_id, section in SECTIONS.items():
    row = df["requirement_id"] == req_id
    assert row.sum() == 1, f"{req_id} not found exactly once"
    df.loc[row, "section"] = section
    df.loc[row, "retrieved_on"] = TODAY
    df.loc[row, "verified_by"] = VERIFIER

if APPLY_PACKAGING:
    df.loc[df["requirement_id"].isin(UDI_ROWS), "packaging_levels"] = "pouch|carton"

df.to_csv(PATH, index=False)
print("updated", len(SECTIONS), "rows")