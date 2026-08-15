# Plano: clipes MP4 legíveis por editores (Premiere/After Effects)

## Problema
O usuário reportou: os clipes gerados **não são lidos corretamente por editores**
(Premiere/After Effects). Sintoma exato: **"os editores não conseguem ler os
frames pares"** (quadros alternados ilegíveis/errados na timeline).

## Diagnóstico (ffprobe nos clipes de `output/`)
Os clipes são H.264 válidos (decode limpo, `faststart`, `pix_fmt=yuv420p`,
`field_order=progressive`, sem erros de decode), mas o container tem metadados
não padrão que quebram o indexador de frames do Premiere:

1. **Timebase de vídeo não padrão `1/15360`** (padrão MP4 é `1/90000`). Premiere
   indexa frames por PTS/timescale; timescale fora do padrão desalinha a paridade
   par/ímpar → sintoma de "frames pares".
2. **Primeiro pacote de vídeo com DTS negativo (-17ms)** e vídeo iniciando em
   `+16ms` (áudio em `0ms`) — **sem edit list (`edts/elst`)**. Sem reordenação
   correta de B-frames, o Premiere decodifica em ordem de demux e troca pares.
3. **GOP longo (250 frames = ~4,2s)** — menos amigável a seek de edição.
4. **899 frames em vez de 900** para 15s@60fps (deslocamento do início).

Causa raiz: `clipper.cut_clip` usa flags mínimas (`-ss` + libx264) e deixa o
muxer escolher timescale/delay/timestamps.

### Descoberta durante a execução (teste empírico de flags)
Com B-frames (`-bf 2`), os primeiros B-frames de um corte são **descartados**
(não têm referência anterior) → o vídeo começa 2 quadros depois
(`start_time=0.2s` na fonte de teste). Somado ao timescale não padrão, é isso
que faz o Premiere desalinhar a paridade dos frames. `-bf 0` elimina a
reordenação e o offset de início de vez (`start_time=0.000`, 1º dts = 0).

## Mudanças

### 1. `clipper.cut_clip` — encode padronizado para editores
Manter `-ss` antes de `-i` (seek rápido; prioridade escolhida = compatibilidade).
Adicionar flags de saída:
- `-video_track_timescale 90000` — timescale padrão MP4.
- `-avoid_negative_ts make_zero` — timestamps iniciam em 0 (sem DTS negativo).
- `-muxpreload 0 -muxdelay 0` — sem delay inicial do muxer (offset +16ms).
- `-pix_fmt yuv420p` (explícito), `-profile:v high -level 4.1`.
- `-fps_mode cfr` + `-r {fps_fonte}` (fps lido via ffprobe) — CFR determinístico.
- `-g 120 -keyint_min 120` — GOP de ~2s (mais amigável a edição).
- `-bf 0` — sem B-frames: sem descarte de quadros no início do corte
  (`start_time=0.000`) e sem reordenação que o Premiere aplicaria errado.
- `-map 0:v:0? -map 0:a:0?` — só streams de AV (maps opcionais).
- `-ar 48000 -ac 2 -c:a aac -b:a 192k` (explícito).
- Mantém `-movflags +faststart -threads 0`.

### 2. `clipper._verify_clip(out_path, expected_length)` — verificação pós-corte
`ffprobe` (JSON) e assert:
- stream de vídeo existe;
- `start_time ≈ 0` (tolerância 0,05s);
- `time_base = 1/90000`;
- `duration` dentro de `expected_length ± 0,5s`;
- primeiro pacote de vídeo com `dts >= 0`.
Falha → aviso em stderr (não quebra a run). Chamado por `cut_clip` ao final.

### 3. Testes — novo `tests/test_clipper.py`
- Fixture `tests/fixtures/clip_source.mp4`: 3s, 320x240, 30fps, testsrc2 + sine
  (gerada uma vez com ffmpeg lavfi).
- `test_cut_clip_standard_container`: corta 1s e asserta start_time=0,
  time_base=1/90000, dts do 1º pacote >= 0, vídeo+áudio presentes, duração ok.
- `test_verify_clip_ok` e `test_verify_clip_rejects_garbage` (arquivo não-vídeo).

### 4. Validação
- `pytest` completo (sem regressões em killtracker/matcher/worker).
- Re-cortar 1–2 clipes existentes de `output/` com as novas flags e conferir por
  ffprobe: `start_time=0.000`, `time_base=1/90000`, 1º dts >= 0, edit list.
- Usuário abre no Premiere para confirmar leitura dos frames pares.

## Arquivos
- `clipper.py`: `cut_clip` + `_video_frame_rate` + `_verify_clip`.
- `tests/test_clipper.py`: testes do corte/verificação.
- `tests/fixtures/clip_source.mp4`: fonte de teste AV.
- `PLAN_CLIPE_EDITORES.md`: este plano.

## Tradeoffs
- Precisão de quadro exata: não incluída (seek rápida mantida). Futuro: corte em
  2 passos (extração rápida + trim preciso) se necessário.
- Tempo de encode: ~neutro vs atual (mesmo preset `veryfast`).
