"""Exclusion rules: frames from matching apps/windows are never stored nor OCR'd."""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    id: int
    kind: str  # "app" | "title"
    pattern: str
    enabled: bool = True


def normalise_app(name: str) -> str:
    name = (name or "").strip().lower()
    return name[:-4] if name.endswith(".exe") else name


def validate_pattern(kind: str, pattern: str) -> str | None:
    """Return an error message, or None when the pattern is usable."""
    if kind not in ("app", "title"):
        return "kind must be 'app' or 'title'"
    if not pattern or not pattern.strip():
        return "pattern is empty"
    if len(pattern) > 300:
        return "pattern is too long"
    if kind == "title":
        try:
            re.compile(pattern, re.IGNORECASE)
        except re.error as error:
            return f"invalid regular expression: {error}"
    return None


def rule_matches(rule: Rule, app: str, title: str) -> bool:
    if not rule.enabled:
        return False
    if rule.kind == "app":
        return fnmatch.fnmatchcase(normalise_app(app), normalise_app(rule.pattern))
    try:
        return re.search(rule.pattern, title or "", re.IGNORECASE) is not None
    except re.error:
        return False


def first_match(rules: list[Rule], app: str, title: str) -> Rule | None:
    for rule in rules:
        if rule_matches(rule, app, title):
            return rule
    return None


def is_excluded(rules: list[Rule], app: str, title: str) -> bool:
    return first_match(rules, app, title) is not None
