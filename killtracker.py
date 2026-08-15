import os
import re
import shutil
import subprocess

import numpy as np
import pytesseract
from PIL import Image

from clipper import _which, video_size

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

DEFAULT_REGION = "0.785,0.004,0.110,0.028"
CONFIRM_FRAMES = 3
MAX_KILL_JUMP = 5

# Faixa (fração absoluta de x) da coluna do streamer na linha superior direita.
# Layout: [kills time] [vs] [kills time] [KDA do streamer].
# A coluna do streamer mostra K/D/A (ex.: "3/5/11"); lemos o PRIMEIRO número
# (kills). Banda medida nos frames reais do VOD de teste.
KILL_COLUMNS = [
    ("streamer", 0.865, 0.895),
]

# Slot de ABATES do streamer (1º número do K/D/A): banda global x [0.846, 0.858].
# Glifos do HUD são CLAROS sobre fundo escuro (thr alto separa bem). Medido nos
# frames reais: dígito único em x ~0.8486-0.8527; dois dígitos ("10"..) em
# 0.8491-0.8512 + 0.8522-0.8563. Telas de loading/pós-jogo → banda vazia.
KILLS_SLOT_X = (0.846, 0.858)
KILLS_GLYPH_THR = 80
# NCC do vetor 12x26 normalizado: MESMO valor >= 0.997, valores diferentes
# <= 0.93 nos frames reais → 0.95 separa com folga.
KILLS_SAME_NCC = 0.95
# Frames None (HUD oculto) seguidos antes de uma mudança → reset de partida.
KILLS_RESET_GAP = 3


def _locate_tesseract() -> str:
    path = shutil.which("tesseract")
    if path:
        return path
    candidates = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    raise RuntimeError(
        "tesseract não encontrado. Instale com: winget install "
        "UB-Mannheim.TesseractOCR")


_TESSERACT_PATH: str | None = None


def _ensure_tesseract() -> None:
    global _TESSERACT_PATH
    if _TESSERACT_PATH is None:
        _TESSERACT_PATH = _locate_tesseract()
        pytesseract.pytesseract.tesseract_cmd = _TESSERACT_PATH


def parse_region(region: str) -> tuple[float, float, float, float]:
    x, y, w, h = (float(v) for v in region.split(","))
    if not (0 <= x < 1 and 0 <= y < 1 and 0 < w <= 1 and 0 < h <= 1):
        raise ValueError(f"região inválida: {region} (use frações x,y,w,h de 0 a 1)")
    return x, y, w, h


def _build_extract_cmd(vod_path: str, region: str, fps: float,
                       hwaccel: bool) -> tuple[list[str], int, int, int, int]:
    width, height = video_size(vod_path)
    fx, fy, fw, fh = parse_region(region)
    px, py = int(fx * width), int(fy * height)
    pw, ph = max(1, int(fw * width)) // 2 * 2, max(1, int(fh * height)) // 2 * 2
    cmd = [
        _which("ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin",
    ]
    if hwaccel:
        cmd += ["-hwaccel", "d3d11va"]
    cmd += ["-i", vod_path, "-an"]
    cmd += [
        "-vf", f"fps={fps},crop={pw}:{ph}:{px}:{py}",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
    ]
    return cmd, px, py, pw, ph


def extract_frames(vod_path: str, region: str, fps: float,
                   stop_event=None) -> "generator[tuple[float, np.ndarray]]":
    """Amostra frames da região a `fps`. Usa decode por hardware (d3d11va)
    quando disponível, com fallback para decode por software."""
    for hwaccel in (True, False):
        cmd, px, py, pw, ph = _build_extract_cmd(vod_path, region, fps, hwaccel)
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL,
                                creationflags=CREATE_NO_WINDOW)
        frame_size = pw * ph * 3
        idx = 0
        try:
            first = proc.stdout.read(frame_size)
            if not first or len(first) < frame_size:
                proc.kill()
                proc.wait()
                continue
            yield idx / fps, np.frombuffer(first, dtype=np.uint8).reshape(ph, pw, 3)
            idx += 1
            while True:
                if stop_event is not None and stop_event.is_set():
                    proc.kill()
                    break
                buf = proc.stdout.read(frame_size)
                if not buf or len(buf) < frame_size:
                    break
                yield idx / fps, np.frombuffer(buf, dtype=np.uint8).reshape(ph, pw, 3)
                idx += 1
            return
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.stdout.close()
            proc.wait()


def _ncc(a: np.ndarray, b: np.ndarray) -> float:
    """Correlação normalizada (z-score) entre dois vetores iguais."""
    denom = np.sqrt(a.dot(a) * b.dot(b))
    return float(a.dot(b) / denom) if denom > 0 else 0.0


def _kills_slot_vector(img: np.ndarray, x_origin: float,
                       region_w: float) -> np.ndarray | None:
    """Vetor normalizado do glifo de abates (slot global [0.846, 0.858]).

    Recorta a banda, autocorta verticalmente e normaliza para 12x26 (z-score).
    O vetor é ESTÁVEL entre frames do mesmo valor (NCC >= 0.997) e distinto
    entre valores diferentes (NCC <= 0.93) — por isso a detecção de eventos
    compara o vetor por NCC em vez de classificar o dígito (inviável: os
    glifos de 8px são ilegíveis até por OCR). Banda vazia (loading/pós-jogo)
    devolve None.
    """
    lo = (KILLS_SLOT_X[0] - x_origin) / region_w
    hi = (KILLS_SLOT_X[1] - x_origin) / region_w
    w = img.shape[1]
    c0 = int(lo * w)
    c1 = max(c0 + 1, int(hi * w))
    gray = img[:, c0:c1].mean(axis=2)
    mask = gray > KILLS_GLYPH_THR
    rows = mask.any(axis=1)
    if not rows.any():
        return None
    r0 = int(np.argmax(rows))
    r1 = int(len(rows) - np.argmax(rows[::-1]))
    r0 = max(0, r0 - 1)
    r1 = min(len(rows), r1 + 1)
    crop = gray[r0:r1].astype(np.uint8)
    small = np.array(Image.fromarray(crop).resize((26, 12), Image.LANCZOS),
                     dtype=np.float64).ravel()
    small = (small - small.min()) / max(1e-6, small.max() - small.min())
    return small - small.mean()


def _events_from_signatures(samples: list[tuple[float, np.ndarray | None]],
                            confirm_frames: int = CONFIRM_FRAMES,
                            reset_gap: int = KILLS_RESET_GAP
                            ) -> list[tuple[float, str, int]]:
    """Dispara quando o glifo de ABATES muda e persiste por `confirm_frames`.

    - Mesmo vetor (NCC >= KILLS_SAME_NCC) → nada (inclui mortes mudando).
    - Mudança persistente → evento (abate confirmado).
    - Mudança precedida por >= `reset_gap` frames None (HUD oculto) → reset
      de partida: vira baseline novo SEM evento.
    - Frames None → ignora (telas de loading/pós-jogo).

    O total do evento é um contador de abates detectados (a leitura do dígito
    é inviável; só o log usa o total). Retorna (ts, coluna, total).
    """
    events: list[tuple[float, str, int]] = []
    last: np.ndarray | None = None
    pending: np.ndarray | None = None
    pending_ts = 0.0
    pending_count = 0
    pending_gap = 0
    none_streak = 0
    count = 0
    for ts, vec in samples:
        if vec is None:
            none_streak += 1
            continue
        if last is None:
            last = vec
            continue
        if _ncc(last, vec) >= KILLS_SAME_NCC:
            pending = None
            pending_count = 0
            none_streak = 0
            continue
        if pending is None or _ncc(pending, vec) < KILLS_SAME_NCC:
            pending = vec
            pending_ts = ts
            pending_count = 1
            pending_gap = none_streak
            none_streak = 0
            continue
        pending_count += 1
        none_streak = 0
        if pending_count >= confirm_frames:
            if pending_gap < reset_gap:
                count += 1
                events.append((pending_ts, "streamer", count))
            last = vec
            pending = None
            pending_count = 0
    return events


def _inverted_gray(img: np.ndarray) -> Image.Image:
    from PIL import ImageOps
    return ImageOps.invert(Image.fromarray(img).convert("L"))


_DIGIT_FIX = {
    "/": "7", "l": "1", "I": "1", "|": "1", "i": "1",
    "o": "0", "O": "0", "Q": "0", "S": "5", "s": "5",
    "B": "8", "b": "8", "g": "9", "G": "6", "Z": "2", "z": "2",
}


def _fix_digits(text: str) -> str:
    return "".join(_DIGIT_FIX.get(ch, ch) for ch in text)


def _as_kill_value(text: str) -> int | None:
    fixed = _fix_digits(text)
    digits = re.sub(r"[^0-9]", "", fixed)
    if not digits:
        return None
    value = int(digits)
    if value > 150:
        return None
    return value


def _as_kda_kills(text: str) -> int | None:
    """Extrai KILLS (primeiro número) de um KDA tipo "3/5/11".

    O OCR do HUD lê a coluna do streamer como K/D/A (ex.: "3/5/11", "8/11/",
    "#6", "10."). Separamos no primeiro segmento (por "/", espaço ou "."),
    corrigimos dígitos ambíguos e extraímos o inteiro. Não passa por
    `_as_kill_value` direto, senão "/" viraria "7" e juntaria tudo.
    """
    first = re.split(r"[/\s.]+", text, maxsplit=1)[0]
    # Token sem dígito real é separador do placar (ex.: "|" em "28 vs 30 | #9"),
    # não um KDA. Rejeita antes de qualquer correção, senão _fix_digits
    # transformaria "|" em "1" e travaria o contador.
    if not re.search(r"\d", first):
        return None
    # OCR pode fundir separador + KDA ("|#9"); remove não-dígitos à esquerda
    # mantendo os dígitos do primeiro número.
    first = re.sub(r"^[^0-9]+", "", first)
    fixed = _fix_digits(first)
    digits = re.sub(r"[^0-9]", "", fixed)
    if not digits:
        return None
    value = int(digits)
    if value > 150:
        return None
    return value


def _column_value(name: str, text: str) -> int | None:
    if name == "streamer":
        return _as_kda_kills(text)
    return _as_kill_value(text)


def _ocr_groups(img: np.ndarray) -> list[tuple[int, int, str]]:
    _ensure_tesseract()
    pil = _inverted_gray(img)
    pil = pil.resize((pil.width * 3, pil.height * 3), Image.LANCZOS)
    data = pytesseract.image_to_data(
        pil, config="--psm 6", output_type=pytesseract.Output.DICT)
    out: list[tuple[int, int, str]] = []
    for i, text in enumerate(data["text"]):
        text = text.strip()
        if not text:
            continue
        out.append((data["left"][i] // 3, data["width"][i] // 3, text))
    return out


def _token_global_span(img: np.ndarray, left: int, width: int,
                       x_origin: float, region_w: float) -> tuple[float, float]:
    w = img.shape[1]
    return (x_origin + (left / w) * region_w,
            x_origin + ((left + width) / w) * region_w)


def _split_wide_token(text: str, n: int,
                      parser=_as_kill_value) -> list[int | None]:
    digits = re.sub(r"[^0-9]", "", _fix_digits(text))
    if not digits:
        return [None] * n
    if n <= 1 or len(digits) <= 1:
        parts: list[int | None] = [None] * (n - 1)
        parts.append(parser(text))
        return parts
    k = len(digits) // n
    parts = []
    for i in range(n):
        chunk = digits[i * k: i * k + k] if i < n - 1 else digits[(n - 1) * k:]
        if chunk:
            v = int(chunk)
            parts.append(v if v <= 150 else None)
        else:
            parts.append(None)
    return parts


def parse_kill_total(img: np.ndarray, x_origin: float = 0.0,
                     region_w: float = 1.0) -> tuple[int, ...] | None:
    """Lê as kills do streamer (1ª número do KDA) da faixa superior direita.

    A coluna é lida num recorte (banda) isolado por OCR psm 6, escolhendo o
    token mais próximo do centro da banda. Isso evita que o OCR de linha
    inteira funda colunas vizinhas. Se a banda não achar valor, cai no
    token-span (o token que cruza a coluna). Devolve uma tupla com um elemento
    por coluna em `KILL_COLUMNS` (hoje só a do streamer), ou `None`.
    """
    groups = _ocr_groups(img)
    values = tuple(
        _band_value(img, groups, name, x_origin, region_w)
        for name, _lo, _hi in KILL_COLUMNS
    )
    if all(v is None for v in values):
        return None
    return values


def _band_value(img: np.ndarray, groups: list[tuple[int, int, str]],
                name: str, x_origin: float, region_w: float) -> int | None:
    """Lê o valor da coluna `name` a partir dos tokens OCR da região inteira.

    Seleciona os tokens cujo span global cruza a banda `[blo, bhi]` da coluna
    e devolve o valor do token **mais à esquerda** (menor x). Na coluna KDA do
    streamer a kill é o primeiro (esquerdo) número do K/D/A; escolher por
    proximidade do centro da banda pegava a morte (número central) quando o
    OCR lia os números separados (`3`, `5`, `11`). Tokens com centro fora da
    banda (ex.: kills do time azul invadindo a borda) só são usados como
    fallback. Não re-OCRa um recorte isolado: na coluna KDA o recorte estreito
    fragmenta tokens (ex.: `3/5/11` → `1`).
    """
    _name, blo, bhi = next(c for c in KILL_COLUMNS if c[0] == name)
    in_band: list[tuple[float, int]] = []
    crossing: list[tuple[float, int]] = []
    for left, width, text in groups:
        lo, hi = _token_global_span(img, left, width, x_origin, region_w)
        if lo >= bhi or hi <= blo:
            continue
        touched = [c for c, cl, ch in KILL_COLUMNS if lo < ch and hi > cl]
        for col, value in zip(touched, _split_wide_token(
                text, len(touched), lambda t: _column_value(name, t))):
            if col != name or value is None:
                continue
            cx = (lo + hi) / 2
            (in_band if blo <= cx <= bhi else crossing).append((cx, value))
    if in_band:
        return min(in_band, key=lambda t: t[0])[1]
    if crossing:
        return min(crossing, key=lambda t: t[0])[1]
    return None


def increment_events(samples: list[tuple[float, tuple[int, ...] | None]],
                     confirm_frames: int = CONFIRM_FRAMES) -> list[tuple[float, str, int]]:
    """Dispara quando a KILL do streamer (1ª número do KDA) incrementa.

    - Saltos de até MAX_KILL_JUMP confirmados em `confirm_frames` → evento.
    - Saltos grandes podem ser misread do OCR OU lacuna de cobertura (placar
      oculto): só viram novo baseline (sem evento) se persistirem por
      `confirm_frames`; caso contrário são ignorados. Isso evita travar o
      tracker em baseline obsoleto (wedging).
    - Queda PEQUENA (≤ MAX_KILL_JUMP) NÃO reseta o baseline: dentro de uma
      partida o placar só sobe, então queda pequena é misread do OCR e deve
      ser ignorada (evita re-disparar o mesmo total após um frame ruim).
    - Queda GRANDE (> MAX_KILL_JUMP) é reset de partida: vira baseline novo
      se persistir por `confirm_frames`.

    Retorna eventos como (ts, coluna, total).
    """
    events: list[tuple[float, str, int]] = []
    state: dict[str, dict] = {}
    for ts, values in samples:
        if values is None:
            continue
        for (name, _lo, _hi), value in zip(KILL_COLUMNS, values):
            if value is None:
                continue
            st = state.setdefault(name, {"last": None, "pending": None})
            last = st["last"]
            if last is None:
                st["last"] = value
                continue
            if value == last:
                st["pending"] = None
                continue
            if value > last:
                if value - last <= MAX_KILL_JUMP:
                    p = st["pending"]
                    if p is not None and not p["done"] \
                            and p["value"] == value and not p["big"]:
                        p["count"] += 1
                        if p["count"] >= confirm_frames:
                            events.append((p["first_ts"], name, value))
                            p["done"] = True
                            st["last"] = value
                    else:
                        st["pending"] = {"value": value, "first_ts": ts,
                                         "count": 1, "done": False,
                                         "big": False}
                else:
                    p = st["pending"]
                    if p is not None and p["big"] and p["value"] == value:
                        p["count"] += 1
                        if p["count"] >= confirm_frames:
                            st["last"] = value
                            st["pending"] = None
                    else:
                        st["pending"] = {"value": value, "first_ts": ts,
                                         "count": 1, "done": True,
                                         "big": True}
            else:
                diff = last - value
                if diff <= MAX_KILL_JUMP:
                    # queda pequena: misread provável; mantém baseline
                    st["pending"] = None
                    continue
                # queda grande: reset de partida; vira baseline se persistir
                p = st["pending"]
                if p is not None and p["big"] and p["value"] == value \
                        and p["done"]:
                    p["count"] += 1
                    if p["count"] >= confirm_frames:
                        st["last"] = value
                        st["pending"] = None
                else:
                    st["pending"] = {"value": value, "first_ts": ts,
                                     "count": 1, "done": True, "big": True}
    return events


def save_sample(img: np.ndarray, path: str) -> None:
    Image.fromarray(img).resize((img.shape[1] * 3, img.shape[0] * 3),
                                Image.LANCZOS).save(path)


def save_full_frames(vod_path: str, work_dir: str, duration: float) -> list[str]:
    points = [0.0, duration / 2, max(0.0, duration - 1.0)]
    saved: list[str] = []
    for i, ts in enumerate(points):
        out = os.path.join(work_dir, f"frame_full_{i}.jpg")
        cmd = [
            _which("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error",
            "-ss", f"{ts:.1f}", "-i", vod_path, "-frames:v", "1",
            "-q:v", "4", out,
        ]
        try:
            subprocess.run(cmd, check=True, creationflags=CREATE_NO_WINDOW)
            saved.append(out)
        except subprocess.CalledProcessError:
            pass
    return saved


def detect_kill_events(vod_path: str, region: str = DEFAULT_REGION,
                       fps: float = 1.0, confirm_frames: int = CONFIRM_FRAMES,
                       work_dir: str = "work", progress_cb=None,
                       log_cb=None, stop_event=None) -> list[tuple[float, str, int]]:
    os.makedirs(work_dir, exist_ok=True)
    duration = 0.0
    try:
        from clipper import ffprobe_duration
        duration = ffprobe_duration(vod_path)
    except Exception:
        duration = 0.0

    if log_cb is not None:
        log_cb(f"killtracker: região {region} a {fps} fps; "
               f"amostras de calibração em {work_dir}")
    save_full_frames(vod_path, work_dir, duration)

    fx, _fy, fw, _fh = parse_region(region)
    samples: list[tuple[float, np.ndarray | None]] = []
    failed_streak = 0
    frame_count = 0
    total_frames = int(duration * fps) or 1
    saved_sample = False

    for ts, img in extract_frames(vod_path, region, fps, stop_event):
        frame_count += 1
        if progress_cb is not None:
            progress_cb(min(frame_count / total_frames, 1.0))
        if not saved_sample:
            save_sample(img, os.path.join(work_dir, "frame_sample.png"))
            saved_sample = True
        try:
            vec = _kills_slot_vector(img, fx, fw)
        except Exception as e:
            vec = None
            if log_cb is not None:
                log_cb(f"killtracker: falha no frame {frame_count}: {e}")
        if vec is None:
            failed_streak += 1
        else:
            failed_streak = 0
        samples.append((ts, vec))

    if failed_streak >= max(5, frame_count // 4) and log_cb is not None:
        log_cb("killtracker: placar não reconhecido em vários frames. "
               f"Ajuste a região de leitura e confira {work_dir}/frame_sample.png")
    return _events_from_signatures(samples, confirm_frames)
