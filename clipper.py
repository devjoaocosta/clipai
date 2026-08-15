import json
import os
import shutil
import subprocess

from log import get_logger

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
log = get_logger("clipper")

# Altura máxima de saída: VOD acima disso (1440p/1600p/4K) é reduzido para 1080p.
MAX_OUTPUT_HEIGHT = 1080


def _which(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"Binário '{name}' não encontrado. Instale o ffmpeg "
                           "(ex.: winget install Gyan.FFmpeg).")
    return path


def ffprobe_duration(path: str) -> float:
    cmd = [
        _which("ffprobe"), "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path,
    ]
    out = subprocess.check_output(cmd, creationflags=CREATE_NO_WINDOW)
    return float(out.decode().strip())


def _video_frame_rate(path: str) -> float:
    cmd = [
        _which("ffprobe"), "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=avg_frame_rate",
        "-of", "csv=p=0", path,
    ]
    out = subprocess.check_output(cmd, creationflags=CREATE_NO_WINDOW)
    text = out.decode().strip()
    if "/" not in text:
        return 0.0
    num, den = text.split("/")
    return float(num) / float(den) if float(den) else 0.0


def video_size(path: str) -> tuple[int, int]:
    """Devolve (largura, altura) do primeiro stream de vídeo.

    Sem stream de vídeo (ex.: arquivo só de áudio de VOD subscriber-only),
    sobe RuntimeError com mensagem clara em vez de int('').
    """
    cmd = [
        _which("ffprobe"), "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", path,
    ]
    out = subprocess.check_output(cmd, creationflags=CREATE_NO_WINDOW)
    text = out.decode().strip()
    if "x" not in text or not text.split("x")[0].isdigit():
        raise RuntimeError(
            "VOD sem stream de vídeo — provavelmente restrito a assinantes "
            "(subscriber-only); o Twitch só expõe o áudio sem login")
    w, h = (int(v) for v in text.split("x"))
    return w, h


def cut_clip(vod_path: str, out_path: str, start: float, length: float) -> None:
    """Corta um trecho do VOD com encode amigável a editores de vídeo.

    O H.264 gerado é padrão MP4: timescale 1/90000, timestamps começando em 0
    (sem DTS negativo), CFR, GOP curto (2s), yuv420p/high/level 4.1, moov na
    frente (faststart) e SEM B-frames (-bf 0). B-frames no início de um corte
    são descartados (sem referência anterior) → vídeo começa alguns quadros
    depois e o Premiere/After Effects desalinha a paridade dos frames; -bf 0
    elimina a reordenação e o offset de início de vez.
    """
    fps = _video_frame_rate(vod_path)
    cmd = [
        _which("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{start:.3f}", "-i", vod_path,
        "-t", f"{length:.3f}",
        "-map", "0:v:0?", "-map", "0:a:0?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.1",
        "-fps_mode", "cfr", "-r", f"{fps:.2f}",
        "-g", "120", "-keyint_min", "120", "-bf", "0",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-video_track_timescale", "90000",
        "-avoid_negative_ts", "make_zero",
        "-muxpreload", "0", "-muxdelay", "0",
        "-movflags", "+faststart",
        "-threads", "0",
        out_path,
    ]
    _, height = video_size(vod_path)
    if height > MAX_OUTPUT_HEIGHT:
        idx = cmd.index("-map")
        cmd[idx:idx] = ["-vf", f"scale=-2:{MAX_OUTPUT_HEIGHT},setsar=1"]
    subprocess.run(cmd, check=True, creationflags=CREATE_NO_WINDOW)
    ok, msg = _verify_clip(out_path, length, max_height=MAX_OUTPUT_HEIGHT)
    if not ok:
        log.warning("AVISO: clipe %s com problema: %s", out_path, msg)


def _verify_clip(out_path: str, expected_length: float,
                 tolerance: float = 0.5,
                 max_height: int = MAX_OUTPUT_HEIGHT) -> tuple[bool, str]:
    """Verifica se o clipe é um MP4 padrão e saudável.

    Checa: stream de vídeo presente, time_base 1/90000, start_time ~= 0,
    duração dentro da esperada, altura <= max_height e primeiro pacote de
    vídeo com dts >= 0. Devolve (ok, mensagem).
    """
    try:
        out = subprocess.check_output([
            _which("ffprobe"), "-v", "error",
            "-show_entries", "format=duration,start_time",
            "-show_entries", "stream=codec_type,time_base,height",
            "-show_entries", "packet=dts,stream_index",
            "-of", "json", out_path,
        ], creationflags=CREATE_NO_WINDOW)
        data = json.loads(out.decode())
    except Exception as e:
        return False, f"não foi possível ler o clipe: {e}"

    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None:
        return False, "sem stream de vídeo"
    if video.get("time_base") != "1/90000":
        return False, f"time_base {video.get('time_base')} (esperado 1/90000)"
    if video.get("height", 0) > max_height:
        return False, (f"altura {video.get('height')} > limite "
                       f"{max_height}")

    fmt = data.get("format", {})
    try:
        start = float(fmt.get("start_time", "1"))
        duration = float(fmt.get("duration", "0"))
    except ValueError:
        return False, "duração/start_time inválidos"
    if abs(start) > 0.05:
        return False, f"start_time {start:.3f}s (esperado ~0)"
    if duration < expected_length - tolerance:
        return False, (f"duração {duration:.2f}s < esperado "
                       f"{expected_length - tolerance:.2f}s")

    vid_idx = video.get("index")
    packets = [p for p in data.get("packets", [])
               if p.get("stream_index") == vid_idx]
    if packets and packets[0].get("dts", 0) < 0:
        return False, f"primeiro pacote com dts negativo ({packets[0]['dts']})"

    return True, "ok"


def ensure_1080p(vod_path: str, work_dir: str,
                 max_height: int = MAX_OUTPUT_HEIGHT,
                 progress_cb=None) -> tuple[str, str]:
    """Garante um VOD de trabalho com altura <= max_height.

    Se a altura já for <= max_height, devolve (vod_path, vod_path) sem tocar
    no arquivo. Caso contrário transcoda para `work_dir/vod_1080.mp4` (decode
    por hardware d3d11va com fallback software) e devolve
    (working, original). Em falha, loga e devolve o original (o cap do
    `cut_clip` ainda garante clipes 1080p). `progress_cb(fraction)` recebe o
    progresso real da transcode (0..1).
    """
    try:
        height = video_size(vod_path)[1]
    except Exception as e:
        log.warning("não foi possível medir o VOD (%s); seguindo sem transcode.", e)
        return vod_path, vod_path
    if height <= max_height:
        return vod_path, vod_path

    out_path = os.path.join(work_dir, "vod_1080.mp4")
    os.makedirs(work_dir, exist_ok=True)
    duration = 0.0
    try:
        duration = ffprobe_duration(vod_path)
    except Exception:
        pass
    log.info("VOD com altura %s > %s: transcodando para %sp...",
             height, max_height, max_height)

    cmd_base = [
        _which("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error", "-nostdin",
        "-i", vod_path,
        "-map", "0:v:0?", "-map", "0:a:0?",
        "-vf", f"scale=-2:{max_height},setsar=1",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.1",
        "-c:a", "copy",
        "-video_track_timescale", "90000",
        "-avoid_negative_ts", "make_zero",
        "-muxpreload", "0", "-muxdelay", "0",
        "-threads", "0",
        "-progress", "pipe:1",
        out_path,
    ]
    proc = None
    for hwaccel in (True, False):
        cmd = list(cmd_base)
        if hwaccel:
            cmd[2:2] = ["-hwaccel", "d3d11va"]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL,
                                creationflags=CREATE_NO_WINDOW)
        out_time_us = 0.0
        try:
            assert proc.stdout is not None
            for raw in proc.stdout:
                line = raw.decode(errors="replace").strip()
                if line.startswith("out_time_us="):
                    try:
                        out_time_us = float(line.split("=", 1)[1].strip())
                    except ValueError:
                        pass
                if progress_cb is not None and duration > 0:
                    progress_cb(min(out_time_us / 1_000_000 / duration, 1.0))
        except Exception:
            pass
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait()
            if proc.stdout is not None:
                proc.stdout.close()
        if hwaccel and proc.returncode != 0:
            continue
        break
    if proc is None or proc.returncode != 0:
        log.warning("transcode falhou; usando o VOD original.")
        return vod_path, vod_path

    ok, msg = _verify_clip(out_path, duration, max_height=max_height)
    if not ok:
        log.warning("transcode não passou na verificação (%s); "
                    "usando o VOD original.", msg)
        return vod_path, vod_path
    if progress_cb is not None:
        progress_cb(1.0)
    return out_path, vod_path
