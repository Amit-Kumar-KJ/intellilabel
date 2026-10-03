from engines.translation import check


def test_pass_and_fail_cases():
    src = "Do not expand the stent more than 0.5 mm above its nominal diameter."
    ok = "Den Stent nicht mehr als 0,5 mm über den Nenndurchmesser hinaus aufdehnen."
    assert check(src, ok, "de", "MT-WARN-01")["status"] == "PASS"
    assert check(src, ok.replace("0,5", "0,6"), "de", "MT-WARN-01")["status"] == "FAIL"
    assert check(src, ok.replace("nicht ", ""), "de", "MT-WARN-01")["status"] == "FAIL"


def test_glossary_warning():
    r = check("Single use only. Do not reuse.", "Nur zum Einmalgebrauch. Nicht erneut benutzen.", "de", "MT-REUSE-01")
    assert r["status"] == "WARNING"


def test_missing_sentence_fails():
    r = check("Store below 25 °C. Keep dry.", "Conserver à moins de 25 °C.", "fr", "MT-STOR-01")
    assert r["status"] == "FAIL"
