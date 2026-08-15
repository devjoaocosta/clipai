import glob
import os
import re

import yt_dlp

VOD_RE = re.compile(r"twitch\.tv/videos/(\d+)")
VIDEO_EXTS = (".mp4", ".mkv", ".webm", ".flv", ".ts")


class DownloadError(Exception):
    pass


def parse_vod_id(url: str) -> str | None:
    m = VOD_RE.search(url)
    return m.group(1) if m else None


def has_video(formats: list[dict]) -> bool:
    """True se algum formato tem stream de vídeo de verdade.

    Ignora storyboards (sb0/sb1) e Audio_Only, que têm `vcodec == 'none'`.
    VOD subscriber-only só expõe áudio → False.
    """
    return any(f.get("vcodec") and f.get("vcodec") != "none"
               for f in formats or [])


def extract_info(url: str) -> dict:
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
        return ydl.extract_info(url, download=False)


def download_vod(url: str, dest_dir: str, progress_cb=None) -> str:
    os.makedirs(dest_dir, exist_ok=True)

    def hook(d):
        if progress_cb and d.get("status") in ("downloading", "finished"):
            progress_cb(d)

    opts = {
        "format": "bv*[height<=1080]+ba/bv*+ba/b",
        "merge_output_format": "mp4",
        "outtmpl": os.path.join(dest_dir, "vod.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "progress_hooks": [hook],
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
    except yt_dlp.utils.DownloadError as e:
        raise DownloadError(str(e)) from e

    mp4 = os.path.join(dest_dir, "vod.mp4")
    if os.path.exists(mp4) and os.path.getsize(mp4) > 0:
        return mp4

    candidates = [
        f
        for f in glob.glob(os.path.join(dest_dir, "vod.*"))
        if os.path.splitext(f)[1].lower() in VIDEO_EXTS and os.path.getsize(f) > 0
    ]
    if candidates:
        return candidates[0]
    raise DownloadError("Arquivo do VOD não encontrado após o download")
