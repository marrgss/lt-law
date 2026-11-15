from ltlaw.decisions import changes, label, period, series_key

ESO26 = ("Dėl AB „Energijos skirstymo operatorius“ elektros energijos persiuntimo paslaugos kainų ir jų taikymo tvarkos 2026 "
         "metams paskelbimo ir persiuntimo paslaugos kainų diferencijavimo metodikos Derinimo")
ESO20 = "Dėl AB „Energijos skirstymo operatorius“ elektros energijos persiuntimo paslaugos kainų ir jų taikymo tvarkos paskelbimo"


def test_series_key_drops_period_and_verb():
    assert series_key(ESO26) == series_key(ESO20) == \
        "ab „energijos skirstymo operatorius“ elektros energijos persiuntimo paslaugos kainų ir jų taikymo tvarkos"
    assert series_key("Dėl akcinės bendrovės „Energijos skirstymo operatorius“ papildomų paslaugų įkainių derinimo").startswith("ab „")


def test_period_from_the_title_not_from_cited_dates():
    assert period(ESO26) == ("2026-01-01", "2026-12-31")
    assert period("Dėl minimalių elektros energijos persiuntimo patikimumo lygių nustatymo AB „ESO“ 2027–2031 m. reguliavimo periodui") == ("2027-01-01", "2031-12-31")
    assert period("Dėl AB „ESO“ skirstymo paslaugų kainų viršutinių ribų 2022‒2026 metų reguliavimo periodui nustatymo") == ("2022-01-01", "2026-12-31")
    assert period("Dėl prognozuojamos elektros energijos rinkos kainos 2026 metų antrajam pusmečiui nustatymo") == ("2026-07-01", "2026-12-31")
    assert period("Dėl UAB „Ignitis“ 2026 m. I pusmečio visuomeninių elektros energijos kainų paskelbimo") == ("2026-01-01", "2026-06-30")
    assert period("Dėl papildomų dedamųjų 2023 m. I pusm. ir 2023 m. nustatymo") == ("2023-01-01", "2023-06-30")
    assert period("Dėl Valstybinės energetikos reguliavimo tarybos 2015 m. sausio 15 d. nutarimo Nr. O3-3 pakeitimo") is None
    assert period(ESO20) is None


def test_changes_names_the_amended_decision():
    t = ("Dėl Valstybinės energetikos reguliavimo tarybos 2023 m. spalio 27 d. nutarimo Nr. O3E-1603 „Dėl Elektros energijos "
         "perdavimo paslaugų kainų ir jų taikymo tvarkos paskelbimo“ pakeitimo")
    assert changes({"pavadinimas": t}) == "O3E-1603/2023-10-27"
    assert changes({"pavadinimas": ESO26}) is None


def test_labels():
    row = lambda t, ent="2026-01-01", st="galioja": {"pavadinimas": t, "isigalioja": ent, "galioj_busena": st, "atv_dok_nr": "X", "priimtas": "2025-11-12"}
    assert label(row(ESO26), None, "2026-10-27")["state"] == "current"
    assert label(row(ESO26, "2027-01-01"), None, "2026-10-27") == {"state": "pending", "text": "Įsigalios 2027-01-01"}
    assert label(row(ESO26.replace("2026", "2024")), None, "2026-10-27")["text"] == "Ankstesnio laikotarpio (2024 m.)"
    later = {"atv_dok_nr": "O3E-1676", "priimtas": "2025-11-12"}
    assert label(row(ESO20, "2020-01-01"), later, "2026-10-27")["state"] == "replaced"
    assert label(row(ESO20, "2020-01-01"), None, "2026-10-27")["state"] == "register"
    assert label(row(ESO20, "2020-01-01", "negalioja"), None, "2026-10-27")["state"] == "repealed"


def test_ranges_with_any_dash_and_later_decisions_only_once_they_apply():
    assert period("Dėl AB „Achema“ skirstymo paslaugos kainos viršutinės ribos 2025−2029 metams nustatymo") == ("2025-01-01", "2029-12-31")
    assert period("Dėl Litgrid AB perdavimo paslaugos kainos viršutinės ribos 2027 2031 metams nustatymo") == ("2027-01-01", "2031-12-31")
    cur = {"pavadinimas": "Dėl AB „ESO“ skirstymo paslaugų kainų viršutinių ribų 2026 metams koregavimo", "isigalioja": "2025-10-18",
           "galioj_busena": "galioja", "atv_dok_nr": "O3E-1469", "priimtas": "2025-10-17"}
    nxt = {"pavadinimas": "Dėl AB „ESO“ skirstymo paslaugų kainų viršutinių ribų 2027 metams koregavimo", "isigalioja": "2026-10-17",
           "galioj_busena": "galioja", "atv_dok_nr": "O3-1371", "priimtas": "2026-10-16"}
    assert label(cur, nxt, "2026-10-27")["state"] == "current"
    assert label(cur, nxt, "2027-01-02")["state"] == "earlier"
    assert label(nxt, None, "2026-10-27") == {"state": "pending", "text": "Taikomas nuo 2027-01-01"}
