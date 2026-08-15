import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from killtracker import (_as_kda_kills, _as_kill_value, _band_value,
                         _events_from_signatures, _kills_slot_vector, _ncc,
                         increment_events, parse_kill_total, parse_region)

ORIGIN, REGION_W = 0.785, 0.110
FIX_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _region_clip(n: int) -> np.ndarray:
    path = os.path.join(FIX_DIR, f"region_clip{n:02d}.png")
    return np.array(Image.open(path).convert("RGB"))


def _slot_vec(n: int) -> np.ndarray:
    return _kills_slot_vector(_region_clip(n), ORIGIN, REGION_W)


def _font(size=40):
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _to_crop(frac: float) -> int:
    return int((frac - ORIGIN) / REGION_W * 410)


def _text_left(frac: float, text: str, font) -> int:
    d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    bb = d.textbbox((0, 0), text, font=font, stroke_width=2)
    return _to_crop(frac) - (bb[2] - bb[0]) // 2


def _make_row(streamer_kda: str | None = None,
              mins: str | None = None) -> np.ndarray:
    img = Image.new("RGB", (410, 65), (20, 20, 40))
    d = ImageDraw.Draw(img)
    font = _font()
    if mins:
        d.text((8, 10), mins, fill=(255, 255, 255), font=font,
               stroke_width=2, stroke_fill=(255, 255, 255))
    if streamer_kda is not None:
        d.text((_text_left(0.878, streamer_kda, font), 10), streamer_kda,
               fill=(255, 255, 255), font=font,
               stroke_width=2, stroke_fill=(255, 255, 255))
    return np.array(img)


def test_parse_kill_total_streamer_kda():
    assert parse_kill_total(_make_row("3/5/11"), ORIGIN, REGION_W) == (3,)
    assert parse_kill_total(_make_row("0/0/0"), ORIGIN, REGION_W) == (0,)
    assert parse_kill_total(_make_row("24/6/11"), ORIGIN, REGION_W) == (24,)
    assert parse_kill_total(_make_row("2/1/1"), ORIGIN, REGION_W) == (2,)


def _make_separate_kda(row: tuple[float, str, float, str, float, str]) -> np.ndarray:
    img = Image.new("RGB", (410, 65), (20, 20, 40))
    d = ImageDraw.Draw(img)
    font = _font()
    for frac, text in ((row[0], row[1]), (row[2], row[3]), (row[4], row[5])):
        d.text((_text_left(frac, text, font), 10), text,
               fill=(255, 255, 255), font=font,
               stroke_width=2, stroke_fill=(255, 255, 255))
    return np.array(img)


def test_parse_kill_total_picks_leftmost_separated_kda():
    img = _make_separate_kda((0.865, "3", 0.877, "5", 0.888, "11"))
    assert parse_kill_total(img, ORIGIN, REGION_W) == (3,)


def test_parse_kill_total_ignores_timer():
    assert _as_kill_value("10:00") is None
    assert _as_kill_value("10:0012") is None


def _group(center_frac: float, text: str, width: int = 24):
    w = 410
    left = int((center_frac - ORIGIN) / REGION_W * w - width / 2)
    return (left, width, text)


def test_band_value_picks_leftmost_number_of_kda():
    img = np.zeros((65, 410, 3), dtype=np.uint8)
    groups = [_group(0.870, "3"), _group(0.877, "5"), _group(0.888, "11")]
    assert _band_value(img, groups, "streamer", ORIGIN, REGION_W) == 3


def test_band_value_ignores_blue_kills_crossing_band_edge():
    img = np.zeros((65, 410, 3), dtype=np.uint8)
    groups = [_group(0.857, "10", width=36), _group(0.865, "3")]
    assert _band_value(img, groups, "streamer", ORIGIN, REGION_W) == 3


def test_band_value_ignores_separator_and_reads_kda():
    img = np.zeros((65, 410, 3), dtype=np.uint8)
    groups = [_group(0.860, "|", width=24), _group(0.878, "#9")]
    assert _band_value(img, groups, "streamer", ORIGIN, REGION_W) == 9


def test_band_value_falls_back_to_crossing_token():
    img = np.zeros((65, 410, 3), dtype=np.uint8)
    groups = [_group(0.862, "10", width=36)]
    assert _band_value(img, groups, "streamer", ORIGIN, REGION_W) == 10


def test_parse_kill_total_blank_band_is_none():
    assert parse_kill_total(np.zeros((65, 410, 3), dtype=np.uint8),
                            ORIGIN, REGION_W) is None


def test_as_kill_value_fixes_ambiguous_digits():
    assert _as_kill_value("/") == 7
    assert _as_kill_value("l") == 1
    assert _as_kill_value("O") == 0
    assert _as_kill_value("12") == 12
    assert _as_kill_value("") is None
    assert _as_kill_value("aaa") is None
    assert _as_kill_value("12345") is None
    assert _as_kill_value("123") == 123
    assert _as_kill_value("500") is None
    assert _as_kill_value("#13") == 13
    assert _as_kill_value("$2") == 2
    assert _as_kill_value("10:00") is None


def test_as_kda_kills_real_ocr_cases():
    assert _as_kda_kills("3/5/11") == 3
    assert _as_kda_kills("8/11/") == 8
    assert _as_kda_kills("#6") == 6
    assert _as_kda_kills("#10") == 10
    assert _as_kda_kills("10.") == 10
    assert _as_kda_kills("11") == 11
    assert _as_kda_kills("0") == 0


def test_as_kda_kills_rejects_garbage():
    assert _as_kda_kills("") is None
    assert _as_kda_kills("xyw") is None
    assert _as_kda_kills("x/xyw") is None
    assert _as_kda_kills("#") is None


def test_as_kda_kills_rejects_separator():
    assert _as_kda_kills("|") is None
    assert _as_kda_kills("||") is None


def test_as_kda_kills_strips_leading_non_digits():
    assert _as_kda_kills("|#9") == 9
    assert _as_kda_kills("#9") == 9
    assert _as_kda_kills("s#9") == 9


def test_as_kda_kills_rejects_huge():
    assert _as_kda_kills("200/0/0") is None
    assert _as_kda_kills("500") is None


def test_increment_events_confirms_over_frames():
    samples = [(0, None), (1, (0,)), (2, (0,)), (3, (0,)), (4, (0,)),
               (5, (1,)), (6, (1,)), (7, (1,)), (8, (1,))]
    assert increment_events(samples) == [(5, 'streamer', 1)]


def test_increment_events_single_increment():
    samples = [(0, (0,)), (1, (1,)), (2, (1,)), (3, (1,)),
               (4, (2,)), (5, (2,)), (6, (2,)), (7, (2,))]
    assert increment_events(samples) == [(1, 'streamer', 1), (4, 'streamer', 2)]


def test_increment_events_first_reading_is_baseline():
    samples = [(0, (3,)), (1, (3,)), (2, (3,)), (3, (3,))]
    assert increment_events(samples) == []


def test_increment_events_filters_flicker():
    samples = [(0, (5,)), (1, (5,)), (2, (6,)), (3, (5,)),
               (4, (6,)), (5, (6,)), (6, (6,))]
    assert increment_events(samples) == [(4, 'streamer', 6)]


def test_increment_events_ignores_decrease_and_resets():
    samples = [(0, (5,)), (1, (5,)), (2, (7,)), (3, (7,)), (4, (7,)),
               (5, (6,)), (6, (6,)), (7, (6,))]
    assert increment_events(samples) == [(2, 'streamer', 7)]


def test_increment_events_rejects_implausible_jump():
    samples = [(0, (0,)), (1, (55,)), (2, (55,)), (3, (55,)), (4, (55,))]
    assert increment_events(samples) == []


def test_increment_events_recovers_from_gap_jump():
    samples = [(0, (5,)), (1, (5,)), (2, None), (3, (13,)),
               (4, (13,)), (5, (13,)), (6, (14,)), (7, (14,)), (8, (14,))]
    assert increment_events(samples) == [(6, 'streamer', 14)]


def test_increment_events_ignores_transient_big_jump():
    samples = [(0, (5,)), (1, (5,)), (2, (18,)), (3, (5,)),
               (4, (6,)), (5, (6,)), (6, (6,))]
    assert increment_events(samples) == [(4, 'streamer', 6)]


def test_increment_events_small_drop_does_not_reset_baseline():
    samples = [(0, (10,)), (1, (10,)), (2, (11,)), (3, (11,)),
               (4, (11,)), (5, (10,)), (6, (11,)), (7, (11,)), (8, (11,))]
    assert increment_events(samples) == [(2, 'streamer', 11)]


def test_increment_events_big_drop_resets_baseline():
    samples = [(0, (10,)), (1, (10,)), (2, (11,)), (3, (11,)),
               (4, (11,)), (5, (2,)), (6, (2,)), (7, (2,)),
               (8, (2,)), (9, (3,)), (10, (3,)), (11, (3,))]
    assert increment_events(samples) == [(2, 'streamer', 11), (9, 'streamer', 3)]


def test_parse_region_valid():
    assert parse_region("0.1,0.2,0.3,0.4") == (0.1, 0.2, 0.3, 0.4)


def test_parse_region_rejects_out_of_range():
    for bad in ("1.5,0,0.3,0.4", "0,0,0,0.4", "0,0,-1,0.4", "abc"):
        try:
            parse_region(bad)
            raise AssertionError(f"deveria falhar: {bad}")
        except ValueError:
            pass


# ---------------------------------------------------------------------------
# Leitor de ABATES por slot (vetor NCC) com fixtures reais do HUD
# ---------------------------------------------------------------------------

def test_kills_slot_vector_loading_is_none():
    assert _kills_slot_vector(_region_clip(1), ORIGIN, REGION_W) is None


def test_kills_slot_vector_real_clips_non_none():
    for n in (5, 12, 14, 16):
        vec = _slot_vec(n)
        assert vec is not None and vec.shape == (26 * 12,)


def test_kills_slot_vector_same_value_high_ncc():
    # clips 12 e 13: abates 9 -> 9 (queixa do usuário) — vetores ~iguais
    assert _ncc(_slot_vec(12), _slot_vec(13)) >= 0.95


def test_events_from_signatures_no_event_9_to_9():
    v12, v13 = _slot_vec(12), _slot_vec(13)
    samples = [(0, v12), (1, v13), (2, v13), (3, v13)]
    assert _events_from_signatures(samples) == []


def test_events_from_signatures_loading_ignored():
    samples = [(0, None), (1, None), (2, None), (3, None)]
    assert _events_from_signatures(samples) == []


def test_events_from_signatures_real_series():
    # Série GT dos abates: 2,3,5,5,6,6,7,9,9,10,1,1. Na stream cada valor
    # persiste vários frames (fps=1); simula cada valor repetido 3x. Eventos
    # apenas nas MUDANÇAS (3@3, 5@6, 6@12, 7@18, 9@21, 10@27, 1@30-reset).
    seq = [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]
    samples: list = []
    ts = 0
    for n in seq:
        v = _slot_vec(n)
        for _ in range(3):
            samples.append((ts, v))
            ts += 1
    events = _events_from_signatures(samples)
    assert [t for t, _c, _v in events] == [3, 6, 12, 18, 21, 27, 30]


def test_events_from_signatures_reset_after_loading_suppressed():
    # 10 -> 1 depois de tela de loading = reset de partida, não abate
    samples = [(0, _slot_vec(14)), (1, _slot_vec(14)), (2, _slot_vec(14)),
               (3, None), (4, None), (5, None),
               (6, _slot_vec(15)), (7, _slot_vec(15)), (8, _slot_vec(15))]
    assert _events_from_signatures(samples) == []


def test_events_from_signatures_requires_confirmation():
    a = np.linspace(0.1, 0.9, 26 * 12)
    b = a[::-1].copy()
    samples = [(0, a), (1, b), (2, a), (3, a)]  # mudança sem confirmação
    assert _events_from_signatures(samples) == []
    samples = [(0, a), (1, b), (2, b), (3, b)]  # mudança confirmada
    assert _events_from_signatures(samples) == [(1, "streamer", 1)]


def test_kills_slot_vector_blank_is_none():
    blank = np.zeros((30, 210, 3), dtype=np.uint8)
    assert _kills_slot_vector(blank, ORIGIN, REGION_W) is None
