# Blind holdout procedure (Phase 4.8 / Tier 2)

For a teammate or friend who did **not** build the detectors. Run only after `git tag eval-freeze`.

1. `make data` (or `python run.py data`) so the clean labels exist in `data/generated/clean/`.
2. Pick 20-30 clean label folders you have not looked at before.
3. For each, open `label.pdf` in an editor that keeps real text (e.g. LibreOffice Draw or Inkscape) and introduce
   1-3 defects, combining types and placing them where the generator would not, for example:
   - change one digit of the GTIN, lot or date in the human-readable UDI only;
   - delete or move the manufacturer block, EC REP block or a symbol;
   - edit a warning number or delete "not / nicht / ne ... pas" in one language;
   - replace an approved term with a synonym (see `data/master/glossary.csv` forbidden variants);
   - change the revision code, the date format, or cover part of the Data Matrix.
4. Save each as `data/holdout/<new_id>/label.pdf` and record the truth in `data/holdout/holdout_truth.json`
   using the same schema as `data/generated/ground_truth.json` (defect type, element, approximate bbox in mm,
   expected rule, severity).
5. Hand the folder to the team. Results go in a separate "Tier 2" column; any fix made afterwards is reported as
   "after fix", never silently.
