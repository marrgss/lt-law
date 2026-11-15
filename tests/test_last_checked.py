from ltlaw import source


def test_last_checked_takes_the_newer_of_snapshot_and_check(tmp_path):
    assert source.last_checked("X", tmp_path) == ""
    (tmp_path / "X").mkdir()
    (tmp_path / "X" / "2026-10-20.json").write_text("{}")
    assert source.last_checked("X", tmp_path) == "2026-10-20"
    (tmp_path / "X" / "checked.txt").write_text("2026-10-24T02:10:00+03:00\n")
    assert source.last_checked("X", tmp_path).startswith("2026-10-24")
    (tmp_path / "X" / "2026-10-25.json").write_text("{}")
    assert source.last_checked("X", tmp_path).startswith("2026-10-25")

