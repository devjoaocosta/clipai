# Plano: VOD sem vídeo (subscriber-only) → erro claro e parada graciosa

## Problema
URL de VOD subscriber-only (ex.: https://www.twitch.tv/videos/2837865321). O
Twitch só expõe o áudio para sessão anônima (usher devolve apenas `audio_only`),
então o yt-dlp baixa um arquivo **só de áudio**. O pipeline espera vídeo e
quebra com mensagem obscura:

```
Lendo placar de kills (OCR)...
killtracker: região 0.785,0.004,0.110,0.028 a 1.0 fps; amostras de calibração em work
Falha ao ler o placar: invalid literal for int() with base 10: ''
Encontrados 0 momento(s) interessante(s).
```

## Causa raiz
`killtracker.video_size` (e `clipper.video_size`) fazem `ffprobe
-select_streams v:0 -show_entries stream=width,height`. Em arquivo sem stream
de vídeo o ffprobe devolve vazio e `int('')` sobe `ValueError`. O `_run_kills`
engole o erro, a run segue e termina em "0 momentos" sem explicar nada.

## Decisões (aprovadas pelo usuário)
1. Só tratar o erro (sem suporte a cookies/autenticação por ora).
2. Sem vídeo → **abortar tudo** (não baixa, não transcreve, não corta).

## Mudanças

### 1. `clipper.video_size` — erro claro sem stream de vídeo
Se o ffprobe devolver vazio (sem `v:0`), subir
`RuntimeError("VOD sem stream de vídeo — provavelmente restrito a assinantes (subscriber-only)")`
em vez de `int('')`.

### 2. `killtracker` — reutilizar `video_size` de `clipper`
`killtracker.py` já importa `_which` de `clipper`. Trocar para importar também
`video_size` e remover a função duplicada (linhas 73-80). Herda o erro claro.

### 3. `downloader` — helper puro `has_video(formats)`
Função sem rede: devolve `True` se algum formato tem `vcodec` real
(`vcodec != 'none'`), ignorando storyboards (`sb0/sb1`) e `Audio_Only`.

### 4. `worker._run` — dois checks de abort
- **Pré-download**: o worker já chama `downloader.extract_info` no início. Se
  `not downloader.has_video(info.get("formats", []))`, loga + emite
  `{"type": "error", "message": ...}` e **retorna sem baixar**.
- **Pós-download**: depois de `download_vod`, `clipper.video_size(vod_path)` em
  try/except; se falhar, mesmo erro claro e retorna (cobre fallback do formato
  ou ausência de `extract_info`). `_cleanup` ainda roda para apagar o arquivo.

Mensagem padrão: "VOD sem vídeo disponível. O VOD é restrito a assinantes
(subscriber-only) — o Twitch só expõe o áudio sem login. Use uma conta
assinante (cookies) ou outro VOD."

### 5. Testes
- `test_clipper`: `video_size` em arquivo só-áudio → `RuntimeError` com a
  mensagem clara (não `ValueError` cru de `int('')`).
- `test_downloader` (novo, sem rede): `has_video` em formats só-áudio →
  `False`; formats com vídeo → `True`; storyboards sozinhos → `False`.
- Sem regressão nos testes existentes.

## Validação
- `pytest` completo.
- Gerar arquivo só-áudio (lavfi sine) e conferir `video_size` com o erro claro.
- (Opcional) rodar worker com a URL subscriber-only e ver o abort com a
  mensagem clara antes do download.

## Arquivos
- `PLAN_VOD_SEM_VIDEO.md`: este plano.
- `clipper.py`: `video_size` defensivo.
- `killtracker.py`: importa `video_size` de `clipper` (remove cópia).
- `downloader.py`: `has_video(formats)`.
- `worker.py`: pré/pós-checks com abort + mensagem clara.
- `tests/test_clipper.py` e novo `tests/test_downloader.py`.

## Tradeoffs
- Sem download autenticado: VODs subscriber-only seguem inacessíveis (o app
  falha cedo e limpo). Adicionar cookies/OAuth fica para um próximo passo.
- Abortar tudo é intencional: sem vídeo não há como cortar clipes; baixar/
  transcrever desperdiçaria tempo.
