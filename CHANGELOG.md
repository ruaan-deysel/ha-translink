# Changelog

All notable changes to this project are documented in this file.

This project uses Home Assistant's calendar versioning scheme (`YYYY.M.P`, for example `2026.10.0`).

## [2026.10.0] - 2026-10-06

### Added
- **Initial release of Translink Queensland integration for Home Assistant (HACS)**.
- **Journey Planner Tracking**:
  - Real-time journey planning between any Origin and Destination in South East Queensland and regional networks.
  - Sensors for Next Departure timestamp, Arrival timestamp, Total Duration, Status, Transfers count, Next Route / Service, Origin Platform, Adult Go Card Fare (50c fares), Walking Distance, and Disruption Alerts count.
  - Rich journey attributes including full leg breakdown, intermediate/skipped stops, operator info, route hex color codes, and encoded polyline for map cards.
- **Live Vehicle GPS Tracking**:
  - `device_tracker` entity providing live vehicle location (latitude, longitude), bearing, speed, and vehicle ID from Translink's GTFS Realtime feeds.
- **Stop & Station Departure Boards**:
  - Dedicated Stop mode for tracking upcoming departures, platforms, and line delays for any Translink bus stop, train station, ferry terminal, or tram station.
- **Location Autocomplete & Geolocation Support**:
  - Dynamic station/stop search via Translink's search API in config and options flows.
- **Home Assistant Integration Quality Scale (Platinum)**:
  - Strict type checking, Pydantic v2 data models, async I/O with injected websession.
  - Complete translations (`strings.json`, `translations/en.json`) and icon definitions (`icons.json`).
  - Redacted diagnostics download support.
  - Robust test suite with comprehensive unit and integration tests.
