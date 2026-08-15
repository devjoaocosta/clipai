# PLAN — Calibração do contador de abates (3º número do grid do placar)

## Objetivo

Gerar um clipe **sempre** que o contador de abates do streamer atualizar. O
contador é o **terceiro número do grid do placar** (KDA do streamer, topo-direito).
Base de calibração: `work/frame_full_1.jpg` (referência) e `work/calibra ai.png`.

## Diagnóstico

O grid do placar (região `0.785,0.004,0.110,0.028`) tem 3 números:

| # do grid | Conteúdo | x (global) | Exemplos |
|---|---|---|---|
| 1º | kills do time vermelho | ~0.809 | `20`, `11`, `28` |
| — | separador `vs`/`\|` | ~0.83 | |
| 2º | kills do time azul | ~0.838 | `19`, `30` |
| — | separador `\|` | ~0.857–0.864 (no layout do `calibra ai.png`) | |
| **3º** | **KDA do streamer (kills)** | **~0.869–0.895** | `3/5/11`, `#9`, `#2` |

O tracker já mira a 3ª coluna (`KILL_COLUMNS = streamer 0.860–0.895`) e já lê o
3º número certo no `frame_full_1.jpg` (`#2` → `(2,)`).

### Bug raiz (impede os clipes)

No layout `28 vs 30 | #9` do `calibra ai.png` há um separador `|` em
x≈0.857–0.864, na borda da banda `[0.860, 0.895]`. Como `_DIGIT_FIX` mapeia
`|`→`1` e `_band_value` escolhe o token **mais à esquerda** da banda, o tracker
lê **1** em vez de **9** (verificado: `parse_kill_total(calibra) == (1,)`).
Com o contador preso em `1`, qualquer kill real vira "salto grande"
(`1→9` > `MAX_KILL_JUMP=5`) → tratado como partida nova → **nenhum clipe**.

### Problema 2 (1 clipe por atualização)

Em `worker.py`, o merge descarta qualquer momento a ≤ `merge_window` (10s) do
anterior. Duas kills do streamer em <10s → o 2º clipe era perdido. Decisão do
usuário: **nunca fundir duas kills**; dedup só entre kill↔keyword.

## Mudanças

1. `killtracker.py` — `_as_kda_kills`: rejeitar token **sem dígito real** antes
   do `_fix_digits`, e remover não-dígitos à esquerda depois da checagem:
   - `|` → `None` (hoje vira `1` e trava o contador);
   - `|#9` → `9` (caso o OCR funda separador + KDA);
   - mantém `3/5/11`→3, `#6`→6, `#10`→10, `10.`→10, `8/11/`→8, `0`→0;
   - `_as_kill_value` intocado (teste fixo `"/"→7`).
2. `killtracker.py` — `KILL_COLUMNS`: banda do streamer `[0.860, 0.895]` →
   `[0.865, 0.895]` (exclui o separador `|` em 0.857–0.864). Validado contra os
   17 crops do grid e o `frame_full_1`.
3. `worker.py` — merge: pular momento só se ≤ `merge_window` **e** não forem
   duas kills consecutivas.
4. Testes novos: `_as_kda_kills("|") is None`, `_as_kda_kills("|#9") == 9`,
   `_band_value` com `|` na borda + `#9` → `9`, merge com 2 kills <10s → 2
   clipes e kill+keyword <10s → 1 clipe.

## Validação

- [x] `pytest` verde (43 testes).
- [x] `parse_kill_total` nos 17 crops do grid mantém a série
      `3,8,0,1,5,6,6,6,6,9,10,10,10,10,10,11,11`.
- [x] `frame_full_1.jpg` → `(2,)`.
- [x] `calibra ai.png` → `(9,)` (antes `(1,)`).
- [x] Smoke e2e (`work/smoke_e2e.py`) → `SMOKE OK`.

## Fora de escopo

- Região `0.785,0.004,0.110,0.028` mantida.
- Sem script de calibração reutilizável.
