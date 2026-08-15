import csv
import os
import re
import threading
from dataclasses import dataclass

import clipper
import downloader
import killtracker
from config import Config
from log import get_logger
from matcher import Word, clip_window, find_matches, near_misses, ts
from transcriber import Transcriber

log = get_logger("worker")

NO_VIDEO_MSG = ("VOD sem vídeo disponível. O VOD é restrito a assinantes "
                "(subscriber-only) — o Twitch só expõe o áudio sem login. "
                "Use uma conta assinante (cookies) ou outro VOD.")


@dataclass
class ClipResult:
    index: int
    keyword: str
    keyword_time: float
    clip_start: float
    clip_end: float
    file: str


def merge_moments(moments: list[tuple[float, str]],
                  merge_window: float) -> list[tuple[float, str]]:
    """Deduplica momentos (kill/keyword) pela janela de merge.

    Nunca funde DUAS kills: cada kill gera um clipe próprio. A dedup da janela
    só vale entre kill e keyword (mesmo momento anunciado/registrado).
    """
    ordered = sorted(moments, key=lambda x: x[0])
    merged: list[tuple[float, str]] = []
    for t, label in ordered:
        if merged and t - merged[-1][0] <= merge_window \
                and not (label == "kill" and merged[-1][1] == "kill"):
            continue
        merged.append((t, label))
    return merged


class Worker(threading.Thread):
    def __init__(self, cfg: Config, emit):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.emit = emit
        self._stop = threading.Event()
        self.kill_events: list[tuple[float, str, int]] = []
        self.matches: list = []
        self._vod_original: str | None = None
        self._is_local: bool = False

    def cancel(self) -> None:
        self._stop.set()

    def _progress(self, phase: str, fraction=None, status="") -> None:
        self.emit({"type": "progress", "phase": phase,
                   "fraction": fraction, "status": status})

    def run(self) -> None:
        try:
            self._run()
        except Exception as e:
            log.exception("ERRO: %s", e)
            self.emit({"type": "error", "message": str(e)})

    def _run(self) -> None:
        cfg = self.cfg
        os.makedirs(cfg.work_dir, exist_ok=True)
        os.makedirs(cfg.output_dir, exist_ok=True)

        # 0) Fonte: arquivo local ou download do Twitch
        duration = None
        info = None
        vod_path = None
        if cfg.local_file:
            self._is_local = True
            vod_path = os.path.abspath(cfg.local_file)
            if not os.path.isfile(vod_path):
                raise RuntimeError(f"Arquivo local não encontrado: {cfg.local_file}")
            log.info("Usando arquivo local: %s", vod_path)
            self._progress("download", 1.0, "arquivo local pronto")
        else:
            self._is_local = False
            # 1) Extrai info para pegar duração cedo
            try:
                info = downloader.extract_info(cfg.url)
                duration = float(info.get("duration") or 0) or None
                log.info("VOD encontrado: %s (%.1fh)", info.get("title", ""),
                         (info.get("duration", 0) or 0) / 3600)
            except Exception as e:
                log.warning("Não consegui obter metadados (%s); seguindo só "
                            "com o download.", e)

            # 1.5) VOD sem stream de vídeo (subscriber-only) → aborta antes de baixar
            if info is not None and not downloader.has_video(info.get("formats", [])):
                log.error("VOD sem stream de vídeo: %s", NO_VIDEO_MSG)
                self.emit({"type": "error", "message": NO_VIDEO_MSG})
                return

            # 2) Download
            self._progress("download", None, "baixando VOD...")
            log.info("Baixando VOD (isso pode demorar)...")
            vod_path = downloader.download_vod(
                cfg.url, cfg.work_dir, progress_cb=self._on_download_progress)
            self._progress("download", 1.0, "VOD baixado")
            log.info("VOD em: %s", vod_path)

            if self._stop.is_set():
                return

        # 2.1) Garante que o arquivo tem vídeo (cobre fallback sem extract_info)
        try:
            clipper.video_size(vod_path)
        except Exception:
            log.error("VOD sem stream de vídeo: %s", NO_VIDEO_MSG)
            self.emit({"type": "error", "message": NO_VIDEO_MSG})
            self._cleanup(vod_path)
            return

        if not duration:
            duration = clipper.ffprobe_duration(vod_path)

        # 2.5) Reduz VOD >1080p para 1080p (working file) e guarda o original
        # para limpeza posterior. No caso comum (rendition 1080p do Twitch) não
        # há transcode e working == original.
        self._progress("transcode", 0.0, "verificando resolução do VOD...")
        working, original = clipper.ensure_1080p(
            vod_path, cfg.work_dir,
            progress_cb=lambda f: self._progress(
                "transcode", f, "reduzindo VOD para 1080p..."))
        self._vod_original = original
        vod_path = working
        if working == original:
            log.info("VOD já em resolução <= 1080p.")
        else:
            self._progress("transcode", 1.0, "VOD em 1080p")
            log.info("VOD reduzido para 1080p: %s", vod_path)

        wants_kills = cfg.mode in ("kills", "both")
        wants_keywords = cfg.mode in ("keywords", "both")

        # 3) OCR do placar (CPU) em paralelo à transcrição (GPU)
        ocr_thread = None
        if wants_kills:
            ocr_thread = threading.Thread(
                target=self._run_kills, args=(vod_path,), daemon=True)
            ocr_thread.start()

        if wants_keywords:
            self._transcribe_and_match(vod_path, duration)

        if ocr_thread is not None:
            ocr_thread.join()

        if self._stop.is_set():
            self._cleanup(vod_path)
            return

        # 4) Mescla kills + keywords (deduplica pela janela de merge)
        moments = [(t, "kill") for t, _col, _total in self.kill_events]
        moments += [(m.time, m.keyword) for m in self.matches]
        merged = merge_moments(moments, cfg.merge_window)
        log.info("Encontrados %s momento(s) interessante(s).", len(merged))

        if not merged:
            self.emit({"type": "done", "clips": []})
            self._cleanup(vod_path)
            return

        # 5) Corte
        results: list[ClipResult] = []
        for i, (t, label) in enumerate(merged, start=1):
            if self._stop.is_set():
                break
            window = clip_window(t, duration, cfg.offset_before, cfg.clip_length)
            if not window:
                log.info("[%s @ %s] pulado: muito perto do fim.", label, ts(t))
                continue
            start, end = window
            slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_") or "clip"
            out_name = f"clip_{i:02d}_{slug}_{ts(t)}.mp4"
            out_path = os.path.join(cfg.output_dir, out_name)
            self._progress("clip", (i - 1) / max(len(merged), 1),
                           f"cortando clipe {i}/{len(merged)}...")
            clipper.cut_clip(vod_path, out_path, start, end - start)
            results.append(ClipResult(index=i, keyword=label,
                                      keyword_time=t, clip_start=start,
                                      clip_end=end, file=out_path))
            log.info("Clipe criado: %s (keyword @ %s)", out_name, ts(t))
            self.emit({"type": "clip_done", "clip": results[-1]})

        self._progress("clip", 1.0, "clipes criados")

        # 6) CSV
        self._write_csv(results)
        self._cleanup(vod_path)
        self.emit({"type": "done", "clips": results})

    def _transcribe_and_match(self, vod_path: str, duration: float) -> None:
        cfg = self.cfg
        self._progress("transcribe", 0.0, "transcrevendo áudio...")
        transcriber = Transcriber(model=cfg.model, device=cfg.device,
                                  compute_type=cfg.compute_type,
                                  language=cfg.language,
                                  vad_filter=cfg.vad_filter)
        words, info = transcriber.transcribe(
            vod_path, cfg.keyword_list, duration,
            progress_cb=lambda f: self._progress(
                "transcribe", f, "transcrevendo áudio..."))
        self._progress("transcribe", 1.0, "transcrição concluída")
        log.info("Transcrição concluída (%s palavras).", len(words))
        self._dump_transcript(words)
        word_objs = [Word(s, e, w) for s, e, w in words]

        if self._stop.is_set():
            return

        matches = find_matches(
            word_objs, cfg.keyword_list, cfg.merge_window, cfg.fuzzy_threshold)
        for t, text, kw, ratio in near_misses(word_objs, cfg.keyword_list):
            log.info("quase: '%s' @ %s ~ '%s' (%.2f)", text, ts(t), kw, ratio)
        self.matches = matches

    def _run_kills(self, vod_path: str) -> None:
        cfg = self.cfg
        self._progress("kills", 0.0, "lendo placar de kills...")
        log.info("Lendo placar de kills (OCR)...")
        try:
            events = killtracker.detect_kill_events(
                vod_path, cfg.kill_region, cfg.kill_fps,
                work_dir=cfg.work_dir,
                progress_cb=None if cfg.mode == "both" else
                lambda f: self._progress("kills", f, "lendo placar de kills..."),
                stop_event=self._stop)
        except Exception as e:
            log.warning("Falha ao ler o placar: %s", e)
            self.emit({"type": "warning",
                       "message": f"Falha ao ler o placar (modo kills): {e}"})
            return
        self.kill_events = events
        for t, col, total in events:
            log.info("kill detectada @ %s (%s: %s)", ts(t), col, total)
        self._progress("kills", 1.0, "placar lido")

    def _on_download_progress(self, d) -> None:
        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes", 0)
            if total:
                self._progress("download", min(downloaded / total, 1.0),
                               "baixando VOD...")
        elif status == "finished":
            self._progress("download", 1.0, "download concluído")

    def _dump_transcript(self, words) -> None:
        path = os.path.join(self.cfg.work_dir, "transcript.txt")
        with open(path, "w", encoding="utf-8") as f:
            for s, e, w in words:
                f.write(f"{s:.2f}\t{e:.2f}\t{w.strip()}\n")
        log.info("Transcrição completa salva em %s", path)

    def _write_csv(self, results: list[ClipResult]) -> None:
        path = os.path.join(self.cfg.output_dir, "clips.csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["#", "keyword", "keyword_time", "clip_start",
                             "clip_end", "file"])
            for r in results:
                writer.writerow([r.index, r.keyword, f"{r.keyword_time:.1f}",
                                 f"{r.clip_start:.1f}", f"{r.clip_end:.1f}", r.file])
        log.info("Índice salvo em %s", path)

    def _cleanup(self, vod_path: str) -> None:
        if not self.cfg.delete_vod:
            return
        local_abs = os.path.abspath(self.cfg.local_file) if self._is_local else None
        targets = {vod_path}
        if self._vod_original and self._vod_original != vod_path:
            targets.add(self._vod_original)
        for path in targets:
            if not os.path.exists(path):
                continue
            # Nunca apagar o arquivo local do usuário.
            if local_abs and os.path.abspath(path) == local_abs:
                continue
            try:
                os.remove(path)
                log.info("VOD removido: %s", os.path.basename(path))
            except OSError as e:
                log.warning("Não foi possível remover o VOD: %s", e)
