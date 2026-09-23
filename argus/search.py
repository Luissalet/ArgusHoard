"""Ranking and grouping of search hits.

FTS5 finds the candidates, but its bm25() clamps a non-positive IDF to 1e-6:
when a term is on more than half of the frames (two hours on one page) every
rank collapses to about -1e-6, which rounds to -0.0 and drowns that term in
multi-word queries. So candidates are re-scored here with BM25 using a smoothed
IDF (always positive) and per-column weights: window title 3, app 2, text 1.
Rank keeps the FTS5 convention: negative, lower is better.

Consecutive near-identical hits (same app, window and snippet text within ten
minutes) are then collapsed into one "moment" with first/last time, count and
the frame ids, best-ranked first.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field

K1 = 1.2
B = 0.75
WEIGHTS = {"window_title": 3.0, "app": 2.0, "text": 1.0}
GROUP_WINDOW_S = 600
IDF_FLOOR = 0.1  # a term on every frame still ranks by where/how often it appears, with readable numbers


def fold(text: str) -> str:
    """Lowercase, strip diacritics (like unicode61 remove_diacritics)."""
    return "".join(ch for ch in unicodedata.normalize("NFKD", (text or "").lower()) if not unicodedata.combining(ch))


def tokens(text: str) -> list[str]:
    return re.findall(r"[^\W_]+", fold(text), flags=re.UNICODE)


def query_terms(raw: str) -> list[tuple[str, bool]]:
    """(term, is_prefix) pairs mirroring `fts_query`: the last token of 3+ chars is a prefix."""
    words = [t for t in re.findall(r"[\w'’\-]+", raw, flags=re.UNICODE) if t.strip("-'’")]
    out: list[tuple[str, bool]] = []
    for index, word in enumerate(words):
        parts = tokens(word)
        for j, part in enumerate(parts):
            last = index == len(words) - 1 and j == len(parts) - 1
            out.append((part, last and len(word) >= 3))
    return out


def term_frequency(term: str, prefix: bool, toks: list[str]) -> int:
    if prefix:
        return sum(1 for t in toks if t.startswith(term))
    return sum(1 for t in toks if t == term)


@dataclass
class Candidate:
    id: int
    captured_at: float
    app: str
    window_title: str
    text: str
    snippet: str
    row: dict = field(default_factory=dict)


def idf(total: int, hits: int) -> float:
    return max(IDF_FLOOR, math.log(1.0 + (total - hits + 0.5) / (hits + 0.5)))


def score(candidate: Candidate, terms: list[tuple[str, bool]], idfs: dict[str, float], avg_text_len: float) -> float:
    columns = {"window_title": tokens(candidate.window_title), "app": tokens(candidate.app), "text": tokens(candidate.text)}
    text_len = len(columns["text"])
    norm = K1 * (1 - B + B * (text_len / avg_text_len if avg_text_len else 1.0))
    total = 0.0
    for term, prefix in terms:
        weighted_tf = 0.0
        for column, weight in WEIGHTS.items():
            tf = term_frequency(term, prefix, columns[column])
            if tf:
                weighted_tf += weight * tf * (K1 + 1) / (tf + (norm if column == "text" else K1))
        if weighted_tf:
            total += idfs.get(term, 1.0) * weighted_tf
    return total


def rank_candidates(candidates: list[Candidate], terms: list[tuple[str, bool]], idfs: dict[str, float], avg_text_len: float) -> list[tuple[Candidate, float]]:
    scored = [(c, -score(c, terms, idfs, avg_text_len)) for c in candidates]
    scored.sort(key=lambda pair: (pair[1], -pair[0].captured_at))
    return scored


def normalise_snippet(snippet: str) -> str:
    return " ".join(tokens(snippet.replace("[", "").replace("]", "")))


def group_moments(ranked: list[tuple[Candidate, float]], window_s: int = GROUP_WINDOW_S) -> list[dict]:
    """Collapse hits with the same app + window + snippet text seen within `window_s` of each other."""
    by_time = sorted(ranked, key=lambda pair: pair[0].captured_at)
    open_groups: dict[tuple, dict] = {}
    groups: list[dict] = []
    for candidate, rank in by_time:
        key = (candidate.app, candidate.window_title, normalise_snippet(candidate.snippet))
        group = open_groups.get(key)
        if group is not None and candidate.captured_at - group["last_at"] <= window_s:
            group["members"].append((candidate, rank))
            group["last_at"] = candidate.captured_at
            continue
        group = {"key": key, "members": [(candidate, rank)], "first_at": candidate.captured_at, "last_at": candidate.captured_at}
        open_groups[key] = group
        groups.append(group)
    out = []
    for group in groups:
        members = sorted(group["members"], key=lambda pair: (pair[1], -pair[0].captured_at))
        best, best_rank = members[0]
        out.append(
            {
                "best": best,
                "rank": best_rank,
                "first_at": group["first_at"],
                "last_at": max(c.captured_at for c, _ in members),
                "count": len(members),
                "frame_ids": [c.id for c, _ in members],
                "members": members,
            }
        )
    out.sort(key=lambda g: (g["rank"], -g["last_at"]))
    return out
