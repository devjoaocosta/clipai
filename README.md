# Clip.aí

Cortador automático de VODs da Twitch: baixa o VOD e gera clipes de 30s em dois
modos:
- **Palavras-chave**: transcreve o áudio (faster-whisper) e detecta palavras
  (ex.: "pentakill", "lendário")
- **Contador de kills (OCR)**: lê o placar de kills da HUD de LoL no vídeo e
  corta um clipe a cada kill da partida (inclusive kill única)

## Instalação

Pré-requisitos:

- Python 3.11+ (testado com 3.14)
- ffmpeg/ffprobe no PATH: `winget install Gyan.FFmpeg` (ou `choco install ffmpeg`)
- Tesseract OCR (só para o modo kills): `winget install UB-Mannheim.TesseractOCR`
- GPU NVIDIA (opcional, mas recomendada): só o driver basta — o CUDA runtime é
  instalado via pip (ver abaixo)

Setup:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# opcional — libs CUDA/cuDNN para usar a GPU (o app também cai para CPU automaticamente)
pip install nvidia-cuda-runtime-cu12 nvidia-cublas-cu12 nvidia-cudnn-cu12
```

## Uso

```powershell
.\.venv\Scripts\python.exe app.py
```

1. Cole a URL do VOD (ex.: `https://www.twitch.tv/videos/123456789`)
2. Escolha a **Detecção**: `keywords` (palavras-chave), `kills` (contador de
   kills via OCR) ou `both` (as duas, em paralelo — padrão)
3. Ajuste as palavras-chave e offsets se quiser
4. Clique em **Processar**

No primeiro uso, o modelo do Whisper é baixado do Hugging Face (~150MB para `small`,
~1.5GB para `medium`). Modelos maiores transcrevem melhor as chamadas do announcer
(inglês no meio de fala PT) — se o `small` não encontrar nada, teste `large-v3`.

No modo kills, o OCR lê a linha de contadores no canto **superior direito** do placar
(`[kills do time] [vs] [kills do time] [KDA do streamer]`) a 1 frame por segundo e corta
clipe quando o **primeiro número do KDA do streamer** (a kill dele) incrementa — ignora
kills do time inteiro, mortes e assistências. Se o placar não for reconhecido (overlay,
resolução, patch novo), o app salva `work/frame_sample.png` para você conferir e calibrar
a região — pelo campo **"Região do placar (x,y,w,h)"** na UI ou pelo `kill_region` no
`config.py` (frações x,y,w,h).

Os clipes saem em `output/`, com `clips.csv` listando os timestamps. A transcrição
completa fica em `work/transcript.txt` (debug) e o log mostra "quase-matches"
(palavras parecidas com suas keywords e quando ocorreram).

## Como funciona

1. **Download** — yt-dlp baixa o VOD inteiro (merge para MP4)
2. **Transcrição (keywords)** — faster-whisper com timestamps por palavra, VAD
   (ignora silêncio) e `initial_prompt` com as keywords (enviesa o modelo)
3. **Contador de kills (kills)** — ffmpeg recorta a linha do placar a 1 fps; OCR
   (tesseract) lê o **KDA do streamer** (1º número = kills) na coluna por posição-x;
   um clipe é gerado quando a kill dele sobe e se mantém por 3 frames (filtra
   ruído; saltos grandes são descartados como misread)
4. **Match (keywords)** — normalização (acentos/caixa/pontuação) + janela de
   palavras consecutivas (cobre "double kill", "penta kill" x "pentakill"); fuzzy
   apenas para keywords multi-token (evita falsos positivos de token único); hits
   próximos são unidos
5. **Corte** — ffmpeg corta 30s (5s antes + 25s depois), clampado ao início/fim do VOD

## Limitações do MVP

- VODs com trechos **mutados** (música com copyright) não têm áudio → sem detecção ali
- VODs longos demoram: no `medium`+GPU, ~6h de áudio leva ~15-30min; no `small` é bem mais rápido
- O modo kills depende da HUD do LoL na tela (sem overlay cobrindo o placar)
- Um VOD por vez

## Estrutura

```
app.py          UI Tkinter
worker.py       orquestração em thread de fundo
downloader.py   download via yt-dlp
transcriber.py  faster-whisper (CUDA/CPU)
matcher.py      detecção de palavras-chave + merge
killtracker.py  detecção de kills por OCR do placar (tesseract)
clipper.py      ffmpeg/ffprobe (corte e duração)
config.py       configurações padrão
tests/          testes unitários do matcher e do killtracker
```

## Testes

```powershell
.\.venv\Scripts\python.exe -m pytest
```
