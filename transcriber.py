import glob
import os
import sys

from log import get_logger

log = get_logger("transcriber")


def _setup_cuda_paths() -> None:
    nv = os.path.join(os.path.dirname(sys.executable), "..", "Lib",
                      "site-packages", "nvidia")
    paths = sorted(glob.glob(os.path.join(nv, "*", "bin")))
    if paths:
        os.environ["PATH"] = os.pathsep.join(paths + [os.environ.get("PATH", "")])


_setup_cuda_paths()


def cuda_available() -> bool:
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


class Transcriber:
    def __init__(self, model: str = "medium", device: str = "auto",
                 compute_type: str = "auto", language: str = "auto",
                 vad_filter: bool = True):
        self.model = model
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self.vad_filter = vad_filter

    def transcribe(self, audio_path: str, keywords: list[str],
                   duration: float, progress_cb=None):
        from faster_whisper import WhisperModel

        device = self.device
        compute_type = self.compute_type
        if device == "auto":
            device = "cuda" if cuda_available() else "cpu"
        if compute_type == "auto":
            compute_type = "float16" if device == "cuda" else "int8"

        log.info("Transcrevendo com faster-whisper (%s, device=%s, "
                 "compute=%s)...", self.model, device, compute_type)

        try:
            model = WhisperModel(self.model, device=device, compute_type=compute_type)
        except Exception as e:
            if device == "cuda":
                log.warning("Falha ao usar CUDA (%s). Fazendo fallback para "
                            "CPU int8.", e)
                device, compute_type = "cpu", "int8"
                model = WhisperModel(self.model, device="cpu", compute_type="int8")
            else:
                raise

        language = None if self.language in ("auto", "") else self.language
        initial_prompt = ", ".join(keywords) + "."
        segments, info = model.transcribe(
            audio_path,
            language=language,
            word_timestamps=True,
            vad_filter=self.vad_filter,
            initial_prompt=initial_prompt,
            beam_size=5,
        )

        words: list[tuple[float, float, str]] = []
        for seg in segments:
            if seg.words:
                words.extend((w.start, w.end, w.word) for w in seg.words)
            if progress_cb and duration:
                progress_cb(seg.end / duration)
        return words, info
