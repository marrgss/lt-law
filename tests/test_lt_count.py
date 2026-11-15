from ltlaw.render import lt_count


def test_lithuanian_agreement_after_a_number():
    f = lambda n: lt_count(n, "aktas", "aktai", "aktų")
    assert [f(n) for n in (1, 2, 9, 10, 11, 19, 20, 21, 101, 111, 442)] == [
        "1 aktas", "2 aktai", "9 aktai", "10 aktų", "11 aktų", "19 aktų", "20 aktų", "21 aktas", "101 aktas", "111 aktų", "442 aktai"]
