"""
Delivery metrics for spoken answers (voice mock interviews): words per minute, filler words,
answer length. Computed from the transcript and how long the candidate spoke.
"""

import re
from collections import Counter
from typing import Dict, List, Optional

# Multi-word fillers first so "you know" is not also counted as anything else.
FILLER_PATTERNS: List[tuple[str, str]] = [
    ("you know", r"\byou know\b"),
    ("i mean", r"\bi mean\b"),
    ("sort of", r"\bsort of\b"),
    ("kind of", r"\bkind of\b"),
    ("um", r"\bu+m+\b"),
    ("uh", r"\bu+h+\b"),
    ("er", r"\b(?:er|erm)\b"),
    ("basically", r"\bbasically\b"),
    ("literally", r"\bliterally\b"),
    ("actually", r"\bactually\b"),
    # "like" only as a filler: set off by commas ("it was, like, slow"), not "I'd like to".
    ("like", r"(?:^|,)\s*like\s*,"),
]
MIN_SECONDS_FOR_WPM = 5.0
# Comfortable interview pace; outside this range the report suggests slowing down / speeding up.
WPM_RANGE = (110, 170)


def count_words(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9']+", text))


def filler_counts(text: str) -> Counter:
    lowered = text.lower()
    counts: Counter = Counter()
    for name, pattern in FILLER_PATTERNS:
        n = len(re.findall(pattern, lowered))
        if n:
            counts[name] = n
    return counts


def analyze_delivery(text: str, speaking_seconds: Optional[float]) -> Dict[str, Optional[str]]:
    """Message meta (string values) for a spoken answer."""
    words = count_words(text)
    fillers = filler_counts(text)
    wpm = (
        round(words / (speaking_seconds / 60))
        if speaking_seconds is not None and speaking_seconds >= MIN_SECONDS_FOR_WPM
        else None
    )
    return {
        "spoken": "true",
        "speaking_seconds": str(round(speaking_seconds or 0, 1)),
        "word_count": str(words),
        "wpm": str(wpm) if wpm is not None else None,
        "filler_count": str(sum(fillers.values())),
        "fillers": ",".join(f"{k}:{v}" for k, v in fillers.most_common()) or None,
    }


def parse_fillers(value: Optional[str]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for part in (value or "").split(","):
        name, _, n = part.partition(":")
        if name and n.isdigit():
            out[name] = int(n)
    return out


def pace_hint(wpm: Optional[float]) -> Optional[str]:
    if wpm is None:
        return None
    if wpm < WPM_RANGE[0]:
        return "slow"
    if wpm > WPM_RANGE[1]:
        return "fast"
    return "good"
