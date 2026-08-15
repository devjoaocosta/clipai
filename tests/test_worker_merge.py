from worker import merge_moments


def test_merge_never_fuses_two_kills():
    moments = [(10.0, "kill"), (15.0, "kill")]
    assert merge_moments(moments, merge_window=10.0) == moments


def test_merge_fuses_kill_and_keyword_same_moment():
    moments = [(10.0, "kill"), (12.0, "double kill")]
    assert merge_moments(moments, merge_window=10.0) == [(10.0, "kill")]


def test_merge_keeps_moments_beyond_window():
    moments = [(10.0, "kill"), (25.0, "double kill")]
    assert merge_moments(moments, merge_window=10.0) == moments


def test_merge_keeps_distant_kills_but_fuses_same_window():
    moments = [(10.0, "kill"), (14.0, "kill"), (20.0, "triple kill")]
    assert merge_moments(moments, merge_window=10.0) == [(10.0, "kill"), (14.0, "kill")]
