# PLAN — Placar de kills no canto superior direito

**VOD de teste:** https://www.twitch.tv/videos/2838821994 (LOL CLASSIC - TEEMO TOP, ~59 min)

## Objetivo

Ajustar a detecção de kills por OCR para o **placar no canto superior direito**
da tela. No VOD real o placar é uma **linha de contadores** (y≈0.013):
`[kills time] [vs] [kills time] [KDA do streamer]`. O gatilho é a **kill do
streamer**: lemos o primeiro número do KDA (coluna do streamer) e disparamos
quando ele incrementa.

> **Escopo atualizado (2026-08):** a detecção NÃO rastreia mais as kills dos
> times (vermelho/azul) — apenas a kill do streamer. Ver `PLAN_STREAMER.md`.

## Descoberta no VOD real (calibração)

- Região da linha: `x 0.785–0.895`, `y 0.004–0.032` → default
  `kill_region = "0.785,0.004,0.110,0.028"`.
- Colunas (frações absolutas de x): vermelho `0.802–0.822`, azul `0.833–0.859`
  (bandas calibradas para **excluir** o `vs` em ~0.798–0.805), **streamer
  `0.860–0.895`** — o KDA do streamer (ex.: `3/5/11`, `#6`, `#10`); lemos o
  **primeiro número** (kills).
- Série real lida do KDA: 3→8 (partida 1) e 0→11 (partida 2) — monotônica por
  partida; o parser devolve `(kills_streamer,)`.

## Mudanças

1. `killtracker.py`
   - `_as_kda_kills`: extrai o **primeiro número** de um KDA (`3/5/11`→3,
     `#6`→6, `10.`→10); `_as_kill_value` segue para valores comuns.
   - `parse_kill_total(img, x_origin, region_w)`: OCR psm 6 na linha, agrupa os
     tokens na faixa de x (`KILL_COLUMNS`) e devolve **`(kills_streamer,)`**.
   - `increment_events`: detecta incremento da kill do streamer, confirma em
     3 frames, descarta saltos > `MAX_KILL_JUMP=5` (misread do OCR) e reinicia
     baseline em queda.
   - `detect_kill_events`: log da região; salva **3 frames completos**
     (`work/frame_full_0/1/2.jpg`) + `work/frame_sample.png` para calibração.
2. `config.py` — default `kill_region = "0.785,0.004,0.110,0.028"`.
3. `app.py` — campo **"Região do placar (x,y,w,h)"** (frações 0–1) já existente;
   o usuário calibra visualmente sem editar código.
4. Testes sintéticos: linha com KDA → `(kills,)`; timer ignorado;
   `increment_events` por incremento, flicker, queda/reset e salto implausível.

## Validação

- [x] `pytest` — testes verdes (KDA do streamer, queda pequena não reseta,
      queda grande reseta partida).
- [x] Smoke e2e sintético (KDA do streamer, topo-direito).
- [x] **VOD real**: baixado (2,7 GB), região calibrada e validada via sweep de
      OCR (colunas red/blue/streamer mapeadas; coluna do streamer lida como KDA).
- [x] `detect_kill_events` no VOD completo — ver `PLAN_STREAMER.md` para o
      resultado da rodada com gatilho só na kill do streamer.
