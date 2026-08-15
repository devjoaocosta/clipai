# Plano: corrigir crash na UI (`ValueError: too many values to unpack`)

## Sintoma

Ao rodar o app (`python app.py`) no modo kills/both, a thread de OCR estourou:

```
File "worker.py", line 184, in _run_kills
    for t, total in events:
ValueError: too many values to unpack (expected 2, got 3)
```

## Causa raiz

Na rodada de validação do VOD, o `killtracker` foi atualizado para registrar a
**coluna** (red/blue) além do timestamp e do total. O retorno de
`increment_events`/`detect_kill_events` mudou de 2-tuplas `(ts, total)` para
3-tuplas `(ts, coluna, total)`.

O `worker.py` (que orquestra a detecção na UI) continuou consumindo o formato
antigo em **3 pontos**:

1. `worker.py:184` — loop de log em `_run_kills` (CRASH real).
2. `worker.py:100` — fusão de momentos (quebraria logo em seguida).
3. `worker.py:31` — anotação de tipo de `self.kill_events` (cosmético).

Além disso, as anotações de tipo de `killtracker.py` (linhas 253 e 356) ainda
declaram o formato antigo.

## Mudanças

| # | Arquivo | Linha | Antes | Depois |
|---|---------|-------|-------|--------|
| 1 | `worker.py` | 184-186 | `for t, total in events:` | `for t, col, total in events:` + log com coluna |
| 2 | `worker.py` | 100 | `for t, _n in self.kill_events` | `for t, _col, _total in self.kill_events` |
| 3 | `worker.py` | 31 | `list[tuple[float, int]]` | `list[tuple[float, str, int]]` |
| 4 | `killtracker.py` | 253 | `-> list[tuple[float, int]]` | `-> list[tuple[float, str, int]]` |
| 5 | `killtracker.py` | 356 | `-> list[tuple[float, int]]` | `-> list[tuple[float, str, int]]` |

Nenhuma lógica de detecção muda — apenas o desempacotamento.

## Verificação

1. `pytest` — **29/29 verdes** ✅
2. `work/smoke_e2e.py` — **SMOKE OK**: `[(3.0, 'red', 1), (6.0, 'red', 2)]` ✅
3. `Worker._run_kills` com `smoke.mp4` (o caminho exato do crash, linha 184) —
   sem exceção, `kill_events` = `[(3.0, 'red', 1), (6.0, 'red', 2)]` ✅
4. Fusão de momentos (linha 100) com 3-tuplas — ok, gera `[(3.0, 'kill')]` ✅
5. UI com VOD real — **deixado para o usuário rodar** (`python app.py`); o VOD
   de teste (2,7 GB) foi apagado na limpeza e não foi rebaixado.

## Resultado

Thread `_run_kills` não estoura mais; o desempacotamento está consistente
(`ts, col, total`) em `worker.py` e `killtracker.py`. Resta a confirmação
visual na UI (logs `kill detectada @ <ts> (red|blue: <total>)` e clipes em
`output/`).
