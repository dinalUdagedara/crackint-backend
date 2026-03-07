"""
Combined readiness score: CV score + session scores + gap severity.
"""

from typing import Literal, Optional

# Gap penalty by severity (subtract from 100 for the gap component)
GAP_PENALTY_HIGH = 15
GAP_PENALTY_MEDIUM = 8
GAP_PENALTY_LOW = 3

LAST_N_SESSIONS = 5


def _gap_penalty(severity: Optional[str]) -> float:
    """Return penalty to apply based on gap severity."""
    if not severity:
        return 0.0
    s = severity.lower()
    if s == "high":
        return GAP_PENALTY_HIGH
    if s == "medium":
        return GAP_PENALTY_MEDIUM
    if s == "low":
        return GAP_PENALTY_LOW
    return 0.0


def compute_combined_readiness(
    cv_score: Optional[float],
    session_avg: Optional[float],
    gap_severity: Optional[str],
) -> tuple[float, Literal["improving", "stable", "declining"]]:
    """
    Compute combined readiness score (0-100) and trend.

    Formula:
    - When all inputs: 0.3*cv + 0.6*session + 0.1*(100 - gap_penalty)
    - When cv_score missing: 0.6*session + 0.4*(100 - gap_penalty)
    - When session_avg missing: 0.7*cv + 0.3*(100 - gap_penalty)
    - When both cv and session missing: 100 - gap_penalty

    Trend is "stable" for now (could be extended with historical data).
    """
    gap_pen = _gap_penalty(gap_severity)
    gap_component = max(0, 100 - gap_pen)

    cv = cv_score if cv_score is not None else None
    sess = session_avg if session_avg is not None else None

    if cv is not None and sess is not None:
        combined = 0.3 * cv + 0.6 * sess + 0.1 * gap_component
    elif cv is not None and sess is None:
        combined = 0.7 * cv + 0.3 * gap_component
    elif cv is None and sess is not None:
        combined = 0.6 * sess + 0.4 * gap_component
    else:
        combined = gap_component

    combined = round(min(100, max(0, combined)), 1)
    trend: Literal["improving", "stable", "declining"] = "stable"
    return combined, trend
