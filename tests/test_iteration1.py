"""Rules adopted in review iteration 1 (docs/ACCURACY.md, 2026-10-18)."""
from ltlaw.currency import decode_new_label, parse_amending, tar_note_effects
from ltlaw.parse import Block, parse
from ltlaw.render import display_text, long_acronyms, sentence_case

DAY = "2026-10-18"


class Art:
    def __init__(self, *notes):
        self.blocks = [Block("editorial", None, n) for n in notes]


def test_tar_notes():
    # a part with its own later start date
    p, u = tar_note_effects(Art("TAR pastaba. 36 straipsnio 22 dalies 2 punktas įsigalioja 2030-01-01."), DAY)
    assert p == ["2030-01-01"] and not u
    # conditional start, with no date or with a date plus "jeigu"
    assert tar_note_effects(Art("TAR pastaba: 61 straipsnis įsigalioja praėjus 9 mėnesiams nuo Europos Komisijos aktų"), DAY)[1]
    assert tar_note_effects(Art("TAR pastaba. Įsigalioja 2025 m. liepos 1 d., jeigu Europos Komisija pritaria"), DAY)[1]
    assert tar_note_effects(Art("TAR pastaba. Nuostatos pradedamos taikyti, kai naujai išrinktos tarybos susirenka"), DAY)[1]
    # two wordings printed side by side
    p, u, info = tar_note_effects(Art("TAR pastaba: 3 punkto redakcija nuo 2025-07-01:"), DAY, with_info=True)
    assert not p and not u and info  # an older second wording: told to the reader, not a flag
    assert tar_note_effects(Art("TAR pastaba. 34 dalies redakcija nuo 2026-12-31:"), DAY)[0] == ["2026-12-31"]
    # transitional and past-dated notes don't change anything
    for n in ("TAR pastaba. 18 dalies nuostatos taikomos apskaičiuojant 2019 metų ir vėlesnių laikotarpių pajamas.",
              "TAR pastaba. 581 straipsnio 2 dalis įsigalioja 2020-01-01.",
              "TAR pastaba. 4 straipsnio 2 dalies 1 punkto nuostatos taikomos nuo 2022-07-01."):
        assert tar_note_effects(Art(n), DAY) == ([], [])


ENTRY = """1 straipsnis. 5 straipsnio pakeitimas
Pakeisti 5 straipsnį.
2 straipsnis. 7 straipsnio pakeitimas
Pakeisti 7 straipsnį.
3 straipsnis. 9 straipsnio pakeitimas
Pakeisti 9 straipsnį.
4 straipsnis. Įstatymo įsigaliojimas
1. Šis įstatymas įsigalioja 2026 m. sausio 1 d.
2. Šio įstatymo 3 straipsnyje išdėstyto Kodekso 9 straipsnio 2 dalis įsigalioja 2027 m. sausio 1 d.
"""


def test_partial_delay_keeps_the_default_for_the_rest():
    law = parse_amending("XV-1", ENTRY, "2026-01-01")
    assert 3 not in law.whole                  # only part 2 of article 9 is delayed
    assert law.dates_for("9") == {"2026-01-01", "2027-01-01"}


def test_conditional_entry_with_a_date():
    t = ENTRY.replace("1. Šis įstatymas įsigalioja 2026 m. sausio 1 d.",
                      "1. Šis įstatymas įsigalioja 2026 m. sausio 1 d., jeigu iki tol gaunamas Europos Komisijos pritarimas.")
    assert parse_amending("XV-2", t, "2026-01-01").conditional


def test_hyphen_range_of_own_articles():
    t = ENTRY.replace("2. Šio įstatymo 3 straipsnyje išdėstyto Kodekso 9 straipsnio 2 dalis įsigalioja 2027 m. sausio 1 d.",
                      "2. Šio įstatymo 1-3 straipsniai įsigalioja 2027 m. sausio 1 d.")
    law = parse_amending("XV-3", t, "2026-01-01")
    assert {1, 2, 3} <= set(law.own_dates)


def test_decode_new_label():
    labels = ["29", "30", "30-1", "30-2", "31", "70"]
    assert decode_new_label("303", labels) == "30-3"
    assert decode_new_label("52-1", labels) == "52-1"
    assert decode_new_label("71", labels) == "71"


def test_display_text():
    assert display_text(Block("part", None, "161. Farmakologinis", anchor="d16-1")) == "16¹. Farmakologinis"
    assert "paveikslėliu" in display_text(Block("part", None, "9. Suma apskaičiuojama pagal šią formulę:", anchor="d9"))


def test_heading_case_uses_the_acts_own_acronyms():
    assert sentence_case("GAMTINIŲ DUJŲ TIEKIMAS", {"PVM"}) == "Gamtinių dujų tiekimas"
    assert sentence_case("PVM TARIFAI", {"PVM"}) == "PVM tarifai"
    assert sentence_case("RESPUBLIKOS PREZIDENTAS", set()) == "Respublikos Prezidentas"
    acr = long_acronyms(["ENISA veikia pagal šį reglamentą.", "Ženklas „PAVOJUS“ kabinamas.", "XXIII skyrius",
                         "PASTABA. TAIKOMA VISIEMS"])                          # in a sentence only; quotes, numerals out
    assert acr == {"ENISA"}
    assert sentence_case("ENISA BIUDŽETO SUDARYMAS", acr) == "ENISA biudžeto sudarymas"
    assert sentence_case("ENISA BIUDŽETO SUDARYMAS", set()) == "Enisa biudžeto sudarymas"


OLD = """Suvestinė redakcija nuo 2026-01-01
LIETUVOS RESPUBLIKOS BANDOMASIS ĮSTATYMAS
1 straipsnis. Pirmas
Tekstas.
2 straipsnis. Antras
1. Pirma dalis.
2. Antra dalis.
Straipsnio pakeitimai:
TAR pastaba. 2 dalis įsigalioja 2030-01-01.
Nr. XV-1, 2025-06-01, paskelbta TAR 2025-06-05, i. k. 2025-00001
LIETUVOS RESPUBLIKOS
AUKŠČIAUSIOSIOS TARYBOS
PIRMININKAS V.LANDSBERGIS
Pakeitimai:
1.
Lietuvos Respublikos Seimas, Įstatymas
Nr. I-1, 93.07.16
"""


def test_parser_old_signature_and_refs_after_a_tar_note():
    act = parse(OLD)
    a2 = act.main.articles[-1]
    assert a2.label == "2" and not any("LANDSBERGIS" in b.text or "I-1" in b.text for b in a2.blocks)
    assert "XV-1" in {r.nr for r in a2.all_refs()}         # the reference survives the TAR note before it
    assert any("TAR pastaba" in b.text for b in a2.blocks)  # and the note stays visible
