from matcher import Word, clip_window, find_matches, near_misses, normalize


def w(start, end, text):
    return Word(start, end, text)


def test_normalize_strips_accents_case_and_punct():
    assert normalize("LENDÁRIO!!") == ["lendario"]
    assert normalize("Penta-Kill") == ["penta", "kill"]
    assert normalize("") == []


def test_exact_match_single_word():
    words = [w(100.0, 101.0, "lendário")]
    matches = find_matches(words, ["lendário"])
    assert len(matches) == 1
    assert matches[0].time == 100.0
    assert matches[0].keyword == "lendário"


def test_keyword_split_across_words_matches():
    words = [w(200.0, 200.5, "double"), w(200.5, 201.0, "kill")]
    matches = find_matches(words, ["double kill"])
    assert len(matches) == 1
    assert matches[0].time == 200.0


def test_single_word_keyword_matches_two_transcribed_words():
    words = [w(300.0, 300.5, "penta"), w(300.5, 301.0, "kill")]
    matches = find_matches(words, ["pentakill"])
    assert len(matches) == 1


def test_keyword_with_space_matches_single_word():
    words = [w(300.0, 301.0, "pentakill")]
    matches = find_matches(words, ["penta kill"])
    assert len(matches) == 1


def test_no_fuzzy_false_positive_for_single_token():
    words = [w(757.0, 757.5, "achei"), w(1431.0, 1431.5, "Leandro")]
    assert find_matches(words, ["ace", "lendário"]) == []


def test_fuzzy_matches_whisper_variant():
    words = [w(50.0, 50.5, "dobre"), w(50.5, 51.0, "kill")]
    matches = find_matches(words, ["double kill"])
    assert len(matches) == 1
    assert matches[0].time == 50.0


def test_accent_insensitive():
    words = [w(50.0, 51.0, "LENDARIO")]
    matches = find_matches(words, ["lendário"])
    assert len(matches) == 1


def test_no_match_for_unrelated():
    words = [w(10.0, 11.0, "olá pessoal"), w(20.0, 21.0, "café")]
    assert find_matches(words, ["double kill", "lendário"]) == []


def test_merge_nearby_hits():
    words = [w(100.0, 100.5, "double"), w(100.5, 101.0, "kill"),
             w(105.0, 106.0, "lendário")]
    matches = find_matches(words, ["double kill", "lendário"], merge_window=10.0)
    assert len(matches) == 1


def test_no_merge_far_hits():
    words = [w(100.0, 100.5, "double"), w(100.5, 101.0, "kill"),
             w(500.0, 501.0, "lendário")]
    matches = find_matches(words, ["double kill", "lendário"], merge_window=10.0)
    assert len(matches) == 2


def test_near_misses_report_variants():
    words = [w(50.0, 51.0, "dobre"), w(100.0, 101.0, "café")]
    nm = near_misses(words, ["double kill"])
    assert len(nm) >= 1
    assert nm[0][1] == "dobre"
    assert nm[0][2] == "double kill"


def test_clip_window_clamps_to_bounds():
    assert clip_window(10.0, 100.0, 5.0, 30.0) == (5.0, 35.0)
    assert clip_window(2.0, 100.0, 5.0, 30.0) == (0.0, 30.0)
    assert clip_window(95.0, 100.0, 5.0, 30.0) == (90.0, 100.0)
    assert clip_window(99.0, 100.0, 5.0, 30.0) == (94.0, 100.0)
    assert clip_window(1.9, 2.0, 5.0, 30.0) is None
