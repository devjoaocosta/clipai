# PLAN — Correções no killtracker (validação do modo kills no VOD real)

**VOD de teste:** https://www.twitch.tv/videos/2838821994 (~59 min, baixado em `work/vod.mp4`)

## Diagnóstico (código + logs)

A detecção de kills foi iniciada no VOD real, mas o run não terminou
(`work/detect_real.out` só tem a linha de startup; `.err` vazio; PID morto;
apenas os 3 frames de calibração foram salvos). Antes de re-rodar a detecção no
VOD completo, corrigir dois problemas encontrados no código:

1. **Bug de "wedging" em `increment_events`** (`killtracker.py`):
   quando o salto é `> MAX_KILL_JUMP`, o código faz `continue` **sem atualizar o
   baseline**. Se o placar reaparecer após uma lacuna de cobertura (tela preta,
   menu, loading) já com valor muito maior, o tracker fica preso no baseline
   antigo e **nunca mais dispara** (só um decremento destrava). No VOD real há
   trechos sem placar (`frame_full_1` não mostra contadores no topo) → risco
   real.

2. **Risco de OCR fundir as colunas vermelho/azul** em um único token
   (ex.: `20518` lido em `frame_full_0` a 2x). Quando isso ocorre, o token cai
   numa única faixa e a outra coluna fica `None` → frame descartado → kill
   perdida.

## Mudanças

### 1. `increment_events` — destravar após salto grande

- Salto `> MAX_KILL_JUMP` que **persiste por `confirm_frames`** vira o novo
  baseline (sem evento) — cobre lacuna de cobertura.
- Salto grande **transitório** (1–2 frames, misread) é ignorado, baseline
  intacto.
- Saltos `<= MAX_KILL_JUMP` mantêm o comportamento atual (evento com 3 frames
  sustentados).
- `p["big"]` distingue os dois tipos de `pending` (incremento vs baseline novo).

### 2. `parse_kill_total` — OCR por coluna (crop isolado)

- Substituir a leitura da linha inteira (`psm 6` + agrupamento por faixa de x)
  por **um crop por coluna** (`KILL_COLUMNS`) lido isoladamente com `--psm 6`,
  escolhendo o token mais próximo do centro da banda.
- Banda vermelho `0.802–0.822` e azul `0.833–0.859` (a azul antiga `0.823–0.852`
  incluía o `vs` em ~0.798–0.805 → OCR instável).
- Fallback: se a banda não achar valor, usa o token-span (o token que cruza a
  coluna) — evita perder kill quando o número deriva da banda.
- `_as_kill_value` continua removendo não-dígitos (ex.: "vs18" → 18).

### 3. `increment_events` — queda pequena não reseta baseline

- Dentro de uma partida o placar só sobe: queda `≤ MAX_KILL_JUMP` é misread do
  OCR e **não** resetava o baseline (antes resetava → re-disparava o mesmo
  total após um frame ruim).
- Queda **grande** (`> MAX_KILL_JUMP`) é reset de partida: vira baseline novo
  se persistir por `confirm_frames`.
- Eventos agora retornam `(ts, coluna, total)`.

## Testes

- Novo teste de regressão do wedging:
  salto 5 → 13 (>MAX_KILL_JUMP) sustentado vira baseline; o incremento
  13 → 14 confirmado em 3 frames dispara evento.
- Teste de regressão do merge:
  manter `test_parse_kill_total_columns` (números nas duas colunas) passando
  com o novo OCR por coluna.
- Rodar `pytest` completo (hoje 25 testes) — tudo verde.

## Validação

- [x] `pytest` verde (29 testes: wedging, gap jump, salto transitório, queda
      pequena não reseta, queda grande reseta partida, merge).
- [x] `parse_kill_total` no frame real `work/frame_sample.png` → `(20, 18)`.
- [x] Smoke e2e sintético (contador único, topo-direito): vídeo fake com
      placar 0→1→2 gera eventos em ~3.0s e ~6.0s.
- [x] Detecção completa no VOD real: 103 eventos, 102/103 confirmados, 0
      quedas internas por coluna (ver `PLAN_DETECCAO.md`).
