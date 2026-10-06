"""Config flow for Translink Queensland integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import TranslinkApiError, TranslinkClient
from .const import (
    AVAILABLE_FARE_PREFERENCES,
    AVAILABLE_TIME_SEARCH_MODES,
    AVAILABLE_TRANSPORT_MODES,
    AVAILABLE_WALKING_SPEEDS,
    CONF_END_LOCATION_ID,
    CONF_END_NAME,
    CONF_FARE_PREFERENCE,
    CONF_MAX_WALKING_DISTANCE,
    CONF_MODE,
    CONF_NAME,
    CONF_SCAN_INTERVAL,
    CONF_START_LOCATION_ID,
    CONF_START_NAME,
    CONF_STOP_LOCATION_ID,
    CONF_STOP_NAME,
    CONF_TIME_SEARCH_MODE,
    CONF_TRACK_VEHICLE,
    CONF_TRANSPORT_MODES,
    CONF_WALKING_SPEED,
    DEFAULT_FARE_PREFERENCE,
    DEFAULT_MAX_WALKING_DISTANCE,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TIME_SEARCH_MODE,
    DEFAULT_TRACK_VEHICLE,
    DEFAULT_TRANSPORT_MODES,
    DEFAULT_WALKING_SPEED,
    DOMAIN,
    MIN_SCAN_INTERVAL,
    MODE_JOURNEY,
    MODE_STOP,
)

_LOGGER = logging.getLogger(__name__)


class TranslinkConfigFlow(  # pyright: ignore[reportGeneralTypeIssues, reportCallIssue]
    config_entries.ConfigFlow,
    domain=DOMAIN,
):
    """Handle a config flow for Translink Queensland."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._reconfigure_entry: config_entries.ConfigEntry | None = None

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> TranslinkOptionsFlowHandler:
        """Get the options flow for this handler."""
        return TranslinkOptionsFlowHandler()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial mode selection step."""
        if user_input is not None:
            mode = user_input.get(CONF_MODE, MODE_JOURNEY)
            if mode == MODE_JOURNEY:
                return await self.async_step_journey()
            return await self.async_step_stop()

        schema = vol.Schema(
            {
                vol.Required(CONF_MODE, default=MODE_JOURNEY): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(
                                value=MODE_JOURNEY,
                                label="Journey (Origin to Destination)",
                            ),
                            selector.SelectOptionDict(
                                value=MODE_STOP,
                                label="Stop / Station (Departure Board)",
                            ),
                        ],
                        mode=selector.SelectSelectorMode.LIST,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_journey(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle configuring a Journey between origin and destination."""
        errors: dict[str, str] = {}

        if user_input is not None:
            name = str(user_input.get(CONF_NAME, "")).strip() or "Translink Journey"
            start_query = str(user_input.get(CONF_START_NAME, "")).strip()
            end_query = str(user_input.get(CONF_END_NAME, "")).strip()
            transport_modes = user_input.get(
                CONF_TRANSPORT_MODES, DEFAULT_TRANSPORT_MODES
            )
            track_vehicle = bool(
                user_input.get(CONF_TRACK_VEHICLE, DEFAULT_TRACK_VEHICLE)
            )

            session = async_get_clientsession(self.hass)
            client = TranslinkClient(session=session)

            try:
                start_results = await client.search_locations(start_query)
                if not start_results:
                    errors[CONF_START_NAME] = "location_not_found"

                end_results = await client.search_locations(end_query)
                if not end_results:
                    errors[CONF_END_NAME] = "location_not_found"

                if not errors:
                    start_loc = start_results[0]
                    end_loc = end_results[0]

                    # Test plan
                    await client.plan_journey(
                        start_location_id=start_loc.LocationId,
                        start_name=start_loc.Description,
                        end_location_id=end_loc.LocationId,
                        end_name=end_loc.Description,
                        transport_modes=transport_modes,
                    )

                    unique_id = f"journey_{start_loc.LocationId}_{end_loc.LocationId}"
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured()

                    return self.async_create_entry(
                        title=name,
                        data={
                            CONF_MODE: MODE_JOURNEY,
                            CONF_NAME: name,
                            CONF_START_LOCATION_ID: start_loc.LocationId,
                            CONF_START_NAME: start_loc.Description,
                            CONF_END_LOCATION_ID: end_loc.LocationId,
                            CONF_END_NAME: end_loc.Description,
                            CONF_TRANSPORT_MODES: transport_modes,
                            CONF_TRACK_VEHICLE: track_vehicle,
                            CONF_TIME_SEARCH_MODE: DEFAULT_TIME_SEARCH_MODE,
                            CONF_MAX_WALKING_DISTANCE: DEFAULT_MAX_WALKING_DISTANCE,
                            CONF_WALKING_SPEED: DEFAULT_WALKING_SPEED,
                            CONF_FARE_PREFERENCE: DEFAULT_FARE_PREFERENCE,
                            CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
                        },
                    )
            except TranslinkApiError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error in journey config flow")
                errors["base"] = "unknown"

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_NAME, default="Daily Commute"
                ): selector.TextSelector(),
                vol.Required(CONF_START_NAME): selector.TextSelector(),
                vol.Required(CONF_END_NAME): selector.TextSelector(),
                vol.Required(
                    CONF_TRANSPORT_MODES, default=DEFAULT_TRANSPORT_MODES
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=AVAILABLE_TRANSPORT_MODES,
                        multiple=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    CONF_TRACK_VEHICLE, default=DEFAULT_TRACK_VEHICLE
                ): selector.BooleanSelector(),
            }
        )
        return self.async_show_form(
            step_id="journey", data_schema=schema, errors=errors
        )

    async def async_step_stop(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle configuring a Stop/Station departure board."""
        errors: dict[str, str] = {}

        if user_input is not None:
            name = str(user_input.get(CONF_NAME, "")).strip() or "Translink Stop"
            stop_query = str(user_input.get(CONF_STOP_NAME, "")).strip()
            transport_modes = user_input.get(
                CONF_TRANSPORT_MODES, DEFAULT_TRANSPORT_MODES
            )

            session = async_get_clientsession(self.hass)
            client = TranslinkClient(session=session)

            try:
                results = await client.search_locations(stop_query)
                if not results:
                    errors[CONF_STOP_NAME] = "location_not_found"
                else:
                    stop_loc = results[0]
                    unique_id = f"stop_{stop_loc.LocationId}"
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured()

                    return self.async_create_entry(
                        title=name,
                        data={
                            CONF_MODE: MODE_STOP,
                            CONF_NAME: name,
                            CONF_STOP_LOCATION_ID: stop_loc.LocationId,
                            CONF_STOP_NAME: stop_loc.Description,
                            CONF_TRANSPORT_MODES: transport_modes,
                            CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
                        },
                    )
            except TranslinkApiError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error in stop config flow")
                errors["base"] = "unknown"

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_NAME, default="Station Board"
                ): selector.TextSelector(),
                vol.Required(CONF_STOP_NAME): selector.TextSelector(),
                vol.Required(
                    CONF_TRANSPORT_MODES, default=DEFAULT_TRANSPORT_MODES
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=AVAILABLE_TRANSPORT_MODES,
                        multiple=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="stop", data_schema=schema, errors=errors)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of an existing entry."""
        self._reconfigure_entry = self._get_reconfigure_entry()
        if self._reconfigure_entry is None:
            return self.async_abort(reason="reconfigure_failed")
        current_data = self._reconfigure_entry.data
        mode = current_data.get(CONF_MODE, MODE_JOURNEY)

        errors: dict[str, str] = {}

        if user_input is not None:
            if mode == MODE_JOURNEY:
                start_query = str(user_input.get(CONF_START_NAME, "")).strip()
                end_query = str(user_input.get(CONF_END_NAME, "")).strip()
                session = async_get_clientsession(self.hass)
                client = TranslinkClient(session=session)

                try:
                    start_res = await client.search_locations(start_query)
                    end_res = await client.search_locations(end_query)
                    if not start_res:
                        errors[CONF_START_NAME] = "location_not_found"
                    if not end_res:
                        errors[CONF_END_NAME] = "location_not_found"

                    if not errors:
                        return self.async_update_reload_and_abort(
                            self._reconfigure_entry,
                            data={
                                **current_data,
                                CONF_START_LOCATION_ID: start_res[0].LocationId,
                                CONF_START_NAME: start_res[0].Description,
                                CONF_END_LOCATION_ID: end_res[0].LocationId,
                                CONF_END_NAME: end_res[0].Description,
                                CONF_TRANSPORT_MODES: user_input.get(
                                    CONF_TRANSPORT_MODES, DEFAULT_TRANSPORT_MODES
                                ),
                            },
                        )
                except TranslinkApiError:
                    errors["base"] = "cannot_connect"
                except Exception:
                    _LOGGER.exception("Unexpected error during journey reconfiguration")
                    errors["base"] = "unknown"
            else:
                stop_query = str(user_input.get(CONF_STOP_NAME, "")).strip()
                session = async_get_clientsession(self.hass)
                client = TranslinkClient(session=session)
                try:
                    res = await client.search_locations(stop_query)
                    if not res:
                        errors[CONF_STOP_NAME] = "location_not_found"
                    else:
                        return self.async_update_reload_and_abort(
                            self._reconfigure_entry,
                            data={
                                **current_data,
                                CONF_STOP_LOCATION_ID: res[0].LocationId,
                                CONF_STOP_NAME: res[0].Description,
                                CONF_TRANSPORT_MODES: user_input.get(
                                    CONF_TRANSPORT_MODES, DEFAULT_TRANSPORT_MODES
                                ),
                            },
                        )
                except TranslinkApiError:
                    errors["base"] = "cannot_connect"
                except Exception:
                    _LOGGER.exception("Unexpected error during stop reconfiguration")
                    errors["base"] = "unknown"

        if mode == MODE_JOURNEY:
            schema = vol.Schema(
                {
                    vol.Required(
                        CONF_START_NAME,
                        default=current_data.get(CONF_START_NAME, ""),
                    ): selector.TextSelector(),
                    vol.Required(
                        CONF_END_NAME,
                        default=current_data.get(CONF_END_NAME, ""),
                    ): selector.TextSelector(),
                    vol.Required(
                        CONF_TRANSPORT_MODES,
                        default=current_data.get(
                            CONF_TRANSPORT_MODES, DEFAULT_TRANSPORT_MODES
                        ),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=AVAILABLE_TRANSPORT_MODES,
                            multiple=True,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            )
        else:
            schema = vol.Schema(
                {
                    vol.Required(
                        CONF_STOP_NAME,
                        default=current_data.get(CONF_STOP_NAME, ""),
                    ): selector.TextSelector(),
                    vol.Required(
                        CONF_TRANSPORT_MODES,
                        default=current_data.get(
                            CONF_TRANSPORT_MODES, DEFAULT_TRANSPORT_MODES
                        ),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=AVAILABLE_TRANSPORT_MODES,
                            multiple=True,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            )

        return self.async_show_form(
            step_id="reconfigure", data_schema=schema, errors=errors
        )


class TranslinkOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle Translink options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage Translink options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        entry = self.config_entry
        current_data = {**entry.data, **entry.options}

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=current_data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL,
                        max=600,
                        step=10,
                        unit_of_measurement="seconds",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_TIME_SEARCH_MODE,
                    default=current_data.get(
                        CONF_TIME_SEARCH_MODE, DEFAULT_TIME_SEARCH_MODE
                    ),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=AVAILABLE_TIME_SEARCH_MODES,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    CONF_WALKING_SPEED,
                    default=current_data.get(CONF_WALKING_SPEED, DEFAULT_WALKING_SPEED),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=AVAILABLE_WALKING_SPEEDS,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    CONF_MAX_WALKING_DISTANCE,
                    default=current_data.get(
                        CONF_MAX_WALKING_DISTANCE, DEFAULT_MAX_WALKING_DISTANCE
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=500,
                        max=10000,
                        step=250,
                        unit_of_measurement="m",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_FARE_PREFERENCE,
                    default=current_data.get(
                        CONF_FARE_PREFERENCE, DEFAULT_FARE_PREFERENCE
                    ),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=AVAILABLE_FARE_PREFERENCES,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    CONF_TRACK_VEHICLE,
                    default=current_data.get(CONF_TRACK_VEHICLE, DEFAULT_TRACK_VEHICLE),
                ): selector.BooleanSelector(),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
