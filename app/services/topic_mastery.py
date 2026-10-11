"""
Spaced repetition of interview topics (Leitner boxes).

Each evaluated answer has a topic. Per user and topic we keep a box:
  score <  WEAK_BELOW   -> back to box 0 (due again from the next session)
  score >= STRONG_AT    -> up one box (review interval grows)
  otherwise             -> stay in the same box
A topic is "mastered" from MASTERED_BOX on; due topics below that come back in later sessions.
Times are naive UTC, matching the other timestamp columns.
"""

import re
import uuid as uuid_pkg
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TopicMastery

WEAK_BELOW = 70
STRONG_AT = 80
# Review interval per box. Box 0 is due immediately (but never re-asked in the same session).
BOX_INTERVALS = [timedelta(0), timedelta(days=1), timedelta(days=3), timedelta(days=7), timedelta(days=14), timedelta(days=30)]
MASTERED_BOX = 3
AVG_WEIGHT = 0.5  # weight of the newest score in the moving average
MAX_TOPIC_LENGTH = 60


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def normalize_topic(topic: Optional[str]) -> Optional[str]:
    if not topic:
        return None
    t = re.sub(r"\s+", " ", topic).strip().strip(".").lower()
    return t[:MAX_TOPIC_LENGTH] or None


def next_box(box: int, score: float) -> int:
    if score < WEAK_BELOW:
        return 0
    if score >= STRONG_AT:
        return min(box + 1, len(BOX_INTERVALS) - 1)
    return box


def status_of(row: TopicMastery) -> str:
    """'mastered' | 'learning' | 'weak'."""
    if row.box >= MASTERED_BOX:
        return "mastered"
    if row.box == 0:
        return "weak"
    return "learning"


async def record_attempt(
    db: AsyncSession,
    user_id: uuid_pkg.UUID,
    topic: Optional[str],
    score: float,
    now: Optional[datetime] = None,
) -> Optional[TopicMastery]:
    """Update the user's mastery of a topic after a scored answer. No-op without a topic."""
    topic = normalize_topic(topic)
    if topic is None or user_id is None:
        return None
    now = now or utcnow()
    result = await db.execute(
        select(TopicMastery).where(TopicMastery.user_id == user_id, TopicMastery.topic == topic)
    )
    row = result.scalar_one_or_none()
    if row is None:
        # New topics start in "learning"; a weak first score drops to box 0, a strong one moves up.
        row = TopicMastery(user_id=user_id, topic=topic, attempts=0, box=1)
    row.attempts += 1
    row.last_score = float(score)
    row.avg_score = float(score) if row.avg_score is None else round(
        AVG_WEIGHT * float(score) + (1 - AVG_WEIGHT) * row.avg_score, 1
    )
    row.box = next_box(row.box, score)
    row.last_seen_at = now
    row.next_due_at = now + BOX_INTERVALS[row.box]
    db.add(row)
    await db.commit()
    return row


async def due_weak_topics(
    db: AsyncSession,
    user_id: Optional[uuid_pkg.UUID],
    exclude: Sequence[str] = (),
    now: Optional[datetime] = None,
    limit: int = 3,
) -> List[str]:
    """Topics below MASTERED_BOX whose review is due, most overdue / weakest first."""
    if user_id is None:
        return []
    now = now or utcnow()
    excluded = {normalize_topic(t) for t in exclude}
    result = await db.execute(
        select(TopicMastery)
        .where(
            TopicMastery.user_id == user_id,
            TopicMastery.box < MASTERED_BOX,
            TopicMastery.next_due_at <= now,
        )
        .order_by(TopicMastery.box.asc(), TopicMastery.avg_score.asc().nulls_last(), TopicMastery.next_due_at.asc())
    )
    return [row.topic for row in result.scalars().all() if row.topic not in excluded][:limit]


async def list_mastery(db: AsyncSession, user_id: uuid_pkg.UUID) -> List[TopicMastery]:
    result = await db.execute(
        select(TopicMastery)
        .where(TopicMastery.user_id == user_id)
        .order_by(TopicMastery.box.asc(), TopicMastery.avg_score.asc().nulls_last())
    )
    return list(result.scalars().all())
