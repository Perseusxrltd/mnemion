"""Explainable, inexpensive ordering of already authorized retrieval candidates."""

from datetime import datetime
import unicodedata

from .models import RankingPolicy


def archive_adjustment(path: str | None, policy: RankingPolicy) -> dict:
    directories = (
        unicodedata.normalize("NFC", path or "").replace("\\", "/").casefold().split("/")[:-1]
    )
    matched = next((part for part in directories if part in policy.archive_path_segments), None)
    return {
        "archive_factor": policy.archive_weight if matched is not None else 1.0,
        "archive_segment": matched,
    }


def adjustment(
    score: float, date: datetime, path: str | None, reference: datetime, policy: RankingPolicy
) -> dict:
    # Future provider dates receive no more weight than a source modified now.
    # A timestamp is an ordering hint, never evidence that a claim is current.
    age_days = max(0.0, (reference - date).total_seconds() / 86400)
    recency_factor = 1 - policy.recency_weight * (1 - 2 ** (-age_days / policy.half_life_days))
    archive = archive_adjustment(path, policy)
    return {
        "score": score * recency_factor * archive["archive_factor"],
        "date": date,
        "age_days": round(age_days, 6),
        "recency_factor": recency_factor,
        **archive,
    }
