"""BM25 retrieval over a pet's events (review M8; FDE: the score is a rank, not a confidence).

- Okapi BM25 with IDF, so a rare word ("limping") outweighs a common one ("Max").
- Rows that share no query term score 0 and are dropped: an empty list is the explicit
  "no match" path, and the assistant answers ``not_in_records`` without calling a model.
- Ties break by event id, so results never depend on insertion order.
- Scores are only used to rank within one query and are never shown as a percentage.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Sequence

from petpulse.services.events import Event

STOPWORDS = frozenset("""a about after again all am an and any are as at be been before being both but by can could did do does
    doing down during each few for from further had has have having he her here hers him his how i if in into is
    it its itself just me more most my no nor not now of off on once only or other our out over own same she
    should so some such than that the their them then there these they this those through to too under until up
    very was we were what when where which while who whom why will with would you your yours today yesterday
    tell show please pet pets""".split())
_WORD = re.compile(r"[a-z0-9]+")
_SUFFIXES = ("ing", "edly", "ed", "es", "s", "ly")


def stem(word: str) -> str:
    """A deliberately small suffix stripper: vomiting/vomited/vomits -> vomit."""
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            word = word[: -len(suffix)]
            break
    if len(word) > 3 and word[-1] == word[-2] and word[-1] not in "aeiouls":  # running -> runn -> run
        word = word[:-1]
    return word


def tokenize(text: str, extra_stopwords: Iterable[str] = ()) -> list[str]:
    stop = STOPWORDS | {w.lower() for w in extra_stopwords}
    return [stem(w) for w in _WORD.findall(text.lower().replace("'", "")) if w not in stop and len(w) > 1]


@dataclass(frozen=True)
class Hit:
    event: Event
    score: float
    rank: int


class BM25:
    def __init__(self, documents: Sequence[tuple[str, list[str]]], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.docs = [(doc_id, Counter(tokens), len(tokens)) for doc_id, tokens in documents]
        self.n = len(self.docs)
        self.avgdl = (sum(length for _, _, length in self.docs) / self.n) if self.n else 0.0
        df: Counter[str] = Counter()
        for _, counts, _ in self.docs:
            df.update(counts.keys())
        self.idf = {term: math.log(1 + (self.n - freq + 0.5) / (freq + 0.5)) for term, freq in df.items()}

    def scores(self, query: Sequence[str]) -> list[tuple[str, float]]:
        terms = set(query)
        out = []
        for doc_id, counts, length in self.docs:
            score = 0.0
            for term in terms:
                tf = counts.get(term, 0)
                if not tf:
                    continue
                norm = tf + self.k1 * (1 - self.b + self.b * length / (self.avgdl or 1.0))
                score += self.idf.get(term, 0.0) * tf * (self.k1 + 1) / norm
            out.append((doc_id, score))
        return out


def search(events: Sequence[Event], query: str, k: int = 5, extra_stopwords: Iterable[str] = ()) -> list[Hit]:
    """Top ``k`` events with a positive BM25 score; ``[]`` means nothing matched.

    Ties are broken by recency, then by id.
    """
    stop = list(extra_stopwords)
    query_terms = tokenize(query, stop)
    if not query_terms or not events:
        return []
    by_id = {event.id: event for event in events}
    index = BM25([(event.id, tokenize(event.text, stop)) for event in events])
    # Equal scores: newest first, then id, so the order is deterministic and recent context wins.
    ranked = sorted(
        (pair for pair in index.scores(query_terms) if pair[1] > 0),
        key=lambda pair: (-pair[1], -by_id[pair[0]].at.timestamp(), pair[0]),
    )
    return [Hit(by_id[doc_id], round(score, 6), rank) for rank, (doc_id, score) in enumerate(ranked[:k], start=1)]
