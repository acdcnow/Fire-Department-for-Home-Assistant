"""The Fire Department Austria integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import (
    CONF_COLOR_SCHEME,
    CONF_FILTER_CATEGORIES,
    CONF_MAX_ITEMS,
    CONF_PAGE_KIND,
    CONF_PAGE_NAME,
    CONF_PAGE_PARSER,
    CONF_PAGE_URL,
    CONF_PAGE_WINDOW,
    CONF_PAGES,
    CONF_SOURCES,
    CONF_UPDATE_INTERVAL,
    CONFIG_ENTRY_MINOR_VERSION,
    CONFIG_ENTRY_VERSION,
    DEFAULT_COLOR_SCHEME,
    DEFAULT_MAX_ITEMS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    KIND_ACTIVE,
    KIND_HISTORY,
    KIND_UNITS,
    KIND_WINDOW,
    PARSER_WASTL_INCIDENTS,
    PARSER_WASTL_UNITS,
    SOURCES,
    build_sources,
)
from .coordinator import FireDepartmentCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = (Platform.SENSOR, Platform.BINARY_SENSOR)

#: config entry v1 stored the sensor name instead of the source id
LEGACY_KIND_NAMES = {
    KIND_ACTIVE: "active_operations",
    KIND_UNITS: "deployed_fire_brigade",
    KIND_HISTORY: "completed_missions",
}
#: ... and the old parser type instead of the parser id
LEGACY_PARSERS = {"departments": PARSER_WASTL_UNITS, "incidents": PARSER_WASTL_INCIDENTS}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the integration from a config entry."""
    sources = build_sources(entry.options)
    if not sources:
        _LOGGER.error(
            "Config entry %s does not contain a usable source, please reconfigure it",
            entry.entry_id,
        )
        return False

    coordinator = FireDepartmentCoordinator(
        hass,
        entry,
        sources,
        entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
        entry.options.get(CONF_COLOR_SCHEME, DEFAULT_COLOR_SCHEME),
        entry.options.get(CONF_FILTER_CATEGORIES) or [],
        entry.options.get(CONF_MAX_ITEMS, DEFAULT_MAX_ITEMS),
    )
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # changing the options reloads the entry, so a reload button is enough
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    _LOGGER.debug("Set up %s with %s sources", entry.title, len(sources))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry (options changed, manual reload, ...)."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate a version 1 entry (url list) to version 2 (source ids)."""
    if entry.version > CONFIG_ENTRY_VERSION:
        _LOGGER.error("Cannot downgrade fire_department entry from %s", entry.version)
        return False
    if entry.version == CONFIG_ENTRY_VERSION:
        return True

    options = dict(entry.options)
    known_by_url = {source["url"].lower(): source for source in SOURCES.values()}
    sources: dict[str, str] = {}
    custom: list[dict] = []

    for page in options.get(CONF_PAGES) or []:
        url = (page.get(CONF_PAGE_URL) or "").strip()
        parser = LEGACY_PARSERS.get(page.get("type", "incidents"), PARSER_WASTL_INCIDENTS)
        known = known_by_url.get(url.lower())
        if known and known["parser"] == parser and known["kind"] not in sources:
            sources[known["kind"]] = known["id"]
            continue
        kind = next(
            (
                candidate
                for candidate, name in LEGACY_KIND_NAMES.items()
                if name == page.get(CONF_PAGE_NAME)
            ),
            KIND_HISTORY,
        )
        custom.append(
            {
                CONF_PAGE_NAME: page.get(CONF_PAGE_NAME),
                CONF_PAGE_URL: url,
                CONF_PAGE_PARSER: parser,
                CONF_PAGE_KIND: kind,
                CONF_PAGE_WINDOW: KIND_WINDOW.get(kind, "custom"),
            }
        )

    if not sources:
        # no known page survived: fall back to the Lower Austrian defaults so
        # the entry keeps working instead of ending up without any source
        from .const import REGION_NOE, region_sources

        sources = {
            kind: source["id"] for kind, source in region_sources(REGION_NOE).items()
        }

    options[CONF_SOURCES] = sources
    options[CONF_PAGES] = custom
    options.setdefault(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
    options.setdefault(CONF_COLOR_SCHEME, DEFAULT_COLOR_SCHEME)
    options.setdefault(CONF_FILTER_CATEGORIES, [])
    options.setdefault(CONF_MAX_ITEMS, DEFAULT_MAX_ITEMS)

    hass.config_entries.async_update_entry(
        entry,
        options=options,
        version=CONFIG_ENTRY_VERSION,
        minor_version=CONFIG_ENTRY_MINOR_VERSION,
    )
    _LOGGER.info(
        "Migrated fire_department entry %s to version %s (sources: %s)",
        entry.entry_id,
        CONFIG_ENTRY_VERSION,
        ", ".join(sorted(sources)),
    )
    return True
