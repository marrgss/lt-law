import datetime as dt

from ltlaw.render import REGISTER_LAG_DAYS, _easter, working_days_between


def test_easter():
    assert _easter(2026) == dt.date(2026, 4, 5)
    assert _easter(2027) == dt.date(2027, 3, 28)


def test_the_2026_10_31_lag_warns():
    # newest publication Mon 10-26, built Sat 10-31: Tue..Fri missing (SŽNSĮ XV-1230 of 10-27 among them)
    assert working_days_between("2026-10-26", "2026-10-31") == 4 > REGISTER_LAG_DAYS


def test_a_normal_monday_does_not_warn():
    assert working_days_between("2026-10-29", "2026-11-02") <= REGISTER_LAG_DAYS  # Thu → Mon: Fri only
    assert working_days_between("2026-10-30", "2026-11-03") <= REGISTER_LAG_DAYS  # Fri → Tue: Mon (11-02 a holiday)


def test_holidays_are_not_missing_days():
    assert working_days_between("2026-12-23", "2026-12-28") == 0  # 24–26 Dec, then Sunday
    assert working_days_between("2026-04-03", "2026-04-07") == 0  # Easter Monday 04-06
