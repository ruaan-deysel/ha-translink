"""Client module for the Translink integration."""

from .api.client import (
    TranslinkApiError,
    TranslinkClient,
    TranslinkConnectionError,
    TranslinkResponseError,
    build_journey_summary,
    calculate_plan_hash,
    parse_iso_datetime,
    redact_sensitive,
)
from .api.gtfs_realtime import (
    AlertRecord,
    TripUpdateRecord,
    VehiclePositionRecord,
    parse_alerts,
    parse_trip_updates,
    parse_vehicle_positions,
)
from .api.models import (
    JourneyPlanResult,
    JourneySummary,
    LocationSearchResult,
    StopSummary,
)

__all__ = [
    "AlertRecord",
    "JourneyPlanResult",
    "JourneySummary",
    "LocationSearchResult",
    "StopSummary",
    "TranslinkApiError",
    "TranslinkClient",
    "TranslinkConnectionError",
    "TranslinkResponseError",
    "TripUpdateRecord",
    "VehiclePositionRecord",
    "build_journey_summary",
    "calculate_plan_hash",
    "parse_alerts",
    "parse_iso_datetime",
    "parse_trip_updates",
    "parse_vehicle_positions",
    "redact_sensitive",
]
