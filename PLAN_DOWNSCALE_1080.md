# Plano: VOD acima de 1080p → reduzir para 1080p

## Problema
Se o VOD estiver em 1440p (ou acima), o programa hoje corta os clipes na
resolução nativa. Necessário: reduzir para 1080p e manter todo o pipeline
(kills, transcrição, cortes) se comportando como o esperado.

## Decisões (aprovadas pelo usuário)
1. **Pré-transcodificar o VOD** para 1080p após o download (pipeline uniforme e
   determinístico, idêntico ao calibrado em 1080p).
2. **Download preferindo a rendition 1080p** do Twitch quando existir
   (menos banda/disco); transcode local só no fallback.
3. **Cap geral**: qualquer altura > 1080 → 1080p (cobre 1440p, 1600p, 4K).

## Contexto técnico
- `clipper.cut_clip` hoje emite na resolução nativa do VOD.
- Regiões de placar são frações normalizadas (`0.785,0.004,0.110,0.028`) e o NCC
  do placar compara vetores da mesma run — mas pré-transcodificar garante
  pipeline idêntico ao calibrado em 1080p e ainda alivia o decode (1440p é mais
  pesado para extração de frames e corte).
- No caso comum do Twitch (parceiro tem transcode 1080p60), o filtro de download
  já entrega 1080p → **nenhuma transcode**. A transcode só dispara no fallback
  (VOD com apenas source 1440p/4K).

## Mudanças

### 1. `downloader.py` — preferir rendition ≤1080p
Trocar `"bv*+ba/b"` por `"bv*[height<=1080]+ba/bv*+ba/b"` (linha 33). Baixa a
rendition ≤1080p quando existe; fallback para source.

### 2. `clipper.py` — transcode + verificação
- Constante `MAX_OUTPUT_HEIGHT = 1080`.
- Novo `video_size(path) -> (w, h)` (probe ffprobe; sem dependência
  clipper→killtracker).
- Novo `ensure_1080p(vod_path, work_dir, max_height=1080,
  progress_cb=None) -> (working, original)`:
  - Se altura ≤ `max_height` → retorna `(vod_path, vod_path)` (sem transcode).
  - Senão, transcoda para `work_dir/vod_1080.mp4`:
    - decode `-hwaccel d3d11va` com fallback software;
    - `-vf scale=-2:1080,setsar=1`;
    - mesmas flags de container do `cut_clip` (timescale 1/90000,
      `-avoid_negative_ts make_zero`, `-muxpreload 0 -muxdelay 0`, yuv420p,
      `-profile:v high -level 4.1`, `-g 120 -bf 0`, `-c:a copy`), `-crf 20`;
    - `-progress` para fração real.
  - Verifica com `_verify_clip(out, duration, max_height)`; em falha loga e
    **cai no caminho original** (os clipes ainda saem 1080p pelo cap do
    `cut_clip`).
- `cut_clip`: adiciona `-vf scale=-2:1080,setsar=1` condicional quando o source
  tem altura > `MAX_OUTPUT_HEIGHT` (garantia extra) e passa `max_height` para
  `_verify_clip`.
- `_verify_clip(..., max_height=1080)`: novo check `stream.height <= max_height`.

### 3. `worker.py` — orquestra a transcode
- Após download + duração:
  `working, original = clipper.ensure_1080p(vod_path, cfg.work_dir,
  progress_cb=...)`; guarda ambos em `self`; usa `working` em kills,
  transcrição e cortes.
- Fase de progresso `"transcode"` (fração do `-progress`); log
  "VOD 1440p → 1080p" ou "VOD já ≤1080p".
- `_cleanup`: com `delete_vod=True`, apaga `working` **e** `original` (se
  diferentes).

### 4. Testes (`tests/test_clipper.py`)
- Fixture 1440p gerada no teste (lavfi 2560×1440, testsrc2 + sine, ~2s).
- `test_ensure_1080p_transcodes_1440`: saída 1920×1080, duração ≈, áudio
  presente, `_verify` OK.
- `test_ensure_1080p_keeps_720p`: retorna o mesmo caminho (sem transcode).
- `test_cut_clip_caps_height_1440`: corte direto de fonte 1440p → 1920×1080.
- `test_verify_clip_rejects_oversized_1440`: `_verify_clip(max_height=1080)`
  num arquivo 1440p → `False`.
- Sem regressão nos testes existentes.

## Validação
- `pytest` completo.
- Transcode real de um fixture 1440p e conferência por ffprobe: 1920×1080,
  `time_base=1/90000`, `start_time≈0`, duração ≈ source, áudio presente.
- (Opcional) rodar o pipeline com um VOD 1440p real quando disponível e
  confirmar clipes 1080p + kills detectadas.

## Arquivos
- `PLAN_DOWNSCALE_1080.md`: este plano.
- `clipper.py`: `MAX_OUTPUT_HEIGHT`, `video_size`, `ensure_1080p`, cap no
  `cut_clip`, `_verify_clip(max_height)`.
- `downloader.py`: formato de download preferindo ≤1080p.
- `worker.py`: transcode + limpeza dos dois arquivos.
- `tests/test_clipper.py`: testes novos.

## Tradeoffs
- Encode do working file é CPU (`libx264 veryfast`, crf 20). Em fallback raro é
  rápido o bastante; GPU (`nvenc`) fica como otimização futura se VOD longo
  incomodar.
- `-c:a copy` no working file evita perda de áudio; whisper usa o áudio copiado.
- Trabalho é um arquivo intermediário: re-encode no corte é inevitável, mas o
  working file com timescale/container padrão mantém os cortes amigáveis a
  editores.
