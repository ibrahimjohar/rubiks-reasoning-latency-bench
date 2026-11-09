import report


def test_recorded_runs_are_labelled_v1():
    assert report.state_version("20261109T161544Z-dceb5d") == "v1"
    assert report.state_version("20261109T154553Z-47d5b3") == "v1"


def test_other_runs_are_labelled_v2():
    assert report.state_version("20270101T000000Z-abcdef") == "v2"
