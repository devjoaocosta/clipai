# PLAN — Selecionar a KILL (número à esquerda) do KDA, não a morte (central)

**VOD de teste:** https://www.twitch.tv/videos/2838821994 (LOL CLASSIC - TEEMO TOP, ~59 min)
**Relato:** "o programa está pegando minhas mortes e não minhas kills, é o
número do lado esquerdo e não o central". Confirmado pelo usuário: no KDA
`kills/deaths/assists`, **kill = número à esquerda**, **death = central**.

## Diagnóstico

O KDA do streamer é exibido na coluna `0.861–0.895` (banda `[0.860, 0.895]`).
O parser por coluna `_band_value` (`killtracker.py:241`) seleciona o token
**mais próximo do centro** da banda (`killtracker.py:263-264`).

- **VOD de teste:** o OCR lê o KDA como um único token (`3/5/11`, `8/11/`).
  `_as_kda_kills` extrai o 1º segmento (kills) → funcionava.
- **Stream do usuário:** o OCR lê os números do KDA **separados** (`3`, `5`,
  `11`). O **deaths** (central, ~`0.873`) fica mais próximo do centro da banda
  (`0.8775`) do que a kill (`~0.865`) → o deaths vence → clips nas mortes.

## Mudança (1 arquivo)

### `killtracker.py` — `_band_value`

Trocar a seleção de **"mais próximo do centro"** para **"mais à esquerda"**:

1. Entre os tokens que **cruzam** a banda `[blo, bhi]`, preferir os com
   **centro dentro da banda** e escolher o de **menor x** (mais à esquerda =
   primeiro número do KDA = kills).
2. Fallback: se nenhum token tiver centro dentro da banda, usar o token mais à
   esquerda que **cruza** a banda (ex.: kill do time azul que invade a borda).

Isso também evita que o kills do time azul (`0.833–0.859`) que invade a borda
esquerda da banda vença: o centro desse token fica fora da banda.

`_as_kda_kills` (1º segmento de tokens combinados) permanece inalterado.

## Testes (`tests/test_killtracker.py`)

- Novo: tokens separados `3`, `5`, `11` na banda → retorna `3` (kills).
- Novo: token azul invadindo a borda esquerda da banda + kill separada →
  a kill vence.
- Manter: `3/5/11` → `3`, `8/11/` → `8`, `#6` → `6`, `10.` → `10`.

## Validação

1. `pytest` — todos verdes (inclui novos testes).
2. `work/smoke_e2e.py` — SMOKE OK (KDA kills).
3. `parse_kill_total` nos 17 crops do grid → série
   `3,8,0,1,5,6,6,6,6,9,10,10,10,10,10,11,11`.
4. Usuário valida na própria stream.

## Limitação conhecida

Se o OCR perder totalmente o dígito da kill (restar só `5/11`), não há como
recuperar — caso raro, fora do escopo desta correção.

## Critérios de aceite

- [x] `_band_value` seleciona a kill (token mais à esquerda) mesmo com números
      separados `3`, `5`, `11`.
- [x] Kill do time azul invadindo a borda não vence a kill do streamer.
- [x] `pytest` verde + SMOKE OK + grid 17/17.

## Execução e resultado

### Mudança aplicada

`killtracker.py` — `_band_value`: seleção por **"mais próximo do centro"** →
**"mais à esquerda"**:

1. Tokens que cruzam a banda `[0.860, 0.895]` são separados em `in_band`
   (centro dentro da banda) e `crossing` (só cruzam a borda).
2. Se houver `in_band`, vence o de **menor x** (1º número do KDA = kills).
3. Senão, fallback para o `crossing` de menor x (ex.: kill do time azul que
   invade a borda — o centro dela fica fora da banda).

`_as_kda_kills` inalterado (extrai 1º segmento de tokens combinados `3/5/11`).

### Testes novos (`tests/test_killtracker.py`, +4)

- `test_band_value_picks_leftmost_number_of_kda` — tokens `3`/`5`/`11`
  separados → `3` (a morte `5` era a escolha do código antigo).
- `test_band_value_ignores_blue_kills_crossing_band_edge` — kill azul em
  `0.857` invadindo a borda não vence a kill do streamer.
- `test_band_value_falls_back_to_crossing_token` — fallback quando só há
  token cruzando a borda.
- `test_parse_kill_total_picks_leftmost_separated_kda` — OCR end-to-end com
  `3`/`5`/`11` desenhados separados → `(3,)`.

### Validação

- [x] `pytest`: **36 testes verdes** (32 antigos + 4 novos).
- [x] `work/smoke_e2e.py`: **SMOKE OK** (`[(3.0,'streamer',1), (6.0,'streamer',2)]`).
- [x] Grid 17/17: série `3,8,0,1,5,6,6,6,6,9,10,10,10,10,10,11,11` mantida.
- [ ] Usuário valida na própria stream (kill sobe → clipe; morte sobe → nada).
