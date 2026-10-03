"""Results (Phase 13 / 12.2 page 9): benchmark tables from eval/results/."""
import pandas as pd
import streamlit as st
from common import api, footer, setup

setup("Results", ":material/query_stats:")
m = api("GET", "/metrics")
if "compliance_tier1" not in m:
    st.info("No benchmark results yet. Run `make bench` (or `python -m eval.run_benchmark`).")
    st.stop()

t = m["compliance_tier1"]
st.markdown("##### Compliance engine - Tier 1 (seen: seeded defects from Phase 4)")
c = st.columns(4)
c[0].metric("Defective labels", t["n_defective"])
c[1].metric("Macro recall", f"{t['macro_recall']:.1%}")
c[2].metric("Macro precision", f"{t['macro_precision']:.1%}")
c[3].metric("Clean-label false-positive rate", f"{t['clean_fp_rate']:.1%}", help=f"{t['n_clean']} untouched labels")
st.dataframe(pd.DataFrame(t["per_defect"]), hide_index=True, width="stretch")
st.caption("A finding is a true positive when its rule id matches the expected rule and its evidence box overlaps "
           "the truth box (IoU ≥ 0.3) or names the same element. Tier 1 is an upper bound: detectors were built "
           "against these defects.")

if "robustness" in m:
    st.markdown("##### Robustness (raster / OCR path on degraded images)")
    st.dataframe(pd.DataFrame(m["robustness"]["rows"]), hide_index=True, width="stretch")
if "diff_results" in m:
    st.markdown("##### Diff engine")
    d = m["diff_results"]
    c = st.columns(3)
    c[0].metric("Seeded edits detected", f"{d['detection_rate']:.1%}")
    c[1].metric("Correctly classified", f"{d['classification_rate']:.1%}")
    c[2].metric("False alarms on noise-only pairs", d["noise_false_alarms"])
    st.dataframe(pd.DataFrame(d["by_type"]), hide_index=True)
if "translation_results" in m:
    st.markdown("##### Translation validator")
    st.dataframe(pd.DataFrame(m["translation_results"]["by_error_type"]), hide_index=True)
if "ledger_results" in m:
    st.markdown("##### Audit ledger tamper detection")
    st.write(m["ledger_results"])
if "risk_sensitivity" in m:
    st.markdown("##### Risk weights sensitivity (±20% per weight)")
    st.dataframe(pd.DataFrame(m["risk_sensitivity"]["rows"]), hide_index=True)
st.markdown("##### Limitations")
st.markdown("- Synthetic labels and a fictional manufacturer; Tier 2 (blind holdout) and Tier 3 (photographed "
            "labels) must be run by the team after `git tag eval-freeze`.\n- Simplified symbol glyphs.\n"
            "- Regulatory rows are UNVERIFIED until checked against the sources.")
footer()
