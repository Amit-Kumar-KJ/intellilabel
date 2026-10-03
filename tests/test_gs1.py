from core import gs1


def test_check_digit_known_values():
    # GS1 example GTIN-13 4006381333931 and GTIN-14 with indicator
    assert gs1.is_valid_gtin("4006381333931")
    assert gs1.check_digit("400638133393") == 1
    g = gs1.make_gtin14(1, "029876500101")
    assert len(g) == 14 and gs1.is_valid_gtin(g)


def test_invalid_gtin_detected():
    g = gs1.make_gtin14(0, "029876500101")
    bad = g[:-1] + str((int(g[-1]) + 1) % 10)
    assert not gs1.is_valid_gtin(bad)


def test_element_string_roundtrip():
    raw = gs1.build_element_string("10298765001012", "280915", "A12345")
    ais = gs1.parse_element_string(raw)
    assert ais == {"01": "10298765001012", "17": "280915", "10": "A12345"}
    hri = gs1.build_hri("10298765001012", "280915", "A12345")
    assert gs1.parse_hri(hri) == ais


def test_variable_field_separator():
    raw = gs1.build_element_string("10298765001012", "280915", "LOT1", serial="S99")
    assert gs1.GS in raw
    assert gs1.parse_element_string(raw)["21"] == "S99"
