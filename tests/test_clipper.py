import json
import os
import subprocess

import clipper
from clipper import _verify_clip

FIX_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
SOURCE = os.path.join(FIX_DIR, "clip_source.mp4")


def _probe_json(path: str) -> dict:
    out = subprocess.check_output([
        clipper._which("ffprobe"), "-v", "error",
        "-show_entries", "format=duration,start_time",
        "-show_entries", "stream=codec_type,time_base,index",
        "-show_entries", "packet=dts,stream_index",
        "-of", "json", path,
    ])
    return json.loads(out.decode())


def test_cut_clip_standard_container(tmp_path):
    out = tmp_path / "clip.mp4"
    clipper.cut_clip(SOURCE, str(out), 0.5, 1.0)

    data = _probe_json(str(out))
    streams = data["streams"]
    assert [s["codec_type"] for s in streams] == ["video", "audio"]
    vid = next(s for s in streams if s["codec_type"] == "video")
    assert vid["time_base"] == "1/90000"

    fmt = data["format"]
    assert abs(float(fmt["start_time"])) <= 0.05
    assert abs(float(fmt["duration"]) - 1.0) <= 0.5

    vp = [p for p in data["packets"] if p["stream_index"] == vid["index"]]
    assert vp and vp[0]["dts"] >= 0

    assert _verify_clip(str(out), 1.0) == (True, "ok")


def test_cut_clip_video_only_source_optional_audio(tmp_path):
    src = tmp_path / "video_only.mp4"
    subprocess.check_call([
        clipper._which("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i",
        "color=c=black:size=160x120:rate=10:duration=1",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src),
    ])
    out = tmp_path / "clip_video_only.mp4"
    clipper.cut_clip(str(src), str(out), 0.0, 0.5)

    data = _probe_json(str(out))
    assert [s["codec_type"] for s in data["streams"]] == ["video"]
    assert _verify_clip(str(out), 0.5)[0]


def test_verify_clip_rejects_garbage(tmp_path):
    bad = tmp_path / "bad.mp4"
    bad.write_text("isto não é um vídeo")
    ok, msg = _verify_clip(str(bad), 1.0)
    assert not ok
    assert msg


def _make_av_fixture(path, size, rate=30, duration=2.0, audio=True):
    cmd = [
        clipper._which("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i",
        f"testsrc2=size={size[0]}x{size[1]}:rate={rate}:duration={duration}",
    ]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-video_track_timescale", "90000"]
    if audio:
        cmd += ["-c:a", "aac", "-shortest"]
    cmd += [str(path)]
    subprocess.check_call(cmd)
    return str(path)


def test_ensure_1080p_transcodes_1440(tmp_path):
    src = _make_av_fixture(tmp_path / "vod_1440.mp4", (2560, 1440))
    working, original = clipper.ensure_1080p(src, str(tmp_path))
    assert working != original
    assert clipper.video_size(working) == (1920, 1080)
    data = _probe_json(working)
    assert [s["codec_type"] for s in data["streams"]] == ["video", "audio"]
    src_dur = float(_probe_json(src)["format"]["duration"])
    out_dur = float(data["format"]["duration"])
    assert abs(out_dur - src_dur) <= 0.5
    assert _verify_clip(working, src_dur) == (True, "ok")


def test_ensure_1080p_keeps_720p(tmp_path):
    src = _make_av_fixture(tmp_path / "vod_720.mp4", (1280, 720), duration=1.0)
    working, original = clipper.ensure_1080p(src, str(tmp_path))
    assert working == original == src
    assert clipper.video_size(src) == (1280, 720)


def test_cut_clip_caps_height_1440(tmp_path):
    src = _make_av_fixture(tmp_path / "vod_1440.mp4", (2560, 1440), duration=1.5)
    out = tmp_path / "clip_1440.mp4"
    clipper.cut_clip(src, str(out), 0.0, 1.0)
    assert clipper.video_size(str(out)) == (1920, 1080)
    assert _verify_clip(str(out), 1.0) == (True, "ok")


def test_verify_clip_rejects_oversized_1440(tmp_path):
    src = _make_av_fixture(tmp_path / "vod_1440.mp4", (2560, 1440), duration=1.0)
    assert _verify_clip(src, 1.0)[0] is False
    assert "altura" in _verify_clip(src, 1.0)[1]


def test_video_size_rejects_audio_only(tmp_path):
    audio = tmp_path / "audio_only.m4a"
    subprocess.check_call([
        clipper._which("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
        "-c:a", "aac", str(audio),
    ])
    try:
        clipper.video_size(str(audio))
        assert False, "video_size deveria ter falhado"
    except RuntimeError as e:
        assert "stream de vídeo" in str(e)
    except Exception as e:
        assert False, f"esperava RuntimeError claro, veio {type(e).__name__}: {e}"
