# PLAN — Clipe a cada kill (detecção por OCR do placar)

## Objetivo

Em um VOD de LoL, gerar um clipe toda vez que o **contador de kills da partida**
incrementar — qualquer time, incluindo **kill única** (que não tem chamada de voz
do announcer). O gatilho é o número no placar da HUD (topo da tela).

Decisões do usuário: (1) OCR do placar, não áudio; (2) qualquer kill de qualquer
time.

## Por que OCR e não áudio

O announcer só fala em streaks ("Double/Triple/Quadra/Penta", "First Blood").
Kill única é silenciosa; e ainda não foi comprovado que o Whisper ouve o announcer
em áudio misto. O único sinal confiável de *toda* kill é o número no placar.

## Como funciona

Novo módulo `killtracker.py`:

1. **Região de leitura** — ffprobe pega a resolução; recorta a faixa superior
   central (`kill_region`, relativa e configurável, default `0.12,0.0,0.76,0.10`).
2. **Amostragem** — ffmpeg extrai a faixa a **1 fps** via pipe
   (`fps=1,crop=...`, rawvideo) — sem gravar JPEGs em disco.
3. **OCR** — pytesseract (`--psm 6`, whitelist dígitos+`:`) com bounding boxes
   (TSV).
4. **Parsing** — remove grupos que contêm `:` (timer); mantém inteiros curtos
   (1–3 dígitos); soma **kills azul + vermelho** = total da partida (o total é
   monotônico não-decrescente — robusto contra ruído).
5. **Máquina de estados** — evento só quando o total **aumenta e se mantém por
   ≥3 frames** (filtra flicker do OCR). Timestamp = 1º frame do novo valor.
6. **Clipes** — timestamps viram clipes via `clip_window()`/`clipper.py`;
   naming `clip_01_kill_total_5_00h24m10s.mp4`; coluna keyword="kill" no CSV.

## Integração

- `config.py`: `mode: "kills" | "keywords" | "both"` (default **both**),
  `kill_fps=1.0`, `kill_region` (relativa), `MODE_CHOICES`.
- `worker.py`: em `both`, roda o OCR (CPU) em thread paralela **durante** a
  transcrição do Whisper (GPU) → tempo total ≈ só o Whisper; mescla timestamps
  de kills + keywords e deduplica pela janela de merge.
- `app.py`: dropdown "Detecção" (Palavras-chave / Contador de kills / Ambas) +
  fase "Lendo placar".
- `requirements.txt`: `pytesseract`, `Pillow`.
- Sistema: `choco install tesseract -y`. Fallback: EasyOCR (pip puro, mais lento).

## Testes (sintéticos, sem VOD real)

- [x] Gerador de scoreboard fake (PIL) com kills azul/vermelho + timer no layout da HUD.
- [x] OCR/parse: azul=3, vermelho=2 → total 5; timer excluído; `/`→7 corrigido.
- [x] Máquina de estados: 1ª leitura vira baseline; incremento só com 3 frames
      sustentados; flicker filtrado.
- [x] **Smoke e2e**: vídeo sintético (ffmpeg) com placar 0→1→2 gerou eventos nos
      tempos corretos (3.0s e 6.0s) via pipe de frames + OCR + máquina de estados.
- [x] `pytest`: 22 testes verdes (13 matcher + 9 killtracker).

## Validação real (deferida)

Quando houver VOD: e2e conferindo que cada kill gerou clipe. Se a região estiver
errada, o app salva `work/frame_sample.png` para calibrar `kill_region`.

## Riscos e mitigação

- Overlay/resolução cobre o placar → `kill_region` configurável + frame de amostra.
- Ruído do OCR → total monotônico + persistência de 3 frames.
- Champ select gera ruído → placar só existe em jogo; persistência filtra.
- Custo → ~6–12 min por 60 min de VOD a 1 fps, em paralelo ao Whisper.

## Passos de execução

1. Instalar tesseract (choco) + deps pip.
2. Criar `killtracker.py`.
3. Integrar em `config.py`, `worker.py`, `app.py`.
4. Testes sintéticos + `pytest`.
5. Atualizar README e este plano com o resultado.
