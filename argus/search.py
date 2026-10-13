"""Ranking and grouping of search hits.

FTS5 finds the candidates, but its bm25() clamps a non-positive IDF to 1e-6:
when a term is on more than half of the frames (two hours on one page) every
rank collapses to about -1e-6, which rounds to -0.0 and drowns that term in
multi-word queries. So candidates are re-scored with the shared BM25
(`hoard_link.docs.textsearch.bm25_rescore`: smoothed IDF, always positive, taken
from whole-database counts) and per-column weights: window title 3, app 2, text 1.
Rank keeps the FTS5 convention: negative, lower is better.

Consecutive near-identical hits (same app, window and snippet text within ten
minutes) are then collapsed into one "moment" with first/last time, count and
the frame ids, best-ranked first.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .hoard_link.docs import textsearch

WEIGHTS = {"window_title": 3.0, "app": 2.0, "text": 1.0}
GROUP_WINDOW_S = 600
IDF_FLOOR = 0.1  # a term on every frame still ranks by where/how often it appears, with readable numbers


def scoring_terms(raw: str) -> list[tuple[str, bool]]:
    """(folded stem, is_prefix) for the words `textsearch.fts_query(raw, mode="prefix")` matches: the same words, so the
    document counts behind the IDF and the scoring agree with what FTS5 found."""
    return [(term, len(term) >= textsearch.PREFIX_MIN_CHARS) for term in textsearch.query_terms(raw)]


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
    """Smoothed BM25 IDF over the whole database (`total` frames, `hits` containing the term)."""
    return max(IDF_FLOOR, math.log(1.0 + (total - hits + 0.5) / (hits + 0.5)))


def rank_candidates(candidates: list[Candidate], terms: list[tuple[str, bool]], idfs: dict[str, float]) -> list[tuple[Candidate, float]]:
    """`(candidate, rank)` best first; rank is the negative BM25 score. Equal scores: the newer frame first."""
    rows = [{"window_title": c.window_title, "app": c.app, "text": c.text, "candidate": c}
            for c in sorted(candidates, key=lambda c: -c.captured_at)]
    scored = textsearch.bm25_rescore(rows, terms, weights=WEIGHTS, idfs=idfs, idf_floor=IDF_FLOOR)
    return [(row["candidate"], -score) for row, score in scored]


def normalise_snippet(snippet: str) -> str:
    return " ".join(textsearch.tokens(snippet.replace("[", "").replace("]", "")))


def group_moments(ranked: list[tuple[Candidate, float]], window_s: int = GROUP_WINDOW_S) -> list[dict]:
    """Collapse hits with the same app + window + snippet text seen within `window_s` of each other."""
    by_time = sorted(ranked, key=lambda pair: pair[0].captured_at)
    open_groups: dict[tuple, dict] = {}
    groups: list[dict] = []
    for candidate, rank in by_time:
        key = (candidate.row.get("origin", "capture"), candidate.app, candidate.window_title, normalise_snippet(candidate.snippet))
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
