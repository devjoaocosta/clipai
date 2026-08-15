import downloader


def test_has_video_false_audio_only():
    fmts = [
        {"format_id": "sb0", "vcodec": "none", "acodec": "none"},
        {"format_id": "sb1", "vcodec": "none", "acodec": "none"},
        {"format_id": "Audio_Only", "vcodec": "none", "acodec": "mp4a.40.2"},
    ]
    assert downloader.has_video(fmts) is False


def test_has_video_true_with_video():
    fmts = [
        {"format_id": "sb0", "vcodec": "none"},
        {"format_id": "Audio_Only", "vcodec": "none"},
        {"format_id": "720p", "vcodec": "avc1", "acodec": "mp4a.40.2"},
    ]
    assert downloader.has_video(fmts) is True


def test_has_video_empty():
    assert downloader.has_video([]) is False
    assert downloader.has_video(None) is False
