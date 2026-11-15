from ltlaw.numbers import Num, Sequence, from_roman, to_roman


def decode(tokens):
    s = Sequence()
    return [s.next(t).label() for t in tokens]


def test_superscript_after_its_base():
    assert decode(["20", "21", "211", "22"]) == ["20", "21", "21-1", "22"]


def test_real_211_after_210():
    assert decode(["209", "210", "211", "212"]) == ["209", "210", "211", "212"]


def test_two_superscripts_in_a_row():
    assert decode(["21", "211", "212", "22"]) == ["21", "21-1", "21-2", "22"]


def test_civil_code_dotted():
    assert decode(["6.228", "6.2281", "6.2282", "6.229"]) == ["6.228", "6.228-1", "6.228-2", "6.229"]


def test_civil_code_book_change():
    assert decode(["1.138", "2.1", "2.2"]) == ["1.138", "2.1", "2.2"]


def test_explicit_superscript_from_etar():
    assert decode(["21", "21-1", "22"]) == ["21", "21-1", "22"]


def test_parts_with_superscript():
    # article parts: "3." then flattened "31." (3¹) then "4."
    assert decode(["1", "2", "3", "31", "4"]) == ["1", "2", "3", "3-1", "4"]


def test_backwards_is_reported_not_hidden():
    s = Sequence()
    for t in ["5", "6", "3"]:
        s.next(t)
    assert s.ambiguous == [("3", Num(0, 3))]


def test_roman_chapters():
    s = Sequence()
    assert [s.next(t).label(roman=True) for t in ["XVIII", "XVIII1", "XIX", "XIX1", "XX"]] == \
        ["XVIII", "XVIII-1", "XIX", "XIX-1", "XX"]
    assert from_roman("XIX") == 19 and to_roman(49) == "XLIX"


def test_pretty_superscript():
    assert Num(6, 228, 1).pretty() == "6.228¹" and Num(0, 21, 12).pretty() == "21¹²"


def test_heading_sentence_case():
    from ltlaw.render import sentence_case as c
    assert c("PVM TARIFAI") == "PVM tarifai"
    assert c("ĮGYVENDINAMI EUROPOS SĄJUNGOS TEISĖS AKTAI") == "Įgyvendinami Europos Sąjungos teisės aktai"
    assert c("BENDRosios NUOSTATos") == "Bendrosios nuostatos"
    assert c("Šengeno erdvės taisyklės") == "Šengeno erdvės taisyklės"  # normal titles untouched
