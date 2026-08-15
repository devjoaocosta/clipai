import json
from dataclasses import dataclass, fields

CONFIG_FILE = "config.json"

# Campos por sessão (URL/arquivo local não devem ser persistidos).
_SESSION_FIELDS = ("url", "local_file")


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

    def save(self, path: str = CONFIG_FILE) -> None:
        data = {
            f.name: getattr(self, f.name)
            for f in fields(self)
            if f.name not in _SESSION_FIELDS
        }
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)

    @classmethod
    def from_file(cls, path: str = CONFIG_FILE) -> "Config":
        cfg = cls()
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return cfg
        if not isinstance(data, dict):
            return cfg
        known = {f.name for f in fields(cls)}
        for key, value in data.items():
            if key in known and not isinstance(value, dict):
                setattr(cfg, key, value)
        return cfg


MODEL_SIZES = ["tiny", "base", "small", "medium", "large-v3"]
LANGUAGES = ["auto", "pt", "en"]
MODE_CHOICES = ["keywords", "kills", "both"]
