from dataclasses import dataclass, field


@dataclass
class Config:
    url: str = ""
    local_file: str = ""
    keywords: str = "double kill, triple kill, quadra kill, pentakill, ace, lendário"
    model: str = "medium"
    language: str = "auto"
    device: str = "auto"
    compute_type: str = "auto"
    offset_before: float = 5.0
    clip_length: float = 30.0
    merge_window: float = 10.0
    fuzzy_threshold: float = 0.72
    vad_filter: bool = True
    mode: str = "both"
    kill_fps: float = 1.0
    kill_region: str = "0.785,0.004,0.110,0.028"
    output_dir: str = "output"
    work_dir: str = "work"
    delete_vod: bool = True

    @property
    def keyword_list(self) -> list[str]:
        return [k.strip() for k in self.keywords.split(",") if k.strip()]


MODEL_SIZES = ["tiny", "base", "small", "medium", "large-v3"]
LANGUAGES = ["auto", "pt", "en"]
MODE_CHOICES = ["keywords", "kills", "both"]
