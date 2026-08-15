# Plano: usar arquivo de vídeo local

## Objetivo

Permitir processar um vídeo local (gravado por OBS/Streamlabs etc.) em vez de
baixar um VOD da Twitch, reaproveitando toda a pipeline de transcrição/OCR/corte.
O arquivo do usuário **nunca** é apagado.

## Fluxo atual (sem mudanças)

`app.py` (UI) → `worker.py` (orquestração) → `downloader.py` (yt-dlp) →
`transcriber.py` / `killtracker.py` (detecção) → `clipper.py` (corte).

## Alterações

### 1. `config.py`

- Adicionar campo `local_file: str = ""` ao dataclass `Config`.

### 2. `app.py`

- Nova linha na UI (após a linha da URL): label **"Arquivo local (opcional)"**
  + `ttk.Entry` ligado a `local_file_var` + botão **"..."** que chama
  `filedialog.askopenfilename` (filtro `*.mp4 *.mkv *.webm *.flv *.ts`).
- Em `_start`: passar `local_file=self.local_file_var.get().strip()` ao `Config`.
  Validação: se local preenchido, usa ele; senão, exige URL (manter o
  `showerror` atual).

### 3. `worker.py`

- Em `_run`, no início (antes do `extract_info`):
  - Se `cfg.local_file`:
    - Valida `os.path.isfile` — erro claro se não existir.
    - `vod_path = cfg.local_file`; pula extract_info, has_video e download.
    - Mantém o check `clipper.video_size(vod_path)` para garantir stream de
      vídeo (mesma mensagem de erro útil).
    - `duration = clipper.ffprobe_duration(vod_path)` (com fallback já existente).
    - Marca `self._is_local = True`.
  - Senão, fluxo atual intacto (`self._is_local = False`).
- **`_cleanup`** (crítico): se `_is_local`, **nunca** deletar o arquivo do
  usuário. Só deleta o working file de transcode (`work/vod_1080.mp4`) quando
  ele for diferente do arquivo local. Se `_is_local` for False, comportamento
  atual preservado.

### Sem mudanças em

`downloader.py`, `clipper.py`, `transcriber.py`, `killtracker.py`, `matcher.py`.

### Testes

- Adicionar em `tests/` um teste de `_cleanup` com fonte local (não deleta o
  arquivo local; deleta só o working de transcode), seguindo o estilo dos
  testes atuais.
- Rodar `.\.venv\Scripts\python.exe -m pytest`.

### Verificação manual

- Rodar o app com um `.mp4` local, modos `keywords` e `kills`, conferir clipes
  em `output/` e que o arquivo local original permanece intacto.

## Comportamento de "Apagar o VOD após cortar"

Continua valendo para VODs baixados; o arquivo local nunca é removido.

## Passos

1. `config.py`: campo `local_file`.
2. `app.py`: linha + botão "..." + fiação no `_start`.
3. `worker.py`: desvio local no `_run` + guarda no `_cleanup`.
4. Teste de `_cleanup` + `pytest`.
