"""Constitutional Court rulings not yet noted in a consolidation (ACCURACY B3): operative part, subjects, dates."""
from ltlaw import currency
from ltlaw.currency import ruling_effective, ruling_operative, ruling_targets
from ltlaw.parse import parse


def op(s: str) -> str:
    return ruling_operative("… Konstitucinis Teismas\nnutaria:\n" + s + "\nŠis Konstitucinio Teismo nutarimas yra galutinis ir neskundžiamas.")


def test_present_conflict_names_the_article():
    o = op("Pripažinti, kad Lietuvos Respublikos bausmių vykdymo kodekso 83 straipsnio 3 punktas (2024 m. gegužės 7 d. "
           "redakcija, TAR, 2024-05-13, Nr. 8758) prieštarauja konstituciniam teisinės valstybės principui.")
    assert ruling_targets(o, "bausmių vykdymo kodekso") == ["83"]


def test_no_conflict_or_past_wording_changes_nothing():
    o = op("Pripažinti, kad Lietuvos Respublikos darbo kodekso 217 straipsnio 3 dalis (2017 m. birželio 6 d. redakcija; "
           "TAR, 2017-06-14, Nr. 10021) neprieštarauja Lietuvos Respublikos Konstitucijai.")
    assert ruling_targets(o, "darbo kodekso") is None
    o = op("1. Pripažinti, kad Lietuvos Respublikos žemės įstatymo 30 straipsnio 9 dalis (2010 m. birželio 18 d. redakcija) "
           "tiek, kiek pagal ją negalėjo būti atidalijami areštuoti žemės sklypai, prieštaravo Lietuvos Respublikos "
           "Konstitucijos 23 straipsnio 1 daliai. 2. Pripažinti, kad Lietuvos Respublikos žemės įstatymo (2022 m. birželio "
           "30 d. redakcija) 29 straipsnio 9 dalis tiek, kiek pagal ją negali būti atidalijami areštuoti žemės sklypai, "
           "prieštarauja Lietuvos Respublikos Konstitucijos 23 straipsnio 1 daliai.")
    assert ruling_targets(o, "žemės įstatymo") == ["29"]  # 30: an old wording ("prieštaravo")
    o = op("Pripažinti, kad Lietuvos Respublikos civilinio kodekso 3.269 straipsnio (2000 m. liepos 18 d. redakcija) "
           "7 punktas prieštaravo (prieštarauja) Lietuvos Respublikos Konstitucijos 38 straipsnio 2 daliai.")
    assert ruling_targets(o, "civilinio kodekso") == ["3.269"]


def test_only_the_subject_counts():
    # provisions in the "tiek, kiek" clause and the standard after the verdict are not the subject
    o = op("Pripažinti, kad Lietuvos Respublikos baudžiamojo proceso kodekso 338 straipsnio 2 dalis tiek, kiek pagal ją "
           "teismas negali atidėti nuosprendžio vykdymo už nusikaltimus, nurodytus Lietuvos Respublikos baudžiamojo "
           "kodekso 11 straipsnyje, prieštarauja Lietuvos Respublikos Konstitucijos 38 straipsnio 2 daliai.")
    assert ruling_targets(o, "baudžiamojo proceso kodekso") == ["338"]
    assert ruling_targets(o, "baudžiamojo kodekso") is None
    assert ruling_targets(o, "Konstitucijos") is None
    o = op("Pripažinti, kad Lietuvos Respublikos Vyriausybės 2022 m. birželio 22 d. nutarimas Nr. 647 neprieštarauja "
           "Lietuvos Respublikos Konstitucijai, Lietuvos Respublikos Vyriausybės įstatymo 36 straipsniui.")
    assert ruling_targets(o, "vyriausybės įstatymo") is None
    # the approval law and an amending law's own (transitional) articles are not the act's articles
    o = op("1. Pripažinti, kad Lietuvos Respublikos civilinio kodekso patvirtinimo, įsigaliojimo ir įgyvendinimo įstatymo "
           "(Žin., 2000, Nr. 74-2262) 28 straipsnis prieštarauja konstituciniams principams. 2. Pripažinti, kad Lietuvos "
           "Respublikos civilinio kodekso (Žin., 2000, Nr. 74-2262) 3.229 straipsnis tiek, kiek pagal jį partnerystę galima "
           "sudaryti tik tarp vyro ir moters, prieštarauja Lietuvos Respublikos Konstitucijos 29 straipsniui.")
    assert ruling_targets(o, "civilinio kodekso") == ["3.229"]
    o = op("2. Pripažinti, kad Lietuvos Respublikos gyvūnų gerovės ir apsaugos įstatymo Nr. VIII‑500 2, 10, 12 ir 17 "
           "straipsnių pakeitimo įstatymo (TAR, 2023-09-27, Nr. 18812) 5 straipsnio 3, 5–9 dalys prieštarauja "
           "konstituciniam teisinės valstybės principui.")
    assert ruling_targets(o, "gyvūnų gerovės ir apsaugos įstatymo") is None


def test_lists_superscripts_and_delayed_publication():
    o = op("Pripažinti, kad Lietuvos Respublikos baudžiamojo kodekso 72(3) straipsnio (2010 m. gruodžio 2 d. redakcija) "
           "1 dalis, 74 ir 75 straipsniai prieštarauja Lietuvos Respublikos Konstitucijai.")
    assert ruling_targets(o, "baudžiamojo kodekso") == ["72-3", "74", "75"]
    text = "nutaria:\n1. Pripažinti, kad …\n2. Šis Lietuvos Respublikos Konstitucinio Teismo nutarimas Teisės aktų " \
           "registre turi būti oficialiai paskelbtas 2026 m. balandžio 10 d."
    assert ruling_effective(text, "2025-04-10") == "2026-04-10"
    assert ruling_effective("nutaria: …", "2025-04-10") == "2025-04-10"


ACT = """Suvestinė redakcija nuo 2026-01-01
LIETUVOS RESPUBLIKOS BANDOMASIS ĮSTATYMAS
2016 m. rugsėjo 14 d. Nr. XII-1
Vilnius
1 straipsnis. Pirmas
Tekstas.
2 straipsnis. Antras
Tekstas.
"""


class FakeLaws(currency.Laws):
    def __init__(self, rows, texts):
        self.meta, self.fetch, self._cache, self._texts = {r["atv_dok_nr"]: r for r in rows}, False, {}, texts

    def ruling(self, nr):
        t = self._texts[nr]
        return ruling_effective(t, self.meta[nr]["paskelbta_tar"]), ruling_operative(t)


def _ruling(nr, pub, verdict="prieštarauja"):
    row = {"dokumento_id": nr, "atv_dok_nr": nr, "rusis": "Nutarimas", "paskelbta_tar": pub, "priimtas": pub,
           "isigalioja": pub, "pavadinimas": "Dėl Lietuvos Respublikos bandomojo įstatymo 2 straipsnio atitikties Konstitucijai"}
    text = f"nutaria:\nPripažinti, kad Lietuvos Respublikos bandomojo įstatymo 2 straipsnis {verdict} Konstitucijai.\n"
    return row, text


SCOPE = {"abbr": "BĮ", "genitive": "bandomojo įstatymo", "number": "XII-1"}


def test_assess_flags_only_rulings_after_the_text():
    act = parse(ACT)
    row, text = _ruling("KT9-N1/2026", "2026-03-01")
    st = currency.assess(act, SCOPE, FakeLaws([row], {"KT9-N1/2026": text}), "2026-10-21")
    assert st.articles["1"].state == "current"
    assert st.articles["2"].state == "outdated" and "Konstitucinio Teismo nutarimas Nr. KT9-N1/2026" in st.articles["2"].reasons[0]
    row, text = _ruling("KT9-N1/2026", "2026-03-01", "neprieštarauja")
    st = currency.assess(act, SCOPE, FakeLaws([row], {"KT9-N1/2026": text}), "2026-10-21")
    assert st.articles["2"].state == "current"
    # published before the version began and not noted in it: the consolidators found nothing to change
    row, text = _ruling("KT1-N1/2025", "2025-12-01")
    st = currency.assess(act, SCOPE, FakeLaws([row], {"KT1-N1/2025": text}), "2026-10-21")
    assert st.articles["2"].state == "current"
    act.prepared = "2025-11-01"  # … unless the version was prepared before the ruling
    st = currency.assess(act, SCOPE, FakeLaws([row], {"KT1-N1/2025": text}), "2026-10-21")
    assert st.articles["2"].state == "outdated"


def test_assess_delayed_ruling_is_announced():
    act = parse(ACT)
    row, text = _ruling("KT9-N1/2026", "2026-03-01")
    text += "Šis Lietuvos Respublikos Konstitucinio Teismo nutarimas turi būti oficialiai paskelbtas 2027 m. kovo 1 d.\n"
    st = currency.assess(act, SCOPE, FakeLaws([row], {"KT9-N1/2026": text}), "2026-10-21")
    s = st.articles["2"]
    assert s.state == "current" and s.changes_on == "2027-03-01" and "nuo 2027-03-01" in s.note


def test_rewrite_staged_on_a_condition():
    # TPVCAPDĮ XIV-2388: new wordings of articles 9 and 11 from "D or a later condition date", of 17 from "the day
    # set in part 13": an article whose text doesn't list the law yet can't be confirmed current
    text = """LIETUVOS RESPUBLIKOS BANDOMOJO ĮSTATYMO NR. XII-1 PAKEITIMO ĮSTATYMAS
2023 m. gruodžio 12 d. Nr. XIV-9
1 straipsnis. Lietuvos Respublikos bandomojo įstatymo Nr. XII-1 nauja redakcija
Pakeisti Lietuvos Respublikos bandomąjį įstatymą Nr. XII-1 ir jį išdėstyti taip:
„1 straipsnis. Pirmas
Tekstas.“
2 straipsnis. Įstatymo įsigaliojimas
1. Šis įstatymas, išskyrus šio straipsnio 2 ir 3 dalis, įsigalioja 2023 m. gruodžio 23 d.
2. 2024 m. balandžio 23 d. arba Europos Komisijos įgyvendinimo aktų taikymo pradžios dieną, atsižvelgiant į tai, kuri data vėlesnė, įsigalioja tokia šio įstatymo 1 straipsnyje išdėstyto Bandomojo įstatymo 2 straipsnio redakcija:
„2 straipsnis. Antras
Naujas.“
3. Šio straipsnio 4 dalyje nurodytą dieną šio įstatymo 1 straipsnyje išdėstyto Bandomojo įstatymo 1 straipsnis papildomas 3 dalimi:
„3. Trečia.“
"""
    law = currency.parse_amending("XIV-9", text, "2023-12-23", "Lietuvos Respublikos bandomojo įstatymo Nr. XII-1 pakeitimo įstatymas")
    assert law.rewrite_own == 1
    assert law.staged_cond == {"2": "2024-04-23", "1": None}


def test_act_stages_its_own_new_wording():
    # SŽNSĮ 142/143: "Šio įstatymo 10 straipsnio nauja redakcija", dated by the act's entry article
    text = """Suvestinė redakcija nuo 2022-12-14 iki 2022-12-31
LIETUVOS RESPUBLIKOS BANDOMASIS ĮSTATYMAS
2019 m. birželio 6 d. Nr. XIII-1
Vilnius
9 straipsnis. Devintas
Tekstas.
10 straipsnis. Taikymas
Senas tekstas.
140 straipsnis. Įstatymo įsigaliojimas
1. Šis įstatymas, išskyrus 143 straipsnį, įsigalioja 2020 m. sausio 1 d.
2. Šio įstatymo 143 straipsnis įsigalioja 2023 m. sausio 1 d.
143 straipsnis. Šio įstatymo 10 straipsnio nauja redakcija
Pakeisti šio įstatymo 10 straipsnį ir jį išdėstyti taip:
„10 straipsnis. Taikymas
Naujas tekstas.“
"""
    act = parse(text)
    assert currency._self_amendments(act) == [("143", ["10"], "2023-01-01")]
    laws = FakeLaws([], {})
    st = currency.assess(act, SCOPE, laws, "2023-01-01")
    assert st.articles["10"].state == "outdated" and "143 straipsnyje" in st.articles["10"].reasons[0]
    assert st.articles["9"].state == "current"
    assert currency.assess(act, SCOPE, laws, "2022-12-20").articles["10"].state == "current"


def test_amender_in_the_consolidations_own_list_is_consolidated():
    # ŠTVT 47 and 1-399: the law applied on the version's first day and the "Pakeitimai:" list has it, but the
    # article's notes don't name it. e-tar shows the same text: not outdated. A later one still is.
    def law(nr, ent):
        row = {"dokumento_id": nr, "atv_dok_nr": nr, "rusis": "Įstatymas", "paskelbta_tar": ent, "priimtas": ent,
               "isigalioja": ent, "pavadinimas": "Lietuvos Respublikos bandomojo įstatymo Nr. XII-1 2 straipsnio pakeitimo įstatymas"}
        return row, currency.AmendingLaw(nr, ent, all_dates={ent}, title_targets=["2"])
    listed = ACT + "Pakeitimai:\n1.\nLietuvos Respublikos Seimas, Įstatymas\nNr. XII-5, 2025-12-01\n" \
                   "Lietuvos Respublikos bandomojo įstatymo Nr. XII-1 2 straipsnio pakeitimo įstatymas\n"
    for text, nr, ent, state in [(listed, "XII-5", "2026-01-01", "current"), (ACT, "XII-5", "2026-01-01", "outdated"),
                                 (listed, "XII-9", "2026-03-01", "outdated")]:
        act = parse(text)
        row, al = law(nr, ent)
        laws = FakeLaws([row], {})
        laws._cache[nr] = al
        assert currency.assess(act, SCOPE, laws, "2026-10-21").articles["2"].state == state, (nr, state)


def test_repealed_article_an_unconsolidated_law_names_is_not_said_repealed():
    # B86 (MKPVKNSA 3): repealed in the stored text, but a law in force after the text names it (it may put it back):
    # unknown, not "repealed". Without such a law it stays repealed.
    text = ACT.replace("2 straipsnis. Antras\nTekstas.", "2 straipsnis. Neteko galios nuo 2025-06-01")
    act = parse(text)
    assert currency.assess(act, SCOPE, FakeLaws([], {}), "2026-10-21").articles["2"].state == "repealed"
    nr, ent = "XII-9", "2026-03-01"
    row = {"dokumento_id": nr, "atv_dok_nr": nr, "rusis": "Įstatymas", "paskelbta_tar": ent, "priimtas": ent,
           "isigalioja": ent, "pavadinimas": "Lietuvos Respublikos bandomojo įstatymo Nr. XII-1 2 straipsnio pakeitimo įstatymas"}
    laws = FakeLaws([row], {})
    laws._cache[nr] = currency.AmendingLaw(nr, ent, all_dates={ent}, title_targets=["2"])
    st = currency.assess(act, SCOPE, laws, "2026-10-21").articles["2"]
    assert st.state == "unknown" and "XII-9" in " ".join(st.reasons)
    assert currency.assess(act, SCOPE, laws, "2026-02-01").articles["2"].state == "repealed"  # before the law applies
