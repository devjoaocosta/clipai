# PLAN — Detecção de kills no VOD real

**VOD:** https://www.twitch.tv/videos/2838821994 (~59 min)
**Arquivo:** `work/vod.mp4` (2,7 GB, já baixado)
**Região:** `0.785,0.004,0.110,0.028` (topo-direito, calibrada)
**Amostragem:** 1 fps → ~3.540 frames → ~6–15 min de OCR em thread de fundo

## Objetivo

Rodar `killtracker.detect_kill_events` no VOD inteiro e **validar cada evento
contra as kills reais** da partida — fechando o item pendente do
`PLAN_REGIAO.md`.

## Etapas

1. **Preparar o runner** (`work/run_detect.py`):
   - chama `detect_kill_events(vod, region, fps=1.0, work_dir="work")`;
   - `log_cb` imprime o progresso (a cada 250 frames) e cada evento
     (`kill detectada @ ts (total N)`);
   - grava `work/kill_events.csv` com `ts,total` e o resumo
     (nº de eventos, red/blue final lido, duração, frames lidos);
   - imprime o tempo de execução.
2. **Executar em background** (como o run anterior):
   - `Start-Process` → `work/detect_v2.out`, `work/detect_v2.err`, `work/detect_v2.pid`;
   - acompanhar o `.out` periodicamente até terminar.
3. **Validar eventos × kills reais** (`work/validate_events.py`):
   - para cada evento, extrair frame completo (`ffmpeg -ss`) em `ts` e `ts-2`;
   - OCR da região nesses frames → confirmar que o contador em `ts` bate com o
     `total` do evento e que em `ts-2` era menor (incremento real);
   - listar os eventos com o contador lido (red/blue) para conferência manual
     (a pessoa confere se cada kill real gerou clipe).
4. **Ajustes finais**:
   - se houver falsos positivos/negativos sistemáticos → ajustar
     `KILL_COLUMNS`, região ou `MAX_KILL_JUMP` e re-rodar;
   - salvar amostras de calibração nos pontos problemáticos.
5. **Limpeza**: remover `vod.mp4` (2,7 GB), `.pid/.out/.err` de experimentos
   e atualizar `PLAN_REGIAO.md`/`PLAN_DETECCAO.md`.

## Critérios de aceite

- [x] Runner termina sem erro e gera `work/kill_events.csv`.
- [x] Cada evento validado tem incremento real no contador (red ou blue).
- [x] Nenhum wedging (parada de eventos no meio do VOD).
- [x] CSV/planos atualizados com o resultado final.

## Resultado (rodada final, `work/detect_v4.out`)

> **Atualização:** a detecção foi redefinida para rastrear **apenas a kill do
> streamer** (1º número do KDA na 3ª coluna). O resultado abaixo (103 eventos
> red/blue) é da rodada antiga; o resultado atual está em **`PLAN_STREAMER.md`**.

- **103 eventos** em ~59 min de VOD (1 fps, ~29 min de processamento).
- **102/103 confirmados** contra o OCR de frames (janela `[ts, ts+3]`).
- **Monotonicidade perfeita por coluna**: 0 quedas internas entre eventos
  consecutivos de cada cor (vermelho 64 eventos, azul 39 eventos).
- Partidas detectadas: partida 1 (vermelho 22→41, azul 19→51) e partida 2
  (vermelho 1→54, azul 1→13), com reset de contador na transição.
- **1 falso positivo**: `red 7 @ ~1087s` — placar oculto/coberto entre
  820–1100s (OCR lê lixo pequeno, o tracker interpreta como partida nova).
- Eventos agora gravam a coluna: `work/kill_events.csv` = `ts,col,total`.

## Resultado atual (só streamer, ver `PLAN_STREAMER.md`)

- **16 eventos**, 0 falsos positivos: partida 1 `4,5,6,8` (kill `7` perdida,
  placar oculto em 297–298s), partida 2 `1→12` completo.
- Cobertura 16/17 kills reais; 16/16 eventos confirmados por frame.
- `work/kill_events.csv` já contém apenas a coluna `streamer`.
