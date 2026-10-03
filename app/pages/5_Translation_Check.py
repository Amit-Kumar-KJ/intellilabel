"""Translation Check (Phase 11.3 / 12.2 page 6)."""
import pandas as pd
import streamlit as st
from common import api, badge, footer, setup

setup("Translation Check", ":material/translate:")
st.markdown("Checks: **glossary** (approved term, no forbidden variant) · **invariants** (numbers, units, negations) "
            "· **completeness** (sentence count). FAIL = invariant broken, WARNING = glossary or similarity.")
EXAMPLES = {
    "Correct (DE warning)": ("MT-WARN-01", "de", "Do not expand the stent more than 0.5 mm above its nominal diameter.",
                             "Den Stent nicht mehr als 0,5 mm über den Nenndurchmesser hinaus aufdehnen."),
    "Number changed": ("MT-WARN-01", "de", "Do not expand the stent more than 0.5 mm above its nominal diameter.",
                       "Den Stent nicht mehr als 0,6 mm über den Nenndurchmesser hinaus aufdehnen."),
    "Negation dropped": ("MT-DAMAGE-01", "fr", "Do not use if package is damaged.",
                         "Utiliser si l'emballage est endommagé."),
    "Glossary violation": ("MT-REUSE-01", "de", "Single use only. Do not reuse.",
                           "Nur zum Einmalgebrauch. Nicht erneut benutzen."),
    "Missing sentence": ("MT-STOR-01", "fr", "Store below 25 °C. Keep dry.", "Conserver à moins de 25 °C."),
}
ex = st.selectbox("Example", list(EXAMPLES))
tid, lang, src, tr = EXAMPLES[ex]
c1, c2 = st.columns(2)
src = c1.text_area("English source", src, height=100)
tr = c2.text_area("Translation", tr, height=100)
c = st.columns(3)
lang = c[0].selectbox("Language", ["de", "fr"], index=["de", "fr"].index(lang))
tid = c[1].text_input("Master text id (optional)", tid)
if st.button("Check translation", type="primary"):
    r = api("POST", "/translations/check", json={"source_en": src, "translation": tr, "language": lang,
                                                 "text_id": tid or None})
    st.markdown(f"Result: {badge(r['status'])}", unsafe_allow_html=True)
    if r["problems"]:
        st.dataframe(pd.DataFrame(r["problems"]), hide_index=True, width="stretch")

m = api("GET", "/metrics").get("translation_results")
if m:
    st.divider()
    st.markdown("##### Measured on the seeded translation set (Tier 1, seen)")
    st.dataframe(pd.DataFrame(m["by_error_type"]), hide_index=True)
footer()
