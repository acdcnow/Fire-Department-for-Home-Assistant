"""The Fire Department integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_PAGES,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)
from .coordinator import FireDeptCoordinator

_LOGGER = logging.getLogger(__name__)

# 'sensor' provides the counts and the data_list attribute,
# 'geo_location' provides the markers for the built-in map card.
PLATFORMS = ["sensor", "geo_location"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Fire Department from a config entry."""
    pages = list(entry.options.get(CONF_PAGES, []))
    update_interval = entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)

    # One coordinator per entry, shared by all platforms.
    coordinator = FireDeptCoordinator(hass, pages, update_interval)
    if pages:
        await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Listen for options updates (to allow changing interval/pages without restart)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False

    coordinator: FireDeptCoordinator | None = hass.data.get(DOMAIN, {}).pop(
        entry.entry_id, None
    )
    if coordinator is not None:
        await coordinator.async_shutdown()
    return True

async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
