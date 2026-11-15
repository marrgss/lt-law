def test_present_tense_repeal_with_a_date():
    from types import SimpleNamespace
    from ltlaw.currency import _article_repealed
    art = lambda t: SimpleNamespace(title=t, blocks=[])
    assert _article_repealed(art("Netenka galios nuo 2010 m. liepos 1 d.")) == (True, "2010-07-01")
    assert _article_repealed(art("Neteko galios nuo 2016-01-01")) == (True, "2016-01-01")
    assert _article_repealed(art("Netenka galios")) == (False, None)


def test_superscript_point_number_is_its_own_point():
    from ltlaw.points import parse_points
    text = ("Suvestinė redakcija nuo 2022-06-01\nPATVIRTINTA\nLietuvos Respublikos energetikos ministro\n"
            "2009 m. lapkričio 26 d. įsakymu Nr. 1-229\nPASTATO ŠILDYMO TVARKOS APRAŠAS\nI SKYRIUS\nBENDROSIOS NUOSTATOS\n"
            "22. Valdytojas sudaro sutartį.\n22¹. Šilumos punktus prižiūri tiekėjas.\n23. Kita.\n")
    labels = [a.label for a in parse_points(text).main.articles]
    assert labels == ["22", "22-1", "23"]
