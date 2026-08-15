import difflib
import re
import unicodedata
from dataclasses import dataclass


@dataclass
class Word:
    start: float
    end: float
    text: str


@dataclass
class Match:
    time: float
    keyword: str
    word: str


def _strip_accents(text: str) -> str:
    text = unicodedata.normalize("NFD", text)
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def normalize(text: str) -> list[str]:
    text = _strip_accents(text).lower()
    text = re.sub(r"[^a-z0-9ç]+", " ", text)
    return [t for t in text.split() if t]


def _ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def _token_hit(wtok: str, ktok: str) -> bool:
    if wtok == ktok:
        return True
    if len(ktok) >= 4 and wtok.startswith(ktok):
        return True
    if len(wtok) >= 4 and ktok.startswith(wtok):
        return True
    return False


def _concat_matches(tokens: list[str], kw_tokens: list[str],
                    fuzzy_ratio: float) -> bool:
    if not tokens or not kw_tokens:
        return False
    a = "".join(tokens)
    b = "".join(kw_tokens)
    if a == b:
        return True
    if len(kw_tokens) == 1:
        return any(_token_hit(t, kw_tokens[0]) for t in tokens)
    return _ratio(a, b) >= fuzzy_ratio


def find_matches(words: list[Word], keywords: list[str],
                 merge_window: float = 10.0, fuzzy_ratio: float = 0.72) -> list[Match]:
    kws = [(kw, normalize(kw)) for kw in keywords if normalize(kw)]
    n = len(words)
    hits: list[Match] = []

    for i in range(n):
        for kw, kw_tokens in kws:
            max_words = len(kw_tokens) + 1
            limit = min(max_words, n - i)
            for wc in range(1, limit + 1):
                tokens: list[str] = []
                for j in range(wc):
                    tokens += normalize(words[i + j].text)
                if _concat_matches(tokens, kw_tokens, fuzzy_ratio):
                    hits.append(Match(
                        time=words[i].start, keyword=kw,
                        word=" ".join(words[i + j].text for j in range(wc)).strip()))
                    break
            else:
                continue
            break

    hits.sort(key=lambda m: m.time)
    merged: list[Match] = []
    for hit in hits:
        if merged and hit.time - merged[-1].time <= merge_window:
            continue
        merged.append(hit)
    return merged


def near_misses(words: list[Word], keywords: list[str],
                threshold: float = 0.68) -> list[tuple[float, str, str, float]]:
    kws = [(kw, normalize(kw)) for kw in keywords if normalize(kw)]
    out: list[tuple[float, str, str, float]] = []
    seen = set()
    for w in words:
        for wtok in normalize(w.text):
            for kw, kw_tokens in kws:
                for ktok in kw_tokens:
                    ratio = _ratio(wtok, ktok)
                    if threshold <= ratio < 1.0:
                        key = (round(w.start, 2), w.text, kw)
                        if key not in seen:
                            seen.add(key)
                            out.append((w.start, w.text, kw, ratio))
    out.sort(key=lambda x: x[0])
    return out


def clip_window(time: float, duration: float, offset_before: float,
                clip_length: float, min_length: float = 3.0):
    start = max(0.0, time - offset_before)
    end = min(duration, start + clip_length)
    if end - start < min_length:
        return None
    return start, end


def ts(hours_seconds: float) -> str:
    hours_seconds = int(hours_seconds)
    h, rem = divmod(hours_seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}h{m:02d}m{s:02d}s"
