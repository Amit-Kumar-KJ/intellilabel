"""Phase 3: builds derived master files (packaging-level GTINs) from a fixed seed."""
from __future__ import annotations

import csv

from core import gs1
from core.config import MASTER_DIR
from core.master import skus

# Indicator digit per packaging level (GS1 packaging indicator 1-8 for higher levels).
INDICATOR = {"pouch": 0, "carton": 1, "shipper": 5}
QUANTITY = {"pouch": 1, "carton": 1, "shipper": 10}
# Fictional company prefix inside the GS1 restricted-circulation range 02x (verify): cannot collide with
# real trade items.
COMPANY = "0298765"


def build_packaging():
    rows = []
    for i, sku_id in enumerate(sorted(skus())):
        item = f"{(i + 1) * 101:05d}"  # 5-digit item reference -> 12-digit GTIN-13 body
        for level, ind in INDICATOR.items():
            gtin = gs1.make_gtin14(ind, COMPANY + item)
            assert gs1.is_valid_gtin(gtin)
            rows.append({"sku_id": sku_id, "packaging_level": level, "gtin14": gtin, "quantity": QUANTITY[level]})
    with open(MASTER_DIR / "packaging.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["sku_id", "packaging_level", "gtin14", "quantity"])
        w.writeheader()
        w.writerows(rows)
    return rows


if __name__ == "__main__":
    for r in build_packaging():
        print(r)
