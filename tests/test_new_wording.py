from ltlaw.today import _quoted_new_wording

LAW = """1 straipsnis. Įstatymo papildymas 12¹ straipsniu
Papildyti Įstatymą 12¹ straipsniu:
„12¹ straipsnis. Kita
1. Tekstas.“

3 straipsnis. Lietuvos Respublikos pavyzdžio įstatymo Nr. XII-1 nauja redakcija
Pakeisti Lietuvos Respublikos pavyzdžio įstatymą Nr. XII-1 ir jį išdėstyti taip:
„LIETUVOS RESPUBLIKOS
PAVYZDŽIO ĮSTATYMAS

1 straipsnis. Paskirtis
1. Šis įstatymas nustato „kabutėse“ dalykus.

2 straipsnis. Įsigaliojimas
Taikoma.

Lietuvos Respublikos pavyzdžio
įstatymo priedas
ĮGYVENDINAMI ES TEISĖS AKTAI
1. Direktyva.
––––––––––––“.

4 straipsnis. Įstatymo įsigaliojimas
Šis įstatymas įsigalioja 2025 m. spalio 1 d.
"""


def test_quoted_new_wording_is_the_whole_act_without_its_annex():
    q = _quoted_new_wording(LAW, 3)
    assert q.startswith("LIETUVOS RESPUBLIKOS")
    assert "2 straipsnis. Įsigaliojimas\nTaikoma." in q
    assert "priedas" not in q and "4 straipsnis. Įstatymo įsigaliojimas" not in q


def test_no_quoted_act_without_a_rewrite_article():
    assert _quoted_new_wording(LAW, None) is None
    assert _quoted_new_wording(LAW, 1) is None  # article 1 adds one article: not a whole act
