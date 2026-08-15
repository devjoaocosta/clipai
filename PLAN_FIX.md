# Plano — Correção da detecção de "double kill"

**VOD de teste:** https://www.twitch.tv/videos/2838821994 (LOL CLASSIC - TEEMO TOP, ~59 min)

## Diagnóstico final (conclusivo)

O Whisper (testado `small` e `large-v3`, GPU) **não transcreve o announcer do jogo**.
Os 2.100+ segundos do VOD só contêm a fala do streamer (1263–1218 palavras, nenhuma
do tipo "kill/double/penta"). Mesmo o `large-v3` ignora o áudio de fundo do jogo —
comportamento conhecido do Whisper em áudio misto: ele suprime sons não-fala e foca
na voz dominante (o mic). Logo, **detecção por transcrição nunca vai achar o
announcer neste tipo de VOD**, independente do modelo.

Além disso, os "matches" da primeira rodada eram **falsos positivos** do fuzzy de
token único: "achei"→`ace` e "Leandro"→`lendário`.

## Solução: detecção por áudio (announcer = arquivo fixo)

As chamadas do announcer do LoL BR ("DOUBLE KILL", "PENTAKILL"...)
são o **mesmo arquivo de áudio** em todas as partidas. Então dá pra detectá-las por
**correlação do áudio** (independente de transcrição):

1. **Referência** — extrair 1 clip do announcer (ex.: do próprio VOD do usuário, ou
   do arquivo de voz do LoL) e normalizar (mono, 16 kHz, normalizar pico).
2. **Correlação** — cross-correlação por FFT do clip contra o áudio do VOD; picos
   altos e nítidos = ocorrências daquela chamada.
3. **Fallback de transcrição** — manter a detecção por palavras (agora sem fuzzy de
   token único) para keywords que o streamer *fala* em voz alta.

## Correções já aplicadas

1. **Matcher por janela de palavras** — janela de palavras consecutivas + texto
   concatenado (cobre "double kill", "penta kill" → "pentakill"...).
2. **Fuzzy só para keywords multi-token** — token único exige match exato/prefixo;
   elimina "achei"→`ace`, "Leandro"→`lendário` (teste de regressão incluído).
3. **Defaults LoL BR** — `double kill, triple kill, quadra kill, pentakill, ace,
   lendário`.
4. **Dump de transcrição** — sempre `work/transcript.txt` (debug) e
   `work/transcript_largev3.txt` (experimento large-v3).
5. **"Quase-matches"** — log de palavras parecidas + timestamp (limiar 0.68).
6. **Idioma na UI** (auto/pt/en) e **VAD configurável**.

## Validação

- [x] `pytest` — 13 testes verdes (incl. regressão de falsos positivos).
- [x] Matcher offline no transcript real → **0 matches** (sem lixo).
- [x] Experimentos `small` e `large-v3` → announcer ausente do transcript.
- [ ] Extrair clip de referência do announcer (precisa do timestamp do double kill
      do usuário) e validar o detector por correlação no VOD inteiro.
