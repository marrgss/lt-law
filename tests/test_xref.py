"""Cross-reference links inside one act (xref.py)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from ltlaw.xref import Linker  # noqa: E402

ANCH = {"52": {"d1", "d2", "d2-p3"}, "21": set(), "21-1": {"d1"}, "211": set(), "5": {"d1"}, "7": set()}


def links(text, here="5", **kw):
    return str(Linker("/ta/X/", "str", ANCH, **kw).html(text, here))


def test_same_act_article_part_and_point():
    assert links("pagal šio kodekso 52 straipsnio 2 dalį") == \
        'pagal <a class="xref" href="/ta/X/str/52/#d2">šio kodekso 52 straipsnio 2 dalį</a>'
    assert '/ta/X/str/52/#d2-p3"' in links("šio Kodekso 52 straipsnio 2 dalies 3 punkte")
    assert '/ta/X/str/52/"' in links("šio įstatymo 52 straipsnio 9 dalyje")   # no part 9: the article only
    assert "href" not in links("šio kodekso 99 straipsnyje")                # no such article: plain text


def test_flattened_superscripts_only_when_unambiguous():
    # "211" could be 21¹ or 211: both are articles here, so no link
    assert "href" not in links("šio įstatymo 211 straipsnyje")
    only = Linker("/ta/X/", "str", {"21": set(), "21-1": {"d1"}})
    assert '/ta/X/str/21-1/#d1"' in str(only.html("šio įstatymo 211 straipsnio 1 dalyje", "21"))


def test_same_article_and_escaping():
    assert links("kaip nurodyta šio straipsnio 1 dalyje <b>") == \
        'kaip nurodyta <a class="xref" href="#d1">šio straipsnio 1 dalyje</a> &lt;b&gt;'
    assert "href" not in links("šio straipsnio 4 dalyje")                   # article 5 has no part 4


def test_rules_points():
    ket = Linker("/ta/K/", "p", {"66": set(), "66-3": set(), "3": {"p3.2-1"}}, points=True)
    assert '/ta/K/p/3/#p3.2-1"' in str(ket.html("Taisyklių 3.2-1 papunktyje", "1"))
    assert '/ta/K/p/66-3/"' in str(ket.html("išskyrus Taisyklių 663 punkte nustatytus atvejus", "1"))
    assert "href" not in str(ket.html("šio kodekso 66 straipsnyje", "1"))    # not an article act


def test_other_acts_need_their_full_or_capitalised_name():
    from ltlaw.xref import Others
    others = Others([{"genitive": "energetikos įstatymo", "url": "/ta/E/", "seg": "str", "labels": {"5"}},
                     {"genitive": "darbo kodekso", "url": "/ta/DK/", "seg": "str", "labels": {"52", "21", "21-1", "211"}},
                     {"genitive": "kelių eismo taisyklių", "url": "/ta/K/", "seg": "p", "labels": {"5"}}])
    l = Linker("/ta/X/", "str", ANCH, others=others)
    assert '/ta/DK/str/52/"' in str(l.html("pagal Lietuvos Respublikos darbo kodekso 52 straipsnį", "5"))
    assert '/ta/DK/str/52/"' in str(l.html("Lietuvos Respublikos darbo kodekso (Nr. XII-2603) 52 straipsnio", "5"))
    # "energetikos įstatymo" inside "elektros energetikos įstatymo" is another law: no link
    assert "href" not in str(l.html("Lietuvos Respublikos elektros energetikos įstatymo 5 straipsnyje", "5"))
    assert "href" not in str(l.html("darbo kodekso 52 straipsnyje", "5"))            # without "Lietuvos Respublikos"
    assert "href" not in str(l.html("Lietuvos Respublikos darbo kodekso 211 straipsnyje", "5"))  # ambiguous there
    # the usual form in rules after the first mention: the name alone, capitalised (D-036)
    assert '/ta/E/str/5/"' in str(l.html("nustatytos Energetikos įstatymo 5 straipsnio 1 dalyje", "5"))
    assert '/ta/DK/str/52/"' in str(l.html("pagal Darbo kodekso 52 straipsnį", "5"))
    # lower case inside another law's name is never it
    assert "href" not in str(l.html("pagal Atominės energetikos įstatymo 5 straipsnį", "5"))


def test_links_to_other_articles_are_recorded_for_related():
    from ltlaw.xref import Others
    others = Others([{"genitive": "darbo kodekso", "url": "/ta/DK/", "seg": "str", "labels": {"52"}}])
    sink: list = []
    l = Linker("/ta/X/", "str", ANCH, others=others, sink=sink)
    l.html("pagal Darbo kodekso 52 straipsnį ir šio straipsnio 2 dalį, šio kodekso 52 straipsnio 1 dalyje", "5", "d3", record=True)
    assert sink == [("/ta/X/str/5/#d3", "/ta/DK/str/52/"), ("/ta/X/str/5/#d3", "/ta/X/str/52/#d1")]  # not "#d2" (own part)
    l.html("pagal Darbo kodekso 52 straipsnį", "5")  # an older wording shown below: not recorded
    assert len(sink) == 2


def test_lists_and_ranges_link_each_number():
    out = links("pagal šio kodekso 52 ir 5 straipsniuose bei šio įstatymo 5–7 straipsnių nuostatas")
    assert out.count('class="xref"') == 4 and '>52</a>' in out and '>7</a>' in out    # 52, 5; range ends 5 and 7
    assert "href" not in links("šio kodekso 98 ir 99 straipsniuose")                   # neither exists


def test_lists_of_parts():
    out = links("šio straipsnio 1 ir 2 dalyse", here="52")
    assert out == 'šio straipsnio <a class="xref" href="#d1">1</a> ir <a class="xref" href="#d2">2</a> dalyse'
    out = links("pagal šio kodekso 52 straipsnio 1–2 dalis")
    assert '<a class="xref" href="/ta/X/str/52/">šio kodekso 52 straipsnio</a>' in out
    assert 'href="/ta/X/str/52/#d1">1</a>–<a class="xref" href="/ta/X/str/52/#d2">2</a> dalis' in out
    assert links("šio straipsnio 1 ir 4 dalyse", here="52").count("href") == 1   # no part 4: that number stays text


def test_references_to_eu_acts_by_number_in_any_case():
    from ltlaw.xref import Others
    others = Others([{"genitive": "Reglamento (ES) 2016/679", "url": "/es/32016R0679/", "seg": "str", "labels": {"6", "4a"},
                      "eu_names": ["Reglamento (ES) 2016/679", "reglamento (ES) 2016/679"]},
                     {"genitive": "darbo kodekso", "url": "/ta/DK/", "seg": "str", "labels": {"52"}}])
    l = Linker("/ta/X/", "str", ANCH, others=others)
    assert '/es/32016R0679/str/6/"' in str(l.html("pagal Reglamento (ES) 2016/679 6 straipsnio 1 dalį", "5"))
    assert '/es/32016R0679/str/6/"' in str(l.html("Europos Parlamento ir Tarybos reglamento (ES) 2016/679 6 straipsnyje", "5"))
    assert '/es/32016R0679/str/4a/"' in str(l.html("Reglamento (ES) 2016/679 4a straipsnis", "5"))
    assert "href" not in str(l.html("Reglamento (ES) 2016/680 6 straipsnio", "5"))  # another act
    assert '/ta/DK/str/52/"' in str(l.html("Darbo kodekso 52 straipsnio", "5"))
    assert '/es/32016R0679/str/6/"' in str(l.html("Reglamento (ES) 2016/679 (Bendrasis duomenų apsaugos reglamentas) 6 straipsnio", "5"))


def test_an_eu_acts_bare_references_are_its_own_articles():
    l = Linker("/es/X/", "str", {"6": {"d1"}, "28": set(), "5": set()}, eu=True)
    assert 'href="/es/X/str/6/#d1"' in str(l.html("kaip nurodyta 6 straipsnio 1 dalyje", "5"))
    assert 'href="/es/X/str/28/"' in str(l.html("pagal 28 straipsnį", "5"))
    assert "href" not in str(l.html("Reglamento (ES) 2019/1020 6 straipsnio", "5"))      # another act's
    assert "href" not in str(l.html("pagal Direktyvos 2014/53/ES 6 straipsnį", "5"))
    assert "href" not in str(l.html("SESV 28 straipsnį", "5"))
    assert "href" not in str(Linker("/ta/X/", "str", {"6": set()}).html("pagal 6 straipsnį", "5"))  # Lithuanian acts: never
    l = Linker("/es/X/", "str", {"2": {"d1"}, "5": set()}, eu=True)
    assert 'href="/es/X/str/2/#d1"' in str(l.html("4. 2 straipsnio 1 dalyje išvardyti subjektai", "5"))  # "4." is the part
    assert "href" not in str(l.html("2 straipsnis pakeičiamas taip: „Pagal 2 straipsnį …“", "5").split("„", 1)[1])
