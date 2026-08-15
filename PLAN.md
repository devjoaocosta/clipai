# PLAN — Validação final e fechamento do Clip.aí

**VOD de teste:** https://www.twitch.tv/videos/2838821994 (LOL CLASSIC - TEEMO TOP, ~59 min)

## 1. Histórico

O app baixa o VOD, transcreve com faster-whisper (CUDA), detecta keywords e corta
clipes de 30s. A validação com o VOD acima mostrou dois problemas:

1. **Falsos positivos** — o fuzzy de token único casava "achei"→`ace` e
   "Leandro"→`lendário`, gerando 3 clipes que não eram momentos reais.
2. **"Double kill" não detectado** — investigação concluiu que **não houve double
   kill nesse VOD** (confirmado pelo usuário). Sem evento real, o comportamento do
   app de não gerar clipe estava **correto**. A hipótese de que o Whisper ignora o
   announcer ficou **não comprovada** (não havia áudio de chamada para testar).

## 2. Correções aplicadas

- `matcher.py`: matching por **janela de palavras consecutivas** (cobre keywords
  multi-token como "double kill"). **Fuzzy só para keywords multi-token**; token
  único exige match exato/prefixo (`_token_hit`). `near_misses()` com limiar 0.68.
- `config.py`: keywords default `double kill, triple kill, quadra kill, pentakill,
  ace, lendário`; novos campos `fuzzy_threshold` (0.72), `vad_filter` (True).
- `transcriber.py`: repassa `vad_filter` ao `model.transcribe()`.
- `worker.py`: dump da transcrição em `work/transcript.txt`, quase-matches no log,
  repassa VAD e fuzzy threshold.
- `app.py`: dropdown de idioma (auto/pt/en) e checkbox de VAD.
- `tests/test_matcher.py`: 13 testes, incl. regressão de falsos positivos.

## 3. Validações

- [x] `pytest` — 13 verdes.
- [x] Matcher offline no transcript real (`small`) → **0 matches** (sem lixo).
- [x] Experimentos `small` e `large-v3` no VOD → 0 palavras de announcer
      (coerente: não havia evento).
- [ ] E2E com VOD que tenha um evento real de keyword (deferido: usuário sem VOD
      disponível no momento).

## 4. Execução (passos finais)

1. Rodar `pytest` (regressão).
2. Rodar o matcher offline nos transcripts (`small` e `large-v3`) e conferir que
   não há falsos positivos e que `near_misses` reporta de forma útil.
3. Verificar `near_misses`/`clip_window` com casos sintéticos de referência.
4. Limpar artefatos de experimento (`work/largev3.*`).
5. Conferir consistência de README/PLAN e resumir para o usuário.

## 5. Pendências futuras (quando houver VOD)

- Rodar e2e num VOD com evento confirmado (ex.: o de ~22 min que acertou
  penta/lendário).
- Se `small` não detectar o announcer, re-transcrever com `large-v3`.
- Só se ambos falharem, avaliar detecção por correlação de áudio (announcer do LoL
  BR é arquivo de áudio fixo, independente de transcrição).
