# PLAN — Rastrear só a kill do streamer (3ª coluna, KDA)

**VOD de teste:** https://www.twitch.tv/videos/2838821994 (LOL CLASSIC - TEEMO TOP, ~59 min)

## Objetivo

Trocar o gatilho da detecção de kills de **"red/blue (time inteiro)"** para
**apenas a kill do streamer**, lendo o **primeiro número** do KDA exibido na
terceira coluna do HUD (superior-direito).

## Descoberta (OCR dos frames reais)

Layout da região `0.785,0.004,0.110,0.028` (lido via `_ocr_groups`):

| Faixa x | Conteúdo | Significado |
|---------|----------|-------------|
| 0.785–0.802 | `ee)`, `mae`, `115`, `89`... | contador/ícone à esquerda (ignorado) |
| 0.804–0.822 | `20`, `22`, `24`... | kills do time vermelho |
| 0.824–0.830 | `vs` | separador |
| 0.833–0.859 | `18`, `19`, `6`... | kills do time azul |
| 0.861–0.895 | `3/5/11`, `8/11/`, `#6`, `#10`, `10.`, `11`... | **KDA do streamer** |

A terceira coluna é um **KDA (kills/deaths/assists)**. O primeiro número é a
kill do streamer. O parser antigo (`_as_kill_value`) quebraria nisso
(`3/5/11` → fix de `/`→`7` → `375711` → >150 → `None`), por isso um parser
dedicado é necessário.

Série real conhecida nos 17 crops do grid (`work/grid/ts_*.png`):
`3, 8, 0, 1, 5, 6, 6, 6, 6, 9, 10, 10, 10, 10, 10, 11, 11` — monotônica por
partida (partida 2: 0→11).

## Mudanças

### 1. `killtracker.py`

- **`KILL_COLUMNS`** → `[("streamer", 0.860, 0.895)]` (remove red/blue).
- **Novo `_as_kda_kills(text)`**: separa em `re.split(r"[/\s.]+")`, pega o 1º
  segmento, aplica `_fix_digits`, extrai dígitos e limita a 150.
  `3/5/11`→3, `#6`→6, `10.`→10, `8/11/`→8, `11`→11.
- **Helper `_column_value(name, text)`**: `streamer` → `_as_kda_kills`;
  default → `_as_kill_value` (mantém compatibilidade se houver mais colunas).
- **`_band_value` / `_token_span_value`**: usar `_column_value` para o valor do
  token. `_split_wide_token` ganha parâmetro `parser` (default `_as_kill_value`).
- **`parse_kill_total`**: devolve `tuple[int, ...] | None` (1-tupla `(kills,)`
  ou `None`).
- **`increment_events`**: annotation dos samples → `tuple[int, ...] | None`;
  lógica e formato dos eventos `(ts, "streamer", total)` inalterados.
- **`detect_kill_events`**: annotation do `samples` ajustada.

### 2. Sem mudança

- `worker.py` — já trata `(ts, col, total)` genericamente; log vira
  `kill detectada @ ts (streamer: N)`.
- `work/run_detect.py` — CSV `ts,col,total` já suporta.
- `config.py` — região mantida `0.785,0.004,0.110,0.028`.

### 3. `work/smoke_e2e.py`

- Desenhar apenas o KDA do streamer (`K/0/0`) na posição da coluna;
- esperar `[(3.0, 'streamer', 1), (6.0, 'streamer', 2)]`.

### 4. `tests/test_killtracker.py`

- `_make_row` desenha só o texto KDA do streamer;
- `parse_kill_total` → valor único `(v,)`;
- `increment_events` → amostras `(ts, (v,))`, eventos `(ts, 'streamer', v)`;
- novos testes de `_as_kda_kills` cobrindo os casos do OCR real.

### 5. Docs

- `README.md`, `PLAN_REGIAO.md`, `PLAN_DETECCAO.md`: modo kills dispara só na
  kill do streamer (1º número do KDA).

### 6. `_band_value` refatorado (durante a validação)

O recorte (banda) isolado de ~21 px fragmentava o OCR do KDA (ex.: `3/5/11`
virava `1`). `_band_value` agora seleciona nos **grupos da região inteira** os
tokens cujo span cruza a banda `[0.860, 0.895]` e devolve o valor do token
mais próximo do centro da banda. `_token_span_value` foi removido (ficou morto).

> **Ajuste posterior (ver `PLAN_KILLS_ESQUERDA.md`):** a seleção passou de
> "mais próximo do centro" para **"mais à esquerda"** — quando o OCR lê o KDA
> com os números separados (`3`, `5`, `11`), o deaths (central) era escolhido
> e o tracker disparava clips nas mortes. Agora a kill (1º número, à esquerda)
> é sempre a selecionada.

## Validação

1. [x] `pytest` — 32 testes verdes.
2. [x] `work/smoke_e2e.py` — SMOKE OK com KDA (`[(3.0,'streamer',1), (6.0,'streamer',2)]`).
3. [x] `parse_kill_total` nos 17 crops do grid → 17/17 OK
   (`3,8,0,1,5,6,6,6,6,9,10,10,10,10,10,11,11`).
4. [x] **VOD completo**: baixado (~2,7 GB), `run_detect.py` rodado (12 min,
   decode por hardware), `work/kill_events.csv` gerado só com `streamer`.
5. [x] Cada evento conferido contra o frame (amostragem contínua fps=1, mesma
   do detector) — **16/16 OK**: em cada `ts` o KDA mostra o `total`, com
   monotonicidade por partida. Validador: `work/validate_events.py`.
6. [x] Limpeza: VOD (2,7 GB) e script de debug removidos.

## Resultado (VOD real)

16 eventos de kill do streamer, 0 falsos positivos:

- **Partida 1** (placar já em 3 ao iniciar o VOD): `4@84s, 5@88s, 6@202s, 8@299s`.
  A kill `7` **não** foi capturada: o placar fica oculto em 297–298s (OCR None)
  e reaparece direto em `8` (salto 6→8 confirmado em 299s). Sem frame com `7`,
  nenhum detector capturaria — limitação do VOD, não do algoritmo.
- **Partida 2**: `1@1546s ... 12@3387s` — as 12 kills detectadas, monotônicas.

Cobertura: **16 de 17 kills reais** (94%). Conferido contra os 17 pontos do
grid (todos consistentes: ts_01242=0 antes do 1@1546, ts_02230-02316=6 entre
6@2231 e 7@2422, ts_02936=9 entre 9@2645 e 10@3089, ts_03094-03214=10 entre
10@3089 e 11@3261, ts_03264/03326=11 entre 11@3261 e 12@3387).

Misreads observados (absorvidos pela confirmação, sem efeito nos eventos):
`�S5`→`55` quando a kill é 5 (fix `S`→`5`), `29` e `89` em frames isolados.

## Critérios de aceite

- [x] `KILL_COLUMNS` só com `streamer`; nada de red/blue em eventos/CSV.
- [x] `_as_kda_kills` cobre `3/5/11`, `#6`, `#10`, `10.`, `8/11/`.
- [x] `pytest` verde + SMOKE OK.
- [x] Série do grid confirmada por `parse_kill_total` (17/17).
- [x] Detecção no VOD inteiro: eventos monotônicos por partida, todos
      confirmados por frame (16/16).
