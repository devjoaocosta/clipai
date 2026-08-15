# Plano: ler ABATES via template matching (NCC) no KDA do streamer

## Problema
O tracker dispara clipes em **mortes**, não em abates. Usuário relatou: clipe 12
tem 9 abates, clipe 13 continua 9 abates, mas o tracker gerou o clipe 13 porque o
contador de **mortes** incrementou (8 -> 9).

## Causa raiz (diagnóstico)
- O HUD do streamer mostra, na linha superior, o KDA com **3 grupos de glifos**:
  - **Abates (kills)**: x global ≈ 0.8484–0.8557 (1–2 dígitos; ex. `10`).
  - **"9" fixo (rótulo/ícone do HUD)**: x ≈ 0.8677–0.8734, constante em todas as
    partidas (não é contador).
  - **Mortes (deaths)**: x ≈ 0.8792–0.8828, incrementa 1..12 e reseta por partida.
- A banda atual `KILL_COLUMNS = [("streamer", 0.865, 0.895)]` cobre o "9" fixo e as
  **mortes** → o tracker lê mortes.
- O glifo de **abates** é escuro/ilegível ao Tesseract (testado invert, thresholds,
  Otsu, stretch, dilatação, upscales 8–20x, PSM 6/7/8/10/11/13, OEM 1/3 → lê
  `?`/`�`/`*`). O glifo de mortes é legível (mesma fonte do HUD).
- **Descartada**: classificação de dígitos por template (NCC vs banco 0–9). Medido
  nos glifos reais de ~8px: matriz de NCC entre templates mostra 3↔5 = 0.87,
  7↔8 = 0.97, 0↔9 = 0.84 → dígitos não discriminam. Inviável.
- **Solução implementada**: **detecção de MUDANÇA no slot de abates** por NCC do
  vetor normalizado 12×26. Medido nos frames reais: MESMO valor NCC ≥ 0.997;
  valores diferentes NCC ≤ 0.93 → limiar 0.95 separa com folga. Não precisa de
  templates nem de OCR.
- Clipes 01–04 (telas de loading/pós-jogo) não têm glifo na banda de abates →
  leitor retorna `None` → sem eventos.

## Mudanças implementadas

### 1. `_kills_slot_vector(img, x_origin, region_w)` em `killtracker.py`
- Banda global x [0.846, 0.858] → relativa à região (x_origin, region_w).
- Glifos são CLAROS sobre fundo escuro → binariza com `gray > 80`.
- Autocrop vertical (±1 linha) + resize LANCZOS 12×26 + z-score.
- Banda vazia (loading) → `None`.
- Estável entre frames do mesmo valor; distinto entre valores diferentes.

### 2. `_events_from_signatures(samples, confirm_frames, reset_gap)`
- Mesmo vetor (NCC ≥ 0.95) → nada (inclui mortes mudando e 9 → 9).
- Mudança persistente por `confirm_frames` (3) → evento `(ts, "streamer", total)`
  onde `total` = contador sequencial de abates detectados (a leitura do dígito é
  inviável; só o log usa o total).
- Mudança precedida por ≥ `reset_gap` (3) frames `None` (HUD oculto) → **reset de
  partida**: vira baseline novo SEM evento.

### 3. Integração
- `detect_kill_events`: coleta `_kills_slot_vector` por frame e usa
  `_events_from_signatures` (substitui OCR + `increment_events`). Sem tesseract.
- `parse_kill_total`, `_band_value`, `_as_kda_kills`, `increment_events`:
  **mantidos intactos** (usados por testes OCR/legados e validação).

### 4. Testes (`tests/test_killtracker.py` + fixtures reais)
- Fixtures `tests/fixtures/region_clipNN.png`: crops da região (0.785, 0.004,
  0.110, 0.028) dos clips 01 e 05–16.
- Casos:
  - clip_01 (loading) → vetor `None`; blank → `None`.
  - clips 12/13 (9 → 9) → NCC ≥ 0.95 e **0 eventos** (queixa do usuário).
  - série real 2,3,5,5,6,6,7,9,9,10,1,1 (repetida 3x/frame) → eventos nas
    mudanças `[3, 6, 12, 18, 21, 27, 30]` (inclui 1 reset sem gap).
  - reset 10 → 1 precedido de loading → **0 eventos**.
  - confirmação: mudança isolada (flicker) → 0 eventos.

## Validação
- `pytest`: **52 passando** (50 anteriores + 2 substituídos).
- Frames reais c12/c13 (kills=9 por ~10s): **0 eventos**.
- Loading (clip_01): vetor `None` → sem eventos.
- Limitação documentada: VOD apagado → sem e2e completo; validação por frames.
  Reset de partida SEM tela de loading entre partidas → evento falso (raro).
  Abate que ocorra inteiramente com HUD oculto pode ser perdido.
