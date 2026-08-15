from config import Config
from worker import Worker


def _make_worker(local_file: str) -> Worker:
    cfg = Config(url="", local_file=local_file, delete_vod=True)
    return Worker(cfg, lambda ev: None)


def test_cleanup_never_deletes_local_file(tmp_path):
    local = tmp_path / "meu_vod.mp4"
    local.write_bytes(b"fake")
    working = tmp_path / "vod_1080.mp4"
    working.write_bytes(b"fake")

    w = _make_worker(str(local))
    w._is_local = True
    w._vod_original = str(local)
    w._cleanup(str(working))

    assert local.exists()
    assert not working.exists()


def test_cleanup_local_sem_transcode_keeps_file(tmp_path):
    local = tmp_path / "meu_vod.mp4"
    local.write_bytes(b"fake")

    w = _make_worker(str(local))
    w._is_local = True
    w._vod_original = str(local)
    w._cleanup(str(local))

    assert local.exists()


def test_cleanup_download_ainda_deleta(tmp_path):
    vod = tmp_path / "vod.mp4"
    vod.write_bytes(b"fake")
    original = tmp_path / "vod_original.mp4"
    original.write_bytes(b"fake")

    w = _make_worker("")
    w._is_local = False
    w._vod_original = str(original)
    w._cleanup(str(vod))

    assert not vod.exists()
    assert not original.exists()
