# Changelog

All notable changes to this project are documented in this file.

This project uses Home Assistant's calendar versioning scheme (`YYYY.M.P`, for example `2026.10.0`).

## [2026.10.1] - 2026-10-06

### Added
- **Disruption Event Entity (`event.<entry>_disruption`)**:
  - Implements Home Assistant's native `event` entity platform (`EventEntity`) for service disruption alerts.
  - Fires `disruption` events containing full incident attributes (`title`, `description`, `cause`, `effect`, `severity`, `route`, and notice list) whenever disruptions are detected or updated.
  - Fires `cleared` events when service returns to normal, enabling instant automation triggers and smartphone push notifications.
- **Disruption Description Sensor (`sensor.<entry>_disruption_description`)**:
  - Diagnostic text sensor displaying the active disruption headline (or `Normal` when clear) directly on dashboards and glance cards.
  - Includes multi-line formatted summary and details in entity extra state attributes.
- **Enriched Disruption Sensor Attributes**:
  - `sensor.<entry>_disruptions` now provides `summary`, `description`, `latest_title`, `latest_description`, and structured disruption notice lists in addition to notice counts.
- **Comprehensive Notice Mapping**:
  - Added notice extraction and cross-referencing between itinerary legs and Translink notice feeds in `TranslinkApiClient`.

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
