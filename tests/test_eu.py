from ltlaw.eu import find


def celex(text):
    return [r.celex for r in find(text)]


def test_directive_old_and_new_style():
    assert celex("1991 m. birželio 25 d. Tarybos direktyva 91/383/EEB, pateikianti") == ["31991L0383"]
    assert celex("Europos Parlamento ir Tarybos direktyva (ES) 2019/944 dėl elektros energijos") == ["32019L0944"]
    assert celex("Europos Parlamento ir Tarybos direktyva 2009/72/EB") == ["32009L0072"]


def test_regulation_number_order():
    assert celex("Tarybos reglamentas (EB) Nr. 338/97 dėl laukinės faunos") == ["31997R0338"]
    assert celex("Komisijos reglamentas (ES) Nr. 651/2014") == ["32014R0651"]
    assert celex("Europos Parlamento ir Tarybos reglamentas (ES) 2016/679") == ["32016R0679"]


def test_framework_decision_and_decision():
    assert celex("Tarybos pagrindų sprendimas 2008/913/TVR dėl kovos") == ["32008F0913"]
    assert celex("Komisijos sprendimas 2010/75/ES") == ["32010D0075"]


def test_national_decision_not_taken_and_dedup():
    assert celex("savivaldybės tarybos sprendimas 12/2019") == []
    assert celex("direktyva 2019/944 … direktyvos 2019/944") == ["32019L0944"]


def test_old_regulation_without_nr():
    assert celex("Komisijos reglamentas (EEB) 3649/92 dėl supaprastinto") == ["31992R3649"]
