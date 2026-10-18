from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, PlainSerializer


def utcnow() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def to_iso(value: datetime) -> str:
    """ISO-8601 in UTC without fractional seconds.

    The app decodes with `JSONDecoder.DateDecodingStrategy.iso8601`, which rejects
    fractional seconds, so never emit microseconds.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


UtcDatetime = Annotated[datetime, PlainSerializer(to_iso, return_type=str, when_used="json")]


class Contract(BaseModel):
    model_config = ConfigDict(use_enum_values=True, extra="ignore")


class HazardType(StrEnum):
    lightning = "lightning"
    flood = "flood"
    heat = "heat"
    wildfire = "wildfire"
    wildlife = "wildlife"
    soil_saturation = "soil_saturation"
    other = "other"


class AlertSeverity(StrEnum):
    advisory = "advisory"
    warning = "warning"
    stop_work = "stop_work"


class RiskLevel(StrEnum):
    low = "low"
    moderate = "moderate"
    high = "high"
    severe = "severe"

    @classmethod
    def from_index(cls, index: float) -> RiskLevel:
        # Same placeholder bands as the app's RiskLevel.
        if index < 3:
            return cls.low
        if index < 5.5:
            return cls.moderate
        if index < 8:
            return cls.high
        return cls.severe


class Role(StrEnum):
    supervisor = "supervisor"
    crew = "crew"
