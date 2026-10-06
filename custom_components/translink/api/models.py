"""Pydantic v2 models for Translink Queensland payloads and summaries."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

type JourneyStatus = Literal[
    "scheduled",
    "on_time",
    "delayed",
    "departed",
    "arrived",
    "no_service",
]


class TranslinkApiModel(BaseModel):
    """Base model following Pydantic v2 conventions."""

    model_config = ConfigDict(
        extra="ignore",
        str_strip_whitespace=True,
        populate_by_name=True,
        validate_default=True,
    )


class LocationSearchResult(TranslinkApiModel):
    """Result from /api/location/search."""

    LocationId: str
    Description: str


class Position(TranslinkApiModel):
    """Geographic position coordinates."""

    lat: float
    lng: float


class StationInfo(TranslinkApiModel):
    """Station info."""

    id: str | None = None
    name: str | None = None
    stopType: str | None = None
    position: Position | None = None


class StopInfo(TranslinkApiModel):
    """Stop/platform info."""

    id: str | None = None
    name: str | None = None
    platform: str | None = None
    zone: str | None = None
    stopType: str | None = None
    position: Position | None = None
    station: StationInfo | None = None


class RouteLine(TranslinkApiModel):
    """Route line representation."""

    id: str | None = None
    name: str | None = None
    code: str | None = None
    textColorCode: str | None = None
    hexColorCode: str | None = None


class LegRoute(TranslinkApiModel):
    """Public transport route details."""

    id: str | None = None
    regionId: str | None = None
    regionName: str | None = None
    vehicle: str | None = None
    code: str | None = None
    direction: str | None = None
    isExpress: bool = False
    isFree: bool = False
    isPrepaid: bool = False
    isTransLinkService: bool = True
    isSchool: bool = False
    name: str | None = None
    headsign: str | None = None
    headsignShort: str | None = None
    operator: str | None = None
    hexColorCode: str | None = None
    textColorCode: str | None = None
    lines: list[RouteLine] = Field(default_factory=list)


class FareItem(TranslinkApiModel):
    """Fare details."""

    type: str
    name: str
    price: float = 0.0


class NoticeItem(TranslinkApiModel):
    """Notice or alert details."""

    id: int | str | None = None
    severity: str | None = None


class SkippedStop(TranslinkApiModel):
    """Intermediate / skipped stop."""

    id: str | None = None
    name: str | None = None


class JourneyLeg(TranslinkApiModel):
    """Single leg of a journey."""

    arrivalTimeUtc: str | None = None
    departureTimeUtc: str | None = None
    distanceM: int = 0
    durationMins: int = 0
    origin: StopInfo | None = None
    destination: StopInfo | None = None
    legRoute: LegRoute | None = None
    travelMode: str = "Walk"
    tripId: str | None = None
    tripHeadsign: str | None = None
    numberOfStops: int = 0
    skippedStops: list[SkippedStop] = Field(default_factory=list)
    sameVehicleContinuation: bool = False
    polyline: str | None = None
    maxNoticeSeverity: str | None = None
    notices: list[NoticeItem] = Field(default_factory=list)


class JourneyItinerary(TranslinkApiModel):
    """Single complete journey itinerary."""

    durationMins: int = 0
    endTimeUtc: str | None = None
    firstDepartureTimeUtc: str | None = None
    lastArrivalTimeUtc: str | None = None
    fares: list[FareItem] = Field(default_factory=list)
    legs: list[JourneyLeg] = Field(default_factory=list)


class JourneyPlanResult(TranslinkApiModel):
    """Response from /api/plan."""

    itineraries: list[JourneyItinerary] = Field(default_factory=list)


class JourneySummary(TranslinkApiModel):
    """Normalized, typed presentation summary for Home Assistant entities."""

    status: JourneyStatus = "scheduled"
    departure_time: datetime | None = None
    arrival_time: datetime | None = None
    duration_mins: int = 0
    transfers: int = 0
    next_service_name: str | None = None
    next_service_vehicle: str | None = None
    next_service_headsign: str | None = None
    next_service_route_code: str | None = None
    next_service_color: str | None = None
    operator: str | None = None
    origin_name: str = ""
    origin_platform: str | None = None
    destination_name: str = ""
    destination_platform: str | None = None
    fare_price: float | None = None
    fare_currency: str = "AUD"
    fare_type: str | None = None
    fares_breakdown: list[dict[str, Any]] = Field(default_factory=list)
    walking_distance_m: int = 0
    delay_mins: int = 0
    disruptions_count: int = 0
    disruptions: list[dict[str, Any]] = Field(default_factory=list)
    trip_id: str | None = None
    vehicle_id: str | None = None
    vehicle_label: str | None = None
    vehicle_latitude: float | None = None
    vehicle_longitude: float | None = None
    vehicle_bearing: float | None = None
    vehicle_speed: float | None = None
    vehicle_tracked: bool = False
    polyline: str | None = None
    itinerary_legs: list[dict[str, Any]] = Field(default_factory=list)
    last_updated: datetime | None = None


class StopDepartureItem(TranslinkApiModel):
    """Single departure item from a stop."""

    route_code: str
    route_name: str
    vehicle: str
    headsign: str
    departure_time: datetime | None = None
    platform: str | None = None
    delay_mins: int = 0
    trip_id: str | None = None


class StopSummary(TranslinkApiModel):
    """Normalized presentation summary for stop departure boards."""

    stop_id: str
    stop_name: str
    stop_type: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    next_departure_time: datetime | None = None
    next_route: str | None = None
    next_vehicle: str | None = None
    next_platform: str | None = None
    next_headsign: str | None = None
    delay_mins: int = 0
    departures: list[dict[str, Any]] = Field(default_factory=list)
    disruptions_count: int = 0
    disruptions: list[dict[str, Any]] = Field(default_factory=list)
    last_updated: datetime | None = None
