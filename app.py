import copy
import os
import queue
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

import log as log_module
from config import CONFIG_FILE, LANGUAGES, MODE_CHOICES, MODEL_SIZES, Config
from worker import Worker

PHASES = ["download", "transcribe", "kills", "clip"]
PHASE_LABEL = {
    "download": "Baixando VOD",
    "transcribe": "Transcrevendo áudio",
    "kills": "Lendo placar de kills",
    "clip": "Cortando clipes",
}


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Clip.aí — Cortador de VODs da Twitch")
        self.geometry("720x660")
        self.events = queue.Queue()
        self.worker: Worker | None = None
        self.cfg = Config.from_file(CONFIG_FILE)
        log_module.setup(lambda ev: self.events.put(ev))
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._poll)

    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}
        frame = ttk.Frame(self, padding=10)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="URL do VOD da Twitch").grid(
            row=0, column=0, sticky="w", **pad)
        self.url_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.url_var).grid(
            row=0, column=1, sticky="ew", **pad)

        ttk.Label(frame, text="Arquivo local (opcional)").grid(
            row=1, column=0, sticky="w", **pad)
        self.local_file_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.local_file_var).grid(
            row=1, column=1, sticky="ew", **pad)
        ttk.Button(frame, text="...", width=3,
                   command=self._choose_video).grid(row=1, column=2, **pad)

        ttk.Label(frame, text="Palavras-chave (separadas por vírgula)").grid(
            row=2, column=0, sticky="w", **pad)
        self.keywords_var = tk.StringVar(value=self.cfg.keywords)
        ttk.Entry(frame, textvariable=self.keywords_var).grid(
            row=2, column=1, sticky="ew", **pad)

        opts = ttk.Frame(frame)
        opts.grid(row=3, column=0, columnspan=2, sticky="ew", **pad)
        for col in range(4):
            opts.columnconfigure(col, weight=1)

        ttk.Label(opts, text="Modelo Whisper").grid(row=0, column=0, sticky="w")
        self.model_var = tk.StringVar(value=self.cfg.model)
        ttk.Combobox(opts, textvariable=self.model_var, values=MODEL_SIZES,
                     state="readonly", width=12).grid(row=1, column=0, sticky="w")

        ttk.Label(opts, text="Antes (s)").grid(row=0, column=1, sticky="w")
        self.before_var = tk.DoubleVar(value=self.cfg.offset_before)
        ttk.Spinbox(opts, from_=0, to=60, increment=1, textvariable=self.before_var,
                    width=8).grid(row=1, column=1, sticky="w")

        ttk.Label(opts, text="Duração (s)").grid(row=0, column=2, sticky="w")
        self.length_var = tk.DoubleVar(value=self.cfg.clip_length)
        ttk.Spinbox(opts, from_=5, to=300, increment=5, textvariable=self.length_var,
                    width=8).grid(row=1, column=2, sticky="w")

        ttk.Label(opts, text="Unir hits < (s)").grid(row=0, column=3, sticky="w")
        self.merge_var = tk.DoubleVar(value=self.cfg.merge_window)
        ttk.Spinbox(opts, from_=0, to=120, increment=1, textvariable=self.merge_var,
                    width=8).grid(row=1, column=3, sticky="w")

        ttk.Label(opts, text="Idioma do áudio").grid(
            row=2, column=0, sticky="w", pady=(6, 0))
        self.language_var = tk.StringVar(value=self.cfg.language)
        ttk.Combobox(opts, textvariable=self.language_var, values=LANGUAGES,
                     state="readonly", width=12).grid(row=3, column=0, sticky="w")

        ttk.Label(opts, text="Detecção").grid(row=2, column=2, sticky="w", pady=(6, 0))
        self.mode_var = tk.StringVar(value=self.cfg.mode)
        ttk.Combobox(opts, textvariable=self.mode_var, values=MODE_CHOICES,
                     state="readonly", width=12).grid(row=3, column=2, sticky="w")

        ttk.Label(opts, text="Região placar (x,y,w,h)").grid(
            row=2, column=3, sticky="w", pady=(6, 0))
        self.region_var = tk.StringVar(value=self.cfg.kill_region)
        ttk.Entry(opts, textvariable=self.region_var, width=16).grid(
            row=3, column=3, sticky="w")

        self.vad_var = tk.BooleanVar(value=self.cfg.vad_filter)
        ttk.Checkbutton(opts, text="Filtrar silêncio (VAD)",
                        variable=self.vad_var).grid(row=3, column=1, sticky="w",
                                                   pady=(6, 0))

        out = ttk.Frame(frame)
        out.grid(row=4, column=0, columnspan=2, sticky="ew", **pad)
        out.columnconfigure(1, weight=1)
        ttk.Label(out, text="Pasta de saída").grid(row=0, column=0, sticky="w")
        self.out_dir_var = tk.StringVar(value=self.cfg.output_dir)
        ttk.Entry(out, textvariable=self.out_dir_var).grid(row=0, column=1, sticky="ew")
        ttk.Button(out, text="...", width=3, command=self._choose_dir).grid(
            row=0, column=2)

        self.delete_var = tk.BooleanVar(value=self.cfg.delete_vod)
        ttk.Checkbutton(frame, text="Apagar o VOD após cortar",
                        variable=self.delete_var).grid(
            row=5, column=0, columnspan=2, sticky="w", **pad)

        btns = ttk.Frame(frame)
        btns.grid(row=6, column=0, columnspan=2, sticky="ew", **pad)
        self.process_btn = ttk.Button(btns, text="Processar", command=self._start)
        self.process_btn.pack(side="left")
        self.cancel_btn = ttk.Button(btns, text="Cancelar", command=self._cancel,
                                     state="disabled")
        self.cancel_btn.pack(side="left", padx=6)

        self.progress = ttk.Progressbar(frame, mode="determinate", maximum=100)
        self.progress.grid(row=7, column=0, columnspan=2, sticky="ew", **pad)
        self.status_var = tk.StringVar(value="Pronto.")
        ttk.Label(frame, textvariable=self.status_var).grid(
            row=8, column=0, columnspan=2, sticky="w", **pad)

        ttk.Label(frame, text="Log").grid(row=9, column=0, sticky="w", **pad)
        self.log = scrolledtext.ScrolledText(frame, height=12, state="disabled")
        self.log.grid(row=10, column=0, columnspan=2, sticky="nsew", **pad)
        frame.rowconfigure(10, weight=1)

        self.results_var = tk.StringVar(value="")
        ttk.Label(frame, textvariable=self.results_var, foreground="#0a6").grid(
            row=11, column=0, columnspan=2, sticky="w", **pad)
        self.open_btn = ttk.Button(frame, text="Abrir pasta de saída",
                                   command=self._open_output, state="disabled")
        self.open_btn.grid(row=11, column=1, sticky="e", **pad)

    def _choose_dir(self):
        path = filedialog.askdirectory(initialdir=self.out_dir_var.get() or ".")
        if path:
            self.out_dir_var.set(path)

    def _choose_video(self):
        path = filedialog.askopenfilename(
            initialdir=os.path.dirname(self.local_file_var.get()) or ".",
            filetypes=[("Vídeos", "*.mp4 *.mkv *.webm *.flv *.ts"),
                       ("Todos os arquivos", "*.*")])
        if path:
            self.local_file_var.set(path)

    def _append_log(self, message: str):
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _current_cfg(self) -> Config:
        cfg = copy.copy(self.cfg)
        cfg.url = self.url_var.get().strip()
        cfg.local_file = self.local_file_var.get().strip()
        cfg.keywords = self.keywords_var.get().strip()
        cfg.model = self.model_var.get()
        cfg.language = self.language_var.get()
        cfg.offset_before = float(self.before_var.get())
        cfg.clip_length = float(self.length_var.get())
        cfg.merge_window = float(self.merge_var.get())
        cfg.mode = self.mode_var.get()
        cfg.kill_region = self.region_var.get().strip() or Config().kill_region
        cfg.output_dir = self.out_dir_var.get().strip() or "output"
        cfg.delete_vod = self.delete_var.get()
        cfg.vad_filter = self.vad_var.get()
        return cfg

    def _on_close(self):
        try:
            self._current_cfg().save()
        finally:
            self.destroy()

    def _start(self):
        cfg = self._current_cfg()
        if not cfg.url and not cfg.local_file:
            messagebox.showerror("Falta fonte",
                                 "Informe a URL do VOD da Twitch ou um arquivo local.")
            return
        self.cfg = cfg
        cfg.save()
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self.progress["value"] = 0
        self.results_var.set("")
        self.open_btn.configure(state="disabled")
        self.process_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.worker = Worker(cfg, lambda ev: self.events.put(ev))
        self.worker.start()

    def _cancel(self):
        if self.worker:
            self._append_log("Cancelando...")
            self.worker.cancel()

    def _poll(self):
        try:
            while True:
                ev = self.events.get_nowait()
                self._handle(ev)
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _handle(self, ev):
        t = ev["type"]
        if t == "log":
            self._append_log(ev["message"])
        elif t == "progress":
            phase = ev.get("phase")
            fraction = ev.get("fraction")
            if fraction is not None:
                self.progress["value"] = fraction * 100
            status = ev.get("status", "")
            self.status_var.set(f"{PHASE_LABEL.get(phase, phase)} — {status}")
        elif t == "clip_done":
            c = ev["clip"]
            self._append_log(f"OK clipe: {c.file}")
        elif t == "warning":
            self._append_log(f"AVISO: {ev['message']}")
            self.status_var.set("Atenção — veja o log.")
        elif t == "done":
            clips = ev["clips"]
            n = len(clips)
            self.status_var.set(f"Concluído! {n} clipe(s) gerado(s).")
            self.results_var.set(f"Concluído! {n} clipe(s) em {self.out_dir_var.get()}")
            self.open_btn.configure(state="normal")
            self._finish()
            if n == 0:
                messagebox.showinfo("Sem clipes",
                                    "Nenhuma palavra-chave encontrada no áudio.")
        elif t == "error":
            self.status_var.set("Erro.")
            self._finish()
            messagebox.showerror("Erro", ev["message"])

    def _finish(self):
        self.worker = None
        self.process_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled")

    def _open_output(self):
        path = self.out_dir_var.get()
        if os.path.isdir(path):
            subprocess.Popen(["explorer", os.path.abspath(path)])


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
