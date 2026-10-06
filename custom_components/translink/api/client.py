"""API client and data processing helpers for Translink Queensland."""

from __future__ import annotations

import logging
import urllib.parse
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

import aiohttp
from pydantic import ValidationError

from ..const import (
    BRISBANE_TZ,
    ENDPOINT_LOCATION_SEARCH,
    ENDPOINT_PLAN,
    ENDPOINT_STOP_BY_GEOLOCATION,
    GTFS_FEED_ALERTS,
    GTFS_FEED_TRIP_UPDATES,
    GTFS_FEED_VEHICLE_POSITIONS,
    GTFSRT_API_BASE_URL,
    JP_API_BASE_URL,
)
from .gtfs_realtime import (
    AlertRecord,
    TripUpdateRecord,
    VehiclePositionRecord,
    parse_alerts,
    parse_trip_updates,
    parse_vehicle_positions,
)
from .models import (
    JourneyPlanResult,
    JourneySummary,
    LocationSearchResult,
)

_LOGGER = logging.getLogger(__name__)

USER_AGENT = "HomeAssistant-Translink/2026.10.0"


class TranslinkApiError(Exception):
    """Base exception for Translink API failures."""


class TranslinkConnectionError(TranslinkApiError):
    """Raised when connection to Translink fails."""


class TranslinkResponseError(TranslinkApiError):
    """Raised when Translink returns an error status code."""


def calculate_plan_hash(query_string: str) -> int:
    """Calculate 32-bit signed hash matching Translink's frontend hash function."""
    h = 0
    for ch in query_string:
        h = ((h << 5) - h + ord(ch)) & 0xFFFFFFFF
        if h >= 0x80000000:
            h -= 0x100000000
    return h


def parse_iso_datetime(value: str | None) -> datetime | None:
    """Safely parse an ISO-8601 UTC timestamp string."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone(UTC)
    except (ValueError, TypeError):
        return None


SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "latitude",
        "longitude",
        "origin_latitude",
        "origin_longitude",
        "destination_latitude",
        "destination_longitude",
        "lat",
        "lng",
        "api_key",
        "token",
        "password",
        "secret",
    }
)


def redact_sensitive(data: Any) -> Any:
    """Recursively redact sensitive data for diagnostics."""
    if isinstance(data, dict):
        return {
            k: "**REDACTED**" if str(k).lower() in SENSITIVE_KEYS else redact_sensitive(v)
            for k, v in data.items()
        }
    if isinstance(data, list):
        return [redact_sensitive(item) for item in data]
    return data


class TranslinkClient:
    """Asynchronous client for Translink Queensland APIs and GTFS Realtime feeds."""

    def __init__(
        self,
        session: aiohttp.ClientSession | None = None,
        jp_base_url: str = JP_API_BASE_URL,
        gtfsrt_base_url: str = GTFSRT_API_BASE_URL,
    ) -> None:
        """Initialize the client."""
        self._session = session
        self._owns_session = session is None
        self._jp_base_url = jp_base_url.rstrip("/")
        self._gtfsrt_base_url = gtfsrt_base_url.rstrip("/")

    async def _get_session(self) -> aiohttp.ClientSession:
        """Ensure an active aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers={"User-Agent": USER_AGENT})
            self._owns_session = True
        return self._session

    async def close(self) -> None:
        """Close the underlying session if owned."""
        if self._owns_session and self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def search_locations(self, query: str) -> list[LocationSearchResult]:
        """Search for stops, stations, and locations matching the query."""
        if not query or len(query.strip()) < 2:
            return []

        session = await self._get_session()
        url = f"{self._jp_base_url}{ENDPOINT_LOCATION_SEARCH}"
        params = {"location": query.strip()}

        try:
            async with session.get(
                url,
                params=params,
                headers={"Accept": "application/json, text/plain, */*"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status != 200:
                    text = await response.text()
                    raise TranslinkResponseError(
                        f"Location search failed with status {response.status}: {text}"
                    )
                payload = await response.json()
                if not isinstance(payload, list):
                    return []
                try:
                    return [
                        LocationSearchResult.model_validate(item) for item in payload
                    ]
                except ValidationError as err:
                    raise TranslinkResponseError(
                        f"Failed to parse location search response: {err}"
                    ) from err
        except aiohttp.ClientError as err:
            raise TranslinkConnectionError(
                f"Error connecting to Translink location search: {err}"
            ) from err

    async def get_stops_by_geolocation(
        self, lat: float, lng: float, max_results: int = 10
    ) -> list[dict[str, Any]]:
        """Find nearby transit stops given latitude and longitude."""
        session = await self._get_session()
        url = f"{self._jp_base_url}{ENDPOINT_STOP_BY_GEOLOCATION}"
        params = {
            "lat": str(lat),
            "lng": str(lng),
            "maxResults": str(max_results),
        }

        try:
            async with session.get(
                url,
                params=params,
                headers={"Accept": "application/json, text/plain, */*"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status != 200:
                    text = await response.text()
                    raise TranslinkResponseError(
                        f"Geolocation stop search failed with status {response.status}: {text}"
                    )
                data = await response.json()
                return data if isinstance(data, list) else []
        except aiohttp.ClientError as err:
            raise TranslinkConnectionError(
                f"Error connecting to Translink geolocation stop search: {err}"
            ) from err

    async def plan_journey(
        self,
        start_location_id: str,
        start_name: str,
        end_location_id: str,
        end_name: str = "",
        transport_modes: list[str] | None = None,
        time_search_mode: str = "LeaveAfter",
        max_walking_distance: int = 4000,
        walking_speed: str = "Normal",
        target_datetime: datetime | None = None,
    ) -> JourneyPlanResult:
        """Plan journey between starting point and destination."""
        session = await self._get_session()

        tz = ZoneInfo(BRISBANE_TZ)
        now_brisbane = (target_datetime or datetime.now(tz)).astimezone(tz)
        search_date = now_brisbane.strftime("%Y-%m-%d")
        search_time = now_brisbane.strftime("%-I:%M%p").lower()

        modes = transport_modes or ["Bus", "Ferry", "Train", "Tram"]

        # Build urlencoded parameters
        params: list[tuple[str, str]] = [
            ("searchDate", search_date),
            ("searchTime", search_time),
            ("startLocationId", start_location_id),
            ("start", start_name),
            ("endLocationId", end_location_id),
            ("end", end_name),
            ("timeSearchMode", time_search_mode),
            ("maximumWalkingDistance", str(max_walking_distance)),
            ("walkingSpeed", walking_speed),
        ]

        for m in modes:
            params.append(("transportModes", m))
        for st in ["Express", "NightLink", "Regular", "School"]:
            params.append(("serviceTypes", st))
        for ft in ["Free", "Prepaid", "Standard"]:
            params.append(("fareTypes", ft))

        body_string = urllib.parse.urlencode(params)
        plan_id = calculate_plan_hash(body_string)
        url = f"{self._jp_base_url}{ENDPOINT_PLAN}?id={plan_id}"

        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Accept": "application/json, text/plain, */*",
            "Origin": self._jp_base_url,
            "Referer": f"{self._jp_base_url}/plan-your-journey/journey-planner",
        }

        try:
            async with session.post(
                url,
                data=body_string,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as response:
                if response.status != 200:
                    text = await response.text()
                    raise TranslinkResponseError(
                        f"Journey planner failed with status {response.status}: {text}"
                    )
                payload = await response.json()
                try:
                    return JourneyPlanResult.model_validate(payload)
                except ValidationError as err:
                    raise TranslinkResponseError(
                        f"Failed to parse journey planner response: {err}"
                    ) from err
        except aiohttp.ClientError as err:
            raise TranslinkConnectionError(
                f"Error connecting to Translink journey planner: {err}"
            ) from err

    async def fetch_vehicle_positions(self) -> dict[str, VehiclePositionRecord]:
        """Fetch and parse live vehicle positions from Translink GTFS-RT feed."""
        session = await self._get_session()
        url = f"{self._gtfsrt_base_url}{GTFS_FEED_VEHICLE_POSITIONS}"

        try:
            async with session.get(
                url,
                headers={"Accept": "application/x-protobuf"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status != 200:
                    _LOGGER.warning(
                        "VehiclePositions feed returned status %s", response.status
                    )
                    return {}
                data = await response.read()
                return parse_vehicle_positions(data)
        except aiohttp.ClientError as err:
            _LOGGER.debug("Failed to fetch live vehicle positions feed: %s", err)
            return {}

    async def fetch_trip_updates(self) -> dict[str, TripUpdateRecord]:
        """Fetch and parse live trip delays from Translink GTFS-RT feed."""
        session = await self._get_session()
        url = f"{self._gtfsrt_base_url}{GTFS_FEED_TRIP_UPDATES}"

        try:
            async with session.get(
                url,
                headers={"Accept": "application/x-protobuf"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status != 200:
                    _LOGGER.warning(
                        "TripUpdates feed returned status %s", response.status
                    )
                    return {}
                data = await response.read()
                return parse_trip_updates(data)
        except aiohttp.ClientError as err:
            _LOGGER.debug("Failed to fetch live trip updates feed: %s", err)
            return {}

    async def fetch_alerts(self) -> list[AlertRecord]:
        """Fetch and parse live service disruptions from Translink GTFS-RT feed."""
        session = await self._get_session()
        url = f"{self._gtfsrt_base_url}{GTFS_FEED_ALERTS}"

        try:
            async with session.get(
                url,
                headers={"Accept": "application/x-protobuf"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status != 200:
                    return []
                data = await response.read()
                return parse_alerts(data)
        except aiohttp.ClientError as err:
            _LOGGER.debug("Failed to fetch live alerts feed: %s", err)
            return []


def build_journey_summary(
    plan: JourneyPlanResult,
    vehicle_positions: dict[str, VehiclePositionRecord] | None = None,
    trip_updates: dict[str, TripUpdateRecord] | None = None,
    fare_preference: str = "Adult",
    origin_name_fallback: str = "",
    destination_name_fallback: str = "",
    now: datetime | None = None,
) -> JourneySummary:
    """Build a unified presentation summary for Home Assistant sensors."""
    if now is None:
        now = datetime.now(UTC)

    if not plan.itineraries:
        return JourneySummary(
            status="no_service",
            origin_name=origin_name_fallback,
            destination_name=destination_name_fallback,
            last_updated=now,
        )

    itinerary = plan.itineraries[0]
    departure_time = parse_iso_datetime(itinerary.firstDepartureTimeUtc)
    arrival_time = parse_iso_datetime(itinerary.lastArrivalTimeUtc)

    # Find the primary transit leg (first non-walking leg, or first leg)
    transit_legs = [leg for leg in itinerary.legs if leg.travelMode.lower() != "walk"]
    primary_leg = (
        transit_legs[0]
        if transit_legs
        else (itinerary.legs[0] if itinerary.legs else None)
    )

    transfers = max(0, len(transit_legs) - 1)

    next_service_name: str | None = None
    next_service_vehicle: str | None = None
    next_service_headsign: str | None = None
    next_service_route_code: str | None = None
    next_service_color: str | None = None
    operator: str | None = None
    origin_name = origin_name_fallback
    origin_platform: str | None = None
    destination_name = destination_name_fallback
    destination_platform: str | None = None
    trip_id: str | None = None
    polyline: str | None = None

    if primary_leg:
        trip_id = primary_leg.tripId
        polyline = primary_leg.polyline
        if primary_leg.legRoute:
            next_service_name = primary_leg.legRoute.name
            next_service_vehicle = primary_leg.legRoute.vehicle
            next_service_headsign = primary_leg.legRoute.headsign
            next_service_route_code = primary_leg.legRoute.code
            next_service_color = primary_leg.legRoute.hexColorCode
            operator = primary_leg.legRoute.operator
        else:
            next_service_name = primary_leg.travelMode
            next_service_vehicle = primary_leg.travelMode

        if primary_leg.origin:
            origin_name = primary_leg.origin.name or origin_name_fallback
            origin_platform = primary_leg.origin.platform

    last_leg = itinerary.legs[-1] if itinerary.legs else None
    if last_leg and last_leg.destination:
        destination_name = last_leg.destination.name or destination_name_fallback
        destination_platform = last_leg.destination.platform

    # Calculate walking distance
    walking_distance = sum(
        leg.distanceM for leg in itinerary.legs if leg.travelMode.lower() == "walk"
    )

    # Process fares
    fare_price: float | None = None
    fare_type_chosen: str | None = None
    fares_breakdown: list[dict[str, Any]] = []

    is_concession = "concession" in fare_preference.lower()
    for fare in itinerary.fares:
        fares_breakdown.append(
            {"type": fare.type, "name": fare.name, "price": fare.price}
        )
        if fare_price is None and (
            (
                is_concession
                and "concession" in fare.type.lower()
                and "paper" not in fare.type.lower()
            )
            or (
                not is_concession
                and "adult" in fare.type.lower()
                and "paper" not in fare.type.lower()
            )
        ):
            fare_price = fare.price
            fare_type_chosen = fare.name

    if fare_price is None and itinerary.fares:
        fare_price = itinerary.fares[0].price
        fare_type_chosen = itinerary.fares[0].name

    # Check delays via TripUpdates
    delay_mins = 0
    if trip_updates and trip_id and trip_id in trip_updates:
        tu = trip_updates[trip_id]
        delay_mins = max(0, round(tu.delay_seconds / 60))

    # Determine status
    status = "scheduled"
    if departure_time and arrival_time:
        if now > arrival_time:
            status = "arrived"
        elif departure_time <= now <= arrival_time:
            status = "departed"
        elif delay_mins >= 3:
            status = "delayed"
        else:
            status = "on_time"

    # Correlate live vehicle tracking via VehiclePositions
    veh_id: str | None = None
    veh_label: str | None = None
    veh_lat: float | None = None
    veh_lng: float | None = None
    veh_bearing: float | None = None
    veh_speed: float | None = None
    veh_tracked = False

    if vehicle_positions and trip_id and trip_id in vehicle_positions:
        vp = vehicle_positions[trip_id]
        veh_id = vp.vehicle_id or vp.entity_id
        veh_label = vp.vehicle_label
        veh_lat = vp.latitude
        veh_lng = vp.longitude
        veh_bearing = vp.bearing
        veh_speed = vp.speed
        veh_tracked = True
    elif primary_leg and primary_leg.origin and primary_leg.origin.position:
        # Fallback to origin platform/station coordinates
        veh_lat = primary_leg.origin.position.lat
        veh_lng = primary_leg.origin.position.lng

    # Aggregate disruptions
    disruptions: list[dict[str, Any]] = []
    for leg in itinerary.legs:
        for notice in leg.notices:
            disruptions.append(
                {
                    "id": notice.id,
                    "severity": notice.severity,
                    "leg": leg.travelMode,
                    "route": leg.legRoute.name if leg.legRoute else None,
                }
            )

    # Detailed legs representation
    legs_summary: list[dict[str, Any]] = []
    for leg in itinerary.legs:
        legs_summary.append(
            {
                "travelMode": leg.travelMode,
                "durationMins": leg.durationMins,
                "distanceM": leg.distanceM,
                "departureTimeUtc": leg.departureTimeUtc,
                "arrivalTimeUtc": leg.arrivalTimeUtc,
                "origin": leg.origin.name if leg.origin else None,
                "originPlatform": leg.origin.platform if leg.origin else None,
                "destination": leg.destination.name if leg.destination else None,
                "destinationPlatform": leg.destination.platform
                if leg.destination
                else None,
                "route": leg.legRoute.name if leg.legRoute else None,
                "routeCode": leg.legRoute.code if leg.legRoute else None,
                "routeColor": leg.legRoute.hexColorCode if leg.legRoute else None,
                "operator": leg.legRoute.operator if leg.legRoute else None,
                "numberOfStops": leg.numberOfStops,
                "skippedStops": [s.name for s in leg.skippedStops],
            }
        )

    return JourneySummary(
        status=status,
        departure_time=departure_time,
        arrival_time=arrival_time,
        duration_mins=itinerary.durationMins,
        transfers=transfers,
        next_service_name=next_service_name,
        next_service_vehicle=next_service_vehicle,
        next_service_headsign=next_service_headsign,
        next_service_route_code=next_service_route_code,
        next_service_color=next_service_color,
        operator=operator,
        origin_name=origin_name,
        origin_platform=origin_platform,
        destination_name=destination_name,
        destination_platform=destination_platform,
        fare_price=fare_price,
        fare_currency="AUD",
        fare_type=fare_type_chosen,
        fares_breakdown=fares_breakdown,
        walking_distance_m=walking_distance,
        delay_mins=delay_mins,
        disruptions_count=len(disruptions),
        disruptions=disruptions,
        trip_id=trip_id,
        vehicle_id=veh_id,
        vehicle_label=veh_label,
        vehicle_latitude=veh_lat,
        vehicle_longitude=veh_lng,
        vehicle_bearing=veh_bearing,
        vehicle_speed=veh_speed,
        vehicle_tracked=veh_tracked,
        polyline=polyline,
        itinerary_legs=legs_summary,
        last_updated=now,
    )
